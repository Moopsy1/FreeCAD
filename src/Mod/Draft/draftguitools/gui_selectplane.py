# ***************************************************************************
# *   Copyright (c) 2019 Yorik van Havre <yorik@uncreated.net>              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************
"""Provides the Draft SelectPlane tool."""
## @package gui_selectplane
# \ingroup DRAFT
# \brief This module provides the Draft SelectPlane tool.

import math
from pivy import coin
from PySide import QtGui
from PySide.QtCore import QT_TRANSLATE_NOOP

import FreeCAD
import FreeCADGui
import Draft
import Draft_rc
import DraftVecUtils
import drafttaskpanels.task_selectplane as task_selectplane
from draftutils.todo import todo
from draftutils.messages import _msg
from draftutils.translate import translate

# The module is used to prevent complaints from code checkers (flake8)
True if Draft_rc.__name__ else False

__title__ = "FreeCAD Draft Workbench GUI Tools - Working plane-related tools"
__author__ = ("Yorik van Havre, Werner Mayer, Martin Burbaum, Ken Cline, "
              "Dmitry Chigrin")
__url__ = "https://www.freecadweb.org"


class Draft_SelectPlane:
    """The Draft_SelectPlane FreeCAD command definition."""

    def __init__(self):
        self.ac = "FreeCAD.DraftWorkingPlane.alignToPointAndAxis"
        self.param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft")
        self.states = []

    def GetResources(self):
        """Set icon, menu and tooltip."""
        _msg = ("Select the face of solid body to create a working plane "
                "on which to sketch Draft objects.\n"
                "You may also select a three vertices or "
                "a Working Plane Proxy.")
        d = {'Pixmap': 'Draft_SelectPlane',
             'Accel': "W, P",
             'MenuText': QT_TRANSLATE_NOOP("Draft_SelectPlane", "SelectPlane"),
             'ToolTip': QT_TRANSLATE_NOOP("Draft_SelectPlane", _msg)}
        return d

    def IsActive(self):
        """Return True when this command should be available."""
        if FreeCADGui.ActiveDocument:
            return True
        else:
            return False

    def Activated(self):
        """Execute when the command is called."""
        # Reset variables
        self.view = Draft.get3DView()
        self.wpButton = FreeCADGui.draftToolBar.wplabel
        FreeCAD.DraftWorkingPlane.setup()

        # Write current WP if states are empty
        if not self.states:
            p = FreeCAD.DraftWorkingPlane
            self.states.append([p.u, p.v, p.axis, p.position])

        m = translate("draft", "Pick a face, 3 vertices "
                      "or a WP Proxy to define the drawing plane")
        _msg(m)

        # Create task panel
        FreeCADGui.Control.closeDialog()
        self.taskd = task_selectplane.SelectPlaneTaskPanel()

        # Fill values
        self.taskd.form.checkCenter.setChecked(self.param.GetBool("CenterPlaneOnView", False))
        q = FreeCAD.Units.Quantity(self.param.GetFloat("gridSpacing", 1.0), FreeCAD.Units.Length)
        self.taskd.form.fieldGridSpacing.setText(q.UserString)
        self.taskd.form.fieldGridMainLine.setValue(self.param.GetInt("gridEvery", 10))
        self.taskd.form.fieldSnapRadius.setValue(self.param.GetInt("snapRange", 8))

        # Set icons
        self.taskd.form.setWindowIcon(QtGui.QIcon(":/icons/Draft_SelectPlane.svg"))
        self.taskd.form.buttonTop.setIcon(QtGui.QIcon(":/icons/view-top.svg"))
        self.taskd.form.buttonFront.setIcon(QtGui.QIcon(":/icons/view-front.svg"))
        self.taskd.form.buttonSide.setIcon(QtGui.QIcon(":/icons/view-right.svg"))
        self.taskd.form.buttonAlign.setIcon(QtGui.QIcon(":/icons/view-isometric.svg"))
        self.taskd.form.buttonAuto.setIcon(QtGui.QIcon(":/icons/view-axonometric.svg"))
        self.taskd.form.buttonMove.setIcon(QtGui.QIcon(":/icons/Draft_Move.svg"))
        self.taskd.form.buttonCenter.setIcon(QtGui.QIcon(":/icons/view-fullscreen.svg"))
        self.taskd.form.buttonPrevious.setIcon(QtGui.QIcon(":/icons/edit-undo.svg"))

        # Connect slots
        self.taskd.form.buttonTop.clicked.connect(self.onClickTop)
        self.taskd.form.buttonFront.clicked.connect(self.onClickFront)
        self.taskd.form.buttonSide.clicked.connect(self.onClickSide)
        self.taskd.form.buttonAlign.clicked.connect(self.onClickAlign)
        self.taskd.form.buttonAuto.clicked.connect(self.onClickAuto)
        self.taskd.form.buttonMove.clicked.connect(self.onClickMove)
        self.taskd.form.buttonCenter.clicked.connect(self.onClickCenter)
        self.taskd.form.buttonPrevious.clicked.connect(self.onClickPrevious)
        self.taskd.form.fieldGridSpacing.textEdited.connect(self.onSetGridSize)
        self.taskd.form.fieldGridMainLine.valueChanged.connect(self.onSetMainline)
        self.taskd.form.fieldSnapRadius.valueChanged.connect(self.onSetSnapRadius)

        # Try to find a WP from the current selection
        if self.handle():
            return

        # Try another method
        if FreeCAD.DraftWorkingPlane.alignToSelection():
            FreeCADGui.Selection.clearSelection()
            self.display(FreeCAD.DraftWorkingPlane.axis)
            self.finish()
            return

        # Execute the actual task panel
        FreeCADGui.Control.showDialog(self.taskd)
        self.call = self.view.addEventCallback("SoEvent", self.action)

    def finish(self, close=False):
        """Execute when the command is terminated."""
        # Store values
        self.param.SetBool("CenterPlaneOnView",
                           self.taskd.form.checkCenter.isChecked())

        # Terminate coin callbacks
        if self.call:
            try:
                self.view.removeEventCallback("SoEvent", self.call)
            except RuntimeError:
                # The view has been deleted already
                pass
            self.call = None

        # Reset everything else
        FreeCADGui.Control.closeDialog()
        FreeCAD.DraftWorkingPlane.restore()
        FreeCADGui.ActiveDocument.resetEdit()
        return True

    def reject(self):
        """Execute when clicking the Cancel button."""
        self.finish()
        return True

    def action(self, arg):
        """Set the callbacks for the view."""
        if arg["Type"] == "SoKeyboardEvent" and arg["Key"] == "ESCAPE":
            self.finish()
        if arg["Type"] == "SoMouseButtonEvent":
            if (arg["State"] == "DOWN") and (arg["Button"] == "BUTTON1"):
                # Coin detection happens before the selection
                # got a chance of being updated, so we must delay
                todo.delay(self.checkSelection, None)

    def checkSelection(self):
        """Check the selection, if there is a handle, finish the command."""
        if self.handle():
            self.finish()

    def handle(self):
        """Build a working plane. Return True if successful."""
        sel = FreeCADGui.Selection.getSelectionEx()
        if len(sel) == 1:
            sel = sel[0]
            if Draft.getType(sel.Object) == "Axis":
                FreeCAD.DraftWorkingPlane.alignToEdges(sel.Object.Shape.Edges)
                self.display(FreeCAD.DraftWorkingPlane.axis)
                return True
            elif Draft.getType(sel.Object) in ("WorkingPlaneProxy",
                                               "BuildingPart"):
                FreeCAD.DraftWorkingPlane.setFromPlacement(sel.Object.Placement, rebase=True)
                FreeCAD.DraftWorkingPlane.weak = False
                if hasattr(sel.Object.ViewObject, "AutoWorkingPlane"):
                    if sel.Object.ViewObject.AutoWorkingPlane:
                        FreeCAD.DraftWorkingPlane.weak = True
                if hasattr(sel.Object.ViewObject, "CutView") and hasattr(sel.Object.ViewObject, "AutoCutView"):
                    if sel.Object.ViewObject.AutoCutView:
                        sel.Object.ViewObject.CutView = True
                if hasattr(sel.Object.ViewObject, "RestoreView"):
                    if sel.Object.ViewObject.RestoreView:
                        if hasattr(sel.Object.ViewObject, "ViewData"):
                            if len(sel.Object.ViewObject.ViewData) >= 12:
                                d = sel.Object.ViewObject.ViewData
                                camtype = "orthographic"
                                if len(sel.Object.ViewObject.ViewData) == 13:
                                    if d[12] == 1:
                                        camtype = "perspective"
                                c = FreeCADGui.ActiveDocument.ActiveView.getCameraNode()
                                if isinstance(c, coin.SoOrthographicCamera):
                                    if camtype == "perspective":
                                        FreeCADGui.ActiveDocument.ActiveView.setCameraType("Perspective")
                                elif isinstance(c, coin.SoPerspectiveCamera):
                                    if camtype == "orthographic":
                                        FreeCADGui.ActiveDocument.ActiveView.setCameraType("Orthographic")
                                c = FreeCADGui.ActiveDocument.ActiveView.getCameraNode()
                                c.position.setValue([d[0], d[1], d[2]])
                                c.orientation.setValue([d[3], d[4], d[5], d[6]])
                                c.nearDistance.setValue(d[7])
                                c.farDistance.setValue(d[8])
                                c.aspectRatio.setValue(d[9])
                                c.focalDistance.setValue(d[10])
                                if camtype == "orthographic":
                                    c.height.setValue(d[11])
                                else:
                                    c.heightAngle.setValue(d[11])
                if hasattr(sel.Object.ViewObject, "RestoreState"):
                    if sel.Object.ViewObject.RestoreState:
                        if hasattr(sel.Object.ViewObject, "VisibilityMap"):
                            if sel.Object.ViewObject.VisibilityMap:
                                for k,v in sel.Object.ViewObject.VisibilityMap.items():
                                    o = FreeCADGui.ActiveDocument.getObject(k)
                                    if o:
                                        if o.Visibility != (v == "True"):
                                            FreeCADGui.doCommand("FreeCADGui.ActiveDocument.getObject(\""+k+"\").Visibility = "+v)
                self.display(FreeCAD.DraftWorkingPlane.axis)
                self.wpButton.setText(sel.Object.Label)
                self.wpButton.setToolTip(translate("draft", "Current working plane")+": "+self.wpButton.text())
                return True
            elif Draft.getType(sel.Object) == "SectionPlane":
                FreeCAD.DraftWorkingPlane.setFromPlacement(sel.Object.Placement, rebase=True)
                FreeCAD.DraftWorkingPlane.weak = False
                self.display(FreeCAD.DraftWorkingPlane.axis)
                self.wpButton.setText(sel.Object.Label)
                self.wpButton.setToolTip(translate("draft", "Current working plane")+": "+self.wpButton.text())
                return True
            elif sel.HasSubObjects:
                if len(sel.SubElementNames) == 1:
                    if "Face" in sel.SubElementNames[0]:
                        FreeCAD.DraftWorkingPlane.alignToFace(sel.SubObjects[0], self.getOffset())
                        self.display(FreeCAD.DraftWorkingPlane.axis)
                        return True
                    elif sel.SubElementNames[0] == "Plane":
                        FreeCAD.DraftWorkingPlane.setFromPlacement(sel.Object.Placement, rebase=True)
                        self.display(FreeCAD.DraftWorkingPlane.axis)
                        return True
                elif len(sel.SubElementNames) == 3:
                    if ("Vertex" in sel.SubElementNames[0]) \
                    and ("Vertex" in sel.SubElementNames[1]) \
                    and ("Vertex" in sel.SubElementNames[2]):
                        FreeCAD.DraftWorkingPlane.alignTo3Points(sel.SubObjects[0].Point,
                                                                 sel.SubObjects[1].Point,
                                                                 sel.SubObjects[2].Point,
                                                                 self.getOffset())
                        self.display(FreeCAD.DraftWorkingPlane.axis)
                        return True
            elif sel.Object.isDerivedFrom("Part::Feature"):
                if sel.Object.Shape:
                    if len(sel.Object.Shape.Faces) == 1:
                        FreeCAD.DraftWorkingPlane.alignToFace(sel.Object.Shape.Faces[0], self.getOffset())
                        self.display(FreeCAD.DraftWorkingPlane.axis)
                        return True
        elif sel:
            subs = []
            import Part
            for s in sel:
                for so in s.SubObjects:
                    if isinstance(so, Part.Vertex):
                        subs.append(so)
            if len(subs) == 3:
                FreeCAD.DraftWorkingPlane.alignTo3Points(subs[0].Point,
                                                         subs[1].Point,
                                                         subs[2].Point,
                                                         self.getOffset())
                self.display(FreeCAD.DraftWorkingPlane.axis)
                return True
        return False

    def getCenterPoint(self, x, y, z):
        """Get the center point."""
        if not self.taskd.form.checkCenter.isChecked():
            return FreeCAD.Vector()
        v = FreeCAD.Vector(x, y, z)
        view = FreeCADGui.ActiveDocument.ActiveView
        camera = view.getCameraNode()
        cam1 = FreeCAD.Vector(camera.position.getValue().getValue())
        cam2 = FreeCADGui.ActiveDocument.ActiveView.getViewDirection()
        vcam1 = DraftVecUtils.project(cam1, v)
        a = vcam1.getAngle(cam2)
        if a < 0.0001:
            return FreeCAD.Vector()
        d = vcam1.Length
        L = d/math.cos(a)
        vcam2 = DraftVecUtils.scaleTo(cam2, L)
        cp = cam1.add(vcam2)
        return cp

    def tostr(self, v):
        """Make a string from a vector or tuple."""
        string = "FreeCAD.Vector("
        string += str(v[0]) + ", "
        string += str(v[1]) + ", "
        string += str(v[2]) + ")"
        return string

    def getOffset(self):
        """Return the offset value as a float in mm."""
        try:
            o = float(self.taskd.form.fieldOffset.text())
        except Exception:
            o = FreeCAD.Units.Quantity(self.taskd.form.fieldOffset.text())
            o = o.Value
        return o

    def onClickTop(self):
        """Execute when pressing the top button."""
        offset = str(self.getOffset())
        _cmd = self.ac
        _cmd += "("
        _cmd += self.tostr(self.getCenterPoint(0, 0, 1)) + ", "
        _cmd += self.tostr((0, 0, 1)) + ", "
        _cmd += offset
        _cmd += ")"
        FreeCADGui.doCommandGui(_cmd)
        self.display('Top')
        self.finish()

    def onClickFront(self):
        """Execute when pressing the front button."""
        offset = str(self.getOffset())
        _cmd = self.ac
        _cmd += "("
        _cmd += self.tostr(self.getCenterPoint(0, -1, 0)) + ", "
        _cmd += self.tostr((0, -1, 0)) + ", "
        _cmd += offset
        _cmd += ")"
        FreeCADGui.doCommandGui(_cmd)
        self.display('Front')
        self.finish()

    def onClickSide(self):
        """Execute when pressing the side button."""
        offset = str(self.getOffset())
        _cmd = self.ac
        _cmd += "("
        _cmd += self.tostr(self.getCenterPoint(1, 0, 0)) + ", "
        _cmd += self.tostr((1, 0, 0)) + ", "
        _cmd += offset
        _cmd += ")"
        FreeCADGui.doCommandGui(_cmd)
        self.display('Side')
        self.finish()

    def onClickAlign(self):
        """Execute when pressing the align."""
        FreeCADGui.doCommandGui("FreeCAD.DraftWorkingPlane.setup(force=True)")
        d = self.view.getViewDirection().negative()
        self.display(d)
        self.finish()

    def onClickAuto(self):
        """Execute when pressing the auto button."""
        FreeCADGui.doCommandGui("FreeCAD.DraftWorkingPlane.reset()")
        self.display('Auto')
        self.finish()

    def onClickMove(self):
        """Execute when pressing the move button."""
        sel = FreeCADGui.Selection.getSelectionEx()
        if sel:
            verts = []
            import Part
            for s in sel:
                for so in s.SubObjects:
                    if isinstance(so, Part.Vertex):
                        verts.append(so)
            if len(verts) == 1:
                target = verts[0].Point
                FreeCAD.DraftWorkingPlane.position = target
                self.display(target)
                self.finish()
        else:
            # move the WP to the center of the current view
            c = FreeCADGui.ActiveDocument.ActiveView.getCameraNode()
            p = FreeCAD.Vector(c.position.getValue().getValue())
            d = FreeCADGui.ActiveDocument.ActiveView.getViewDirection()
            pp = FreeCAD.DraftWorkingPlane.projectPoint(p, d)
            FreeCAD.DraftWorkingPlane.position = pp
            self.display(pp)
            self.finish()

    def onClickCenter(self):
        """Execute when pressing the center button."""
        c = FreeCADGui.ActiveDocument.ActiveView.getCameraNode()
        r = FreeCAD.DraftWorkingPlane.getRotation().Rotation.Q
        c.orientation.setValue(r)
        # calculate delta
        p = FreeCAD.Vector(c.position.getValue().getValue())
        pp = FreeCAD.DraftWorkingPlane.projectPoint(p)
        delta = pp.negative()  # to bring it above the (0,0) point
        np = p.add(delta)
        c.position.setValue(tuple(np))
        self.finish()

    def onClickPrevious(self):
        """Execute when pressing the previous button."""
        p = FreeCAD.DraftWorkingPlane
        if len(self.states) > 1:
            self.states.pop()  # discard the last one
            s = self.states[-1]
            p.u = s[0]
            p.v = s[1]
            p.axis = s[2]
            p.position = s[3]
            FreeCADGui.Snapper.setGrid()
            self.finish()

    def onSetGridSize(self, text):
        """Execute when setting the grid size."""
        try:
            q = FreeCAD.Units.Quantity(text)
        except Exception:
            pass
        else:
            self.param.SetFloat("gridSpacing", q.Value)
            if hasattr(FreeCADGui, "Snapper"):
                FreeCADGui.Snapper.setGrid()

    def onSetMainline(self, i):
        """Execute when setting main line grid spacing."""
        if i > 1:
            self.param.SetInt("gridEvery", i)
            if hasattr(FreeCADGui, "Snapper"):
                FreeCADGui.Snapper.setGrid()

    def onSetSnapRadius(self, i):
        """Execute when setting the snap radius."""
        self.param.SetInt("snapRange", i)
        if hasattr(FreeCADGui, "Snapper"):
            FreeCADGui.Snapper.showradius()

    def display(self, arg):
        """Set the text of the working plane button in the toolbar."""
        o = self.getOffset()
        if o:
            if o > 0:
                suffix = ' +O'
            else:
                suffix = ' -O'
        else:
            suffix = ''
        _vdir = FreeCAD.DraftWorkingPlane.axis
        vdir = '('
        vdir += str(_vdir.x)[:4] + ','
        vdir += str(_vdir.y)[:4] + ','
        vdir += str(_vdir.z)[:4]
        vdir += ')'

        vdir = " " + translate("draft", "Dir") + ": " + vdir
        if type(arg).__name__ == 'str':
            self.wpButton.setText(arg + suffix)
            if o != 0:
                o = " " + translate("draft", "Offset") + ": " + str(o)
            else:
                o = ""
            _tool = translate("draft", "Current working plane") + ": "
            _tool += self.wpButton.text() + o + vdir
            self.wpButton.setToolTip(_tool)
        elif type(arg).__name__ == 'Vector':
            plv = '('
            plv += str(arg.x)[:6] + ','
            plv += str(arg.y)[:6] + ','
            plv += str(arg.z)[:6]
            plv += ')'
            self.wpButton.setText(translate("draft", "Custom"))
            _tool = translate("draft", "Current working plane")
            _tool += ": " + plv + vdir
            self.wpButton.setToolTip(_tool)
        p = FreeCAD.DraftWorkingPlane
        self.states.append([p.u, p.v, p.axis, p.position])
        FreeCADGui.doCommandGui("FreeCADGui.Snapper.setGrid()")


