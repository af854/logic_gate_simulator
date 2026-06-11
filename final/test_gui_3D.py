"""Tests for the 3D canvas layout and camera logic.

The real 3D canvas needs wxPython and OpenGL, so these tests use a small
dummy object.  The dummy borrows only the calculation methods from Canvas3D.
That lets us test the maths without opening a GUI window.
"""

from types import SimpleNamespace
import pytest
from gui_3D import Canvas3D


MODULE_Z_SPACING = 250.0


class DummyMonitor:
    """Small monitor object with only the trace data used by Canvas3D."""

    def __init__(self, trace):
        self.trace = trace


class DummyCanvas3D:
    """Small stand-in for Canvas3D that avoids wx and OpenGL."""

    _compute_layout = Canvas3D._compute_layout
    _calculate_focal_and_zoom = Canvas3D._calculate_focal_and_zoom
    snap_front_view = Canvas3D.snap_front_view
    snap_reset_view = Canvas3D.snap_reset_view

    def __init__(self, monitor_traces, width=600, height=400):
        self.monitors = SimpleNamespace(
            monitors_dictionary={
                name: DummyMonitor(trace) for name, trace in monitor_traces.items()
            }
        )
        self.window_size = SimpleNamespace(width=width, height=height)
        self.connections = []
        self.times_refreshed = 0
        self._needs_framing_on_show = False

        self.init = True
        self.focal_x = 0.0
        self.focal_y = 0.0
        self.focal_z = -150.0
        self.camera_pitch = 25.0
        self.camera_yaw = -35.0
        self.camera_distance = 800.0

    def GetClientSize(self):
        """Return the pretend canvas size."""
        return self.window_size

    def IsShownOnScreen(self):
        """Pretend the canvas is hidden so no real OpenGL context is needed."""
        return False

    def Refresh(self):
        """Record that a real canvas would have been redrawn."""
        self.times_refreshed += 1


@pytest.fixture
def module_canvas():
    """Canvas with top-level, module, and nested-module signals."""
    return DummyCanvas3D(
        {
            "SW1": [0, 1, 1],
            "FULL_ADDER->A": [0, 0, 1],
            "FULL_ADDER->X1": [1, 0, 1],
            "FULL_ADDER->INNER->SUM": [None, 0, 1],
            "OUT": [0, 1, 0],
        }
    )


def signal_names_in(blocks, path):
    """Return the signal labels drawn on one 3D plane."""
    return [
        signal_name
        for block in blocks
        if block["path"] == path
        for signal_name, _trace, _y in block["signals"]
    ]


def z_by_path(blocks):
    """Return each module path's z position."""
    return {block["path"]: block["z"] for block in blocks}


def test_module_signals_are_split_onto_3d_planes(module_canvas):
    """Top-level, module, and nested-module signals go on separate planes."""
    blocks = module_canvas._compute_layout()

    assert signal_names_in(blocks, ()) == ["SW1", "OUT"]
    assert signal_names_in(blocks, ("FULL_ADDER",)) == ["A", "X1"]
    assert signal_names_in(blocks, ("FULL_ADDER", "INNER")) == ["SUM"]

    z_positions = z_by_path(blocks)
    assert z_positions[()] == 0.0
    assert z_positions[("FULL_ADDER",)] == -MODULE_Z_SPACING
    assert z_positions[("FULL_ADDER", "INNER")] == -2 * MODULE_Z_SPACING


def test_module_planes_have_headings_and_connectors(module_canvas):
    """Module planes get headings and connection lines to their children."""
    blocks = module_canvas._compute_layout()

    headings = [block["heading"] for block in blocks if block["heading"]]
    connection_depths = {
        (connection["z1"], connection["z2"])
        for connection in module_canvas.connections
    }

    assert headings == ["FULL_ADDER internals", "INNER internals"]
    assert (0.0, -MODULE_Z_SPACING) in connection_depths
    assert (-MODULE_Z_SPACING, -2 * MODULE_Z_SPACING) in connection_depths


def test_top_level_only_signals_stay_on_one_plane():
    """Signals without module names do not create extra 3D planes."""
    canvas = DummyCanvas3D({"A": [0, 1], "B": [1, 0]})

    blocks = canvas._compute_layout()

    assert len(blocks) == 1
    assert blocks[0]["path"] == ()
    assert blocks[0]["z"] == 0.0
    assert signal_names_in(blocks, ()) == ["A", "B"]
    assert canvas.connections == []


def test_sibling_module_planes_are_sorted_by_name():
    """Sibling modules are laid out in alphabetical order for stable output."""
    canvas = DummyCanvas3D(
        {
            "TOP": [0],
            "Z_MOD->OUT": [1],
            "A_MOD->OUT": [0],
        }
    )

    blocks = canvas._compute_layout()
    module_paths = [block["path"] for block in blocks if block["path"]]

    assert module_paths == [("A_MOD",), ("Z_MOD",)]


def test_camera_framing_centres_the_3d_planes(module_canvas):
    """Auto-framing points the camera at the middle of the 3D layout."""
    module_canvas._calculate_focal_and_zoom()

    assert module_canvas.focal_z == pytest.approx(-MODULE_Z_SPACING)
    assert module_canvas.camera_distance >= MODULE_Z_SPACING
    assert module_canvas.init is False
    assert module_canvas.times_refreshed == 1


def test_camera_framing_waits_until_canvas_has_a_real_size(module_canvas):
    """A very small canvas is probably not visible yet, so framing is delayed."""
    module_canvas.window_size = SimpleNamespace(width=20, height=20)

    module_canvas._calculate_focal_and_zoom()

    assert module_canvas._needs_framing_on_show is True
    assert module_canvas.times_refreshed == 0


def test_camera_framing_handles_no_monitors():
    """With no signals, framing falls back to the default view centre."""
    canvas = DummyCanvas3D({})

    canvas._calculate_focal_and_zoom()

    assert canvas.focal_x == 0.0
    assert canvas.focal_y == 0.0
    assert canvas.focal_z == -150.0
    assert canvas.init is False
    assert canvas.times_refreshed == 1


def test_camera_snap_buttons_use_3d_camera_presets(module_canvas):
    """The front and reset presets set clear camera angles."""
    module_canvas.snap_front_view()

    assert module_canvas.camera_pitch == 0.0
    assert module_canvas.camera_yaw == 0.0
    assert module_canvas.times_refreshed == 1

    module_canvas.snap_reset_view()

    assert module_canvas.camera_pitch == 25.0
    assert module_canvas.camera_yaw == -35.0
    assert module_canvas.times_refreshed == 2
