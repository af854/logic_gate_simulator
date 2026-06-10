"""Implement the graphical user interface for the Logic Simulator.

Used in the Logic Simulator project to enable the user to run the simulation
or adjust the network properties.

Classes
-------
MyGLCanvas - handles all canvas drawing operations.
Gui - configures the main window and all the widgets.
"""

from __future__ import annotations

import contextlib
import csv
import io
import os
import sys
from typing import Any

import wx
import wx.glcanvas as wxcanvas
import wx.lib.buttons as wxbuttons
from devices import Devices
from gui_3D import Canvas3D
from monitors import Monitors
from names import Names
from network import Network
from OpenGL import GL, GLUT
from parse import Parser
from scanner import Scanner


def _(message: str) -> str:
    """Translate GUI text unless English is selected."""
    app = wx.GetApp()
    if app is not None and getattr(app, "language_code", "en") == "en":
        return message
    return wx.GetTranslation(message)


def tr(message: str, **values: Any) -> str:
    """Translate and format a GUI message."""
    return _(message).format(**values)


def set_gui_language(language_code: str) -> wx.Locale:
    """Switch wx translations for this process between English and Arabic."""
    if language_code == "en":
        os.environ["LANG"] = "en"
        language = wx.LANGUAGE_ENGLISH
    else:
        os.environ["LANG"] = "ar"
        language = wx.LANGUAGE_ARABIC

    locale = wx.Locale()
    locale.Init(language)
    locale_dir = os.path.join(os.path.dirname(__file__), "locale")
    locale.AddCatalogLookupPathPrefix(locale_dir)
    locale.AddCatalog("logsim")

    app = wx.GetApp()
    if app is not None:
        app.locale = locale
        app.language_code = language_code
    return locale


def _get_active_canvas(gui: Any) -> Any:
    """Return the active canvas for real GUI or test double instances."""
    if hasattr(gui, "canvas"):
        return gui.canvas
    if hasattr(gui, "view_3d_menu_item") and gui.view_3d_menu_item.IsChecked():
        return gui.canvas_3d
    return gui.canvas_2d


# GLUT is initialised once to avoid repeated initialisation warnings on macOS.
GLUT_INITIALISED = False


def _initialise_glut_once() -> None:
    """Initialise GLUT the first time the GUI needs bitmap text."""
    global GLUT_INITIALISED
    if not GLUT_INITIALISED:
        try:
            GLUT.glutInit(sys.argv)
            GLUT_INITIALISED = True
        except Exception as e:
            print(f"Warning: GLUT initialization failed: {e}")


# Features implemented:
# - Run the simulation for a user-specified number of cycles
# - Run the simulation one cycle at a time
# - Reset the simulation to its initial state
# - Clear the waveform traces while keeping the selected monitors
# - Add/remove monitors for any output signal in the network
# - Pan and zoom the waveform display using mouse controls or buttons
# - View status messages in a scrollable box and clear the status history
# - View the number of cycles completed since the last reset
# - Toggle switch values between HIGH and LOW
# - Monitor signals inside modules through collapsible panes, seeing a list
#   of all its signals that can be monitored
# - Option to export the waveform display as an image file
# - Option to export the monitor traces as a CSV file for analysis in Excel
#   etc.
# - Option to change the colour scheme (e.g. dark mode) of the waveform
#   display for better accessibility
# - Load circuit definition files without restarting the program
# - Show parser diagnostics in the console when a circuit file cannot be loaded
# - Hide internal parser-created signals from switch and monitor lists
# - Resolve named output ports and parser net names when adding monitors
# - panels are collapsible if user does not want them visible, e.g. the
#   available signals panel can be very long and is not always needed
# - Window menu controls to hide and restore the main side panels
# - Help menu with instructions on how to use the GUI and explanations of the
#   different features, e.g. the mouse controls for panning and zooming the
#   waveform display
# - About, keyboard shortcut, circuit syntax, and external documentation help
# - Keyboard shortcuts for common run, view, file, and help actions
# - Icon buttons and tooltips for compact actions such as add/remove, undo/redo,
#   play/pause, theme switching, and panel closing
# - Slider and text entry that show the value of all signals at a particular
#   cycle in the simulation history
# - Undo/redo buttons
# - Live tracing mode where the display advances one cycle at a time
# - Live tracing pause/resume controls and selectable playback speeds
# - Validation for missing circuit files and excessive cycle counts
#
#
# GUI responsibilities:
#    The simulator state is owned by Names, Devices, Network, and Monitors.
#    The GUI does not duplicate simulator logic. Instead, it reads state from
#    those classes, displays it, and calls their public methods in response to
#    user actions.
#
#    Gui builds the wxPython frame, panels, menus, and event bindings.
#    MyGLCanvas draws the waveform display using OpenGL and handles canvas
#    interactions such as panning, zooming, and cycle inspection.
#
# Waveform display:
#    Monitor traces are stored in monitors.monitors_dictionary. Each trace is
#    a list of signal values, with one value per simulation cycle.
#
#    The canvas converts each signal value into a y-position and each cycle
#    number into an x-position. Module signals are grouped into display rows so
#    nested module headings can be drawn above their corresponding traces.
#
# GUI state management:
#    Simulation history is stored as snapshots so undo and redo can restore
#    earlier simulator states. Live tracing advances the network one cycle at a
#    time using a wx.Timer and keeps the display aligned with the latest cycle.
#
#    File loading creates a new Names, Devices, Network, and Monitors set from
#    the selected definition file, then refreshes all panels that depend on the
#    loaded circuit.
#
# Features considered but not implemented:
# - Multiple tabs for comparing waveform displays side by side. This was not
#   implemented because exported PNG or CSV files provide a simpler comparison
#   workflow without adding substantial GUI complexity.
# - Add a search box to the available signals panel to make it easier to find
#   the signal to monitor. This was not implemented because the collapsible
#   module signal list remains navigable for the current circuit sizes.


# wxPython uses ID numbers to connect shortcuts and menu events to handlers
ID_RUN = wx.NewIdRef()
ID_RUN_ONE = wx.NewIdRef()
ID_TOGGLE_LIVE_TRACE = wx.NewIdRef()
ID_UNDO_CYCLE = wx.NewIdRef()
ID_REDO_CYCLE = wx.NewIdRef()
ID_UNDO_LAST_CYCLE = wx.NewIdRef()
ID_REDO_LAST_CYCLE = wx.NewIdRef()
ID_HELP = wx.NewIdRef()
ID_HELP_SHORTCUTS = wx.NewIdRef()
ID_HELP_SYNTAX = wx.NewIdRef()
ID_HELP_EXTERNAL_DOCS = wx.NewIdRef()
ID_CLEAR_STATUS = wx.NewIdRef()
ID_RESET_VIEW = wx.NewIdRef()
ID_TOGGLE_CYCLE_INSPECTOR = wx.NewIdRef()
ID_EXPORT_IMAGE = wx.NewIdRef()
ID_EXPORT_CSV = wx.NewIdRef()
ID_ZOOM_IN = wx.NewIdRef()
ID_ZOOM_OUT = wx.NewIdRef()
ID_OPEN_FILE = wx.NewIdRef()
ID_TOGGLE_THEME = wx.NewIdRef()
ID_TOGGLE_LANGUAGE = wx.NewIdRef()
ID_SHOW_AVAILABLE_SIGNALS = wx.NewIdRef()
ID_SHOW_SIMULATION = wx.NewIdRef()
ID_SHOW_SWITCHES = wx.NewIdRef()
ID_SHOW_CONSOLE = wx.NewIdRef()
ID_TOGGLE_3D = wx.NewIdRef()
ID_TOGGLE_MULTISAMPLE = wx.NewIdRef()


MAX_RUN_CYCLES = 1000
LIVE_TRACE_INTERVAL_MS = 1000
LIVE_TRACE_SPEEDS = [
    ("1x", 1.0),
    ("1.5x", 1.5),
    ("2x", 2.0),
    ("3x", 3.0),
    ("5x", 5.0),
    ("0.5x", 0.5),
]
MIN_FRAME_WIDTH = 900
MIN_FRAME_HEIGHT = 650
SIMULATION_CONTROL_WIDTH = 140
COMMAND_BUTTON_HEIGHT = 24
CYCLES_COMPLETED_WIDTH = 140
CYCLE_INSPECTOR_ENTRY_WIDTH = 90
CYCLE_INSPECTOR_ENTRY_HEIGHT = 22
LIVE_TRACE_BUTTON_SIZE = 28
LIVE_TRACE_SPEED_BUTTON_WIDTH = 30
CYCLE_SPIN_WIDTH = 88
SIDE_PANEL_WIDTH = 180
SIMULATION_PANEL_WIDTH = 210
SIMULATION_PANEL_HEIGHT = 230
RESET_VIEW_BUTTON_WIDTH = 106
MODULE_NESTED_INDENT_WIDTH = 12
MODULE_SIGNAL_INDENT_WIDTH = 16
SIGNAL_ACTION_BUTTON_SIZE = 18
SIGNAL_ACTION_COLUMN_WIDTH = 24
SIGNAL_LABEL_MIN_WIDTH = 64
COLLAPSIBLE_PANE_STYLE = wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE
HIERARCHY_GUIDE_WIDTH = 14
MODULE_PANE_GAP = 8


THEMES = {
    "light": {
        "frame_bg": wx.Colour(240, 240, 240),
        "panel_bg": wx.Colour(255, 255, 255),
        "text": wx.Colour(20, 24, 28),
        "muted_text": wx.Colour(95, 99, 104),
        "hierarchy_line": wx.Colour(218, 222, 226),
        "button_bg": wx.Colour(255, 255, 255),
        "toggle_on": wx.Colour(72, 170, 232),
        "toggle_off": wx.Colour(160, 164, 168),
        "toggle_text": wx.Colour(255, 255, 255),
        "add": wx.Colour(67, 150, 95),
        "remove": wx.Colour(255, 15, 15),
        "status_bg": wx.Colour(255, 255, 255),
        "status_text": wx.Colour(20, 24, 28),
        "canvas_bg": (1.0, 1.0, 1.0),
        "canvas_text": (0.12, 0.14, 0.16),
        "canvas_muted": (0.36, 0.40, 0.46),
        "canvas_axis": (0.42, 0.46, 0.52),
        "canvas_grid": (0.92, 0.94, 0.96),
        "canvas_grid_major": (0.83, 0.86, 0.90),
        "canvas_value_grid": (0.88, 0.90, 0.93),
        "canvas_trace": (0.11, 0.30, 0.85),
        "canvas_label_bg": (1.0, 1.0, 1.0),
    },
    "dark": {
        "frame_bg": wx.Colour(32, 34, 37),
        "panel_bg": wx.Colour(43, 46, 51),
        "text": wx.Colour(232, 234, 237),
        "muted_text": wx.Colour(174, 180, 188),
        "hierarchy_line": wx.Colour(82, 88, 96),
        "button_bg": wx.Colour(55, 59, 66),
        "toggle_on": wx.Colour(72, 170, 232),
        "toggle_off": wx.Colour(160, 164, 168),
        "toggle_text": wx.Colour(255, 255, 255),
        "add": wx.Colour(115, 208, 145),
        "remove": wx.Colour(255, 120, 120),
        "status_bg": wx.Colour(24, 26, 29),
        "status_text": wx.Colour(232, 234, 237),
        "canvas_bg": (0.08, 0.09, 0.10),
        "canvas_text": (0.88, 0.90, 0.94),
        "canvas_muted": (0.68, 0.72, 0.78),
        "canvas_axis": (0.58, 0.63, 0.70),
        "canvas_grid": (0.18, 0.20, 0.24),
        "canvas_grid_major": (0.28, 0.31, 0.36),
        "canvas_value_grid": (0.24, 0.27, 0.32),
        "canvas_trace": (0.42, 0.68, 1.0),
        "canvas_label_bg": (0.08, 0.09, 0.10),
    },
}

EXTERNAL_DOCUMENTATION_URL = "https://ibrahim-nur.github.io/GF2"
LIGHT_CLOSE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "x_icon_light.png"
)
DARK_CLOSE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "x_icon_dark.png"
)
LIGHT_UNDO_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "undo_light.png"
)
DARK_UNDO_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "undo_dark.png")
LIGHT_REDO_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "redo_light.png"
)
DARK_REDO_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "redo_dark.png")
LIGHT_INSPECTOR_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "inspector_light.png"
)
DARK_INSPECTOR_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "inspector_dark.png"
)
LIGHT_PLAY_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "play_light.png"
)
DARK_PLAY_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "play_dark.png")
LIGHT_PAUSE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "pause_light.png"
)
DARK_PAUSE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "pause_dark.png"
)
LIGHT_ADD_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "add_light.png")
DARK_ADD_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "add_dark.png")
LIGHT_REMOVE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "remove_light.png"
)
DARK_REMOVE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "remove_dark.png"
)


def _add_signal_to_module_tree(
    module_tree: dict[str, Any], full_signal_name: str, value: Any
) -> None:
    """Store a module signal in a tree that mirrors its arrow-separated path.

    Arguments:
    module_tree -- dictionary being built for module headings and signal rows.
    full_signal_name -- signal name such as Adder->HalfAdder->Sum.
    value -- object stored at the leaf, usually a trace or full signal name.

    Creates missing nested dictionaries and appends the final signal to the
    'signals_at_this_level' list for the deepest module

    """
    signal_parts = full_signal_name.split("->")
    module_names = signal_parts[:-1]
    short_signal_name = signal_parts[-1]
    signal_list_name = "signals_at_this_level"
    current_group = module_tree

    # Step down through the modules and create missing ones
    for module_name in module_names:
        if module_name not in current_group:
            current_group[module_name] = {}
        current_group = current_group[module_name]

    # Store the final signal at the lowest module level
    if signal_list_name not in current_group:
        current_group[signal_list_name] = []
    current_group[signal_list_name].append((short_signal_name, value))


