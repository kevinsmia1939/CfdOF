# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD
from FreeCAD import Units
from CfdOF import CfdTools
from CfdOF.CfdTools import setQuantity, getQuantity, storeIfChanged
from CfdOF.Solve import CfdMeanVelocityForce
from CfdOF import CfdFaceSelectWidget
if FreeCAD.GuiUp:
    import FreeCADGui


class TaskPanelCfdMeanVelocityForce:
    """
    Task panel for adding/editing mean velocity force fvOption objects
    """
    def __init__(self, obj):
        FreeCADGui.Selection.clearSelection()
        self.obj = obj
        self.analysis_obj = CfdTools.getParentAnalysisObject(obj)

        self.ShapeRefsOrig = list(self.obj.ShapeRefs)
        self.NeedsCaseRewriteOrig = self.analysis_obj.NeedsCaseRewrite if self.analysis_obj else False

        ui_path = os.path.join(CfdTools.getModulePath(), 'Gui', "TaskPanelCfdMeanVelocityForce.ui")
        self.form = FreeCADGui.PySideUic.loadUi(ui_path)

        self.load()

        self.form.comboSelectionMode.currentIndexChanged.connect(self.updateUI)
        self.updateUI()

        self.faceSelector = CfdFaceSelectWidget.CfdFaceSelectWidget(
            self.form.faceSelectWidget,
            self.obj,
            True,
            False,
            True,
        )

    def load(self):
        self.form.comboSelectionMode.addItems(CfdMeanVelocityForce.SELECTION_MODES)

        setQuantity(self.form.inputDirectionX, self.obj.Direction.x)
        setQuantity(self.form.inputDirectionY, self.obj.Direction.y)
        setQuantity(self.form.inputDirectionZ, self.obj.Direction.z)

        setQuantity(self.form.inputUbarX, "{} mm/s".format(float(self.obj.Ubar.x) * 1000.0))
        setQuantity(self.form.inputUbarY, "{} mm/s".format(float(self.obj.Ubar.y) * 1000.0))
        setQuantity(self.form.inputUbarZ, "{} mm/s".format(float(self.obj.Ubar.z) * 1000.0))

        setQuantity(self.form.inputRelaxation, self.obj.Relaxation)

        selection_mode_index = CfdTools.indexOrDefault(
            CfdMeanVelocityForce.SELECTION_MODES,
            self.obj.SelectionMode,
            0,
        )
        self.form.comboSelectionMode.setCurrentIndex(selection_mode_index)
        self.form.inputCellZone.setText(self.obj.CellZone)

    def updateUI(self):
        use_cell_zone = self.form.comboSelectionMode.currentText() == 'cellZone'
        if use_cell_zone:
            self.form.inputCellZone.setText(self._firstSelectedSolidName())
        self.form.labelCellZone.setVisible(use_cell_zone)
        self.form.inputCellZone.setVisible(use_cell_zone)
        self.form.faceSelectWidget.setVisible(use_cell_zone)

    def _toMS(self, widget, field_name):
        try:
            return Units.Quantity(getQuantity(widget)).getValueAs('m/s')
        except Exception:
            raise ValueError("{} must be a valid velocity".format(field_name))

    def _firstSelectedSolidName(self):
        if not self.obj.ShapeRefs:
            return ""
        return self.obj.ShapeRefs[0][0].Name

    def accept(self):
        try:
            direction = FreeCAD.Vector(
                self.form.inputDirectionX.property("quantity").Value,
                self.form.inputDirectionY.property("quantity").Value,
                self.form.inputDirectionZ.property("quantity").Value)
            ubar = FreeCAD.Vector(
                self._toMS(self.form.inputUbarX, 'Ubar X'),
                self._toMS(self.form.inputUbarY, 'Ubar Y'),
                self._toMS(self.form.inputUbarZ, 'Ubar Z'))
            relaxation = self.form.inputRelaxation.property("quantity").Value
            selection_mode = self.form.comboSelectionMode.currentText()

            if selection_mode == 'cellZone':
                if not self.obj.ShapeRefs:
                    raise ValueError("Select at least one solid when selection mode is cellZone")
                if len(self.obj.ShapeRefs) > 1:
                    raise ValueError("Only one solid can be selected for mean velocity force cellZone")
                cell_zone = self._firstSelectedSolidName()
            else:
                cell_zone = ''
        except ValueError as err:
            CfdTools.cfdErrorBox(str(err))
            return

        if self.analysis_obj:
            self.analysis_obj.NeedsCaseRewrite = self.NeedsCaseRewriteOrig

        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

        storeIfChanged(self.obj, 'Direction', direction)
        storeIfChanged(self.obj, 'Ubar', ubar)
        storeIfChanged(self.obj, 'Relaxation', relaxation)
        storeIfChanged(self.obj, 'SelectionMode', selection_mode)
        storeIfChanged(self.obj, 'CellZone', cell_zone)

        if self.obj.ShapeRefs != self.ShapeRefsOrig:
            refstr = "FreeCAD.ActiveDocument.{}.ShapeRefs = [\n".format(self.obj.Name)
            refstr += ',\n'.join(
                "(FreeCAD.ActiveDocument.getObject('{}'), {})".format(ref[0].Name, ref[1]) for ref in self.obj.ShapeRefs)
            refstr += "]"
            FreeCADGui.doCommand(refstr)

        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")

    def reject(self):
        self.obj.ShapeRefs = self.ShapeRefsOrig
        FreeCADGui.doCommand("App.activeDocument().recompute()")
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

    def closing(self):
        self.faceSelector.closing()
