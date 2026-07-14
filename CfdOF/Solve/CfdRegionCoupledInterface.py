# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD
import Part
from pivy import coin

from CfdOF import CfdTools
from CfdOF.CfdTools import addObjectProperty

if FreeCAD.GuiUp:
    import FreeCADGui

QT_TRANSLATE_NOOP = FreeCAD.Qt.QT_TRANSLATE_NOOP

INTERFACE_FACE_COLORS = [
    (0.0, 0.45, 1.0),    # blue
    (1.0, 0.55, 0.0),    # orange
    (0.1, 0.75, 0.25),   # green
    (0.8, 0.2, 0.75),    # magenta
    (0.95, 0.85, 0.0),   # yellow
    (0.0, 0.75, 0.75),   # cyan
]
DEFAULT_INTERFACE_FACE_COLOR = (0.0, 0.6, 0.6)


def _safe_label(label):
    return str(label).replace(" ", "_")


def getRegionName(obj):
    return getattr(obj, 'RegionName', '') or obj.Label


def _shape_from_mesh(mesh_obj):
    part = getattr(mesh_obj, 'Part', None)
    if part is None or not hasattr(part, 'Shape'):
        return None
    sub_shape = getattr(mesh_obj, 'PartSubShape', '')
    if sub_shape:
        try:
            return part.Shape.getElement(sub_shape)
        except Exception:
            return None
    return part.Shape


def _shape_from_solid_material(material_obj):
    refs = getattr(material_obj, 'ShapeRefs', [])
    if not refs:
        return None
    ref_obj = refs[0][0]
    if not hasattr(ref_obj, 'Shape'):
        return None
    subnames = refs[0][1]
    if subnames:
        try:
            return ref_obj.Shape.getElement(subnames[0])
        except Exception:
            return None
    return ref_obj.Shape


def getRegionShape(obj):
    if hasattr(obj, 'Proxy') and getattr(obj.Proxy, 'Type', '') == 'CfdMesh':
        return _shape_from_mesh(obj)
    if hasattr(obj, 'Proxy') and getattr(obj.Proxy, 'Type', '') == 'CfdSolidMaterial':
        return _shape_from_solid_material(obj)
    if hasattr(obj, 'Shape'):
        return obj.Shape
    return None


def _candidate_container(region_objects):
    parts = [getattr(obj, 'Part', None) for obj in region_objects if getattr(obj, 'Part', None)]
    parts = [part for part in parts if hasattr(part, 'Shape')]
    if parts and all(part is parts[0] for part in parts):
        return parts[0]
    documents = set(obj.Document for obj in region_objects if getattr(obj, 'Document', None))
    for doc in documents:
        named_fragments = [
            obj for obj in doc.Objects
            if hasattr(obj, 'Shape') and
            (obj.Name == 'BooleanFragments' or obj.Label == 'BooleanFragments')
        ]
        if named_fragments:
            return named_fragments[0]
    for obj in region_objects:
        refs = getattr(obj, 'ShapeRefs', [])
        for ref_obj, _subnames in refs:
            if hasattr(ref_obj, 'Shape'):
                return ref_obj
    return parts[0] if parts else None


def _face_touches_shape(face, shape, tolerance):
    try:
        distance = face.distToShape(shape)[0]
        centroid_inside = shape.isInside(face.CenterOfMass, tolerance, True)
    except Exception:
        return False
    return distance <= tolerance and centroid_inside


def _touching_region_key(face, region_objects, tolerance=1e-5):
    touching = []
    for obj in region_objects:
        shape = getRegionShape(obj)
        if shape is None:
            continue
        if _face_touches_shape(face, shape, tolerance):
            touching.append(getRegionName(obj))
    if len(touching) < 2:
        return None
    return tuple(touching)


def generateTouchingFaceRefs(region_objects, tolerance=1e-5):
    region_shapes = []
    for obj in region_objects:
        shape = getRegionShape(obj)
        if shape is not None:
            region_shapes.append((getRegionName(obj), shape))
    if len(region_shapes) < 2:
        raise ValueError("At least two region objects with valid shapes are required")

    container = _candidate_container(region_objects)
    if container is None or not hasattr(container, 'Shape'):
        raise ValueError("Could not find a BooleanFragments object from the selected regions")

    face_names = []
    for face_id, face in enumerate(container.Shape.Faces, 1):
        touched = [region_name for region_name, shape in region_shapes
                   if _face_touches_shape(face, shape, tolerance)]
        if len(touched) >= 2:
            face_names.append("Face{}".format(face_id))

    if not face_names:
        raise ValueError("No touching BooleanFragments faces were found for the selected regions")
    return container, tuple(face_names)


def makeCfdRegionCoupledInterface(name="RegionCoupledInterface"):
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    CfdRegionCoupledInterface(obj)
    if FreeCAD.GuiUp:
        ViewProviderCfdRegionCoupledInterface(obj.ViewObject)
    return obj