class Draft_WorkingPlaneProxy:
    """The Draft_WorkingPlaneProxy command definition."""

    def GetResources(self):
        """Set icon, menu and tooltip."""
        _menu = "Create working plane proxy"
        _tip = ("Creates a proxy object from the current working plane.\n"
                "Once the object is created double click it in the tree view "
                "to restore the camera position and objects' visibilities.\n"
                "Then you can use it to save a different camera position "
                "and objects' states any time you need.")
        d = {'Pixmap': 'Draft_PlaneProxy',
             'MenuText': QT_TRANSLATE_NOOP("Draft_SetWorkingPlaneProxy",
                                           _menu),
             'ToolTip': QT_TRANSLATE_NOOP("Draft_SetWorkingPlaneProxy",
                                          _tip)}
        return d

    def IsActive(self):
        """Return True when this command should be available."""
        if FreeCADGui.ActiveDocument:
            return True
        else:
            return False

    def Activated(self):
        """Execute when the command is called."""
        if hasattr(FreeCAD, "DraftWorkingPlane"):
            FreeCAD.ActiveDocument.openTransaction("Create WP proxy")
            FreeCADGui.addModule("Draft")
            _cmd = "Draft.makeWorkingPlaneProxy("
            _cmd += "FreeCAD.DraftWorkingPlane.getPlacement()"
            _cmd += ")"
            FreeCADGui.doCommand(_cmd)
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()


FreeCADGui.addCommand('Draft_SelectPlane', Draft_SelectPlane())
FreeCADGui.addCommand('Draft_WorkingPlaneProxy',
                      Draft_WorkingPlaneProxy())