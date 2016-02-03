#-------------------------------------------------------------------------------
# Name: NHD-WBD Update QC process
# Purpose: Identifies the lowest point within a WBD polygon associated with the
# NHD flowlines.  Currently this is set as a funciton of a larger WBD/NHD data
# integration and the idenification of errors arising from the update of the
# NHD.
#
# Author:      Alex Headman (aheadman@usgs.gov)
#
# Created:     20/01/2016
# Copyright:   Created under GNU-GPL
#
#-------------------------------------------------------------------------------

# Import arcpy modules and check out spatial extension

import arcpy
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *

# variable definition, ideally this will be user defined and filter into a
# function.

env.workspace = env.scratchWorkspace = r'D:\GIS\AlaskaCode\ucrbtest.gdb'
env.overwriteOutput = True

StrLines = "NHD1406Extract"
DEM = "BigAssDEMvSix1"
##WBDPoly = "Huc12Export2"
WBDLine = "WBDLine"
PourPoints = 'PourPoints'
HucsIn = "WBDHU12"

spatial_ref = arcpy.Describe(StrLines)
spatial_ref = spatial_ref.spatialReference


# In the immortal words of Samuel L. Jackson - "Hold onto your butts"

def PourLinesAndPoints (StrLines, DEM, WBDPoly, WBDLine):
    # Creates a clip mask based on the selected WBD Polygon, does general dissolve stuff
    # To make the SA tools run in a sane time over larger datasets (NHD Lines, DEM, WBDLine, WBDPoly)

    StrClip = "StrClip"
    arcpy.Clip_analysis(StrLines, WBDPoly, StrClip)
    DissolveOut = "Dissolve"
    arcpy.Dissolve_management(StrClip, DissolveOut)
    MP2SP = "MP2SP"
    arcpy.MultipartToSinglepart_management(DissolveOut, MP2SP)

    # Buffer streams is currently set to 30 meters to account for 2x error at 1:24000
    # This can be adjusted.

    BufferOut = "Buffer"
    arcpy.Buffer_analysis(MP2SP, BufferOut, "30 Meters", "FULL", "FLAT", "NONE")

    # Extracts the DEM based on the NHD Buffers and clips that to the extent of the WBD Polygon

    DEMMask = ExtractByMask(DEM, BufferOut)
    DEMMask = ExtractByMask(DEMMask, WBDPoly)
    MaskExtract = "MaskExtract"
    DEMMask.save(MaskExtract)
    mini = arcpy.GetRasterProperties_management(MaskExtract, "MINIMUM")

    # Raster math to tease out the low point in the NHD values. relative to the WBD polygon.
    outRast = 'outRast'
    outRas = Con(Raster(MaskExtract), 1, "", "Value =" +str(mini))
    outRas.save(outRast)
    LowPolys = "LowPolys"
    arcpy.RasterToPolygon_conversion(outRas, LowPolys)

    # Buffers the low polygons to account for 2x 1:24000 acceptable error.  Selects the
    # applicable NHD lines and passes them to a new feautre class.  Also creates an outlet
    # point.

    LowPolysBuffer = 'LowPolysBuffer'
    arcpy.Buffer_analysis(LowPolys, LowPolysBuffer, "30 Meters")
    arcpy.MakeFeatureLayer_management(StrClip, 'StrLines_lyr')
    arcpy.SelectLayerByLocation_management('StrLines_lyr', 'intersect', LowPolysBuffer)
    lines = arcpy.CopyFeatures_management('StrLines_lyr', 'NHDPourPointLine')
    arcpy.MakeFeatureLayer_management('NHDPourPointLine', 'NHDPPLine_lyr')
    arcpy.SelectLayerByLocation_management('NHDPPLine_lyr', 'intersect', WBDLine)
    lines = arcpy.CopyFeatures_management('NHDPPLine_lyr', 'NHDPourPointLine_final')
    points = arcpy.FeatureVerticesToPoints_management('NHDPourPointLine_final', 'NHDPourPoint', "END", )
    PourPoints = 'PourPoints'
    PourLines = 'PourLines'
    if arcpy.Exists(PourLines):
        arcpy.Append_management(lines, PourLines, "NO_TEST", "", "")
    else:
        arcpy.CreateFeatureclass_management(env.workspace, PourLines, "POLYLINE", lines, "", "", spatial_reference=spatial_ref)
        arcpy.Append_management(lines, PourLines, "NO_TEST", "", "")

    if arcpy.Exists(PourPoints):
        arcpy.Append_management(points, PourPoints, "NO_TEST", "", "")
    else:
        arcpy.CreateFeatureclass_management(env.workspace, PourPoints, "POINT", points, spatial_reference=spatial_ref)
        arcpy.Append_management(points, PourPoints, "NO_TEST", "", "")

    #Clean up, PourLines and PourPoints are the output files from this function
    rmlist = ['StrClip', 'MP2SP', 'Buffer', 'MaskExtract', 'OutRast', 'LowPolys', 'LowPolysBuffer', 'NHDPourPointLine', 'NHDPourPointLine_final', 'NHDPourPoint', 'Buffer', 'Dissolve']
    for x in rmlist:
        arcpy.Delete_management(x)


