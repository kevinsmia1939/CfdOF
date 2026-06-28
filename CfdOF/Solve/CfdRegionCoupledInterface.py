# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD
import Part

from CfdOF import CfdTools
from CfdOF.CfdTools import addObjectProperty

if FreeCAD.GuiUp:
    import FreeCADGui


QT_TRANSLATE_NOOP = FreeCAD.Qt.QT_TRANSLATE_NOOP


def makeCfdRegionCoupledInterface(name="CfdRegionCoupledInterface"):
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    CfdRegionCoupledInterface(obj)
    if FreeCAD.GuiUp:
        ViewProviderCfdRegionCoupledInterface(obj.ViewObject)
    return obj


class CommandCfdRegionCoupledInterface:
    def GetResources(self):
        icon_path = os.path.join(CfdTools.getModulePath(), "Gui", "Icons", "region_coupled_interface.svg")
        return {
            'Pixmap': icon_path,
            'MenuText': QT_TRANSLATE_NOOP("CfdOF_RegionCoupledInterface", "Region-coupled interface"),
            'ToolTip': QT_TRANSLATE_NOOP(
                "CfdOF_RegionCoupledInterface",
                "Creates a paired multi-region interface for non-conformal CHT coupling")}

    def IsActive(self):
        return CfdTools.getActiveAnalysis() is not None

    def Activated(self):
        FreeCAD.ActiveDocument.openTransaction("Create CfdRegionCoupledInterface")
        FreeCADGui.doCommand("from CfdOF.Solve import CfdRegionCoupledInterface")
        FreeCADGui.doCommand("from CfdOF import CfdTools")
        FreeCADGui.doCommand(
            "CfdTools.getActiveAnalysis().addObject("
            "CfdRegionCoupledInterface.makeCfdRegionCoupledInterface())")
        FreeCADGui.ActiveDocument.setEdit(FreeCAD.ActiveDocument.ActiveObject.Name)


class CfdRegionCoupledInterface:
    def __init__(self, obj):
        self.initProperties(obj)

    def initProperties(self, obj):
        obj.Proxy = self
        self.Type = 'CfdRegionCoupledInterface'

        addObjectProperty(
            obj,
            "Region1Name",
            "",
            "App::PropertyString",
            "Region 1",
            QT_TRANSLATE_NOOP("App::Property", "OpenFOAM region name for side 1"),
        )
        addObjectProperty(
            obj,
            "ShapeRefs1",
            [],
            "App::PropertyLinkSubListGlobal",
            "Region 1",
            QT_TRANSLATE_NOOP("App::Property", "Faces on side 1 of the interface"),
        )
        addObjectProperty(
            obj,
            "Patch1Name",
            "",
            "App::PropertyString",
            "Region 1",
            QT_TRANSLATE_NOOP("App::Property", "OpenFOAM patch name for side 1; defaults to region1_to_region2"),
        )

        addObjectProperty(
            obj,
            "Region2Name",
            "",
            "App::PropertyString",
            "Region 2",
            QT_TRANSLATE_NOOP("App::Property", "OpenFOAM region name for side 2"),
        )
        addObjectProperty(
            obj,
            "ShapeRefs2",
            [],
            "App::PropertyLinkSubListGlobal",
            "Region 2",
            QT_TRANSLATE_NOOP("App::Property", "Faces on side 2 of the interface"),
        )
        addObjectProperty(
            obj,
            "Patch2Name",
            "",
            "App::PropertyString",
            "Region 2",
            QT_TRANSLATE_NOOP("App::Property", "OpenFOAM patch name for side 2; defaults to region2_to_region1"),
        )

        addObjectProperty(
            obj,
            "CouplingType",
            ["mappedWallAMI"],
            "App::PropertyEnumeration",
            "Coupling",
            QT_TRANSLATE_NOOP("App::Property", "OpenFOAM region-coupled boundary implementation"),
        )
        addObjectProperty(
            obj,
            "ThermalBoundaryType",
            "zeroGradient",
            "App::PropertyString",
            "Coupling",
            QT_TRANSLATE_NOOP("App::Property", "Fallback thermal condition before the region-coupled patch is applied"),
        )

    def onDocumentRestored(self, obj):
        self.initProperties(obj)

    def execute(self, obj):
        shapes = []
        for refs in (obj.ShapeRefs1, obj.ShapeRefs2):
            shape = CfdTools.makeShapeFromReferences(refs, False)
            if shape is not None:
                shapes.append(shape)
        obj.Shape = Part.makeCompound(shapes) if shapes else Part.Shape()

        if FreeCAD.GuiUp:
            obj.ViewObject.ShapeColor = (0.0, 0.55, 0.45)
            obj.ViewObject.Transparency = 35

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


class _CfdRegionCoupledInterface:
    """Backward compatibility for old class name when loading from file."""
    def onDocumentRestored(self, obj):
        CfdRegionCoupledInterface(obj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderCfdRegionCoupledInterface:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.ViewObject = vobj
        self.Object = vobj.Object

    def getIcon(self):
        return os.path.join(CfdTools.getModulePath(), "Gui", "Icons", "region_coupled_interface.svg")

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def updateData(self, obj, prop):
        analysis_obj = CfdTools.getParentAnalysisObject(obj)
        if analysis_obj and not analysis_obj.Proxy.loading:
            if prop in ('ShapeRefs1', 'ShapeRefs2', 'Region1Name', 'Region2Name', 'Patch1Name', 'Patch2Name'):
                analysis_obj.NeedsMeshRewrite = True
            else:
                analysis_obj.NeedsCaseRewrite = True

    def onChanged(self, vobj, prop):
        return

    def setEdit(self, vobj, mode):
        return False

    def unsetEdit(self, vobj, mode):
        return

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


class _ViewProviderCfdRegionCoupledInterface:
    """Backward compatibility for old class name when loading from file."""
    def onDocumentRestored(self, vobj):
        ViewProviderCfdRegionCoupledInterface(vobj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


if FreeCAD.GuiUp:
    FreeCADGui.addCommand('CfdOF_RegionCoupledInterface', CommandCfdRegionCoupledInterface())