class CommandCfdRegionCoupledInterface:

    def GetResources(self):
        return {
            'Pixmap': os.path.join(CfdTools.getModulePath(), "Gui", "Icons",
                                   "region_coupled_interface.svg"),
            'MenuText': QT_TRANSLATE_NOOP("CfdOF_RegionCoupledInterface",
                                          "Region-coupled interface"),
            'ToolTip': QT_TRANSLATE_NOOP(
                "CfdOF_RegionCoupledInterface",
                "Create a non-conformal region-coupled interface boundary"),
        }

    def IsActive(self):
        return CfdTools.getActiveAnalysis() is not None

    def Activated(self):
        FreeCAD.ActiveDocument.openTransaction("Create region-coupled interface")
        FreeCADGui.doCommand("from CfdOF import CfdTools")
        FreeCADGui.doCommand("from CfdOF.Solve import CfdRegionCoupledInterface")
        FreeCADGui.doCommand(
            "CfdTools.getActiveAnalysis().addObject("
            "CfdRegionCoupledInterface.makeCfdRegionCoupledInterface())")
        FreeCADGui.ActiveDocument.setEdit(FreeCAD.ActiveDocument.ActiveObject.Name)


class CfdRegionCoupledInterface:
    """User-facing definition of a coupled interface between two CHT regions."""

    def __init__(self, obj):
        self.initProperties(obj)

    def initProperties(self, obj):
        obj.Proxy = self
        self.Type = 'CfdRegionCoupledInterface'

        addObjectProperty(
            obj,
            "ShapeRefs",
            [],
            "App::PropertyLinkSubListGlobal",
            "Region-coupled interface",
            QT_TRANSLATE_NOOP("App::Property",
                              "Shared/generated BooleanFragments interface faces"),
        )
        addObjectProperty(
            obj,
            "RegionNames",
            [],
            "App::PropertyStringList",
            "Region-coupled interface",
            QT_TRANSLATE_NOOP("App::Property",
                              "OpenFOAM region names connected by this interface"),
        )
        addObjectProperty(
            obj,
            "RegionObjects",
            [],
            "App::PropertyLinkListGlobal",
            "Region-coupled interface",
            QT_TRANSLATE_NOOP("App::Property",
                              "Mesh or material objects participating in this interface"),
        )
        if addObjectProperty(
            obj,
            "ThermalBoundaryType",
            ["zeroGradient", "fixedValue", "fixedGradient", "totalPower",
             "externalWallHeatFluxTemperature"],
            "App::PropertyEnumeration",
            "Thermal",
            QT_TRANSLATE_NOOP("App::Property",
                              "Thermal boundary type written on the generated patches"),
        ):
            obj.ThermalBoundaryType = "zeroGradient"
        addObjectProperty(
            obj,
            "Temperature",
            "293 K",
            "App::PropertyQuantity",
            "Thermal",
            QT_TRANSLATE_NOOP("App::Property",
                              "Temperature used by fixedValue thermal coupling patches"),
        )
        addObjectProperty(
            obj,
            "HeatFlux",
            "0 W/m^2",
            "App::PropertyQuantity",
            "Thermal",
            QT_TRANSLATE_NOOP("App::Property",
                              "Heat flux used by fixedGradient thermal coupling patches"),
        )
        addObjectProperty(
            obj,
            "Power",
            "0 W",
            "App::PropertyQuantity",
            "Thermal",
            QT_TRANSLATE_NOOP("App::Property",
                              "Total power used by totalPower thermal coupling patches"),
        )
        addObjectProperty(
            obj,
            "HeatTransferCoeff",
            "0 W/m^2/K",
            "App::PropertyQuantity",
            "Thermal",
            QT_TRANSLATE_NOOP("App::Property",
                              "Heat-transfer coefficient for external wall heat flux"),
        )

    def onDocumentRestored(self, obj):
        self.initProperties(obj)
        if FreeCAD.GuiUp and obj.ViewObject.Proxy == 0:
            ViewProviderCfdRegionCoupledInterface(obj.ViewObject)

    def execute(self, obj):
        faces = []
        for ref_obj, subnames in obj.ShapeRefs:
            for subname in subnames:
                try:
                    faces.append(ref_obj.Shape.getElement(subname))
                except Exception:
                    pass
        obj.Shape = Part.makeCompound(faces) if faces else Part.Shape()
        self.updateInterfaceFaceColors(obj, faces)

    def updateInterfaceFaceColors(self, obj, faces):
        if not FreeCAD.GuiUp:
            return
        obj.ViewObject.Transparency = 20
        obj.ViewObject.ShapeColor = DEFAULT_INTERFACE_FACE_COLOR
        if not faces:
            return

        pair_colors = {}
        face_colors = []
        for face in faces:
            pair_key = _touching_region_key(face, obj.RegionObjects)
            if pair_key is None:
                face_colors.append(DEFAULT_INTERFACE_FACE_COLOR)
                continue
            if pair_key not in pair_colors:
                color_index = len(pair_colors) % len(INTERFACE_FACE_COLORS)
                pair_colors[pair_key] = INTERFACE_FACE_COLORS[color_index]
            face_colors.append(pair_colors[pair_key])
        obj.ViewObject.DiffuseColor = face_colors

    def makeBoundaryObjects(self, obj):
        region_names = [r for r in obj.RegionNames if r]
        if len(region_names) < 2:
            return []
        generated = []
        for i, region_name in enumerate(region_names):
            partner_names = region_names[:i] + region_names[i + 1:]
            label = "{}_{}".format(_safe_label(obj.Label), _safe_label(region_name))
            generated.append(_GeneratedRegionCoupledBoundary(obj, label, region_name, partner_names))
        return generated

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


