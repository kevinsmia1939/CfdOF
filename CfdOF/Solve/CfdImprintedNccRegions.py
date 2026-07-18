# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD

from CfdOF import CfdTools
from CfdOF.CfdTools import addObjectProperty
from CfdOF.Solve import CfdRegionCoupledInterface

if FreeCAD.GuiUp:
    import FreeCADGui

QT_TRANSLATE_NOOP = FreeCAD.Qt.QT_TRANSLATE_NOOP

GENERATED_BY = "CfdOF_ImprintedNccRegions"


def _safe_name(label):
    safe = ''.join(c if c.isalnum() else '_' for c in str(label)).strip('_')
    return safe or "Region"


def _clear_generated_objects(doc):
    for obj in list(doc.Objects):
        if getattr(obj, 'GeneratedBy', '') == GENERATED_BY:
            doc.removeObject(obj.Name)
    old_group = doc.getObject("ImprintedRegions")
    if old_group is not None and not getattr(old_group, 'Group', []):
        doc.removeObject(old_group.Name)
    old_interface = doc.getObject("ImprintedRegionCoupledInterface")
    if old_interface is not None and getattr(getattr(old_interface, 'Proxy', None), 'Type', '') == \
            'CfdRegionCoupledInterface':
        doc.removeObject(old_interface.Name)


def _add_generated_marker(obj):
    addObjectProperty(
        obj,
        "GeneratedBy",
        GENERATED_BY,
        "App::PropertyString",
        "Imprinted NCC",
        QT_TRANSLATE_NOOP("App::Property", "Generator marker for CfdOF imprinted NCC regions"),
    )


def _add_generated_properties(obj, source_obj, region_name):
    _add_generated_marker(obj)
    addObjectProperty(
        obj,
        "SourceObject",
        source_obj,
        "App::PropertyLinkGlobal",
        "Imprinted NCC",
        QT_TRANSLATE_NOOP("App::Property", "Original source object for this imprinted region"),
    )
    addObjectProperty(
        obj,
        "RegionName",
        region_name,
        "App::PropertyString",
        "Imprinted NCC",
        QT_TRANSLATE_NOOP("App::Property", "OpenFOAM region name for this imprinted region"),
    )


def _clone_source_object(doc, source_obj):
    clone = doc.addObject("Part::Feature", "NccSourceClone_{}".format(_safe_name(source_obj.Name)))
    clone.Label = "{}_clone".format(source_obj.Label)
    clone.Shape = source_obj.Shape.copy()
    _add_generated_marker(clone)
    doc.recompute()
    if getattr(clone, 'ViewObject', None):
        clone.ViewObject.Visibility = False
    return clone


def _make_slice_feature(doc, base_obj, tool_obj, name, label, source_obj, region_name):
    from BOPTools import SplitFeatures

    slice_obj = SplitFeatures.makeSlice(name=name)
    slice_obj.Label = label
    slice_obj.Base = base_obj
    slice_obj.Tools = [tool_obj]
    slice_obj.Mode = "Split"
    _add_generated_properties(slice_obj, source_obj, region_name)
    doc.recompute()
    return slice_obj


def _shapes_touch_or_overlap(shape_a, shape_b, tolerance=1e-5):
    try:
        if shape_a.BoundBox.getIntersection(shape_b.BoundBox).isValid():
            return True
    except Exception:
        pass
    try:
        return shape_a.distToShape(shape_b)[0] <= tolerance
    except Exception:
        return False


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


def findTouchingShapePairs(source_objects, tolerance=1e-5):
    """Return selected-object pairs that touch or overlap, preserving selection order."""
    pairs = []
    for i, obj_a in enumerate(source_objects):
        for obj_b in source_objects[i + 1:]:
            if _shapes_touch_or_overlap(obj_a.Shape, obj_b.Shape, tolerance):
                pairs.append((obj_a, obj_b))
    return pairs


def touchingPartnersForSource(source_obj, touching_pairs, object_map=None):
    """Return ordered touching partners for one source from a touching-pair list."""
    partners = []
    for obj_a, obj_b in touching_pairs:
        if obj_a is source_obj:
            partners.append(object_map.get(obj_b, obj_b) if object_map else obj_b)
        elif obj_b is source_obj:
            partners.append(object_map.get(obj_a, obj_a) if object_map else obj_a)
    return partners


