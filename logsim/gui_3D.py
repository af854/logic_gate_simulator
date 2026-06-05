"""Implement the 3D graphical user interface for the Logic Simulator.

This module defines an OpenGL canvas that renders signal traces in three
dimensional space and groups inputs, internals and outputs onto separated depth
planes for clearer visual analysis.
"""

import sys

import numpy as np
import wx
import wx.glcanvas as wxcanvas
from OpenGL import GL, GLU, GLUT

GLUT_INITIALISED = False


def initialise_glut_once():
    """Initialise GLUT once per process to support bitmap text.

    This function is safe to call repeatedly and only performs work on the
    first call.
    """
    global GLUT_INITIALISED
    if not GLUT_INITIALISED:
        try:
            GLUT.glutInit(sys.argv)
            GLUT_INITIALISED = True
        except Exception:
            pass


if sys.platform == "win32":
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class Canvas3D(wxcanvas.GLCanvas):
    """Handle the 3D drawing operations and data-flow visualisation for
    the logic simulator.

    This class manages camera state, OpenGL initialisation and rendering
    of the signal ribbons across input, net and output planes.
    """

    def __init__(self, parent, devices, monitors):
        """Initialise the 3D canvas and bind wx event handlers.

        This method stores simulator state, creates the OpenGL context and
        sets the default camera, theme and plane settings.
        """
        super().__init__(
            parent,
            -1,
            attribList=[
                wxcanvas.WX_GL_RGBA,
                wxcanvas.WX_GL_DOUBLEBUFFER,
                wxcanvas.WX_GL_DEPTH_SIZE,
                16,
                wxcanvas.WX_GL_SAMPLE_BUFFERS,
                1,
                wxcanvas.WX_GL_SAMPLES,
                4,
                0,
            ],
        )
        initialise_glut_once()
        self.init = False
        self.multisample_enabled = True
        self.context = wxcanvas.GLContext(self)
        self.devices = devices
        self.monitors = monitors
        self.cycle_offset = 0
        self.cycle_inspector_enabled = False
        self.cycle_inspector_index = 0
        self.trace_bg_mode = 2
        self.render_size_override = None
        self.theme = {
            "canvas_bg": (0.08, 0.09, 0.1),
            "canvas_text": (0.88, 0.9, 0.94),
            "canvas_grid": (0.18, 0.2, 0.24),
            "canvas_trace": (0.42, 0.68, 1.0),
        }
        self.z_planes = {"INPUTS": 0.0, "INTERNALS": -150.0, "OUTPUTS": -300.0}
        self.focal_x = 0.0
        self.focal_y = 0.0
        self.focal_z = -150.0
        self.camera_pitch = 25.0
        self.camera_yaw = -35.0
        self.camera_distance = 800.0
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self._needs_framing_on_show = True
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.on_mouse)
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.Bind(wx.EVT_SHOW, self.on_show)

    def on_show(self, event):
        """Trigger a camera framing update when the canvas becomes visible.

        This ensures the first visible view is scaled and centred correctly.
        """
        if event.IsShown() and getattr(self, "_needs_framing_on_show", False):
            self._needs_framing_on_show = False
            wx.CallAfter(self.snap_reset_view)
        event.Skip()

    def reset_view(self):
        """Reset the GL initialisation state so the next render
        reconfigures the graphics context.

        The current camera orientation remains unchanged.
        """
        self.init = False
        self.Refresh()

    def initialise_gl(self):
        """Configure OpenGL projection, lighting and camera transforms for
        the 3D canvas.

        This prepares the graphics context for rendering the 3D scene.
        """
        size = self.GetClientSize()
        if size.width == 0 or size.height == 0:
            return

        self.SetCurrent(self.context)

        scale = self.GetContentScaleFactor()
        vp_width = int(size.width * scale)
        vp_height = int(size.height * scale)

        bg = self.theme.get("canvas_bg", (0, 0, 0))
        GL.glClearColor(bg[0], bg[1], bg[2], 1.0)

        GL.glViewport(0, 0, vp_width, vp_height)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(45, vp_width / vp_height, 10, 10000)

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GLU.gluPerspective(45, size.width / size.height, 10, 10000)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        ambient_light = [0.4, 0.4, 0.4, 1.0]
        diffuse_light = [0.6, 0.6, 0.6, 1.0]
        light_pos = [50.0, 100.0, 150.0, 0.0]
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, ambient_light)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, diffuse_light)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, light_pos)
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        if self.multisample_enabled:
            GL.glEnable(GL.GL_MULTISAMPLE)
        else:
            GL.glDisable(GL.GL_MULTISAMPLE)
        GL.glShadeModel(GL.GL_SMOOTH)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_NORMALIZE)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glTranslatef(0.0, 0.0, -self.camera_distance)
        GL.glRotatef(self.camera_pitch, 1, 0, 0)
        GL.glRotatef(self.camera_yaw, 0, 1, 0)
        GL.glTranslatef(-self.focal_x, -self.focal_y, -self.focal_z)

    def get_world_on_focal_plane(self, screen_x, screen_y):
        """Compute the world-space coordinate on the locked focal plane
        under a screen point.

        The method raycasts from the camera through the viewport and
        returns the intersection with the focal depth.
        """
        self.SetCurrent(self.context)
        size = self.GetClientSize()
        if size.width == 0 or size.height == 0:
            return None

        scale = self.GetContentScaleFactor()
        vp_width = int(size.width * scale)
        vp_height = int(size.height * scale)

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(45, vp_width / vp_height, 10, 10000)

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glTranslatef(0.0, 0.0, -self.camera_distance)
        GL.glRotatef(self.camera_pitch, 1, 0, 0)
        GL.glRotatef(self.camera_yaw, 0, 1, 0)
        GL.glTranslatef(-self.focal_x, -self.focal_y, -self.focal_z)

        modelview = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX)
        projection = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX)

        viewport = (0, 0, vp_width, vp_height)

        win_y = float(vp_height - (screen_y * scale))
        win_x = float(screen_x * scale)

        try:
            near_pt = GLU.gluUnProject(
                win_x, win_y, 0.0, modelview, projection, viewport
            )
            far_pt = GLU.gluUnProject(
                win_x, win_y, 1.0, modelview, projection, viewport
            )
        except ValueError:
            return None
        dx = far_pt[0] - near_pt[0]
        dy = far_pt[1] - near_pt[1]
        dz = far_pt[2] - near_pt[2]
        if dz == 0:
            return None
        t = (self.focal_z - near_pt[2]) / dz
        hit_x = near_pt[0] + dx * t
        hit_y = near_pt[1] + dy * t
        return (hit_x, hit_y)

    def set_multisample(self, enabled):
        """Enable or disable multisample antialiasing for the OpenGL context."""
        self.multisample_enabled = enabled
        self.SetCurrent(self.context)
        if enabled:
            GL.glEnable(GL.GL_MULTISAMPLE)
        else:
            GL.glDisable(GL.GL_MULTISAMPLE)
        self.Refresh()

    def categorise_signals(self):
        """Group active monitors into input, internal, and output planes.

        Nested signals are grouped into internals. Remaining top-level
        signals are split into inputs (switches/clocks) and outputs.
        """
        inputs, internals, outputs = ([], [], [])
        for name, monitor in self.monitors.monitors_dictionary.items():
            device = self.devices.get_device(monitor.device_id)
            if device is None:
                continue
            if "->" in name:
                internals.append((name, monitor))
                continue

            is_input = device.device_kind in [self.devices.SWITCH, self.devices.CLOCK]
            if (
                hasattr(self.devices, "SIGGEN")
                and device.device_kind == self.devices.SIGGEN
            ):
                is_input = True

            if is_input:
                inputs.append((name, monitor))
            else:
                outputs.append((name, monitor))

        return {"INPUTS": inputs, "INTERNALS": internals, "OUTPUTS": outputs}

    def render(self):
        """Render the complete 3D scene for the current monitor traces.

        It draws grouping planes, axes, signal ribbons and an optional
        cycle inspector slice.
        """
        self.SetCurrent(self.context)
        if not self.init:
            self.initialise_gl()
            self.init = True
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if not self.monitors.monitors_dictionary:
            self.render_text(
                "No active monitors. Add signals to see 3D view.",
                -50,
                0,
                0,
                colour=self.theme.get("canvas_text"),
            )
            GL.glFlush()
            self.SwapBuffers()
            return
        step_x = 20
        amplitude_y = 15
        spacing_y = 30
        start_x = -150
        signal_groups = self.categorise_signals()
        max_trace_len = max(
            (len(m.trace) for m in self.monitors.monitors_dictionary.values())
        )
        max_x = start_x + max_trace_len * step_x
        global_max_y = 0
        GL.glLineWidth(2.0)
        for group_name, signals in signal_groups.items():
            if not signals:
                continue
            z_depth = self.z_planes[group_name]
            max_y_for_plane = len(signals) * spacing_y
            global_max_y = max(global_max_y, max_y_for_plane)
            self.draw_z_plane(group_name, z_depth, start_x, max_x, max_y_for_plane)
            self.draw_axes(group_name, z_depth, start_x, max_x, max_trace_len, step_x)
            current_y = 0
            ordered_signals = list(reversed(signals))
            for name, monitor in ordered_signals:
                trace_colour = self.theme.get("canvas_trace", (0.11, 0.45, 0.95))
                GL.glDepthMask(GL.GL_FALSE)
                self.render_text(
                    name,
                    start_x - 60,
                    current_y + 4,
                    z_depth + 4,
                    colour=self.theme.get("canvas_text"),
                )
                GL.glDepthMask(GL.GL_TRUE)
                GL.glColor3f(*trace_colour)
                self.draw_3d_ribbon(
                    monitor.trace, start_x, current_y, z_depth, step_x, amplitude_y
                )
                current_y += spacing_y
        if self.cycle_inspector_enabled and max_trace_len > 0:
            inspector_x = start_x + self.cycle_inspector_index * step_x + step_x / 2.0
            signal_groups = self.categorise_signals()
            self.draw_cycle_inspector_slice(
                inspector_x,
                global_max_y,
                signal_groups,
                start_x,
                spacing_y,
                amplitude_y,
            )
        GL.glLineWidth(1.0)
        GL.glFlush()
        self.SwapBuffers()

    def draw_z_plane(self, name, z_depth, start_x, max_x, max_y):
        """Draw a semi-transparent grid floor at the given depth plane."""
        if self.trace_bg_mode == 0:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        plane_bg_colour = self.theme.get("canvas_grid", (0.5, 0.5, 0.5))
        line_colour = self.theme.get("canvas_axis", (0.5, 0.5, 0.5))
        pad = 20.0

        if self.trace_bg_mode == 2:
            GL.glColor4f(
                plane_bg_colour[0], plane_bg_colour[1], plane_bg_colour[2], 0.35
            )

            quad_verts = np.array(
                [
                    [start_x - pad, -pad, z_depth],
                    [max_x + pad, -pad, z_depth],
                    [max_x + pad, max_y + pad, z_depth],
                    [start_x - pad, max_y + pad, z_depth],
                ],
                dtype=np.float32,
            )

            GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, quad_verts)
            GL.glDrawArrays(GL.GL_QUADS, 0, 4)
            GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

        if self.trace_bg_mode in (1, 2):
            GL.glColor4f(line_colour[0], line_colour[1], line_colour[2], 0.25)

            y_vals = np.arange(0, max_y + pad + 1, 30, dtype=np.float32)
            h_lines = np.zeros((len(y_vals), 2, 3), dtype=np.float32)
            h_lines[:, 0, 0] = start_x - pad
            h_lines[:, 1, 0] = max_x + pad
            h_lines[:, :, 1] = y_vals[:, np.newaxis]
            h_lines[:, :, 2] = z_depth

            x_vals = np.arange(start_x, max_x + pad + 1, 100, dtype=np.float32)
            v_lines = np.zeros((len(x_vals), 2, 3), dtype=np.float32)
            v_lines[:, :, 0] = x_vals[:, np.newaxis]
            v_lines[:, 0, 1] = -pad
            v_lines[:, 1, 1] = max_y + pad
            v_lines[:, :, 2] = z_depth

            all_lines = np.ascontiguousarray(
                np.concatenate([h_lines.reshape(-1, 3), v_lines.reshape(-1, 3)], axis=0)
            )

            GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, all_lines)
            GL.glDrawArrays(GL.GL_LINES, 0, len(all_lines))
            GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def draw_axes(self, group_name, z_depth, start_x, max_x, trace_length, step_x):
        """Draw the plane label, axis line and cycle tick marks."""
        GL.glDisable(GL.GL_LIGHTING)

        text_colour = self.theme.get("canvas_text", (1, 1, 1))
        muted_colour = self.theme.get("canvas_muted", (0.5, 0.5, 0.5))
        axis_colour = self.theme.get("canvas_axis", (0.5, 0.5, 0.5))

        self.render_text(f"[{group_name}]", start_x - 80, -40, z_depth, text_colour)

        GL.glColor3f(*axis_colour)
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(start_x, -10, z_depth)
        GL.glVertex3f(max_x, -10, z_depth)
        GL.glEnd()

        for cycle in range(0, trace_length + 1):
            if cycle % 5 == 0:
                x_pos = start_x + cycle * step_x
                self.render_text(
                    str(cycle + self.cycle_offset),
                    x_pos - 2,
                    -25,
                    z_depth,
                    muted_colour,
                )
                GL.glBegin(GL.GL_LINES)
                GL.glVertex3f(x_pos, -10, z_depth)
                GL.glVertex3f(x_pos, -15, z_depth)
                GL.glEnd()

        GL.glEnable(GL.GL_LIGHTING)

    def draw_3d_ribbon(self, trace, start_x, base_y, z_depth, step_x, amplitude_y):
        """Render a 3D ribbon for a signal trace using horizontal segments
        and vertical connectors.

        It maps signal values to height levels and builds the geometry for
        OpenGL rendering.
        """
        if not trace:
            return
        ribbon_thickness = 3.0
        trace_height = 1.5
        z1 = z_depth + ribbon_thickness
        z2 = z_depth - ribbon_thickness
        t_arr = np.array(trace)
        y_arr = np.full(len(trace), base_y + amplitude_y / 2.0, dtype=np.float32)
        high_mask = (t_arr == self.devices.HIGH) | (t_arr == self.devices.RISING)
        low_mask = (t_arr == self.devices.LOW) | (t_arr == self.devices.FALLING)
        y_arr[high_mask] = base_y + amplitude_y
        y_arr[low_mask] = base_y
        x1_arr = start_x + np.arange(len(trace), dtype=np.float32) * step_x
        x2_arr = x1_arr + step_x
        y1_arr = y_arr - trace_height
        y2_arr = y_arr + trace_height
        vertices = []
        normals = []

        def add_box_vectorised(x_start, x_end, y_min, y_max):
            """Append vertex and normal arrays for a batch of rectangular
            prism segments.

            This helper builds the six faces of each box in a vectorised
            form for efficient GPU submission.
            """
            N = len(x_start)
            z1_arr = np.full(N, z1, dtype=np.float32)
            z2_arr = np.full(N, z2, dtype=np.float32)
            v_front = np.stack(
                [
                    x_start,
                    y_min,
                    z1_arr,
                    x_end,
                    y_min,
                    z1_arr,
                    x_end,
                    y_max,
                    z1_arr,
                    x_start,
                    y_max,
                    z1_arr,
                ],
                axis=-1,
            ).reshape(N, 4, 3)
            n_front = np.tile([0, 0, 1], (N, 4, 1))
            v_back = np.stack(
                [
                    x_start,
                    y_min,
                    z2_arr,
                    x_start,
                    y_max,
                    z2_arr,
                    x_end,
                    y_max,
                    z2_arr,
                    x_end,
                    y_min,
                    z2_arr,
                ],
                axis=-1,
            ).reshape(N, 4, 3)
            n_back = np.tile([0, 0, -1], (N, 4, 1))
            v_top = np.stack(
                [
                    x_start,
                    y_max,
                    z1_arr,
                    x_end,
                    y_max,
                    z1_arr,
                    x_end,
                    y_max,
                    z2_arr,
                    x_start,
                    y_max,
                    z2_arr,
                ],
                axis=-1,
            ).reshape(N, 4, 3)
            n_top = np.tile([0, 1, 0], (N, 4, 1))
            v_bottom = np.stack(
                [
                    x_start,
                    y_min,
                    z1_arr,
                    x_start,
                    y_min,
                    z2_arr,
                    x_end,
                    y_min,
                    z2_arr,
                    x_end,
                    y_min,
                    z1_arr,
                ],
                axis=-1,
            ).reshape(N, 4, 3)
            n_bottom = np.tile([0, -1, 0], (N, 4, 1))
            v_left = np.stack(
                [
                    x_start,
                    y_min,
                    z1_arr,
                    x_start,
                    y_max,
                    z1_arr,
                    x_start,
                    y_max,
                    z2_arr,
                    x_start,
                    y_min,
                    z2_arr,
                ],
                axis=-1,
            ).reshape(N, 4, 3)
            n_left = np.tile([-1, 0, 0], (N, 4, 1))
            v_right = np.stack(
                [
                    x_end,
                    y_min,
                    z1_arr,
                    x_end,
                    y_min,
                    z2_arr,
                    x_end,
                    y_max,
                    z2_arr,
                    x_end,
                    y_max,
                    z1_arr,
                ],
                axis=-1,
            ).reshape(N, 4, 3)
            n_right = np.tile([1, 0, 0], (N, 4, 1))
            vertices.append(
                np.concatenate(
                    [v_front, v_back, v_top, v_bottom, v_left, v_right], axis=1
                ).reshape(-1, 3)
            )
            normals.append(
                np.concatenate(
                    [n_front, n_back, n_top, n_bottom, n_left, n_right], axis=1
                ).reshape(-1, 3)
            )

        add_box_vectorised(x1_arr, x2_arr, y1_arr, y2_arr)
        y_diff = np.diff(y_arr)
        change_idx = np.where(y_diff != 0)[0]
        if len(change_idx) > 0:
            cx = x2_arr[change_idx]
            cy1 = y_arr[change_idx]
            cy2 = y_arr[change_idx + 1]
            cx1_arr = cx - 0.5
            cx2_arr = cx + 0.5
            cy_min_arr = np.minimum(cy1, cy2) - trace_height
            cy_max_arr = np.maximum(cy1, cy2) + trace_height
            add_box_vectorised(cx1_arr, cx2_arr, cy_min_arr, cy_max_arr)
        all_verts = np.ascontiguousarray(
            np.concatenate(vertices, axis=0).astype(np.float32)
        )
        all_norms = np.ascontiguousarray(
            np.concatenate(normals, axis=0).astype(np.float32)
        )
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_NORMAL_ARRAY)
        GL.glVertexPointer(3, GL.GL_FLOAT, 0, all_verts)
        GL.glNormalPointer(GL.GL_FLOAT, 0, all_norms)
        GL.glDrawArrays(GL.GL_QUADS, 0, len(all_verts))
        GL.glDisableClientState(GL.GL_NORMAL_ARRAY)
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

    def draw_cycle_inspector_slice(
        self, inspector_x, max_y, signal_groups, start_x, spacing_y, amplitude_y
    ):
        """Draw a translucent vertical slice through the 3D stack with value labels."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        slice_colour = self.theme.get("canvas_trace", (0.2, 0.6, 1.0))
        GL.glColor4f(slice_colour[0], slice_colour[1], slice_colour[2], 0.25)

        z_front = 50
        z_back = self.z_planes["OUTPUTS"] - 50
        y_bottom = -30
        y_top = max_y + 30
        thickness = 1.0

        GL.glDepthMask(GL.GL_FALSE)
        GL.glBegin(GL.GL_QUADS)
        GL.glVertex3f(inspector_x - thickness, y_bottom, z_front)
        GL.glVertex3f(inspector_x - thickness, y_top, z_front)
        GL.glVertex3f(inspector_x - thickness, y_top, z_back)
        GL.glVertex3f(inspector_x - thickness, y_bottom, z_back)
        GL.glVertex3f(inspector_x + thickness, y_bottom, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_back)
        GL.glVertex3f(inspector_x + thickness, y_bottom, z_back)
        GL.glVertex3f(inspector_x - thickness, y_top, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_back)
        GL.glVertex3f(inspector_x - thickness, y_top, z_back)
        GL.glEnd()
        GL.glDepthMask(GL.GL_TRUE)

        # Draw value labels for each trace with depth testing
        for group_name, signals in signal_groups.items():
            if not signals:
                continue
            z_depth = self.z_planes[group_name]
            current_y = 0
            ordered_signals = list(reversed(signals))
            for name, monitor in ordered_signals:
                if self.cycle_inspector_index < len(monitor.trace):
                    value_text = self.signal_to_display_text(
                        monitor.trace[self.cycle_inspector_index]
                    )
                else:
                    value_text = "-"
                # Position text forward from z_depth so it's on top of own plane
                # but can be occluded by traces in front
                self.render_text(
                    value_text,
                    inspector_x + 6,
                    current_y + amplitude_y / 2,
                    z_depth + 20,
                    colour=self.theme.get("canvas_text"),
                )
                current_y += spacing_y

        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def render_text(self, text, x, y, z, colour=(1.0, 1.0, 1.0)):
        """Render raster text at a 3D OpenGL coordinate using GLUT bitmap
        characters.

        It disables lighting while drawing and supports simple newline
        handling.
        """
        if not GLUT_INITIALISED:
            return
        GL.glDisable(GL.GL_LIGHTING)
        GL.glColor3f(colour[0], colour[1], colour[2])
        GL.glRasterPos3f(x, y, z)
        font = GLUT.GLUT_BITMAP_HELVETICA_18
        for char in text:
            if char == "\n":
                y -= 15
                GL.glRasterPos3f(x, y, z)
            else:
                GLUT.glutBitmapCharacter(font, ord(char))
        GL.glEnable(GL.GL_LIGHTING)

    def signal_to_display_text(self, signal):
        """Return the compact text shown by the cycle inspector for a signal."""
        if signal == self.devices.HIGH or signal == self.devices.RISING:
            return "1"
        if signal == self.devices.LOW or signal == self.devices.FALLING:
            return "0"
        if signal == self.devices.BLANK:
            return "-"
        return str(signal)

    def snap_reset_view(self):
        """Set the camera to an isometric side view and recalculate
        framing.

        This provides a balanced perspective of the 3D planes.
        """
        self.SetCurrent(self.context)
        self.camera_pitch = 25.0
        self.camera_yaw = -35.0
        self._calculate_focal_and_zoom()

    def snap_front_view(self):
        """Set the camera to a flat front view and recalculate framing.

        This shows the planes without perspective rotation.
        """
        self.SetCurrent(self.context)
        self.camera_pitch = 0.0
        self.camera_yaw = 0.0
        self._calculate_focal_and_zoom()

    def _calculate_focal_and_zoom(self):
        """Recalculate the focal point and camera distance so all visible
        signals fit tightly within the view.
        """
        size = self.GetClientSize()
        if size.width < 50 or size.height < 50:
            self._needs_framing_on_show = True
            return

        signal_groups = self.categorise_signals()

        active_z_depths = [
            self.z_planes[group] for group, signals in signal_groups.items() if signals
        ]

        if active_z_depths:
            self.focal_z = (min(active_z_depths) + max(active_z_depths)) / 2.0
        else:
            self.focal_z = -150.0

        max_signals_in_a_plane = max(
            [len(sigs) for sigs in signal_groups.values()] + [0]
        )

        step_x = 20.0
        spacing_y = 30.0
        amplitude_y = 15.0
        start_x = -150.0

        min_y = -40.0
        max_y = max(0, max_signals_in_a_plane - 1) * spacing_y + amplitude_y
        total_height = max_y - min_y
        self.focal_y = min_y + (total_height / 2.0)

        max_len = max(
            [len(m.trace) for m in self.monitors.monitors_dictionary.values()] + [10]
        )
        min_x = start_x - 80.0
        max_x = start_x + (max_len * step_x)
        total_width = max_x - min_x
        self.focal_x = min_x + (total_width / 2.0)

        aspect = size.width / size.height
        pad_x = 80.0
        pad_y = 80.0

        half_fov_y_rad = np.radians(22.5)
        half_fov_x_rad = np.arctan(np.tan(half_fov_y_rad) * aspect)

        dist_y = ((total_height / 2.0) + pad_y) / np.tan(half_fov_y_rad)
        dist_x = ((total_width / 2.0) + pad_x) / np.tan(half_fov_x_rad)

        pitch_rad = np.radians(abs(self.camera_pitch))
        yaw_rad = np.radians(abs(self.camera_yaw))

        proj_dist_x = dist_x * (1.0 + np.sin(yaw_rad) * 0.5)
        proj_dist_y = dist_y * (1.0 + np.sin(pitch_rad) * 0.5)

        z_depth_spread = 0
        if active_z_depths:
            z_depth_spread = (max(active_z_depths) - min(active_z_depths)) / 2.0

        self.camera_distance = max(proj_dist_x, proj_dist_y, 250.0) + z_depth_spread

        self.init = False
        self.Refresh()

    def on_key(self, event):
        """Handle keyboard shortcuts for the 3D camera presets.

        Keys 1/F select front, 2/S select side and 3/T select top.
        """
        keycode = event.GetKeyCode()
        if keycode == ord("1") or keycode == ord("F"):
            self.snap_front_view()
        elif keycode == ord("2") or keycode == ord("R"):
            self.snap_reset_view()
        elif keycode == ord("B"):
            self.trace_bg_mode = (self.trace_bg_mode + 1) % 3
            self.Refresh()
        event.Skip()

    def on_paint(self, event):
        """Redraw the canvas in response to a paint event.

        This delegates directly to the render routine.
        """
        _ = wx.PaintDC(self)

        if not self.IsShownOnScreen():
            return

        self.SetCurrent(self.context)
        self.render()

    def on_size(self, event):
        """Mark the OpenGL state as stale after a canvas resize.

        The next render will update the projection settings.
        """
        self.init = False
        event.Skip()

    def on_mouse(self, event):
        """Handle mouse interaction for orbiting, panning and zooming the
        3D view.

        Dragging moves the camera and the mouse wheel zooms toward the
        pointer.
        """
        if not self.IsShownOnScreen():
            event.Skip()
            return
        self.SetCurrent(self.context)
        if event.ButtonDown():
            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
            self.SetFocus()
        if event.Dragging():
            dx = event.GetX() - self.last_mouse_x
            dy = event.GetY() - self.last_mouse_y
            if event.ShiftDown():
                speed = self.camera_distance / 1000.0
                yaw_rad = np.radians(self.camera_yaw)
                self.focal_x -= dx * np.cos(yaw_rad) * speed
                self.focal_z -= dx * np.sin(yaw_rad) * speed
                self.focal_y += dy * speed
            elif event.LeftIsDown():
                speed = 0.5
                self.camera_yaw += dx * speed
                self.camera_pitch += dy * speed
                self.camera_pitch = max(-89.0, min(89.0, self.camera_pitch))
            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
            self.init = False
        wheel = event.GetWheelRotation()
        if wheel != 0:
            hit = self.get_world_on_focal_plane(event.GetX(), event.GetY())
            factor = 0.9 if wheel > 0 else 1.1
            self.camera_distance *= factor
            if hit:
                self.focal_x = self.focal_x + (hit[0] - self.focal_x) * (1.0 - factor)
                self.focal_y = self.focal_y + (hit[1] - self.focal_y) * (1.0 - factor)
            self.init = False
        self.Refresh()
