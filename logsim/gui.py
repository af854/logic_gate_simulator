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

        # Initialise instances of the two inner simulator classes
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
            # Find maximum trace length and monitor name length to determine
            # how to scale the display
            monitor_count = len(self.monitors.monitors_dictionary)
            max_trace_length = 0
            for trace in self.monitors.monitors_dictionary.values():
                trace_length = len(trace)
                if trace_length > max_trace_length:
                    max_trace_length = trace_length

            max_name_length = 0
            for device_id, output_id in self.monitors.monitors_dictionary:
                monitor_name = self.monitors.get_monitor_display_name(
                    device_id,
                    output_id,
                )
                name_length = len(monitor_name)
                if name_length > max_name_length:
                    max_name_length = name_length

            # Leave enough space for labels, but not more than 45% of the
            # canvas width
            label_space = max_name_length * 8 + 20
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

            available_height = size.height - 80
            if available_height < 1:
                available_height = 1

            row_gap = available_height / monitor_count
            if row_gap > 60:
                row_gap = 60
            if row_gap < 35:
                row_gap = 35

            amplitude = row_gap * 0.45
            if amplitude > 25:
                amplitude = 25
            if amplitude < 12:
                amplitude = 12

            top_y = size.height - 50

            row = 0
            for monitor_key, trace in (
                self.monitors.monitors_dictionary.items()
            ):
                device_id, output_id = monitor_key

                low_y = top_y - row * row_gap
                high_y = low_y + amplitude

                # Use the monitor's display name so nets can keep their alias
                signal_name = self.monitors.get_monitor_display_name(
                    device_id,
                    output_id,
                )
                self.render_text(signal_name, 10, low_y)

                # Draw waveform traces in blue
                GL.glColor3f(0.0, 0.0, 1.0)
                self.draw_trace(trace, start_x, low_y, high_y, step)
                row += 1

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

    def render_text(self, text, x_pos, y_pos):
        """Handle text drawing operations."""
        GL.glColor3f(0.0, 0.0, 0.0)  # text is black
        GL.glRasterPos2f(x_pos, y_pos)
        font = GLUT.GLUT_BITMAP_HELVETICA_12

        for character in text:
            if character == '\n':
                y_pos = y_pos - 20
                GL.glRasterPos2f(x_pos, y_pos)
            else:
                GLUT.glutBitmapCharacter(font, ord(character))

    def signal_to_y(self, signal, low_y, high_y):
        """Convert a signal value into a y-position."""
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

    def draw_trace(self, trace, start_x, low_y, high_y, step):
        """Draw a single monitored signal trace."""
        previous_y = None

        for index, signal in enumerate(trace):
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

    on_run_button(self, event): Event handler for when the user clicks the run
                                button.

    """

    def __init__(self, title, path, names, devices, network, monitors):
        """Initialise widgets and layout."""
        super().__init__(parent=None, title=title, size=(800, 600))

        # Initialise instances of the four inner simulator classes
        self.path = path
        self.names = names
        self.devices = devices
        self.network = network
        self.monitors = monitors
        self.cycles_completed = 0

        # Configure the file menu
        fileMenu = wx.Menu()
        menuBar = wx.MenuBar()
        fileMenu.Append(wx.ID_ABOUT, "&About")
        fileMenu.Append(wx.ID_EXIT, "&Exit")
        menuBar.Append(fileMenu, "&File")
        self.SetMenuBar(menuBar)

        # Canvas for drawing signals
        self.canvas = MyGLCanvas(self, devices, monitors)

        # Configure the widgets
        self.text = wx.StaticText(self, wx.ID_ANY, "Cycles")
        self.spin = wx.SpinCtrl(self, wx.ID_ANY, "10")
        self.run_button = wx.Button(self, wx.ID_ANY, "Run")

        # Continue keeps existing traces and device state, unlike Run
        self.continue_button = wx.Button(self, wx.ID_ANY, "Continue")
        self.status_box = wx.TextCtrl(
            self,
            wx.ID_ANY,
            "",
            style=wx.TE_MULTILINE | wx.TE_READONLY,
        )
        self.switch_box = wx.Choice(
            self,
            wx.ID_ANY,
            choices=self.get_switch_names(),
        )

        if self.switch_box.GetCount() > 0:
            self.switch_box.SetSelection(0)

        self.switch_value = wx.Choice(self, wx.ID_ANY, choices=["0", "1"])
        self.set_switch_button = wx.Button(self, wx.ID_ANY, "Set Switch")
        self.switch_value.SetSelection(0)

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
        self.remove_monitor_button = wx.Button(
            self,
            wx.ID_ANY,
            "Remove Monitor",
        )

        # Bind events to widgets
        self.Bind(wx.EVT_MENU, self.on_menu)
        self.run_button.Bind(wx.EVT_BUTTON, self.on_run_button)
        self.continue_button.Bind(wx.EVT_BUTTON, self.on_continue_button)
        self.set_switch_button.Bind(wx.EVT_BUTTON, self.on_set_switch_button)
        self.add_monitor_button.Bind(wx.EVT_BUTTON, self.on_add_monitor_button)
        self.remove_monitor_button.Bind(
            wx.EVT_BUTTON,
            self.on_remove_monitor_button,
        )

        # Configure sizers for layout
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        side_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add(self.canvas, 5, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(side_sizer, 1, wx.ALL, 5)

        side_sizer.Add(self.text, 1, wx.TOP, 10)
        side_sizer.Add(self.spin, 1, wx.ALL, 5)
        side_sizer.Add(self.run_button, 1, wx.ALL, 5)
        side_sizer.Add(self.continue_button, 1, wx.ALL, 5)
        side_sizer.Add(self.status_box, 3, wx.EXPAND | wx.ALL, 5)
        side_sizer.Add(self.switch_box, 1, wx.ALL, 5)
        side_sizer.Add(self.switch_value, 1, wx.ALL, 5)
        side_sizer.Add(self.set_switch_button, 1, wx.ALL, 5)
        side_sizer.Add(self.monitor_box, 1, wx.ALL, 5)
        side_sizer.Add(self.add_monitor_button, 1, wx.ALL, 5)
        side_sizer.Add(self.remove_monitor_button, 1, wx.ALL, 5)

        self.SetSizeHints(600, 600)
        self.SetSizer(main_sizer)

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

    def on_run_button(self, event):
        """Handle the event when the user clicks the run button."""
        cycles = self.spin.GetValue()

        if not self.network.check_network():
            self.show_status("Error: network is incomplete.")
            return

        self.devices.cold_startup()
        self.monitors.reset_monitors()
        self.cycles_completed = 0

        # Run starts from a clean trace - the shared helper records each
        # cycle's signals and updates the display after running the requested
        # number of cycles
        if self.run_cycles(cycles):
            self.show_status(f"Ran simulation for {cycles} cycles.")
            self.canvas.render()

    def run_cycles(self, cycles):
        """Run the network for the requested number of cycles."""
        if cycles <= 0:
            self.show_status("Error: number of cycles must be positive.")
            return False

        for _ in range(cycles):
            if not self.network.execute_network():
                self.show_status(
                    "Error: network failed to reach a steady state."
                )
                return False

            self.monitors.record_signals()
            self.cycles_completed += 1

        return True

    def show_status(self, message):
        """Display a status message in the GUI."""
        self.status_box.AppendText(message + "\n")

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

    def on_continue_button(self, event):
        """Continue the simulation without resetting."""
        cycles = self.spin.GetValue()

        # Continue only works after Run
        if self.cycles_completed == 0:
            self.show_status("Error: nothing to continue. Run first.")
            return

        if self.run_cycles(cycles):
            self.show_status(f"Continued simulation for {cycles} cycles.")
            self.canvas.render()

    def get_switch_names(self):
        """Return a list of all switch device names."""
        switch_names = []

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

        return signal_names

    def on_set_switch_button(self, event):
        """Handle the event when the user sets a switch value."""
        switch_selection = self.switch_box.GetSelection()

        if switch_selection == wx.NOT_FOUND:
            self.show_status("Error: select a switch.")
            return

        value_selection = self.switch_value.GetSelection()
        if value_selection == wx.NOT_FOUND:
            self.show_status("Error: select a switch value.")
            return

        switch_name = self.switch_box.GetString(switch_selection)
        switch_value_text = self.switch_value.GetString(value_selection)
        switch_value = int(switch_value_text)

        switch_id = self.names.query(switch_name)

        if switch_id is None:
            self.show_status(f"Error: unknown switch '{switch_name}'.")
            return

        # set_switch returns True/False, not one of the Devices error codes
        switch_was_set = self.devices.set_switch(switch_id, switch_value)

        if switch_was_set:
            self.show_status(f"Set switch {switch_name} to {switch_value}.")
        else:
            self.show_status(f"Error: could not set {switch_name}.")

    def change_monitor(self, add_monitor):
        """Add or remove a monitor."""
        monitor_name = self.monitor_box.GetValue().strip()

        if not monitor_name:
            self.show_status("Error: enter a monitor name.")
            return

        signal_ids = self.get_signal_ids(monitor_name)

        if signal_ids is None:
            self.show_status(f"Error: unknown signal '{monitor_name}'.")
            return

        device_id, output_id = signal_ids

        if add_monitor:
            error_type = self.monitors.make_monitor(
                device_id,
                output_id,
                self.cycles_completed,
            )

            # make_monitor returns an error code, so decode it if it fails or
            # confirm success if it works
            if error_type == self.monitors.NO_ERROR:
                self.show_status(f"Added monitor for {monitor_name}.")
            elif error_type == self.monitors.MONITOR_PRESENT:
                existing_name = self.monitors.get_monitor_display_name(
                    device_id,
                    output_id,
                )

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

        else:
            # remove_monitor returns True/False, unlike make_monitor
            monitor_was_removed = self.monitors.remove_monitor(
                device_id,
                output_id,
            )

            if monitor_was_removed:
                self.show_status(f"Removed monitor for {monitor_name}.")
            else:
                self.show_status(
                    f"Error: could not remove monitor for {monitor_name}."
                )

        self.canvas.render()

    def on_add_monitor_button(self, event):
        """Handle the event when the user adds a monitor."""
        self.change_monitor(add_monitor=True)

    def on_remove_monitor_button(self, event):
        """Handle the event when the user removes a monitor."""
        self.change_monitor(add_monitor=False)