def generateImprintedInterfacePairs(source_to_region_obj, touching_pairs, tolerance=1e-5):
    interface_pairs = []
    for source_a, source_b in touching_pairs:
        region_obj_a = source_to_region_obj[source_a]
        region_obj_b = source_to_region_obj[source_b]
        region_name_a = getattr(region_obj_a, 'RegionName', '') or region_obj_a.Label
        region_name_b = getattr(region_obj_b, 'RegionName', '') or region_obj_b.Label
        for face_id_a, face_a in enumerate(region_obj_a.Shape.Faces, 1):
            for face_id_b, face_b in enumerate(region_obj_b.Shape.Faces, 1):
                if not _faces_are_paired(face_a, face_b, tolerance):
                    continue
                interface_pairs.append(CfdRegionCoupledInterface.makeInterfacePair(
                    region_name_a,
                    region_obj_a,
                    "Face{}".format(face_id_a),
                    region_name_b,
                    region_obj_b,
                    "Face{}".format(face_id_b),
                ))
    if not interface_pairs:
        raise ValueError("No paired imprinted interface faces were found between generated regions")
    return interface_pairs


def _slice_source_by_touching_pairs(doc, source_obj, base_obj, touching_pairs, clone_map):
    region_name = getattr(source_obj, 'RegionName', '') or source_obj.Label
    current_obj = base_obj
    slice_steps = []
    tools = touchingPartnersForSource(source_obj, touching_pairs, clone_map)
    for tool_index, tool_obj in enumerate(tools):
        if not _shapes_touch_or_overlap(current_obj.Shape, tool_obj.Shape):
            continue
        is_final_tool = tool_index == len(tools) - 1
        slice_obj = _make_slice_feature(
            doc,
            current_obj,
            tool_obj,
            "{}_slice".format(_safe_name(source_obj.Name)) if is_final_tool
            else "NccSlice_{}_by_{}".format(_safe_name(source_obj.Name), _safe_name(tool_obj.Name)),
            "{}_slice".format(source_obj.Label) if is_final_tool
            else "{}_slice".format(tool_obj.Label),
            source_obj,
            region_name,
        )
        if not slice_obj.Shape.Solids:
            doc.removeObject(slice_obj.Name)
            continue
        if getattr(current_obj, 'GeneratedBy', '') == GENERATED_BY and getattr(current_obj, 'ViewObject', None):
            current_obj.ViewObject.Visibility = False
        current_obj = slice_obj
        slice_steps.append(slice_obj)

    if not slice_steps:
        slice_obj = doc.addObject("Part::Feature", "{}_slice".format(_safe_name(source_obj.Name)))
        slice_obj.Label = "{}_slice".format(source_obj.Label)
        slice_obj.Shape = base_obj.Shape.copy()
        _add_generated_properties(slice_obj, source_obj, region_name)
        return slice_obj

    final_obj = slice_steps[-1]
    final_name = "{}_slice".format(_safe_name(source_obj.Name))
    if final_obj.Name != final_name and getattr(getattr(final_obj, 'Proxy', None), 'Type', '') == "FeatureSlice" \
            and getattr(final_obj, 'Base', None) is not None and getattr(final_obj, 'Tools', []):
        replacement = _make_slice_feature(
            doc,
            final_obj.Base,
            final_obj.Tools[0],
            final_name,
            "{}_slice".format(source_obj.Label),
            source_obj,
            region_name,
        )
        doc.removeObject(final_obj.Name)
        final_obj = replacement
    if getattr(final_obj, 'ViewObject', None):
        final_obj.ViewObject.Visibility = True
    return final_obj


def _face_touches_other_region(face, region_obj, region_objects, tolerance=1e-5):
    for other_obj in region_objects:
        if other_obj is region_obj:
            continue
        try:
            if face.distToShape(other_obj.Shape)[0] <= tolerance:
                return True
        except Exception:
            continue
    return False


