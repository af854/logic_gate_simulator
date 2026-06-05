"""Implement the 3D graphical user interface for the Logic Simulator.

This module defines an OpenGL canvas that renders signal traces in three
dimensional space and groups inputs, nets and outputs onto separated depth
planes for clearer visual analysis.
"""

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
            GLUT.glutInit()
            GLUT_INITIALISED = True
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
                0,
            ],
        )
        initialise_glut_once()
        self.init = False
        self.context = wxcanvas.GLContext(self)
        self.devices = devices
        self.monitors = monitors
        self.cycle_offset = 0
        self.cycle_inspector_enabled = False
        self.cycle_inspector_index = 0
        self.render_size_override = None
        self.theme = {
            "canvas_bg": (0.08, 0.09, 0.1),
            "canvas_text": (0.88, 0.9, 0.94),
            "canvas_grid": (0.18, 0.2, 0.24),
            "canvas_trace": (0.42, 0.68, 1.0),
        }
        self.z_planes = {"INPUTS": 0.0, "NETS": -150.0, "OUTPUTS": -300.0}
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
            wx.CallAfter(self.snap_side_view)
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
        bg = self.theme.get("canvas_bg", (0, 0, 0))
        GL.glClearColor(bg[0], bg[1], bg[2], 1.0)
        GL.glViewport(0, 0, size.width, size.height)
        GL.glMatrixMode(GL.GL_PROJECTION)
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
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(45, size.width / size.height, 10, 10000)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glTranslatef(0.0, 0.0, -self.camera_distance)
        GL.glRotatef(self.camera_pitch, 1, 0, 0)
        GL.glRotatef(self.camera_yaw, 0, 1, 0)
        GL.glTranslatef(-self.focal_x, -self.focal_y, -self.focal_z)
        modelview = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX)
        projection = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX)
        viewport = GL.glGetIntegerv(GL.GL_VIEWPORT)
        win_y = float(viewport[3] - screen_y)
        win_x = float(screen_x)
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

    def categorise_signals(self):
        """Group active monitors into input, net and output planes.

        Input signals include switches, clocks and compatible signal
        generators. Nets and outputs are classified by their names.
        """
        inputs, nets, outputs = ([], [], [])
        for name, monitor in self.monitors.monitors_dictionary.items():
            device = self.devices.get_device(monitor.device_id)
            if device is None:
                continue
            is_input = device.device_kind in [self.devices.SWITCH, self.devices.CLOCK]
            if (
                hasattr(self.devices, "SIGGEN")
                and device.device_kind == self.devices.SIGGEN
            ):
                is_input = True
            if is_input:
                inputs.append((name, monitor))
            elif "->" in name or "." in name:
                nets.append((name, monitor))
            else:
                outputs.append((name, monitor))
        return {"INPUTS": inputs, "NETS": nets, "OUTPUTS": outputs}

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
                self.render_text(
                    name,
                    start_x - 60,
                    current_y + 4,
                    z_depth + 4,
                    colour=self.theme.get("canvas_text"),
                )
                GL.glColor3f(*trace_colour)
                self.draw_3d_ribbon(
                    monitor.trace, start_x, current_y, z_depth, step_x, amplitude_y
                )
                current_y += spacing_y
        if self.cycle_inspector_enabled and max_trace_len > 0:
            inspector_x = start_x + self.cycle_inspector_index * step_x + step_x / 2.0
            self.draw_cycle_inspector_slice(inspector_x, global_max_y)
        GL.glFlush()
        self.SwapBuffers()

    def draw_z_plane(self, name, z_depth, start_x, max_x, max_y):
        """Draw a semi-transparent grid floor at the given depth plane.

        This visually groups signals for inputs, nets and outputs.
        """
        GL.glDisable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        grid_colour = self.theme.get("canvas_grid", (0.5, 0.5, 0.5))
        GL.glColor4f(grid_colour[0], grid_colour[1], grid_colour[2], 0.15)
        pad = 20
        GL.glBegin(GL.GL_QUADS)
        GL.glVertex3f(start_x - pad, -pad, z_depth)
        GL.glVertex3f(max_x + pad, -pad, z_depth)
        GL.glVertex3f(max_x + pad, max_y + pad, z_depth)
        GL.glVertex3f(start_x - pad, max_y + pad, z_depth)
        GL.glEnd()
        GL.glColor4f(grid_colour[0], grid_colour[1], grid_colour[2], 0.3)
        GL.glBegin(GL.GL_LINES)
        y = 0
        while y <= max_y + pad:
            GL.glVertex3f(start_x - pad, y, z_depth)
            GL.glVertex3f(max_x + pad, y, z_depth)
            y += 30
        x = start_x
        while x <= max_x + pad:
            GL.glVertex3f(x, -pad, z_depth)
            GL.glVertex3f(x, max_y + pad, z_depth)
            x += 100
        GL.glEnd()
        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def draw_axes(self, group_name, z_depth, start_x, max_x, trace_length, step_x):
        """Draw the plane label, axis line and cycle tick marks for a
        depth plane.

        It also renders cycle numbers at regular intervals.
        """
        GL.glDisable(GL.GL_LIGHTING)
        text_colour = self.theme.get("canvas_text", (1, 1, 1))
        self.render_text(f"[{group_name}]", start_x - 80, -40, z_depth, text_colour)
        GL.glColor3f(text_colour[0] * 0.5, text_colour[1] * 0.5, text_colour[2] * 0.5)
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(start_x, -10, z_depth)
        GL.glVertex3f(max_x, -10, z_depth)
        GL.glEnd()
        for cycle in range(0, trace_length + 1):
            if cycle % 5 == 0:
                x_pos = start_x + cycle * step_x
                self.render_text(
                    str(cycle + self.cycle_offset), x_pos - 2, -25, z_depth, text_colour
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

    def draw_cycle_inspector_slice(self, inspector_x, max_y):
        """Draw a translucent vertical slice through the entire 3D stack
        at the selected cycle index.

        This highlights the current cycle across all signal planes.
        """
        GL.glDisable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glColor4f(1.0, 0.8, 0.2, 0.3)
        z_front = 50
        z_back = self.z_planes["OUTPUTS"] - 50
        y_bottom = -30
        y_top = max_y + 30
        thickness = 1.0
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
        font = GLUT.GLUT_BITMAP_HELVETICA_12
        for char in text:
            if char == "\n":
                y -= 15
                GL.glRasterPos3f(x, y, z)
            else:
                GLUT.glutBitmapCharacter(font, ord(char))
        GL.glEnable(GL.GL_LIGHTING)

    def snap_side_view(self):
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

    def snap_top_view(self):
        """Set the camera to a near-vertical top view and recalculate
        framing.

        This reveals the depth separation along the z-axis.
        """
        self.SetCurrent(self.context)
        self.camera_pitch = 89.0
        self.camera_yaw = 0.0
        self._calculate_focal_and_zoom()

    def _calculate_focal_and_zoom(self):
        """Recalculate the focal point and camera distance so all visible
        signals fit within the view.

        It uses a bounding sphere and the canvas aspect ratio to choose the
        zoom level.
        """
        size = self.GetClientSize()
        if size.width < 50 or size.height < 50:
            self._needs_framing_on_show = True
            return
        num_signals = len(self.monitors.monitors_dictionary)
        max_len = max(
            [len(m.trace) for m in self.monitors.monitors_dictionary.values()] + [10]
        )
        step_x = 20.0
        spacing_y = 40.0
        amplitude_y = 20.0
        total_width = max_len * step_x
        total_height = max(0, num_signals - 1) * spacing_y + amplitude_y
        self.focal_x = 0.0
        self.focal_y = total_height / 2.0
        self.focal_z = -150.0
        aspect = size.width / size.height
        dx_max = total_width
        dy_max = total_height / 2.0
        dz_max = 150.0
        radius = np.sqrt(dx_max**2 + dy_max**2 + dz_max**2)
        half_fov_y_rad = np.radians(22.5)
        half_fov_x_rad = np.arctan(np.tan(half_fov_y_rad) * aspect)
        dist_y = radius / np.sin(half_fov_y_rad)
        dist_x = radius / np.sin(half_fov_x_rad)
        self.camera_distance = max(dist_x, dist_y) * 1.1
        self.init = False
        self.Refresh()

    def on_key(self, event):
        """Handle keyboard shortcuts for the 3D camera presets.

        Keys 1/F select front, 2/S select side and 3/T select top.
        """
        keycode = event.GetKeyCode()
        if keycode == ord("1") or keycode == ord("F"):
            self.snap_front_view()
        elif keycode == ord("2") or keycode == ord("S"):
            self.snap_side_view()
        elif keycode == ord("3") or keycode == ord("T"):
            self.snap_top_view()
        event.Skip()

    def on_paint(self, event):
        """Redraw the canvas in response to a paint event.

        This delegates directly to the render routine.
        """
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
