# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD
from CfdOF import CfdTools
from CfdOF.CfdTools import storeIfChanged
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
        self.form.inputDirectionX.setText(str(float(self.obj.Direction.x)))
        self.form.inputDirectionY.setText(str(float(self.obj.Direction.y)))
        self.form.inputDirectionZ.setText(str(float(self.obj.Direction.z)))

        self.form.inputUbarX.setText(str(float(self.obj.Ubar.x)))
        self.form.inputUbarY.setText(str(float(self.obj.Ubar.y)))
        self.form.inputUbarZ.setText(str(float(self.obj.Ubar.z)))

        self.form.inputRelaxation.setText(str(float(self.obj.Relaxation)))

    def _getFloat(self, widget, field_name):
        val = widget.text().strip()
        try:
            return float(val)
        except ValueError:
            raise ValueError("{} must be a valid number".format(field_name))

    def accept(self):
        try:
            direction = FreeCAD.Vector(
                self._getFloat(self.form.inputDirectionX, 'Direction X'),
                self._getFloat(self.form.inputDirectionY, 'Direction Y'),
                self._getFloat(self.form.inputDirectionZ, 'Direction Z'))
            ubar = FreeCAD.Vector(
                self._getFloat(self.form.inputUbarX, 'Ubar X'),
                self._getFloat(self.form.inputUbarY, 'Ubar Y'),
                self._getFloat(self.form.inputUbarZ, 'Ubar Z'))
            relaxation = self._getFloat(self.form.inputRelaxation, 'Relaxation')
        except ValueError as err:
            CfdTools.cfdErrorBox(str(err))
            return

        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

        storeIfChanged(self.obj, 'Direction', direction)
        storeIfChanged(self.obj, 'Ubar', ubar)
        storeIfChanged(self.obj, 'Relaxation', relaxation)

        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")

    def reject(self):
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()