class _GeneratedRegionCoupledBoundary:
    """Boundary-like adapter consumed by the existing OpenFOAM case writer."""

    def __init__(self, interface_obj, label, region_name, partner_names):
        self.InterfaceObject = interface_obj
        self.Name = "{}_{}".format(interface_obj.Name, _safe_label(region_name))
        self.Label = label
        self.ShapeRefs = interface_obj.ShapeRefs
        self.RegionName = region_name
        self.PartnerRegionNames = partner_names
        self.BoundaryType = "wall"
        self.BoundarySubType = "regionCoupledWall"
        self.ThermalBoundaryType = interface_obj.ThermalBoundaryType
        self.DefaultBoundary = False

    def toDict(self):
        return {
            'BoundaryType': self.BoundaryType,
            'BoundarySubType': self.BoundarySubType,
            'ThermalBoundaryType': self.ThermalBoundaryType,
            'RegionName': self.RegionName,
            'DefaultBoundary': False,
            'VelocityIsCartesian': True,
            'VelocityMag': FreeCAD.Units.Quantity('0 m/s'),
            'DirectionFace': '',
            'ReverseNormal': False,
            'Ux': FreeCAD.Units.Quantity('0 m/s'),
            'Uy': FreeCAD.Units.Quantity('0 m/s'),
            'Uz': FreeCAD.Units.Quantity('0 m/s'),
            'Pressure': FreeCAD.Units.Quantity('0 Pa'),
            'PorousBaffleMethod': 'lossCoeff',
            'ScreenWireDiameter': FreeCAD.Units.Quantity('1 mm'),
            'ScreenSpacing': FreeCAD.Units.Quantity('2 mm'),
            'RotationAxis': FreeCAD.Vector(0, 0, 1),
            'VolumeFractions': {},
            'TurbulenceIntensityPercentage': 1.0,
            'TurbulenceInletSpecification': 'intensityAndLengthScale',
            'TurbulenceLengthScale': FreeCAD.Units.Quantity('1 mm'),
            'Temperature': self.InterfaceObject.Temperature,
            'HeatFlux': self.InterfaceObject.HeatFlux,
            'Power': self.InterfaceObject.Power,
            'HeatTransferCoeff': self.InterfaceObject.HeatTransferCoeff,
            'ShapeRefs': self.ShapeRefs,
        }


class ViewProviderCfdRegionCoupledInterface:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.taskd = None

    def getIcon(self):
        return os.path.join(CfdTools.getModulePath(), "Gui", "Icons",
                            "region_coupled_interface.svg")

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        self.standard = coin.SoGroup()
        vobj.addDisplayMode(self.standard, "Standard")
        vobj.ShapeColor = (0.0, 0.6, 0.6)
        vobj.Transparency = 60
        return

    def updateData(self, obj, prop):
        analysis_obj = CfdTools.getParentAnalysisObject(obj)
        if analysis_obj and not analysis_obj.Proxy.loading:
            analysis_obj.NeedsCaseRewrite = True

    def onChanged(self, vobj, prop):
        return

    def doubleClicked(self, vobj):
        doc = FreeCADGui.getDocument(vobj.Object.Document)
        if not doc.getInEdit():
            doc.setEdit(vobj.Object.Name)
        else:
            FreeCAD.Console.PrintError('Task dialog already active\\n')
            FreeCADGui.Control.showTaskView()
        return True

    def setEdit(self, vobj, mode):
        analysis_object = CfdTools.getParentAnalysisObject(self.Object)
        if analysis_object is None:
            CfdTools.cfdErrorBox("Region-coupled interface object must have a parent analysis object")
            return False
        from CfdOF.Solve import TaskPanelCfdRegionCoupledInterface
        import importlib
        importlib.reload(TaskPanelCfdRegionCoupledInterface)
        self.taskd = TaskPanelCfdRegionCoupledInterface.TaskPanelCfdRegionCoupledInterface(self.Object)
        self.taskd.obj = vobj.Object
        FreeCADGui.Control.showDialog(self.taskd)
        return True

    def unsetEdit(self, vobj, mode):
        if self.taskd:
            self.taskd.closing()
            self.taskd = None
        FreeCADGui.Control.closeDialog()
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
    def attach(self, vobj):
        new_proxy = ViewProviderCfdRegionCoupledInterface(vobj)
        new_proxy.attach(vobj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


if FreeCAD.GuiUp and hasattr(FreeCADGui, 'addCommand'):
    FreeCADGui.addCommand('CfdOF_RegionCoupledInterface',
                          CommandCfdRegionCoupledInterface())
