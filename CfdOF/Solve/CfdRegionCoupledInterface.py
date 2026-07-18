# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os
import json

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
IMPRINTED_NCC_GENERATED_BY = "CfdOF_ImprintedNccRegions"
THERMAL_BOUNDARY_TYPES = [
    "zeroGradient",
    "fixedValue",
    "fixedGradient",
    "totalPower",
    "externalWallHeatFluxTemperature",
]
THERMAL_VALUE_FIELDS = {
    "fixedValue": "Temperature",
    "fixedGradient": "HeatFlux",
    "totalPower": "Power",
    "externalWallHeatFluxTemperature": "HeatTransferCoeff",
}
THERMAL_VALUE_DISPLAY_UNITS = {
    "fixedValue": "K",
    "fixedGradient": "W/m^2",
    "totalPower": "W",
    "externalWallHeatFluxTemperature": "W/m^2/K",
}


def defaultThermalValue(interface_obj, thermal_type):
    value_field = THERMAL_VALUE_FIELDS.get(thermal_type)
    if not value_field:
        return ""
    value = getattr(interface_obj, value_field, "")
    display_unit = THERMAL_VALUE_DISPLAY_UNITS.get(thermal_type)
    if display_unit:
        try:
            value = value.getValueAs(display_unit)
        except Exception:
            try:
                value = FreeCAD.Units.Quantity(value).getValueAs(display_unit)
            except Exception:
                pass
        value_text = str(value)
        return value_text if display_unit in value_text else "{} {}".format(value_text, display_unit)
    return str(value)


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


def isImprintedNccGeneratedObject(obj):
    return getattr(obj, 'GeneratedBy', '') == IMPRINTED_NCC_GENERATED_BY


def isFinalImprintedRegionObject(obj):
    if not isImprintedNccGeneratedObject(obj):
        return False
    name = getattr(obj, 'Name', '')
    if name.startswith('NccSourceClone_') or name.startswith('NccSlice_'):
        return False
    return hasattr(obj, 'Shape') and not obj.Shape.isNull()


def getImprintedRegionForSource(source_obj):
    """Return the final imprinted slice generated from a source object, if any."""
    if source_obj is None or getattr(source_obj, 'Document', None) is None:
        return None
    if isFinalImprintedRegionObject(source_obj):
        return source_obj
    exact_name = "{}_slice".format(source_obj.Name)
    fallback = None
    for obj in source_obj.Document.Objects:
        if not isFinalImprintedRegionObject(obj):
            continue
        if getattr(obj, 'SourceObject', None) is not source_obj:
            continue
        if obj.Name == exact_name:
            return obj
        if fallback is None:
            fallback = obj
    return fallback


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


def _shape_refs_for_region(interface_obj, region_name, tolerance=1e-5):
    region_objects = [
        obj for obj in interface_obj.RegionObjects
        if getRegionName(obj) == region_name
    ]
    region_shapes = [getRegionShape(obj) for obj in region_objects if getRegionShape(obj) is not None]
    if not region_objects or not region_shapes:
        return interface_obj.ShapeRefs

    direct_ref_objects = set()
    for obj in region_objects:
        if hasattr(obj, 'Shape'):
            direct_ref_objects.add(obj)
        part_obj = getattr(obj, 'Part', None)
        if part_obj is not None and hasattr(part_obj, 'Shape'):
            direct_ref_objects.add(part_obj)

    direct_refs = [
        (ref_obj, subnames)
        for ref_obj, subnames in interface_obj.ShapeRefs
        if ref_obj in direct_ref_objects
    ]
    if direct_refs:
        return direct_refs

    region_refs = []
    for ref_obj, subnames in interface_obj.ShapeRefs:
        matched_subnames = []
        for subname in subnames:
            try:
                face = ref_obj.Shape.getElement(subname)
            except Exception:
                continue
            if any(_face_touches_shape(face, shape, tolerance) for shape in region_shapes):
                matched_subnames.append(subname)
        if matched_subnames:
            region_refs.append((ref_obj, tuple(matched_subnames)))

    return region_refs if region_refs else interface_obj.ShapeRefs


