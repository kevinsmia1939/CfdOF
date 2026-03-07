# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD
from CfdOF import CfdTools
from CfdOF.CfdTools import setQuantity, storeIfChanged

if FreeCAD.GuiUp:
    import FreeCADGui


class TaskPanelCfdFvOptions:
    """Task panel for Cfd fvOptions object"""

    def __init__(self, obj):
        self.obj = obj
        ui_path = os.path.join(CfdTools.getModulePath(), 'Gui', 'TaskPanelCfdFvOptions.ui')
        self.form = FreeCADGui.PySideUic.loadUi(ui_path)
        self.load()

    def load(self):
        self.form.inputSourceName.setText(self.obj.SourceName)
        self.form.checkActive.setChecked(self.obj.Active)

        setQuantity(self.form.inputDirectionX, str(self.obj.Direction.x))
        setQuantity(self.form.inputDirectionY, str(self.obj.Direction.y))
        setQuantity(self.form.inputDirectionZ, str(self.obj.Direction.z))

        setQuantity(self.form.inputUbarX, '{} m/s'.format(self.obj.Ubar.x))
        setQuantity(self.form.inputUbarY, '{} m/s'.format(self.obj.Ubar.y))
        setQuantity(self.form.inputUbarZ, '{} m/s'.format(self.obj.Ubar.z))

        setQuantity(self.form.inputRelaxation, str(self.obj.Relaxation))

    @staticmethod
    def _input_value(input_field, unit):
        q = input_field.property("quantity")
        return q.getValueAs(unit).Value

    def accept(self):
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

        storeIfChanged(self.obj, 'SourceName', self.form.inputSourceName.text())
        storeIfChanged(self.obj, 'Active', self.form.checkActive.isChecked())

        direction = FreeCAD.Vector(
            self._input_value(self.form.inputDirectionX, '1'),
            self._input_value(self.form.inputDirectionY, '1'),
            self._input_value(self.form.inputDirectionZ, '1'),
        )
        storeIfChanged(self.obj, 'Direction', direction)

        ubar = FreeCAD.Vector(
            self._input_value(self.form.inputUbarX, 'm/s'),
            self._input_value(self.form.inputUbarY, 'm/s'),
            self._input_value(self.form.inputUbarZ, 'm/s'),
        )
        storeIfChanged(self.obj, 'Ubar', ubar)

        storeIfChanged(self.obj, 'Relaxation', self._input_value(self.form.inputRelaxation, '1'))

        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")

    def reject(self):
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()