def BufferAnalysis(StrLines, WBDPoly, PourPoints):
    # Buffers the NHD Polygons, selects the lines and exports them to an error file. (WBD Poly, NHD Lines, PourPoints)

    PolyBuff = arcpy.Buffer_analysis(WBDPoly, 'WBDPoly_Buffer', "30 Meters", "FULL")
    arcpy.MakeFeatureLayer_management(StrLines, 'StrLines_lyr')
    arcpy.SelectLayerByLocation_management('StrLines_lyr', 'CROSSED_BY_THE_OUTLINE_OF', 'WBDPoly_Buffer')
    IntersectError = "NHDBufferIntersect_Error"
    lines = arcpy.CopyFeatures_management('StrLines_lyr', 'Line_Error')
    if arcpy.Exists(IntersectError):
        arcpy.Append_management(lines, IntersectError, "NO_TEST", "", "")
    else:
        arcpy.CreateFeatureclass_management(env.workspace, IntersectError, "POLYLINE", lines, spatial_reference=spatial_ref)
        arcpy.Append_management(lines, IntersectError, "NO_TEST", "", "")


    # Buffers the pour points and exports them to a notError files for correction, then removes them
    # from the error file.  Not error file is retained for comparision.

    PPBuff = arcpy.Buffer_analysis(PourPoints, 'PP_Buffer', "30 Meters")
    BuffSelect = arcpy.SelectLayerByLocation_management('StrLines_lyr', 'intersect', 'PP_Buffer')
    lines = arcpy.CopyFeatures_management('StrLines_lyr', 'Line_NotError')
    NotIntersectError = "NHDBufferIntersect_NotError"
    if arcpy.Exists(NotIntersectError):
        arcpy.Append_management(lines, NotIntersectError, "NO_TEST", "", "")
    else:
        arcpy.CreateFeatureclass_management(env.workspace, NotIntersectError, "POLYLINE", lines, spatial_reference=spatial_ref)
        arcpy.Append_management(lines, NotIntersectError, "NO_TEST", "", "")

    arcpy.MakeFeatureLayer_management(IntersectError, 'IntersectError_lyr')
    check = arcpy.SelectLayerByLocation_management('IntersectError_Lyr', 'ARE_IDENTICAL_TO', NotIntersectError)
    if int(arcpy.GetCount_management(check).getOutput(0)) > 0:
         arcpy.DeleteFeatures_management(check)

    #Clean up, NHDBufferIntersectError and _NotError are retained as the output files
    #from this function. PourPoint Buffer and WBDPoly_Buffer are appended to a master
    #file for each of them.
    PointBuffers = 'PourPointBuffers_'
    WBDPolyBuffers = 'WBDPolyBuffers'
    if arcpy.Exists(PointBuffers):
        arcpy.Append_management(PPBuff, PointBuffers, "NO_TEST", "", "")
    else:
        arcpy.CreateFeatureclass_management(env.workspace, PointBuffers, "POLYGON", PPBuff, spatial_reference=spatial_ref)
        arcpy.Append_management(PPBuff, PointBuffers, "NO_TEST", "", "")
    if arcpy.Exists(WBDPolyBuffers):
        arcpy.Append_management(PolyBuff, WBDPolyBuffers, "NO_TEST", "", "")
    else:
        arcpy.CreateFeatureclass_management(env.workspace, WBDPolyBuffers, "POLYGON", PolyBuff, spatial_reference=spatial_ref)
        arcpy.Append_management(PolyBuff, WBDPolyBuffers, "NO_TEST", "", "")
    rmlist = ['Line_Error', 'Line_NotError', 'PP_Buffer', 'WBDPoly_Buffer']
    for x in rmlist:
        arcpy.Delete_management(x)

arcpy.MakeFeatureLayer_management(HucsIn, "Huc_lyr")
sc = arcpy.SearchCursor("Huc_lyr")
for feat in sc:
    expression= "TNMID" + "='" + feat.getValue("TNMID") + "'"
    select = arcpy.SelectLayerByAttribute_management('Huc_lyr', "NEW_SELECTION", expression)
    WBDPoly = arcpy.CopyFeatures_management("Huc_lyr", 'WBDTemp')
    PourLinesAndPoints(StrLines, DEM, WBDPoly, WBDLine)
    BufferAnalysis(StrLines, WBDPoly, PourPoints)
arcpy.Delete_management(WBDPoly)
