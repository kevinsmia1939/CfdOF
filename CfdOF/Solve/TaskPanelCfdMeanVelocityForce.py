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
        self.form.inputDirectionX.setValue(float(self.obj.Direction.x))
        self.form.inputDirectionY.setValue(float(self.obj.Direction.y))
        self.form.inputDirectionZ.setValue(float(self.obj.Direction.z))

        self.form.inputUbarX.setValue(float(self.obj.Ubar.x))
        self.form.inputUbarY.setValue(float(self.obj.Ubar.y))
        self.form.inputUbarZ.setValue(float(self.obj.Ubar.z))

        self.form.inputRelaxation.setValue(float(self.obj.Relaxation))

    def accept(self):
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

        storeIfChanged(
            self.obj,
            'Direction',
            FreeCAD.Vector(self.form.inputDirectionX.value(), self.form.inputDirectionY.value(), self.form.inputDirectionZ.value()))
        storeIfChanged(
            self.obj,
            'Ubar',
            FreeCAD.Vector(self.form.inputUbarX.value(), self.form.inputUbarY.value(), self.form.inputUbarZ.value()))
        storeIfChanged(self.obj, 'Relaxation', self.form.inputRelaxation.value())

        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")

    def reject(self):
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()