class MyGLCanvas(wxcanvas.GLCanvas):
    """Handle all drawing operations.

    This class contains functions for drawing onto the canvas. It
    also contains handlers for events relating to the canvas.

    Parameters
    ----------
    parent: parent window.
    devices: instance of the devices.Devices() class.
    monitors: instance of the monitors.Monitors() class.

    Public methods
    --------------
    init_gl(self): Configures the OpenGL context.

    render(self): Handles all drawing operations.

    on_paint(self, event): Handles the paint event.

    on_size(self, event): Handles the canvas resize event.

    on_mouse(self, event): Handles mouse events.

    render_text(self, text, x_pos, y_pos): Handles text drawing
                                           operations.
    """

    def __init__(self, parent: wx.Window, devices: Devices, monitors: Monitors) -> None:
        """Initialise OpenGL, drawing state, and canvas event bindings.

        Creates the GL context, stores simulator references, resets pan/zoom
        values, and binds paint, resize, and mouse events

        """
        super().__init__(
            parent,
            -1,
            attribList=[
                wxcanvas.WX_GL_RGBA,
                wxcanvas.WX_GL_DOUBLEBUFFER,
                wxcanvas.WX_GL_DEPTH_SIZE,
                16,
                0,
            ],
        )
        _initialise_glut_once()
        self.init = False
        self.context = wxcanvas.GLContext(self)

        # Store the simulator objects so monitor traces and signal values can be read
        self.devices = devices
        self.monitors = monitors
        self.theme = THEMES["light"]

        # Initialise variables for panning
        self.pan_x = 0
        self.pan_y = 0
        self.last_mouse_x = 0  # previous mouse x position
        self.last_mouse_y = 0  # previous mouse y position

        # Initialise variables for zooming
        self.zoom = 1
        self.cycle_offset = 0
        self.cycle_inspector_enabled = False
        self.cycle_inspector_index = 0
        self.waveform_layout = {"start_x": 0, "step": 20, "trace_length": 0}
        self.render_size_override = None
        self.no_monitor_label = wx.StaticText(self, label="", pos=(10, 10))
        self.no_monitor_label.Hide()
        self.apply_no_monitor_label_theme()

        # Bind events to the canvas
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.on_mouse)

    def init_gl(self) -> None:
        """Configure OpenGL so waveform coordinates match window pixels.

        Sets the view and projection for the current render size, then
        applies the current pan and zoom transform before drawing

        """
        size = self.get_render_size()
        if size.width == 0 or size.height == 0:
            return
        self.SetCurrent(self.context)

        # Use window pixels as OpenGL coordinates as this makes drawing easier
        # e.g. x = 10 means about 10 pixels from the left edge, regardless of
        # the window size or zoom level
        GL.glDrawBuffer(GL.GL_BACK)
        GL.glClearColor(*self.theme["canvas_bg"], 0.0)
        GL.glViewport(0, 0, size.width, size.height)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(0, size.width, 0, size.height, -1, 1)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glTranslated(self.pan_x, self.pan_y, 0.0)
        GL.glScaled(self.zoom, self.zoom, self.zoom)

    def get_render_size(self) -> wx.Size:
        """Return the size used for drawing and layout calculations.

        Return the real canvas client size during normal drawing. During PNG
        export, return the temporary export size so the same layout code can
        draw tiles larger than the visible window.

        """
        render_size_override = getattr(self, "render_size_override", None)
        if render_size_override is not None:
            return render_size_override

        return self.GetClientSize()

    def render(self, swap_buffers: bool = True) -> None:
        """Redraw the waveform canvas.

        Optional arguments:
        swap_buffers -- if True, present the back buffer on screen. PNG export
        passes False while reading pixels from off-screen tiles.

        Clears the canvas, lays out monitor rows, draws axes, waveforms, module
        headings, and optional cycle inspector values

        """
        size = self.get_render_size()
        if size.width == 0 or size.height == 0:
            return
        self.SetCurrent(self.context)
        if not self.init:
            # Configure the viewport, modelview and projection matrices
            self.init_gl()
            self.init = True

        # Clear everything
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        size = self.get_render_size()

        if not self.monitors.monitors_dictionary:
            no_monitor_text = _("No monitor signals to display.")
            if any("\u0600" <= character <= "\u06ff" for character in no_monitor_text):
                self.show_no_monitor_label(no_monitor_text)
            else:
                self.no_monitor_label.Hide()
                self.render_text(
                    no_monitor_text,
                    10,
                    size.height - 30,
                    colour=self.theme["canvas_text"],
                )
        else:
            self.no_monitor_label.Hide()
            # First convert the monitor dictionary into display rows
            # This is the GUI equivalent of the parser's "collect, then
            # process" pass:
            # once headings and traces are in one list, the drawing loop does
            # not need to know whether a row came from a module or top level
            display_rows = self.get_monitor_display_rows()
            layout = self.get_waveform_layout(display_rows)
            display_height = layout["display_height"]
            max_trace_length = layout["trace_length"]
            start_x = layout["start_x"]
            step = layout["step"]
            self.waveform_layout = layout

            available_height = size.height - 115
            if available_height < 1:
                available_height = 1

            # Use the total display height, not just the number of rows so
            # module headings can sit closer to the signals below them
            row_gap = available_height / display_height
            if row_gap > 60:
                row_gap = 60
            if row_gap < 50:
                row_gap = 50

            # amplitude is the distance between LOW and HIGH
            amplitude = row_gap * 0.45
            if amplitude > 25:
                amplitude = 25
            if amplitude < 12:
                amplitude = 12

            top_y = size.height - 95
            bottom_y = top_y - (display_height - 1) * row_gap
            top_axis_y = top_y + amplitude + 24

            # Draw the cycle axis once, then draw each signal below it
            self.draw_cycle_axis(
                max_trace_length,
                start_x,
                top_axis_y,
                bottom_y,
                top_y + amplitude,
                step,
                self.cycle_offset,
            )

            # headings have height 0.35, signal traces have height 1
            row_position = 0
            for display_row in display_rows:
                low_y = top_y - row_position * row_gap
                high_y = low_y + amplitude

                if display_row["kind"] == "heading":
                    # heading labels a module
                    # It doesn't have a trace so only draw the text and then
                    # move down by its height
                    label_text = self.get_canvas_label_text(
                        display_row["label"], start_x
                    )
                    self.render_text(
                        label_text,
                        10,
                        low_y + amplitude / 2 - 4,
                        colour=self.theme["canvas_muted"],
                    )
                    row_position += display_row["height"]
                    continue

                label_text = self.get_canvas_label_text(display_row["label"], start_x)
                self.render_text(
                    label_text,
                    10,
                    low_y + amplitude / 2 - 4,
                    colour=self.theme["canvas_text"],
                )
                self.draw_value_axis(start_x, low_y, high_y, step, max_trace_length)

                # Draw the actual signal trace on top of the axes and grid
                GL.glColor3f(*self.theme["canvas_trace"])
                GL.glLineWidth(2.0)
                self.draw_trace(display_row["trace"], start_x, low_y, high_y, step)
                GL.glLineWidth(1.0)
                if self.cycle_inspector_enabled and max_trace_length > 0:
                    self.draw_cycle_inspector_value(
                        display_row["trace"],
                        self.cycle_inspector_index,
                        start_x,
                        low_y,
                        high_y,
                        step,
                    )
                row_position += display_row["height"]

            if self.cycle_inspector_enabled and max_trace_length > 0:
                self.draw_cycle_inspector(
                    max_trace_length,
                    start_x,
                    bottom_y,
                    top_y + amplitude,
                    step,
                )

        # We have been drawing to the back buffer, flush the graphics pipeline
        # and swap the back buffer to the front
        GL.glFlush()
        if swap_buffers:
            self.SwapBuffers()

    def on_paint(self, event: wx.PaintEvent) -> None:
        """Redraw the canvas in response to a wx paint event."""
        _ = wx.PaintDC(self)

        if not self.IsShownOnScreen():
            return
        self.SetCurrent(self.context)
        if not self.init:
            # Configure the viewport, modelview and projection matrices
            self.init_gl()
            self.init = True

        self.render()

    def on_size(self, event: wx.SizeEvent) -> None:
        """Mark the OpenGL projection as stale after a canvas resize."""
        # Forces reconfiguration of the viewport, modelview and projection
        # matrices on the next paint event
        self.init = False

    def on_mouse(self, event: wx.MouseEvent) -> None:
        """Pan by dragging and zoom around the mouse wheel position.

        Updates pan_x, pan_y, and zoom, clamps the view against the top-left
        origin, and schedules a redraw

        """
        size = self.get_render_size()
        ox = (event.GetX() - self.pan_x) / self.zoom
        oy = (size.height - event.GetY() - self.pan_y) / self.zoom
        old_zoom = self.zoom

        # 1. Track if the drag legitimately started inside this canvas
        if not hasattr(self, "_drag_initialised"):
            self._drag_initialised = False

        if event.ButtonDown():
            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
            self._drag_initialised = True  # A valid drag has started

        if event.ButtonUp() or event.Leaving():
            self._drag_initialised = False  # Reset when user lets go or leaves window

        if event.Dragging():
            if not getattr(self, "_drag_initialised", False):
                self.last_mouse_x = event.GetX()
                self.last_mouse_y = event.GetY()
                self._drag_initialised = True
                return

            self.pan_x += event.GetX() - self.last_mouse_x
            self.pan_y -= event.GetY() - self.last_mouse_y
            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
            self.limit_top_left_pan()
            self.init = False

        if event.GetWheelRotation() < 0:
            self.zoom *= 1.0 + (event.GetWheelRotation() / (20 * event.GetWheelDelta()))
            # Adjust pan so as to zoom around the mouse position
            self.pan_x -= (self.zoom - old_zoom) * ox
            self.pan_y -= (self.zoom - old_zoom) * oy
            self.limit_top_left_pan()
            self.init = False

        if event.GetWheelRotation() > 0:
            self.zoom /= 1.0 - (event.GetWheelRotation() / (20 * event.GetWheelDelta()))
            # Adjust pan so as to zoom around the mouse position
            self.pan_x -= (self.zoom - old_zoom) * ox
            self.pan_y -= (self.zoom - old_zoom) * oy
            self.limit_top_left_pan()
            self.init = False

        self.Refresh()  # triggers the paint event

    def limit_top_left_pan(self) -> None:
        """Clamp panning so the user cannot drag past the waveform origin"""
        size = self.get_render_size()
        minimum_pan_y = size.height * (1 - self.zoom)

        if self.pan_x > 0:
            self.pan_x = 0
        if self.pan_y < minimum_pan_y:
            self.pan_y = minimum_pan_y

    def zoom_at_canvas_centre(self, factor: float) -> None:
        """Scale the view while keeping the canvas centre visually fixed.

        Arguments:
        factor -- multiplier applied to the current zoom, for example 1.25 to
        zoom in or 0.8 to zoom out

        Adjusts pan as well as zoom so the centre point stays under the centre
        of the canvas after scaling.

        """
        # Find the centre of the canvas
        size = self.get_render_size()
        object_x = (size.width / 2 - self.pan_x) / self.zoom
        object_y = (size.height / 2 - self.pan_y) / self.zoom
        old_zoom = self.zoom

        self.zoom *= factor
        self.pan_x -= (self.zoom - old_zoom) * object_x
        self.pan_y -= (self.zoom - old_zoom) * object_y
        self.limit_top_left_pan()

        # The view has changed so init_gl() must run again before drawing
        self.init = False
        self.Refresh()

    def reset_view(self) -> None:
        """Return the waveform view to the unpanned unzoomed state."""
        self.pan_x = 0
        self.pan_y = 0
        self.zoom = 1
        self.init = False
        self.Refresh()

    def follow_latest_cycle(self, right_margin: int = 20) -> None:
        """Pan right just enough to keep the newest cycle visible.

        Optional arguments:
        right_margin -- minimum number of screen pixels to leave after the
        newest cycle.

        Return True if the view was moved, otherwise False.

        """
        layout = self.get_waveform_layout()
        trace_length = layout["trace_length"]
        if trace_length <= 0:
            return False

        size = self.get_render_size()
        latest_cycle_x = layout["start_x"] + trace_length * layout["step"]
        latest_screen_x = latest_cycle_x * self.zoom + self.pan_x
        maximum_visible_x = size.width - right_margin

        if latest_screen_x <= maximum_visible_x:
            return False

        self.pan_x -= latest_screen_x - maximum_visible_x
        self.limit_top_left_pan()
        self.init = False
        return True

    def get_export_image_size(self) -> wx.Size:
        """Return a PNG size large enough for all visible waveform data

        The export can be wider or taller than the current window so long
        signal names and long traces are not clipped in the saved image.

        """
        if not self.monitors.monitors_dictionary:
            return self.GetClientSize()

        display_rows = self.get_monitor_display_rows()
        display_height = 0
        max_name_length = 0
        max_trace_length = 0

        for row in display_rows:
            display_height += row["height"]
            if len(row["label"]) > max_name_length:
                max_name_length = len(row["label"])

        for monitor in self.monitors.monitors_dictionary.values():
            if len(monitor.trace) > max_trace_length:
                max_trace_length = len(monitor.trace)

        label_space = max_name_length * 8 + 70
        width = int(label_space + max_trace_length * 20 + 40)
        height = int(135 + display_height * 50)

        if width < 500:
            width = 500
        if height < 300:
            height = 300

        return wx.Size(width, height)

    def save_image(self, file_path: str) -> bool:
        """Save the current waveform display as a PNG image.

        Arguments:
        file_path -- destination path for the PNG file

        Return True if wx successfully writes the image, otherwise False.

        Temporarily renders the waveform in export-sized tiles, restores the
        user's pan/zoom state, and redraws the visible canvas afterwards.

        """
        export_size = self.get_export_image_size()
        if export_size.width <= 0 or export_size.height <= 0:
            return False

        capture_size = self.GetClientSize()
        if capture_size.width <= 0 or capture_size.height <= 0:
            return False

        old_pan_x = self.pan_x
        old_pan_y = self.pan_y
        old_zoom = self.zoom
        old_render_size_override = self.render_size_override

        try:
            export_image = self.create_blank_export_image(export_size)
            self.render_size_override = export_size
            self.zoom = 1

            for tile in self.get_export_tiles(export_size, capture_size):
                self.pan_x = -tile["source_x"]
                self.pan_y = -tile["source_y"]
                self.init = False
                self.SetCurrent(self.context)
                self.render(swap_buffers=False)

                # OpenGL pixels are read from the bottom up so mirror each tile
                # before pasting it into the png
                pixels = GL.glReadPixels(
                    0,
                    0,
                    tile["width"],
                    tile["height"],
                    GL.GL_RGB,
                    GL.GL_UNSIGNED_BYTE,
                )
                tile_image = wx.Image(tile["width"], tile["height"])
                tile_image.SetData(bytes(pixels))
                tile_image = tile_image.Mirror(False)
                export_image.Paste(tile_image, tile["dest_x"], tile["dest_y"])

            return export_image.SaveFile(file_path, wx.BITMAP_TYPE_PNG)

        finally:
            self.pan_x = old_pan_x
            self.pan_y = old_pan_y
            self.zoom = old_zoom
            self.render_size_override = old_render_size_override
            self.init = False
            self.SetCurrent(self.context)
            self.render()

    def create_blank_export_image(self, export_size: wx.Size) -> wx.Image:
        """Return an export image filled with the canvas background colour."""
        red = int(self.theme["canvas_bg"][0] * 255)
        green = int(self.theme["canvas_bg"][1] * 255)
        blue = int(self.theme["canvas_bg"][2] * 255)
        export_image = wx.Image(export_size.width, export_size.height)
        export_image.SetData(
            bytes([red, green, blue]) * export_size.width * export_size.height
        )
        return export_image

    def get_export_tiles(
        self, export_size: wx.Size, capture_size: wx.Size
    ) -> list[dict[str, int]]:
        """Return the OpenGL tiles needed to capture a full size export.

        Arguments:
        export_size -- final PNG size
        capture_size -- maximum tile size available from the visible GL canvas

        The tile source coordinates use OpenGL's bottom-left origin, while the
        destination coordinates use wx.Image's top-left origin.

        """
        tiles = []
        source_y = 0
        while source_y < export_size.height:
            tile_height = min(capture_size.height, export_size.height - source_y)
            source_x = 0
            while source_x < export_size.width:
                tile_width = min(capture_size.width, export_size.width - source_x)
                tiles.append(
                    {
                        "source_x": source_x,
                        "source_y": source_y,
                        "width": tile_width,
                        "height": tile_height,
                        "dest_x": source_x,
                        "dest_y": export_size.height - source_y - tile_height,
                    }
                )
                source_x += capture_size.width
            source_y += capture_size.height

        return tiles

    def render_text(
        self,
        text: str,
        x_pos: float,
        y_pos: float,
        colour: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        """Draw bitmap text at an OpenGL coordinate.

        Arguments:
        text -- string to draw; newline characters move down by one text row
        x_pos, y_pos -- OpenGL position of the first character
        colour -- RGB tuple using OpenGL's 0.0 to 1.0 colour range

        """
        GL.glColor3f(*colour)
        GL.glRasterPos2f(x_pos, y_pos)
        font = GLUT.GLUT_BITMAP_HELVETICA_12

        for character in text:
            if character == "\n":
                y_pos = y_pos - 20
                GL.glRasterPos2f(x_pos, y_pos)
            else:
                GLUT.glutBitmapCharacter(font, ord(character))

    def show_no_monitor_label(self, text: str) -> None:
        """Show the empty-canvas message using normal wx text."""
        self.no_monitor_label.SetLabel(text)
        self.no_monitor_label.SetPosition((10, 10))
        self.no_monitor_label.SetLayoutDirection(wx.Layout_RightToLeft)
        self.no_monitor_label.SetSize(self.no_monitor_label.GetBestSize())
        self.no_monitor_label.Show()
        self.no_monitor_label.Raise()

    def apply_no_monitor_label_theme(self) -> None:
        """Match the empty-canvas message to the canvas colours."""
        self.no_monitor_label.SetForegroundColour(
            self.opengl_colour_to_wx_colour(self.theme["canvas_text"])
        )
        self.no_monitor_label.SetBackgroundColour(
            self.opengl_colour_to_wx_colour(self.theme["canvas_bg"])
        )

    def opengl_colour_to_wx_colour(
        self, colour: tuple[float, float, float]
    ) -> wx.Colour:
        """Convert an OpenGL RGB tuple into a wx colour."""
        red, green, blue = colour
        return wx.Colour(int(red * 255), int(green * 255), int(blue * 255))

    def get_canvas_label_text(self, label_text: str, start_x: float) -> str:
        """Shorten a signal label before it overlaps the waveform area."""
        label_margin = 30
        average_character_width = 8
        available_width = start_x - label_margin
        max_characters = int(available_width / average_character_width)

        if max_characters < 4:
            return "..."
        if len(label_text) <= max_characters:
            return label_text
        return label_text[: max_characters - 3] + "..."

    def get_monitor_display_rows(self) -> list[dict[str, Any]]:
        """Return rows drawn by render() for labels, headings, and traces.

        Top-level monitors become trace rows. Module monitors are first grouped
        into a tree, then flattened into heading rows and indented trace rows.

        """
        rows = []
        module_tree = {}

        # First build a small tree from monitor names containing ->
        # e.g. A->B->Q becomes module A inside module B signal Q
        for monitor in self.monitors.monitors_dictionary.values():
            monitor_name = monitor.requested_name

            if "->" not in monitor_name:
                # Top level signals do not need a heading so draw directly as
                # normal trace rows
                rows.append(
                    {
                        "kind": "trace",
                        "label": monitor_name,
                        "trace": monitor.trace,
                        "height": 1,
                    }
                )
                continue

            _add_signal_to_module_tree(module_tree, monitor_name, monitor.trace)

        # now flatten the tree into drawing rows
        # This keeps the render() method simple because it only has to loop over
        # one list
        self.add_module_monitor_display_rows(rows, module_tree, 0)
        return rows

    def add_module_monitor_display_rows(
        self,
        rows: list[dict[str, Any]],
        signal_group: dict[str, Any],
        depth: int,
    ) -> None:
        """Append display rows for a nested module group.

        Arguments:
        rows -- list being filled with heading and trace row dictionaries
        signal_group -- subtree produced by add_signal_to_module_tree
        depth -- current module nesting depth, used for indentation

        Adds rows in sorted order so module traces appear predictably.

        """
        indent = "  " * depth

        for module_name in sorted(signal_group):
            if module_name == "signals_at_this_level":
                continue

            # Headings are given a smaller height
            rows.append(
                {
                    "kind": "heading",
                    "label": indent + module_name,
                    "height": 0.35,
                }
            )

            child_group = signal_group[module_name]
            child_indent = "  " * (depth + 1)

            for signal_name, trace in sorted(
                child_group.get("signals_at_this_level", [])
            ):
                rows.append(
                    {
                        "kind": "trace",
                        "label": child_indent + signal_name,
                        "trace": trace,
                        "height": 1,
                    }
                )

            self.add_module_monitor_display_rows(rows, child_group, depth + 1)

    def signal_to_y(self, signal: int, low_y: float, high_y: float) -> float | None:
        """Convert a simulator signal value into a waveform y-coordinate."""
        # RISING and FALLING are drawn at the level they are moving towards
        if signal in [self.devices.HIGH, self.devices.RISING]:
            return high_y

        if signal in [self.devices.LOW, self.devices.FALLING]:
            return low_y

        return None

    def draw_line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Draw one OpenGL line segment between two canvas coordinates."""
        GL.glBegin(GL.GL_LINES)
        GL.glVertex2f(x1, y1)
        GL.glVertex2f(x2, y2)
        GL.glEnd()

    def draw_filled_rectangle(
        self, x_pos: float, y_pos: float, width: float, height: float
    ) -> None:
        """Draw a filled OpenGL rectangle from its lower-left corner."""
        GL.glBegin(GL.GL_QUADS)
        GL.glVertex2f(x_pos, y_pos)
        GL.glVertex2f(x_pos + width, y_pos)
        GL.glVertex2f(x_pos + width, y_pos + height)
        GL.glVertex2f(x_pos, y_pos + height)
        GL.glEnd()

    def get_cycle_label_interval(self, step: float) -> int:
        """Return how often cycle numbers should be labelled for this scale."""
        # Do not label every cycle, otherwise the numbers overlap and become
        # unreadable - the interval depends on the zoom level
        if step >= 18:
            return 5
        if step >= 10:
            return 10
        if step >= 6:
            return 20
        return 50

    def get_waveform_layout(
        self, display_rows: list[dict[str, Any]] | None = None
    ) -> dict[str, float | int]:
        """Calculate waveform spacing shared by drawing and view controls.

        Optional arguments:
        display_rows -- precomputed monitor rows; if omitted, rows are built
        from the current monitor dictionary

        Return a dictionary containing display_height, start_x, step, and
        trace_length.

        """
        size = self.get_render_size()
        if display_rows is None:
            display_rows = self.get_monitor_display_rows()

        display_height = 0
        max_name_length = 0
        for display_row in display_rows:
            display_height += display_row["height"]
            name_length = len(display_row["label"])
            if name_length > max_name_length:
                max_name_length = name_length

        max_trace_length = 0
        for monitor in self.monitors.monitors_dictionary.values():
            trace_length = len(monitor.trace)
            if trace_length > max_trace_length:
                max_trace_length = trace_length

        label_space = max_name_length * 8 + 70
        maximum_label_space = size.width * 0.45
        if label_space > maximum_label_space:
            start_x = maximum_label_space
        else:
            start_x = label_space

        available_width = size.width - start_x - 20
        if available_width < 1:
            available_width = 1

        step = 20
        if max_trace_length > 0:
            step = available_width / max_trace_length
            if step > 20:
                step = 20
            if step < 4:
                step = 4

        return {
            "display_height": display_height,
            "start_x": start_x,
            "step": step,
            "trace_length": max_trace_length,
        }

    def draw_cycle_axis(
        self,
        trace_length: int,
        start_x: float,
        axis_y: float,
        bottom_y: float,
        top_y: float,
        step: float,
        cycle_offset: int = 0,
    ) -> None:
        """Draw the shared x-axis and vertical cycle grid lines."""
        if trace_length <= 0:
            return

        end_x = start_x + trace_length * step
        label_interval = self.get_cycle_label_interval(step)

        # Minor ticks show every cycle, numbers are shown less often depending
        # on the zoom level
        GL.glColor3f(*self.theme["canvas_axis"])
        self.draw_line(start_x, axis_y, end_x, axis_y)
        self.render_text(
            "Cycles",
            start_x - 56,
            axis_y - 4,
            colour=self.theme["canvas_muted"],
        )

        for cycle in range(0, trace_length + 1):
            x_pos = start_x + cycle * step

            # If the cycle divides exactly by label_interval, draw its number
            remainder = cycle % label_interval
            if remainder == 0:
                is_labelled_tick = True
            else:
                is_labelled_tick = False

            if is_labelled_tick:
                GL.glColor3f(*self.theme["canvas_grid_major"])
            else:
                GL.glColor3f(*self.theme["canvas_grid"])
            self.draw_line(x_pos, bottom_y - 8, x_pos, top_y + 4)

            GL.glColor3f(*self.theme["canvas_axis"])
            if is_labelled_tick:
                tick_height = 5
            else:
                tick_height = 3
            self.draw_line(x_pos, axis_y - tick_height, x_pos, axis_y + tick_height)

            if is_labelled_tick:
                cycle_label = cycle + cycle_offset
                if cycle_label < 10:
                    label_offset = 3
                else:
                    label_offset = 7
                self.render_text(
                    str(cycle_label),
                    x_pos - label_offset,
                    axis_y + 9,
                    colour=self.theme["canvas_text"],
                )

    def draw_value_axis(
        self,
        start_x: float,
        low_y: float,
        high_y: float,
        step: float,
        trace_length: int,
    ) -> None:
        """Draw the 0/1 guide lines and labels for one binary trace."""
        axis_x = start_x - 10
        end_x = start_x + trace_length * step

        # Each trace is binary, so the y-axis only needs 0 and 1
        GL.glColor3f(*self.theme["canvas_value_grid"])
        self.draw_line(start_x, low_y, end_x, low_y)
        self.draw_line(start_x, high_y, end_x, high_y)

        GL.glColor3f(*self.theme["canvas_axis"])
        self.draw_line(axis_x, low_y, axis_x, high_y)
        self.draw_line(axis_x - 4, low_y, axis_x + 4, low_y)
        self.draw_line(axis_x - 4, high_y, axis_x + 4, high_y)
        self.render_text("0", axis_x - 18, low_y - 4, colour=self.theme["canvas_muted"])
        self.render_text(
            "1", axis_x - 18, high_y - 4, colour=self.theme["canvas_muted"]
        )

    def draw_trace(
        self,
        trace: list[int],
        start_x: float,
        low_y: float,
        high_y: float,
        step: float,
    ) -> None:
        """Draw one monitor trace as horizontal LOW/HIGH waveform segments."""
        previous_y = None

        for index, signal in enumerate(trace):
            # Each list entry is one simulation cycle
            x_start = start_x + index * step
            x_end = start_x + (index + 1) * step

            current_y = self.signal_to_y(signal, low_y, high_y)

            if current_y is None:
                previous_y = None
                continue

            # Draw vertical edges between LOW and HIGH segments
            if previous_y is not None and previous_y != current_y:
                self.draw_line(x_start, previous_y, x_start, current_y)

            self.draw_line(x_start, current_y, x_end, current_y)
            previous_y = current_y

    def signal_to_display_text(self, signal: int) -> str:
        """Return compact signal text for the cycle inspector."""
        if signal == self.devices.HIGH or signal == self.devices.RISING:
            return "1"
        if signal == self.devices.LOW or signal == self.devices.FALLING:
            return "0"
        if signal == self.devices.BLANK:
            return "-"
        return str(signal)

    def draw_cycle_inspector(
        self,
        trace_length: int,
        start_x: float,
        bottom_y: float,
        top_y: float,
        step: float,
    ) -> None:
        """Draw the vertical cursor for the selected cycle."""
        if trace_length <= 0:
            return

        cursor_x = self.get_cycle_inspector_x(trace_length, start_x, step)
        GL.glColor3f(*self.theme["canvas_axis"])
        GL.glLineWidth(1.5)
        self.draw_line(cursor_x, bottom_y - 8, cursor_x, top_y + 4)
        GL.glLineWidth(1.0)

    def get_cycle_inspector_x(
        self, trace_length: int, start_x: float, step: float
    ) -> float:
        """Return the x coordinate of the cycle inspector cursor."""
        cycle_index = min(self.cycle_inspector_index, trace_length - 1)
        return start_x + (cycle_index + 1) * step

    def draw_cycle_inspector_value(
        self,
        trace: list[int],
        cycle_index: int,
        start_x: float,
        low_y: float,
        high_y: float,
        step: float,
    ) -> None:
        """Draw the inspected value beside one trace at the cursor position."""
        if cycle_index < 0 or cycle_index >= len(trace):
            value_text = "-"
        else:
            value_text = self.signal_to_display_text(trace[cycle_index])

        cursor_x = start_x + (cycle_index + 1) * step
        value_y = low_y + (high_y - low_y) / 2 - 4
        text_x = cursor_x + 6
        background_rect = self.get_cycle_inspector_value_background(
            text_x, value_y, value_text
        )
        GL.glColor3f(*self.theme["canvas_label_bg"])
        self.draw_filled_rectangle(*background_rect)
        self.render_text(value_text, text_x, value_y, colour=self.theme["canvas_text"])

    def get_cycle_inspector_value_background(
        self, text_x: float, text_y: float, value_text: str
    ) -> tuple[float, float, int, int]:
        """Return the background rectangle behind one inspected value label."""
        width = len(value_text) * 8 + 8
        height = 16
        return (text_x - 4, text_y - 4, width, height)


class Gui(wx.Frame):
    """Configure the main window and all the widgets.

    This class provides a graphical user interface for the Logic Simulator and
    enables the user to change the circuit properties and run simulations.

    Gui owns the wx controls, menus, status console, and event bindings. The
    simulator state still belongs to Names, Devices, Network, and Monitors.
    This class displays that state and calls their public methods when the user
    runs or edits the simulation.

    Arguments:
    title -- title shown in the window bar.
    path -- currently loaded circuit definition path, or None for a blank GUI.
    names -- names.Names instance used for ID/string lookup.
    devices -- devices.Devices instance containing circuit devices.
    network -- network.Network instance used to execute the circuit.
    monitors -- monitors.Monitors instance containing selected traces.
    net_driver_dict -- parser mapping from net IDs to their driving signals.

    Public methods
    --------------
    run_cycles(self, cycles): execute the network and record monitor traces.

    load_network_file(self, path): replace the current circuit from a file.

    add_monitor_by_name(self, monitor_name): add a signal to the waveform view.

    """

    def __init__(
        self,
        title: str,
        path: str | None,
        names: Names,
        devices: Devices,
        network: Network,
        monitors: Monitors,
        net_driver_dict: dict[Any, Any],
    ) -> None:
        """Create the frame, controls, menus, and initial simulator view.

        Sets up the window layout, stores simulator references, creates the
        waveform canvas, binds menu/button/keyboard events, applies the system
        theme, and disables file-dependent controls when no circuit is loaded.

        """
        self.language_code = getattr(wx.GetApp(), "language_code", "en")

        # Create the main window and set its starting size
        super().__init__(parent=None, title=_(title), size=(1200, 750))
        base_font = self.GetFont()
        base_font.SetPointSize(max(1, base_font.GetPointSize() - 1))
        self.SetFont(base_font)

        # Initialise instances of the four inner simulator classes
        self.path = path
        self.names = names
        self.devices = devices
        self.network = network
        self.monitors = monitors

        # From the parser - so GUI knows the driving
        # signals of nets to make the appropriate monitors.
        self.net_driver_dict = net_driver_dict
        self.theme_name = self.get_system_theme_name()
        self.theme = THEMES[self.theme_name]

        # Number of cycles currently shown on the trace display
        self.cycles_completed = 0
        # Total cycles since the last reset
        self.total_cycles_completed = 0

        self.simulation_history = []
        self.redo_history = []
        self.cycle_history = []
        self.cycle_redo_history = []

        self.live_trace_running = False
        self.live_trace_target_cycles = 0
        self.live_trace_cycles_completed = 0
        self.live_trace_paused = False
        self.live_trace_speed_index = 0

        # Configure the file menu
        file_menu = wx.Menu()
        export_menu = wx.Menu()
        view_menu = wx.Menu()
        window_menu = wx.Menu()
        help_menu = wx.Menu()
        menu_bar = wx.MenuBar()

        # Keep these menu items so their labels can be translated later.
        self.file_menu_items = {}
        self.export_menu_items = {}
        self.view_menu_items = {}
        self.help_menu_items = {}

        self.file_menu_items["open"] = file_menu.Append(
            ID_OPEN_FILE, _("&Open...\tCtrl+O")
        )
        file_menu.AppendSeparator()
        self.file_menu_items["exit"] = file_menu.Append(wx.ID_EXIT, _("&Exit\tCtrl+Q"))
        self.help_menu_items["quick_start"] = help_menu.Append(
            ID_HELP, _("&Quick start\tF1")
        )
        self.help_menu_items["shortcuts"] = help_menu.Append(
            ID_HELP_SHORTCUTS, _("&Keyboard shortcuts")
        )
        self.help_menu_items["syntax"] = help_menu.Append(
            ID_HELP_SYNTAX, _("&Circuit file syntax")
        )
        help_menu.AppendSeparator()
        self.help_menu_items["external_docs"] = help_menu.Append(
            ID_HELP_EXTERNAL_DOCS, _("External &documentation")
        )
        help_menu.AppendSeparator()
        self.help_menu_items["about"] = help_menu.Append(wx.ID_ABOUT, _("&About"))
        self.export_menu_items["image"] = export_menu.Append(
            ID_EXPORT_IMAGE, _("Export as PNG\tCtrl+Shift+P")
        )
        self.export_menu_items["csv"] = export_menu.Append(
            ID_EXPORT_CSV, _("Export as CSV\tCtrl+Shift+E")
        )
        self.view_menu_items["zoom_in"] = view_menu.Append(
            ID_ZOOM_IN, _("Zoom in\tCtrl+=")
        )
        self.view_menu_items["zoom_out"] = view_menu.Append(
            ID_ZOOM_OUT, _("Zoom out\tCtrl+-")
        )
        self.view_menu_items["reset_view"] = view_menu.Append(
            ID_RESET_VIEW, _("Reset view\tR")
        )
        view_menu.AppendSeparator()

        self.cycle_inspector_menu_item = view_menu.AppendCheckItem(
            ID_TOGGLE_CYCLE_INSPECTOR, _("Show cycle inspector")
        )
        self.view_3d_menu_item = view_menu.AppendCheckItem(
            ID_TOGGLE_3D, _("Enable 3D view\tCtrl+D")
        )
        self.view_aa_menu_item = view_menu.AppendCheckItem(
            ID_TOGGLE_MULTISAMPLE, _("Enable 3D anti-aliasing")
        )
        if hasattr(self, "canvas_3d") and hasattr(
            self.canvas_3d, "multisample_enabled"
        ):
            if not self.canvas_3d.multisample_enabled:
                self.view_aa_menu_item.Check(False)
                self.view_aa_menu_item.Enable(False)
            else:
                self.view_aa_menu_item.Check(True)
        else:
            self.view_aa_menu_item.Check(True)

        view_menu.AppendSeparator()

        if self.theme_name == "dark":
            theme_label = _("Switch to light mode\tCtrl+Shift+T")
        else:
            theme_label = _("Switch to dark mode\tCtrl+Shift+T")

        self.theme_menu_item = view_menu.Append(ID_TOGGLE_THEME, theme_label)
        self.language_menu_item = view_menu.Append(
            ID_TOGGLE_LANGUAGE, self.get_language_menu_label()
        )

        self.window_menu_items = {
            "available_signals": window_menu.AppendCheckItem(
                ID_SHOW_AVAILABLE_SIGNALS, _("Show Available Signals\tCtrl+1")
            ),
            "simulation": window_menu.AppendCheckItem(
                ID_SHOW_SIMULATION, _("Show Simulation\tCtrl+2")
            ),
            "switches": window_menu.AppendCheckItem(
                ID_SHOW_SWITCHES, _("Show Switches\tCtrl+3")
            ),
            "console": window_menu.AppendCheckItem(
                ID_SHOW_CONSOLE, _("Show Console\tCtrl+4")
            ),
        }

        self.menu_bar = menu_bar
        self.menu_bar_menus = [
            ("file", file_menu, "&File"),
            ("view", view_menu, "&View"),
            ("window", window_menu, "&Window"),
            ("export", export_menu, "&Export"),
            ("help", help_menu, "&Help"),
        ]
        self.update_menu_bar_order()
        self.SetMenuBar(menu_bar)
        self.update_menu_bar_order()
        self.CreateStatusBar()
        self.SetStatusText(_("Ready"))

        # Canvases for drawing signals
        self.canvas_2d = MyGLCanvas(self, devices, monitors)
        self.canvas_2d.SetMinSize((500, 420))

        self.canvas_3d = Canvas3D(self, devices, monitors)
        self.canvas_3d.SetMinSize((500, 420))
        self.canvas_3d.Hide()

        # Configure the widgets
        self.text = wx.StaticText(self, wx.ID_ANY, _("Cycles to run"))
        self.cycles_completed_text = wx.StaticText(
            self, wx.ID_ANY, tr("Cycles passed: {count}", count=0)
        )
        self.run_cycles_button = wx.Button(self, wx.ID_ANY, _("Run cycles"))
        self.live_trace_button = wxbuttons.GenBitmapButton(
            self,
            wx.ID_ANY,
            wx.Bitmap(1, 1),
            size=(LIVE_TRACE_BUTTON_SIZE, LIVE_TRACE_BUTTON_SIZE),
            style=wx.BORDER_NONE,
        )
        self.live_trace_speed_button = wxbuttons.GenButton(
            self,
            wx.ID_ANY,
            LIVE_TRACE_SPEEDS[self.live_trace_speed_index][0],
            size=(LIVE_TRACE_SPEED_BUTTON_WIDTH, LIVE_TRACE_BUTTON_SIZE),
            style=wx.BORDER_NONE,
        )
        self.reset_button = wx.Button(self, wx.ID_ANY, _("Reset simulation"))
        self.clear_traces_button = wx.Button(self, wx.ID_ANY, _("Clear traces"))
        self.live_trace_timer = wx.Timer(self)
        self.cycles_completed_text.SetMinSize((CYCLES_COMPLETED_WIDTH, -1))
        self.align_static_text(self.text)
        self.align_static_text(self.cycles_completed_text)
        self.run_cycles_button.SetMinSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.run_cycles_button.SetInitialSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.live_trace_button.SetMinSize(
            (LIVE_TRACE_BUTTON_SIZE, LIVE_TRACE_BUTTON_SIZE)
        )
        self.live_trace_speed_button.SetMinSize(
            (LIVE_TRACE_SPEED_BUTTON_WIDTH, LIVE_TRACE_BUTTON_SIZE)
        )
        self.live_trace_speed_button.SetMaxSize(
            (LIVE_TRACE_SPEED_BUTTON_WIDTH, LIVE_TRACE_BUTTON_SIZE)
        )
        self.reset_button.SetMinSize((SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT))
        self.reset_button.SetInitialSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.clear_traces_button.SetMinSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.clear_traces_button.SetInitialSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.live_trace_button.SetMaxSize(
            (LIVE_TRACE_BUTTON_SIZE, LIVE_TRACE_BUTTON_SIZE)
        )
        self.console_box = wx.TextCtrl(
            self,
            wx.ID_ANY,
            "",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
        )
        self.console_box.SetMinSize((-1, 90))
        self.clear_status_button = wx.Button(self, wx.ID_ANY, _("Clear console"))
        self.clear_status_button.SetMinSize((-1, COMMAND_BUTTON_HEIGHT))
        self.clear_status_button.SetInitialSize((-1, COMMAND_BUTTON_HEIGHT))
        self.cycle_inspector_panel = wx.Panel(self, wx.ID_ANY)
        self.cycle_inspector_label = wx.StaticText(
            self.cycle_inspector_panel, wx.ID_ANY, _("Cycle:")
        )
        self.cycle_inspector_entry = wx.TextCtrl(
            self.cycle_inspector_panel,
            wx.ID_ANY,
            "-",
            style=wx.TE_PROCESS_ENTER,
        )
        self.cycle_inspector_entry.SetMinSize(
            (CYCLE_INSPECTOR_ENTRY_WIDTH, CYCLE_INSPECTOR_ENTRY_HEIGHT)
        )
        self.cycle_inspector_entry.SetMaxSize(
            (CYCLE_INSPECTOR_ENTRY_WIDTH, CYCLE_INSPECTOR_ENTRY_HEIGHT)
        )
        self.cycle_inspector_entry.SetInitialSize(
            (CYCLE_INSPECTOR_ENTRY_WIDTH, CYCLE_INSPECTOR_ENTRY_HEIGHT)
        )
        self.cycle_inspector_slider = wx.Slider(
            self.cycle_inspector_panel,
            wx.ID_ANY,
            0,
            0,
            1,
            style=wx.SL_HORIZONTAL,
        )
        self.cycle_inspector_panel.Hide()
        self.undo_button = wxbuttons.GenBitmapButton(
            self,
            wx.ID_ANY,
            wx.Bitmap(1, 1),
            size=(28, 28),
            style=wx.BORDER_NONE,
        )
        self.redo_button = wxbuttons.GenBitmapButton(
            self,
            wx.ID_ANY,
            wx.Bitmap(1, 1),
            size=(28, 28),
            style=wx.BORDER_NONE,
        )
        self.reset_view_button = wx.Button(
            self,
            wx.ID_ANY,
            _("Reset view"),
            size=(RESET_VIEW_BUTTON_WIDTH, 28),
        )
        self.cycle_inspector_button = wxbuttons.GenBitmapButton(
            self,
            wx.ID_ANY,
            wx.Bitmap(1, 1),
            size=(28, 28),
            style=wx.BORDER_NONE,
        )
        self.undo_button.SetMinSize((28, 28))
        self.redo_button.SetMinSize((28, 28))
        self.reset_view_button.SetMinSize((RESET_VIEW_BUTTON_WIDTH, 28))
        self.reset_view_button.SetMaxSize((RESET_VIEW_BUTTON_WIDTH, 28))
        self.cycle_inspector_button.SetMinSize((28, 28))
        self.switch_rows = wx.ScrolledWindow(
            self, wx.ID_ANY, style=wx.VSCROLL | wx.BORDER_SIMPLE
        )
        self.switch_rows.SetScrollRate(0, 10)
        self.switch_rows.SetMinSize((SIDE_PANEL_WIDTH - 20, 140))
        self.switch_rows_sizer = wx.BoxSizer(wx.VERTICAL)
        self.switch_rows.SetSizer(self.switch_rows_sizer)
        self.switch_state_buttons = {}

        # This is the visible monitor picker
        self.module_signal_rows = wx.ScrolledWindow(
            self, wx.ID_ANY, style=wx.HSCROLL | wx.VSCROLL | wx.BORDER_SIMPLE
        )
        self.module_signal_rows.SetScrollRate(10, 10)
        self.module_signal_rows.SetMinSize((220, 420))
        self.module_signal_rows_sizer = wx.BoxSizer(wx.VERTICAL)
        self.module_signal_rows.SetSizer(self.module_signal_rows_sizer)

        # These dictionaries connect buttons and panes back to signal names or
        # module paths
        self.module_signal_button_names = {}
        self.module_signal_action_buttons = {}
        self.module_signal_pane_paths = {}
        self.module_signal_expanded_paths = set()

        self.monitor_rows = wx.ScrolledWindow(
            self,
            wx.ID_ANY,
            style=wx.VSCROLL | wx.BORDER_SIMPLE,
        )
        self.monitor_rows.SetScrollRate(0, 10)
        self.monitor_rows.SetMinSize((-1, 100))
        self.monitor_rows_sizer = wx.BoxSizer(wx.VERTICAL)
        self.monitor_rows.SetSizer(self.monitor_rows_sizer)
        self.monitor_button_keys = {}

        # The separate active monitors panel is hidden because the available
        # signal list now shows add or remove next to each signal
        self.monitor_rows.Hide()

        # Bind events
        self.Bind(wx.EVT_MENU, self.on_menu)
        self.Bind(wx.EVT_MENU, self.on_help, id=ID_HELP)
        self.Bind(wx.EVT_MENU, self.on_keyboard_shortcuts_help, id=ID_HELP_SHORTCUTS)
        self.Bind(wx.EVT_MENU, self.on_syntax_help, id=ID_HELP_SYNTAX)
        self.Bind(
            wx.EVT_MENU,
            self.on_external_documentation,
            id=ID_HELP_EXTERNAL_DOCS,
        )
        self.run_cycles_button.Bind(wx.EVT_BUTTON, self.on_run_cycles_button)
        self.live_trace_button.Bind(wx.EVT_BUTTON, self.on_toggle_live_trace)
        self.live_trace_speed_button.Bind(
            wx.EVT_BUTTON, self.on_live_trace_speed_button
        )
        self.reset_button.Bind(wx.EVT_BUTTON, self.on_reset_button)
        self.clear_traces_button.Bind(wx.EVT_BUTTON, self.on_clear_traces)
        self.Bind(wx.EVT_TIMER, self.on_live_trace_timer, self.live_trace_timer)
        self.clear_status_button.Bind(wx.EVT_BUTTON, self.on_clear_status)
        self.cycle_inspector_slider.Bind(wx.EVT_SLIDER, self.on_cycle_inspector_slider)
        self.cycle_inspector_entry.Bind(
            wx.EVT_TEXT_ENTER, self.on_cycle_inspector_entry
        )
        self.cycle_inspector_entry.Bind(
            wx.EVT_KILL_FOCUS, self.on_cycle_inspector_entry
        )
        self.undo_button.Bind(wx.EVT_BUTTON, self.on_undo_cycle)
        self.redo_button.Bind(wx.EVT_BUTTON, self.on_redo_cycle)
        self.reset_view_button.Bind(wx.EVT_BUTTON, self.on_reset_view)
        self.cycle_inspector_button.Bind(wx.EVT_BUTTON, self.on_cycle_inspector_button)

        self.Bind(wx.EVT_MENU, self.on_run_cycles_button, id=ID_RUN)
        self.Bind(wx.EVT_MENU, self.on_run_one_cycle, id=ID_RUN_ONE)
        self.Bind(wx.EVT_MENU, self.on_toggle_live_trace, id=ID_TOGGLE_LIVE_TRACE)
        self.Bind(wx.EVT_MENU, self.on_undo_cycle, id=ID_UNDO_CYCLE)
        self.Bind(wx.EVT_MENU, self.on_redo_cycle, id=ID_REDO_CYCLE)
        self.Bind(wx.EVT_MENU, self.on_undo_last_cycle, id=ID_UNDO_LAST_CYCLE)
        self.Bind(wx.EVT_MENU, self.on_redo_last_cycle, id=ID_REDO_LAST_CYCLE)
        self.Bind(wx.EVT_MENU, self.on_clear_status, id=ID_CLEAR_STATUS)
        self.Bind(wx.EVT_MENU, self.on_reset_view, id=ID_RESET_VIEW)
        self.Bind(
            wx.EVT_MENU,
            self.on_toggle_cycle_inspector,
            id=ID_TOGGLE_CYCLE_INSPECTOR,
        )
        self.Bind(wx.EVT_MENU, self.on_toggle_3d, id=ID_TOGGLE_3D)
        self.Bind(wx.EVT_MENU, self.on_toggle_multisample, id=ID_TOGGLE_MULTISAMPLE)
        self.Bind(wx.EVT_MENU, self.on_export_image, id=ID_EXPORT_IMAGE)
        self.Bind(wx.EVT_MENU, self.on_export_csv, id=ID_EXPORT_CSV)
        self.Bind(wx.EVT_MENU, self.on_zoom_in, id=ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, self.on_zoom_out, id=ID_ZOOM_OUT)
        self.Bind(wx.EVT_MENU, self.on_open_file, id=ID_OPEN_FILE)
        self.Bind(wx.EVT_MENU, self.on_toggle_theme, id=ID_TOGGLE_THEME)
        self.Bind(wx.EVT_MENU, self.on_toggle_language, id=ID_TOGGLE_LANGUAGE)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_AVAILABLE_SIGNALS)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_SIMULATION)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_SWITCHES)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_CONSOLE)

        # Keyboard shortcuts
        accelerators = wx.AcceleratorTable(
            [
                (wx.ACCEL_NORMAL, wx.WXK_SPACE, ID_RUN),
                (wx.ACCEL_NORMAL, wx.WXK_LEFT, ID_UNDO_LAST_CYCLE),
                (wx.ACCEL_NORMAL, wx.WXK_RIGHT, ID_REDO_LAST_CYCLE),
                (wx.ACCEL_CTRL, wx.WXK_SPACE, ID_TOGGLE_LIVE_TRACE),
                (wx.ACCEL_CTRL, ord("Z"), ID_UNDO_CYCLE),
                (wx.ACCEL_CTRL, ord("Y"), ID_REDO_CYCLE),
                (wx.ACCEL_CTRL, ord("O"), ID_OPEN_FILE),
                (wx.ACCEL_CTRL, ord("="), ID_ZOOM_IN),
                (wx.ACCEL_CTRL, ord("-"), ID_ZOOM_OUT),
                (wx.ACCEL_NORMAL, ord("R"), ID_RESET_VIEW),
                (wx.ACCEL_CTRL, ord("I"), ID_TOGGLE_CYCLE_INSPECTOR),
                (wx.ACCEL_CTRL, ord("D"), ID_TOGGLE_3D),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("P"), ID_EXPORT_IMAGE),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("E"), ID_EXPORT_CSV),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("T"), ID_TOGGLE_THEME),
                (wx.ACCEL_CTRL, ord("1"), ID_SHOW_AVAILABLE_SIGNALS),
                (wx.ACCEL_CTRL, ord("2"), ID_SHOW_SIMULATION),
                (wx.ACCEL_CTRL, ord("3"), ID_SHOW_SWITCHES),
                (wx.ACCEL_CTRL, ord("4"), ID_SHOW_CONSOLE),
                (wx.ACCEL_NORMAL, wx.WXK_F1, ID_HELP),
                (wx.ACCEL_CTRL, ord("Q"), wx.ID_EXIT),
                (wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_CLEAR_STATUS),
            ]
        )
        self.SetAcceleratorTable(accelerators)

        # Configure sizers
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        canvas_sizer = wx.BoxSizer(wx.VERTICAL)
        side_sizer = wx.BoxSizer(wx.VERTICAL)
        history_theme_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.section_panels = {}
        self.section_titles = {}
        self.section_close_buttons = {}
        self.section_header_sizers = {}
        self.section_visible = {}
        self.side_splitter_windows = {}
        self.side_splitter = wx.SplitterWindow(
            self, style=wx.SP_LIVE_UPDATE | wx.SP_NOBORDER
        )
        self.side_splitter.SetMinimumPaneSize(120)

        simulation_panel, simulation_sizer = self.create_section_panel(
            _("Simulation"), "simulation"
        )
        simulation_holder = wx.Panel(self.side_splitter, wx.ID_ANY)
        simulation_holder.SetBackgroundColour(self.theme["frame_bg"])
        simulation_holder_sizer = wx.BoxSizer(wx.VERTICAL)
        simulation_panel.Reparent(simulation_holder)
        simulation_holder_sizer.Add(simulation_panel, 1, wx.EXPAND | wx.BOTTOM, 4)
        simulation_holder.SetSizer(simulation_holder_sizer)
        self.side_splitter_windows["simulation"] = simulation_holder
        simulation_panel.SetMinSize((SIMULATION_PANEL_WIDTH, SIMULATION_PANEL_HEIGHT))
        simulation_holder.SetMinSize((SIMULATION_PANEL_WIDTH, SIMULATION_PANEL_HEIGHT))

        self.spin = wx.SpinCtrl(simulation_panel, wx.ID_ANY, "10")
        self.spin.SetRange(1, MAX_RUN_CYCLES)
        self.spin.SetMinSize((CYCLE_SPIN_WIDTH, -1))
        self.spin.Bind(wx.EVT_TEXT, self.on_cycle_spin_text)
        self.cycles_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cycles_to_run_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cycles_completed_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text.Reparent(simulation_panel)
        self.cycles_completed_text.Reparent(simulation_panel)
        self.run_cycles_button.Reparent(simulation_panel)
        self.live_trace_button.Reparent(simulation_panel)
        self.live_trace_speed_button.Reparent(simulation_panel)
        self.reset_button.Reparent(simulation_panel)
        self.clear_traces_button.Reparent(simulation_panel)
        self.set_simulation_label_order()
        self.set_simulation_control_order()
        simulation_sizer.Add(
            self.cycles_to_run_sizer,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            6,
        )
        simulation_sizer.Add(self.cycles_input_sizer, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(
            self.cycles_completed_sizer,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            6,
        )
        simulation_sizer.Add(self.run_cycles_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.reset_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.clear_traces_button, 0, wx.EXPAND | wx.ALL, 6)

        switch_panel, switch_sizer = self.create_section_panel(
            _("Switches"), "switches"
        )
        switch_holder = wx.Panel(self.side_splitter, wx.ID_ANY)
        switch_holder.SetBackgroundColour(self.theme["frame_bg"])
        switch_holder_sizer = wx.BoxSizer(wx.VERTICAL)
        switch_panel.Reparent(switch_holder)
        switch_holder_sizer.Add(switch_panel, 1, wx.EXPAND | wx.TOP, 4)
        switch_holder.SetSizer(switch_holder_sizer)
        self.side_splitter_windows["switches"] = switch_holder
        switch_panel.SetMinSize((SIDE_PANEL_WIDTH, 230))
        switch_holder.SetMinSize((SIDE_PANEL_WIDTH, 230))
        self.switch_rows.Reparent(switch_panel)
        switch_sizer.Add(self.switch_rows, 1, wx.EXPAND | wx.ALL, 6)

        self.side_splitter.SplitHorizontally(
            simulation_holder, switch_holder, sashPosition=250
        )
        self.side_splitter.SetMinimumPaneSize(SIMULATION_PANEL_HEIGHT)
        self.side_splitter.SetSashGravity(0.0)
        self.apply_splitter_style()

        signal_panel, signal_sizer = self.create_section_panel(
            _("Available signals"), "available_signals"
        )
        self.module_signal_rows.Reparent(signal_panel)
        signal_sizer.Add(self.module_signal_rows, 1, wx.EXPAND | wx.ALL, 6)

        console_panel, console_sizer = self.create_section_panel(
            _("Console"), "console"
        )
        self.console_box.Reparent(console_panel)
        console_sizer.Add(self.console_box, 1, wx.EXPAND | wx.ALL, 6)

        self.inspector_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cycle_inspector_slider.SetMinSize((120, -1))
        self.set_cycle_inspector_order()
        self.cycle_inspector_panel.SetSizer(self.inspector_sizer)

        # Add both canvases to the layout
        canvas_sizer.Add(self.canvas_2d, 1, wx.EXPAND)
        canvas_sizer.Add(self.canvas_3d, 1, wx.EXPAND)
        canvas_sizer.Add(
            self.cycle_inspector_panel,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            5,
        )

        self.undo_button.Reparent(self)
        self.redo_button.Reparent(self)
        self.reset_view_button.Reparent(self)
        self.cycle_inspector_button.Reparent(self)
        history_theme_sizer.Add(
            self.undo_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        history_theme_sizer.Add(
            self.redo_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        history_theme_sizer.Add(
            self.reset_view_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        history_theme_sizer.Add(
            self.cycle_inspector_button,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            8,
        )
        history_theme_sizer.AddStretchSpacer()
        side_sizer.Add(history_theme_sizer, 0, wx.EXPAND | wx.BOTTOM, 8)

        # Add the single splitter to the side sizer instead of the two panels
        side_sizer.Add(self.side_splitter, 1, wx.EXPAND | wx.BOTTOM, 8)

        main_sizer.Add(signal_panel, 0, wx.EXPAND | wx.ALL, 8)
        main_sizer.Add(canvas_sizer, 4, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(side_sizer, 0, wx.EXPAND | wx.ALL, 8)

        root_sizer.Add(main_sizer, 1, wx.EXPAND)
        root_sizer.Add(console_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(root_sizer)
        self.update_layout_direction()
        self.SetMinSize((MIN_FRAME_WIDTH, MIN_FRAME_HEIGHT))
        self.update_switch_rows()
        self.update_module_signal_rows()
        self.apply_theme()
        self.update_file_dependent_controls()
        self.update_section_window_menu()

        minimum_width = MIN_FRAME_WIDTH
        minimum_height = MIN_FRAME_HEIGHT

        current_size = self.GetSize()
        if current_size.width < minimum_width or current_size.height < minimum_height:
            self.SetSize((minimum_width, minimum_height))

        self.Centre()

    # MENU AND SIMULATION EVENT HANDLERS

    def on_menu(self, event: wx.CommandEvent) -> None:
        """Handle menu items that do not need their own event ID binding."""
        Id = event.GetId()
        if Id == wx.ID_EXIT:
            self.Close(True)
        if Id == wx.ID_ABOUT:
            wx.MessageBox(
                _(
                    "Logic Simulator\n\n"
                    "A graphical logic circuit simulator for the GF2 Software "
                    "project.\n\n"
                    "Use it to load circuit definition files, run simulations "
                    "cycle by cycle, toggle switch inputs, monitor output "
                    "signals, and export waveform traces as PNG or CSV "
                    "files.\n\n"
                    "Language sample: Arabic"
                ),
                _("About Logsim"),
                wx.ICON_INFORMATION | wx.OK,
            )

    def on_help(self, event: wx.CommandEvent) -> None:
        """Show the quick-start workflow for simulating a circuit."""
        wx.MessageBox(
            _(
                "1. Open a circuit definition file from File > Open.\n"
                "2. Use the Switches panel to set switch inputs LOW or HIGH.\n"
                "3. Add signals from the Available signals panel to display "
                "them.\n"
                "4. Choose the number of cycles to run and click Run cycles.\n"
                "5. Use Play live to advance the trace one cycle at a time.\n"
                "6. Use Clear traces to clear the waveform history without "
                "resetting switches.\n"
                "7. Use Reset simulation to restart the circuit and clear all "
                "traces.\n"
                "8. Export the waveform as PNG or the trace data as CSV from "
                "the Export menu."
            ),
            _("Quick Start"),
            wx.ICON_INFORMATION | wx.OK,
        )

    def on_keyboard_shortcuts_help(self, event: wx.CommandEvent) -> None:
        """Show all keyboard shortcuts registered by the accelerator table."""
        wx.MessageBox(
            _(
                "F1: Quick start help\n"
                "Space: Run the selected number of cycles\n"
                "Left arrow: Undo one cycle\n"
                "Right arrow: Redo one cycle\n"
                "Ctrl+Space: Play or pause live tracing\n"
                "Ctrl+Z: Undo last action\n"
                "Ctrl+Y: Redo last action\n"
                "Ctrl+O: Open a circuit file\n"
                "Ctrl+=: Zoom in\n"
                "Ctrl+-: Zoom out\n"
                "Ctrl+I: Show or hide cycle inspector\n"
                "Ctrl+Shift+P: Export waveform as PNG\n"
                "Ctrl+Shift+E: Export traces as CSV\n"
                "F: Snap the 3D view to the front\n"
                "R: Reset view\n"
                "B: Cycle the 3D trace background display mode\n"
                "Drag: Orbit the 3D view\n"
                "Shift+Drag: Pan the 3D view\n"
                "Scroll: Zoom the 3D view\n"
                "Ctrl+1: Show Available Signals panel\n"
                "Ctrl+2: Show Simulation panel\n"
                "Ctrl+3: Show Switches panel\n"
                "Ctrl+4: Show Console panel\n"
                "Delete: Clear console messages\n"
                "Ctrl+Q: Exit"
            ),
            _("Keyboard Shortcuts"),
            wx.ICON_INFORMATION | wx.OK,
        )

    def on_syntax_help(self, event: wx.CommandEvent) -> None:
        """Show a brief reminder of the circuit definition sections."""
        wx.MessageBox(
            _(
                "Circuit files describe devices, connections, and "
                "monitors.\n\n"
                "Typical sections define:\n"
                "- devices such as switches, gates, clocks, and D-types\n"
                "- connections between device outputs and inputs\n"
                "- monitor signals to record and display\n\n"
                "Signals inside modules are shown with collapsible module "
                "names in the GUI.\n"
                "Use File > Open to load another circuit definition without "
                "restarting."
            ),
            _("Circuit File Syntax"),
            wx.ICON_INFORMATION | wx.OK,
        )

    def on_external_documentation(self, event: wx.CommandEvent) -> None:
        """Open the external project documentation in the default browser."""
        if wx.LaunchDefaultBrowser(EXTERNAL_DOCUMENTATION_URL):
            self.SetStatusText(_("Opened external documentation"))
        else:
            self.show_status(_("Error: could not open external documentation."))

    def run_cycles(self, cycles: int, record_history: bool = True) -> bool:
        """Run the simulator and record monitor outputs.

        Arguments:
        cycles -- number of cycles to execute from the current simulator state

        Return True if all cycles executed successfully, otherwise False.

        Records one undo snapshot for the whole run action, records monitor
        traces, updates cycle counters, and refreshes inspector/history
        controls. If network execution fails, restores the snapshot from before
        the failed run.

        """
        if cycles <= 0:
            self.show_status(_("Error: number of cycles must be positive."))
            return False
        if cycles > MAX_RUN_CYCLES:
            self.show_status(
                tr(
                    "Error: cannot run more than {max_cycles} cycles at once.",
                    max_cycles=MAX_RUN_CYCLES,
                )
            )
            return False

        action_snapshot = self.get_simulation_snapshot()

        # Run one cycle at a time and record the monitored signals
        for cycle_index in range(cycles):
            cycle_snapshot = self.get_simulation_snapshot()
            if not self.network.execute_network():
                self.restore_simulation_snapshot(action_snapshot)
                self.show_status(_("Error: network failed to reach a steady state."))
                return False

            self.monitors.record_signals()
            self.cycle_history.append(cycle_snapshot)
            self.cycles_completed += 1
            self.total_cycles_completed += 1

        self.cycle_redo_history = []
        if record_history:
            self.simulation_history.append(action_snapshot)
            self.redo_history = []
        self.update_cycles_completed_text()
        self.update_history_buttons()
        self.update_cycle_inspector_range()
        return True

    def get_simulation_snapshot(self) -> dict[str, Any]:
        """Return enough simulator state to undo or restore one cycle.

        The snapshot stores device outputs and internal counters, monitor
        traces, cycle counters, and the canvas cycle offset. It deliberately
        copies trace lists so later simulation changes do not mutate the saved
        state.

        """
        # Store plain Python values rather than device objects
        # The simulator objects stay alive
        # The snapshot only needs the mutable fields that can change while the
        # circuit is running
        device_snapshots = []
        for device in self.devices.devices_list:
            device_snapshots.append(
                {
                    "device_id": device.device_id,
                    "outputs": dict(device.outputs),
                    "clock_counter": device.clock_counter,
                    "switch_state": device.switch_state,
                    "dtype_memory": device.dtype_memory,
                }
            )

        monitor_snapshots = []
        for monitor_name, monitor in self.monitors.monitors_dictionary.items():
            # Copy trace lists so future simulation steps cannot mutate the
            # history entry through a shared list reference
            monitor_snapshots.append(
                {
                    "requested_name": monitor_name,
                    "device_id": monitor.device_id,
                    "output_id": monitor.output_id,
                    "trace": list(monitor.trace),
                }
            )

        return {
            "devices": device_snapshots,
            "monitors": monitor_snapshots,
            "cycles_completed": self.cycles_completed,
            "total_cycles_completed": self.total_cycles_completed,
            "cycle_offset": _get_active_canvas(self).cycle_offset,
        }

    def restore_simulation_snapshot(self, simulation_snapshot: dict[str, Any]) -> None:
        """Restore simulator state saved by get_simulation_snapshot.

        Arguments:
        simulation_snapshot -- dictionary returned by get_simulation_snapshot

        Restores device state, monitor traces, cycle counters, and inspector
        range information.

        """
        # Restore devices first, then monitor traces and counters
        # Repainting after this method will then see a consistent simulator
        # state
        for device_snapshot in simulation_snapshot["devices"]:
            device = self.devices.get_device(device_snapshot["device_id"])

            if device is not None:
                device.outputs = dict(device_snapshot["outputs"])
                device.clock_counter = device_snapshot["clock_counter"]
                device.switch_state = device_snapshot["switch_state"]
                device.dtype_memory = device_snapshot["dtype_memory"]

        self.monitors.monitors_dictionary.clear()
        for monitor_snapshot in simulation_snapshot.get("monitors", []):
            error_type = self.monitors.make_monitor(
                monitor_snapshot["device_id"],
                monitor_snapshot["output_id"],
                requested_name=monitor_snapshot["requested_name"],
            )
            if error_type == self.monitors.NO_ERROR:
                monitor = self.monitors.monitors_dictionary[
                    monitor_snapshot["requested_name"]
                ]
                monitor.trace = list(monitor_snapshot["trace"])

        self.cycles_completed = simulation_snapshot["cycles_completed"]
        self.total_cycles_completed = simulation_snapshot["total_cycles_completed"]
        for canvas_name in ("canvas", "canvas_2d", "canvas_3d"):
            if hasattr(self, canvas_name):
                getattr(self, canvas_name).cycle_offset = simulation_snapshot[
                    "cycle_offset"
                ]
        self.update_cycles_completed_text()
        self.update_cycle_inspector_range()

    def record_history_snapshot(self) -> None:
        """Save the current simulator state before a user action changes it."""
        self.simulation_history.append(self.get_simulation_snapshot())
        self.redo_history = []
        self.update_history_buttons()

    def refresh_after_history_restore(self) -> None:
        """Refresh panels that reflect simulator state after undo or redo."""
        self.cycle_history = []
        self.cycle_redo_history = []
        self.refresh_switch_rows()
        self.update_monitor_rows()
        self.update_module_signal_rows()
        self.update_cycle_inspector_range()
        _get_active_canvas(self).render()
        self.update_history_buttons()

    def update_history_buttons(self) -> None:
        """Enable undo and redo when their history stacks have entries."""
        if hasattr(self, "undo_button"):
            self.undo_button.Enable(bool(self.simulation_history))
        if hasattr(self, "redo_button"):
            self.redo_button.Enable(bool(self.redo_history))

    def get_max_trace_length(self) -> int:
        """Return the longest trace length among all selected monitors."""
        max_trace_length = 0
        for monitor in self.monitors.monitors_dictionary.values():
            trace_length = len(monitor.trace)
            if trace_length > max_trace_length:
                max_trace_length = trace_length
        return max_trace_length

    def update_cycle_inspector_range(self) -> None:
        """Synchronise the cycle inspector controls with recorded trace data.

        Disables the slider and entry when no trace data exists. Otherwise
        clamps the selected cycle to the available range and updates the
        displayed cycle number.

        """
        if not hasattr(self, "cycle_inspector_slider"):
            return

        max_trace_length = self.get_max_trace_length()
        if max_trace_length <= 0:
            self.cycle_inspector_slider.SetRange(0, 1)
            self.cycle_inspector_slider.SetValue(0)
            self.cycle_inspector_slider.Enable(False)
            self.cycle_inspector_entry.SetValue("-")
            self.cycle_inspector_entry.Enable(False)
            for canvas_name in ("canvas", "canvas_2d", "canvas_3d"):
                if hasattr(self, canvas_name):
                    getattr(self, canvas_name).cycle_inspector_index = 0
            return

        max_index = max_trace_length - 1
        current_index = _get_active_canvas(self).cycle_inspector_index
        if current_index > max_index:
            current_index = max_index

        if max_trace_length == 1:
            self.cycle_inspector_slider.SetRange(0, 1)
        else:
            self.cycle_inspector_slider.SetRange(1, max_trace_length)

        self.cycle_inspector_slider.SetValue(current_index + 1)
        self.cycle_inspector_slider.Enable(True)
        self.cycle_inspector_entry.Enable(True)
        for canvas_name in ("canvas", "canvas_2d", "canvas_3d"):
            if hasattr(self, canvas_name):
                getattr(self, canvas_name).cycle_inspector_index = current_index
        self.update_cycle_inspector_label()

    def update_cycle_inspector_label(self) -> None:
        """Show the real cycle number selected by the inspector entry."""
        selected_cycle = (
            _get_active_canvas(self).cycle_offset
            + _get_active_canvas(self).cycle_inspector_index
            + 1
        )
        if self.cycle_inspector_entry.GetValue() != str(selected_cycle):
            self.cycle_inspector_entry.SetValue(str(selected_cycle))

    def cycle_number_to_cycle_index(self, cycle_number: int) -> int:
        """Convert a displayed cycle number into a zero-based trace index.

        Arguments:
        cycle_number -- cycle number shown to the user, including any cycle
        offset caused by clearing traces.

        Return the nearest valid trace index for the current monitor data.

        """
        max_trace_length = self.get_max_trace_length()
        if max_trace_length <= 0:
            return 0

        minimum_cycle = _get_active_canvas(self).cycle_offset + 1
        maximum_cycle = _get_active_canvas(self).cycle_offset + max_trace_length
        if cycle_number < minimum_cycle:
            cycle_number = minimum_cycle
        if cycle_number > maximum_cycle:
            cycle_number = maximum_cycle

        return cycle_number - _get_active_canvas(self).cycle_offset - 1

    def set_cycle_inspector_index(self, cycle_index: int) -> None:
        """Select a trace index for inspection and update the controls."""
        max_trace_length = self.get_max_trace_length()
        if max_trace_length <= 0:
            self.update_cycle_inspector_range()
            return

        if cycle_index < 0:
            cycle_index = 0
        if cycle_index >= max_trace_length:
            cycle_index = max_trace_length - 1

        for canvas_name in ("canvas", "canvas_2d", "canvas_3d"):
            if hasattr(self, canvas_name):
                getattr(self, canvas_name).cycle_inspector_index = cycle_index
        self.cycle_inspector_slider.SetValue(cycle_index + 1)
        self.update_cycle_inspector_label()

    def show_status(self, message: str) -> None:
        """Append a message to the console and status bar."""
        self.append_console_text(message)
        self.SetStatusText(message)

    def append_console_text(self, text: str) -> None:
        """Append text to the console without adding a trailing blank line."""
        if not text:
            return

        current_text = self.console_box.GetValue()
        if current_text:
            self.console_box.AppendText("\n")
        if hasattr(self, "set_console_text_direction"):
            self.set_console_text_direction(text)
        self.console_box.AppendText(text)

    def set_console_text_direction(self, text: str) -> None:
        """Set console alignment for Arabic and English lines."""
        if not hasattr(self.console_box, "SetDefaultStyle"):
            return

        text_style = wx.TextAttr(self.theme["status_text"], self.theme["status_bg"])
        if hasattr(text_style, "SetAlignment"):
            has_arabic = any("\u0600" <= character <= "\u06ff" for character in text)
            if has_arabic:
                text_style.SetAlignment(wx.TEXT_ALIGNMENT_RIGHT)
            else:
                text_style.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)
        self.console_box.SetDefaultStyle(text_style)

    def update_cycles_completed_text(self) -> None:
        """Update the cycle counter shown in the Simulation panel."""
        self.cycles_completed_text.SetLabel(
            tr("Cycles passed: {count}", count=self.total_cycles_completed)
        )

    def on_cycle_spin_text(self, event: Any) -> None:
        """Clamp typed cycle counts to the per-run maximum.

        Lets ordinary text editing continue, but clamps values above
        MAX_RUN_CYCLES back to the maximum and shows a warning.

        """
        raw_cycles_text = ""
        if hasattr(event, "GetString"):
            raw_cycles_text = event.GetString()
        if not raw_cycles_text and hasattr(self.spin, "GetTextValue"):
            raw_cycles_text = self.spin.GetTextValue()

        cycles = None
        try:
            if raw_cycles_text:
                cycles = int(raw_cycles_text)
            else:
                cycles = self.spin.GetValue()

        except ValueError:
            if hasattr(event, "Skip"):
                event.Skip()
            return

        if cycles is not None and cycles > MAX_RUN_CYCLES:
            self.spin.SetValue(MAX_RUN_CYCLES)
            if wx.GetApp() is not None:
                wx.CallAfter(self.show_max_run_cycles_popup)
            else:
                self.show_max_run_cycles_popup()

        if hasattr(event, "Skip"):
            event.Skip()

    def show_max_run_cycles_popup(self) -> None:
        """Warn when the cycle spin control exceeds the limit."""
        wx.MessageBox(
            tr(
                "You can run at most {max_cycles} cycles at a time.",
                max_cycles=MAX_RUN_CYCLES,
            ),
            _("Maximum Cycles"),
            wx.ICON_WARNING | wx.OK,
        )

    # ERROR MESSAGE HELPERS

    def monitor_error_message(self, error_type: int) -> str:
        """Translate a monitor error code into a short GUI message.

        Arguments:
        error_type -- error code returned by monitors.Monitors

        Return a lowercase message fragment suitable for embedding inside a
        longer status line.

        """
        # Translate monitor error codes into messages suitable for the GUI
        if error_type == self.monitors.NOT_OUTPUT:
            return _("signal is not an output")

        if error_type == self.monitors.MONITOR_PRESENT:
            return _("signal is already monitored")

        if error_type == self.monitors.DEVICE_ABSENT:
            return _("device does not exist")

        return _("unknown monitor error")

    def show_no_loaded_circuit_error(self) -> None:
        """Show the shared error for actions needing a loaded circuit."""
        self.show_status(_("Error: no circuit loaded. Use File > Open to load one."))

    def update_file_dependent_controls(self) -> None:
        """Enable simulation controls only when there is a circuit to run."""
        circuit_loaded = self.path is not None
        for control_name in [
            "run_cycles_button",
            "live_trace_button",
            "live_trace_speed_button",
            "reset_button",
            "clear_traces_button",
        ]:
            if hasattr(self, control_name):
                getattr(self, control_name).Enable(circuit_loaded)

    def on_run_cycles_button(self, event: wx.CommandEvent) -> None:
        """Handle the Run cycles button and menu shortcut."""
        self.stop_live_trace()
        if self.path is None:
            self.show_no_loaded_circuit_error()
            return

        cycles = self.spin.GetValue()

        if not self.network.check_network():
            self.show_status(_("Error: network is incomplete."))
            return

        if self.run_cycles(cycles):
            self.show_status(tr("Ran simulation for {cycles} cycles.", cycles=cycles))
            self.SetStatusText(tr("Ran {cycles} cycles", cycles=cycles))
            _get_active_canvas(self).render()

    def on_run_one_cycle(self, event: wx.CommandEvent) -> None:
        """Run exactly one simulation cycle from the current state."""
        self.stop_live_trace()
        if self.path is None:
            self.show_no_loaded_circuit_error()
            return

        if not self.network.check_network():
            self.show_status(_("Error: network is incomplete."))
            return

        if self.run_cycles(1):
            self.show_status(_("Ran simulation for 1 cycle."))
            self.SetStatusText(_("Ran 1 cycle"))
            _get_active_canvas(self).render()

    def on_toggle_live_trace(self, event: wx.CommandEvent) -> None:
        """Start, pause, or resume live tracing depending on current state."""
        if self.live_trace_running:
            self.stop_live_trace(show_message=True, keep_paused=True)
        elif self.live_trace_paused:
            self.resume_live_trace()
        else:
            self.start_live_trace()

    def start_live_trace(self) -> None:
        """Start automatically advancing the simulation one cycle at a time.

        Return True if live tracing started, otherwise False.

        Validates the circuit, stores the requested cycle budget, starts the wx
        timer, updates the play/pause button, and reports status to the user.

        """
        if self.path is None:
            self.show_no_loaded_circuit_error()
            return False

        if not self.network.check_network():
            self.show_status(_("Error: network is incomplete."))
            return False

        cycles = self.spin.GetValue()
        if cycles <= 0:
            self.show_status(_("Error: number of cycles must be positive."))
            return False

        self.record_history_snapshot()
        self.live_trace_target_cycles = cycles
        self.live_trace_cycles_completed = 0
        self.live_trace_paused = False
        self.live_trace_running = True
        self.live_trace_timer.Start(self.get_live_trace_interval_ms())
        self.update_live_trace_button()
        self.show_status(tr("Started live tracing for {cycles} cycles.", cycles=cycles))
        self.update_live_trace_status_text()
        return True

    def resume_live_trace(self) -> None:
        """Resume a paused live trace without resetting its cycle budget.

        Return True if tracing resumed or restarted otherwise False.

        Keeps the original target cycle count and continues from the number of
        live cycles already completed.

        """
        if self.path is None:
            self.show_no_loaded_circuit_error()
            return False

        if not self.network.check_network():
            self.show_status(_("Error: network is incomplete."))
            return False

        remaining_cycles = (
            self.live_trace_target_cycles - self.live_trace_cycles_completed
        )
        if remaining_cycles <= 0:
            self.live_trace_paused = False
            return self.start_live_trace()

        self.live_trace_paused = False
        self.live_trace_running = True
        self.live_trace_timer.Start(self.get_live_trace_interval_ms())
        self.update_live_trace_button()
        self.show_status(
            tr(
                "Resumed live tracing with {remaining} cycles remaining.",
                remaining=remaining_cycles,
            )
        )
        self.update_live_trace_status_text()
        return True

    def stop_live_trace(
        self, show_message: bool = False, keep_paused: bool = False
    ) -> None:
        """Stop the live tracing timer.

        Optional arguments:
        show_message -- if True, tell the user live tracing was paused
        keep_paused -- if True, remember that the next toggle should resume
        rather than start a fresh live trace

        """
        if not getattr(self, "live_trace_running", False):
            if not keep_paused:
                self.live_trace_paused = False
            return

        self.live_trace_running = False
        self.live_trace_paused = keep_paused
        if hasattr(self, "live_trace_timer") and self.live_trace_timer.IsRunning():
            self.live_trace_timer.Stop()
        self.update_live_trace_button()
        if show_message:
            self.show_status(_("Paused live tracing."))
            self.SetStatusText(_("Live tracing paused"))

    def update_live_trace_button(self) -> None:
        """Keep the live tracing button in sync with playback."""
        if not hasattr(self, "live_trace_button"):
            return

        if self.live_trace_running:
            self.live_trace_button.SetLabel(_("Pause live"))
        else:
            self.live_trace_button.SetLabel(_("Play live"))
        if hasattr(self, "apply_live_trace_button_theme"):
            self.apply_live_trace_button_theme()

    def get_live_trace_interval_ms(self) -> int:
        """Return the wx timer interval for the selected live tracing speed."""
        speed_multiplier = LIVE_TRACE_SPEEDS[self.live_trace_speed_index][1]
        return int(LIVE_TRACE_INTERVAL_MS / speed_multiplier)

    def on_live_trace_speed_button(self, event: wx.CommandEvent) -> None:
        """Cycle to the next live tracing speed."""
        self.live_trace_speed_index = (self.live_trace_speed_index + 1) % len(
            LIVE_TRACE_SPEEDS
        )
        self.update_live_trace_speed_button()

        if self.live_trace_running and self.live_trace_timer.IsRunning():
            self.live_trace_timer.Start(self.get_live_trace_interval_ms())

    def update_live_trace_speed_button(self) -> None:
        """Update the live tracing speed button label, tooltip, and theme."""
        if not hasattr(self, "live_trace_speed_button"):
            return

        speed_label = LIVE_TRACE_SPEEDS[self.live_trace_speed_index][0]
        self.live_trace_speed_button.SetLabel(speed_label)
        self.live_trace_speed_button.SetToolTip(
            tr("Live tracing speed: {speed}", speed=speed_label)
        )

        if hasattr(self, "apply_live_trace_speed_button_theme"):
            self.apply_live_trace_speed_button_theme()

    def update_live_trace_status_text(self) -> None:
        """Refresh the status bar text shown during live tracing."""
        if self.live_trace_running:
            self.SetStatusText(
                tr(
                    "Live tracing: {done}/{target} cycles",
                    done=self.live_trace_cycles_completed,
                    target=self.live_trace_target_cycles,
                )
            )
        elif self.live_trace_paused:
            self.SetStatusText(_("Live tracing paused"))

    def on_live_trace_timer(self, event: wx.TimerEvent) -> None:
        """Advance live tracing by one cycle when the wx timer fires."""
        if not self.network.check_network():
            self.stop_live_trace()
            self.show_status(_("Error: network is incomplete."))
            return

        if not self.run_cycles(1, record_history=False):
            self.stop_live_trace()
            self.SetStatusText(_("Live tracing stopped"))
            return

        self.live_trace_cycles_completed += 1
        self.update_live_trace_status_text()
        if hasattr(_get_active_canvas(self), "follow_latest_cycle"):
            _get_active_canvas(self).follow_latest_cycle()
        _get_active_canvas(self).render()

        if self.live_trace_cycles_completed >= self.live_trace_target_cycles:
            completed_cycles = self.live_trace_cycles_completed
            self.stop_live_trace()
            self.live_trace_paused = False
            message = tr(
                "Completed live tracing for {cycles} cycles.",
                cycles=completed_cycles,
            )
            self.show_status(message)
            self.SetStatusText(message)

    def on_undo_cycle(self, event: wx.CommandEvent) -> None:
        """Restore the simulator state from before the most recent action."""
        self.stop_live_trace()
        if not self.simulation_history:
            self.show_status(_("Error: no action to undo."))
            return

        self.redo_history.append(self.get_simulation_snapshot())
        simulation_snapshot = self.simulation_history.pop()
        self.restore_simulation_snapshot(simulation_snapshot)
        self.refresh_after_history_restore()
        self.show_status(_("Undid last action."))

    def on_redo_cycle(self, event: wx.CommandEvent) -> None:
        """Restore the simulator state from before the most recent undo."""
        self.stop_live_trace()
        if not self.redo_history:
            self.show_status(_("Error: no action to redo."))
            return

        self.simulation_history.append(self.get_simulation_snapshot())
        simulation_snapshot = self.redo_history.pop()
        self.restore_simulation_snapshot(simulation_snapshot)
        self.refresh_after_history_restore()
        self.show_status(_("Redid last action."))

    def on_undo_last_cycle(self, event: wx.CommandEvent) -> None:
        """Remove the most recent completed simulation cycle."""
        self.stop_live_trace()
        if not getattr(self, "cycle_history", []):
            self.show_status(_("Error: no simulation cycle to undo."))
            return

        self.cycle_redo_history.append(self.get_simulation_snapshot())
        simulation_snapshot = self.cycle_history.pop()
        self.restore_simulation_snapshot(simulation_snapshot)
        self.refresh_switch_rows()
        _get_active_canvas(self).render()
        self.show_status(_("Undid 1 cycle."))

    def on_redo_last_cycle(self, event: wx.CommandEvent) -> None:
        """Restore the most recently removed simulation cycle."""
        self.stop_live_trace()
        if not getattr(self, "cycle_redo_history", []):
            self.show_status(_("Error: no simulation cycle to redo."))
            return

        self.cycle_history.append(self.get_simulation_snapshot())
        simulation_snapshot = self.cycle_redo_history.pop()
        self.restore_simulation_snapshot(simulation_snapshot)
        self.refresh_switch_rows()
        _get_active_canvas(self).render()
        self.show_status(_("Redid 1 cycle."))

    def on_toggle_3d(self, event: wx.CommandEvent) -> None:
        """Switch between 2D and 3D canvas modes seamlessly."""
        is_3d = self.view_3d_menu_item.IsChecked()

        if is_3d:
            self.canvas_2d.Hide()
            self.canvas_3d.Show()
            self.show_status(_("Switched to 3D view"))
        else:
            self.canvas_3d.Hide()
            self.canvas_2d.Show()
            self.show_status(_("Switched to 2D trace view"))

        self.Layout()
        self.Refresh()

    def on_toggle_multisample(self, event: wx.CommandEvent) -> None:
        """Toggle multisample antialiasing for the 3D canvas."""
        if not hasattr(self, "canvas_3d"):
            return

        new_state = not self.canvas_3d.multisample_enabled
        self.canvas_3d.set_multisample(new_state)
        self.view_aa_menu_item.Check(new_state)
        if new_state:
            self.show_status(_("3D antialiasing enabled"))
        else:
            self.show_status(_("3D antialiasing disabled"))
        if self.view_3d_menu_item.IsChecked():
            _get_active_canvas(self).render()

    def on_reset_button(self, event: wx.CommandEvent) -> None:
        """Cold-start the circuit and clear all recorded trace history."""
        self.stop_live_trace()
        if self.path is None:
            self.show_no_loaded_circuit_error()
            return

        action_snapshot = self.get_simulation_snapshot()
        self.devices.cold_startup()
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        self.total_cycles_completed = 0
        for canvas_name in ("canvas", "canvas_2d", "canvas_3d"):
            if hasattr(self, canvas_name):
                getattr(self, canvas_name).cycle_offset = 0
        self.cycle_history = []
        self.cycle_redo_history = []
        self.update_cycles_completed_text()

        if hasattr(_get_active_canvas(self), "reset_view"):
            _get_active_canvas(self).reset_view()
        elif hasattr(_get_active_canvas(self), "snap_reset_view"):
            _get_active_canvas(self).snap_reset_view()

        self.update_cycle_inspector_range()
        _get_active_canvas(self).render()
        self.simulation_history.append(action_snapshot)
        self.redo_history = []
        self.update_history_buttons()
        self.show_status(_("Reset simulation."))

    def on_clear_traces(self, event: wx.CommandEvent) -> None:
        """Clear waveform history without resetting switch/device state.

        Keeps selected monitors, preserves the total cycle count for future CSV
        and axis labels, records the action for undo, and returns the waveform
        view to its default pan/zoom.

        """
        self.stop_live_trace()
        if self.path is None:
            self.show_no_loaded_circuit_error()
            return

        action_snapshot = self.get_simulation_snapshot()
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        for canvas_name in ("canvas", "canvas_2d", "canvas_3d"):
            if hasattr(self, canvas_name):
                getattr(self, canvas_name).cycle_offset = self.total_cycles_completed
        self.cycle_history = []
        self.cycle_redo_history = []
        self.update_cycles_completed_text()

        if hasattr(_get_active_canvas(self), "reset_view"):
            _get_active_canvas(self).reset_view()
        elif hasattr(_get_active_canvas(self), "snap_reset_view"):
            _get_active_canvas(self).snap_reset_view()

        self.update_cycle_inspector_range()
        _get_active_canvas(self).render()
        self.simulation_history.append(action_snapshot)
        self.redo_history = []
        self.update_history_buttons()
        self.show_status(_("Cleared traces."))

    def on_clear_status(self, event: wx.CommandEvent) -> None:
        """Clear the GUI console and return the status bar to Ready."""
        self.console_box.SetValue("")
        self.SetStatusText(_("Ready"))

    def on_zoom_in(self, event: wx.CommandEvent) -> None:
        """Zoom into the waveform display from the View menu or shortcut."""
        if hasattr(_get_active_canvas(self), "zoom_at_canvas_centre"):
            _get_active_canvas(self).zoom_at_canvas_centre(1.25)
        else:
            _get_active_canvas(self).zoom *= 1.25
            _get_active_canvas(self).init = False
            _get_active_canvas(self).Refresh()
        self.SetStatusText(_("Zoomed in"))

    def on_zoom_out(self, event: wx.CommandEvent) -> None:
        """Zoom out of the waveform display from the View menu or shortcut."""
        if hasattr(_get_active_canvas(self), "zoom_at_canvas_centre"):
            _get_active_canvas(self).zoom_at_canvas_centre(0.8)
        else:
            _get_active_canvas(self).zoom *= 0.8
            _get_active_canvas(self).init = False
            _get_active_canvas(self).Refresh()
        self.SetStatusText(_("Zoomed out"))

    def on_reset_view(self, event: wx.CommandEvent) -> None:
        """Reset waveform pan and zoom from the view menu or shortcut."""
        canvas = _get_active_canvas(self)
        if hasattr(canvas, "snap_reset_view"):
            canvas.snap_reset_view()
        else:
            canvas.reset_view()
        self.SetStatusText(_("Reset view"))

    def on_toggle_cycle_inspector(self, event: wx.CommandEvent) -> None:
        """Show or hide the cycle inspector controls and canvas cursor."""
        inspector_is_visible = self.cycle_inspector_menu_item.IsChecked()
        for canvas_name in ("canvas", "canvas_2d", "canvas_3d"):
            if hasattr(self, canvas_name):
                getattr(
                    self, canvas_name
                ).cycle_inspector_enabled = inspector_is_visible

        if inspector_is_visible:
            self.update_cycle_inspector_range()
            self.cycle_inspector_panel.Show()
            self.SetStatusText(_("Shown cycle inspector"))
        else:
            self.cycle_inspector_panel.Hide()
            self.SetStatusText(_("Hidden cycle inspector"))

        self.Layout()
        _get_active_canvas(self).render()

    def on_cycle_inspector_button(self, event):
        """Toggle the cycle inspector from the toolbar button."""
        self.cycle_inspector_menu_item.Check(
            not self.cycle_inspector_menu_item.IsChecked()
        )
        self.on_toggle_cycle_inspector(event)

    def on_cycle_inspector_slider(self, event):
        """Update the inspected cycle when the slider is moved."""
        slider_value = self.cycle_inspector_slider.GetValue()
        if slider_value <= 1:
            cycle_index = 0
        else:
            cycle_index = slider_value - 1
        self.set_cycle_inspector_index(cycle_index)
        _get_active_canvas(self).render()

    def on_cycle_inspector_entry(self, event):
        """Jump to the cycle typed into the cycle inspector entry."""
        try:
            cycle_number = int(self.cycle_inspector_entry.GetValue())
        except ValueError:
            self.update_cycle_inspector_label()
            if hasattr(event, "Skip"):
                event.Skip()
            return

        self.set_cycle_inspector_index(self.cycle_number_to_cycle_index(cycle_number))
        _get_active_canvas(self).render()
        if hasattr(event, "Skip"):
            event.Skip()

    def on_toggle_theme(self, event):
        """Switch between the built-in light and dark colour themes."""
        if self.theme_name == "dark":
            self.theme_name = "light"
        else:
            self.theme_name = "dark"
        self.theme = THEMES[self.theme_name]
        self.apply_theme()
        self.show_status(
            tr("Switched to {theme_name} mode.", theme_name=self.theme_name)
        )

    def get_language_menu_label(self):
        """Return the label for the View menu language toggle."""
        if getattr(self, "language_code", "en") == "ar":
            return _("Switch to English")
        return _("Switch to Arabic")

    def on_toggle_language(self, event):
        """Switch the GUI labels between English and Arabic."""
        if self.language_code == "ar":
            self.language_code = "en"
        else:
            self.language_code = "ar"

        set_gui_language(self.language_code)
        self.refresh_translated_labels()

    def refresh_translated_labels(self):
        """Refresh labels that can change when the GUI language changes."""
        self.SetTitle(
            tr("Logic Simulator - {path}", path=self.path)
            if self.path
            else _("Logic Simulator")
        )
        self.text.SetLabel(_("Cycles to run"))
        self.run_cycles_button.SetLabel(_("Run cycles"))
        self.reset_button.SetLabel(_("Reset simulation"))
        self.reset_view_button.SetLabel(_("Reset view"))
        self.reset_view_button.SetToolTip(_("Reset view"))
        self.cycle_inspector_button.SetToolTip(_("Show cycle inspector"))
        self.clear_traces_button.SetLabel(_("Clear traces"))
        self.clear_status_button.SetLabel(_("Clear console"))
        self.cycle_inspector_label.SetLabel(_("Cycle:"))
        self.update_cycles_completed_text()
        self.update_layout_direction()
        self.align_static_text(self.text)
        self.align_static_text(self.cycles_completed_text)
        self.set_simulation_label_order()
        self.set_simulation_control_order()
        self.set_cycle_inspector_order()

        section_labels = {
            "simulation": _("Simulation"),
            "switches": _("Switches"),
            "available_signals": _("Available signals"),
            "console": _("Console"),
        }
        for section_name, label in section_labels.items():
            if section_name in self.section_titles:
                self.section_titles[section_name].SetLabel(label)
                self.set_section_header_order(
                    section_name,
                    self.section_header_sizers[section_name],
                    self.section_titles[section_name],
                    self.section_close_buttons[section_name],
                )

        self.rebuild_menu_bar()

        self.update_live_trace_button()
        self.update_live_trace_speed_button()
        self.update_live_trace_status_text()
        self.update_switch_rows()
        self.update_module_signal_rows()
        self.update_monitor_rows()
        self.Layout()
        self.Refresh()
        self.Update()

    def rebuild_menu_bar(self):
        """Recreate the menu bar using the current language.

        Changing wx menu labels in place can crash some Windows wxPython
        builds. Rebuilding the menu avoids that and keeps the language switch
        reliable.
        """
        file_menu = wx.Menu()
        export_menu = wx.Menu()
        view_menu = wx.Menu()
        window_menu = wx.Menu()
        help_menu = wx.Menu()
        menu_bar = wx.MenuBar()

        self.file_menu_items = {}
        self.export_menu_items = {}
        self.view_menu_items = {}
        self.help_menu_items = {}

        self.file_menu_items["open"] = file_menu.Append(
            ID_OPEN_FILE, _("&Open...\tCtrl+O")
        )
        file_menu.AppendSeparator()
        self.file_menu_items["exit"] = file_menu.Append(wx.ID_EXIT, _("&Exit\tCtrl+Q"))

        self.view_menu_items["zoom_in"] = view_menu.Append(
            ID_ZOOM_IN, _("Zoom in\tCtrl+=")
        )
        self.view_menu_items["zoom_out"] = view_menu.Append(
            ID_ZOOM_OUT, _("Zoom out\tCtrl+-")
        )
        self.view_menu_items["reset_view"] = view_menu.Append(
            ID_RESET_VIEW, _("Reset view\tR")
        )
        view_menu.AppendSeparator()

        self.cycle_inspector_menu_item = view_menu.AppendCheckItem(
            ID_TOGGLE_CYCLE_INSPECTOR, _("Show cycle inspector")
        )
        self.cycle_inspector_menu_item.Check(self.cycle_inspector_panel.IsShown())
        self.view_3d_menu_item = view_menu.AppendCheckItem(
            ID_TOGGLE_3D, _("Enable 3D view\tCtrl+D")
        )
        self.view_3d_menu_item.Check(self.canvas_3d.IsShown())
        self.view_aa_menu_item = view_menu.AppendCheckItem(
            ID_TOGGLE_MULTISAMPLE, _("Enable 3D anti-aliasing")
        )
        if hasattr(self, "canvas_3d") and hasattr(
            self.canvas_3d, "multisample_enabled"
        ):
            if not self.canvas_3d.multisample_enabled:
                self.view_aa_menu_item.Check(False)
                self.view_aa_menu_item.Enable(False)
            else:
                self.view_aa_menu_item.Check(True)
        else:
            self.view_aa_menu_item.Check(True)

        view_menu.AppendSeparator()

        if self.theme_name == "dark":
            theme_label = _("Switch to light mode\tCtrl+Shift+T")
        else:
            theme_label = _("Switch to dark mode\tCtrl+Shift+T")
        self.theme_menu_item = view_menu.Append(ID_TOGGLE_THEME, theme_label)
        self.language_menu_item = view_menu.Append(
            ID_TOGGLE_LANGUAGE, self.get_language_menu_label()
        )

        self.window_menu_items = {
            "available_signals": window_menu.AppendCheckItem(
                ID_SHOW_AVAILABLE_SIGNALS, _("Show Available Signals\tCtrl+1")
            ),
            "simulation": window_menu.AppendCheckItem(
                ID_SHOW_SIMULATION, _("Show Simulation\tCtrl+2")
            ),
            "switches": window_menu.AppendCheckItem(
                ID_SHOW_SWITCHES, _("Show Switches\tCtrl+3")
            ),
            "console": window_menu.AppendCheckItem(
                ID_SHOW_CONSOLE, _("Show Console\tCtrl+4")
            ),
        }
        self.update_section_window_menu()

        self.export_menu_items["image"] = export_menu.Append(
            ID_EXPORT_IMAGE, _("Export as PNG\tCtrl+Shift+P")
        )
        self.export_menu_items["csv"] = export_menu.Append(
            ID_EXPORT_CSV, _("Export as CSV\tCtrl+Shift+E")
        )

        self.help_menu_items["quick_start"] = help_menu.Append(
            ID_HELP, _("&Quick start\tF1")
        )
        self.help_menu_items["shortcuts"] = help_menu.Append(
            ID_HELP_SHORTCUTS, _("&Keyboard shortcuts")
        )
        self.help_menu_items["syntax"] = help_menu.Append(
            ID_HELP_SYNTAX, _("&Circuit file syntax")
        )
        help_menu.AppendSeparator()
        self.help_menu_items["external_docs"] = help_menu.Append(
            ID_HELP_EXTERNAL_DOCS, _("External &documentation")
        )
        help_menu.AppendSeparator()
        self.help_menu_items["about"] = help_menu.Append(wx.ID_ABOUT, _("&About"))

        self.menu_bar = menu_bar
        self.menu_bar_menus = [
            ("file", file_menu, "&File"),
            ("view", view_menu, "&View"),
            ("window", window_menu, "&Window"),
            ("export", export_menu, "&Export"),
            ("help", help_menu, "&Help"),
        ]
        self.update_menu_bar_order()
        self.SetMenuBar(menu_bar)
        if hasattr(self, "theme"):
            self.menu_bar.SetBackgroundColour(self.theme["frame_bg"])
            self.menu_bar.SetForegroundColour(self.theme["text"])

    def update_menu_bar_order(self):
        """Refresh the translated top menu labels."""
        menu_order = self.menu_bar_menus
        while self.menu_bar.GetMenuCount() > 0:
            self.menu_bar.Remove(0)

        for _menu_name, menu, label in menu_order:
            self.menu_bar.Append(menu, _(label))

    def update_layout_direction(self):
        """Use wx's native layout direction for English or Arabic."""
        if self.language_code == "ar":
            self.SetLayoutDirection(wx.Layout_RightToLeft)
        else:
            self.SetLayoutDirection(wx.Layout_LeftToRight)

    def align_static_text(self, label):
        """Align a simple text label for the current language."""
        style = label.GetWindowStyleFlag()
        style &= ~(wx.ALIGN_LEFT | wx.ALIGN_RIGHT | wx.ALIGN_CENTRE_HORIZONTAL)
        if self.language_code == "ar":
            style |= wx.ALIGN_RIGHT
        else:
            style |= wx.ALIGN_LEFT
        label.SetWindowStyleFlag(style)

    def set_simulation_label_order(self):
        """Place Simulation text labels on the correct side."""
        if not hasattr(self, "cycles_to_run_sizer"):
            return

        label_rows = (
            (self.cycles_to_run_sizer, self.text),
            (self.cycles_completed_sizer, self.cycles_completed_text),
        )
        for row_sizer, label in label_rows:
            row_sizer.Clear(delete_windows=False)
            if self.language_code == "ar":
                row_sizer.AddStretchSpacer(1)
                row_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            else:
                row_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                row_sizer.AddStretchSpacer(1)
            row_sizer.Layout()

    def set_simulation_control_order(self):
        """Place the cycle input and live controls for the current language."""
        if not hasattr(self, "cycles_input_sizer"):
            return

        self.cycles_input_sizer.Clear(delete_windows=False)
        if self.language_code == "ar":
            self.cycles_input_sizer.Add(
                self.live_trace_speed_button,
                0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
                6,
            )
            self.cycles_input_sizer.Add(
                self.live_trace_button,
                0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
                6,
            )
            self.cycles_input_sizer.Add(self.spin, 1, wx.ALIGN_CENTER_VERTICAL)
        else:
            self.cycles_input_sizer.Add(
                self.spin, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6
            )
            self.cycles_input_sizer.Add(
                self.live_trace_button, 0, wx.ALIGN_CENTER_VERTICAL
            )
            self.cycles_input_sizer.Add(
                self.live_trace_speed_button, 0, wx.ALIGN_CENTER_VERTICAL
            )
        self.cycles_input_sizer.Layout()

    def set_cycle_inspector_order(self):
        """Place the cycle inspector controls for the current language."""
        if not hasattr(self, "inspector_sizer"):
            return

        self.inspector_sizer.Clear(delete_windows=False)
        if self.language_code == "ar":
            self.inspector_sizer.Add(
                self.cycle_inspector_slider, 1, wx.EXPAND | wx.LEFT, 8
            )
            self.inspector_sizer.Add(
                self.cycle_inspector_entry,
                0,
                wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.FIXED_MINSIZE,
                4,
            )
            self.inspector_sizer.Add(
                self.cycle_inspector_label, 0, wx.ALIGN_CENTER_VERTICAL
            )
        else:
            self.inspector_sizer.Add(
                self.cycle_inspector_label,
                0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
                4,
            )
            self.inspector_sizer.Add(
                self.cycle_inspector_entry,
                0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT | wx.FIXED_MINSIZE,
                8,
            )
            self.inspector_sizer.Add(self.cycle_inspector_slider, 1, wx.EXPAND)
        self.inspector_sizer.Layout()

    def on_close_section(self, event):
        """Hide the section whose close button was clicked."""
        section_name = event.GetEventObject().GetName()
        panel = self.section_panels[section_name]
        self.section_visible[section_name] = False

        # If the panel is inside the splitter, unsplit it safely
        if section_name in ["simulation", "switches"]:
            self.update_side_splitter_panels()
        else:
            panel.Hide()

        self.update_section_window_menu()
        self.Layout()

    def on_show_section(self, event):
        """Show or hide one section from the Window menu."""
        menu_id = event.GetId()
        if menu_id == ID_SHOW_AVAILABLE_SIGNALS:
            section_name = "available_signals"
        elif menu_id == ID_SHOW_SIMULATION:
            section_name = "simulation"
        elif menu_id == ID_SHOW_SWITCHES:
            section_name = "switches"
        else:
            section_name = "console"

        panel = self.section_panels[section_name]
        is_showing = event.IsChecked()
        self.section_visible[section_name] = is_showing

        # Handle splitter panels
        if section_name in ["simulation", "switches"]:
            self.update_side_splitter_panels()
        # Handle standard panels
        else:
            panel.Show(is_showing)

        self.update_section_window_menu()
        self.Layout()

    def on_open_file(self, event):
        """Ask the user for a circuit file and load it into this window."""
        with wx.FileDialog(
            self,
            _("Open circuit definition"),
            wildcard=_("Circuit files (*.txt)|*.txt|All files (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_CANCEL:
                self.load_network_file(file_dialog.GetPath())

    def on_export_image(self, event):
        """Ask for a PNG path and export the current waveform display."""
        if not self.monitors.monitors_dictionary:
            self.show_status(_("Error: no monitors to export."))
            return

        if not hasattr(_get_active_canvas(self), "save_image"):
            self.show_status(_("Error: Image export is only supported in 2D view."))
            return

        with wx.FileDialog(
            self,
            _("Export waveform image"),
            wildcard=_("PNG image (*.png)|*.png"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_CANCEL:
                file_path = file_dialog.GetPath()
                if not file_path.lower().endswith(".png"):
                    file_path += ".png"

                if _get_active_canvas(self).save_image(file_path):
                    self.show_status(
                        tr(
                            "Exported waveform image to {file_path}.",
                            file_path=file_path,
                        )
                    )
                else:
                    self.show_status(_("Error: could not export waveform image."))

    def on_export_csv(self, event):
        """Ask for a CSV path and export the recorded monitor traces."""
        if not self.monitors.monitors_dictionary:
            self.show_status(_("Error: no monitor traces to export."))
            return

        with wx.FileDialog(
            self,
            _("Export monitor traces"),
            wildcard=_("CSV file (*.csv)|*.csv"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_CANCEL:
                file_path = file_dialog.GetPath()

                if not file_path.lower().endswith(".csv"):
                    file_path += ".csv"

                try:
                    self.export_traces_to_csv(file_path)
                    self.show_status(
                        tr(
                            "Exported monitor traces to {file_path}.",
                            file_path=file_path,
                        )
                    )

                except OSError as error:
                    self.show_status(
                        tr(
                            "Error: could not export CSV: {error}.",
                            error=error,
                        )
                    )

    # GUI HELPER FUNCTIONS

    def create_section_panel(self, title, section_name):
        """Create a titled GUI section with a close button.

        arguments:
        title -- text displayed in the section header
        section_name -- stable key used by the window menu and close handler

        Return the panel and the body sizer where callers should add content.

        """
        panel = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SIMPLE)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        header_panel = wx.Panel(panel, wx.ID_ANY)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        body_sizer = wx.BoxSizer(wx.VERTICAL)

        title_label = wx.StaticText(header_panel, wx.ID_ANY, title)
        close_button = wxbuttons.GenBitmapButton(
            header_panel, wx.ID_ANY, wx.Bitmap(1, 1), size=(30, 26)
        )
        close_button.SetMinSize((30, 26))
        close_button.SetName(section_name)
        close_button.Bind(wx.EVT_BUTTON, self.on_close_section)

        if section_name == "console":
            self.clear_status_button.Reparent(header_panel)
        self.set_section_header_order(
            section_name, header_sizer, title_label, close_button
        )
        header_panel.SetSizer(header_sizer)
        panel_sizer.Add(header_panel, 0, wx.EXPAND)
        panel_sizer.Add(body_sizer, 1, wx.EXPAND)
        panel.SetSizer(panel_sizer)

        self.section_panels[section_name] = panel
        self.section_titles[section_name] = title_label
        self.section_close_buttons[section_name] = close_button
        self.section_header_sizers[section_name] = header_sizer
        self.section_visible[section_name] = True
        self.apply_close_button_theme(close_button)
        return panel, body_sizer

    def set_section_header_order(
        self, section_name, header_sizer, title_label, close_button
    ):
        """Swap section title and close button for Arabic."""
        header_panel = header_sizer.GetContainingWindow()
        if header_panel is not None:
            header_panel.SetLayoutDirection(wx.Layout_LeftToRight)
        header_sizer.Clear(delete_windows=False)
        if self.language_code == "ar":
            header_sizer.Add(close_button, 0, wx.LEFT | wx.TOP, 4)
            if section_name == "console":
                header_sizer.Add(self.clear_status_button, 0, wx.LEFT | wx.TOP, 4)
            header_sizer.AddStretchSpacer()
            header_sizer.Add(title_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        else:
            header_sizer.Add(title_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
            if section_name == "console":
                header_sizer.Add(self.clear_status_button, 0, wx.RIGHT | wx.TOP, 4)
            header_sizer.Add(close_button, 0, wx.RIGHT | wx.TOP, 4)
        header_sizer.Layout()
        if header_panel is not None:
            header_panel.Layout()

    def update_section_window_menu(self):
        """Tick Window menu items to match the current panel visibility."""
        for section_name, menu_item in self.window_menu_items.items():
            menu_item.Check(self.section_visible[section_name])

    def update_side_splitter_panels(self):
        """Show Simulation and Switches using stored visibility."""
        simulation_panel = self.section_panels["simulation"]
        switch_panel = self.section_panels["switches"]
        simulation_window = self.side_splitter_windows["simulation"]
        switch_window = self.side_splitter_windows["switches"]
        show_simulation = self.section_visible["simulation"]
        show_switches = self.section_visible["switches"]

        # wx SplitterWindow is easiest to keep correct by returning to an
        # unsplit state first, then rebuilding the one-panel or two-panel view
        # from the stored visibility flags
        if self.side_splitter.IsSplit():
            self.side_splitter.Unsplit()

        simulation_panel.Show(show_simulation)
        switch_panel.Show(show_switches)
        simulation_window.Show(show_simulation)
        switch_window.Show(show_switches)
        self.side_splitter.Show(show_simulation or show_switches)

        if show_simulation and show_switches:
            # When both panels are visible the splitter owns them both
            # Make sure the first window is Simulation before splitting
            # Otherwise wx can keep an old child from a previous hide/show
            # operation
            current_panel = self.side_splitter.GetWindow1()
            if current_panel is not None and current_panel != simulation_window:
                self.side_splitter.ReplaceWindow(current_panel, simulation_window)
            self.side_splitter.SplitHorizontally(
                simulation_window, switch_window, sashPosition=250
            )
        elif show_simulation or show_switches:
            # With only one panel visible the splitter behaves like a
            # container; replace its single child if the user toggled between
            # Simulation and Switches
            visible_panel = simulation_window if show_simulation else switch_window
            current_panel = self.side_splitter.GetWindow1()
            if current_panel is None:
                self.side_splitter.Initialize(visible_panel)
            elif current_panel != visible_panel:
                self.side_splitter.ReplaceWindow(current_panel, visible_panel)

        self.apply_splitter_style()

    def apply_splitter_style(self):
        """Keep the simulation/switch splitter divider visually quiet."""
        self.side_splitter.SetBackgroundColour(self.theme["frame_bg"])
        for splitter_window in self.side_splitter_windows.values():
            splitter_window.SetBackgroundColour(self.theme["frame_bg"])
        if hasattr(self.side_splitter, "SetSashInvisible"):
            self.side_splitter.SetSashInvisible(True)

    def get_system_theme_name(self):
        """Return OS light/dark appearance, with a brightness fallback."""
        if hasattr(wx.SystemSettings, "GetAppearance"):
            appearance = wx.SystemSettings.GetAppearance()
            if appearance.IsDark():
                return "dark"

        colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)

        # this is a fallback for if wx.SystemSettings.GetAppearance() is unavailable
        # add the RGB values of the window background
        # Values below middle grey probably mean dark mode
        brightness = colour.Red() + colour.Green() + colour.Blue()

        if brightness < 384:
            return "dark"
        return "light"

    def apply_theme(self):
        """Apply the selected colour theme to the whole window.

        Updates the canvas palette, menu labels, icons, panels, text controls,
        switch rows, monitor rows, and history/live-trace buttons.

        """
        self.theme = THEMES[self.theme_name]

        # Canvases cache colours and OpenGL projection state, so update their
        # palette and mark them for a fresh projection before repainting
        self.canvas_2d.theme = self.theme
        self.canvas_2d.apply_no_monitor_label_theme()
        self.canvas_2d.init = False
        self.canvas_3d.theme = self.theme
        self.canvas_3d.init = False

        if self.theme_name == "dark":
            # Icons are paired with the theme so the toolbar keeps enough
            # contrast on both light and dark backgrounds
            self.theme_menu_item.SetItemLabel(_("Switch to light mode\tCtrl+Shift+T"))
            undo_icon_path = DARK_UNDO_ICON_PATH
            redo_icon_path = DARK_REDO_ICON_PATH
            inspector_icon_path = DARK_INSPECTOR_ICON_PATH
        else:
            self.theme_menu_item.SetItemLabel(_("Switch to dark mode\tCtrl+Shift+T"))
            undo_icon_path = LIGHT_UNDO_ICON_PATH
            redo_icon_path = LIGHT_REDO_ICON_PATH
            inspector_icon_path = LIGHT_INSPECTOR_ICON_PATH

        self.apply_history_button_theme(
            self.undo_button, undo_icon_path, _("Undo last action")
        )
        self.apply_history_button_theme(
            self.redo_button, redo_icon_path, _("Redo last action")
        )
        self.apply_history_button_theme(
            self.reset_view_button,
            None,
            _("Reset view"),
            fallback_label=_("Reset view"),
        )
        self.apply_history_button_theme(
            self.cycle_inspector_button,
            inspector_icon_path,
            _("Show cycle inspector"),
            icon_size=22,
        )
        self.apply_live_trace_button_theme()
        self.apply_live_trace_speed_button_theme()

        self.SetBackgroundColour(self.theme["frame_bg"])
        self.apply_theme_to_text_box(self.console_box)
        self.menu_bar.SetBackgroundColour(self.theme["frame_bg"])
        self.menu_bar.SetForegroundColour(self.theme["text"])

        themed_controls = [
            self.text,
            self.spin,
            self.cycles_completed_text,
            self.run_cycles_button,
            self.reset_button,
            self.clear_traces_button,
            self.clear_status_button,
            self.cycle_inspector_panel,
            self.cycle_inspector_label,
            self.cycle_inspector_entry,
            self.cycle_inspector_slider,
            self.switch_rows,
            self.module_signal_rows,
            self.monitor_rows,
            self.side_splitter,
        ]

        # wx controls do not inherit all colour changes reliably on every
        # platform, so theme each known control explicitly
        for control in themed_controls:
            self.apply_theme_to_control(control)
        self.apply_splitter_style()

        for section_name, panel in self.section_panels.items():
            panel.SetBackgroundColour(self.theme["frame_bg"])
            self.section_titles[section_name].SetForegroundColour(self.theme["text"])
            self.apply_close_button_theme(self.section_close_buttons[section_name])

        # Rebuilding these rows reapplies button colours and icon choices to
        # controls that were created dynamically from the loaded circuit
        self.update_switch_rows()
        self.update_module_signal_rows()
        self.update_monitor_rows()
        self.update_history_buttons()
        self.Layout()
        self.Refresh()
        _get_active_canvas(self).Refresh()

    def apply_theme_to_control(self, control):
        """Apply the current theme to one wx control."""
        if isinstance(control, wx.SpinCtrl):
            control.SetBackgroundColour(self.theme["panel_bg"])
            control.SetForegroundColour(self.theme["text"])
        elif isinstance(control, wx.Button):
            control.SetBackgroundColour(self.theme["button_bg"])
            control.SetForegroundColour(self.theme["text"])
        elif isinstance(control, wx.TextCtrl):
            self.apply_theme_to_text_box(control)
        elif isinstance(control, wx.ScrolledWindow):
            control.SetBackgroundColour(self.theme["panel_bg"])
            control.SetForegroundColour(self.theme["text"])
        else:
            control.SetBackgroundColour(self.theme["frame_bg"])
            control.SetForegroundColour(self.theme["text"])

        control.Refresh()

    def apply_theme_to_text_box(self, text_box):
        """Apply theme colours to existing and future text in a text box."""
        text_box.SetBackgroundColour(self.theme["status_bg"])
        text_box.SetForegroundColour(self.theme["status_text"])
        text_style = wx.TextAttr(self.theme["status_text"], self.theme["status_bg"])
        text_box.SetDefaultStyle(text_style)

        last_position = text_box.GetLastPosition()
        if last_position > 0:
            text_box.SetStyle(0, last_position, text_style)

        text_box.Refresh()
        text_box.Update()

    def load_icon_bitmap(self, icon_path, size):
        """Load and cache a square icon bitmap.

        Arguments:
        icon_path -- path to the image file
        size -- requested width and height in pixels

        Return a wx.Bitmap or None if the icon cannot be loaded.

        """
        if icon_path is None:
            return None

        cache_key = (icon_path, size)
        if not hasattr(self, "icon_bitmap_cache"):
            self.icon_bitmap_cache = {}
        if cache_key in self.icon_bitmap_cache:
            return self.icon_bitmap_cache[cache_key]

        if not os.path.exists(icon_path):
            return None

        image = wx.Image(icon_path, wx.BITMAP_TYPE_ANY)
        if not image.IsOk():
            return None

        image = image.Scale(size, size, wx.IMAGE_QUALITY_HIGH)
        bitmap = wx.Bitmap(image)
        self.icon_bitmap_cache[cache_key] = bitmap
        return bitmap

    def apply_history_button_theme(
        self, button, icon_path, tooltip, fallback_label=None, icon_size=16
    ):
        """Apply the shared compact style to toolbar buttons."""
        button.SetBackgroundColour(self.theme["frame_bg"])
        button.SetForegroundColour(self.theme["text"])
        button.SetToolTip(tooltip)

        if hasattr(button, "SetBezelWidth"):
            button.SetBezelWidth(0)
        if hasattr(button, "SetMargins"):
            button.SetMargins(0, 0)
        if hasattr(button, "SetUseFocusIndicator"):
            button.SetUseFocusIndicator(False)

        bitmap = self.load_icon_bitmap(icon_path, icon_size)
        if bitmap is not None:
            button.SetLabel("")
            button.SetBitmapLabel(bitmap)
        else:
            button.SetLabel(fallback_label or tooltip.split()[0])
            if icon_path is not None and hasattr(button, "SetBitmapLabel"):
                button.SetBitmapLabel(wx.Bitmap(1, 1))

        button.Refresh()

    def apply_live_trace_button_theme(self):
        """Apply the play or pause icon that matches live tracing state."""
        if self.live_trace_running:
            fallback_label = _("Pause")
            tooltip = _("Pause live tracing")
            if self.theme_name == "dark":
                icon_path = DARK_PAUSE_ICON_PATH
            else:
                icon_path = LIGHT_PAUSE_ICON_PATH
        else:
            fallback_label = _("Play")
            tooltip = _("Start live tracing")
            if self.theme_name == "dark":
                icon_path = DARK_PLAY_ICON_PATH
            else:
                icon_path = LIGHT_PLAY_ICON_PATH

        self.live_trace_button.SetToolTip(tooltip)
        self.live_trace_button.SetBackgroundColour(self.theme["frame_bg"])
        self.live_trace_button.SetForegroundColour(self.theme["text"])

        if hasattr(self.live_trace_button, "SetBezelWidth"):
            self.live_trace_button.SetBezelWidth(0)
        if hasattr(self.live_trace_button, "SetMargins"):
            self.live_trace_button.SetMargins(0, 0)
        if hasattr(self.live_trace_button, "SetUseFocusIndicator"):
            self.live_trace_button.SetUseFocusIndicator(False)

        bitmap = self.load_icon_bitmap(icon_path, 18)
        if bitmap is not None:
            self.live_trace_button.SetLabel("")
            self.live_trace_button.SetBitmapLabel(bitmap)
        else:
            self.live_trace_button.SetLabel(fallback_label)
            self.live_trace_button.SetBitmapLabel(wx.Bitmap(1, 1))

        self.live_trace_button.Refresh()

    def apply_live_trace_speed_button_theme(self):
        """Theme the live tracing speed button."""
        if not hasattr(self, "live_trace_speed_button"):
            return

        speed_label = LIVE_TRACE_SPEEDS[self.live_trace_speed_index][0]
        self.live_trace_speed_button.SetLabel(speed_label)
        self.live_trace_speed_button.SetToolTip(
            tr("Live tracing speed: {speed}", speed=speed_label)
        )
        self.live_trace_speed_button.SetBackgroundColour(self.theme["frame_bg"])
        self.live_trace_speed_button.SetForegroundColour(self.theme["text"])

        if hasattr(self.live_trace_speed_button, "SetBezelWidth"):
            self.live_trace_speed_button.SetBezelWidth(0)
        if hasattr(self.live_trace_speed_button, "SetMargins"):
            self.live_trace_speed_button.SetMargins(0, 0)
        if hasattr(self.live_trace_speed_button, "SetUseFocusIndicator"):
            self.live_trace_speed_button.SetUseFocusIndicator(False)

        self.live_trace_speed_button.Refresh()

    def apply_close_button_theme(self, button):
        """Apply the small section-close icon style to a button."""
        button.SetBackgroundColour(self.theme["frame_bg"])
        button.SetForegroundColour(self.theme["text"])

        if hasattr(button, "SetBezelWidth"):
            button.SetBezelWidth(0)
        if hasattr(button, "SetUseFocusIndicator"):
            button.SetUseFocusIndicator(False)

        if self.theme_name == "dark":
            icon_path = DARK_CLOSE_ICON_PATH
        else:
            icon_path = LIGHT_CLOSE_ICON_PATH

        bitmap = self.load_icon_bitmap(icon_path, 14)
        if bitmap is not None:
            button.SetLabel("")
            button.SetBitmapLabel(bitmap)
            button.SetToolTip(_("Close section"))
        else:
            button.SetLabel("X")
            button.SetBitmapLabel(wx.Bitmap(1, 1))

        button.Refresh()
        button.Update()

    def set_collapsible_pane_colours(self, collapsible_pane):
        """Apply theme colours to a wx.CollapsiblePane and its children."""
        collapsible_pane.SetBackgroundColour(self.theme["panel_bg"])

        # wx draws the collapsible header itself
        # On Windows OS at least, the header seems to stay light even in dark
        # mode so here the text is made dark as its is easier to read.
        # Need to test on more platforms to see if this is a general issue with
        # wx or just a quirk of Windows.
        if self.theme_name == "dark" and wx.Platform == "__WXMSW__":
            header_text_colour = wx.Colour(0, 0, 0)
        else:
            header_text_colour = self.theme["text"]

        collapsible_pane.SetForegroundColour(header_text_colour)
        for child in collapsible_pane.GetChildren():
            child.SetForegroundColour(header_text_colour)
            child.Refresh()

        collapsible_pane.Refresh()

    def update_switch_state_buttons(
        self, low_button, high_button, low_label, high_label, switch_value
    ):
        """Colour a switch row so LOW or HIGH appears selected."""
        if switch_value == 1:
            high_button.SetBackgroundColour(self.theme["toggle_on"])
            low_button.SetBackgroundColour(self.theme["toggle_off"])
            high_label.SetForegroundColour(self.theme["text"])
            low_label.SetForegroundColour(self.theme["muted_text"])
        else:
            low_button.SetBackgroundColour(self.theme["toggle_on"])
            high_button.SetBackgroundColour(self.theme["toggle_off"])
            low_label.SetForegroundColour(self.theme["text"])
            high_label.SetForegroundColour(self.theme["muted_text"])

        low_button.SetForegroundColour(self.theme["toggle_text"])
        high_button.SetForegroundColour(self.theme["toggle_text"])
        low_button.Refresh()
        high_button.Refresh()
        low_label.Refresh()
        high_label.Refresh()

    def refresh_switch_rows(self):
        """Refresh switch colours without rebuilding the whole switch panel."""
        refreshed_low_buttons = set()

        for (
            switch_name,
            _,
            low_button,
            high_button,
            low_label,
            high_label,
        ) in self.switch_state_buttons.values():
            if low_button.GetId() in refreshed_low_buttons:
                continue

            switch_id = self.names.query(switch_name)
            device = self.devices.get_device(switch_id)

            if device is not None:
                self.update_switch_state_buttons(
                    low_button,
                    high_button,
                    low_label,
                    high_label,
                    device.switch_state,
                )

            refreshed_low_buttons.add(low_button.GetId())

    def load_network_file(self, path):
        """Parse a circuit file and replace the current simulator state.

        Arguments:
        path -- path to the circuit definition file to load

        Return True if parsing succeeded and the GUI was refreshed, otherwise
        False.

        Creates fresh Names, Devices, Network, and Monitors objects, captures
        parser diagnostics for the console, resets run history, updates every
        circuit-dependent panel, and resets the waveform view.

        """
        self.stop_live_trace()
        names = Names()
        devices = Devices(names)
        network = Network(names, devices)
        monitors = Monitors(names, devices, network)
        parser_output = io.StringIO()

        with (
            contextlib.redirect_stdout(parser_output),
            contextlib.redirect_stderr(parser_output),
        ):
            scanner = Scanner(path, names)
            parser = Parser(names, devices, network, monitors, scanner)
            parsed_ok = parser.parse_network()

        if not parsed_ok:
            message = tr("Could not load circuit file:\n{path}", path=path)
            self.show_status(tr("Error: could not load {path}.", path=path))
            error_text = parser_output.getvalue().strip()
            if error_text:
                self.append_console_text(error_text)
            wx.MessageBox(message, _("Invalid circuit file"), wx.ICON_ERROR | wx.OK)
            return False

        self.path = path
        self.names = names
        self.devices = devices
        self.network = network
        self.monitors = monitors
        self.net_driver_dict = parser.net_driver_dict
        self.cycles_completed = 0
        self.total_cycles_completed = 0
        self.simulation_history = []
        self.redo_history = []
        self.cycle_history = []
        self.cycle_redo_history = []
        self.module_signal_expanded_paths = set()

        self.canvas_2d.devices = devices
        self.canvas_2d.monitors = monitors
        self.canvas_2d.cycle_offset = 0
        self.canvas_2d.reset_view()

        self.canvas_3d.devices = devices
        self.canvas_3d.monitors = monitors
        self.canvas_3d.cycle_offset = 0
        self.canvas_3d.snap_reset_view()

        self.update_cycles_completed_text()
        self.update_module_signal_rows()
        self.update_switch_rows()
        self.update_monitor_rows()
        self.update_file_dependent_controls()
        self.update_history_buttons()
        self.update_cycle_inspector_range()
        self.SetTitle(tr("Logic Simulator - {path}", path=path))
        self.show_status(tr("Loaded {path}.", path=path))
        _get_active_canvas(self).render()
        return True

    def export_traces_to_csv(self, file_path):
        """Write monitor traces to a CSV file.

        Arguments:
        file_path -- destination path for the CSV file

        Writes one row per recorded cycle. The cycle column uses the canvas
        cycle offset so exported traces remain correctly numbered after Clear
        traces.

        """
        monitor_list = list(self.monitors.monitors_dictionary.values())
        max_trace_length = 0

        for monitor in monitor_list:
            if len(monitor.trace) > max_trace_length:
                max_trace_length = len(monitor.trace)

        with open(file_path, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            header_row = ["cycle"]
            for monitor in monitor_list:
                header_row.append(monitor.requested_name)
            writer.writerow(header_row)

            for cycle in range(max_trace_length):
                row = [_get_active_canvas(self).cycle_offset + cycle + 1]
                for monitor in monitor_list:
                    if cycle < len(monitor.trace):
                        row.append(self.signal_to_csv_text(monitor.trace[cycle]))
                    else:
                        row.append("")
                writer.writerow(row)

    def signal_to_csv_text(self, signal):
        """Return the CSV text representation of one simulator signal value."""
        if signal == self.devices.HIGH:
            return "1"
        if signal == self.devices.LOW:
            return "0"
        if signal == self.devices.RISING:
            return "1"
        if signal == self.devices.FALLING:
            return "0"
        if signal == self.devices.BLANK:
            return ""
        return str(signal)

    def get_switch_names(self):
        """Return switch names that should be visible in the GUI.

        Internal parser-created switches whose names begin with @ are
        filtered out because they are implementation details, not user
        controls.

        """
        switch_names = []

        # Do not show internal switches made by the parser
        for device in self.devices.devices_list:
            if device.device_kind == self.devices.SWITCH:
                switch_name = self.names.get_name_string(device.device_id)
                if switch_name.startswith("@"):
                    continue
                switch_names.append(switch_name)

        return switch_names

    def get_signal_ids(self, signal_name):
        """Resolve a GUI signal name into simulator device and output IDs.

        Arguments:
        signal_name -- signal name shown to the user using dot notation for
        output ports

        Return [device_id, port_id] for a valid monitorable output or None
        if the name cannot be resolved.

        """
        # Using query rather than lookup so invalid GUI input does not create
        # names
        name_parts = signal_name.split(".")
        number_of_parts = len(name_parts)

        if number_of_parts < 1 or number_of_parts > 2:
            return None

        device_name = name_parts[0]
        device_id = self.names.query(device_name)
        if device_id is None:
            return None

        port_id = None
        if number_of_parts == 2:
            port_name = name_parts[1]
            port_id = self.names.query(port_name)
            if port_id is None:
                return None

        # Resolve module-port display names back to internal net names.
        # The parser internal net names resolve input and output ports
        # within modules as nets, so TL_CTRL.GREEN port is internally
        # kept as TL_CTRL->GREEN net. In the GUI we want to display
        # TL_CTRL.GREEN, so get_output_signal_names converted everything
        # to the dot form TL_CTRL.GREEN. Now when we are getting the
        # signal IDs, convert back to parser internal net names
        # which are in the net_driver_dict.
        # Example:
        #   TL_CTRL.GREEN       -> TL_CTRL->GREEN
        #   TL_CTRL->TIMER.Q0   -> TL_CTRL->TIMER->Q0
        if port_id is not None:
            internal_net_name = device_name + "->" + port_name
            internal_net_id = self.names.query(internal_net_name)

            if internal_net_id in self.net_driver_dict:
                driver_signal = self.net_driver_dict[internal_net_id]

                if driver_signal.is_literal:
                    const_device_id = self.names.query(
                        "@LITERAL_" + str(driver_signal.literal_value)
                    )
                    if const_device_id is None:
                        return None
                    return [const_device_id, None]

                return [driver_signal.main_id, driver_signal.port_id]

        # Resolve ordinary net names to their driver.
        if port_id is None and device_id in self.net_driver_dict:
            driver_signal = self.net_driver_dict[device_id]
            if driver_signal.is_literal:
                const_device_id = self.names.query(
                    "@LITERAL_" + str(driver_signal.literal_value)
                )
                if const_device_id is None:
                    return None
                return [const_device_id, None]

            return [driver_signal.main_id, driver_signal.port_id]

        return [device_id, port_id]

    def get_output_signal_names(self):
        """Return GUI-facing names for all monitorable output signals.

        Real device outputs keep their device.port form. Module port nets are
        converted from parser arrow notation to a friendlier dotted final port,
        for example 'TL_CTRL->GREEN' becomes 'TL_CTRL.GREEN'.

        """
        signal_names = []

        # Populate the monitor dropdown from real device outputs only
        for device_id in self.devices.find_devices():
            device = self.devices.get_device(device_id)

            for output_id in device.outputs:
                signal_name = self.devices.get_signal_name(
                    device_id,
                    output_id,
                )
                if signal_name is not None:
                    if signal_name.startswith("@"):
                        continue
                    signal_names.append(signal_name)

        for net_id in self.net_driver_dict:
            signal_name = self.names.get_name_string(net_id)
            if signal_name is not None:
                if signal_name.startswith("@"):
                    continue
                # In the GUI,
                # Display module port nets using dot notation:
                #   TL_CTRL->GREEN       becomes TL_CTRL.GREEN
                #   TL_CTRL->TIMER->Q0   becomes TL_CTRL->TIMER.Q0
                #
                # Existing real device outputs already contain dots, e.g.
                #   TL_CTRL->TIMER->R0.Q
                # so leave those unchanged.
                if "->" in signal_name and "." not in signal_name:
                    instance_name, port_name = signal_name.rsplit("->", 1)
                    signal_name = instance_name + "." + port_name

                signal_names.append(signal_name)

        return signal_names

    def get_module_signal_groups(self):
        """Return module output signals grouped into a nested display tree."""
        module_signal_groups = {}

        # The parser names internal module signals with ->
        # The GUI keeps that as the internal name but presents it as collapsed
        # module panes so the user doesn't read long arrow separated strings
        for signal_name in self.get_output_signal_names():
            if "->" not in signal_name:
                continue

            _add_signal_to_module_tree(module_signal_groups, signal_name, signal_name)

        return module_signal_groups

    def get_top_level_signal_names(self):
        """Return monitorable outputs that are not inside a module path."""
        signal_names = []

        for signal_name in self.get_output_signal_names():
            if "->" not in signal_name:
                signal_names.append(signal_name)

        return signal_names

    def update_switch_rows(self):
        """Rebuild the switch panel from the current circuit."""
        # Clear the old rows and rebuild them
        self.switch_rows_sizer.Clear(delete_windows=True)
        self.switch_state_buttons = {}

        switch_names = self.get_switch_names()
        if not switch_names:
            empty_label = wx.StaticText(self.switch_rows, wx.ID_ANY, _("No switches"))
            self.align_static_text(empty_label)
            empty_label.SetForegroundColour(self.theme["muted_text"])
            self.switch_rows_sizer.Add(empty_label, 0, wx.EXPAND | wx.ALL, 6)
        else:
            for switch_name in switch_names:
                self.add_switch_row(switch_name)

        self.switch_rows.Layout()
        self.switch_rows.FitInside()

    def add_switch_row(self, switch_name):
        """Add one switch row with LOW/HIGH state buttons.

        Arguments:
        switch_name -- visible switch device name from get_switch_names

        Stores both button IDs in switch_state_buttons so either button can be
        mapped back to the same switch row.

        """
        switch_id = self.names.query(switch_name)
        device = self.devices.get_device(switch_id)

        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(
            self.switch_rows, wx.ID_ANY, switch_name, style=wx.ST_ELLIPSIZE_END
        )
        self.align_static_text(label)
        label.SetMinSize((0, -1))
        label.SetToolTip(switch_name)
        low_label = wx.StaticText(self.switch_rows, wx.ID_ANY, _("LOW"))
        low_button = wx.Button(self.switch_rows, wx.ID_ANY, "")
        high_button = wx.Button(self.switch_rows, wx.ID_ANY, "")
        high_label = wx.StaticText(self.switch_rows, wx.ID_ANY, _("HIGH"))

        low_button.SetMinSize((22, 18))
        high_button.SetMinSize((22, 18))
        low_button.Bind(wx.EVT_BUTTON, self.on_switch_state_button)
        high_button.Bind(wx.EVT_BUTTON, self.on_switch_state_button)

        self.switch_state_buttons[low_button.GetId()] = (
            switch_name,
            0,
            low_button,
            high_button,
            low_label,
            high_label,
        )
        self.switch_state_buttons[high_button.GetId()] = (
            switch_name,
            1,
            low_button,
            high_button,
            low_label,
            high_label,
        )

        label.SetForegroundColour(self.theme["text"])
        label_font = label.GetFont()
        label_font.SetWeight(wx.FONTWEIGHT_BOLD)
        label.SetFont(label_font)
        self.update_switch_state_buttons(
            low_button, high_button, low_label, high_label, device.switch_state
        )

        if self.language_code == "ar":
            row_sizer.Add(high_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
            row_sizer.Add(high_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
            row_sizer.Add(low_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
            row_sizer.Add(low_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
            row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL)
        else:
            row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
            row_sizer.Add(low_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
            row_sizer.Add(low_button, 0, wx.ALIGN_CENTER_VERTICAL)
            row_sizer.Add(high_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
            row_sizer.Add(high_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self.switch_rows_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

    def update_module_signal_rows(self):
        """Rebuild the available signal list while preserving pane position.

        Saves expanded module panes, rebuilds top-level and nested module
        signal rows, restores scroll position, refreshes the scrolled area,

        """
        # The list is rebuilt when the available signals really change
        # Save open/closed pane state first so user navigation is not lost
        self.store_module_signal_pane_state()
        scroll_x, scroll_y = self.module_signal_rows.GetViewStart()
        self.module_signal_button_names = {}
        self.module_signal_action_buttons = {}
        self.module_signal_pane_paths = {}
        self.module_signal_rows_sizer.Clear(delete_windows=True)

        top_level_signal_names = self.get_top_level_signal_names()
        module_signal_groups = self.get_module_signal_groups()

        if not top_level_signal_names and not module_signal_groups:
            empty_label = wx.StaticText(
                self.module_signal_rows, wx.ID_ANY, _("No monitorable signals")
            )
            self.align_static_text(empty_label)
            empty_label.SetForegroundColour(self.theme["muted_text"])
            self.module_signal_rows_sizer.Add(empty_label, 0, wx.EXPAND | wx.ALL, 6)
        else:
            for signal_name in sorted(top_level_signal_names):
                self.add_available_signal_row(
                    self.module_signal_rows,
                    self.module_signal_rows_sizer,
                    signal_name,
                    signal_name,
                    indent=0,
                )

            if top_level_signal_names and module_signal_groups:
                self.module_signal_rows_sizer.AddSpacer(10)

            self.add_module_signal_group_rows(
                self.module_signal_rows,
                self.module_signal_rows_sizer,
                module_signal_groups,
                (),
            )

        self.module_signal_rows.Layout()
        self.module_signal_rows.FitInside()
        self.module_signal_rows.Scroll(scroll_x, scroll_y)

    def add_module_signal_group_rows(
        self, parent, parent_sizer, signal_group, parent_path
    ):
        """Add nested module panes and their signal rows to a sizer.

        Arguments:
        parent -- wx parent for rows and panes at this level
        parent_sizer -- sizer receiving the rows for this level
        signal_group -- nested signal tree for this module level
        parent_path -- tuple naming the current module path

        Builds collapsible panes recursively and records pane IDs so expansion
        state can survive later rebuilds.

        """
        for signal_name, full_signal_name in sorted(
            signal_group.get("signals_at_this_level", [])
        ):
            self.add_available_signal_row(
                parent,
                parent_sizer,
                signal_name,
                full_signal_name,
                indent=MODULE_SIGNAL_INDENT_WIDTH,
            )

        for module_name in sorted(signal_group):
            if module_name == "signals_at_this_level":
                continue
            pane_label = tr("{module_name} internals", module_name=module_name)
            pane_parent = parent
            if self.language_code == "ar":
                pane_parent = wx.Panel(parent, wx.ID_ANY)
                pane_parent.SetBackgroundColour(self.theme["panel_bg"])
                pane_parent.SetLayoutDirection(wx.Layout_LeftToRight)

            collapsible_pane = wx.CollapsiblePane(
                pane_parent,
                wx.ID_ANY,
                pane_label,
                style=COLLAPSIBLE_PANE_STYLE,
            )
            if self.language_code == "ar":
                collapsible_pane.SetLayoutDirection(wx.Layout_RightToLeft)
            pane_font = collapsible_pane.GetFont()
            pane_font.SetWeight(wx.FONTWEIGHT_BOLD)
            collapsible_pane.SetFont(pane_font)
            self.set_collapsible_pane_colours(collapsible_pane)
            pane = collapsible_pane.GetPane()
            if self.language_code == "ar":
                pane.SetLayoutDirection(wx.Layout_LeftToRight)
            pane.SetBackgroundColour(self.theme["panel_bg"])
            pane_sizer = wx.BoxSizer(wx.HORIZONTAL)
            guide_panel = wx.Panel(pane, wx.ID_ANY)
            guide_panel.SetMinSize((1, -1))
            guide_panel.SetBackgroundColour(self.theme["hierarchy_line"])
            child_sizer = wx.BoxSizer(wx.VERTICAL)
            module_path = parent_path + (module_name,)

            self.add_module_signal_group_rows(
                pane, child_sizer, signal_group[module_name], module_path
            )
            if self.language_code == "ar":
                pane_sizer.Add(child_sizer, 1, wx.EXPAND)
                pane_sizer.AddSpacer((HIERARCHY_GUIDE_WIDTH - 1) // 2)
                pane_sizer.Add(guide_panel, 0, wx.EXPAND)
                pane_sizer.AddSpacer((HIERARCHY_GUIDE_WIDTH - 1) // 2)
            else:
                pane_sizer.AddSpacer((HIERARCHY_GUIDE_WIDTH - 1) // 2)
                pane_sizer.Add(guide_panel, 0, wx.EXPAND)
                pane_sizer.AddSpacer((HIERARCHY_GUIDE_WIDTH - 1) // 2)
                pane_sizer.Add(child_sizer, 1, wx.EXPAND)

            pane.SetSizer(pane_sizer)

            self.module_signal_pane_paths[collapsible_pane.GetId()] = (
                collapsible_pane,
                module_path,
            )
            if module_path in self.module_signal_expanded_paths:
                collapsible_pane.Collapse(False)

            collapsible_pane.Bind(
                wx.EVT_COLLAPSIBLEPANE_CHANGED,
                self.on_module_signal_pane_changed,
            )
            pane_row_sizer = wx.BoxSizer(wx.HORIZONTAL)
            if self.language_code == "ar":
                pane_row_sizer.AddStretchSpacer(1)
                pane_row_sizer.Add(collapsible_pane, 0, wx.EXPAND)
                if parent_path:
                    pane_row_sizer.AddSpacer(MODULE_NESTED_INDENT_WIDTH)
                pane_parent.SetSizer(pane_row_sizer)
                parent_sizer.Add(
                    pane_parent,
                    0,
                    wx.EXPAND | wx.TOP | wx.BOTTOM | wx.LEFT | wx.RIGHT,
                    MODULE_PANE_GAP,
                )
            else:
                if parent_path:
                    pane_row_sizer.AddSpacer(MODULE_NESTED_INDENT_WIDTH)
                pane_row_sizer.Add(collapsible_pane, 1, wx.EXPAND)
                parent_sizer.Add(
                    pane_row_sizer,
                    0,
                    wx.EXPAND | wx.TOP | wx.BOTTOM | wx.LEFT | wx.RIGHT,
                    MODULE_PANE_GAP,
                )

    def store_module_signal_pane_state(self):
        """Remember expanded module panes before the signal list is rebuilt."""
        for pane, module_path in self.module_signal_pane_paths.values():
            try:
                is_expanded = pane.IsExpanded()
            except RuntimeError:
                continue
            if is_expanded:
                self.module_signal_expanded_paths.add(module_path)
            else:
                self.module_signal_expanded_paths.discard(module_path)

    def add_available_signal_row(
        self, parent, parent_sizer, label_text, signal_name, indent=0
    ):
        """Add one available signal row with an Add/Remove action button.

        Arguments:
        parent -- wx parent containing the row
        parent_sizer -- sizer receiving the row
        label_text -- text shown beside the action button
        signal_name -- full internal signal name used for monitor actions
        indent -- optional left spacer for nested module signals

        """
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(parent, wx.ID_ANY, label_text, style=wx.ST_ELLIPSIZE_END)
        label.SetMinSize((SIGNAL_LABEL_MIN_WIDTH, -1))
        label.SetToolTip(signal_name)
        label.SetForegroundColour(self.theme["text"])
        label_font = label.GetFont()
        label_font.SetPointSize(max(1, label_font.GetPointSize() - 1))
        label_font.SetWeight(wx.FONTWEIGHT_NORMAL)
        label.SetFont(label_font)

        action_button = wxbuttons.GenBitmapButton(
            parent,
            wx.ID_ANY,
            wx.Bitmap(1, 1),
            size=(SIGNAL_ACTION_BUTTON_SIZE, SIGNAL_ACTION_BUTTON_SIZE),
            style=wx.BORDER_NONE,
        )
        action_button.SetMinSize((SIGNAL_ACTION_BUTTON_SIZE, SIGNAL_ACTION_BUTTON_SIZE))
        action_button.SetMaxSize((SIGNAL_ACTION_BUTTON_SIZE, SIGNAL_ACTION_BUTTON_SIZE))
        self.module_signal_button_names[action_button.GetId()] = signal_name
        self.module_signal_action_buttons[signal_name] = action_button
        self.update_available_signal_button(action_button, signal_name)

        action_column_sizer = wx.BoxSizer(wx.HORIZONTAL)
        action_column_sizer.SetMinSize(
            (SIGNAL_ACTION_COLUMN_WIDTH, SIGNAL_ACTION_BUTTON_SIZE)
        )
        action_column_sizer.Add(action_button, 0, wx.ALIGN_CENTER_VERTICAL)
        if self.language_code == "ar":
            row_sizer.AddStretchSpacer(1)
            if indent > 0:
                row_sizer.AddSpacer(indent)
            row_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
            row_sizer.Add(action_column_sizer, 0, wx.ALIGN_CENTER_VERTICAL)
        else:
            if indent > 0:
                row_sizer.AddSpacer(indent)
            row_sizer.Add(
                action_column_sizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
            )
            row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL)
        parent_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

    def update_available_signal_button(self, button, signal_name):
        """Set one available signal button to the correct Add/Remove state."""
        # The same button changes job after it is clicked so remove the old
        # event binding before attaching the new add or remove handler
        button.Unbind(wx.EVT_BUTTON)
        button.Unbind(wx.EVT_LEFT_DOWN)

        if self.is_signal_monitored(signal_name):
            action_label = _("Remove")
            action_handler = self.on_delete_module_signal_button
            if getattr(self, "theme_name", "light") == "dark":
                icon_path = DARK_REMOVE_ICON_PATH
            else:
                icon_path = LIGHT_REMOVE_ICON_PATH
        else:
            action_label = _("Add")
            action_handler = self.on_add_module_signal_button
            if getattr(self, "theme_name", "light") == "dark":
                icon_path = DARK_ADD_ICON_PATH
            else:
                icon_path = LIGHT_ADD_ICON_PATH

        button.SetToolTip(action_label)
        button.SetBackgroundColour(self.theme["panel_bg"])
        button.SetForegroundColour(self.theme["text"])
        if hasattr(button, "SetBezelWidth"):
            button.SetBezelWidth(0)
        if hasattr(button, "SetMargins"):
            button.SetMargins(0, 0)
        if hasattr(button, "SetUseFocusIndicator"):
            button.SetUseFocusIndicator(False)

        bitmap = self.load_icon_bitmap(icon_path, 12)
        if bitmap is not None and hasattr(button, "SetBitmapLabel"):
            button.SetLabel("")
            button.SetBitmapLabel(bitmap)
        else:
            button.SetLabel(action_label)
        button.Bind(wx.EVT_BUTTON, action_handler)
        button.Bind(wx.EVT_LEFT_DOWN, action_handler)
        button.Refresh()

    def is_signal_monitored(self, signal_name):
        """Return whether a signal is already monitored."""
        return signal_name in self.monitors.monitors_dictionary

    def update_monitor_rows(self):
        """Rebuild the legacy active monitor list.

        The visible monitor picker is now the available signal panel but this
        list is still maintained for older code paths and tests.

        """
        # Clear the old rows and rebuild them
        self.monitor_rows_sizer.Clear(delete_windows=True)
        self.monitor_button_keys = {}

        if not self.monitors.monitors_dictionary:
            empty_label = wx.StaticText(
                self.monitor_rows, wx.ID_ANY, _("No active monitors")
            )
            empty_label.SetForegroundColour(self.theme["muted_text"])
            self.monitor_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
        else:
            for monitor_name in self.monitors.monitors_dictionary:
                row_sizer = wx.BoxSizer(wx.HORIZONTAL)
                label = wx.StaticText(self.monitor_rows, wx.ID_ANY, monitor_name)
                button = wx.Button(self.monitor_rows, wx.ID_ANY, _("Remove"))
                label.SetForegroundColour(self.theme["text"])
                button.SetBackgroundColour(self.theme["button_bg"])
                button.SetForegroundColour(self.theme["remove"])

                self.monitor_button_keys[button.GetId()] = monitor_name
                button.Bind(wx.EVT_BUTTON, self.on_remove_monitor_row_button)
                row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
                row_sizer.Add(button, 0)
                self.monitor_rows_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

        self.monitor_rows.Layout()
        self.monitor_rows.FitInside()

    def on_remove_monitor_row_button(self, event):
        """Remove a monitor selected from the active monitor list."""
        button_id = event.GetId()
        monitor_name = self.monitor_button_keys[button_id]
        action_snapshot = self.get_simulation_snapshot()

        if self.monitors.remove_monitor(monitor_name):
            self.simulation_history.append(action_snapshot)
            self.redo_history = []
            self.cycle_history = []
            self.cycle_redo_history = []
            self.update_history_buttons()
            self.update_cycle_inspector_range()
            self.show_status(
                tr(
                    "Removed monitor for {monitor_name}.",
                    monitor_name=monitor_name,
                )
            )
        else:
            self.show_status(
                tr(
                    "Error: could not remove monitor for {monitor_name}.",
                    monitor_name=monitor_name,
                )
            )

        self.update_monitor_rows()
        _get_active_canvas(self).render()

    # SWITCH AND MONITOR EVENT HANDLERS

    def on_switch_state_button(self, event):
        """Handle a LOW/HIGH button click in the switch panel."""
        (
            switch_name,
            switch_value,
            low_button,
            high_button,
            low_label,
            high_label,
        ) = self.switch_state_buttons[event.GetId()]
        self.update_switch_state_buttons(
            low_button,
            high_button,
            low_label,
            high_label,
            switch_value,
        )
        self.set_switch_value(switch_name, switch_value)

    def set_switch_value(self, switch_name, switch_value):
        """Set one switch to LOW or HIGH.

        Arguments:
        switch_name -- visible switch name.
        switch_value -- simulator value, 0 for LOW or 1 for HIGH

        Updates the Devices switch state and records the action for undo.

        """
        switch_id = self.names.query(switch_name)

        if switch_id is None:
            self.show_status(
                tr(
                    "Error: unknown switch '{switch_name}'.",
                    switch_name=switch_name,
                )
            )
            return

        # set_switch returns True/False, not one of the Devices error codes
        action_snapshot = self.get_simulation_snapshot()
        switch_was_set = self.devices.set_switch(switch_id, switch_value)

        if switch_was_set:
            self.simulation_history.append(action_snapshot)
            self.redo_history = []
            self.cycle_history = []
            self.cycle_redo_history = []
            self.update_history_buttons()
            if switch_value == 1:
                switch_label = _("HIGH")
            else:
                switch_label = _("LOW")
            self.show_status(
                tr(
                    "Set switch {switch_name} to {switch_label}.",
                    switch_name=switch_name,
                    switch_label=switch_label,
                )
            )
        else:
            self.show_status(
                tr(
                    "Error: could not set {switch_name}.",
                    switch_name=switch_name,
                )
            )

    def on_module_signal_pane_changed(self, event):
        """Record a pane expansion change and refit the scrolled list."""
        pane = event.GetEventObject()
        pane_data = self.module_signal_pane_paths.get(pane.GetId())
        if pane_data is not None:
            module_path = pane_data[1]
            if pane.IsExpanded():
                self.module_signal_expanded_paths.add(module_path)
            else:
                self.module_signal_expanded_paths.discard(module_path)

        self.module_signal_rows.Layout()
        self.module_signal_rows.FitInside()

    def on_add_module_signal_button(self, event):
        """Add the signal attached to an available-list action button."""
        button_id = event.GetId()
        signal_name = self.module_signal_button_names[button_id]

        scroll_x, scroll_y = self.module_signal_rows.GetViewStart()
        self.add_monitor_by_name(signal_name, refresh_available_signals=False)

        button = self.module_signal_action_buttons[signal_name]
        self.update_available_signal_button(button, signal_name)
        self.module_signal_rows.Scroll(scroll_x, scroll_y)

    def on_delete_module_signal_button(self, event):
        """Remove the signal attached to an available-list action button."""
        self.stop_live_trace()
        button_id = event.GetId()
        signal_name = self.module_signal_button_names[button_id]
        scroll_x, scroll_y = self.module_signal_rows.GetViewStart()
        action_snapshot = self.get_simulation_snapshot()

        if self.monitors.remove_monitor(signal_name):
            self.simulation_history.append(action_snapshot)
            self.redo_history = []
            self.cycle_history = []
            self.cycle_redo_history = []
            self.update_history_buttons()
            self.update_cycle_inspector_range()
            self.show_status(
                tr(
                    "Removed monitor for {monitor_name}.",
                    monitor_name=signal_name,
                )
            )
        else:
            self.show_status(
                tr(
                    "Error: {signal_name} is not monitored.",
                    signal_name=signal_name,
                )
            )

        button = self.module_signal_action_buttons[signal_name]
        self.update_available_signal_button(button, signal_name)
        self.module_signal_rows.Scroll(scroll_x, scroll_y)
        _get_active_canvas(self).render()

    def add_monitor_by_name(self, monitor_name, refresh_available_signals=True):
        """Add a named signal to the monitor list.

        Arguments:
        monitor_name -- GUI-facing signal name to monitor
        refresh_available_signals -- if True, rebuild the available signal list
        after adding the monitor; button handlers pass False and update only
        the clicked row to preserve scroll position.

        Resolves the display name to simulator IDs, pads new traces for cycles
        already recorded, clears undo/redo history, updates monitor controls,
        redraws the waveform.

        """
        self.stop_live_trace()

        if not monitor_name:
            self.show_status(_("Error: enter a monitor name."))
            return

        signal_ids = self.get_signal_ids(monitor_name)

        if signal_ids is None:
            self.show_status(
                tr(
                    "Error: unknown signal '{monitor_name}'.",
                    monitor_name=monitor_name,
                )
            )
            return

        device_id, output_id = signal_ids

        action_snapshot = self.get_simulation_snapshot()
        error_type = self.monitors.make_monitor(
            device_id,
            output_id,
            requested_name=monitor_name,
            cycles_completed=self.cycles_completed,
        )

        if error_type == self.monitors.NO_ERROR:
            self.simulation_history.append(action_snapshot)
            self.redo_history = []
            self.cycle_history = []
            self.cycle_redo_history = []
            self.update_history_buttons()
            self.update_cycle_inspector_range()
            self.show_status(
                tr(
                    "Added monitor for {monitor_name}.",
                    monitor_name=monitor_name,
                )
            )
            if refresh_available_signals:
                self.update_module_signal_rows()
            self.update_monitor_rows()
        else:
            self.show_status(
                tr(
                    "Error: could not add monitor for {monitor_name}. {reason}.",
                    monitor_name=monitor_name,
                    reason=self.monitor_error_message(error_type),
                )
            )

        _get_active_canvas(self).render()
