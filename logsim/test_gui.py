"""Test the GUI module.

The real GUI uses wxPython and OpenGL so these tests will avoid opening an actual window to make the automated tests easy to run and reliable  
Instead, small dummy classes are used for the parts of the GUI that would normally draw to the screen or update widgets etc.
Hence we can test the logic in gui.py without needing to click buttons manually
"""

import pytest
from types import SimpleNamespace
import wx

from devices import Devices
from gui import Gui, MyGLCanvas, COLLAPSIBLE_PANE_STYLE, LIVE_TRACE_INTERVAL_MS, LIVE_TRACE_SPEEDS, MAX_RUN_CYCLES, THEMES
from monitors import Monitors
from names import Names
from network import Network


class DummyGui:
    """Replacement for the Gui class that does not open a window.

    For these tests we only need a few of its methods, so this class borrows those methods but avoids all the window setup
    """

    run_cycles = Gui.run_cycles
    get_simulation_snapshot = Gui.get_simulation_snapshot
    restore_simulation_snapshot = Gui.restore_simulation_snapshot
    on_undo_cycle = Gui.on_undo_cycle
    on_redo_cycle = Gui.on_redo_cycle
    start_live_trace = Gui.start_live_trace
    resume_live_trace = Gui.resume_live_trace
    stop_live_trace = Gui.stop_live_trace
    update_live_trace_button = Gui.update_live_trace_button
    on_toggle_live_trace = Gui.on_toggle_live_trace
    on_live_trace_timer = Gui.on_live_trace_timer
    get_live_trace_interval_ms = Gui.get_live_trace_interval_ms
    on_live_trace_speed_button = Gui.on_live_trace_speed_button
    update_live_trace_speed_button = Gui.update_live_trace_speed_button
    has_loaded_circuit = Gui.has_loaded_circuit
    show_no_loaded_circuit_error = Gui.show_no_loaded_circuit_error
    update_file_dependent_controls = Gui.update_file_dependent_controls
    on_run_cycles_button = Gui.on_run_cycles_button
    on_run_one_cycle = Gui.on_run_one_cycle
    on_module_signal_pane_changed = Gui.on_module_signal_pane_changed
    update_history_buttons = Gui.update_history_buttons
    get_max_trace_length = Gui.get_max_trace_length
    update_cycle_inspector_range = Gui.update_cycle_inspector_range
    update_cycle_inspector_label = Gui.update_cycle_inspector_label
    update_cycle_inspector_label_width = Gui.update_cycle_inspector_label_width
    cycle_index_to_slider_value = Gui.cycle_index_to_slider_value
    slider_value_to_cycle_index = Gui.slider_value_to_cycle_index
    cycle_number_to_cycle_index = Gui.cycle_number_to_cycle_index
    set_cycle_inspector_index = Gui.set_cycle_inspector_index
    on_cycle_inspector_entry = Gui.on_cycle_inspector_entry
    update_cycles_completed_text = Gui.update_cycles_completed_text
    on_cycle_spin_text = Gui.on_cycle_spin_text
    get_switch_names = Gui.get_switch_names
    get_signal_ids = Gui.get_signal_ids
    get_output_signal_names = Gui.get_output_signal_names
    get_module_signal_groups = Gui.get_module_signal_groups
    get_top_level_signal_names = Gui.get_top_level_signal_names
    add_monitor_by_name = Gui.add_monitor_by_name
    monitor_error_message = Gui.monitor_error_message
    signal_to_csv_text = Gui.signal_to_csv_text
    export_traces_to_csv = Gui.export_traces_to_csv
    is_signal_monitored = Gui.is_signal_monitored
    update_available_signal_button = Gui.update_available_signal_button
    on_add_module_signal_button = Gui.on_add_module_signal_button
    on_delete_module_signal_button = Gui.on_delete_module_signal_button
    append_console_text = Gui.append_console_text
    set_switch_value = Gui.set_switch_value
    on_reset_button = Gui.on_reset_button
    on_clear_traces = Gui.on_clear_traces
    on_clear_status = Gui.on_clear_status

    def show_status(self, message):
        """Store status messages so the tests can check them later"""
        self.status_messages.append(message)

    def set_status(self, message):
        """Store the short status bar message."""
        self.status_bar_message = message

    def update_monitor_rows(self):
        """Skip rebuilding the monitor panel because there is no real panel"""
        pass

    def update_module_signal_rows(self):
        """Skip rebuilding the available signals panel because there is no real panel"""
        pass

    def show_max_run_cycles_popup(self):
        """Count maximum-cycle popups instead of opening a dialog."""
        self.max_run_cycles_popup_count += 1

    def update_switch_rows(self):
        """Skip rebuilding the switch panel because there is no real panel."""
        self.switch_rows_rebuilt += 1

    def refresh_switch_rows(self):
        """Count lightweight switch refreshes instead of using real switch buttons."""
        self.switch_rows_refreshed += 1

    def load_icon_bitmap(self, icon_path, size):
        """Return a simple dummy bitmap marker instead of loading real icons."""
        return f"{icon_path}:{size}"


class DummyCanvas:
    """Replacement for MyGLCanvas that does not use OpenGL.

    some drawing helper methods are just calculations e.g. deciding where a signal should be drawn
    Those calculations can be tested without creating an OpenGL canvas
    """

    signal_to_y = MyGLCanvas.signal_to_y
    get_cycle_label_interval = MyGLCanvas.get_cycle_label_interval
    reset_view = MyGLCanvas.reset_view
    limit_top_left_pan = MyGLCanvas.limit_top_left_pan
    get_render_size = MyGLCanvas.get_render_size
    get_export_image_size = MyGLCanvas.get_export_image_size
    get_export_tiles = MyGLCanvas.get_export_tiles
    get_monitor_display_rows = MyGLCanvas.get_monitor_display_rows
    add_module_monitor_display_rows = MyGLCanvas.add_module_monitor_display_rows
    get_waveform_layout = MyGLCanvas.get_waveform_layout
    get_canvas_label_text = MyGLCanvas.get_canvas_label_text
    follow_latest_cycle = MyGLCanvas.follow_latest_cycle
    draw_trace = MyGLCanvas.draw_trace

    def GetClientSize(self):
        """Return a fixed canvas size for tests that need a window size."""
        return SimpleNamespace(width=500, height=300)

    def Refresh(self):
        """Count refreshes instead of asking wxPython to redraw."""
        self.times_refreshed += 1


