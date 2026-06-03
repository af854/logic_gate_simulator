"""Implement the graphical user interface for the Logic Simulator.

Used in the Logic Simulator project to enable the user to run the simulation
or adjust the network properties.

Classes
-------
MyGLCanvas - handles all canvas drawing operations.
Gui - configures the main window and all the widgets.
"""

import wx
import wx.lib.buttons as wxbuttons
import wx.glcanvas as wxcanvas
from OpenGL import GL, GLUT
import csv
import contextlib
import io
import os

from names import Names
from devices import Devices
from network import Network
from monitors import Monitors
from scanner import Scanner
from parse import Parser


# GLUT is initialised once to avoid repeated initialisation warnings on macOS.
GLUT_INITIALISED = False


def initialise_glut_once():
    """Initialise GLUT once per process."""
    global GLUT_INITIALISED
    if not GLUT_INITIALISED:
        GLUT.glutInit()
        GLUT_INITIALISED = True


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
ID_SHOW_AVAILABLE_SIGNALS = wx.NewIdRef()
ID_SHOW_SIMULATION = wx.NewIdRef()
ID_SHOW_SWITCHES = wx.NewIdRef()
ID_SHOW_CONSOLE = wx.NewIdRef()


MAX_RUN_CYCLES = 1000
LIVE_TRACE_INTERVAL_MS = 1000
LIVE_TRACE_SPEEDS = [("1x", 1.0), ("1.5x", 1.5), ("2x", 2.0), ("0.5x", 0.5)]
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

EXTERNAL_DOCUMENTATION_URL = ""
LIGHT_CLOSE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "x_icon_light.png"
)
DARK_CLOSE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "x_icon_dark.png"
)
LIGHT_MODE_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "light_mode.png"
)
DARK_MODE_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "dark_mode.png")
LIGHT_UNDO_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "undo_light.png"
)
DARK_UNDO_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "undo_dark.png")
LIGHT_REDO_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "icons", "redo_light.png"
)
DARK_REDO_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "redo_dark.png")
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


def add_signal_to_module_tree(module_tree, full_signal_name, value):
    """Add one arrow-separated signal name to a nested module tree."""
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


