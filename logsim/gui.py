"""Implement the graphical user interface for the Logic Simulator.

Used in the Logic Simulator project to enable the user to run the simulation
or adjust the network properties.

Classes:
--------
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


# This GUI file has two main classes:
# - MyGLCanvas draws the waveform display using OpenGL
# - Gui builds the wxPython controls and connects them to the simulator
#
# Design pattern used in this file:
# - The simulator state lives in Names, Devices, Network and Monitors
# - The GUI should not duplicate that logic - it should only: 
#     - ask those classes for information
#     - display it
#     - call their public methods when the user presses a button / changes a switch
#
# Waveform display:
# - Monitor traces are stored in monitors.monitors_dictionary
# - Each trace is a list of signal values, one value per simulation cycle
# - The canvas converts:
#     - each signal value into a y-position
#     - each cycle number into an x-position
#
# ----- Current features -----
# - Run the simulation for a user-specified number of cycles
# - Reset the simulation to its initial state
# - Clear the waveform traces while keeping the selected monitors
# - Add/remove monitors for any output signal in the network
# - Pan and zoom the waveform display using mouse controls or buttons
# - View status messages in a scrollable box and clear the status history
# - View the number of cycles completed since the last reset
# - Toggle switch values between HIGH and LOW
# - Monitor signals inside modules through collapsible panes, seeing a list of all its signals that can be monitored
# - Option to export the waveform display as an image file
# - Option to export the monitor traces as a CSV file for analysis in Excel etc.
# - Option to change the colour scheme (e.g. dark mode) of the waveform display for better accessibility
# - File upload so that different files can be tested without restarting the program
# - panels are collapsible if user does not want them visible, e.g. the available signals panel can be very long and is not always needed
# - Help menu with instructions on how to use the GUI and explanations of the different features, e.g. the mouse controls for panning and zooming the waveform display

# ----- Features to add -----
# - Slider that shows the value of all signals at a particular cycle that can be dragged back and forth to explore the history of the simulation

# ----- Features that were considered but ultimately not implemented -----
# - Live tracing mode where the display updates in real time as the simulation runs, instead of only after the user clicks 'Run cycles'
#     - This was not implemented because it is more complex and could cause performance issues for large simulations
#     - if there was more time available, it could've been addd as an optional mode that can be toggled on or off by the user
# - multiple tabs for different waveform displays, e.g. to compare the outputs of two different simulations side by side
#     - again, extremely comlex to implement and not a core feature so was not implemented in the interest of time
#     - also just not sure if it would be useful, you could just export both simulations as images and compare them that way - much easier to implement than a whole new tabbed interface within the GUI
# - Add a search box to the available signals panel to make it easier to find the signal you want to monitor
#     - This would be a nice quality of life improvement but was not implemented because the available signals panel is already quite easy to navigate without a search box


# wxPython uses ID numbers to connect shortcuts and menu events to handlers
ID_RUN = wx.NewIdRef()
ID_RUN_ONE = wx.NewIdRef()
ID_UNDO_CYCLE = wx.NewIdRef()
ID_HELP = wx.NewIdRef()
ID_HELP_SHORTCUTS = wx.NewIdRef()
ID_HELP_SYNTAX = wx.NewIdRef()
ID_HELP_EXTERNAL_DOCS = wx.NewIdRef()
ID_CLEAR_STATUS = wx.NewIdRef()
ID_RESET_VIEW = wx.NewIdRef()
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


THEMES = {
    "light": {
        "frame_bg": wx.Colour(240, 240, 240),
        "panel_bg": wx.Colour(255, 255, 255),
        "text": wx.Colour(20, 24, 28),
        "muted_text": wx.Colour(95, 99, 104),
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
    },
    "dark": {
        "frame_bg": wx.Colour(32, 34, 37),
        "panel_bg": wx.Colour(43, 46, 51),
        "text": wx.Colour(232, 234, 237),
        "muted_text": wx.Colour(174, 180, 188),
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
    },
}

EXTERNAL_DOCUMENTATION_URL = ""
LIGHT_CLOSE_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "x_icon_light.png")
DARK_CLOSE_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "x_icon_dark.png")
LIGHT_MODE_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "light_mode.png")
DARK_MODE_ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "dark_mode.png")


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
        super().__init__(parent, -1,
                         attribList=[wxcanvas.WX_GL_RGBA,
                                     wxcanvas.WX_GL_DOUBLEBUFFER,
                                     wxcanvas.WX_GL_DEPTH_SIZE, 16, 0])
        GLUT.glutInit()
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

        # Bind events to the canvas
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.on_mouse)

    def init_gl(self):
        """Configure and initialise the OpenGL context."""
        size = self.GetClientSize()
        self.SetCurrent(self.context)

        # Use window pixels as OpenGL coordinates as this makes drawing easier
        # e.g. x = 10 means about 10 pixels from the left edge, regardless of the window size or zoom level
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

    def render(self, swap_buffers=True):
        """Handle all drawing operations."""
        self.SetCurrent(self.context)
        if not self.init:
            # Configure the viewport, modelview and projection matrices
            self.init_gl()
            self.init = True

        # Clear everything
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        size = self.GetClientSize()

        if not self.monitors.monitors_dictionary:
            self.render_text(
                "No monitor signals to display.",
                10,
                size.height - 30,
            )
        else:
            # The monitor dictionary only stores real traces
            # The waveform display needs heading rows for modules so make a separate list of rows to draw
            display_rows = self.get_monitor_display_rows()

            # Headings are shorter than traces
            # Adding the row heights gives the amount of vertical space needed by the whole display
            display_height = 0
            for display_row in display_rows:
                display_height += display_row["height"]

            max_trace_length = 0
            for monitor in self.monitors.monitors_dictionary.values():
                trace_length = len(monitor.trace)
                if trace_length > max_trace_length:
                    max_trace_length = trace_length

            max_name_length = 0
            for row in display_rows:
                name_length = len(row["label"])
                if name_length > max_name_length:
                    max_name_length = name_length

            # Leave enough space for labels, but not more than 45% of the
            # canvas width
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
                # Compress long traces horizontally instead of drawing
                # off-screen
                step = available_width / max_trace_length
                if step > 20:
                    step = 20
                if step < 4:
                    step = 4

            available_height = size.height - 115
            if available_height < 1:
                available_height = 1

            # Use the total display height, not just the number of rows somodule headings can sit closer to the signals below them
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
            self.draw_cycle_axis(max_trace_length, start_x, top_axis_y, bottom_y, top_y + amplitude, step, self.cycle_offset)

            # headings have height 0.35, signal traces have height 1
            row_position = 0
            for display_row in display_rows:
                low_y = top_y - row_position * row_gap
                high_y = low_y + amplitude

                if display_row["kind"] == "heading":
                    # heading labels a module
                    # It doesn't have a trace so only draw the text and then move down by its height
                    self.render_text(display_row["label"], 10, low_y + amplitude / 2 - 4, colour=self.theme["canvas_muted"])
                    row_position += display_row["height"]
                    continue

                self.render_text(display_row["label"], 10, low_y + amplitude / 2 - 4, colour=self.theme["canvas_text"])
                self.draw_value_axis(start_x, low_y, high_y, step, max_trace_length)

                # Draw the actual signal trace on top of the axes and grid
                GL.glColor3f(*self.theme["canvas_trace"])
                GL.glLineWidth(2.0)
                self.draw_trace(display_row["trace"], start_x, low_y, high_y, step)
                GL.glLineWidth(1.0)
                row_position += display_row["height"]

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
        size = self.GetClientSize()
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
            self.zoom *= (1.0 + (
                event.GetWheelRotation() / (20 * event.GetWheelDelta())))
            # Adjust pan so as to zoom around the mouse position
            self.pan_x -= (self.zoom - old_zoom) * ox
            self.pan_y -= (self.zoom - old_zoom) * oy
            self.limit_top_left_pan()
            self.init = False
        if event.GetWheelRotation() > 0:
            self.zoom /= (1.0 - (
                event.GetWheelRotation() / (20 * event.GetWheelDelta())))
            # Adjust pan so as to zoom around the mouse position
            self.pan_x -= (self.zoom - old_zoom) * ox
            self.pan_y -= (self.zoom - old_zoom) * oy
            self.limit_top_left_pan()
            self.init = False
        self.Refresh()  # triggers the paint event

    def limit_top_left_pan(self):
        """Prevent dragging the waveform past its top-left starting corner."""
        if self.pan_x > 0:
            self.pan_x = 0
        if self.pan_y < 0:
            self.pan_y = 0

    def zoom_at_canvas_centre(self, factor):
        """Zoom around the centre of the canvas."""
        # Find the centre of thw canvas
        size = self.GetClientSize()
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
        old_size = self.GetSize()
        old_min_size = self.GetMinSize()
        export_size = self.get_export_image_size()
        if export_size.width <= 0 or export_size.height <= 0:
            return False

        old_pan_x = self.pan_x
        old_pan_y = self.pan_y
        old_zoom = self.zoom

        try:
            # Make the canvas temporarily large enough for all the trace data
            # the finally block restores the screen view afterwards
            self.SetMinSize(export_size)
            self.SetSize(export_size)

            parent = self.GetParent()
            if parent is not None:
                parent.Layout()
                
            self.Update()
            wx.YieldIfNeeded()
            capture_size = self.GetClientSize()

            self.pan_x = 0
            self.pan_y = 0
            self.zoom = 1
            self.init = False
            self.SetCurrent(self.context)
            self.render(swap_buffers=False)

            # OpenGL pixels are read from the bottom up so need to mirrorthe image before saving
            pixels = GL.glReadPixels(0, 0, capture_size.width, capture_size.height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)

            image = wx.Image(capture_size.width, capture_size.height)
            image.SetData(bytes(pixels))
            image = image.Mirror(False)
            return image.SaveFile(file_path, wx.BITMAP_TYPE_PNG)
        
        finally:
            self.SetMinSize(old_min_size)
            self.SetSize(old_size)

            parent = self.GetParent()
            if parent is not None:
                parent.Layout()

            self.pan_x = old_pan_x
            self.pan_y = old_pan_y
            self.zoom = old_zoom
            self.init = False
            self.SetCurrent(self.context)
            self.render()

    def render_text(self, text, x_pos, y_pos, colour=(0.0, 0.0, 0.0)):
        """Handle text drawing operations."""
        GL.glColor3f(*colour)
        GL.glRasterPos2f(x_pos, y_pos)
        font = GLUT.GLUT_BITMAP_HELVETICA_12

        for character in text:
            if character == '\n':
                y_pos = y_pos - 20
                GL.glRasterPos2f(x_pos, y_pos)
            else:
                GLUT.glutBitmapCharacter(font, ord(character))

    def get_monitor_display_rows(self):
        """Return grouped rows for waveform monitor labels and traces."""
        rows = []
        module_tree = {}

        # First build a small tree from monitor names containing ->
        # e.g. A->B->Q becomes module A inside module B signal Q
        for monitor in self.monitors.monitors_dictionary.values():
            monitor_name = monitor.requested_name

            if "->" not in monitor_name:
                # Top level signals do not need a heading so draw directly as normal trace rows
                rows.append({"kind": "trace",
                             "label": monitor_name,
                             "trace": monitor.trace,
                             "height": 1})
                continue

            add_signal_to_module_tree(module_tree, monitor_name, monitor.trace)

        # now flatten the tree into drawing rows  
        # This keeps the render() method simple because it only has to loop over one list
        self.add_module_monitor_display_rows(rows, module_tree, 0)
        return rows

    def add_module_monitor_display_rows(self, rows, signal_group, depth):
        """Append heading and trace rows for one module signal group."""
        indent = "  " * depth

        for module_name in sorted(signal_group):
            if module_name == "signals_at_this_level":
                continue

            # Headings are given a smaller height
            rows.append({"kind": "heading",
                         "label": indent + module_name,
                         "height": 0.35})

            child_group = signal_group[module_name]
            child_indent = "  " * (depth + 1)

            for signal_name, trace in sorted(child_group.get("signals_at_this_level", [])):
                rows.append({"kind": "trace",
                             "label": child_indent + signal_name,
                             "trace": trace,
                             "height": 1})

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

    def get_cycle_label_interval(self, step):
        """Return a readable cycle label interval for the current scale."""
        # Do not label every cycle, otherwise the numbers overlap and become unreadable - the interval depends on the zoom level
        if step >= 18:
            return 5
        if step >= 10:
            return 10
        if step >= 6:
            return 20
        return 50

    def draw_cycle_axis(self, trace_length, start_x, axis_y, bottom_y, top_y, step, cycle_offset=0):
        """Draw the shared x-axis showing simulation cycles."""
        if trace_length <= 0:
            return

        end_x = start_x + trace_length * step
        label_interval = self.get_cycle_label_interval(step)

        # Minor ticks show every cycle, numbers are shown less often depending on the zoom level
        GL.glColor3f(*self.theme["canvas_axis"])
        self.draw_line(start_x, axis_y, end_x, axis_y)
        self.render_text("Cycles", start_x - 56, axis_y - 4, colour=self.theme["canvas_muted"])

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
                self.render_text(str(cycle_label), x_pos - label_offset, axis_y + 9, colour=self.theme["canvas_text"])

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
        self.render_text("1", axis_x - 18, high_y - 4, colour=self.theme["canvas_muted"])

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

        if self.theme_name == "dark":
            theme_label = "Switch to light mode\tctrl+shift+T"
        else:
            theme_label = "Switch to dark mode\tctrl+shift+T"

        self.theme_menu_item = view_menu.Append(ID_TOGGLE_THEME, theme_label)
        self.window_menu_items = {"available_signals": window_menu.Append(ID_SHOW_AVAILABLE_SIGNALS, "Show Available signals\tctrl+1"),
                                  "simulation": window_menu.Append(ID_SHOW_SIMULATION, "Show Simulation\tctrl+2"),
                                  "switches": window_menu.Append(ID_SHOW_SWITCHES, "Show Switches\tctrl+3"),
                                  "console": window_menu.Append(ID_SHOW_CONSOLE, "Show Console\tctrl+4")}
        
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
        self.reset_button = wx.Button(self, wx.ID_ANY, "Reset simulation")
        self.clear_traces_button = wx.Button(self, wx.ID_ANY, "Clear traces")
        self.console_box = wx.TextCtrl(self, wx.ID_ANY, "", style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.console_box.SetMinSize((-1, 90))
        self.clear_status_button = wx.Button(self, wx.ID_ANY, "Clear console")
        self.toggle_theme_button = wx.Button(self, wx.ID_ANY, "", size=(34, 34))
        self.toggle_theme_button.SetMinSize((34, 34))
        self.switch_rows = wx.ScrolledWindow(self, wx.ID_ANY, style=wx.VSCROLL | wx.BORDER_SIMPLE)
        self.switch_rows.SetScrollRate(0, 10)
        self.switch_rows.SetMinSize((100, 140))
        self.switch_rows_sizer = wx.BoxSizer(wx.VERTICAL)
        self.switch_rows.SetSizer(self.switch_rows_sizer)
        self.switch_state_buttons = {}

        # This is the visible monitor picker
        self.module_signal_rows = wx.ScrolledWindow(self, wx.ID_ANY, style=wx.VSCROLL | wx.BORDER_SIMPLE)
        self.module_signal_rows.SetScrollRate(0, 10)
        self.module_signal_rows.SetMinSize((220, 420))
        self.module_signal_rows_sizer = wx.BoxSizer(wx.VERTICAL)
        self.module_signal_rows.SetSizer(self.module_signal_rows_sizer)

        # These dictionaries connect buttons and panes back to signal names or module paths
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

        # The separate active monitors panel is hidden because the available signal list now shows add or remove next to each signal
        self.monitor_rows.Hide()

        # Bind events to widgets
        self.Bind(wx.EVT_MENU, self.on_menu)
        self.Bind(wx.EVT_MENU, self.on_help, id=ID_HELP)
        self.Bind(wx.EVT_MENU, self.on_keyboard_shortcuts_help, id=ID_HELP_SHORTCUTS)
        self.Bind(wx.EVT_MENU, self.on_syntax_help, id=ID_HELP_SYNTAX)
        self.Bind(wx.EVT_MENU, self.on_external_documentation, id=ID_HELP_EXTERNAL_DOCS)
        self.run_cycles_button.Bind(wx.EVT_BUTTON, self.on_run_cycles_button)
        self.reset_button.Bind(wx.EVT_BUTTON, self.on_reset_button)
        self.clear_traces_button.Bind(wx.EVT_BUTTON, self.on_clear_traces)
        self.clear_status_button.Bind(wx.EVT_BUTTON, self.on_clear_status)
        self.toggle_theme_button.Bind(wx.EVT_BUTTON, self.on_toggle_theme)

        self.Bind(wx.EVT_MENU, self.on_run_cycles_button, id=ID_RUN)
        self.Bind(wx.EVT_MENU, self.on_run_one_cycle, id=ID_RUN_ONE)
        self.Bind(wx.EVT_MENU, self.on_undo_cycle, id=ID_UNDO_CYCLE)
        self.Bind(wx.EVT_MENU, self.on_clear_status, id=ID_CLEAR_STATUS)
        self.Bind(wx.EVT_MENU, self.on_reset_view, id=ID_RESET_VIEW)
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
        accelerators = wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_SPACE, ID_RUN),  # Space: run cycles
            (wx.ACCEL_NORMAL, wx.WXK_RIGHT, ID_RUN_ONE),  # Right arrow: run one cycle
            (wx.ACCEL_NORMAL, wx.WXK_LEFT, ID_UNDO_CYCLE),  # Left arrow: undo one cycle
            (wx.ACCEL_CTRL, ord("O"), ID_OPEN_FILE),  # Ctrl+O: open file
            (wx.ACCEL_CTRL, ord("="), ID_ZOOM_IN),  # Ctrl+=: zoom in
            (wx.ACCEL_CTRL, ord("-"), ID_ZOOM_OUT),  # Ctrl+-: zoom out
            (wx.ACCEL_CTRL, ord("0"), ID_RESET_VIEW),  # Ctrl+0: reset view
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("P"), ID_EXPORT_IMAGE),  # Ctrl+Shift+P: export PNG
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("E"), ID_EXPORT_CSV),  # Ctrl+Shift+E: export CSV
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("T"), ID_TOGGLE_THEME),  # Ctrl+Shift+T: light/dark mode
            (wx.ACCEL_CTRL, ord("1"), ID_SHOW_AVAILABLE_SIGNALS),  # Ctrl+1: show available signals
            (wx.ACCEL_CTRL, ord("2"), ID_SHOW_SIMULATION),  # Ctrl+2: show simulation
            (wx.ACCEL_CTRL, ord("3"), ID_SHOW_SWITCHES),  # Ctrl+3: show switches
            (wx.ACCEL_CTRL, ord("4"), ID_SHOW_CONSOLE),  # Ctrl+4: show console
            (wx.ACCEL_NORMAL, wx.WXK_F1, ID_HELP),  # F1: help
            (wx.ACCEL_CTRL, ord("Q"), wx.ID_EXIT),  # Ctrl+Q: exit
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_CLEAR_STATUS)])  # Delete: clear console
        self.SetAcceleratorTable(accelerators)

        # Configure sizers for layout
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        side_sizer = wx.BoxSizer(wx.VERTICAL)
        self.section_panels = {}
        self.section_titles = {}
        self.section_close_buttons = {}

        simulation_panel, simulation_sizer = self.create_section_panel("Simulation", "simulation")
        self.spin = wx.SpinCtrl(simulation_panel, wx.ID_ANY, "10")
        self.spin.SetRange(1, 100000)
        self.spin.SetMinSize((120, -1))
        self.text.Reparent(simulation_panel)
        self.cycles_completed_text.Reparent(simulation_panel)
        self.run_cycles_button.Reparent(simulation_panel)
        self.reset_button.Reparent(simulation_panel)
        self.clear_traces_button.Reparent(simulation_panel)
        simulation_sizer.Add(self.text, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        simulation_sizer.Add(self.spin, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.cycles_completed_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        simulation_sizer.Add(self.run_cycles_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.reset_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.clear_traces_button, 0, wx.EXPAND | wx.ALL, 6)

        switch_panel, switch_sizer = self.create_section_panel("Switches", "switches")
        switch_panel.SetMinSize((180, 230))
        self.switch_rows.Reparent(switch_panel)
        switch_sizer.Add(self.switch_rows, 1, wx.EXPAND | wx.ALL, 6)

        signal_panel, signal_sizer = self.create_section_panel("Available signals", "available_signals")
        self.module_signal_rows.Reparent(signal_panel)
        signal_sizer.Add(self.module_signal_rows, 1, wx.EXPAND | wx.ALL, 6)

        console_panel, console_sizer = self.create_section_panel("Console", "console")
        self.console_box.Reparent(console_panel)
        console_sizer.Add(self.console_box, 1, wx.EXPAND | wx.ALL, 6)

        self.toggle_theme_button.Reparent(self)
        side_sizer.Add(self.toggle_theme_button, 0, wx.ALIGN_RIGHT | wx.BOTTOM, 8)
        side_sizer.Add(simulation_panel, 0, wx.EXPAND | wx.BOTTOM, 8)
        side_sizer.Add(switch_panel, 1, wx.EXPAND | wx.BOTTOM, 8)

        main_sizer.Add(signal_panel, 0, wx.EXPAND | wx.ALL, 8)
        main_sizer.Add(self.canvas, 4, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(side_sizer, 0, wx.EXPAND | wx.ALL, 8)

        root_sizer.Add(main_sizer, 1, wx.EXPAND)
        root_sizer.Add(console_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(root_sizer)
        self.update_switch_rows()
        self.update_module_signal_rows()
        self.apply_theme()
        self.update_section_window_menu()

        # Prevent the user from shrinking the window so much that the controls or canvas become unusable
        root_sizer.SetSizeHints(self)
        best_size = self.GetBestSize()
        minimum_width = max(best_size.width, 800)
        minimum_height = max(best_size.height, 650)
        self.SetMinSize((minimum_width, minimum_height))

        # If the starting size is smaller than the minimum size, make the window start at the minimum size
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
                "About Logsim", wx.ICON_INFORMATION | wx.OK)

    def on_help(self, event):
        """Show a short guide to the main GUI workflow."""
        wx.MessageBox(
            "1. Open a circuit definition file from File > Open.\n"
            "2. Use the Switches panel to set switch inputs LOW or HIGH.\n"
            "3. Add signals from the Available signals panel to display them.\n"
            "4. Choose the number of cycles to run and click Run cycles.\n"
            "5. Use Clear traces to clear the waveform history without resetting switches.\n"
            "6. Use Reset simulation to restart the circuit and clear all traces.\n"
            "7. Export the waveform as PNG or the trace data as CSV from the Export menu.",
            "Quick Start", wx.ICON_INFORMATION | wx.OK)

    def on_keyboard_shortcuts_help(self, event):
        """Show keyboard shortcuts."""
        wx.MessageBox(
            "F1: quick start help\n"
            "Space: run the selected number of cycles\n"
            "Right arrow: run one cycle\n"
            "Left arrow: undo one cycle\n"
            "Ctrl+O: open a circuit file\n"
            "Ctrl+=: zoom in\n"
            "Ctrl+-: zoom out\n"
            "Ctrl+0: reset waveform view\n"
            "Ctrl+Shift+T: switch light/dark mode\n"
            "Ctrl+Shift+P: export waveform as PNG\n"
            "Ctrl+Shift+E: export traces as CSV\n"
            "Ctrl+1: show Available signals panel\n"
            "Ctrl+2: show Simulation panel\n"
            "Ctrl+3: show Switches panel\n"
            "Ctrl+4: show Console panel\n"
            "Delete: clear console messages\n"
            "Ctrl+Q: exit",
            "Keyboard Shortcuts", wx.ICON_INFORMATION | wx.OK)

    def on_syntax_help(self, event):
        """Show a short summary of the circuit file syntax."""
        wx.MessageBox(
            "Circuit files describe devices, connections, and monitors.\n\n"
            "Typical sections define:\n"
            "- devices such as switches, gates, clocks, and D-types\n"
            "- connections between device outputs and inputs\n"
            "- monitor signals to record and display\n\n"
            "Signals inside modules are shown with collapsible module names in the GUI.\n"
            "Use File > Open to load another circuit definition without restarting.",
            "Circuit File Syntax", wx.ICON_INFORMATION | wx.OK)

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

        # Run one cycle at a time and record the monitored signals
        for _ in range(cycles):
            simulation_snapshot = self.get_simulation_snapshot()
            if not self.network.execute_network():
                self.restore_simulation_snapshot(simulation_snapshot)
                self.show_status(
                    "Error: network failed to reach a steady state."
                )
                return False

            self.monitors.record_signals()
            self.simulation_history.append(simulation_snapshot)
            self.cycles_completed += 1
            self.total_cycles_completed += 1

        self.update_cycles_completed_text()
        return True

    def get_simulation_snapshot(self):
        """Return a snapshot of the simulator state before one cycle runs."""
        device_snapshots = []
        for device in self.devices.devices_list:
            device_snapshots.append({
                "device_id": device.device_id,
                "outputs": dict(device.outputs),
                "clock_counter": device.clock_counter,
                "switch_state": device.switch_state,
                "dtype_memory": device.dtype_memory})

        monitor_traces = {}
        for monitor_name, monitor in self.monitors.monitors_dictionary.items():
            monitor_traces[monitor_name] = list(monitor.trace)

        return {
            "devices": device_snapshots,
            "monitor_traces": monitor_traces,
            "cycles_completed": self.cycles_completed,
            "total_cycles_completed": self.total_cycles_completed,
            "cycle_offset": self.canvas.cycle_offset}

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

    def show_status(self, message):
        """Display a status message in the GUI."""
        self.console_box.AppendText(message + "\n")
        self.set_status(message)

    def set_status(self, message):
        """Display a short status message in the frame status bar."""
        self.SetStatusText(message)

    def update_cycles_completed_text(self):
        """Update the cycles completed readout."""
        self.cycles_completed_text.SetLabel(f"Cycles passed: {self.total_cycles_completed}")

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

    def on_run_cycles_button(self, event):
        """Run the simulation from its current state."""
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
        if not self.network.check_network():
            self.show_status("Error: network is incomplete.")
            return

        if self.run_cycles(1):
            self.show_status("Ran simulation for 1 cycle.")
            self.set_status("Ran 1 cycle")
            self.canvas.render()

    def on_undo_cycle(self, event):
        """Undo the most recent simulation cycle."""
        if not self.simulation_history:
            self.show_status("Error: no simulation cycle to undo.")
            return

        simulation_snapshot = self.simulation_history.pop()
        self.restore_simulation_snapshot(simulation_snapshot)
        self.update_switch_rows()
        self.canvas.render()
        self.show_status("Undid 1 cycle.")

    def on_reset_button(self, event):
        """Reset the simulation state and traces."""
        # Start again, but do not run any cycles yet
        self.devices.cold_startup()
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        self.total_cycles_completed = 0
        self.simulation_history = []
        self.canvas.cycle_offset = 0
        self.update_cycles_completed_text()
        self.canvas.reset_view()
        self.canvas.render()
        self.show_status("Reset simulation.")

    def on_clear_traces(self, event):
        """Clear waveform traces while keeping the selected monitors."""
        # Only clear what is drawn - do not reset the circuit itself
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        self.simulation_history = []
        self.canvas.cycle_offset = self.total_cycles_completed
        self.update_cycles_completed_text()
        self.canvas.render()
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
        """Show one hidden side panel section from the Window menu."""
        menu_id = event.GetId()
        if menu_id == ID_SHOW_AVAILABLE_SIGNALS:
            section_name = "available_signals"
        elif menu_id == ID_SHOW_SIMULATION:
            section_name = "simulation"
        elif menu_id == ID_SHOW_SWITCHES:
            section_name = "switches"
        else:
            section_name = "console"

        self.section_panels[section_name].Show()
        self.section_close_buttons[section_name].SetLabel("X")
        self.section_close_buttons[section_name].Refresh()
        self.update_section_window_menu()
        self.Layout()

    def on_open_file(self, event):
        """Load a new circuit definition file into the current GUI."""
        with wx.FileDialog(self, "Open circuit definition", wildcard="Circuit files (*.txt)|*.txt|All files (*.*)|*.*", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_CANCEL:
                self.load_network_file(file_dialog.GetPath())

    def on_export_image(self, event):
        """Save the waveform display as a PNG image."""
        if not self.monitors.monitors_dictionary:
            self.show_status("Error: no monitors to export.")
            return

        with wx.FileDialog(self, "Export waveform image", wildcard="PNG image (*.png)|*.png", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as file_dialog:
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

        with wx.FileDialog(self, "Export monitor traces", wildcard="CSV file (*.csv)|*.csv", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as file_dialog:
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
        close_button = wxbuttons.GenBitmapButton(panel, wx.ID_ANY, wx.Bitmap(1, 1), size=(30, 26))
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
        """Enable Window menu items only for hidden sections."""
        for section_name, menu_item in self.window_menu_items.items():
            menu_item.Enable(not self.section_panels[section_name].IsShown())

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
        self.apply_theme_toggle_button()

        self.SetBackgroundColour(self.theme["frame_bg"])
        self.apply_theme_to_text_box(self.console_box)
        self.menu_bar.SetBackgroundColour(self.theme["frame_bg"])
        self.menu_bar.SetForegroundColour(self.theme["text"])

        themed_controls = [self.text,
                           self.spin,
                           self.cycles_completed_text,
                           self.run_cycles_button,
                           self.reset_button,
                           self.clear_traces_button,
                           self.clear_status_button,
                           self.toggle_theme_button,
                           self.switch_rows,
                           self.module_signal_rows,
                           self.monitor_rows]

        for control in themed_controls:
            self.apply_theme_to_control(control)

        for section_name, panel in self.section_panels.items():
            panel.SetBackgroundColour(self.theme["frame_bg"])
            self.section_titles[section_name].SetForegroundColour(self.theme["text"])
            self.apply_close_button_theme(self.section_close_buttons[section_name])

        self.update_switch_rows()
        self.update_module_signal_rows()
        self.update_monitor_rows()
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
        if not os.path.exists(icon_path):
            return None

        image = wx.Image(icon_path, wx.BITMAP_TYPE_ANY)
        if not image.IsOk():
            return None

        image = image.Scale(size, size, wx.IMAGE_QUALITY_HIGH)
        return wx.Bitmap(image)

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

        if bitmap is not None:
            self.toggle_theme_button.SetLabel("")
            self.toggle_theme_button.SetBitmap(bitmap)
        else:
            self.toggle_theme_button.SetLabel(fallback_label)
            self.toggle_theme_button.SetBitmap(wx.NullBitmap)

        self.toggle_theme_button.Refresh()

    def apply_close_button_theme(self, button):
        """Apply colours to a small close button"""
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
        # On Windows OS at least, the header seems to stay light even in dark mode so here the text is made dark as its is easier to read
        # Need to test on more platforms to see if this is a general issue with wx or just a quirk of Windows
        if self.theme_name == "dark" and wx.Platform == "__WXMSW__":
            header_text_colour = wx.Colour(0, 0, 0)
        else:
            header_text_colour = self.theme["text"]

        collapsible_pane.SetForegroundColour(header_text_colour)
        for child in collapsible_pane.GetChildren():
            child.SetForegroundColour(header_text_colour)
            child.Refresh()

        collapsible_pane.Refresh()

    def update_switch_state_buttons(self, low_button, high_button, low_label, high_label, switch_value):
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

    def load_network_file(self, path):
        """Parse a circuit file and replace the current simulator state."""
        names = Names()
        devices = Devices(names)
        network = Network(names, devices)
        monitors = Monitors(names, devices, network)
        parser_output = io.StringIO()

        with contextlib.redirect_stdout(parser_output), contextlib.redirect_stderr(parser_output):
            scanner = Scanner(path, names)
            parser = Parser(names, devices, network, monitors, scanner)
            parsed_ok = parser.parse_network()

        if not parsed_ok:
            message = f"Could not load circuit file:\n{path}"
            self.show_status(f"Error: could not load {path}.")
            error_text = parser_output.getvalue().strip()
            if error_text:
                self.console_box.AppendText(error_text + "\n")
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
        self.module_signal_expanded_paths = set()

        self.canvas.devices = devices
        self.canvas.monitors = monitors
        self.canvas.cycle_offset = 0
        self.canvas.reset_view()

        self.update_cycles_completed_text()
        self.update_module_signal_rows()
        self.update_switch_rows()
        self.update_monitor_rows()
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
        # now can also be a net 
        device_id = self.names.query(device_name)
        if device_id is None:
            return None

        port_id = None
        if number_of_parts == 2:
            port_name = name_parts[1]
            port_id = self.names.query(port_name)
            if port_id is None:
                return None

        # Resolve the net to its driver based on net_driver_dict
        if port_id is None and device_id in self.net_driver_dict:
            driver_signal = self.net_driver_dict[device_id]
            return [driver_signal.main_id, driver_signal.port_id]

        return [device_id, port_id]

    def get_output_signal_names(self):
        """Return names for all output signals in the network."""
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
                signal_names.append(signal_name)

        return signal_names

    def get_module_signal_groups(self):
        """Return internal module output signals as a nested tree."""
        module_signal_groups = {}

        # The parser names internal module signals with ->
        # The GUI keeps that as the internal name but presents it as collapsed module panes so the user doesn't read long arrow separated strings
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
        label = wx.StaticText(self.switch_rows, wx.ID_ANY, switch_name)
        low_label = wx.StaticText(self.switch_rows, wx.ID_ANY, "LOW")
        low_button = wx.Button(self.switch_rows, wx.ID_ANY, "")
        high_button = wx.Button(self.switch_rows, wx.ID_ANY, "")
        high_label = wx.StaticText(self.switch_rows, wx.ID_ANY, "HIGH")

        low_button.SetMinSize((22, 18))
        high_button.SetMinSize((22, 18))
        low_button.Bind(wx.EVT_BUTTON, self.on_switch_state_button)
        high_button.Bind(wx.EVT_BUTTON, self.on_switch_state_button)

        self.switch_state_buttons[low_button.GetId()] = (switch_name, 0, low_button, high_button, low_label,high_label)
        self.switch_state_buttons[high_button.GetId()] = (switch_name, 1, low_button, high_button, low_label,high_label)

        label.SetForegroundColour(self.theme["text"])
        label_font = label.GetFont()
        label_font.SetWeight(wx.FONTWEIGHT_BOLD)
        label.SetFont(label_font)
        self.update_switch_state_buttons(low_button, high_button, low_label,high_label, device.switch_state)

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
            empty_label = wx.StaticText(self.module_signal_rows, wx.ID_ANY, "No monitorable signals")
            empty_label.SetForegroundColour(self.theme["muted_text"])
            self.module_signal_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
        else:
            for signal_name in sorted(top_level_signal_names):
                self.add_available_signal_row(self.module_signal_rows, self.module_signal_rows_sizer, signal_name, signal_name, indent=0)

            self.add_module_signal_group_rows(self.module_signal_rows, self.module_signal_rows_sizer, module_signal_groups,())

        self.module_signal_rows.Layout()
        self.module_signal_rows.FitInside()
        self.module_signal_rows.Scroll(scroll_x, scroll_y)

    def add_module_signal_group_rows(self, parent, parent_sizer, signal_group, parent_path):
        """Add nested module panes and signal rows to a sizer."""
        for signal_name, full_signal_name in sorted(signal_group.get("signals_at_this_level", [])):
            self.add_available_signal_row(parent, parent_sizer, signal_name, full_signal_name, indent=32)

        for module_name in sorted(signal_group):
            if module_name == "signals_at_this_level":
                continue

            collapsible_pane = wx.CollapsiblePane(parent, wx.ID_ANY, module_name)
            self.set_collapsible_pane_colours(collapsible_pane)
            pane = collapsible_pane.GetPane()
            pane.SetBackgroundColour(self.theme["panel_bg"])
            pane_sizer = wx.BoxSizer(wx.VERTICAL)
            module_path = parent_path + (module_name,)

            self.add_module_signal_group_rows(pane, pane_sizer, signal_group[module_name], module_path)

            pane.SetSizer(pane_sizer)

            self.module_signal_pane_paths[collapsible_pane.GetId()] = (collapsible_pane, module_path)
            if module_path in self.module_signal_expanded_paths:
                collapsible_pane.Collapse(False)

            collapsible_pane.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.on_module_signal_pane_changed)
            parent_sizer.Add(collapsible_pane, 0, wx.EXPAND | wx.ALL, 4)

    def store_module_signal_pane_state(self):
        """Remember which module panes are expanded before rebuilding."""
        for pane, module_path in self.module_signal_pane_paths.values():
            if pane.IsExpanded():
                self.module_signal_expanded_paths.add(module_path)
            else:
                self.module_signal_expanded_paths.discard(module_path)

    def add_available_signal_row(self, parent, parent_sizer, label_text, signal_name, indent=0):
        """Add one available signal row with a monitor action."""
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(parent, wx.ID_ANY, label_text)
        label.SetForegroundColour(self.theme["text"])

        # row always has one button
        # Its label and handler are set by update_available_signal_button() depending on whether the signal is already monitored
        action_button = wx.Button(parent, wx.ID_ANY, "")
        self.module_signal_button_names[action_button.GetId()] = signal_name
        self.module_signal_action_buttons[signal_name] = action_button
        self.update_available_signal_button(action_button, signal_name)

        if indent > 0:
            row_sizer.AddSpacer(indent)
        row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row_sizer.Add(action_button, 0)
        parent_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

    def update_available_signal_button(self, button, signal_name):
        """Set one available signal button to Add or Remove."""
        # The same button changes job after it is clicked so remove the old event binding before attaching the new add or remove handler
        button.Unbind(wx.EVT_BUTTON)
        button.Unbind(wx.EVT_LEFT_DOWN)

        if self.is_signal_monitored(signal_name):
            action_label = "Remove"
            action_handler = self.on_delete_module_signal_button
            button_background = self.theme["toggle_off"]
        else:
            action_label = "Add"
            action_handler = self.on_add_module_signal_button
            button_background = self.theme["toggle_on"]

        button.SetLabel(action_label)
        button.SetBackgroundColour(button_background)
        button.SetForegroundColour(self.theme["toggle_text"])
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
            empty_label = wx.StaticText(self.monitor_rows, wx.ID_ANY, "No active monitors")
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
        switch_name, switch_value, low_button, high_button, low_label, high_label = self.switch_state_buttons[event.GetId()]
        self.update_switch_state_buttons(low_button, high_button, low_label,high_label, switch_value,)
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
            if switch_value == 1:
                switch_label = "HIGH"
            else:
                switch_label = "LOW"
            self.show_status(f"Set switch {switch_name} to {switch_label}.")
        else:
            self.show_status(f"Error: could not set {switch_name}.")

    def on_module_signal_pane_changed(self, event):
        """Resize the module signal list when a module is expanded."""
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
        event.Skip()

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
        button_id = event.GetId()
        signal_name = self.module_signal_button_names[button_id]
        scroll_x, scroll_y = self.module_signal_rows.GetViewStart()

        if self.monitors.remove_monitor(signal_name):
            self.simulation_history = []
            self.show_status(f"Removed monitor for {signal_name}.")
        else:
            self.show_status(f"Error: {signal_name} is not monitored.")

        # Removing a monitor changes only this row in the available signals panel so update this button instead of rebuilding the full panel
        button = self.module_signal_action_buttons[signal_name]
        self.update_available_signal_button(button, signal_name)
        self.module_signal_rows.Scroll(scroll_x, scroll_y)
        self.canvas.render()

    def add_monitor_by_name(self, monitor_name, refresh_available_signals=True):
        """Add the named signal to the monitor list."""

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