def _decode_interface_pairs(interface_obj):
    pairs = []
    for entry in getattr(interface_obj, 'InterfacePairs', []):
        try:
            pair = json.loads(entry)
        except Exception:
            continue
        required = {'region_a', 'object_a', 'face_a', 'region_b', 'object_b', 'face_b'}
        if required.issubset(pair):
            if pair.get('thermal_type') not in THERMAL_BOUNDARY_TYPES:
                pair['thermal_type'] = "zeroGradient"
            if 'thermal_value' not in pair:
                pair['thermal_value'] = defaultThermalValue(interface_obj, pair['thermal_type'])
            pairs.append(pair)
    return pairs


def encodeInterfacePair(pair):
    return json.dumps(pair, sort_keys=True)


def makeInterfacePair(region_a, object_a, face_a, region_b, object_b, face_b,
                      thermal_type="zeroGradient", thermal_value=""):
    if thermal_type not in THERMAL_BOUNDARY_TYPES:
        thermal_type = "zeroGradient"
    return encodeInterfacePair({
        'region_a': region_a,
        'object_a': object_a.Name,
        'face_a': face_a,
        'region_b': region_b,
        'object_b': object_b.Name,
        'face_b': face_b,
        'thermal_type': thermal_type,
        'thermal_value': thermal_value,
    })


def updateInterfacePairThermalType(interface_obj, pair_index, thermal_type):
    if thermal_type not in THERMAL_BOUNDARY_TYPES:
        thermal_type = "zeroGradient"
    pairs = _decode_interface_pairs(interface_obj)
    if pair_index < 0 or pair_index >= len(pairs):
        return False
    old_field = THERMAL_VALUE_FIELDS.get(pairs[pair_index].get('thermal_type'))
    new_field = THERMAL_VALUE_FIELDS.get(thermal_type)
    pairs[pair_index]['thermal_type'] = thermal_type
    if not new_field:
        pairs[pair_index]['thermal_value'] = ""
    elif old_field != new_field or not pairs[pair_index].get('thermal_value', ''):
        pairs[pair_index]['thermal_value'] = defaultThermalValue(interface_obj, thermal_type)
    interface_obj.InterfacePairs = [encodeInterfacePair(pair) for pair in pairs]
    return True


def _paired_shape_refs_for_region_partner(interface_obj, region_name, partner_name):
    doc = interface_obj.Document
    refs_by_object = {}
    for pair in _decode_interface_pairs(interface_obj):
        if pair['region_a'] == region_name and pair['region_b'] == partner_name:
            obj_name = pair['object_a']
            face_name = pair['face_a']
        elif pair['region_b'] == region_name and pair['region_a'] == partner_name:
            obj_name = pair['object_b']
            face_name = pair['face_b']
        else:
            continue
        ref_obj = doc.getObject(obj_name)
        if ref_obj is None:
            continue
        refs_by_object.setdefault(ref_obj, []).append(face_name)
    return [(ref_obj, tuple(face_names)) for ref_obj, face_names in refs_by_object.items()]


def _shape_refs_for_pair_side(interface_obj, pair, region_name):
    doc = interface_obj.Document
    if pair['region_a'] == region_name:
        ref_obj = doc.getObject(pair['object_a'])
        face_name = pair['face_a']
    elif pair['region_b'] == region_name:
        ref_obj = doc.getObject(pair['object_b'])
        face_name = pair['face_b']
    else:
        return []
    if ref_obj is None:
        return []
    if not face_name:
        return []
    return [(ref_obj, (face_name,))]


def _face_overlap_fraction(face_a, face_b):
    area_a = abs(getattr(face_a, 'Area', 0.0))
    area_b = abs(getattr(face_b, 'Area', 0.0))
    if area_a <= 0 or area_b <= 0:
        return 0.0
    try:
        return abs(face_a.common(face_b).Area) / min(area_a, area_b)
    except Exception:
        return 0.0


def _faces_are_paired(face_a, face_b, tolerance=1e-5, overlap_threshold=0.5):
    try:
        if face_a.distToShape(face_b)[0] > tolerance:
            return False
    except Exception:
        return False
    return _face_overlap_fraction(face_a, face_b) > overlap_threshold


