# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD
from FreeCAD import Units
from CfdOF import CfdTools
from CfdOF.CfdTools import setQuantity, getQuantity, storeIfChanged
from CfdOF.Solve import CfdMeanVelocityForce
if FreeCAD.GuiUp:
    import FreeCADGui


class TaskPanelCfdMeanVelocityForce:
    """
    Task panel for adding/editing mean velocity force fvOption objects
    """
    def __init__(self, obj):
        self.obj = obj

        ui_path = os.path.join(CfdTools.getModulePath(), 'Gui', "TaskPanelCfdMeanVelocityForce.ui")
        self.form = FreeCADGui.PySideUic.loadUi(ui_path)

        self.load()

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
        self.form.comboSelectionMode.currentIndexChanged.connect(self.updateUI)
        self.updateUI()

    def updateUI(self):
        use_cell_zone = self.form.comboSelectionMode.currentText() == 'cellZone'
        self.form.labelCellZone.setVisible(use_cell_zone)
        self.form.inputCellZone.setVisible(use_cell_zone)

    def _toMS(self, widget, field_name):
        try:
            return Units.Quantity(getQuantity(widget)).getValueAs('m/s')
        except Exception:
            raise ValueError("{} must be a valid velocity".format(field_name))

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
            cell_zone = self.form.inputCellZone.text().strip()
            if selection_mode == 'cellZone' and not cell_zone:
                raise ValueError("Cell zone must be specified when selection mode is cellZone")
        except ValueError as err:
            CfdTools.cfdErrorBox(str(err))
            return

        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

        storeIfChanged(self.obj, 'Direction', direction)
        storeIfChanged(self.obj, 'Ubar', ubar)
        storeIfChanged(self.obj, 'Relaxation', relaxation)
        storeIfChanged(self.obj, 'SelectionMode', selection_mode)
        storeIfChanged(self.obj, 'CellZone', cell_zone)

        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")

    def reject(self):
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()
