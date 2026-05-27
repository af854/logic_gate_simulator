"""Test the GUI module.

The real GUI uses wxPython and OpenGL so these tests will avoid opening an actual window to make the automated tests easy to run and reliable  
Instead, small dummy classes are used for the parts of the GUI that would normally draw to the screen or update widgets etc.
Hence we can test the logic in gui.py without needing to click buttons manually
"""

import pytest

from devices import Devices
from gui import Gui, MyGLCanvas
from monitors import Monitors
from names import Names
from network import Network


class DummyGui:
    """Replacement for the Gui class that does not open a window.

    For these tests we only need a few of its methods, so this class borrows those methods but avoids all the window setup
    """

    run_cycles = Gui.run_cycles
    update_cycles_completed_text = Gui.update_cycles_completed_text
    get_switch_names = Gui.get_switch_names
    get_signal_ids = Gui.get_signal_ids
    get_output_signal_names = Gui.get_output_signal_names
    add_monitor = Gui.add_monitor
    monitor_error_message = Gui.monitor_error_message

    def show_status(self, message):
        """Store status messages so the tests can check them later"""
        self.status_messages.append(message)

    def update_monitor_rows(self):
        """Skip rebuilding the monitor panel because there is no real panel"""
        pass


class DummyCanvas:
    """Replacement for MyGLCanvas that does not use OpenGL.

    some drawing helper methods are just calculations e.g. deciding where a signal should be drawn
    Those calculations can be tested without creating an OpenGL canvas
    """

    signal_to_y = MyGLCanvas.signal_to_y
    get_cycle_label_interval = MyGLCanvas.get_cycle_label_interval
    draw_trace = MyGLCanvas.draw_trace


class DummyLabel:
    """Replacement for wx.StaticText.

    In the real GUI this would show text on the screen
    In the tests, it just remembers the latest text value
    """

    def SetLabel(self, text):
        self.text = text


class DummyMonitorBox:
    """Replacement for wx.ComboBox.

    The add monitor function reads the selected signal name from a combo box
    This dummy object gives it a fixed value to read
    """

    def __init__(self, text):
        self.text = text

    def GetValue(self):
        return self.text


class DummyCanvasWidget:
    """Replacement for the real canvas widget.

    The GUI asks the canvas to redraw after monitors are changed
    This class counts how many times that would have happened
    """

    def __init__(self):
        self.times_rendered = 0

    def render(self):
        self.times_rendered += 1


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
    new_gui.devices = new_devices
    new_gui.network = new_network
    new_gui.monitors = new_monitors
    new_gui.cycles_completed = 0
    new_gui.total_cycles_completed = 0
    new_gui.cycles_completed_text = DummyLabel()
    new_gui.canvas = DummyCanvasWidget()
    new_gui.status_messages = []

    return new_gui


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
    assert new_gui.monitors.monitors_dictionary[(OR1_ID, None)] == [new_gui.devices.HIGH, new_gui.devices.HIGH, new_gui.devices.HIGH]


def test_run_cycles_zero_is_not_allowed(new_gui):
    """Test that the GUI rejects zero cycles.

    Running zero cycles would not do anything useful so the method should return False and show a clear status message
    """
    assert new_gui.run_cycles(0) is False
    assert new_gui.total_cycles_completed == 0
    assert new_gui.status_messages == ["Error: number of cycles must be positive."]


def test_add_monitor(new_gui):
    """Test adding a new monitor after some cycles have already run.

    The new monitor should be padded with BLANK values for the cycles that happened before it was added so all monitor traces stay the same length
    """
    new_gui.run_cycles(2)
    new_gui.monitor_box = DummyMonitorBox("Sw1")

    new_gui.add_monitor()

    [SW1_ID] = new_gui.names.lookup(["Sw1"])
    assert new_gui.monitors.monitors_dictionary[(SW1_ID, None)] == [new_gui.devices.BLANK, new_gui.devices.BLANK]
    assert new_gui.status_messages[-1] == "Added monitor for Sw1."
    assert new_gui.canvas.times_rendered == 1


def test_add_same_monitor_twice(new_gui):
    """Test the message shown when the same monitor is added twice.

    Or1 is already monitored in the fixture so trying to add it again should not change the monitor list
    The GUI should explain the problem
    """
    new_gui.monitor_box = DummyMonitorBox("Or1")

    new_gui.add_monitor()

    assert new_gui.status_messages == ["Error: could not add monitor for Or1. signal is already monitored."]
    assert new_gui.canvas.times_rendered == 1


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
