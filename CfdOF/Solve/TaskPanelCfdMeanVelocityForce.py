# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os

import FreeCAD
from FreeCAD import Units
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

        self.form.inputUbarX.setText("{} mm/s".format(float(self.obj.Ubar.x) * 1000.0))
        self.form.inputUbarY.setText("{} mm/s".format(float(self.obj.Ubar.y) * 1000.0))
        self.form.inputUbarZ.setText("{} mm/s".format(float(self.obj.Ubar.z) * 1000.0))

        self.form.inputRelaxation.setText(str(float(self.obj.Relaxation)))

    def _getFloat(self, widget, field_name):
        val = widget.text().strip()
        try:
            return float(val)
        except ValueError:
            raise ValueError("{} must be a valid number".format(field_name))

    def _getVelocity(self, widget, field_name):
        val = widget.text().strip()
        if not val:
            raise ValueError("{} must be a valid velocity".format(field_name))

        if any(u in val for u in ('m/s', 'mm/s', 'cm/s', 'km/h')):
            try:
                qty = Units.Quantity(val)
            except Exception:
                raise ValueError("{} must be a valid velocity (e.g. 1000 mm/s)".format(field_name))
            return qty.getValueAs('m/s')

        try:
            numeric = float(val)
        except ValueError:
            raise ValueError("{} must be a valid velocity (e.g. 1000 mm/s)".format(field_name))
        # Unitless entry defaults to mm/s by request
        return numeric / 1000.0

    def accept(self):
        try:
            direction = FreeCAD.Vector(
                self._getFloat(self.form.inputDirectionX, 'Direction X'),
                self._getFloat(self.form.inputDirectionY, 'Direction Y'),
                self._getFloat(self.form.inputDirectionZ, 'Direction Z'))
            ubar = FreeCAD.Vector(
                self._getVelocity(self.form.inputUbarX, 'Ubar X'),
                self._getVelocity(self.form.inputUbarY, 'Ubar Y'),
                self._getVelocity(self.form.inputUbarZ, 'Ubar Z'))
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