def generateImprintedInterfaceFaceRefs(region_objects, tolerance=1e-5):
    """Return per-region face references created by imprinting/slicing."""
    refs = []
    for region_obj in region_objects:
        face_names = []
        for face_id, face in enumerate(region_obj.Shape.Faces, 1):
            if _face_touches_other_region(face, region_obj, region_objects, tolerance):
                face_names.append("Face{}".format(face_id))
        if face_names:
            refs.append((region_obj, tuple(face_names)))
    if not refs:
        raise ValueError("No imprinted interface faces were found between generated regions")
    return refs


def createImprintedNccRegions(source_objects=None, analysis_obj=None):
    """Create root-level per-region Slice Apart shapes and one interface object.

    The selected/source objects remain unchanged. For each source object, CfdOF
    retains that source as the base and slices it by every other selected source
    in sequence. The final ``<source>_slice`` object remains a FreeCAD Slice
    feature whose Base/Tools tree preserves the slicing operations.
    """
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("No active FreeCAD document")
    if analysis_obj is None:
        analysis_obj = CfdTools.getActiveAnalysis()
    if analysis_obj is None:
        raise RuntimeError("No active CfdAnalysis")
    if source_objects is None:
        if not FreeCAD.GuiUp:
            raise RuntimeError("source_objects must be provided when GUI selection is unavailable")
        source_objects = FreeCADGui.Selection.getSelection()
    source_objects = [obj for obj in source_objects if hasattr(obj, 'Shape') and not obj.Shape.isNull()]
    if len(source_objects) < 2:
        raise RuntimeError("Select at least two valid region source objects")

    _clear_generated_objects(doc)
    touching_pairs = findTouchingShapePairs(source_objects)
    if not touching_pairs:
        raise RuntimeError("No touching or overlapping shape pairs were found")
    clone_map = {source_obj: _clone_source_object(doc, source_obj) for source_obj in source_objects}

    slice_objects = []
    source_to_region_obj = {}
    for source_obj in source_objects:
        slice_obj = _slice_source_by_touching_pairs(doc, source_obj, clone_map[source_obj], touching_pairs, clone_map)
        slice_objects.append(slice_obj)
        source_to_region_obj[source_obj] = slice_obj
        if getattr(slice_obj, 'ViewObject', None):
            slice_obj.ViewObject.Visibility = True

    interface = CfdRegionCoupledInterface.makeCfdRegionCoupledInterface("ImprintedRegionCoupledInterface")
    interface.Label = "ImprintedRegionCoupledInterface"
    interface.RegionObjects = slice_objects
    interface.RegionNames = [getattr(obj, 'RegionName', '') or obj.Label for obj in slice_objects]
    interface.ShapeRefs, interface.InterfacePairs = CfdRegionCoupledInterface.generatePairedTouchingFaceData(
        slice_objects
    )
    if interface not in analysis_obj.Group:
        analysis_obj.addObject(interface)

    doc.recompute()
    return None, slice_objects, interface


class CommandCfdImprintedNccRegions:
    def GetResources(self):
        return {
            'Pixmap': os.path.join(CfdTools.getModulePath(), "Gui", "Icons",
                                   "imprinted_ncc_regions.svg"),
            'MenuText': QT_TRANSLATE_NOOP("CfdOF_ImprintedNccRegions",
                                          "Create imprinted NCC regions"),
            'ToolTip': QT_TRANSLATE_NOOP(
                "CfdOF_ImprintedNccRegions",
                "Slice Apart selected regions into root-level imprinted region shapes"),
        }

    def IsActive(self):
        if CfdTools.getActiveAnalysis() is None:
            return False
        return len(FreeCADGui.Selection.getSelection()) >= 2

    def Activated(self):
        FreeCAD.ActiveDocument.openTransaction("Create imprinted NCC regions")
        FreeCADGui.doCommand("from CfdOF.Solve import CfdImprintedNccRegions")
        FreeCADGui.doCommand("CfdImprintedNccRegions.createImprintedNccRegions()")


if FreeCAD.GuiUp and hasattr(FreeCADGui, 'addCommand'):
    FreeCADGui.addCommand('CfdOF_ImprintedNccRegions', CommandCfdImprintedNccRegions())
