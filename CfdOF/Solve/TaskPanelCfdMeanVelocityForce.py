# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import math
import os

import FreeCAD
from FreeCAD import Units
from CfdOF import CfdTools, CfdFaceSelectWidget
from CfdOF.CfdTools import setQuantity, getMeshObject, getQuantity, if2Float, makeShapeFromReferences, storeIfChanged
from CfdOF.Solve.CfdMeanVelocityForce import VELOCITY_PROFILES

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtGui
    from CfdOF.PreviewShapes import directionVectorToAxisAngle, getPrevPointSize, initPrevArrow
    from pivy import coin

SELECTION_MODE_LABELS = ["all", "cellZone"]
SINE_PROPERTIES = ("SineAverageVelocity", "SineAmplitude", "SineFrequency")


class TaskPanelCfdMeanVelocityForce:
    """
    Task panel for adding/editing mean velocity force fvOption objects
    """
    if FreeCAD.GuiUp:
        prev_arrow_node = coin.SoSeparator()
        prev_arrow_move_node = coin.SoTransform()
        prev_arrow_move_node.scaleFactor.setValue([5, 5, 5]) # the default size for the arrow
        prev_arrow_move_node.translation.setValue(0, 0, 0) # the defualt position for the arrow
    def __init__(self, obj):
        self.obj = obj
        self.analysis_obj = CfdTools.getParentAnalysisObject(obj)

        self.ShapeRefsOrig = list(self.obj.ShapeRefs)
        self.NeedsCaseRewriteOrig = self.analysis_obj.NeedsCaseRewrite

        ui_path = os.path.join(CfdTools.getModulePath(), 'Gui', "TaskPanelCfdMeanVelocityForce.ui")
        self.form = FreeCADGui.PySideUic.loadUi(ui_path)

        self.form.faceSelectWidget.setLayout(QtGui.QVBoxLayout())
        self.faceSelector = CfdFaceSelectWidget.CfdFaceSelectWidget(
            self.form.faceSelectWidget, self.obj, False, False, True)

        self.form.comboSelectionMode.currentIndexChanged.connect(self.updateUI)
        self.form.comboVelocityProfile.currentIndexChanged.connect(self.updateUI)
        if FreeCAD.GuiUp:
            self.mesh_obj = getMeshObject(self.analysis_obj)
            self.form.inputDirectionX.valueChanged.connect(self.updateArrowDirection)
            self.form.inputDirectionY.valueChanged.connect(self.updateArrowDirection)
            self.form.inputDirectionZ.valueChanged.connect(self.updateArrowDirection)

        self.load()
        self.updateUI()

    def load(self):
        mode = getattr(self.obj, 'SelectionMode', 'all')
        try:
            idx = SELECTION_MODE_LABELS.index(mode)
        except ValueError:
            idx = 0
        self.form.comboSelectionMode.setCurrentIndex(idx)

        setQuantity(self.form.inputDirectionX, Units.Quantity(float(self.obj.Direction.x)))
        setQuantity(self.form.inputDirectionY, Units.Quantity(float(self.obj.Direction.y)))
        setQuantity(self.form.inputDirectionZ, Units.Quantity(float(self.obj.Direction.z)))
        if FreeCAD.GuiUp:
            self.updateArrowDirection()
            self.updateArrowData()
            initPrevArrow(self.prev_arrow_node, self.prev_arrow_move_node, 0,1,0)

        setQuantity(self.form.inputUbarX, Units.Quantity("{} mm/s".format(float(self.obj.Ubar.x) * 1000.0)))
        setQuantity(self.form.inputUbarY, Units.Quantity("{} mm/s".format(float(self.obj.Ubar.y) * 1000.0)))
        setQuantity(self.form.inputUbarZ, Units.Quantity("{} mm/s".format(float(self.obj.Ubar.z) * 1000.0)))

        self.form.comboVelocityProfile.setCurrentIndex(VELOCITY_PROFILES.index(self.obj.VelocityProfile))
        for name in SINE_PROPERTIES:
            setQuantity(getattr(self.form, 'input' + name), getattr(self.obj, name))

        setQuantity(self.form.inputRelaxation, Units.Quantity(self.obj.Relaxation))

    def updateUI(self):
        is_cell_zone = self.form.comboSelectionMode.currentIndex() == 1
        self.form.faceSelectWidget.setVisible(is_cell_zone)
        sine = self.form.comboVelocityProfile.currentIndex() == 1
        for name in ('labelUbar', 'inputUbarX', 'inputUbarY', 'inputUbarZ'):
            getattr(self.form, name).setVisible(not sine)
        for name in SINE_PROPERTIES:
            getattr(self.form, 'label' + name).setVisible(sine)
            getattr(self.form, 'input' + name).setVisible(sine)
        if FreeCAD.GuiUp:
            self.updateArrowData()

    def updateArrowData(self):
        mode = SELECTION_MODE_LABELS[self.form.comboSelectionMode.currentIndex()]
        if mode == 'cellZone' and self.obj.ShapeRefs:
            combined_shapes = makeShapeFromReferences(self.obj.ShapeRefs)
            size = getPrevPointSize(combined_shapes) * 5
            self.prev_arrow_move_node.scaleFactor.setValue([size, size, size])
            self.prev_arrow_move_node.translation.setValue(combined_shapes.CenterOfGravity)
        elif mode == 'all' and self.mesh_obj: # if modes is all and mesh_obj is not none
            size = getPrevPointSize(self.mesh_obj.Part.Shape) * 5
            self.prev_arrow_move_node.scaleFactor.setValue([size, size, size])
            self.prev_arrow_move_node.translation.setValue(self.mesh_obj.Part.Shape.CenterOfGravity)
        else: # return to the defualt when could not fine niether mesh_obj nor ShapeRefs in the seclected shapes
            self.prev_arrow_move_node.scaleFactor.setValue([5, 5, 5])
            self.prev_arrow_move_node.translation.setValue(0, 0, 0)

    def updateArrowDirection(self):
        axis, angle = directionVectorToAxisAngle(FreeCAD.Vector(0, 1, 0), FreeCAD.Vector(
            if2Float(self.form.inputDirectionX),
            if2Float(self.form.inputDirectionY),
            if2Float(self.form.inputDirectionZ))
            )
        self.prev_arrow_move_node.rotation.setValue(axis, angle)

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
            profile = VELOCITY_PROFILES[self.form.comboVelocityProfile.currentIndex()]
            values = {}
            if profile == 'Sine wave':
                physics = CfdTools.getPhysicsModel(self.analysis_obj)
                if (physics is None or physics.Time != 'Transient' or
                        physics.Phase != 'Single' or physics.Flow != 'Isothermal'):
                    raise ValueError("Sine-wave mean velocity force requires a transient incompressible analysis.")
                if not math.isfinite(direction.Length) or direction.Length == 0:
                    raise ValueError("Enter a nonzero direction for the sine wave.")
                for name, unit in zip(SINE_PROPERTIES, ('m/s', 'm/s', 'Hz')):
                    quantity = getQuantity(getattr(self.form, 'input' + name))
                    value = float(Units.Quantity(quantity).getValueAs(unit))
                    if not math.isfinite(value) or (name == 'SineAmplitude' and value < 0) or (
                            name == 'SineFrequency' and value <= 0):
                        raise ValueError("Enter a finite average velocity, a nonnegative amplitude and a positive frequency.")
                    values[name] = quantity
            else:
                values['Ubar'] = FreeCAD.Vector(
                    self._toMS(self.form.inputUbarX, 'Ubar X'),
                    self._toMS(self.form.inputUbarY, 'Ubar Y'),
                    self._toMS(self.form.inputUbarZ, 'Ubar Z'))
            relaxation = self.form.inputRelaxation.property("quantity").Value
        except (ValueError, RuntimeError) as err:
            CfdTools.cfdErrorBox(str(err))
            return

        mode = SELECTION_MODE_LABELS[self.form.comboSelectionMode.currentIndex()]
        if mode == 'cellZone' and not self.obj.ShapeRefs:
            CfdTools.cfdErrorBox("Please select at least one solid for the cell zone.")
            return

        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

        storeIfChanged(self.obj, 'SelectionMode', mode)
        storeIfChanged(self.obj, 'Direction', direction)
        storeIfChanged(self.obj, 'VelocityProfile', profile)
        for name, value in values.items():
            storeIfChanged(self.obj, name, value)
        storeIfChanged(self.obj, 'Relaxation', relaxation)
        # ShapeRefs is modified in-place by CfdFaceSelectWidget — no explicit store needed

        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")

    def reject(self):
        self.obj.ShapeRefs = self.ShapeRefsOrig
        self.analysis_obj.NeedsCaseRewrite = self.NeedsCaseRewriteOrig
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

    def closing(self):
        FreeCADGui.Selection.removeObserver(self.faceSelector)
        if FreeCAD.GuiUp:
            FreeCADGui.ActiveDocument.ActiveView.getSceneGraph().removeChild(self.prev_arrow_node)
