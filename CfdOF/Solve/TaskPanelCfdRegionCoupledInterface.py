# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore
    from PySide import QtGui

from CfdOF import CfdTools
from CfdOF import CfdFaceSelectWidget
from CfdOF.CfdTools import storeIfChanged


translate = FreeCAD.Qt.translate


class _InterfaceSideSelectionProxy:
    """Expose one ShapeRefs property as ShapeRefs for CfdFaceSelectWidget."""

    def __init__(self, obj, shape_refs_prop):
        self._obj = obj
        self._shape_refs_prop = shape_refs_prop
        self.ShapeRefs = list(getattr(obj, shape_refs_prop))

    def __getattr__(self, name):
        return getattr(self._obj, name)

    def commit(self):
        setattr(self._obj, self._shape_refs_prop, self.ShapeRefs)


class TaskPanelCfdRegionCoupledInterface:
    """Task panel for editing a paired region-coupled interface."""

    def __init__(self, obj):
        self.obj = obj
        self.analysis_obj = CfdTools.getParentAnalysisObject(obj)

        self.Region1NameOrig = str(self.obj.Region1Name)
        self.Patch1NameOrig = str(self.obj.Patch1Name)
        self.ShapeRefs1Orig = list(self.obj.ShapeRefs1)
        self.Region2NameOrig = str(self.obj.Region2Name)
        self.Patch2NameOrig = str(self.obj.Patch2Name)
        self.ShapeRefs2Orig = list(self.obj.ShapeRefs2)
        self.CouplingTypeOrig = str(self.obj.CouplingType)
        self.ThermalBoundaryTypeOrig = str(self.obj.ThermalBoundaryType)
        self.NeedsMeshRewriteOrig = self.analysis_obj.NeedsMeshRewrite
        self.NeedsCaseRewriteOrig = self.analysis_obj.NeedsCaseRewrite

        self.form = QtGui.QWidget()
        self.form.setWindowTitle(translate("CfdOF", "Region-coupled interface"))
        layout = QtGui.QVBoxLayout(self.form)

        self.inputRegion1Name, self.inputPatch1Name, self.side1Selector = self._createSideGroup(
            layout,
            translate("CfdOF", "Side 1"),
            self.obj.Region1Name,
            self.obj.Patch1Name,
            "ShapeRefs1",
        )
        self.inputRegion2Name, self.inputPatch2Name, self.side2Selector = self._createSideGroup(
            layout,
            translate("CfdOF", "Side 2"),
            self.obj.Region2Name,
            self.obj.Patch2Name,
            "ShapeRefs2",
        )

        coupling_group = QtGui.QGroupBox(translate("CfdOF", "Coupling"))
        coupling_layout = QtGui.QFormLayout(coupling_group)
        self.comboCouplingType = QtGui.QComboBox()
        self.comboCouplingType.addItem("mappedWallAMI")
        self.comboCouplingType.setCurrentIndex(0)
        self.comboCouplingType.setEnabled(False)
        self.inputThermalBoundaryType = QtGui.QLineEdit(self.obj.ThermalBoundaryType)
        coupling_layout.addRow(translate("CfdOF", "Type"), self.comboCouplingType)
        coupling_layout.addRow(translate("CfdOF", "Fallback thermal BC"), self.inputThermalBoundaryType)
        layout.addWidget(coupling_group)

        layout.addStretch()

    def _createSideGroup(self, parent_layout, title, region_name, patch_name, refs_prop):
        group = QtGui.QGroupBox(title)
        group_layout = QtGui.QVBoxLayout(group)
        form_layout = QtGui.QFormLayout()

        input_region_name = QtGui.QLineEdit(region_name)
        input_patch_name = QtGui.QLineEdit(patch_name)
        form_layout.addRow(translate("CfdOF", "Region name"), input_region_name)
        form_layout.addRow(translate("CfdOF", "Patch name"), input_patch_name)
        group_layout.addLayout(form_layout)

        selector_widget = QtGui.QWidget()
        selector_widget.setLayout(QtGui.QVBoxLayout())
        selector_proxy = _InterfaceSideSelectionProxy(self.obj, refs_prop)
        selector = CfdFaceSelectWidget.CfdFaceSelectWidget(
            selector_widget,
            selector_proxy,
            False,
            True,
            False,
        )
        selector.proxy = selector_proxy
        group_layout.addWidget(selector_widget)
        parent_layout.addWidget(group)
        return input_region_name, input_patch_name, selector

    def accept(self):
        region1_name = self.inputRegion1Name.text().strip()
        region2_name = self.inputRegion2Name.text().strip()
        patch1_name = self.inputPatch1Name.text().strip()
        patch2_name = self.inputPatch2Name.text().strip()
        thermal_boundary_type = self.inputThermalBoundaryType.text().strip()

        if not region1_name or not region2_name:
            CfdTools.cfdErrorBox("Both region names must be specified.")
            return False
        if not self.side1Selector.proxy.ShapeRefs or not self.side2Selector.proxy.ShapeRefs:
            CfdTools.cfdErrorBox("Faces must be selected for both sides of the interface.")
            return False

        storeIfChanged(self.obj, 'Region1Name', region1_name)
        storeIfChanged(self.obj, 'Patch1Name', patch1_name)
        self.side1Selector.proxy.commit()
        storeIfChanged(self.obj, 'Region2Name', region2_name)
        storeIfChanged(self.obj, 'Patch2Name', patch2_name)
        self.side2Selector.proxy.commit()
        storeIfChanged(self.obj, 'CouplingType', "mappedWallAMI")
        storeIfChanged(self.obj, 'ThermalBoundaryType', thermal_boundary_type)

        self.obj.Document.recompute()
        FreeCADGui.getDocument(self.obj.Document).resetEdit()
        return True

    def reject(self):
        self.obj.Region1Name = self.Region1NameOrig
        self.obj.Patch1Name = self.Patch1NameOrig
        self.obj.ShapeRefs1 = self.ShapeRefs1Orig
        self.obj.Region2Name = self.Region2NameOrig
        self.obj.Patch2Name = self.Patch2NameOrig
        self.obj.ShapeRefs2 = self.ShapeRefs2Orig
        self.obj.CouplingType = self.CouplingTypeOrig
        self.obj.ThermalBoundaryType = self.ThermalBoundaryTypeOrig
        self.analysis_obj.NeedsMeshRewrite = self.NeedsMeshRewriteOrig
        self.analysis_obj.NeedsCaseRewrite = self.NeedsCaseRewriteOrig

        self.obj.Document.recompute()
        FreeCADGui.getDocument(self.obj.Document).resetEdit()
        return True

    def closing(self):
        self.side1Selector.closing()
        self.side2Selector.closing()