class DummyLabel:
    """Replacement for wx.StaticText.

    In the real GUI this would show text on the screen
    In the tests, it just remembers the latest text value
    """

    def SetLabel(self, text):
        self.text = text


class DummyButton:
    """Replacement for wx.Button."""

    def __init__(self):
        self.label = ""
        self.enabled = True
        self.bound_events = {}
        self.unbound_events = []

    def SetLabel(self, text):
        self.label = text

    def SetBitmapLabel(self, bitmap):
        self.bitmap = bitmap

    def SetToolTip(self, text):
        self.tooltip = text

    def Enable(self, enabled):
        self.enabled = enabled

    def Bind(self, event_binder, handler):
        self.bound_events[event_binder] = handler

    def Unbind(self, event_binder):
        self.unbound_events.append(event_binder)

    def SetBackgroundColour(self, colour):
        self.background_colour = colour

    def SetForegroundColour(self, colour):
        self.foreground_colour = colour

    def SetBezelWidth(self, width):
        self.bezel_width = width

    def SetMargins(self, x_margin, y_margin):
        self.margins = (x_margin, y_margin)

    def SetUseFocusIndicator(self, use_focus_indicator):
        self.use_focus_indicator = use_focus_indicator

    def Refresh(self):
        self.refreshed = True


class DummyTimer:
    """Replacement for wx.Timer used by live tracing tests."""

    def __init__(self):
        self.running = False
        self.interval = None
        self.times_started = 0
        self.times_stopped = 0

    def Start(self, interval):
        self.running = True
        self.interval = interval
        self.times_started += 1

    def Stop(self):
        self.running = False
        self.times_stopped += 1

    def IsRunning(self):
        return self.running


class DummyTextEntry:
    """Replacement for wx.TextCtrl used by cycle inspector tests."""

    def __init__(self, text=""):
        self.text = text
        self.enabled = True

    def GetValue(self):
        return self.text

    def SetValue(self, text):
        self.text = text

    def Enable(self, enabled):
        self.enabled = enabled


class DummyCanvasWidget:
    """Replacement for the real canvas widget.

    The GUI asks the canvas to redraw after monitors are changed
    This class counts how many times that would have happened
    """

    get_monitor_display_rows = MyGLCanvas.get_monitor_display_rows
    add_module_monitor_display_rows = MyGLCanvas.add_module_monitor_display_rows
    get_waveform_layout = MyGLCanvas.get_waveform_layout
    follow_latest_cycle = MyGLCanvas.follow_latest_cycle

    def __init__(self):
        self.times_rendered = 0
        self.times_reset = 0
        self.cycle_offset = 0
        self.cycle_inspector_index = 0
        self.cycle_inspector_enabled = False
        self.pan_x = 0
        self.pan_y = 0
        self.zoom = 1
        self.init = False
        self.monitors = None

    def GetClientSize(self):
        """Return a fixed canvas size for tests that need a window size."""
        return SimpleNamespace(width=500, height=300)

    def get_render_size(self):
        """Return the fixed render size."""
        return self.GetClientSize()

    def limit_top_left_pan(self):
        """Use the real canvas pan limiting logic."""
        MyGLCanvas.limit_top_left_pan(self)

    def render(self):
        self.times_rendered += 1

    def reset_view(self):
        self.times_reset += 1


class DummyStatusBox:
    """Replacement for the status history text box."""

    def __init__(self):
        self.text = ""

    def SetValue(self, text):
        self.text = text

    def GetValue(self):
        return self.text

    def AppendText(self, text):
        self.text += text


class DummyScrolledRows:
    """Replacement for the scrolled available-signals rows."""

    def __init__(self):
        self.times_laid_out = 0
        self.times_fit_inside = 0

    def Layout(self):
        self.times_laid_out += 1

    def FitInside(self):
        self.times_fit_inside += 1


class DummyCollapsiblePane:
    """Replacement for wx.CollapsiblePane in pane-change tests."""

    def __init__(self, pane_id, expanded):
        self.pane_id = pane_id
        self.expanded = expanded

    def GetId(self):
        return self.pane_id

    def IsExpanded(self):
        return self.expanded


class DummyPaneEvent:
    """Replacement for a collapsible pane event."""

    def __init__(self, pane):
        self.pane = pane

    def GetEventObject(self):
        return self.pane


class DummyTextEvent:
    """Replacement for text events that records Skip calls."""

    def __init__(self, text=""):
        self.text = text
        self.skip_count = 0

    def GetString(self):
        return self.text

    def Skip(self):
        self.skip_count += 1