###############################################################################
# OPENGL CANVAS
###############################################################################


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

    def __init__(self, parent, devices, monitors):
        """Initialise canvas properties and useful variables."""
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
        initialise_glut_once()
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

        # Bind events to the canvas
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.on_mouse)

    def init_gl(self):
        """Configure and initialise the OpenGL context."""
        size = self.get_render_size()
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

    def get_render_size(self):
        """Return the size used for layout calculations."""
        render_size_override = getattr(self, "render_size_override", None)
        if render_size_override is not None:
            return render_size_override

        return self.GetClientSize()

    def render(self, swap_buffers=True):
        """Handle all drawing operations."""
        self.SetCurrent(self.context)
        if not self.init:
            # Configure the viewport, modelview and projection matrices
            self.init_gl()
            self.init = True

        # Clear everything
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        size = self.get_render_size()

        if not self.monitors.monitors_dictionary:
            self.render_text(
                "No monitor signals to display.",
                10,
                size.height - 30,
                colour=self.theme["canvas_text"],
            )
        else:
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
                    max_trace_length, start_x, bottom_y, top_y + amplitude, step
                )

        # We have been drawing to the back buffer, flush the graphics pipeline
        # and swap the back buffer to the front
        GL.glFlush()
        if swap_buffers:
            self.SwapBuffers()

    def on_paint(self, event):
        """Handle the paint event."""
        self.SetCurrent(self.context)
        if not self.init:
            # Configure the viewport, modelview and projection matrices
            self.init_gl()
            self.init = True

        self.render()

    def on_size(self, event):
        """Handle the canvas resize event."""
        # Forces reconfiguration of the viewport, modelview and projection
        # matrices on the next paint event
        self.init = False

    def on_mouse(self, event):
        """Handle mouse events."""
        # Calculate object coordinates of the mouse position
        size = self.get_render_size()
        ox = (event.GetX() - self.pan_x) / self.zoom
        oy = (size.height - event.GetY() - self.pan_y) / self.zoom
        old_zoom = self.zoom
        if event.ButtonDown():
            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
        if event.Dragging():
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

    def limit_top_left_pan(self):
        """Prevent dragging the waveform past its top-left starting corner."""
        size = self.get_render_size()
        minimum_pan_y = size.height * (1 - self.zoom)

        if self.pan_x > 0:
            self.pan_x = 0
        if self.pan_y < minimum_pan_y:
            self.pan_y = minimum_pan_y

    def zoom_at_canvas_centre(self, factor):
        """Zoom around the centre of the canvas."""
        # Find the centre of thw canvas
        size = self.get_render_size()
        centre_x = size.width / 2
        centre_y = size.height / 2
        object_x = (centre_x - self.pan_x) / self.zoom
        object_y = (centre_y - self.pan_y) / self.zoom
        old_zoom = self.zoom

        self.zoom *= factor
        self.pan_x -= (self.zoom - old_zoom) * object_x
        self.pan_y -= (self.zoom - old_zoom) * object_y
        self.limit_top_left_pan()

        # The view has changed so init_gl() must run again before drawing
        self.init = False
        self.Refresh()

    def zoom_in(self):
        """Zoom into the waveform display."""
        self.zoom_at_canvas_centre(1.25)

    def zoom_out(self):
        """Zoom out of the waveform display."""
        self.zoom_at_canvas_centre(0.8)

    def reset_view(self):
        """Reset waveform panning and zooming."""
        self.pan_x = 0
        self.pan_y = 0
        self.zoom = 1
        self.init = False
        self.Refresh()

    def follow_latest_cycle(self, right_margin=20):
        """Pan horizontally enough to keep the newest trace cycle visible."""
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

    def get_export_image_size(self):
        """Return a PNG size large enough for the current waveform data."""
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

    def save_image(self, file_path):
        """Save the current waveform display as a PNG image."""
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
                    0, 0, tile["width"], tile["height"], GL.GL_RGB, GL.GL_UNSIGNED_BYTE
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

    def create_blank_export_image(self, export_size):
        """Return a blank export image filled with the canvas background colour."""
        red = int(self.theme["canvas_bg"][0] * 255)
        green = int(self.theme["canvas_bg"][1] * 255)
        blue = int(self.theme["canvas_bg"][2] * 255)
        export_image = wx.Image(export_size.width, export_size.height)
        export_image.SetData(
            bytes([red, green, blue]) * export_size.width * export_size.height
        )
        return export_image

    def get_export_tiles(self, export_size, capture_size):
        """Return bottom-origin canvas tiles needed to cover one export image."""
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

    def render_text(self, text, x_pos, y_pos, colour=(0.0, 0.0, 0.0)):
        """Handle text drawing operations."""
        GL.glColor3f(*colour)
        GL.glRasterPos2f(x_pos, y_pos)
        font = GLUT.GLUT_BITMAP_HELVETICA_12

        for character in text:
            if character == "\n":
                y_pos = y_pos - 20
                GL.glRasterPos2f(x_pos, y_pos)
            else:
                GLUT.glutBitmapCharacter(font, ord(character))

    def get_canvas_label_text(self, label_text, start_x):
        """Shorten a canvas label if it would run into the waveform."""
        label_margin = 30
        average_character_width = 8
        available_width = start_x - label_margin
        max_characters = int(available_width / average_character_width)

        if max_characters < 4:
            return "..."
        if len(label_text) <= max_characters:
            return label_text
        return label_text[: max_characters - 3] + "..."

    def get_monitor_display_rows(self):
        """Return grouped rows for waveform monitor labels and traces."""
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

            add_signal_to_module_tree(module_tree, monitor_name, monitor.trace)

        # now flatten the tree into drawing rows
        # This keeps the render() method simple because it only has to loop over
        # one list
        self.add_module_monitor_display_rows(rows, module_tree, 0)
        return rows

    def add_module_monitor_display_rows(self, rows, signal_group, depth):
        """Append heading and trace rows for one module signal group."""
        indent = "  " * depth

        for module_name in sorted(signal_group):
            if module_name == "signals_at_this_level":
                continue

            # Headings are given a smaller height
            rows.append(
                {"kind": "heading", "label": indent + module_name, "height": 0.35}
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

    def signal_to_y(self, signal, low_y, high_y):
        """Convert a signal value into a y-position."""
        # RISING and FALLING are drawn at the level they are moving towards
        if signal in [self.devices.HIGH, self.devices.RISING]:
            return high_y

        if signal in [self.devices.LOW, self.devices.FALLING]:
            return low_y

        return None

    def draw_line(self, x1, y1, x2, y2):
        """Draw a single OpenGL line."""
        GL.glBegin(GL.GL_LINES)
        GL.glVertex2f(x1, y1)
        GL.glVertex2f(x2, y2)
        GL.glEnd()

    def draw_filled_rectangle(self, x_pos, y_pos, width, height):
        """Draw a filled rectangle on the canvas."""
        GL.glBegin(GL.GL_QUADS)
        GL.glVertex2f(x_pos, y_pos)
        GL.glVertex2f(x_pos + width, y_pos)
        GL.glVertex2f(x_pos + width, y_pos + height)
        GL.glVertex2f(x_pos, y_pos + height)
        GL.glEnd()

    def get_cycle_label_interval(self, step):
        """Return a readable cycle label interval for the current scale."""
        # Do not label every cycle, otherwise the numbers overlap and become
        # unreadable - the interval depends on the zoom level
        if step >= 18:
            return 5
        if step >= 10:
            return 10
        if step >= 6:
            return 20
        return 50

    def get_waveform_layout(self, display_rows=None):
        """Return horizontal waveform layout values used by drawing and controls."""
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
        self, trace_length, start_x, axis_y, bottom_y, top_y, step, cycle_offset=0
    ):
        """Draw the shared x-axis showing simulation cycles."""
        if trace_length <= 0:
            return

        end_x = start_x + trace_length * step
        label_interval = self.get_cycle_label_interval(step)

        # Minor ticks show every cycle, numbers are shown less often depending
        # on the zoom level
        GL.glColor3f(*self.theme["canvas_axis"])
        self.draw_line(start_x, axis_y, end_x, axis_y)
        self.render_text(
            "Cycles", start_x - 56, axis_y - 4, colour=self.theme["canvas_muted"]
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

    def draw_value_axis(self, start_x, low_y, high_y, step, trace_length):
        """Draw the per-trace y-axis showing LOW/HIGH values."""
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

    def draw_trace(self, trace, start_x, low_y, high_y, step):
        """Draw a single monitored signal trace."""
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

    def signal_to_display_text(self, signal):
        """Return a short text value for a signal on the canvas."""
        if signal == self.devices.HIGH or signal == self.devices.RISING:
            return "1"
        if signal == self.devices.LOW or signal == self.devices.FALLING:
            return "0"
        if signal == self.devices.BLANK:
            return "-"
        return str(signal)

    def draw_cycle_inspector(self, trace_length, start_x, bottom_y, top_y, step):
        """Draw a vertical cursor for the selected inspected cycle."""
        if trace_length <= 0:
            return

        cursor_x = self.get_cycle_inspector_x(trace_length, start_x, step)
        GL.glColor3f(*self.theme["canvas_axis"])
        GL.glLineWidth(1.5)
        self.draw_line(cursor_x, bottom_y - 8, cursor_x, top_y + 4)
        GL.glLineWidth(1.0)

    def get_cycle_inspector_x(self, trace_length, start_x, step):
        """Return the x-position of the cycle inspector cursor."""
        cycle_index = min(self.cycle_inspector_index, trace_length - 1)
        return start_x + (cycle_index + 1) * step

    def draw_cycle_inspector_value(
        self, trace, cycle_index, start_x, low_y, high_y, step
    ):
        """Draw the selected cycle value beside one trace."""
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

    def get_cycle_inspector_value_background(self, text_x, text_y, value_text):
        """Return the rectangle behind one cycle inspector value."""
        width = len(value_text) * 8 + 8
        height = 16
        return (text_x - 4, text_y - 4, width, height)


###############################################################################
# GUI FRAME
###############################################################################


class Gui(wx.Frame):
    """Configure the main window and all the widgets.

    This class provides a graphical user interface for the Logic Simulator and
    enables the user to change the circuit properties and run simulations.

    Parameters
    ----------
    title: title of the window.

    Public methods
    --------------
    on_menu(self, event): Event handler for the file menu.

    on_run_cycles_button(self, event): Event handler for running cycles.

    """

    def __init__(self, title, path, names, devices, network, monitors, net_driver_dict):
        """Initialise widgets and layout."""
        # Create the main window and set its starting size
        super().__init__(parent=None, title=title, size=(1200, 750))
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

        file_menu.Append(ID_OPEN_FILE, "&Open...\tctrl+O")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "&Exit\tctrl+Q")
        help_menu.Append(ID_HELP, "&Quick start\tF1")
        help_menu.Append(ID_HELP_SHORTCUTS, "&Keyboard shortcuts")
        help_menu.Append(ID_HELP_SYNTAX, "&Circuit file syntax")
        help_menu.AppendSeparator()
        help_menu.Append(ID_HELP_EXTERNAL_DOCS, "External &documentation")
        help_menu.AppendSeparator()
        help_menu.Append(wx.ID_ABOUT, "&About")
        export_menu.Append(ID_EXPORT_IMAGE, "Export as PNG\tctrl+shift+P")
        export_menu.Append(ID_EXPORT_CSV, "Export as CSV\tctrl+shift+E")
        view_menu.Append(ID_ZOOM_IN, "Zoom in\tctrl+=")
        view_menu.Append(ID_ZOOM_OUT, "Zoom out\tctrl+-")
        view_menu.Append(ID_RESET_VIEW, "Reset view\tctrl+0")
        view_menu.AppendSeparator()

        self.cycle_inspector_menu_item = view_menu.AppendCheckItem(
            ID_TOGGLE_CYCLE_INSPECTOR, "Show cycle inspector"
        )
        view_menu.AppendSeparator()

        if self.theme_name == "dark":
            theme_label = "Switch to light mode\tctrl+shift+T"
        else:
            theme_label = "Switch to dark mode\tctrl+shift+T"

        self.theme_menu_item = view_menu.Append(ID_TOGGLE_THEME, theme_label)
        self.window_menu_items = {
            "available_signals": window_menu.AppendCheckItem(
                ID_SHOW_AVAILABLE_SIGNALS, "Show Available signals\tctrl+1"
            ),
            "simulation": window_menu.AppendCheckItem(
                ID_SHOW_SIMULATION, "Show Simulation\tctrl+2"
            ),
            "switches": window_menu.AppendCheckItem(
                ID_SHOW_SWITCHES, "Show Switches\tctrl+3"
            ),
            "console": window_menu.AppendCheckItem(
                ID_SHOW_CONSOLE, "Show Console\tctrl+4"
            ),
        }

        menu_bar.Append(file_menu, "&File")
        menu_bar.Append(view_menu, "&View")
        menu_bar.Append(window_menu, "&Window")
        menu_bar.Append(export_menu, "&Export")
        menu_bar.Append(help_menu, "&Help")

        self.menu_bar = menu_bar
        self.SetMenuBar(menu_bar)
        self.CreateStatusBar()
        self.set_status("Ready")

        # Canvas for drawing signals
        self.canvas = MyGLCanvas(self, devices, monitors)
        self.canvas.SetMinSize((500, 420))

        # Configure the widgets
        self.text = wx.StaticText(self, wx.ID_ANY, "Cycles to run")
        self.cycles_completed_text = wx.StaticText(self, wx.ID_ANY, "Cycles passed: 0")
        self.run_cycles_button = wx.Button(self, wx.ID_ANY, "Run cycles")
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
        self.reset_button = wx.Button(self, wx.ID_ANY, "Reset simulation")
        self.clear_traces_button = wx.Button(self, wx.ID_ANY, "Clear traces")
        self.live_trace_timer = wx.Timer(self)
        self.cycles_completed_text.SetMinSize((CYCLES_COMPLETED_WIDTH, -1))
        self.cycles_completed_text.SetMaxSize((CYCLES_COMPLETED_WIDTH, -1))
        self.run_cycles_button.SetMinSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.run_cycles_button.SetInitialSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.run_cycles_button.SetMaxSize((-1, COMMAND_BUTTON_HEIGHT))
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
        self.reset_button.SetMaxSize((-1, COMMAND_BUTTON_HEIGHT))
        self.clear_traces_button.SetMinSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.clear_traces_button.SetInitialSize(
            (SIMULATION_CONTROL_WIDTH, COMMAND_BUTTON_HEIGHT)
        )
        self.clear_traces_button.SetMaxSize((-1, COMMAND_BUTTON_HEIGHT))
        self.live_trace_button.SetMaxSize(
            (LIVE_TRACE_BUTTON_SIZE, LIVE_TRACE_BUTTON_SIZE)
        )
        self.console_box = wx.TextCtrl(
            self, wx.ID_ANY, "", style=wx.TE_MULTILINE | wx.TE_READONLY
        )
        self.console_box.SetMinSize((-1, 90))
        self.clear_status_button = wx.Button(self, wx.ID_ANY, "Clear console")
        self.clear_status_button.SetMinSize((-1, COMMAND_BUTTON_HEIGHT))
        self.clear_status_button.SetInitialSize((-1, COMMAND_BUTTON_HEIGHT))
        self.clear_status_button.SetMaxSize((-1, COMMAND_BUTTON_HEIGHT))
        self.cycle_inspector_panel = wx.Panel(self, wx.ID_ANY)
        self.cycle_inspector_label = wx.StaticText(
            self.cycle_inspector_panel, wx.ID_ANY, "Cycle:"
        )
        self.cycle_inspector_entry = wx.TextCtrl(
            self.cycle_inspector_panel, wx.ID_ANY, "-", style=wx.TE_PROCESS_ENTER
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
            self.cycle_inspector_panel, wx.ID_ANY, 0, 0, 1, style=wx.SL_HORIZONTAL
        )
        self.cycle_inspector_panel.Hide()
        self.undo_button = wxbuttons.GenBitmapButton(
            self, wx.ID_ANY, wx.Bitmap(1, 1), size=(28, 28), style=wx.BORDER_NONE
        )
        self.redo_button = wxbuttons.GenBitmapButton(
            self, wx.ID_ANY, wx.Bitmap(1, 1), size=(28, 28), style=wx.BORDER_NONE
        )
        self.toggle_theme_button = wxbuttons.GenBitmapButton(
            self, wx.ID_ANY, wx.Bitmap(1, 1), size=(34, 34)
        )
        self.undo_button.SetMinSize((28, 28))
        self.redo_button.SetMinSize((28, 28))
        self.toggle_theme_button.SetMinSize((34, 34))
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

        # Bind events to widgets
        self.Bind(wx.EVT_MENU, self.on_menu)
        self.Bind(wx.EVT_MENU, self.on_help, id=ID_HELP)
        self.Bind(wx.EVT_MENU, self.on_keyboard_shortcuts_help, id=ID_HELP_SHORTCUTS)
        self.Bind(wx.EVT_MENU, self.on_syntax_help, id=ID_HELP_SYNTAX)
        self.Bind(wx.EVT_MENU, self.on_external_documentation, id=ID_HELP_EXTERNAL_DOCS)
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
        self.toggle_theme_button.Bind(wx.EVT_BUTTON, self.on_toggle_theme)

        self.Bind(wx.EVT_MENU, self.on_run_cycles_button, id=ID_RUN)
        self.Bind(wx.EVT_MENU, self.on_run_one_cycle, id=ID_RUN_ONE)
        self.Bind(wx.EVT_MENU, self.on_toggle_live_trace, id=ID_TOGGLE_LIVE_TRACE)
        self.Bind(wx.EVT_MENU, self.on_undo_cycle, id=ID_UNDO_CYCLE)
        self.Bind(wx.EVT_MENU, self.on_redo_cycle, id=ID_REDO_CYCLE)
        self.Bind(wx.EVT_MENU, self.on_clear_status, id=ID_CLEAR_STATUS)
        self.Bind(wx.EVT_MENU, self.on_reset_view, id=ID_RESET_VIEW)
        self.Bind(
            wx.EVT_MENU, self.on_toggle_cycle_inspector, id=ID_TOGGLE_CYCLE_INSPECTOR
        )
        self.Bind(wx.EVT_MENU, self.on_export_image, id=ID_EXPORT_IMAGE)
        self.Bind(wx.EVT_MENU, self.on_export_csv, id=ID_EXPORT_CSV)
        self.Bind(wx.EVT_MENU, self.on_zoom_in, id=ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, self.on_zoom_out, id=ID_ZOOM_OUT)
        self.Bind(wx.EVT_MENU, self.on_open_file, id=ID_OPEN_FILE)
        self.Bind(wx.EVT_MENU, self.on_toggle_theme, id=ID_TOGGLE_THEME)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_AVAILABLE_SIGNALS)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_SIMULATION)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_SWITCHES)
        self.Bind(wx.EVT_MENU, self.on_show_section, id=ID_SHOW_CONSOLE)

        # Keyboard shortcuts call the same handlers as the buttons
        accelerators = wx.AcceleratorTable(
            [
                (wx.ACCEL_NORMAL, wx.WXK_SPACE, ID_RUN),  # Space: run cycles
                (
                    wx.ACCEL_NORMAL,
                    wx.WXK_RIGHT,
                    ID_RUN_ONE,
                ),  # Right arrow: run one cycle
                (
                    wx.ACCEL_CTRL,
                    wx.WXK_SPACE,
                    ID_TOGGLE_LIVE_TRACE,
                ),  # Ctrl+Space: play/pause live tracing
                (wx.ACCEL_CTRL, ord("Z"), ID_UNDO_CYCLE),  # Ctrl+Z: undo one cycle
                (wx.ACCEL_CTRL, ord("Y"), ID_REDO_CYCLE),  # Ctrl+Y: redo one cycle
                (wx.ACCEL_CTRL, ord("O"), ID_OPEN_FILE),  # Ctrl+O: open file
                (wx.ACCEL_CTRL, ord("="), ID_ZOOM_IN),  # Ctrl+=: zoom in
                (wx.ACCEL_CTRL, ord("-"), ID_ZOOM_OUT),  # Ctrl+-: zoom out
                (wx.ACCEL_CTRL, ord("0"), ID_RESET_VIEW),  # Ctrl+0: reset view
                (
                    wx.ACCEL_CTRL,
                    ord("I"),
                    ID_TOGGLE_CYCLE_INSPECTOR,
                ),  # Ctrl+I: show/hide cycle inspector
                (
                    wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
                    ord("P"),
                    ID_EXPORT_IMAGE,
                ),  # Ctrl+Shift+P: export PNG
                (
                    wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
                    ord("E"),
                    ID_EXPORT_CSV,
                ),  # Ctrl+Shift+E: export CSV
                (
                    wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
                    ord("T"),
                    ID_TOGGLE_THEME,
                ),  # Ctrl+Shift+T: light/dark mode
                (
                    wx.ACCEL_CTRL,
                    ord("1"),
                    ID_SHOW_AVAILABLE_SIGNALS,
                ),  # Ctrl+1: show available signals
                (
                    wx.ACCEL_CTRL,
                    ord("2"),
                    ID_SHOW_SIMULATION,
                ),  # Ctrl+2: show simulation
                (wx.ACCEL_CTRL, ord("3"), ID_SHOW_SWITCHES),  # Ctrl+3: show switches
                (wx.ACCEL_CTRL, ord("4"), ID_SHOW_CONSOLE),  # Ctrl+4: show console
                (wx.ACCEL_NORMAL, wx.WXK_F1, ID_HELP),  # F1: help
                (wx.ACCEL_CTRL, ord("Q"), wx.ID_EXIT),  # Ctrl+Q: exit
                (wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_CLEAR_STATUS),
            ]
        )  # Delete: clear console
        self.SetAcceleratorTable(accelerators)

        # Configure sizers for layout
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        canvas_sizer = wx.BoxSizer(wx.VERTICAL)
        side_sizer = wx.BoxSizer(wx.VERTICAL)
        history_theme_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.section_panels = {}
        self.section_titles = {}
        self.section_close_buttons = {}

        simulation_panel, simulation_sizer = self.create_section_panel(
            "Simulation", "simulation"
        )
        simulation_panel.SetMinSize((SIMULATION_PANEL_WIDTH, -1))
        self.spin = wx.SpinCtrl(simulation_panel, wx.ID_ANY, "10")
        self.spin.SetRange(1, MAX_RUN_CYCLES)
        self.spin.SetMinSize((CYCLE_SPIN_WIDTH, -1))
        self.spin.Bind(wx.EVT_TEXT, self.on_cycle_spin_text)
        cycles_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text.Reparent(simulation_panel)
        self.cycles_completed_text.Reparent(simulation_panel)
        self.run_cycles_button.Reparent(simulation_panel)
        self.live_trace_button.Reparent(simulation_panel)
        self.live_trace_speed_button.Reparent(simulation_panel)
        self.reset_button.Reparent(simulation_panel)
        self.clear_traces_button.Reparent(simulation_panel)
        simulation_sizer.Add(self.text, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        cycles_input_sizer.Add(self.spin, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        cycles_input_sizer.Add(self.live_trace_button, 0, wx.ALIGN_CENTER_VERTICAL)
        cycles_input_sizer.Add(
            self.live_trace_speed_button, 0, wx.ALIGN_CENTER_VERTICAL
        )
        simulation_sizer.Add(cycles_input_sizer, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(
            self.cycles_completed_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6
        )
        simulation_sizer.Add(self.run_cycles_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.reset_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.clear_traces_button, 0, wx.EXPAND | wx.ALL, 6)

        switch_panel, switch_sizer = self.create_section_panel("Switches", "switches")
        switch_panel.SetMinSize((SIDE_PANEL_WIDTH, 230))
        self.switch_rows.Reparent(switch_panel)
        switch_sizer.Add(self.switch_rows, 1, wx.EXPAND | wx.ALL, 6)

        signal_panel, signal_sizer = self.create_section_panel(
            "Available signals", "available_signals"
        )
        self.module_signal_rows.Reparent(signal_panel)
        signal_sizer.Add(self.module_signal_rows, 1, wx.EXPAND | wx.ALL, 6)

        console_panel, console_sizer = self.create_section_panel("Console", "console")
        self.console_box.Reparent(console_panel)
        console_sizer.Add(self.console_box, 1, wx.EXPAND | wx.ALL, 6)

        inspector_sizer = wx.BoxSizer(wx.HORIZONTAL)
        inspector_sizer.Add(
            self.cycle_inspector_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        inspector_sizer.Add(
            self.cycle_inspector_entry,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT | wx.FIXED_MINSIZE,
            8,
        )
        self.cycle_inspector_slider.SetMinSize((120, -1))
        inspector_sizer.Add(self.cycle_inspector_slider, 1, wx.EXPAND)
        self.cycle_inspector_panel.SetSizer(inspector_sizer)
        canvas_sizer.Add(self.canvas, 1, wx.EXPAND)
        canvas_sizer.Add(
            self.cycle_inspector_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5
        )

        self.undo_button.Reparent(self)
        self.redo_button.Reparent(self)
        self.toggle_theme_button.Reparent(self)
        history_theme_sizer.Add(
            self.undo_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        history_theme_sizer.Add(
            self.redo_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8
        )
        history_theme_sizer.AddStretchSpacer()
        history_theme_sizer.Add(self.toggle_theme_button, 0)
        side_sizer.Add(history_theme_sizer, 0, wx.EXPAND | wx.BOTTOM, 8)
        side_sizer.Add(simulation_panel, 0, wx.EXPAND | wx.BOTTOM, 8)
        side_sizer.Add(switch_panel, 1, wx.EXPAND | wx.BOTTOM, 8)

        main_sizer.Add(signal_panel, 0, wx.EXPAND | wx.ALL, 8)
        main_sizer.Add(canvas_sizer, 4, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(side_sizer, 0, wx.EXPAND | wx.ALL, 8)

        root_sizer.Add(main_sizer, 1, wx.EXPAND)
        root_sizer.Add(console_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(root_sizer)
        self.SetMinSize((MIN_FRAME_WIDTH, MIN_FRAME_HEIGHT))
        self.update_switch_rows()
        self.update_module_signal_rows()
        self.apply_theme()
        self.update_file_dependent_controls()
        self.update_section_window_menu()

        minimum_width = MIN_FRAME_WIDTH
        minimum_height = MIN_FRAME_HEIGHT

        # If the starting size is smaller than the fixed minimum, make the
        # window start at the minimum size
        current_size = self.GetSize()
        if current_size.width < minimum_width or current_size.height < minimum_height:
            self.SetSize((minimum_width, minimum_height))

        self.Centre()

    ###############################################################################
    # MENU AND SIMULATION EVENT HANDLERS
    ###############################################################################

    def on_menu(self, event):
        """Handle the event when the user selects a menu item."""
        Id = event.GetId()
        if Id == wx.ID_EXIT:
            self.Close(True)
        if Id == wx.ID_ABOUT:
            wx.MessageBox(
                "Logic Simulator\n\n"
                "A graphical logic circuit simulator for the GF2 Software "
                "project.\n\n"
                "Use it to load circuit definition files, run simulations "
                "cycle by cycle, toggle switch inputs, monitor output "
                "signals, and export waveform traces as PNG or CSV files.",
                "About Logsim",
                wx.ICON_INFORMATION | wx.OK,
            )

    def on_help(self, event):
        """Show a short guide to the main GUI workflow."""
        wx.MessageBox(
            "1. Open a circuit definition file from File > Open.\n"
            "2. Use the Switches panel to set switch inputs LOW or HIGH.\n"
            "3. Add signals from the Available signals panel to display them.\n"
            "4. Choose the number of cycles to run and click Run cycles.\n"
            "5. Use Play live to advance the trace one cycle at a time.\n"
            "6. Use Clear traces to clear the waveform history without "
            "resetting switches.\n"
            "7. Use Reset simulation to restart the circuit and clear all traces.\n"
            "8. Export the waveform as PNG or the trace data as CSV from the "
            "Export menu.",
            "Quick Start",
            wx.ICON_INFORMATION | wx.OK,
        )

    def on_keyboard_shortcuts_help(self, event):
        """Show keyboard shortcuts."""
        wx.MessageBox(
            "F1: quick start help\n"
            "Space: run the selected number of cycles\n"
            "Right arrow: run one cycle\n"
            "Ctrl+Space: play or pause live tracing\n"
            "Ctrl+Z: undo one cycle\n"
            "Ctrl+Y: redo one cycle\n"
            "Ctrl+O: open a circuit file\n"
            "Ctrl+=: zoom in\n"
            "Ctrl+-: zoom out\n"
            "Ctrl+0: reset waveform view\n"
            "Ctrl+I: show or hide cycle inspector\n"
            "Ctrl+Shift+T: switch light/dark mode\n"
            "Ctrl+Shift+P: export waveform as PNG\n"
            "Ctrl+Shift+E: export traces as CSV\n"
            "Ctrl+1: show Available signals panel\n"
            "Ctrl+2: show Simulation panel\n"
            "Ctrl+3: show Switches panel\n"
            "Ctrl+4: show Console panel\n"
            "Delete: clear console messages\n"
            "Ctrl+Q: exit",
            "Keyboard Shortcuts",
            wx.ICON_INFORMATION | wx.OK,
        )

    def on_syntax_help(self, event):
        """Show a short summary of the circuit file syntax."""
        wx.MessageBox(
            "Circuit files describe devices, connections, and monitors.\n\n"
            "Typical sections define:\n"
            "- devices such as switches, gates, clocks, and D-types\n"
            "- connections between device outputs and inputs\n"
            "- monitor signals to record and display\n\n"
            "Signals inside modules are shown with collapsible module names "
            "in the GUI.\n"
            "Use File > Open to load another circuit definition without restarting.",
            "Circuit File Syntax",
            wx.ICON_INFORMATION | wx.OK,
        )

    def on_external_documentation(self, event):
        """Open external documentation in the default browser."""
        if wx.LaunchDefaultBrowser(EXTERNAL_DOCUMENTATION_URL):
            self.set_status("Opened external documentation")
        else:
            self.show_status("Error: could not open external documentation.")

    def run_cycles(self, cycles):
        """Run the network for the requested number of cycles."""
        if cycles <= 0:
            self.show_status("Error: number of cycles must be positive.")
            return False
        if cycles > MAX_RUN_CYCLES:
            self.show_status(
                f"Error: cannot run more than {MAX_RUN_CYCLES} cycles at once."
            )
            return False

        self.redo_history = []

        # Run one cycle at a time and record the monitored signals
        for _ in range(cycles):
            simulation_snapshot = self.get_simulation_snapshot()
            if not self.network.execute_network():
                self.restore_simulation_snapshot(simulation_snapshot)
                self.show_status("Error: network failed to reach a steady state.")
                return False

            self.monitors.record_signals()
            self.simulation_history.append(simulation_snapshot)
            self.cycles_completed += 1
            self.total_cycles_completed += 1

        self.update_cycles_completed_text()
        self.update_history_buttons()
        self.update_cycle_inspector_range()
        return True

    def get_simulation_snapshot(self):
        """Return a snapshot of the simulator state before one cycle runs."""
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

        monitor_traces = {}
        for monitor_name, monitor in self.monitors.monitors_dictionary.items():
            monitor_traces[monitor_name] = list(monitor.trace)

        return {
            "devices": device_snapshots,
            "monitor_traces": monitor_traces,
            "cycles_completed": self.cycles_completed,
            "total_cycles_completed": self.total_cycles_completed,
            "cycle_offset": self.canvas.cycle_offset,
        }

    def restore_simulation_snapshot(self, simulation_snapshot):
        """Restore a snapshot made by get_simulation_snapshot()."""
        for device_snapshot in simulation_snapshot["devices"]:
            device = self.devices.get_device(device_snapshot["device_id"])

            if device is not None:
                device.outputs = dict(device_snapshot["outputs"])
                device.clock_counter = device_snapshot["clock_counter"]
                device.switch_state = device_snapshot["switch_state"]
                device.dtype_memory = device_snapshot["dtype_memory"]

        for monitor_name, trace in simulation_snapshot["monitor_traces"].items():
            monitor = self.monitors.monitors_dictionary.get(monitor_name)
            if monitor is not None:
                monitor.trace = list(trace)

        self.cycles_completed = simulation_snapshot["cycles_completed"]
        self.total_cycles_completed = simulation_snapshot["total_cycles_completed"]
        self.canvas.cycle_offset = simulation_snapshot["cycle_offset"]
        self.update_cycles_completed_text()
        self.update_cycle_inspector_range()

    def update_history_buttons(self):
        """Enable undo and redo buttons only when their history stacks have entries."""
        if hasattr(self, "undo_button"):
            self.undo_button.Enable(bool(self.simulation_history))
        if hasattr(self, "redo_button"):
            self.redo_button.Enable(bool(self.redo_history))

    def get_max_trace_length(self):
        """Return the longest recorded monitor trace length."""
        max_trace_length = 0
        for monitor in self.monitors.monitors_dictionary.values():
            trace_length = len(monitor.trace)
            if trace_length > max_trace_length:
                max_trace_length = trace_length
        return max_trace_length

    def update_cycle_inspector_range(self):
        """Keep the cycle inspector slider in sync with recorded traces."""
        if not hasattr(self, "cycle_inspector_slider"):
            return

        max_trace_length = self.get_max_trace_length()
        if max_trace_length <= 0:
            self.cycle_inspector_slider.SetRange(0, 1)
            self.cycle_inspector_slider.SetValue(0)
            self.cycle_inspector_slider.Enable(False)
            self.cycle_inspector_entry.SetValue("-")
            self.cycle_inspector_entry.Enable(False)
            self.update_cycle_inspector_label_width()
            self.canvas.cycle_inspector_index = 0
            return

        max_index = max_trace_length - 1
        current_index = self.canvas.cycle_inspector_index
        if current_index > max_index:
            current_index = max_index

        if max_trace_length == 1:
            self.cycle_inspector_slider.SetRange(0, 1)
        else:
            self.cycle_inspector_slider.SetRange(1, max_trace_length)
        self.cycle_inspector_slider.SetValue(
            self.cycle_index_to_slider_value(current_index)
        )
        self.cycle_inspector_slider.Enable(True)
        self.cycle_inspector_entry.Enable(True)
        self.canvas.cycle_inspector_index = current_index
        self.update_cycle_inspector_label()

    def update_cycle_inspector_label(self):
        """Show the real cycle number selected by the inspector."""
        selected_cycle = (
            self.canvas.cycle_offset + self.canvas.cycle_inspector_index + 1
        )
        if self.cycle_inspector_entry.GetValue() != str(selected_cycle):
            self.cycle_inspector_entry.SetValue(str(selected_cycle))
        self.update_cycle_inspector_label_width()

    def update_cycle_inspector_label_width(self):
        """Keep the cycle inspector entry width stable."""
        if not hasattr(self, "cycle_inspector_entry") or not hasattr(
            self.cycle_inspector_entry, "SetMinSize"
        ):
            return

        self.cycle_inspector_entry.SetMinSize(
            (CYCLE_INSPECTOR_ENTRY_WIDTH, CYCLE_INSPECTOR_ENTRY_HEIGHT)
        )
        if hasattr(self.cycle_inspector_entry, "SetMaxSize"):
            self.cycle_inspector_entry.SetMaxSize(
                (CYCLE_INSPECTOR_ENTRY_WIDTH, CYCLE_INSPECTOR_ENTRY_HEIGHT)
            )
        if hasattr(self.cycle_inspector_entry, "SetInitialSize"):
            self.cycle_inspector_entry.SetInitialSize(
                (CYCLE_INSPECTOR_ENTRY_WIDTH, CYCLE_INSPECTOR_ENTRY_HEIGHT)
            )
        if hasattr(self, "cycle_inspector_panel"):
            self.cycle_inspector_panel.Layout()

    def cycle_index_to_slider_value(self, cycle_index):
        """Convert a trace list index into the matching slider value."""
        return cycle_index + 1

    def slider_value_to_cycle_index(self, slider_value):
        """Convert the slider value back into a trace list index."""
        if slider_value <= 1:
            return 0
        return slider_value - 1

    def cycle_number_to_cycle_index(self, cycle_number):
        """Convert a displayed cycle number into a trace list index."""
        max_trace_length = self.get_max_trace_length()
        if max_trace_length <= 0:
            return 0

        minimum_cycle = self.canvas.cycle_offset + 1
        maximum_cycle = self.canvas.cycle_offset + max_trace_length
        if cycle_number < minimum_cycle:
            cycle_number = minimum_cycle
        if cycle_number > maximum_cycle:
            cycle_number = maximum_cycle

        return cycle_number - self.canvas.cycle_offset - 1

    def set_cycle_inspector_index(self, cycle_index):
        """Set the inspected cycle and update the slider and entry."""
        max_trace_length = self.get_max_trace_length()
        if max_trace_length <= 0:
            self.update_cycle_inspector_range()
            return

        if cycle_index < 0:
            cycle_index = 0
        if cycle_index >= max_trace_length:
            cycle_index = max_trace_length - 1

        self.canvas.cycle_inspector_index = cycle_index
        self.cycle_inspector_slider.SetValue(
            self.cycle_index_to_slider_value(cycle_index)
        )
        self.update_cycle_inspector_label()

    def show_status(self, message):
        """Display a status message in the GUI."""
        self.append_console_text(message)
        self.set_status(message)

    def append_console_text(self, text):
        """Append console text without leaving a blank trailing line."""
        if not text:
            return

        current_text = self.console_box.GetValue()
        if current_text:
            self.console_box.AppendText("\n")
        self.console_box.AppendText(text)

    def set_status(self, message):
        """Display a short status message in the frame status bar."""
        self.SetStatusText(message)

    def update_cycles_completed_text(self):
        """Update the cycles completed readout."""
        self.cycles_completed_text.SetLabel(
            f"Cycles passed: {self.total_cycles_completed}"
        )

    def on_cycle_spin_text(self, event):
        """Reject typed cycle counts above the per-run maximum."""
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

    def show_max_run_cycles_popup(self):
        """Show the maximum cycles-per-run message."""
        wx.MessageBox(
            f"You can run at most {MAX_RUN_CYCLES} cycles at a time.",
            "Maximum Cycles",
            wx.ICON_WARNING | wx.OK,
        )

    ###############################################################################
    # ERROR MESSAGE HELPERS
    ###############################################################################

    def monitor_error_message(self, error_type):
        """Return a user-facing monitor error message."""
        # Translate monitor error codes into messages suitable for the GUI
        if error_type == self.monitors.NOT_OUTPUT:
            return "signal is not an output"

        if error_type == self.monitors.MONITOR_PRESENT:
            return "signal is already monitored"

        if error_type == self.monitors.DEVICE_ABSENT:
            return "device does not exist"

        return "unknown monitor error"

    def has_loaded_circuit(self):
        """Return True when the GUI has a circuit file loaded."""
        return self.path is not None

    def show_no_loaded_circuit_error(self):
        """Show the shared error for actions that need a loaded circuit."""
        self.show_status("Error: no circuit loaded. Use File > Open to load one.")

    def update_file_dependent_controls(self):
        """Enable simulation controls only when a circuit file is loaded."""
        circuit_loaded = self.has_loaded_circuit()
        for control_name in [
            "run_cycles_button",
            "live_trace_button",
            "live_trace_speed_button",
            "reset_button",
            "clear_traces_button",
        ]:
            if hasattr(self, control_name):
                getattr(self, control_name).Enable(circuit_loaded)

    def on_run_cycles_button(self, event):
        """Run the simulation from its current state."""
        self.stop_live_trace()
        if not self.has_loaded_circuit():
            self.show_no_loaded_circuit_error()
            return

        cycles = self.spin.GetValue()

        # Check the network before running it
        if not self.network.check_network():
            self.show_status("Error: network is incomplete.")
            return

        if self.run_cycles(cycles):
            self.show_status(f"Ran simulation for {cycles} cycles.")
            self.set_status(f"Ran {cycles} cycles")
            self.canvas.render()

    def on_run_one_cycle(self, event):
        """Run the simulation forward by one cycle."""
        self.stop_live_trace()
        if not self.has_loaded_circuit():
            self.show_no_loaded_circuit_error()
            return

        if not self.network.check_network():
            self.show_status("Error: network is incomplete.")
            return

        if self.run_cycles(1):
            self.show_status("Ran simulation for 1 cycle.")
            self.set_status("Ran 1 cycle")
            self.canvas.render()

    def on_toggle_live_trace(self, event):
        """Start or stop live tracing."""
        if self.live_trace_running:
            self.stop_live_trace(show_message=True, keep_paused=True)
        elif self.live_trace_paused:
            self.resume_live_trace()
        else:
            self.start_live_trace()

    def start_live_trace(self):
        """Start automatically advancing the simulation one cycle at a time."""
        if not self.has_loaded_circuit():
            self.show_no_loaded_circuit_error()
            return False

        if not self.network.check_network():
            self.show_status("Error: network is incomplete.")
            return False

        cycles = self.spin.GetValue()
        if cycles <= 0:
            self.show_status("Error: number of cycles must be positive.")
            return False

        self.live_trace_target_cycles = cycles
        self.live_trace_cycles_completed = 0
        self.live_trace_paused = False
        self.live_trace_running = True
        self.live_trace_timer.Start(self.get_live_trace_interval_ms())
        self.update_live_trace_button()
        self.show_status(f"Started live tracing for {cycles} cycles.")
        self.set_status(f"Live tracing: 0/{cycles} cycles")
        return True

    def resume_live_trace(self):
        """Resume a paused live trace without resetting its cycle budget."""
        if not self.has_loaded_circuit():
            self.show_no_loaded_circuit_error()
            return False

        if not self.network.check_network():
            self.show_status("Error: network is incomplete.")
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
            f"Resumed live tracing with {remaining_cycles} cycles remaining."
        )
        self.set_status(
            f"Live tracing: {self.live_trace_cycles_completed}/"
            f"{self.live_trace_target_cycles} cycles"
        )
        return True

    def stop_live_trace(self, show_message=False, keep_paused=False):
        """Stop automatically advancing the simulation."""
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
            self.show_status("Paused live tracing.")
            self.set_status("Live tracing paused")

    def update_live_trace_button(self):
        """Keep the live tracing button label in sync with playback state."""
        if not hasattr(self, "live_trace_button"):
            return

        if self.live_trace_running:
            self.live_trace_button.SetLabel("Pause live")
        else:
            self.live_trace_button.SetLabel("Play live")
        if hasattr(self, "apply_live_trace_button_theme"):
            self.apply_live_trace_button_theme()

    def get_live_trace_interval_ms(self):
        """Return the timer interval for the selected live tracing speed."""
        speed_multiplier = LIVE_TRACE_SPEEDS[self.live_trace_speed_index][1]
        return int(LIVE_TRACE_INTERVAL_MS / speed_multiplier)

    def on_live_trace_speed_button(self, event):
        """Cycle through available live tracing speeds."""
        self.live_trace_speed_index = (self.live_trace_speed_index + 1) % len(
            LIVE_TRACE_SPEEDS
        )
        self.update_live_trace_speed_button()

        if self.live_trace_running and self.live_trace_timer.IsRunning():
            self.live_trace_timer.Start(self.get_live_trace_interval_ms())

    def update_live_trace_speed_button(self):
        """Keep the live tracing speed button in sync with selected speed."""
        if not hasattr(self, "live_trace_speed_button"):
            return

        speed_label = LIVE_TRACE_SPEEDS[self.live_trace_speed_index][0]
        self.live_trace_speed_button.SetLabel(speed_label)
        self.live_trace_speed_button.SetToolTip(f"Live tracing speed: {speed_label}")

        if hasattr(self, "apply_live_trace_speed_button_theme"):
            self.apply_live_trace_speed_button_theme()

    def on_live_trace_timer(self, event):
        """Advance the live trace by one simulation cycle."""
        if not self.network.check_network():
            self.stop_live_trace()
            self.show_status("Error: network is incomplete.")
            return

        if not self.run_cycles(1):
            self.stop_live_trace()
            self.set_status("Live tracing stopped")
            return

        self.live_trace_cycles_completed += 1
        self.set_status(
            f"Live tracing: {self.live_trace_cycles_completed}/"
            f"{self.live_trace_target_cycles} cycles"
        )
        self.canvas.follow_latest_cycle()
        self.canvas.render()

        if self.live_trace_cycles_completed >= self.live_trace_target_cycles:
            completed_cycles = self.live_trace_cycles_completed
            self.stop_live_trace()
            self.live_trace_paused = False
            self.show_status(f"Completed live tracing for {completed_cycles} cycles.")
            self.set_status(f"Completed live tracing for {completed_cycles} cycles.")

    def on_undo_cycle(self, event):
        """Undo the most recent simulation cycle."""
        self.stop_live_trace()
        if not self.simulation_history:
            self.show_status("Error: no simulation cycle to undo.")
            return

        self.redo_history.append(self.get_simulation_snapshot())
        simulation_snapshot = self.simulation_history.pop()
        self.restore_simulation_snapshot(simulation_snapshot)
        self.refresh_switch_rows()
        self.canvas.render()
        self.update_history_buttons()
        self.show_status("Undid 1 cycle.")

    def on_redo_cycle(self, event):
        """Redo the most recently undone simulation cycle."""
        self.stop_live_trace()
        if not self.redo_history:
            self.show_status("Error: no simulation cycle to redo.")
            return

        self.simulation_history.append(self.get_simulation_snapshot())
        simulation_snapshot = self.redo_history.pop()
        self.restore_simulation_snapshot(simulation_snapshot)
        self.refresh_switch_rows()
        self.canvas.render()
        self.update_history_buttons()
        self.show_status("Redid 1 cycle.")

    def on_reset_button(self, event):
        """Reset the simulation state and traces."""
        self.stop_live_trace()
        if not self.has_loaded_circuit():
            self.show_no_loaded_circuit_error()
            return

        # Start again, but do not run any cycles yet
        self.devices.cold_startup()
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        self.total_cycles_completed = 0
        self.simulation_history = []
        self.redo_history = []
        self.canvas.cycle_offset = 0
        self.update_cycles_completed_text()
        self.canvas.reset_view()
        self.update_cycle_inspector_range()
        self.canvas.render()
        self.update_history_buttons()
        self.show_status("Reset simulation.")

    def on_clear_traces(self, event):
        """Clear waveform traces while keeping the selected monitors."""
        self.stop_live_trace()
        if not self.has_loaded_circuit():
            self.show_no_loaded_circuit_error()
            return

        # Only clear what is drawn - do not reset the circuit itself
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        self.simulation_history = []
        self.redo_history = []
        self.canvas.cycle_offset = self.total_cycles_completed
        self.update_cycles_completed_text()
        self.update_cycle_inspector_range()
        self.canvas.render()
        self.update_history_buttons()
        self.show_status("Cleared traces.")

    def on_clear_status(self, event):
        """Clear the console history."""
        self.console_box.SetValue("")
        self.set_status("Ready")

    def on_zoom_in(self, event):
        """Zoom into the waveform display."""
        self.canvas.zoom_in()
        self.set_status("Zoomed in")

    def on_zoom_out(self, event):
        """Zoom out of the waveform display."""
        self.canvas.zoom_out()
        self.set_status("Zoomed out")

    def on_reset_view(self, event):
        """Reset the waveform view."""
        self.canvas.reset_view()
        self.set_status("Reset view")

    def on_toggle_cycle_inspector(self, event):
        """Show or hide the cycle inspector slider."""
        inspector_is_visible = self.cycle_inspector_menu_item.IsChecked()
        self.canvas.cycle_inspector_enabled = inspector_is_visible

        if inspector_is_visible:
            self.update_cycle_inspector_range()
            self.cycle_inspector_panel.Show()
            self.set_status("Shown cycle inspector")
        else:
            self.cycle_inspector_panel.Hide()
            self.set_status("Hidden cycle inspector")

        self.Layout()
        self.canvas.render()

    def on_cycle_inspector_slider(self, event):
        """Update the inspected cycle from the slider."""
        slider_value = self.cycle_inspector_slider.GetValue()
        self.set_cycle_inspector_index(self.slider_value_to_cycle_index(slider_value))
        self.canvas.render()

    def on_cycle_inspector_entry(self, event):
        """Jump to the cycle typed into the cycle inspector."""
        try:
            cycle_number = int(self.cycle_inspector_entry.GetValue())

        except ValueError:
            self.update_cycle_inspector_label()
            if hasattr(event, "Skip"):
                event.Skip()
            return

        self.set_cycle_inspector_index(self.cycle_number_to_cycle_index(cycle_number))
        self.canvas.render()
        if hasattr(event, "Skip"):
            event.Skip()

    def on_toggle_theme(self, event):
        """Switch between light and dark mode."""
        if self.theme_name == "dark":
            self.theme_name = "light"
        else:
            self.theme_name = "dark"
        self.theme = THEMES[self.theme_name]
        self.apply_theme()
        self.show_status(f"Switched to {self.theme_name} mode.")

    def on_close_section(self, event):
        """Hide one side panel section."""
        section_name = event.GetEventObject().GetName()
        self.section_panels[section_name].Hide()
        self.update_section_window_menu()
        self.Layout()

    def on_show_section(self, event):
        """Show or hide one side panel section from the Window menu."""
        menu_id = event.GetId()
        if menu_id == ID_SHOW_AVAILABLE_SIGNALS:
            section_name = "available_signals"
        elif menu_id == ID_SHOW_SIMULATION:
            section_name = "simulation"
        elif menu_id == ID_SHOW_SWITCHES:
            section_name = "switches"
        else:
            section_name = "console"

        self.section_panels[section_name].Show(event.IsChecked())
        self.update_section_window_menu()
        self.Layout()

    def on_open_file(self, event):
        """Load a new circuit definition file into the current GUI."""
        with wx.FileDialog(
            self,
            "Open circuit definition",
            wildcard="Circuit files (*.txt)|*.txt|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_CANCEL:
                self.load_network_file(file_dialog.GetPath())

    def on_export_image(self, event):
        """Save the waveform display as a PNG image."""
        if not self.monitors.monitors_dictionary:
            self.show_status("Error: no monitors to export.")
            return

        with wx.FileDialog(
            self,
            "Export waveform image",
            wildcard="PNG image (*.png)|*.png",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_CANCEL:
                file_path = file_dialog.GetPath()
                if not file_path.lower().endswith(".png"):
                    file_path += ".png"

                if self.canvas.save_image(file_path):
                    self.show_status(f"Exported waveform image to {file_path}.")
                else:
                    self.show_status("Error: could not export waveform image.")

    def on_export_csv(self, event):
        """Save monitor traces as a CSV file."""
        if not self.monitors.monitors_dictionary:
            self.show_status("Error: no monitor traces to export.")
            return

        with wx.FileDialog(
            self,
            "Export monitor traces",
            wildcard="CSV file (*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_CANCEL:
                file_path = file_dialog.GetPath()

                if not file_path.lower().endswith(".csv"):
                    file_path += ".csv"

                try:
                    self.export_traces_to_csv(file_path)
                    self.show_status(f"Exported monitor traces to {file_path}.")

                except OSError as error:
                    self.show_status(f"Error: could not export CSV: {error}.")

    ###############################################################################
    # GUI HELPER FUNCTIONS
    ###############################################################################

    def create_section_panel(self, title, section_name):
        """Create one side panel section with a close button."""
        panel = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SIMPLE)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        body_sizer = wx.BoxSizer(wx.VERTICAL)

        title_label = wx.StaticText(panel, wx.ID_ANY, title)
        close_button = wxbuttons.GenBitmapButton(
            panel, wx.ID_ANY, wx.Bitmap(1, 1), size=(30, 26)
        )
        close_button.SetMinSize((30, 26))
        close_button.SetName(section_name)
        close_button.Bind(wx.EVT_BUTTON, self.on_close_section)

        header_sizer.Add(title_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        if section_name == "console":
            self.clear_status_button.Reparent(panel)
            header_sizer.Add(self.clear_status_button, 0, wx.RIGHT | wx.TOP, 4)
        header_sizer.Add(close_button, 0, wx.RIGHT | wx.TOP, 4)
        panel_sizer.Add(header_sizer, 0, wx.EXPAND)
        panel_sizer.Add(body_sizer, 1, wx.EXPAND)
        panel.SetSizer(panel_sizer)

        self.section_panels[section_name] = panel
        self.section_titles[section_name] = title_label
        self.section_close_buttons[section_name] = close_button
        self.apply_close_button_theme(close_button)
        return panel, body_sizer

    def update_section_window_menu(self):
        """Tick Window menu items for panels that are visible."""
        for section_name, menu_item in self.window_menu_items.items():
            menu_item.Check(self.section_panels[section_name].IsShown())

    def get_system_theme_name(self):
        """Return the OS light/dark appearance when wx exposes it."""
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
        """Apply the current light/dark theme to the GUI."""
        self.theme = THEMES[self.theme_name]
        self.canvas.theme = self.theme
        self.canvas.init = False

        if self.theme_name == "dark":
            self.theme_menu_item.SetItemLabel("Switch to light mode\tctrl+shift+T")
        else:
            self.theme_menu_item.SetItemLabel("Switch to dark mode\tctrl+shift+T")
        if self.theme_name == "dark":
            undo_icon_path = DARK_UNDO_ICON_PATH
            redo_icon_path = DARK_REDO_ICON_PATH
        else:
            undo_icon_path = LIGHT_UNDO_ICON_PATH
            redo_icon_path = LIGHT_REDO_ICON_PATH

        self.apply_history_button_theme(
            self.undo_button, undo_icon_path, "Undo one cycle"
        )
        self.apply_history_button_theme(
            self.redo_button, redo_icon_path, "Redo one cycle"
        )
        self.apply_live_trace_button_theme()
        self.apply_live_trace_speed_button_theme()
        self.apply_theme_toggle_button()

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
        ]

        for control in themed_controls:
            self.apply_theme_to_control(control)

        for section_name, panel in self.section_panels.items():
            panel.SetBackgroundColour(self.theme["frame_bg"])
            self.section_titles[section_name].SetForegroundColour(self.theme["text"])
            self.apply_close_button_theme(self.section_close_buttons[section_name])

        self.update_switch_rows()
        self.update_module_signal_rows()
        self.update_monitor_rows()
        self.update_history_buttons()
        self.Layout()
        self.Refresh()
        self.canvas.Refresh()

    def apply_theme_to_control(self, control):
        """Apply theme colours to a wx control."""
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
        """Return a scaled bitmap for an icon path, or None if it cannot load."""
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

    def apply_history_button_theme(self, button, icon_path, tooltip):
        """Apply icon and colours to an undo or redo button."""
        button.SetBackgroundColour(self.theme["frame_bg"])
        button.SetForegroundColour(self.theme["text"])
        button.SetToolTip(tooltip)

        if hasattr(button, "SetBezelWidth"):
            button.SetBezelWidth(0)
        if hasattr(button, "SetMargins"):
            button.SetMargins(0, 0)
        if hasattr(button, "SetUseFocusIndicator"):
            button.SetUseFocusIndicator(False)

        bitmap = self.load_icon_bitmap(icon_path, 16)
        if bitmap is not None:
            button.SetLabel("")
            button.SetBitmapLabel(bitmap)
        else:
            button.SetLabel(tooltip.split()[0])
            button.SetBitmapLabel(wx.Bitmap(1, 1))

        button.Refresh()

    def apply_theme_toggle_button(self):
        """Apply icon to the day/night mode button."""
        if self.theme_name == "dark":
            icon_path = LIGHT_MODE_ICON_PATH
            fallback_label = "Light"
            tooltip = "Switch to light mode"
        else:
            icon_path = DARK_MODE_ICON_PATH
            fallback_label = "Dark"
            tooltip = "Switch to dark mode"

        bitmap = self.load_icon_bitmap(icon_path, 20)
        self.toggle_theme_button.SetToolTip(tooltip)
        self.toggle_theme_button.SetBackgroundColour(self.theme["button_bg"])
        self.toggle_theme_button.SetForegroundColour(self.theme["text"])

        if hasattr(self.toggle_theme_button, "SetBezelWidth"):
            self.toggle_theme_button.SetBezelWidth(0)
        if hasattr(self.toggle_theme_button, "SetUseFocusIndicator"):
            self.toggle_theme_button.SetUseFocusIndicator(False)

        if bitmap is not None:
            self.toggle_theme_button.SetLabel("")
            self.toggle_theme_button.SetBitmapLabel(bitmap)
        else:
            self.toggle_theme_button.SetLabel(fallback_label)
            self.toggle_theme_button.SetBitmapLabel(wx.Bitmap(1, 1))

        self.toggle_theme_button.Refresh()

    def apply_live_trace_button_theme(self):
        """Apply the current play/pause icon to the live tracing button."""
        if self.live_trace_running:
            fallback_label = "Pause"
            tooltip = "Pause live tracing"
            if self.theme_name == "dark":
                icon_path = DARK_PAUSE_ICON_PATH
            else:
                icon_path = LIGHT_PAUSE_ICON_PATH
        else:
            fallback_label = "Play"
            tooltip = "Start live tracing"
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
        """Apply theme colours to the live tracing speed button."""
        if not hasattr(self, "live_trace_speed_button"):
            return

        speed_label = LIVE_TRACE_SPEEDS[self.live_trace_speed_index][0]
        self.live_trace_speed_button.SetLabel(speed_label)
        self.live_trace_speed_button.SetToolTip(f"Live tracing speed: {speed_label}")
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
        """Apply colours to a small close button."""
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
            button.SetToolTip("Close section")
        else:
            button.SetLabel("X")
            button.SetBitmapLabel(wx.Bitmap(1, 1))

        button.Refresh()
        button.Update()

    def set_collapsible_pane_colours(self, collapsible_pane):
        """Set colours for a native collapsible pane."""
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
        """Colour the two middle buttons and side labels."""
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
        """Update existing switch controls without rebuilding the switch panel."""
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
                    low_button, high_button, low_label, high_label, device.switch_state
                )

            refreshed_low_buttons.add(low_button.GetId())

    def load_network_file(self, path):
        """Parse a circuit file and replace the current simulator state."""
        self.stop_live_trace()
        names = Names()
        devices = Devices(names)
        network = Network(names, devices)
        monitors = Monitors(names, devices, network)
        parser_output = io.StringIO()

        with contextlib.redirect_stdout(parser_output), contextlib.redirect_stderr(
            parser_output
        ):
            scanner = Scanner(path, names)
            parser = Parser(names, devices, network, monitors, scanner)
            parsed_ok = parser.parse_network()

        if not parsed_ok:
            message = f"Could not load circuit file:\n{path}"
            self.show_status(f"Error: could not load {path}.")
            error_text = parser_output.getvalue().strip()
            if error_text:
                self.append_console_text(error_text)
            wx.MessageBox(message, "Invalid circuit file", wx.ICON_ERROR | wx.OK)
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
        self.module_signal_expanded_paths = set()

        self.canvas.devices = devices
        self.canvas.monitors = monitors
        self.canvas.cycle_offset = 0
        self.canvas.reset_view()

        self.update_cycles_completed_text()
        self.update_module_signal_rows()
        self.update_switch_rows()
        self.update_monitor_rows()
        self.update_file_dependent_controls()
        self.update_history_buttons()
        self.update_cycle_inspector_range()
        self.SetTitle(f"Logic Simulator - {path}")
        self.show_status(f"Loaded {path}.")
        self.canvas.render()
        return True

    def export_traces_to_csv(self, file_path):
        """Write monitor traces to a CSV file."""
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
                row = [self.canvas.cycle_offset + cycle + 1]
                for monitor in monitor_list:
                    if cycle < len(monitor.trace):
                        row.append(self.signal_to_csv_text(monitor.trace[cycle]))
                    else:
                        row.append("")
                writer.writerow(row)

    def signal_to_csv_text(self, signal):
        """Return a readable signal value for CSV export."""
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
        """Return a list of all switch device names."""
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
        """Return device and port IDs for an existing signal name."""
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
        """Return GUI-facing names for all output signals in the network."""
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
        """Return internal module output signals as a nested tree."""
        module_signal_groups = {}

        # The parser names internal module signals with ->
        # The GUI keeps that as the internal name but presents it as collapsed
        # module panes so the user doesn't read long arrow separated strings
        for signal_name in self.get_output_signal_names():
            if "->" not in signal_name:
                continue

            add_signal_to_module_tree(module_signal_groups, signal_name, signal_name)

        return module_signal_groups

    def get_top_level_signal_names(self):
        """Return output signals that are not inside an expanded module."""
        signal_names = []

        for signal_name in self.get_output_signal_names():
            if "->" not in signal_name:
                signal_names.append(signal_name)

        return signal_names

    def update_switch_rows(self):
        """Refresh the switch list."""
        # Clear the old rows and rebuild them
        self.switch_rows_sizer.Clear(delete_windows=True)
        self.switch_state_buttons = {}

        switch_names = self.get_switch_names()
        if not switch_names:
            empty_label = wx.StaticText(self.switch_rows, wx.ID_ANY, "No switches")
            empty_label.SetForegroundColour(self.theme["muted_text"])
            self.switch_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
        else:
            for switch_name in switch_names:
                self.add_switch_row(switch_name)

        self.switch_rows.Layout()
        self.switch_rows.FitInside()

    def add_switch_row(self, switch_name):
        """Add one switch row with LOW/HIGH state buttons."""
        switch_id = self.names.query(switch_name)
        device = self.devices.get_device(switch_id)

        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(
            self.switch_rows, wx.ID_ANY, switch_name, style=wx.ST_ELLIPSIZE_END
        )
        label.SetMinSize((0, -1))
        label.SetToolTip(switch_name)
        low_label = wx.StaticText(self.switch_rows, wx.ID_ANY, "LOW")
        low_button = wx.Button(self.switch_rows, wx.ID_ANY, "")
        high_button = wx.Button(self.switch_rows, wx.ID_ANY, "")
        high_label = wx.StaticText(self.switch_rows, wx.ID_ANY, "HIGH")

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

        row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_sizer.Add(low_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
        row_sizer.Add(low_button, 0, wx.ALIGN_CENTER_VERTICAL)
        row_sizer.Add(high_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
        row_sizer.Add(high_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self.switch_rows_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

    def update_module_signal_rows(self):
        """Refresh the available monitor signal list."""
        # The list is rebuilt when the available signals really change
        # Save open/closed pane state first so user navigation is not lost
        self.store_module_signal_pane_state()
        scroll_x, scroll_y = self.module_signal_rows.GetViewStart()
        self.module_signal_rows_sizer.Clear(delete_windows=True)
        self.module_signal_button_names = {}
        self.module_signal_action_buttons = {}
        self.module_signal_pane_paths = {}

        top_level_signal_names = self.get_top_level_signal_names()
        module_signal_groups = self.get_module_signal_groups()

        if not top_level_signal_names and not module_signal_groups:
            empty_label = wx.StaticText(
                self.module_signal_rows, wx.ID_ANY, "No monitorable signals"
            )
            empty_label.SetForegroundColour(self.theme["muted_text"])
            self.module_signal_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
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
        """Add nested module panes and signal rows to a sizer."""
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
            pane_label = module_name + " internals"
            collapsible_pane = wx.CollapsiblePane(
                parent, wx.ID_ANY, pane_label, style=COLLAPSIBLE_PANE_STYLE
            )
            pane_font = collapsible_pane.GetFont()
            pane_font.SetWeight(wx.FONTWEIGHT_BOLD)
            collapsible_pane.SetFont(pane_font)
            self.set_collapsible_pane_colours(collapsible_pane)
            pane = collapsible_pane.GetPane()
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
                wx.EVT_COLLAPSIBLEPANE_CHANGED, self.on_module_signal_pane_changed
            )
            pane_row_sizer = wx.BoxSizer(wx.HORIZONTAL)
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
        """Remember which module panes are expanded before rebuilding."""
        for pane, module_path in self.module_signal_pane_paths.values():
            if pane.IsExpanded():
                self.module_signal_expanded_paths.add(module_path)
            else:
                self.module_signal_expanded_paths.discard(module_path)

    def add_available_signal_row(
        self, parent, parent_sizer, label_text, signal_name, indent=0
    ):
        """Add one available signal row with a monitor action."""
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

        if indent > 0:
            row_sizer.AddSpacer(indent)
        action_column_sizer = wx.BoxSizer(wx.HORIZONTAL)
        action_column_sizer.SetMinSize(
            (SIGNAL_ACTION_COLUMN_WIDTH, SIGNAL_ACTION_BUTTON_SIZE)
        )
        action_column_sizer.Add(action_button, 0, wx.ALIGN_CENTER_VERTICAL)
        row_sizer.Add(action_column_sizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL)
        parent_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

    def update_available_signal_button(self, button, signal_name):
        """Set one available signal button to Add or Remove."""
        # The same button changes job after it is clicked so remove the old
        # event binding before attaching the new add or remove handler
        button.Unbind(wx.EVT_BUTTON)
        button.Unbind(wx.EVT_LEFT_DOWN)

        if self.is_signal_monitored(signal_name):
            action_label = "Remove"
            action_handler = self.on_delete_module_signal_button
            if getattr(self, "theme_name", "light") == "dark":
                icon_path = DARK_REMOVE_ICON_PATH
            else:
                icon_path = LIGHT_REMOVE_ICON_PATH
        else:
            action_label = "Add"
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
        """Return True if a signal name is currently monitored."""
        return signal_name in self.monitors.monitors_dictionary

    def update_monitor_rows(self):
        """Refresh the active monitor list."""
        # Clear the old rows and rebuild them
        self.monitor_rows_sizer.Clear(delete_windows=True)
        self.monitor_button_keys = {}

        if not self.monitors.monitors_dictionary:
            empty_label = wx.StaticText(
                self.monitor_rows, wx.ID_ANY, "No active monitors"
            )
            empty_label.SetForegroundColour(self.theme["muted_text"])
            self.monitor_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
        else:
            for monitor_name in self.monitors.monitors_dictionary:
                row_sizer = wx.BoxSizer(wx.HORIZONTAL)
                label = wx.StaticText(self.monitor_rows, wx.ID_ANY, monitor_name)
                button = wx.Button(self.monitor_rows, wx.ID_ANY, "Remove")
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
        """Remove a monitor from the active monitor list."""
        button_id = event.GetId()
        monitor_name = self.monitor_button_keys[button_id]

        if self.monitors.remove_monitor(monitor_name):
            self.show_status(f"Removed monitor for {monitor_name}.")
        else:
            self.show_status(f"Error: could not remove monitor for {monitor_name}.")

        self.update_monitor_rows()
        self.canvas.render()

    ###############################################################################
    # SWITCH AND MONITOR EVENT HANDLERS
    ###############################################################################

    def on_switch_state_button(self, event):
        """Handle the event when the user clicks LOW or HIGH."""
        switch_name, switch_value, low_button, high_button, low_label, high_label = (
            self.switch_state_buttons[event.GetId()]
        )
        self.update_switch_state_buttons(
            low_button,
            high_button,
            low_label,
            high_label,
            switch_value,
        )
        self.set_switch_value(switch_name, switch_value)

    def set_switch_value(self, switch_name, switch_value):
        """Set one switch to LOW or HIGH."""
        switch_id = self.names.query(switch_name)

        if switch_id is None:
            self.show_status(f"Error: unknown switch '{switch_name}'.")
            return

        # set_switch returns True/False, not one of the Devices error codes
        switch_was_set = self.devices.set_switch(switch_id, switch_value)

        if switch_was_set:
            self.simulation_history = []
            self.redo_history = []
            self.update_history_buttons()
            if switch_value == 1:
                switch_label = "HIGH"
            else:
                switch_label = "LOW"
            self.show_status(f"Set switch {switch_name} to {switch_label}.")
        else:
            self.show_status(f"Error: could not set {switch_name}.")

    def on_module_signal_pane_changed(self, event):
        """Resize the module signal list without resizing the main frame."""
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
        """Add a monitor from the available signal list."""
        button_id = event.GetId()
        signal_name = self.module_signal_button_names[button_id]

        scroll_x, scroll_y = self.module_signal_rows.GetViewStart()
        self.add_monitor_by_name(signal_name, refresh_available_signals=False)

        button = self.module_signal_action_buttons[signal_name]
        self.update_available_signal_button(button, signal_name)
        self.module_signal_rows.Scroll(scroll_x, scroll_y)

    def on_delete_module_signal_button(self, event):
        """Remove a monitor from the available signal list."""
        self.stop_live_trace()
        button_id = event.GetId()
        signal_name = self.module_signal_button_names[button_id]
        scroll_x, scroll_y = self.module_signal_rows.GetViewStart()

        if self.monitors.remove_monitor(signal_name):
            self.simulation_history = []
            self.redo_history = []
            self.update_history_buttons()
            self.update_cycle_inspector_range()
            self.show_status(f"Removed monitor for {signal_name}.")
        else:
            self.show_status(f"Error: {signal_name} is not monitored.")

        # Removing a monitor changes only this row in the available signals
        # panel so update this button instead of rebuilding the full panel
        button = self.module_signal_action_buttons[signal_name]
        self.update_available_signal_button(button, signal_name)
        self.module_signal_rows.Scroll(scroll_x, scroll_y)
        self.canvas.render()

    def add_monitor_by_name(self, monitor_name, refresh_available_signals=True):
        """Add the named signal to the monitor list."""
        self.stop_live_trace()

        if not monitor_name:
            self.show_status("Error: enter a monitor name.")
            return

        signal_ids = self.get_signal_ids(monitor_name)

        if signal_ids is None:
            self.show_status(f"Error: unknown signal '{monitor_name}'.")
            return

        device_id, output_id = signal_ids

        error_type = self.monitors.make_monitor(
            device_id,
            output_id,
            requested_name=monitor_name,
            cycles_completed=self.cycles_completed,
        )

        # make_monitor returns an error code, so decode it if it fails or
        # confirm success if it works
        if error_type == self.monitors.NO_ERROR:
            self.simulation_history = []
            self.redo_history = []
            self.update_history_buttons()
            self.update_cycle_inspector_range()
            self.show_status(f"Added monitor for {monitor_name}.")
            if refresh_available_signals:
                self.update_module_signal_rows()
            self.update_monitor_rows()
        elif error_type == self.monitors.MONITOR_PRESENT:
            self.show_status(
                f"Error: could not add monitor for {monitor_name}. "
                f"{self.monitor_error_message(error_type)}."
            )

        else:
            self.show_status(
                f"Error: could not add monitor for {monitor_name}. "
                f"{self.monitor_error_message(error_type)}."
            )

        self.canvas.render()
