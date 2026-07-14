# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui

from CfdOF import CfdTools
from CfdOF.Solve import CfdRegionCoupledInterface


class TaskPanelCfdRegionCoupledInterface:
    """Task panel for selecting and generating region-coupled interfaces."""

    def __init__(self, obj):
        self.obj = obj
        self.analysis_obj = CfdTools.getParentAnalysisObject(obj)
        self.RegionNamesOrig = list(obj.RegionNames)
        self.RegionObjectsOrig = list(getattr(obj, 'RegionObjects', []))
        self.ShapeRefsOrig = list(obj.ShapeRefs)
        self.ThermalBoundaryTypeOrig = obj.ThermalBoundaryType
        self.NeedsCaseRewriteOrig = self.analysis_obj.NeedsCaseRewrite
        self.candidates = self._collect_candidates()
        self.candidates_by_object = dict((candidate[1].Name, candidate) for candidate in self.candidates)
        self.choosing_regions = False
        self.choosing_faces = False

        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Region-coupled interface")
        layout = QtGui.QVBoxLayout(self.form)

        self.regionHelpLabel = QtGui.QLabel("Select multiple region objects by holding crtl and clicking any part of the object, press Generate touching patches to automatically detect shared face on boolean fragment objject")

        layout.addWidget(QtGui.QLabel("Region objects"))
        choose_layout = QtGui.QHBoxLayout()
        self.chooseRegionsButton = QtGui.QPushButton("Choose regions")
        self.chooseRegionsButton.setCheckable(True)
        self.chooseRegionsButton.clicked.connect(self.chooseRegionsClicked)
        choose_layout.addWidget(self.chooseRegionsButton)
        self.selectFromListButton = QtGui.QPushButton("Select from list")
        self.selectFromListButton.setCheckable(True)
        self.selectFromListButton.clicked.connect(self.selectFromList)
        choose_layout.addWidget(self.selectFromListButton)
        self.clearRegionsButton = QtGui.QPushButton("Clear")
        self.clearRegionsButton.clicked.connect(self.clearRegions)
        choose_layout.addWidget(self.clearRegionsButton)
        layout.addLayout(choose_layout)

        self.selectedRegionList = QtGui.QListWidget()
        self.selectedRegionList.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.selectedRegionList.setMinimumHeight(120)
        self.selectedRegionList.currentRowChanged.connect(self.setSelectedRegionListSelection)
        layout.addWidget(self.selectedRegionList)

        self.regionHelpLabel.setWordWrap(True)
        layout.addWidget(self.regionHelpLabel)

        edit_layout = QtGui.QGridLayout()
        edit_layout.setColumnStretch(0, 1)
        edit_layout.setColumnStretch(1, 1)
        edit_layout.setColumnStretch(3, 1)
        edit_layout.setColumnStretch(5, 1)
        self.addRegionButton = QtGui.QPushButton("Add")
        self.addRegionButton.setCheckable(True)
        self.addRegionButton.clicked.connect(self.addRegionButtonClicked)
        edit_layout.addWidget(self.addRegionButton, 0, 2)
        self.removeRegionButton = QtGui.QPushButton("Remove")
        self.removeRegionButton.clicked.connect(self.removeSelectedRegions)
        edit_layout.addWidget(self.removeRegionButton, 0, 4)
        layout.addLayout(edit_layout)

        self.availableRegionList = QtGui.QListWidget()
        self.availableRegionList.setSelectionMode(QtGui.QAbstractItemView.NoSelection)
        self.availableRegionList.setMinimumHeight(120)
        self.availableRegionList.itemChanged.connect(self.availableRegionListItemChanged)
        self.availableRegionList.setVisible(False)
        layout.addWidget(self.availableRegionList)

        thermal_layout = QtGui.QHBoxLayout()
        thermal_layout.addWidget(QtGui.QLabel("Thermal type"))
        self.thermalCombo = QtGui.QComboBox()
        for item in ["zeroGradient", "fixedValue", "fixedGradient", "totalPower",
                     "externalWallHeatFluxTemperature"]:
            self.thermalCombo.addItem(item)
        thermal_layout.addWidget(self.thermalCombo)
        layout.addLayout(thermal_layout)

        self.generateButton = QtGui.QPushButton("Generate interface faces")
        self.generateButton.clicked.connect(self.generateTouchingPatches)
        layout.addWidget(self.generateButton)

        layout.addWidget(QtGui.QLabel("Interface faces"))
        self.faceList = QtGui.QListWidget()
        self.faceList.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.faceList.currentRowChanged.connect(self.setInterfaceFaceListSelection)
        layout.addWidget(self.faceList)

        face_edit_layout = QtGui.QGridLayout()
        face_edit_layout.setColumnStretch(0, 1)
        face_edit_layout.setColumnStretch(1, 1)
        face_edit_layout.setColumnStretch(3, 1)
        face_edit_layout.setColumnStretch(5, 1)
        self.addFaceButton = QtGui.QPushButton("Add")
        self.addFaceButton.setCheckable(True)
        self.addFaceButton.clicked.connect(self.addFaceButtonClicked)
        face_edit_layout.addWidget(self.addFaceButton, 0, 2)
        self.removeFaceButton = QtGui.QPushButton("Remove")
        self.removeFaceButton.clicked.connect(self.removeSelectedInterfaceFaces)
        face_edit_layout.addWidget(self.removeFaceButton, 0, 4)
        layout.addLayout(face_edit_layout)

        self.statusLabel = QtGui.QLabel("")
        self.statusLabel.setWordWrap(True)
        layout.addWidget(self.statusLabel)

        self._load()
        self._refreshFaceList()

    def _collect_candidates(self):
        candidates = []
        names_seen = set()
        represented_shapes = set()
        if self.analysis_obj is None:
            return candidates
        for mesh_obj in CfdTools.getMeshObjects(self.analysis_obj):
            region_name = CfdRegionCoupledInterface.getRegionName(mesh_obj)
            shape = CfdRegionCoupledInterface.getRegionShape(mesh_obj)
            if region_name and shape is not None:
                candidates.append((region_name, mesh_obj, shape))
                names_seen.add(region_name)
                part = getattr(mesh_obj, 'Part', None)
                if part is not None:
                    represented_shapes.add(part.Name)
        for solid_obj in CfdTools.getSolidMaterials(self.analysis_obj):
            region_name = CfdRegionCoupledInterface.getRegionName(solid_obj)
            shape = CfdRegionCoupledInterface.getRegionShape(solid_obj)
            if region_name and shape is not None and region_name not in names_seen:
                candidates.append((region_name, solid_obj, shape))
                for ref_obj, _subnames in getattr(solid_obj, 'ShapeRefs', []):
                    represented_shapes.add(ref_obj.Name)
        for shape_obj in self.obj.Document.Objects:
            if shape_obj.Name in represented_shapes or shape_obj is self.obj:
                continue
            if not hasattr(shape_obj, 'Shape') or shape_obj.Shape.isNull():
                continue
            if hasattr(shape_obj, 'Proxy') and getattr(shape_obj.Proxy, 'Type', '').startswith('Cfd'):
                continue
            candidates.append((shape_obj.Label, shape_obj, shape_obj.Shape))
        return candidates

    def _load(self):
        selected_names = set(self.obj.RegionNames)
        selected_objects = list(getattr(self.obj, 'RegionObjects', []))
        self.availableRegionList.blockSignals(True)
        if not self.candidates:
            item = QtGui.QListWidgetItem("No region shapes found")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            self.availableRegionList.addItem(item)
        else:
            for region_name, region_obj, _shape in self.candidates:
                item = QtGui.QListWidgetItem(self._candidateListLabel(region_name, region_obj))
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                checked = region_name in selected_names or region_obj in selected_objects
                item.setCheckState(QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
                item.setData(QtCore.Qt.UserRole, region_obj.Name)
                self.availableRegionList.addItem(item)
                if checked:
                    self._addCandidateToSelectedList((region_name, region_obj, _shape), update_object=False)
        self.availableRegionList.blockSignals(False)
        idx = self.thermalCombo.findText(str(self.obj.ThermalBoundaryType))
        self.thermalCombo.setCurrentIndex(idx if idx >= 0 else 0)

    def _selected_candidates(self):
        selected = []
        for row in range(self.selectedRegionList.count()):
            item = self.selectedRegionList.item(row)
            candidate = self.candidates_by_object.get(item.data(QtCore.Qt.UserRole))
            if candidate:
                selected.append(candidate)
        return selected

    def _syncObjectFromSelectedList(self):
        selected = self._selected_candidates()
        self.obj.RegionNames = [region_name for region_name, _obj, _shape in selected]
        self.obj.RegionObjects = [obj for _region_name, obj, _shape in selected]
        self.obj.ShapeRefs = []
        self._refreshFaceList()
        self._recomputeInterfaceObject()
        return selected

    def _candidateListLabel(self, region_name, region_obj):
        part = getattr(region_obj, 'Part', None)
        if part is not None:
            sub_shape = getattr(region_obj, 'PartSubShape', '')
            if sub_shape:
                return "{}: {} ({})".format(part.Label, sub_shape, region_name)
            return "{} ({})".format(part.Label, region_name)
        refs = getattr(region_obj, 'ShapeRefs', [])
        if refs:
            ref_obj, subnames = refs[0]
            if subnames:
                return "{}: {} ({})".format(ref_obj.Label, ", ".join(subnames), region_name)
            return "{} ({})".format(ref_obj.Label, region_name)
        return "{} ({})".format(region_obj.Label, region_name)

    def _candidate_for_selection(self, selected_object, subname):
        for candidate in self.candidates:
            _region_name, region_obj, _shape = candidate
            if selected_object is region_obj:
                return candidate
            part = getattr(region_obj, 'Part', None)
            if part is selected_object:
                part_subshape = getattr(region_obj, 'PartSubShape', '')
                if not part_subshape or not subname or subname == part_subshape:
                    return candidate
            refs = getattr(region_obj, 'ShapeRefs', [])
            for ref_obj, subnames in refs:
                if ref_obj is not selected_object:
                    continue
                if not subnames or not subname or subname in subnames:
                    return candidate
        if hasattr(selected_object, 'Shape') and subname:
            try:
                selected_shape = selected_object.Shape.getElement(subname)
                centroid = selected_shape.CenterOfMass
            except Exception:
                return None
            containing = []
            for candidate in self.candidates:
                _region_name, _region_obj, shape = candidate
                try:
                    if shape.isInside(centroid, 1e-5, True):
                        containing.append(candidate)
                except Exception:
                    pass
            if len(containing) == 1:
                return containing[0]
        return None

    def _candidateIsSelected(self, region_obj):
        for row in range(self.selectedRegionList.count()):
            item = self.selectedRegionList.item(row)
            if item.data(QtCore.Qt.UserRole) == region_obj.Name:
                return True
        return False

    def _addCandidateToSelectedList(self, candidate, update_object=True):
        region_name, region_obj, _shape = candidate
        if self._candidateIsSelected(region_obj):
            return False
        item = QtGui.QListWidgetItem(self._candidateListLabel(region_name, region_obj))
        item.setData(QtCore.Qt.UserRole, region_obj.Name)
        self.selectedRegionList.addItem(item)
        if update_object:
            self._syncObjectFromSelectedList()
        return True

    def _removeCandidateFromSelectedList(self, region_obj, update_object=True):
        for row in range(self.selectedRegionList.count() - 1, -1, -1):
            item = self.selectedRegionList.item(row)
            if item.data(QtCore.Qt.UserRole) == region_obj.Name:
                self.selectedRegionList.takeItem(row)
        if update_object:
            self._syncObjectFromSelectedList()
        return False

    def _setAvailableCandidateChecked(self, region_obj, checked=True):
        self.availableRegionList.blockSignals(True)
        for row in range(self.availableRegionList.count()):
            item = self.availableRegionList.item(row)
            if item.data(QtCore.Qt.UserRole) == region_obj.Name:
                item.setCheckState(QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
                break
        self.availableRegionList.blockSignals(False)

    def setSelectedRegionListSelection(self, row):
        if row < 0:
            return
        item = self.selectedRegionList.item(row)
        candidate = self.candidates_by_object.get(item.data(QtCore.Qt.UserRole))
        if not candidate:
            return
        _region_name, region_obj, _shape = candidate
        FreeCADGui.Selection.clearSelection()
        part = getattr(region_obj, 'Part', None)
        if part is not None:
            sub_shape = getattr(region_obj, 'PartSubShape', '')
            if sub_shape:
                FreeCADGui.Selection.addSelection(part, sub_shape)
            else:
                FreeCADGui.Selection.addSelection(part)
        else:
            FreeCADGui.Selection.addSelection(region_obj)

    def availableRegionListItemChanged(self, item):
        candidate = self.candidates_by_object.get(item.data(QtCore.Qt.UserRole))
        if not candidate:
            return
        _region_name, region_obj, _shape = candidate
        if item.checkState() == QtCore.Qt.Checked:
            self._addCandidateToSelectedList(candidate)
        else:
            self._removeCandidateFromSelectedList(region_obj)
        selected = self._syncObjectFromSelectedList()
        self.statusLabel.setText("{} region object(s) selected from list.".format(len(selected)))

    def selectFromList(self):
        if self.selectFromListButton.isChecked():
            self.availableRegionList.setVisible(True)
            self.availableRegionList.setFocus()
            self.statusLabel.setText(
                "Tick the region shapes to connect. No component selection is required.")
        else:
            self.availableRegionList.setVisible(False)
            self.statusLabel.setText("")

    def addRegionButtonClicked(self):
        selecting = not self.choosing_regions
        if selecting and len(FreeCADGui.Selection.getSelectionEx()) >= 1:
            for sel in FreeCADGui.Selection.getSelectionEx():
                if sel.HasSubObjects:
                    for sub in sel.SubElementNames:
                        self._addSelectionCandidate(sel.DocumentName, sel.ObjectName, sub)
                else:
                    self._addSelectionCandidate(sel.DocumentName, sel.ObjectName, None)
            selecting = False
        self._enableChoosingRegions(selecting)

    def chooseRegionsClicked(self):
        self._enableChoosingRegions(self.chooseRegionsButton.isChecked())

    def _enableChoosingRegions(self, choosing):
        if self.choosing_regions == choosing:
            self.chooseRegionsButton.setChecked(choosing)
            self.addRegionButton.setChecked(choosing)
            return
        if choosing:
            self._enableChoosingFaces(False)
        self.choosing_regions = choosing
        if self.choosing_regions:
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addObserver(self)
            self.statusLabel.setText(
                "Select mesh objects, material objects, or their region geometry in the tree or viewport.")
        else:
            FreeCADGui.Selection.removeObserver(self)
            self.statusLabel.setText("")
        self.chooseRegionsButton.setChecked(self.choosing_regions)
        self.addRegionButton.setChecked(self.choosing_regions)

    def clearRegions(self):
        self.availableRegionList.blockSignals(True)
        for row in range(self.availableRegionList.count()):
            item = self.availableRegionList.item(row)
            if item.flags() & QtCore.Qt.ItemIsUserCheckable:
                item.setCheckState(QtCore.Qt.Unchecked)
        self.availableRegionList.blockSignals(False)
        self.selectedRegionList.clear()
        self.obj.RegionNames = []
        self.obj.RegionObjects = []
        self.obj.ShapeRefs = []
        self._refreshFaceList()
        self.statusLabel.setText("Region selection cleared.")

    def removeSelectedRegions(self):
        selected_items = list(self.selectedRegionList.selectedItems())
        if not selected_items:
            return
        for item in selected_items:
            candidate = self.candidates_by_object.get(item.data(QtCore.Qt.UserRole))
            if candidate:
                _region_name, region_obj, _shape = candidate
                self._setAvailableCandidateChecked(region_obj, False)
                self._removeCandidateFromSelectedList(region_obj, update_object=False)
        selected = self._syncObjectFromSelectedList()
        self.statusLabel.setText("{} region object(s) selected.".format(len(selected)))

    def _addSelectionCandidate(self, doc_name, obj_name, sub):
        if FreeCADGui.activeDocument().Document.Name != self.obj.Document.Name:
            return False
        selected_object = FreeCAD.getDocument(doc_name).getObject(obj_name)
        candidate = self._candidate_for_selection(selected_object, sub)
        if candidate is None:
            self.statusLabel.setText("Selection is not a known mesh/material region: {}".format(obj_name))
            return False
        region_name, region_obj, _shape = candidate
        self._addCandidateToSelectedList(candidate)
        self._setAvailableCandidateChecked(region_obj, True)
        selected_count = len(self._selected_candidates())
        self.statusLabel.setText(
            "Selected {}. {} region object(s) selected.".format(region_name, selected_count))
        return True

    def addSelection(self, doc_name, obj_name, sub, selected_point=None):
        if self.choosing_regions:
            self._addSelectionCandidate(doc_name, obj_name, sub)
        elif self.choosing_faces:
            self._addFaceSelection(doc_name, obj_name, sub)

    def _refreshFaceList(self):
        self.faceList.clear()
        pair_colors = {}
        for ref_obj, subnames in self.obj.ShapeRefs:
            for subname in subnames:
                item = QtGui.QListWidgetItem("{}:{}".format(ref_obj.Label, subname))
                item.setData(QtCore.Qt.UserRole, (ref_obj.Name, subname))
                try:
                    face = ref_obj.Shape.getElement(subname)
                    pair_key = CfdRegionCoupledInterface._touching_region_key(face, self.obj.RegionObjects)
                except Exception:
                    pair_key = None
                if pair_key is not None:
                    if pair_key not in pair_colors:
                        color_index = len(pair_colors) % len(CfdRegionCoupledInterface.INTERFACE_FACE_COLORS)
                        pair_colors[pair_key] = CfdRegionCoupledInterface.INTERFACE_FACE_COLORS[color_index]
                    r, g, b = pair_colors[pair_key]
                    item.setBackground(QtGui.QBrush(QtGui.QColor.fromRgbF(r, g, b, 0.35)))
                    item.setToolTip("{} interface".format("-".join(pair_key)))
                self.faceList.addItem(item)

    def setInterfaceFaceListSelection(self, row):
        if row < 0:
            return
        item = self.faceList.item(row)
        if item is None:
            return
        ref_obj_name, subname = item.data(QtCore.Qt.UserRole)
        ref_obj = self.obj.Document.getObject(ref_obj_name)
        if ref_obj is None:
            return
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(ref_obj, subname)

    def addFaceButtonClicked(self):
        choosing = not self.choosing_faces
        if choosing and len(FreeCADGui.Selection.getSelectionEx()) >= 1:
            added = False
            for sel in FreeCADGui.Selection.getSelectionEx():
                if sel.HasSubObjects:
                    for sub in sel.SubElementNames:
                        added = self._addFaceSelection(sel.DocumentName, sel.ObjectName, sub) or added
            choosing = False
            if not added:
                self.statusLabel.setText("Select one or more faces before pressing Add.")
        self._enableChoosingFaces(choosing)

    def _enableChoosingFaces(self, choosing):
        if self.choosing_faces == choosing:
            self.addFaceButton.setChecked(choosing)
            return
        if choosing:
            self._enableChoosingRegions(False)
        self.choosing_faces = choosing
        if self.choosing_faces:
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addObserver(self)
            self.statusLabel.setText("Select interface faces by single-clicking in the viewport.")
        else:
            FreeCADGui.Selection.removeObserver(self)
            self.statusLabel.setText("")
        self.addFaceButton.setChecked(self.choosing_faces)

    def _addFaceSelection(self, doc_name, obj_name, sub):
        if FreeCADGui.activeDocument().Document.Name != self.obj.Document.Name:
            return False
        if not sub or not str(sub).startswith("Face"):
            self.statusLabel.setText("Selection is not a face: {}".format(obj_name))
            return False
        selected_object = FreeCAD.getDocument(doc_name).getObject(obj_name)
        self._appendShapeRef(selected_object, str(sub))
        self._refreshFaceList()
        self._recomputeInterfaceObject()
        self.statusLabel.setText("Added interface face {}:{}.".format(selected_object.Label, sub))
        return True

    def _appendShapeRef(self, ref_obj, subname):
        shape_refs = list(self.obj.ShapeRefs)
        for idx, (existing_obj, subnames) in enumerate(shape_refs):
            if existing_obj.Name == ref_obj.Name:
                if subname not in subnames:
                    shape_refs[idx] = (existing_obj, tuple(list(subnames) + [subname]))
                self.obj.ShapeRefs = shape_refs
                return
        shape_refs.append((ref_obj, (subname,)))
        self.obj.ShapeRefs = shape_refs

    def removeSelectedInterfaceFaces(self):
        selected_items = list(self.faceList.selectedItems())
        if not selected_items:
            return
        remove_refs = set(item.data(QtCore.Qt.UserRole) for item in selected_items)
        new_shape_refs = []
        for ref_obj, subnames in self.obj.ShapeRefs:
            remaining = tuple(subname for subname in subnames
                              if (ref_obj.Name, subname) not in remove_refs)
            if remaining:
                new_shape_refs.append((ref_obj, remaining))
        self.obj.ShapeRefs = new_shape_refs
        self._refreshFaceList()
        self._recomputeInterfaceObject()
        self.statusLabel.setText("Removed {} interface face(s).".format(len(selected_items)))

    def _recomputeInterfaceObject(self):
        self.obj.touch()
        self.obj.Document.recompute()

    def generateTouchingPatches(self):
        selected = self._selected_candidates()
        if len(selected) < 2:
            CfdTools.cfdErrorBox("Select at least two region objects to couple.")
            return

        region_names = [region_name for region_name, _obj, _shape in selected]
        region_objects = [obj for _region_name, obj, _shape in selected]
        try:
            container, face_names = CfdRegionCoupledInterface.generateTouchingFaceRefs(region_objects)
        except ValueError as err:
            CfdTools.cfdErrorBox(str(err))
            return

        self.obj.RegionNames = region_names
        self.obj.RegionObjects = region_objects
        self.obj.ShapeRefs = [(container, tuple(face_names))]
        self.statusLabel.setText(
            "Generated {} interface face(s) from {}.".format(len(face_names), container.Label))
        self._refreshFaceList()
        self._recomputeInterfaceObject()

    def accept(self):
        if self.choosing_regions:
            FreeCADGui.Selection.removeObserver(self)
            self.choosing_regions = False
        if self.choosing_faces:
            FreeCADGui.Selection.removeObserver(self)
            self.choosing_faces = False
        selected = self._selected_candidates()
        if len(selected) < 2:
            CfdTools.cfdErrorBox("Select at least two region objects to couple.")
            return False
        if not self.obj.ShapeRefs:
            CfdTools.cfdErrorBox("Generate touching patches before closing the task panel.")
            return False
        self.obj.RegionNames = [region_name for region_name, _obj, _shape in selected]
        self.obj.RegionObjects = [obj for _region_name, obj, _shape in selected]
        self.obj.ThermalBoundaryType = self.thermalCombo.currentText()
        self.analysis_obj.NeedsCaseRewrite = True
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()
        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")
        return True

    def reject(self):
        if self.choosing_regions:
            FreeCADGui.Selection.removeObserver(self)
            self.choosing_regions = False
        if self.choosing_faces:
            FreeCADGui.Selection.removeObserver(self)
            self.choosing_faces = False
        self.obj.RegionNames = self.RegionNamesOrig
        self.obj.RegionObjects = self.RegionObjectsOrig
        self.obj.ShapeRefs = self.ShapeRefsOrig
        self.obj.ThermalBoundaryType = self.ThermalBoundaryTypeOrig
        self.analysis_obj.NeedsCaseRewrite = self.NeedsCaseRewriteOrig
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()
        return True

    def closing(self):
        if self.choosing_regions:
            FreeCADGui.Selection.removeObserver(self)
            self.choosing_regions = False
        if self.choosing_faces:
            FreeCADGui.Selection.removeObserver(self)
            self.choosing_faces = False
        return