def generatePairedTouchingFaceData(region_objects, tolerance=1e-5):
    """Return shape refs and explicit face pairs for touching generated regions."""
    valid_region_objects = [obj for obj in region_objects if getRegionShape(obj) is not None]
    if len(valid_region_objects) < 2:
        raise ValueError("At least two region objects with valid shapes are required")

    refs_by_object = {}
    interface_pairs = []
    for i, obj_a in enumerate(valid_region_objects):
        shape_a = getRegionShape(obj_a)
        for obj_b in valid_region_objects[i + 1:]:
            shape_b = getRegionShape(obj_b)
            for face_id_a, face_a in enumerate(shape_a.Faces, 1):
                for face_id_b, face_b in enumerate(shape_b.Faces, 1):
                    if not _faces_are_paired(face_a, face_b, tolerance):
                        continue
                    face_name_a = "Face{}".format(face_id_a)
                    face_name_b = "Face{}".format(face_id_b)
                    refs_by_object.setdefault(obj_a, set()).add(face_name_a)
                    refs_by_object.setdefault(obj_b, set()).add(face_name_b)
                    interface_pairs.append(makeInterfacePair(
                        getRegionName(obj_a),
                        obj_a,
                        face_name_a,
                        getRegionName(obj_b),
                        obj_b,
                        face_name_b,
                    ))

    if not interface_pairs:
        raise ValueError("No paired touching faces were found between the selected regions")
    shape_refs = [
        (ref_obj, tuple(sorted(face_names, key=lambda name: int(name[4:]))))
        for ref_obj, face_names in refs_by_object.items()
    ]
    return shape_refs, interface_pairs


def generateTouchingFaceRefs(region_objects, tolerance=1e-5):
    shape_refs, _interface_pairs = generatePairedTouchingFaceData(region_objects, tolerance)
    return shape_refs


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
                              "Paired generated region interface faces"),
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
        addObjectProperty(
            obj,
            "InterfacePairs",
            [],
            "App::PropertyStringList",
            "Region-coupled interface",
            QT_TRANSLATE_NOOP("App::Property",
                              "JSON encoded paired interface faces between generated regions"),
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
        interface_pairs = _decode_interface_pairs(obj)
        generated = []
        if interface_pairs:
            for pair_index, pair in enumerate(interface_pairs, 1):
                if pair['region_a'] not in region_names or pair['region_b'] not in region_names:
                    continue
                for region_name, partner_name, face_name in (
                    (pair['region_a'], pair['region_b'], pair['face_a']),
                    (pair['region_b'], pair['region_a'], pair['face_b']),
                ):
                    shape_refs = _shape_refs_for_pair_side(obj, pair, region_name)
                    if not shape_refs:
                        continue
                    label = "{}_{}_to_{}_{}".format(
                        _safe_label(obj.Label),
                        _safe_label(region_name),
                        _safe_label(partner_name),
                        _safe_label(face_name),
                    )
                    generated.append(_GeneratedRegionCoupledBoundary(
                        obj,
                        label,
                        region_name,
                        [partner_name],
                        shape_refs,
                        pair['thermal_type'],
                        pair.get('thermal_value', defaultThermalValue(obj, pair['thermal_type'])),
                    ))
            return generated

        for i, region_name in enumerate(region_names):
            partner_names = region_names[:i] + region_names[i + 1:]
            label = "{}_{}".format(_safe_label(obj.Label), _safe_label(region_name))
            generated.append(_GeneratedRegionCoupledBoundary(
                obj,
                label,
                region_name,
                partner_names,
                _shape_refs_for_region(obj, region_name),
                obj.ThermalBoundaryType,
                defaultThermalValue(obj, obj.ThermalBoundaryType),
            ))
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

    def __init__(self, interface_obj, label, region_name, partner_names, shape_refs,
                 thermal_boundary_type, thermal_value):
        self.InterfaceObject = interface_obj
        self.Name = "{}_{}".format(interface_obj.Name, _safe_label(region_name))
        self.Label = label
        self.ShapeRefs = shape_refs
        self.RegionName = region_name
        self.PartnerRegionNames = partner_names
        self.BoundaryType = "wall"
        self.BoundarySubType = "regionCoupledWall"
        self.ThermalBoundaryType = thermal_boundary_type
        self.ThermalValue = thermal_value
        self.Temperature = interface_obj.Temperature
        self.HeatFlux = interface_obj.HeatFlux
        self.Power = interface_obj.Power
        self.HeatTransferCoeff = interface_obj.HeatTransferCoeff
        value_field = THERMAL_VALUE_FIELDS.get(thermal_boundary_type)
        if value_field and thermal_value:
            try:
                setattr(self, value_field, FreeCAD.Units.Quantity(thermal_value))
            except Exception:
                setattr(self, value_field, thermal_value)
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
            'Temperature': self.Temperature,
            'HeatFlux': self.HeatFlux,
            'Power': self.Power,
            'HeatTransferCoeff': self.HeatTransferCoeff,
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