class DummySlider:
    """Replacement for wx.Slider used by cycle inspector tests."""

    def __init__(self):
        self.minimum = 0
        self.maximum = 0
        self.value = 0
        self.enabled = True

    def SetRange(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    def SetValue(self, value):
        self.value = value

    def Enable(self, enabled):
        self.enabled = enabled


class DummySpin:
    """Replacement for wx.SpinCtrl."""

    def __init__(self, value=1):
        self.value = value
        self.enabled = True

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        self.value = value

    def Enable(self, enabled):
        self.enabled = enabled


@pytest.fixture
def new_gui():
    """Return a DummyGui instance with a small working network.

    The network has two visible switches connected to one OR gate  
    It also has one hidden switch whose name starts with @ because the GUI is supposed to hide internal parser created signals from the user
    """
    new_names = Names()
    new_devices = Devices(new_names)
    new_network = Network(new_names, new_devices)
    new_monitors = Monitors(new_names, new_devices, new_network)

    [SW1_ID, SW2_ID, OR1_ID, HIDDEN_ID, I1, I2] = new_names.lookup(["Sw1", "Sw2", "Or1", "@hidden", "I1", "I2"])

    # Add 2 normal switches, 1 hidden switch, 1 OR gate
    new_devices.make_device(SW1_ID, new_devices.SWITCH, 0)
    new_devices.make_device(SW2_ID, new_devices.SWITCH, 1)
    new_devices.make_device(OR1_ID, new_devices.OR, 2)
    new_devices.make_device(HIDDEN_ID, new_devices.SWITCH, 1)

    # Connect both normal switches to the OR gate
    new_network.make_connection(SW1_ID, None, OR1_ID, I1)
    new_network.make_connection(SW2_ID, None, OR1_ID, I2)
    new_monitors.make_monitor(OR1_ID, None)

    new_gui = DummyGui()
    new_gui.names = new_names
    new_gui.path = "test_definition_files/test_gui.txt"
    new_gui.devices = new_devices
    new_gui.network = new_network
    new_gui.monitors = new_monitors
    new_gui.net_driver_dict = {}
    new_gui.theme = THEMES["light"]
    new_gui.cycles_completed = 0
    new_gui.total_cycles_completed = 0
    new_gui.simulation_history = []
    new_gui.redo_history = []
    new_gui.live_trace_running = False
    new_gui.live_trace_target_cycles = 0
    new_gui.live_trace_cycles_completed = 0
    new_gui.live_trace_paused = False
    new_gui.live_trace_speed_index = 0
    new_gui.run_cycles_button = DummyButton()
    new_gui.live_trace_button = DummyButton()
    new_gui.live_trace_speed_button = DummyButton()
    new_gui.reset_button = DummyButton()
    new_gui.clear_traces_button = DummyButton()
    new_gui.live_trace_timer = DummyTimer()
    new_gui.spin = DummySpin(1)
    new_gui.cycles_completed_text = DummyLabel()
    new_gui.canvas = DummyCanvasWidget()
    new_gui.canvas.monitors = new_monitors
    new_gui.console_box = DummyStatusBox()
    new_gui.status_messages = []
    new_gui.status_bar_message = ""
    new_gui.max_run_cycles_popup_count = 0
    new_gui.switch_rows_rebuilt = 0
    new_gui.switch_rows_refreshed = 0

    return new_gui


def add_dummy_cycle_inspector_widgets(gui):
    """Add the dummy widgets needed by cycle inspector tests."""
    gui.cycle_inspector_slider = DummySlider()
    gui.cycle_inspector_label = DummyLabel()
    gui.cycle_inspector_entry = DummyTextEntry()


def test_get_switch_names(new_gui):
    """Test that only switches the user can see are shown in the switch list.

    The hidden switch is still part of the circuit but the user should not see it in the GUI because it is an internal helper device
    """
    assert new_gui.get_switch_names() == ["Sw1", "Sw2"]


def test_get_output_signal_names(new_gui):
    """Test that only output signals the user can see are shown for monitoring.

    This is the list that would appear in the monitor dropdown box  
    Internal names beginning with @ should be left out
    """
    assert new_gui.get_output_signal_names() == ["Sw1", "Sw2", "Or1"]


def test_get_signal_ids(new_gui):
    """Test converting a signal name typed in the GUI into internal IDs.

    A valid name should return the device and output ID
    Invalid names should return None instead of accidentally creating a new name
    """

    [OR1_ID] = new_gui.names.lookup(["Or1"])

    assert new_gui.get_signal_ids("Or1") == [OR1_ID, None]
    assert new_gui.get_signal_ids("NotADevice") is None
    assert new_gui.get_signal_ids("abcdefg") is None


def test_run_cycles(new_gui):
    """Test that the GUI can run the network and record monitor values.

    Sw2 starts HIGH, so the OR gate output should be HIGH on every recorded cycle
    The cycle counter label should also be updated for the user
    """
    assert new_gui.run_cycles(3) is True

    assert new_gui.cycles_completed == 3
    assert new_gui.total_cycles_completed == 3
    assert new_gui.cycles_completed_text.text == "Cycles passed: 3"

    [OR1_ID] = new_gui.names.lookup(["Or1"])
    or1_monitor = new_gui.monitors.monitors_dictionary["Or1"]
    assert or1_monitor.device_id == OR1_ID
    assert or1_monitor.output_id is None
    assert or1_monitor.trace == [new_gui.devices.HIGH, new_gui.devices.HIGH, new_gui.devices.HIGH]


def test_undo_cycle_restores_previous_state(new_gui):
    """Test undoing one simulated cycle from the GUI."""
    new_gui.run_cycles(2)

    assert new_gui.total_cycles_completed == 2
    assert new_gui.monitors.monitors_dictionary["Or1"].trace == [new_gui.devices.HIGH, new_gui.devices.HIGH]

    new_gui.on_undo_cycle(None)

    assert new_gui.total_cycles_completed == 1
    assert new_gui.cycles_completed == 1
    assert new_gui.switch_rows_refreshed == 1
    assert new_gui.switch_rows_rebuilt == 0
    assert new_gui.monitors.monitors_dictionary["Or1"].trace == [new_gui.devices.HIGH]
    assert new_gui.cycles_completed_text.text == "Cycles passed: 1"
    assert new_gui.status_messages[-1] == "Undid 1 cycle."


def test_redo_cycle_restores_undone_state(new_gui):
    """Test redoing one cycle after undo."""
    new_gui.run_cycles(2)
    new_gui.on_undo_cycle(None)
    new_gui.on_redo_cycle(None)

    assert new_gui.total_cycles_completed == 2
    assert new_gui.cycles_completed == 2
    assert new_gui.switch_rows_refreshed == 2
    assert new_gui.switch_rows_rebuilt == 0
    assert new_gui.monitors.monitors_dictionary["Or1"].trace == [new_gui.devices.HIGH, new_gui.devices.HIGH]
    assert new_gui.cycles_completed_text.text == "Cycles passed: 2"
    assert new_gui.status_messages[-1] == "Redid 1 cycle."


def test_running_after_undo_clears_redo_history(new_gui):
    """Test that a new simulation step replaces the redo path."""
    new_gui.run_cycles(2)
    new_gui.on_undo_cycle(None)

    assert len(new_gui.redo_history) == 1

    new_gui.run_cycles(1)

    assert new_gui.redo_history == []
    new_gui.on_redo_cycle(None)
    assert new_gui.status_messages[-1] == "Error: no simulation cycle to redo."


def test_run_cycles_zero_is_not_allowed(new_gui):
    """Test that the GUI rejects zero cycles.

    Running zero cycles would not do anything useful so the method should return False and show a clear status message
    """
    assert new_gui.run_cycles(0) is False
    assert new_gui.total_cycles_completed == 0
    assert new_gui.status_messages == ["Error: number of cycles must be positive."]


def test_run_cycles_above_limit_is_not_allowed(new_gui):
    """Test that the GUI rejects too many cycles in one run."""
    assert new_gui.run_cycles(1001) is False
    assert new_gui.total_cycles_completed == 0
    assert new_gui.status_messages == ["Error: cannot run more than 1000 cycles at once."]


def test_cycle_spin_text_rejects_values_above_limit(new_gui):
    """Test typing too many cycles clamps the spin control and shows a popup."""
    event = DummyTextEvent(str(MAX_RUN_CYCLES + 1))
    new_gui.spin.SetValue(MAX_RUN_CYCLES)

    new_gui.on_cycle_spin_text(event)

    assert new_gui.spin.GetValue() == MAX_RUN_CYCLES
    assert new_gui.max_run_cycles_popup_count == 1
    assert event.skip_count == 1


def test_cycle_spin_text_allows_values_at_limit(new_gui):
    """Test the maximum allowed cycle count is accepted."""
    event = DummyTextEvent(str(MAX_RUN_CYCLES))
    new_gui.spin.SetValue(MAX_RUN_CYCLES)

    new_gui.on_cycle_spin_text(event)

    assert new_gui.spin.GetValue() == MAX_RUN_CYCLES
    assert new_gui.max_run_cycles_popup_count == 0
    assert event.skip_count == 1


def test_live_trace_start_and_timer_tick(new_gui):
    """Test live tracing starts a timer and advances one cycle per tick."""
    new_gui.spin.SetValue(2)

    assert new_gui.start_live_trace() is True
    assert new_gui.live_trace_running is True
    assert new_gui.live_trace_timer.running is True
    assert new_gui.live_trace_timer.interval == LIVE_TRACE_INTERVAL_MS
    assert new_gui.live_trace_button.label == "Pause live"
    assert new_gui.live_trace_target_cycles == 2
    assert new_gui.live_trace_cycles_completed == 0
    assert new_gui.status_messages[-1] == "Started live tracing for 2 cycles."

    new_gui.on_live_trace_timer(None)

    assert new_gui.live_trace_running is True
    assert new_gui.live_trace_timer.running is True
    assert new_gui.total_cycles_completed == 1
    assert new_gui.cycles_completed == 1
    assert new_gui.live_trace_cycles_completed == 1
    assert new_gui.canvas.times_rendered == 1
    assert new_gui.status_bar_message == "Live tracing: 1/2 cycles"


def test_live_trace_keeps_latest_cycle_visible(new_gui):
    """Test live tracing pans the canvas when the newest cycle leaves the view."""
    new_gui.spin.SetValue(40)
    new_gui.canvas.zoom = 3
    new_gui.start_live_trace()

    for _ in range(10):
        new_gui.on_live_trace_timer(None)

    assert new_gui.canvas.pan_x < 0
    layout = new_gui.canvas.get_waveform_layout()
    latest_cycle_x = layout["start_x"] + layout["trace_length"] * layout["step"]
    latest_screen_x = latest_cycle_x * new_gui.canvas.zoom + new_gui.canvas.pan_x
    assert latest_screen_x <= new_gui.canvas.GetClientSize().width - 20


def test_live_trace_speed_button_cycles_available_speeds(new_gui):
    """Test the live tracing speed button cycles through fixed speeds."""
    assert [label for label, _speed in LIVE_TRACE_SPEEDS] == ["1x", "1.5x", "2x"]
    assert new_gui.get_live_trace_interval_ms() == LIVE_TRACE_INTERVAL_MS

    new_gui.on_live_trace_speed_button(None)

    assert new_gui.live_trace_speed_index == 1
    assert new_gui.live_trace_speed_button.label == "1.5x"
    assert new_gui.live_trace_speed_button.tooltip == "Live tracing speed: 1.5x"
    assert new_gui.get_live_trace_interval_ms() == int(LIVE_TRACE_INTERVAL_MS / 1.5)

    new_gui.on_live_trace_speed_button(None)

    assert new_gui.live_trace_speed_index == 2
    assert new_gui.live_trace_speed_button.label == "2x"
    assert new_gui.get_live_trace_interval_ms() == int(LIVE_TRACE_INTERVAL_MS / 2.0)

    new_gui.on_live_trace_speed_button(None)

    assert new_gui.live_trace_speed_index == 0
    assert new_gui.live_trace_speed_button.label == "1x"
    assert new_gui.get_live_trace_interval_ms() == LIVE_TRACE_INTERVAL_MS


def test_live_trace_speed_change_updates_running_timer(new_gui):
    """Test changing speed during live tracing restarts the timer interval."""
    new_gui.spin.SetValue(3)
    assert new_gui.start_live_trace() is True
    assert new_gui.live_trace_timer.interval == LIVE_TRACE_INTERVAL_MS
    assert new_gui.live_trace_timer.times_started == 1

    new_gui.on_live_trace_speed_button(None)

    assert new_gui.live_trace_running is True
    assert new_gui.live_trace_timer.running is True
    assert new_gui.live_trace_timer.interval == int(LIVE_TRACE_INTERVAL_MS / 1.5)
    assert new_gui.live_trace_timer.times_started == 2
    assert new_gui.live_trace_cycles_completed == 0


def test_live_trace_stops_after_selected_cycle_count(new_gui):
    """Test live tracing stops once the selected number of cycles has run."""
    new_gui.spin.SetValue(2)

    assert new_gui.start_live_trace() is True

    new_gui.on_live_trace_timer(None)
    new_gui.on_live_trace_timer(None)

    assert new_gui.live_trace_running is False
    assert new_gui.live_trace_timer.running is False
    assert new_gui.live_trace_timer.times_stopped == 1
    assert new_gui.live_trace_button.label == "Play live"
    assert new_gui.total_cycles_completed == 2
    assert new_gui.cycles_completed == 2
    assert new_gui.live_trace_cycles_completed == 2
    assert new_gui.canvas.times_rendered == 2
    assert new_gui.status_messages[-1] == "Completed live tracing for 2 cycles."
    assert new_gui.status_bar_message == "Completed live tracing for 2 cycles."


def test_toggle_live_trace_pauses_running_trace(new_gui):
    """Test pressing the live button again pauses playback."""
    new_gui.start_live_trace()

    new_gui.on_toggle_live_trace(None)

    assert new_gui.live_trace_running is False
    assert new_gui.live_trace_paused is True
    assert new_gui.live_trace_timer.running is False
    assert new_gui.live_trace_timer.times_stopped == 1
    assert new_gui.live_trace_button.label == "Play live"
    assert new_gui.status_messages[-1] == "Paused live tracing."


def test_toggle_live_trace_resumes_paused_trace_without_resetting_budget(new_gui):
    """Test play resumes a paused live trace rather than starting over."""
    new_gui.spin.SetValue(4)
    new_gui.start_live_trace()
    new_gui.on_live_trace_timer(None)
    new_gui.on_live_trace_timer(None)
    new_gui.on_toggle_live_trace(None)
    new_gui.spin.SetValue(10)

    new_gui.on_toggle_live_trace(None)

    assert new_gui.live_trace_running is True
    assert new_gui.live_trace_paused is False
    assert new_gui.live_trace_timer.running is True
    assert new_gui.live_trace_timer.times_started == 2
    assert new_gui.live_trace_target_cycles == 4
    assert new_gui.live_trace_cycles_completed == 2
    assert new_gui.total_cycles_completed == 2
    assert new_gui.status_messages[-1] == "Resumed live tracing with 2 cycles remaining."
    assert new_gui.status_bar_message == "Live tracing: 2/4 cycles"


def test_run_cycles_clears_paused_live_trace(new_gui):
    """Test other simulation actions cancel a paused live trace."""
    new_gui.spin.SetValue(3)
    new_gui.start_live_trace()
    new_gui.on_live_trace_timer(None)
    new_gui.on_toggle_live_trace(None)

    new_gui.on_run_cycles_button(None)

    assert new_gui.live_trace_running is False
    assert new_gui.live_trace_paused is False
    assert new_gui.total_cycles_completed == 4


def test_live_trace_rejects_incomplete_network(new_gui):
    """Test live tracing does not start if the network is incomplete."""
    new_gui.network.check_network = lambda: False

    assert new_gui.start_live_trace() is False
    assert new_gui.live_trace_running is False
    assert new_gui.live_trace_timer.running is False

    assert new_gui.status_messages[-1] == "Error: network is incomplete."


def test_live_trace_rejects_missing_circuit_file(new_gui):
    """Test live tracing does not start from the blank GUI."""
    new_gui.path = None

    assert new_gui.start_live_trace() is False
    assert new_gui.live_trace_running is False
    assert new_gui.live_trace_timer.running is False

    assert new_gui.status_messages[-1] == "Error: no circuit loaded. Use File > Open to load one."


def test_file_dependent_controls_disable_without_circuit_file(new_gui):
    """Test simulation controls are disabled until a circuit file is loaded."""
    new_gui.path = None

    new_gui.update_file_dependent_controls()

    assert new_gui.run_cycles_button.enabled is False
    assert new_gui.live_trace_button.enabled is False
    assert new_gui.live_trace_speed_button.enabled is False
    assert new_gui.reset_button.enabled is False
    assert new_gui.clear_traces_button.enabled is False

    new_gui.path = "test_definition_files/test_gui.txt"
    new_gui.update_file_dependent_controls()

    assert new_gui.run_cycles_button.enabled is True
    assert new_gui.live_trace_button.enabled is True
    assert new_gui.live_trace_speed_button.enabled is True
    assert new_gui.reset_button.enabled is True
    assert new_gui.clear_traces_button.enabled is True


def test_run_reset_and_clear_reject_missing_circuit_file(new_gui):
    """Test simulation actions cannot run from the blank GUI."""
    new_gui.path = None

    new_gui.on_run_cycles_button(None)
    new_gui.on_run_one_cycle(None)
    new_gui.on_reset_button(None)
    new_gui.on_clear_traces(None)

    assert new_gui.total_cycles_completed == 0
    assert new_gui.cycles_completed == 0
    assert new_gui.canvas.times_rendered == 0
    assert new_gui.canvas.times_reset == 0
    assert new_gui.status_messages == [
        "Error: no circuit loaded. Use File > Open to load one.",
        "Error: no circuit loaded. Use File > Open to load one.",
        "Error: no circuit loaded. Use File > Open to load one.",
        "Error: no circuit loaded. Use File > Open to load one."]


def test_live_trace_stops_when_execution_fails(new_gui):
    """Test a failed live tick stops the timer."""
    new_gui.start_live_trace()
    new_gui.network.execute_network = lambda: False
    new_gui.on_live_trace_timer(None)

    assert new_gui.live_trace_running is False
    assert new_gui.live_trace_timer.running is False
    assert new_gui.live_trace_button.label == "Play live"
    assert new_gui.total_cycles_completed == 0
    assert new_gui.status_messages[-1] == "Error: network failed to reach a steady state."


def test_reset_stops_live_trace(new_gui):
    """Test reset pauses live tracing before clearing the simulation."""
    new_gui.start_live_trace()
    new_gui.on_reset_button(None)

    assert new_gui.live_trace_running is False
    assert new_gui.live_trace_timer.running is False
    assert new_gui.live_trace_button.label == "Play live"
    assert new_gui.status_messages[-1] == "Reset simulation."


def test_cycle_inspector_range_tracks_trace_length(new_gui):
    """Test that the cycle inspector slider follows recorded trace data."""
    add_dummy_cycle_inspector_widgets(new_gui)
    new_gui.canvas.cycle_inspector_index = 99
    new_gui.run_cycles(3)

    assert new_gui.cycle_inspector_slider.minimum == 1
    assert new_gui.cycle_inspector_slider.maximum == 3
    assert new_gui.cycle_inspector_slider.value == 3
    assert new_gui.cycle_inspector_slider.enabled is True
    assert new_gui.cycle_inspector_entry.enabled is True
    assert new_gui.canvas.cycle_inspector_index == 2
    assert new_gui.cycle_inspector_entry.text == "3"


def test_cycle_inspector_range_disables_without_trace_data(new_gui):
    """Test that the cycle inspector disables itself when no cycles are recorded."""
    add_dummy_cycle_inspector_widgets(new_gui)
    new_gui.canvas.cycle_inspector_index = 2
    new_gui.update_cycle_inspector_range()

    assert new_gui.cycle_inspector_slider.minimum == 0
    assert new_gui.cycle_inspector_slider.maximum == 1
    assert new_gui.cycle_inspector_slider.value == 0
    assert new_gui.cycle_inspector_slider.enabled is False
    assert new_gui.cycle_inspector_entry.enabled is False
    assert new_gui.canvas.cycle_inspector_index == 0
    assert new_gui.cycle_inspector_entry.text == "-"


def test_cycle_inspector_entry_jumps_to_typed_cycle(new_gui):
    """Test typing a cycle number into the cycle inspector."""
    add_dummy_cycle_inspector_widgets(new_gui)
    new_gui.run_cycles(3)
    new_gui.cycle_inspector_entry.SetValue("2")
    new_gui.canvas.times_rendered = 0
    new_gui.on_cycle_inspector_entry(None)

    assert new_gui.canvas.cycle_inspector_index == 1
    assert new_gui.cycle_inspector_slider.value == 2
    assert new_gui.cycle_inspector_entry.text == "2"
    assert new_gui.canvas.times_rendered == 1


def test_cycle_inspector_entry_clamps_to_available_cycles(new_gui):
    """Test typing a cycle number beyond the recorded trace."""
    add_dummy_cycle_inspector_widgets(new_gui)
    new_gui.run_cycles(3)
    new_gui.cycle_inspector_entry.SetValue("99")
    new_gui.on_cycle_inspector_entry(None)

    assert new_gui.canvas.cycle_inspector_index == 2
    assert new_gui.cycle_inspector_slider.value == 3
    assert new_gui.cycle_inspector_entry.text == "3"


def test_add_monitor(new_gui):
    """Test adding a new monitor after some cycles have already run.

    The new monitor should be padded with BLANK values for the cycles that happened before it was added so all monitor traces stay the same length
    """
    new_gui.run_cycles(2)

    new_gui.add_monitor_by_name("Sw1")

    [SW1_ID] = new_gui.names.lookup(["Sw1"])
    sw1_monitor = new_gui.monitors.monitors_dictionary["Sw1"]
    assert sw1_monitor.device_id == SW1_ID
    assert sw1_monitor.trace == [new_gui.devices.BLANK, new_gui.devices.BLANK]
    assert new_gui.status_messages[-1] == "Added monitor for Sw1."
    assert new_gui.canvas.times_rendered == 1


def test_add_same_monitor_twice(new_gui):
    """Test the message shown when the same monitor is added twice.

    Or1 is already monitored in the fixture so trying to add it again should not change the monitor list
    The GUI should explain the problem
    """
    new_gui.add_monitor_by_name("Or1")

    assert new_gui.status_messages == ["Error: could not add monitor for Or1. signal is already monitored."]
    assert new_gui.canvas.times_rendered == 1


def test_get_signal_ids_for_output_port(new_gui):
    """Test converting a device output with a port name into internal IDs.

    Some devices have more than one output, so the GUI lets the user write names like Dtype1.Q  
    The device part and port part should both be found without making any new names
    """
    [D1_ID, Q_ID] = new_gui.names.lookup(["Dtype1", "Q"])
    new_gui.devices.make_device(D1_ID, new_gui.devices.D_TYPE)

    assert new_gui.get_signal_ids("Dtype1.Q") == [D1_ID, Q_ID]
    assert new_gui.get_signal_ids("Dtype1.NotAPort") is None
    assert new_gui.get_signal_ids("too.many.dots") is None


def test_get_signal_ids_for_net_name(new_gui):
    """Test that a net name can be resolved to the device output that drives it.

    The parser may give the GUI a net name, but the simulator still records the real output behind that net
    """
    [NET_ID, SW1_ID] = new_gui.names.lookup(["net_a", "Sw1"])
    new_gui.net_driver_dict[NET_ID] = SimpleNamespace(main_id=SW1_ID, port_id=None, is_literal=False)

    assert new_gui.get_signal_ids("net_a") == [SW1_ID, None]


def test_module_signal_lists_group_internal_names(new_gui):
    """Test that arrow-separated names are grouped as module signals.

    A signal called Adder->Half->carry should appear inside nested module groups  
    Top level signals should stay in the ordinary signal list
    """
    [MODULE_SIGNAL_ID] = new_gui.names.lookup(["Adder->Half->carry"])
    new_gui.devices.make_device(MODULE_SIGNAL_ID, new_gui.devices.SWITCH, 0)

    assert "Adder->Half->carry" not in new_gui.get_top_level_signal_names()
    assert new_gui.get_module_signal_groups() == {
        "Adder": {
            "Half": {
                "signals_at_this_level": [
                    ("carry", "Adder->Half->carry"),
                ],
            },
        },
    }


def test_module_signal_panes_do_not_request_top_level_resize():
    """Test module panes opt out of wx's automatic frame resizing."""
    assert COLLAPSIBLE_PANE_STYLE & wx.CP_NO_TLW_RESIZE


def test_module_signal_pane_expand_updates_scrolled_list(new_gui):
    """Test expanding a module signal pane records its state and refits the list."""
    pane = DummyCollapsiblePane(10, expanded=True)
    event = DummyPaneEvent(pane)
    new_gui.module_signal_expanded_paths = set()
    new_gui.module_signal_pane_paths = {10: (pane, ("Adder",))}
    new_gui.module_signal_rows = DummyScrolledRows()

    new_gui.on_module_signal_pane_changed(event)

    assert new_gui.module_signal_expanded_paths == {("Adder",)}
    assert new_gui.module_signal_rows.times_laid_out == 1
    assert new_gui.module_signal_rows.times_fit_inside == 1


def test_available_signal_action_buttons_are_flat_clickable_icons(new_gui):
    """Test add/remove signal icon buttons are flat and clickable."""
    button = DummyButton()

    new_gui.update_available_signal_button(button, "Sw1")

    assert wx.EVT_BUTTON in button.bound_events
    assert wx.EVT_LEFT_DOWN in button.bound_events
    assert button.unbound_events == [wx.EVT_BUTTON, wx.EVT_LEFT_DOWN]
    assert button.label == ""
    assert button.tooltip == "Add"
    assert button.background_colour == new_gui.theme["panel_bg"]
    assert button.bezel_width == 0
    assert button.margins == (0, 0)
    assert button.use_focus_indicator is False


def test_set_switch_value(new_gui):
    """Test changing a switch from the GUI helper method.

    The method should update the simulator and show a clear message to the user
    """
    [SW1_ID] = new_gui.names.lookup(["Sw1"])

    new_gui.set_switch_value("Sw1", new_gui.devices.HIGH)

    assert new_gui.devices.get_device(SW1_ID).switch_state == new_gui.devices.HIGH
    assert new_gui.status_messages[-1] == "Set switch Sw1 to HIGH."


def test_set_switch_value_does_not_pause_live_trace(new_gui):
    """Test switches can be changed while live tracing keeps running."""
    new_gui.spin.SetValue(3)
    new_gui.start_live_trace()

    new_gui.set_switch_value("Sw1", new_gui.devices.HIGH)

    assert new_gui.live_trace_running is True
    assert new_gui.live_trace_timer.running is True
    assert new_gui.live_trace_paused is False

    new_gui.on_live_trace_timer(None)

    assert new_gui.total_cycles_completed == 1
    assert new_gui.live_trace_cycles_completed == 1


def test_set_switch_value_unknown_switch(new_gui):
    """Test the error message for a switch name that is not in the circuit."""
    new_gui.set_switch_value("NotASwitch", new_gui.devices.HIGH)

    assert new_gui.status_messages == ["Error: unknown switch 'NotASwitch'."]


def test_clear_traces_keeps_total_cycle_count(new_gui):
    """Test clearing the waveform without resetting the whole simulation.

    The old trace is removed, but the total cycle count is kept so future CSV and axis labels can continue from the right cycle number
    """
    new_gui.run_cycles(2)
    new_gui.on_clear_traces(None)

    assert new_gui.cycles_completed == 0
    assert new_gui.total_cycles_completed == 2
    assert new_gui.canvas.cycle_offset == 2
    assert new_gui.cycles_completed_text.text == "Cycles passed: 2"
    assert new_gui.monitors.monitors_dictionary["Or1"].trace == []
    assert new_gui.status_messages[-1] == "Cleared traces."


def test_reset_button_clears_simulation_state(new_gui):
    """Test resetting the simulation from the GUI.

    Reset should clear traces and return both cycle counters to zero
    """
    new_gui.run_cycles(2)
    new_gui.on_reset_button(None)

    assert new_gui.cycles_completed == 0
    assert new_gui.total_cycles_completed == 0
    assert new_gui.canvas.cycle_offset == 0
    assert new_gui.canvas.times_reset == 1
    assert new_gui.canvas.times_rendered == 1
    assert new_gui.cycles_completed_text.text == "Cycles passed: 0"
    assert new_gui.monitors.monitors_dictionary["Or1"].trace == []
    assert new_gui.status_messages[-1] == "Reset simulation."


def test_clear_status(new_gui):
    """Test clearing the console history box."""
    new_gui.console_box.text = "old message\n"
    new_gui.status_bar_message = "old message"

    new_gui.on_clear_status(None)

    assert new_gui.console_box.text == ""
    assert new_gui.status_bar_message == "Ready"


def test_append_console_text_does_not_leave_trailing_blank_line(new_gui):
    """Test console messages are separated without a final blank line."""
    new_gui.append_console_text("first")
    new_gui.append_console_text("second")

    assert new_gui.console_box.text == "first\nsecond"


@pytest.mark.parametrize("signal, text", [
    ("HIGH", "1"),
    ("RISING", "1"),
    ("LOW", "0"),
    ("FALLING", "0"),
    ("BLANK", "")])

def test_signal_to_csv_text(new_gui, signal, text):
    """Test converting simulator signal values into readable CSV values."""
    signal_value = getattr(new_gui.devices, signal)

    assert new_gui.signal_to_csv_text(signal_value) == text


def test_export_traces_to_csv(new_gui, tmp_path):
    """Test exporting monitor traces to a CSV file.

    The first column should be the real cycle number, followed by one column for each monitor
    """
    new_gui.run_cycles(2)
    new_gui.add_monitor_by_name("Sw1")
    new_gui.run_cycles(1)
    new_gui.canvas.cycle_offset = 5

    csv_file = tmp_path / "traces.csv"
    new_gui.export_traces_to_csv(csv_file)

    assert csv_file.read_text().splitlines() == [
        "cycle,Or1,Sw1",
        "6,1,",
        "7,1,",
        "8,1,0"]


def test_canvas_reset_view():
    """Test resetting pan and zoom values on the waveform canvas."""
    canvas = DummyCanvas()
    canvas.pan_x = 15
    canvas.pan_y = -20
    canvas.zoom = 2
    canvas.init = True
    canvas.times_refreshed = 0

    canvas.reset_view()

    assert canvas.pan_x == 0
    assert canvas.pan_y == 0
    assert canvas.zoom == 1
    assert canvas.init is False
    assert canvas.times_refreshed == 1


def test_canvas_pan_limit_blocks_unzoomed_top_left_overscroll():
    """Test that the canvas cannot be dragged past the unzoomed top-left corner."""
    canvas = DummyCanvas()
    canvas.zoom = 1
    canvas.pan_x = 15
    canvas.pan_y = -20

    canvas.limit_top_left_pan()

    assert canvas.pan_x == 0
    assert canvas.pan_y == 0


def test_canvas_pan_limit_allows_zoomed_vertical_movement():
    """Test that zoomed-in vertical panning can move before hitting the top boundary."""
    canvas = DummyCanvas()
    canvas.zoom = 2
    canvas.pan_x = -40
    canvas.pan_y = -120

    canvas.limit_top_left_pan()

    assert canvas.pan_x == -40
    assert canvas.pan_y == -120


def test_canvas_pan_limit_clamps_zoomed_real_top_boundary():
    """Test that zoomed-in vertical panning is clamped only at the real top boundary."""
    canvas = DummyCanvas()
    canvas.zoom = 2
    canvas.pan_x = 0
    canvas.pan_y = -400

    canvas.limit_top_left_pan()

    assert canvas.pan_y == -300


def test_get_monitor_display_rows_groups_module_monitors():
    """Test the rows used to draw top level and module monitor traces."""
    names = Names()
    devices = Devices(names)
    monitors = SimpleNamespace(monitors_dictionary={
        "Out": SimpleNamespace(requested_name="Out", trace=[devices.HIGH]),
        "Mod->Inner->Q": SimpleNamespace(requested_name="Mod->Inner->Q", trace=[devices.LOW])})
    canvas = DummyCanvas()
    canvas.monitors = monitors

    assert canvas.get_monitor_display_rows() == [
        {"kind": "trace", "label": "Out", "trace": [devices.HIGH], "height": 1},
        {"kind": "heading", "label": "Mod", "height": 0.35},
        {"kind": "heading", "label": "  Inner", "height": 0.35},
        {"kind": "trace", "label": "    Q", "trace": [devices.LOW], "height": 1}]


def test_get_export_image_size_grows_for_long_traces():
    """Test that exported images are large enough for the waveform data."""
    devices = Devices(Names())
    monitors = SimpleNamespace(monitors_dictionary={"VeryLongSignalName": SimpleNamespace(requested_name="VeryLongSignalName", trace=[devices.HIGH] * 40)})
    canvas = DummyCanvas()
    canvas.monitors = monitors

    export_size = canvas.get_export_image_size()

    assert export_size.width == 1054
    assert export_size.height == 300


def test_canvas_render_size_override_controls_layout_size():
    """Test export rendering can use a virtual size without resizing the canvas."""
    devices = Devices(Names())
    canvas = DummyCanvas()
    canvas.monitors = SimpleNamespace(monitors_dictionary={"Signal": SimpleNamespace(requested_name="Signal", trace=[devices.HIGH] * 40)})

    assert canvas.get_render_size() == SimpleNamespace(width=500, height=300)
    small_layout = canvas.get_waveform_layout()

    canvas.render_size_override = SimpleNamespace(width=900, height=400)
    large_layout = canvas.get_waveform_layout()

    assert canvas.get_render_size() == SimpleNamespace(width=900, height=400)
    assert large_layout["step"] > small_layout["step"]


def test_export_tiles_cover_full_image_from_visible_canvas_tiles():
    """Test PNG export tiles cover an image larger than the visible canvas."""
    canvas = DummyCanvas()
    export_size = SimpleNamespace(width=1200, height=650)
    capture_size = SimpleNamespace(width=500, height=300)

    tiles = canvas.get_export_tiles(export_size, capture_size)
    tile_area = sum(tile["width"] * tile["height"] for tile in tiles)

    assert len(tiles) == 9
    assert tile_area == export_size.width * export_size.height
    assert all(tile["width"] <= capture_size.width for tile in tiles)
    assert all(tile["height"] <= capture_size.height for tile in tiles)


def test_get_waveform_layout_matches_trace_area():
    """Test the waveform geometry shared with the cycle inspector slider."""
    devices = Devices(Names())
    monitors = SimpleNamespace(monitors_dictionary={"Signal": SimpleNamespace(requested_name="Signal", trace=[devices.HIGH] * 10)})
    canvas = DummyCanvas()
    canvas.monitors = monitors

    layout = canvas.get_waveform_layout()

    assert layout["start_x"] == 118
    assert layout["step"] == 20
    assert layout["trace_length"] == 10
    assert layout["display_height"] == 1


def test_canvas_label_text_is_shortened_before_waveform():
    """Test long canvas labels are shortened before they overlap traces."""
    canvas = DummyCanvas()

    assert canvas.get_canvas_label_text("SHORT", 120) == "SHORT"
    assert canvas.get_canvas_label_text("VERY_LONG_SIGNAL_NAME_THAT_WOULD_OVERLAP", 120) == "VERY_LON..."


def test_signal_to_y():
    """Test how signal values are converted to y positions on the waveform.

    HIGH / RISING are drawn at the high level, LOW / FALLING are drawn at the low level
    BLANK is not drawn so it returns none
    """
    names = Names()
    devices = Devices(names)
    canvas = DummyCanvas()
    canvas.devices = devices

    assert canvas.signal_to_y(devices.HIGH, 10, 30) == 30
    assert canvas.signal_to_y(devices.RISING, 10, 30) == 30
    assert canvas.signal_to_y(devices.LOW, 10, 30) == 10
    assert canvas.signal_to_y(devices.FALLING, 10, 30) == 10
    assert canvas.signal_to_y(devices.BLANK, 10, 30) is None


@pytest.mark.parametrize("step, interval", [(18, 5), (10, 10), (6, 20), (5, 50)])
def test_cycle_label_interval(step, interval):
    """Test the spacing between cycle number labels.

    When the waveform is compressed, labels need to be spaced further apart so the numbers do not overlap
    """
    canvas = DummyCanvas()
    assert canvas.get_cycle_label_interval(step) == interval


def test_draw_trace():
    """Test the lines drawn for a simple waveform.

    The trace starts LOW, rises to HIGH, has one BLANK value, and then returns to LOW
    The BLANK value should break the line instead of drawing through the missing data
    """
    names = Names()
    devices = Devices(names)
    canvas = DummyCanvas()
    canvas.devices = devices

    lines_drawn = []

    def save_line(x1, y1, x2, y2):
        lines_drawn.append((x1, y1, x2, y2))

    canvas.draw_line = save_line

    canvas.draw_trace([devices.LOW, devices.HIGH, devices.BLANK, devices.LOW], 100, 10, 30, 5)

    assert lines_drawn == [(100, 10, 105, 10),
        (105, 10, 105, 30),
        (105, 30, 110, 30),
        (115, 10, 120, 10)]
