"""Implement the graphical user interface for the Logic Simulator.

Used in the Logic Simulator project to enable the user to run the simulation
or adjust the network properties.

Classes:
--------
MyGLCanvas - handles all canvas drawing operations.
Gui - configures the main window and all the widgets.
"""
import wx
import wx.glcanvas as wxcanvas
from OpenGL import GL, GLUT

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

# ----- Features to add -----
# - File upload so that different files can be tested without restarting the program
# - Slider that shows the value of all signals at a particular cycle that can be dragged back and forth to explore the history of the simulation
# - Option to export the waveform display as an image file
# - Option to export the monitor traces as a CSV file for analysis in Excel etc.
# - Option to change the colour scheme (e.g. dark mode) of the waveform display for better accessibility
# - Live tracing mode where the display updates in real time as the simulation runs, instead of only after the user clicks 'Run cycles'
# - Make panels collapsible if user does not want them visible, e.g. the available signals panel can be very long and is not always needed


# wxPython uses ID numbers to connect shortcuts and menu events to handlers
ID_RUN = wx.NewIdRef()
ID_CLEAR_STATUS = wx.NewIdRef()
ID_RESET_VIEW = wx.NewIdRef()


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

        # Initialise variables for panning
        self.pan_x = 0
        self.pan_y = 0
        self.last_mouse_x = 0  # previous mouse x position
        self.last_mouse_y = 0  # previous mouse y position

        # Initialise variables for zooming
        self.zoom = 1

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
        GL.glClearColor(1.0, 1.0, 1.0, 0.0)
        GL.glViewport(0, 0, size.width, size.height)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(0, size.width, 0, size.height, -1, 1)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glTranslated(self.pan_x, self.pan_y, 0.0)
        GL.glScaled(self.zoom, self.zoom, self.zoom)

    def render(self):
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
            self.draw_cycle_axis(max_trace_length, start_x, top_axis_y, bottom_y, top_y + amplitude, step)

            # headings have height 0.35, signal traces have height 1
            row_position = 0
            for display_row in display_rows:
                low_y = top_y - row_position * row_gap
                high_y = low_y + amplitude

                if display_row["kind"] == "heading":
                    # heading labels a module
                    # It doesn't have a trace so only draw the text and then move down by its height
                    self.render_text(display_row["label"], 10, low_y + amplitude / 2 - 4, colour=(0.36, 0.40, 0.46))
                    row_position += display_row["height"]
                    continue

                self.render_text(display_row["label"], 10, low_y + amplitude / 2 - 4, colour=(0.12, 0.14, 0.16))
                self.draw_value_axis(start_x, low_y, high_y, step, max_trace_length)

                # Draw the actual signal trace on top of the axes and grid
                GL.glColor3f(0.11, 0.30, 0.85)
                GL.glLineWidth(2.0)
                self.draw_trace(display_row["trace"], start_x, low_y, high_y, step)
                GL.glLineWidth(1.0)
                row_position += display_row["height"]

        # We have been drawing to the back buffer, flush the graphics pipeline
        # and swap the back buffer to the front
        GL.glFlush()
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
            self.init = False
        if event.GetWheelRotation() < 0:
            self.zoom *= (1.0 + (
                event.GetWheelRotation() / (20 * event.GetWheelDelta())))
            # Adjust pan so as to zoom around the mouse position
            self.pan_x -= (self.zoom - old_zoom) * ox
            self.pan_y -= (self.zoom - old_zoom) * oy
            self.init = False
        if event.GetWheelRotation() > 0:
            self.zoom /= (1.0 - (
                event.GetWheelRotation() / (20 * event.GetWheelDelta())))
            # Adjust pan so as to zoom around the mouse position
            self.pan_x -= (self.zoom - old_zoom) * ox
            self.pan_y -= (self.zoom - old_zoom) * oy
            self.init = False
        self.Refresh()  # triggers the paint event

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

    def draw_cycle_axis(self, trace_length, start_x, axis_y, bottom_y, top_y, step):
        """Draw the shared x-axis showing simulation cycles."""
        if trace_length <= 0:
            return

        end_x = start_x + trace_length * step
        label_interval = self.get_cycle_label_interval(step)

        # Minor ticks show every cycle, numbers are shown less often depending on the zoom level
        GL.glColor3f(0.42, 0.46, 0.52)
        self.draw_line(start_x, axis_y, end_x, axis_y)
        self.render_text("Cycles", start_x - 56, axis_y - 4, colour=(0.36, 0.40, 0.46))

        for cycle in range(0, trace_length + 1):
            x_pos = start_x + cycle * step

            # If the cycle divides exactly by label_interval, draw its number
            remainder = cycle % label_interval
            if remainder == 0:
                is_labelled_tick = True
            else:
                is_labelled_tick = False

            if is_labelled_tick:
                GL.glColor3f(0.83, 0.86, 0.90)
            else:
                GL.glColor3f(0.92, 0.94, 0.96)
            self.draw_line(x_pos, bottom_y - 8, x_pos, top_y + 4)

            GL.glColor3f(0.42, 0.46, 0.52)
            if is_labelled_tick:
                tick_height = 5
            else:
                tick_height = 3
            self.draw_line(x_pos, axis_y - tick_height, x_pos, axis_y + tick_height)

            if is_labelled_tick:
                if cycle < 10:
                    label_offset = 3
                else:
                    label_offset = 7
                self.render_text(str(cycle), x_pos - label_offset, axis_y + 9, colour=(0.18, 0.20, 0.22))

    def draw_value_axis(self, start_x, low_y, high_y, step, trace_length):
        """Draw the per-trace y-axis showing LOW/HIGH values."""
        axis_x = start_x - 10
        end_x = start_x + trace_length * step

        # Each trace is binary, so the y-axis only needs 0 and 1
        GL.glColor3f(0.88, 0.90, 0.93)
        self.draw_line(start_x, low_y, end_x, low_y)
        self.draw_line(start_x, high_y, end_x, high_y)

        GL.glColor3f(0.48, 0.52, 0.58)
        self.draw_line(axis_x, low_y, axis_x, high_y)
        self.draw_line(axis_x - 4, low_y, axis_x + 4, low_y)
        self.draw_line(axis_x - 4, high_y, axis_x + 4, high_y)
        self.render_text("0", axis_x - 18, low_y - 4, colour=(0.36, 0.40, 0.46))
        self.render_text("1", axis_x - 18, high_y - 4, colour=(0.36, 0.40, 0.46))

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


        # Number of cycles currently shown on the trace display
        self.cycles_completed = 0

        # Total cycles since the last reset
        self.total_cycles_completed = 0

        # Configure the file menu
        file_menu = wx.Menu()
        menu_bar = wx.MenuBar()
        file_menu.Append(wx.ID_ABOUT, "&About")
        file_menu.Append(wx.ID_EXIT, "&Exit")
        menu_bar.Append(file_menu, "&File")
        self.SetMenuBar(menu_bar)
        self.CreateStatusBar()
        self.set_status("Ready")

        # Canvas for drawing signals
        self.canvas = MyGLCanvas(self, devices, monitors)
        self.canvas.SetMinSize((500, 420))

        # Configure the widgets
        self.text = wx.StaticText(self, wx.ID_ANY, "Cycles to run")
        self.spin = wx.SpinCtrl(self, wx.ID_ANY, "10")
        self.spin.SetRange(1, 100000)
        self.cycles_completed_text = wx.StaticText(self, wx.ID_ANY, "Cycles passed: 0")
        self.run_cycles_button = wx.Button(self, wx.ID_ANY, "Run cycles")
        self.reset_button = wx.Button(self, wx.ID_ANY, "Reset simulation")
        self.clear_traces_button = wx.Button(self, wx.ID_ANY, "Clear traces")
        self.status_box = wx.TextCtrl(self, wx.ID_ANY, "", style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.status_box.SetMinSize((-1, 90))
        self.clear_status_button = wx.Button(self, wx.ID_ANY, "Clear status")
        self.switch_rows = wx.ScrolledWindow(self, wx.ID_ANY, style=wx.VSCROLL | wx.BORDER_SIMPLE)
        self.switch_rows.SetScrollRate(0, 10)
        self.switch_rows.SetMinSize((-1, 140))
        self.switch_rows_sizer = wx.BoxSizer(wx.VERTICAL)
        self.switch_rows.SetSizer(self.switch_rows_sizer)

        # ComboBox lets users pick a valid output signal
        self.monitor_box = wx.ComboBox(
            self,
            wx.ID_ANY,
            choices=self.get_output_signal_names(),
            style=wx.CB_READONLY,
        )
        if self.monitor_box.GetCount() > 0:
            self.monitor_box.SetSelection(0)
        self.add_monitor_button = wx.Button(self, wx.ID_ANY, "Add Monitor")

        # The old ComboBox and add button are hidden rather than deleted
        # add_monitor() already uses them so the new 'Available signals' panel can reuse that tested code path by setting the comboBox value first
        self.monitor_box.Hide()
        self.add_monitor_button.Hide()

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

        # When add/remove is clicked from the available signals panel, only the clicked button should change
        # Rebuilding the full panel caused visible flicker so this flag skips that rebuild during add_monitor()
        self.suppress_available_signal_refresh = False

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

        self.zoom_in_button = wx.Button(self, wx.ID_ANY, "Zoom in")
        self.zoom_out_button = wx.Button(self, wx.ID_ANY, "Zoom out")
        self.reset_view_button = wx.Button(self, wx.ID_ANY, "Reset view")

        # Bind events to widgets
        self.Bind(wx.EVT_MENU, self.on_menu)
        self.run_cycles_button.Bind(wx.EVT_BUTTON, self.on_run_cycles_button)
        self.reset_button.Bind(wx.EVT_BUTTON, self.on_reset_button)
        self.clear_traces_button.Bind(wx.EVT_BUTTON, self.on_clear_traces)
        self.clear_status_button.Bind(wx.EVT_BUTTON, self.on_clear_status)
        self.add_monitor_button.Bind(wx.EVT_BUTTON, self.on_add_monitor_button)
        self.zoom_in_button.Bind(wx.EVT_BUTTON, self.on_zoom_in)
        self.zoom_out_button.Bind(wx.EVT_BUTTON, self.on_zoom_out)
        self.reset_view_button.Bind(wx.EVT_BUTTON, self.on_reset_view)

        self.Bind(wx.EVT_MENU, self.on_run_cycles_button, id=ID_RUN)
        self.Bind(wx.EVT_MENU, self.on_clear_status, id=ID_CLEAR_STATUS)
        self.Bind(wx.EVT_MENU, self.on_reset_view, id=ID_RESET_VIEW)

        # Keyboard shortcuts call the same handlers as the buttons
        accelerators = wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_SPACE, ID_RUN),  # Space: run cycles
            (wx.ACCEL_CTRL, ord("R"), ID_RESET_VIEW),  # Ctrl+R: reset view
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_CLEAR_STATUS)])  # Delete: clear status
        self.SetAcceleratorTable(accelerators)

        # Configure sizers for layout
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        side_sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_side_sizer = wx.BoxSizer(wx.VERTICAL)
        right_side_sizer = wx.BoxSizer(wx.VERTICAL)

        simulation_sizer = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Simulation"), wx.VERTICAL)
        simulation_sizer.Add(self.text, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        simulation_sizer.Add(self.spin, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.cycles_completed_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        simulation_sizer.Add(self.run_cycles_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.reset_button, 0, wx.EXPAND | wx.ALL, 6)
        simulation_sizer.Add(self.clear_traces_button, 0, wx.EXPAND | wx.ALL, 6)

        switch_sizer = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Switches"), wx.VERTICAL)
        switch_sizer.Add(self.switch_rows, 1, wx.EXPAND | wx.ALL, 6)

        signal_sizer = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Available signals"), wx.VERTICAL)
        signal_sizer.Add(self.module_signal_rows, 1, wx.EXPAND | wx.ALL, 6)

        zoom_sizer = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "View"), wx.VERTICAL)
        zoom_sizer.Add(self.zoom_in_button, 0, wx.EXPAND | wx.ALL, 6)
        zoom_sizer.Add(self.zoom_out_button, 0, wx.EXPAND | wx.ALL, 6)
        zoom_sizer.Add(self.reset_view_button, 0, wx.EXPAND | wx.ALL, 6)

        status_sizer = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Status"), wx.VERTICAL)
        status_sizer.Add(self.status_box, 1, wx.EXPAND | wx.ALL, 6)
        status_sizer.Add(self.clear_status_button, 0, wx.EXPAND | wx.ALL, 6)

        left_side_sizer.Add(simulation_sizer, 0, wx.EXPAND | wx.BOTTOM, 8)
        left_side_sizer.Add(switch_sizer, 1, wx.EXPAND | wx.BOTTOM, 8)
        left_side_sizer.Add(zoom_sizer, 0, wx.EXPAND)

        right_side_sizer.Add(status_sizer, 0, wx.EXPAND)

        side_sizer.Add(left_side_sizer, 0, wx.EXPAND | wx.RIGHT, 8)
        side_sizer.Add(right_side_sizer, 0, wx.EXPAND)

        main_sizer.Add(signal_sizer, 0, wx.EXPAND | wx.ALL, 8)
        main_sizer.Add(self.canvas, 4, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(side_sizer, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizer(main_sizer)
        self.update_switch_rows()
        self.update_module_signal_rows()

        # Prevent the user from shrinking the window so much that the controls or canvas become unusable
        main_sizer.SetSizeHints(self)
        best_size = self.GetBestSize()
        minimum_width = max(best_size.width, 800)
        minimum_height = max(best_size.height, 650)
        self.SetMinSize((minimum_width, minimum_height))

        # If the starting size is smaller than the minimum size, make the window start at the minimum size
        current_size = self.GetSize()
        if current_size.width < minimum_width or current_size.height < minimum_height:
            self.SetSize((minimum_width, minimum_height))

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
                "Logic Simulator",
                "About Logsim",
                wx.ICON_INFORMATION | wx.OK,
            )

    def run_cycles(self, cycles):
        """Run the network for the requested number of cycles."""
        if cycles <= 0:
            self.show_status("Error: number of cycles must be positive.")
            return False

        # Run one cycle at a time and record the monitored signals
        for _ in range(cycles):
            if not self.network.execute_network():
                self.show_status(
                    "Error: network failed to reach a steady state."
                )
                return False

            self.monitors.record_signals()
            self.cycles_completed += 1
            self.total_cycles_completed += 1

        self.update_cycles_completed_text()
        return True

    def show_status(self, message):
        """Display a status message in the GUI."""
        self.status_box.AppendText(message + "\n")
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

    def on_reset_button(self, event):
        """Reset the simulation state and traces."""
        # Start again, but do not run any cycles yet
        self.devices.cold_startup()
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        self.total_cycles_completed = 0
        self.update_cycles_completed_text()
        self.canvas.reset_view()
        self.canvas.render()
        self.show_status("Reset simulation.")

    def on_clear_traces(self, event):
        """Clear waveform traces while keeping the selected monitors."""
        # Only clear what is drawn - do not reset the circuit itself
        self.monitors.reset_monitors()
        self.cycles_completed = 0
        self.update_cycles_completed_text()
        self.canvas.render()
        self.show_status("Cleared traces.")

    def on_clear_status(self, event):
        """Clear the status history."""
        self.status_box.SetValue("")
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

###############################################################################
# GUI HELPER FUNCTIONS
###############################################################################

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

        switch_names = self.get_switch_names()
        if not switch_names:
            empty_label = wx.StaticText(self.switch_rows, wx.ID_ANY, "No switches")
            empty_label.SetForegroundColour(wx.Colour(95, 99, 104))
            self.switch_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
        else:
            for switch_name in switch_names:
                switch_id = self.names.query(switch_name)
                device = self.devices.get_device(switch_id)

                # Each switch has a name and a LOW/HIGH toggle
                row_sizer = wx.BoxSizer(wx.HORIZONTAL)
                label = wx.StaticText(self.switch_rows, wx.ID_ANY, switch_name)
                toggle = wx.RadioBox(self.switch_rows, wx.ID_ANY, "", choices=["LOW", "HIGH"], majorDimension=2, style=wx.RA_SPECIFY_COLS)
                toggle.SetSelection(device.switch_state)
                toggle.SetName(switch_name)
                toggle.Bind(wx.EVT_RADIOBOX, self.on_switch_toggle)

                row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
                row_sizer.Add(toggle, 0)
                self.switch_rows_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

        self.switch_rows.Layout()
        self.switch_rows.FitInside()

    def update_monitor_choices(self):
        """Refresh the monitor selector after loading a network."""
        self.monitor_box.SetItems(self.get_output_signal_names())
        if self.monitor_box.GetCount() > 0:
            self.monitor_box.SetSelection(0)
        self.update_module_signal_rows()

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
            empty_label.SetForegroundColour(wx.Colour(95, 99, 104))
            self.module_signal_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
        else:
            for signal_name in sorted(top_level_signal_names):
                self.add_available_signal_row(self.module_signal_rows, self.module_signal_rows_sizer, signal_name, signal_name)

            self.add_module_signal_group_rows(self.module_signal_rows, self.module_signal_rows_sizer, module_signal_groups,())

        self.module_signal_rows.Layout()
        self.module_signal_rows.FitInside()
        self.module_signal_rows.Scroll(scroll_x, scroll_y)

    def add_module_signal_group_rows(self, parent, parent_sizer, signal_group, parent_path):
        """Add nested module panes and signal rows to a sizer."""
        for signal_name, full_signal_name in sorted(signal_group.get("signals_at_this_level", [])):
            self.add_available_signal_row(parent, parent_sizer, signal_name, full_signal_name)

        for module_name in sorted(signal_group):
            if module_name == "signals_at_this_level":
                continue

            # Each module becomes one collapsible pane  
            # Signals stored inside that module are added to the pane recursively
            collapsible_pane = wx.CollapsiblePane(parent, wx.ID_ANY, module_name)
            pane = collapsible_pane.GetPane()
            pane_sizer = wx.BoxSizer(wx.VERTICAL)
            module_path = parent_path + (module_name,)

            self.add_module_signal_group_rows(pane, pane_sizer, signal_group[module_name], module_path)

            pane.SetSizer(pane_sizer)

            # Store the module path e.g. ("DIV4_0", "DIV2_0") so the GUI can remember which pane was expanded
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

    def add_available_signal_row(self, parent, parent_sizer, label_text, signal_name):
        """Add one available signal row with a monitor action."""
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(parent, wx.ID_ANY, label_text)

        # row always has one button
        # Its label and handler are set by update_available_signal_button() depending on whether the signal is already monitored
        action_button = wx.Button(parent, wx.ID_ANY, "")
        self.module_signal_button_names[action_button.GetId()] = signal_name
        self.module_signal_action_buttons[signal_name] = action_button
        self.update_available_signal_button(action_button, signal_name)

        row_sizer.Add(label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row_sizer.Add(action_button, 0)
        parent_sizer.Add(row_sizer, 0, wx.EXPAND | wx.ALL, 4)

    def update_available_signal_button(self, button, signal_name):
        """Set one available signal button to Add or Remove."""
        # The same button changes job after it is clicked so remove the old event binding before attaching the new add or remove handler
        button.Unbind(wx.EVT_BUTTON)

        if self.is_signal_monitored(signal_name):
            action_label = "Remove"
            action_handler = self.on_delete_module_signal_button
            button_foreground = wx.Colour(255, 15, 15)
        else:
            action_label = "Add"
            action_handler = self.on_add_module_signal_button
            button_foreground = wx.Colour(67, 150, 95)

        button.SetLabel(action_label)
        button.SetBackgroundColour(wx.Colour(255, 255, 255))
        button.SetForegroundColour(button_foreground)
        button.Bind(wx.EVT_BUTTON, action_handler)
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
            empty_label.SetForegroundColour(wx.Colour(95, 99, 104))
            self.monitor_rows_sizer.Add(empty_label, 0, wx.ALL, 6)
        else:
            for monitor_name in self.monitors.monitors_dictionary:
                row_sizer = wx.BoxSizer(wx.HORIZONTAL)
                label = wx.StaticText(self.monitor_rows, wx.ID_ANY, monitor_name)
                button = wx.Button(self.monitor_rows, wx.ID_ANY, "Remove")

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

    def on_switch_toggle(self, event):
        """Handle the event when the user toggles a switch value."""
        switch_control = event.GetEventObject()
        switch_name = switch_control.GetName()

        # LOW is index 0 and HIGH is index 1
        switch_value = event.GetInt()
        switch_id = self.names.query(switch_name)

        if switch_id is None:
            self.show_status(f"Error: unknown switch '{switch_name}'.")
            return

        # set_switch returns True/False, not one of the Devices error codes
        switch_was_set = self.devices.set_switch(switch_id, switch_value)

        if switch_was_set:
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
            # Update the stored pane state immediately
            # This means the same panes can be reopened after the list is rebuilt
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

        # Reuse add_monitor() by putting the selected signal into the hidden comboBox that add_monitor() already reads from
        self.monitor_box.SetValue(signal_name)

        # add_monitor() normally refreshes the whole monitor UI
        # Skipping the available signal rebuild to avoid the flicker, then update just the clicked button
        self.suppress_available_signal_refresh = True
        try:
            self.add_monitor()
        finally:
            self.suppress_available_signal_refresh = False

        button = self.module_signal_action_buttons[signal_name]
        self.update_available_signal_button(button, signal_name)

    def on_delete_module_signal_button(self, event):
        """Remove a monitor from the available signal list."""
        button_id = event.GetId()
        signal_name = self.module_signal_button_names[button_id]
        signal_ids = self.get_signal_ids(signal_name)

        if signal_ids is None:
            self.show_status(f"Error: unknown signal '{signal_name}'.")
            return

        device_id, output_id = signal_ids

        if self.monitors.remove_monitor(signal_name):
            self.show_status(f"Removed monitor for {signal_name}.")
        else:
            self.show_status(f"Error: {signal_name} is not monitored.")

        # Removing a monitor changes only this row in the available signals panel so update this button instead of rebuilding the full panel
        button = self.module_signal_action_buttons[signal_name]
        self.update_available_signal_button(button, signal_name)
        self.canvas.render()

    def add_monitor(self):
        """Add the selected signal to the monitor list."""
        monitor_name = self.monitor_box.GetValue().strip()

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
            self.show_status(f"Added monitor for {monitor_name}.")
            # Normal monitor additions rebuild the available signal list
            # Sidebar button clicks set suppress_available_signal_refresh so only the clicked button is updated, which prevents flicker
            if (hasattr(self, "update_module_signal_rows") and not self.suppress_available_signal_refresh):
                self.update_module_signal_rows()
            if hasattr(self, "update_monitor_rows"):
                self.update_monitor_rows()
        elif error_type == self.monitors.MONITOR_PRESENT:
            existing_name = self.monitors.get_monitor_display_name(monitor_name)

            if existing_name != monitor_name:
                self.show_status(
                    f"{monitor_name} is already monitored as "
                    f"{existing_name}."
                )
            else:
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

    def on_add_monitor_button(self, event):
        """Handle the event when the user adds a monitor."""
        self.add_monitor()
