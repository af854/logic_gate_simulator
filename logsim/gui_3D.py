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
        if self.IsShownOnScreen():
            self.SetCurrent(self.context)
            if enabled:
                GL.glEnable(GL.GL_MULTISAMPLE)
            else:
                GL.glDisable(GL.GL_MULTISAMPLE)
        self.Refresh()

    def _add_to_tree(self, tree, full_name, trace):
        """Helper to build a dictionary tree representing module hierarchies."""
        parts = full_name.split("->")
        modules = parts[:-1]
        signal = parts[-1]
        curr = tree
        for m in modules:
            if m not in curr:
                curr[m] = {}
            curr = curr[m]
        if "signals_at_this_level" not in curr:
            curr["signals_at_this_level"] = []
        curr["signals_at_this_level"].append((signal, trace))

    def draw_adaptive_text(self, text, start_x, max_x, y, z, colour):
        """Draw text perfectly anchored in 2D screen space to avoid 3D clipping,
        FOV blind spots, and zoom scaling issues.
        """
        if not GLUT_INITIALISED:
            return

        self.SetCurrent(self.context)
        mv = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX)
        proj = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX)
        view = GL.glGetIntegerv(GL.GL_VIEWPORT)

        try:
            # Project the 3D graph edges exactly to 2D screen pixels
            p_start = GLU.gluProject(start_x, y, z, mv, proj, view)
            p_max = GLU.gluProject(max_x, y, z, mv, proj, view)
        except ValueError:
            return

        # gluProject depth is 0.0 (near) to 1.0 (far). If both ends are behind the camera, abort.
        if (p_start[2] < 0.0 or p_start[2] > 1.0) and (
            p_max[2] < 0.0 or p_max[2] > 1.0
        ):
            return

        sx1, sy1 = p_start[0], p_start[1]
        sx2, sy2 = p_max[0], p_max[1]

        left_x = min(sx1, sx2)
        right_x = max(sx1, sx2)
        center_x = view[2] / 2.0

        # Find which edge is closest to the center of your screen
        dist_left = abs(left_x - center_x)
        dist_right = abs(right_x - center_x)

        font = GLUT.GLUT_BITMAP_HELVETICA_12
        text_width = sum(GLUT.glutBitmapWidth(font, ord(c)) for c in text)
        gap = 15.0  # Rigid pixel gap (unaffected by zoom)

        # Anchor logic: Prefer the side closest to screen center so it's always in FOV.
        # Fallback to the opposite side if the preferred side pushes the text off-screen.
        if dist_left < dist_right:
            final_x = left_x - gap - text_width
            final_y = sy1 if sx1 < sx2 else sy2
            # Fallback if pushed off the left edge of the window
            if final_x < 10 and (right_x + gap + text_width) < (view[2] - 10):
                final_x = right_x + gap
                final_y = sy2 if sx1 < sx2 else sy1
        else:
            final_x = right_x + gap
            final_y = sy2 if sx1 < sx2 else sy1
            # Fallback if pushed off the right edge of the window
            if (final_x + text_width) > (view[2] - 10) and (
                left_x - gap - text_width
            ) > 10:
                final_x = left_x - gap - text_width
                final_y = sy1 if sx1 < sx2 else sy2

        # --- 2D ORTHOGRAPHIC RENDER PASS ---
        # Temporarily switch from 3D to a flat 2D projection matching your window pixels
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GLU.gluOrtho2D(0, view[2], 0, view[3])

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)  # Ensure text is drawn strictly on top
        GL.glColor3f(colour[0], colour[1], colour[2])

        # Bulletproof raster position hack: The center of the screen is ALWAYS inside the frustum.
        # We anchor there, then use glBitmap to silently shift the pen to our target final_x/y.
        # This prevents OpenGL from culling the text string if final_x is slightly off-screen.
        center_y = view[3] / 2.0
        GL.glRasterPos2f(center_x, center_y)
        GL.glBitmap(0, 0, 0, 0, final_x - center_x, final_y - center_y, None)

        for char in text:
            GLUT.glutBitmapCharacter(font, ord(char))

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_LIGHTING)

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPopMatrix()

    def draw_adaptive_bottom_text(self, text, world_x, base_y, max_y, z, colour):
        """Draw text perfectly anchored in 2D screen space to the visual bottom
        of the background plane, automatically swapping sides if the camera flips.
        """
        if not GLUT_INITIALISED:
            return

        self.SetCurrent(self.context)
        mv = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX)
        proj = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX)
        view = GL.glGetIntegerv(GL.GL_VIEWPORT)

        pad = 20.0
        try:
            # Project the physical bottom and top bounds of the plane at this X coordinate
            p_bottom = GLU.gluProject(world_x, base_y - pad, z, mv, proj, view)
            p_top = GLU.gluProject(world_x, base_y + max_y + pad, z, mv, proj, view)
        except ValueError:
            return

        # Abort if completely behind the camera
        if (p_bottom[2] < 0.0 or p_bottom[2] > 1.0) and (
            p_top[2] < 0.0 or p_top[2] > 1.0
        ):
            return

        # Find which physical edge is visually closest to the bottom of the screen (lowest Y)
        if p_bottom[1] < p_top[1]:
            screen_y = p_bottom[1]
            screen_x = p_bottom[0]
        else:
            screen_y = p_top[1]
            screen_x = p_top[0]

        font = GLUT.GLUT_BITMAP_HELVETICA_12
        text_width = sum(GLUT.glutBitmapWidth(font, ord(c)) for c in text)
        gap_y = 12.0  # Rigid gap below the plane

        # Center the text horizontally on the tick mark, shift down vertically
        final_x = screen_x - (text_width / 2.0)
        final_y = screen_y - gap_y - 10.0  # extra space to account for character height

        # --- 2D ORTHOGRAPHIC RENDER PASS ---
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GLU.gluOrtho2D(0, view[2], 0, view[3])

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glColor3f(colour[0], colour[1], colour[2])

        # Anchor at center to prevent culling, then shift pen via glBitmap
        center_x = view[2] / 2.0
        center_y = view[3] / 2.0
        GL.glRasterPos2f(center_x, center_y)
        GL.glBitmap(0, 0, 0, 0, final_x - center_x, final_y - center_y, None)

        for char in text:
            GLUT.glutBitmapCharacter(font, ord(char))

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_LIGHTING)

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPopMatrix()

    def render(self):
        """Render the complete 3D scene mapping tree hierarchy to Z/Y depth offsets."""
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

        layout_blocks = self._compute_layout()
        if not layout_blocks:
            return

        max_trace_len = max(
            (len(m.trace) for m in self.monitors.monitors_dictionary.values())
        )
        max_x = start_x + max_trace_len * step_x

        GL.glLineWidth(2.0)

        default_plane_color = self.theme.get("canvas_grid", (0.18, 0.2, 0.24))

        # Determine if the base theme is light or dark based on average brightness
        is_dark_theme = sum(default_plane_color) / 3.0 < 0.5

        if is_dark_theme:
            # Dark theme: Add offsets to create slightly lighter, tinted variations
            cycle_colors = [
                (
                    min(1.0, default_plane_color[0] + 0.08),
                    min(1.0, default_plane_color[1] + 0.12),
                    min(1.0, default_plane_color[2] + 0.20),
                ),  # Muted Blueish
                (
                    min(1.0, default_plane_color[0] + 0.18),
                    min(1.0, default_plane_color[1] + 0.08),
                    min(1.0, default_plane_color[2] + 0.12),
                ),  # Muted Purple/Red
                (
                    min(1.0, default_plane_color[0] + 0.10),
                    min(1.0, default_plane_color[1] + 0.18),
                    min(1.0, default_plane_color[2] + 0.10),
                ),  # Muted Greenish
            ]
        else:
            # Light theme: Alpha is 0.35, so offsets must be drastically stronger to not wash out into white
            cycle_colors = [
                (
                    max(0.0, default_plane_color[0] - 0.40),
                    max(0.0, default_plane_color[1] - 0.30),
                    max(0.0, default_plane_color[2] - 0.10),
                ),  # Distinct Blueish
                (
                    max(0.0, default_plane_color[0] - 0.20),
                    max(0.0, default_plane_color[1] - 0.40),
                    max(0.0, default_plane_color[2] - 0.20),
                ),  # Distinct Purple/Red
                (
                    max(0.0, default_plane_color[0] - 0.40),
                    max(0.0, default_plane_color[1] - 0.10),
                    max(0.0, default_plane_color[2] - 0.40),
                ),  # Distinct Greenish
            ]

        # 1. Draw depth planes, labels, grids, and signal traces per fragmented block
        for block_idx, block in enumerate(layout_blocks):
            depth = block["depth"]
            plane_color = (
                cycle_colors[(depth - 1) % len(cycle_colors)]
                if depth > 0
                else default_plane_color
            )

            # Only draw backdrops and timeline axes if the block contains actual signals
            if block["signals"]:
                self.draw_z_plane(
                    "",
                    block["z"],
                    block["base_y"],
                    start_x,
                    max_x,
                    block["max_y"],
                    plane_color,
                )

                self.draw_axes(
                    "",
                    block["z"],
                    block["base_y"],
                    block["max_y"],
                    start_x,
                    max_x,
                    max_trace_len,
                    step_x,
                )

            if block.get("heading"):
                GL.glDepthMask(GL.GL_FALSE)
                self.draw_adaptive_text(
                    block["heading"],
                    start_x,
                    max_x,
                    block["top_y"] + 4,
                    block["z"] + 4,
                    self.theme.get("canvas_muted", (0.5, 0.5, 0.5)),
                )
                GL.glDepthMask(GL.GL_TRUE)

            for label, trace, y in block["signals"]:
                trace_colour = self.theme.get("canvas_trace", (0.11, 0.45, 0.95))
                GL.glDepthMask(GL.GL_FALSE)

                self.draw_adaptive_text(
                    label,
                    start_x,
                    max_x,
                    y + 4,
                    block["z"] + 4,
                    self.theme.get("canvas_text"),
                )

                GL.glDepthMask(GL.GL_TRUE)
                GL.glColor3f(*trace_colour)
                self.draw_3d_ribbon(trace, start_x, y, block["z"], step_x, amplitude_y)

        # 2. Draw bounding boxes around entire modules when multiple modules exist
        paths = set(b["path"] for b in layout_blocks)
        if len(paths) > 1:
            GL.glDisable(GL.GL_LIGHTING)
            GL.glLineWidth(2.0)
            GL.glEnable(GL.GL_LINE_STIPPLE)
            GL.glLineStipple(4, 0xAAAA)

            line_colour = self.theme.get("canvas_axis", (0.5, 0.5, 0.5))
            if is_dark_theme:
                GL.glColor3f(
                    min(1.0, line_colour[0] + 0.3),
                    min(1.0, line_colour[1] + 0.3),
                    min(1.0, line_colour[2] + 0.3),
                )
            else:
                GL.glColor3f(
                    max(0.0, line_colour[0] - 0.3),
                    max(0.0, line_colour[1] - 0.3),
                    max(0.0, line_colour[2] - 0.3),
                )

            for path in paths:
                p_blocks = [b for b in layout_blocks if b["path"] == path]
                if not p_blocks:
                    continue

                # Only draw the box if the module path contains signals at its depth
                if not any(b["signals"] for b in p_blocks):
                    continue

                # Set pad slightly larger than the z-plane padding (20.0) so it visually encompasses the grids
                box_pad = 24.0
                z_depth = p_blocks[0]["z"]
                box_top = max(b["base_y"] + b["max_y"] for b in p_blocks) + box_pad
                box_bottom = min(b["base_y"] for b in p_blocks) - box_pad
                box_left = start_x - box_pad
                box_right = max_x + box_pad

                GL.glBegin(GL.GL_LINE_LOOP)
                GL.glVertex3f(box_left, box_top, z_depth)
                GL.glVertex3f(box_right, box_top, z_depth)
                GL.glVertex3f(box_right, box_bottom, z_depth)
                GL.glVertex3f(box_left, box_bottom, z_depth)
                GL.glEnd()

            GL.glDisable(GL.GL_LINE_STIPPLE)
            GL.glEnable(GL.GL_LIGHTING)

        # 3. Draw hierarchical branching paths tracking from parent to child module
        if hasattr(self, "connections") and self.connections:
            GL.glDisable(GL.GL_LIGHTING)
            GL.glColor4f(0.4, 0.4, 0.45, 0.8)
            GL.glLineWidth(2.0)
            GL.glBegin(GL.GL_LINES)

            x_conn = start_x - 40
            for conn in self.connections:
                GL.glVertex3f(x_conn, conn["y1"], conn["z1"])
                GL.glVertex3f(x_conn, conn["y1"], conn["z2"])
                GL.glVertex3f(x_conn, conn["y1"], conn["z2"])
                GL.glVertex3f(x_conn, conn["y2"], conn["z2"])

            GL.glEnd()
            GL.glEnable(GL.GL_LIGHTING)

        if self.cycle_inspector_enabled and max_trace_len > 0:
            inspector_x = start_x + self.cycle_inspector_index * step_x + step_x / 2.0
            self.draw_cycle_inspector_slice(
                inspector_x, layout_blocks, start_x, spacing_y, amplitude_y
            )

        GL.glLineWidth(1.0)
        GL.glFlush()
        self.SwapBuffers()

    def draw_axes(
        self, group_name, z_depth, base_y, max_y, start_x, max_x, trace_length, step_x
    ):
        """Draw the plane label, axis line and cycle tick marks."""
        GL.glDisable(GL.GL_LIGHTING)

        text_colour = self.theme.get("canvas_text", (1, 1, 1))
        muted_colour = self.theme.get("canvas_muted", (0.5, 0.5, 0.5))
        axis_colour = self.theme.get("canvas_axis", (0.5, 0.5, 0.5))

        if group_name:
            text_str = f"[{group_name}]"
            self.draw_adaptive_text(
                text_str, start_x, max_x, base_y - 40, z_depth, text_colour
            )

        GL.glColor3f(*axis_colour)
        GL.glBegin(GL.GL_LINES)

        # Base horizontal axis line
        GL.glVertex3f(start_x, base_y - 10, z_depth)
        GL.glVertex3f(max_x, base_y - 10, z_depth)

        # Draw tick marks on BOTH sides of the plane
        for cycle in range(0, trace_length + 1):
            if cycle % 5 == 0:
                x_pos = start_x + cycle * step_x
                # Bottom ticks
                GL.glVertex3f(x_pos, base_y - 10, z_depth)
                GL.glVertex3f(x_pos, base_y - 15, z_depth)
                # Top ticks
                GL.glVertex3f(x_pos, base_y + max_y + 10, z_depth)
                GL.glVertex3f(x_pos, base_y + max_y + 15, z_depth)
        GL.glEnd()

        # Delegate the cycle numbers to the adaptive bottom projector
        for cycle in range(0, trace_length + 1):
            if cycle % 5 == 0:
                x_pos = start_x + cycle * step_x
                self.draw_adaptive_bottom_text(
                    str(cycle + self.cycle_offset),
                    x_pos,
                    base_y,
                    max_y,
                    z_depth,
                    muted_colour,
                )

        GL.glEnable(GL.GL_LIGHTING)

    def _compute_layout(self):
        """Compute Z and Y positioning for contiguous tree-based blocks.
        Dynamically splits background planes to accommodate nested branches,
        maintaining original insertion order, and records connection lines
        linking child modules to parent signals.
        """
        tree = {}

        for name, monitor in self.monitors.monitors_dictionary.items():
            parts = name.split("->")
            if len(parts) == 1:
                path = ()
                sig_name = parts[0]
            else:
                path = tuple(parts[:-1])
                sig_name = parts[-1]

            for i in range(len(path) + 1):
                ancestor_path = path[:i]
                if ancestor_path not in tree:
                    tree[ancestor_path] = []

            tree[path].append((sig_name, monitor.trace, name))

        self.connections = []

        def layout_group(current_path, depth, start_y):
            blocks = []
            current_y = start_y
            spacing_y = 30.0
            heading_spacing_y = 25.0
            gap_y = 15.0

            signals = tree.get(current_path, [])

            # Find immediate child module paths
            child_paths = [
                p
                for p in tree.keys()
                if len(p) == len(current_path) + 1 and p[:-1] == current_path
            ]
            child_paths.sort()

            insertions = {}
            for c_path in child_paths:
                mod_name = c_path[-1]
                idx = len(signals)
                for i, (sig_name, trace, full_name) in enumerate(signals):
                    if sig_name == mod_name or sig_name.startswith(mod_name + "."):
                        idx = i + 1
                insertions.setdefault(idx, []).append(c_path)

            i = 0
            while i <= len(signals):
                is_start_of_module = i == 0 and len(current_path) > 0

                # Close the current contiguous block of signals
                if i < len(signals) or is_start_of_module:
                    block = {
                        "depth": depth,
                        "z": depth * -250.0,
                        "top_y": current_y,
                        "signals": [],
                        "heading": None,
                        "path": current_path,  # Track the module path for dotted bounding boxes
                    }

                    if is_start_of_module:
                        block["heading"] = f"{current_path[-1]} internals"
                        current_y -= heading_spacing_y

                    while i < len(signals):
                        sig_name, trace, full_name = signals[i]
                        block["signals"].append((sig_name, trace, current_y))
                        current_y -= spacing_y
                        i += 1
                        if i in insertions:
                            break

                    # Lock the bottom to the actual last signal to prevent empty phantom rows
                    if block["signals"]:
                        block["bottom_y"] = block["signals"][-1][2]
                    else:
                        block["bottom_y"] = current_y

                    block["base_y"] = block["bottom_y"] - 15.0
                    block["max_y"] = block["top_y"] - block["bottom_y"] + 30.0
                    blocks.append(block)

                # Process child modules branching off the signal we just placed
                if i in insertions:
                    if len(blocks) > 0 and len(blocks[-1]["signals"]) > 0:
                        branch_y_start = blocks[-1]["signals"][-1][2]
                    else:
                        branch_y_start = (
                            blocks[-1]["top_y"] if len(blocks) > 0 else current_y
                        )

                    for c_path in insertions[i]:
                        child_start_y = current_y - gap_y
                        child_next_y, child_blocks = layout_group(
                            c_path, depth + 1, child_start_y
                        )
                        blocks.extend(child_blocks)

                        if child_blocks:
                            branch_y_end = child_blocks[0]["top_y"]
                            # Calculate the absolute visual lowest extent of the entire child subtree
                            min_child_y = min(
                                (b["base_y"] - 20.0)
                                if b["signals"]
                                else (b["top_y"] - 15.0)
                                for b in child_blocks
                            )
                        else:
                            branch_y_end = child_start_y
                            min_child_y = child_start_y

                        self.connections.append(
                            {
                                "z1": depth * -250.0,
                                "z2": (depth + 1) * -250.0,
                                "y1": branch_y_start,
                                "y2": branch_y_end,
                            }
                        )

                        # Shift parent plane completely past the actual rendered descendant footprint
                        axis_tolerance = 50.0
                        current_y = min_child_y - axis_tolerance

                if i == len(signals):
                    break

            return current_y, blocks

        _, all_blocks = layout_group((), depth=0, start_y=0.0)
        return all_blocks

    def draw_z_plane(self, name, z_depth, base_y, start_x, max_x, max_y, plane_color):
        """Draw a semi-transparent grid floor using calculated hues."""
        if self.trace_bg_mode == 0:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        line_colour = self.theme.get("canvas_axis", (0.5, 0.5, 0.5))
        pad = 20.0

        if self.trace_bg_mode == 2:
            GL.glColor4f(plane_color[0], plane_color[1], plane_color[2], 0.35)

            quad_verts = np.array(
                [
                    [start_x - pad, base_y - pad, z_depth],
                    [max_x + pad, base_y - pad, z_depth],
                    [max_x + pad, base_y + max_y + pad, z_depth],
                    [start_x - pad, base_y + max_y + pad, z_depth],
                ],
                dtype=np.float32,
            )

            GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, quad_verts)
            GL.glDrawArrays(GL.GL_QUADS, 0, 4)
            GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

        if self.trace_bg_mode in (1, 2):
            GL.glColor4f(line_colour[0], line_colour[1], line_colour[2], 0.25)

            y_vals = np.arange(base_y, base_y + max_y + pad + 1, 30, dtype=np.float32)
            h_lines = np.zeros((len(y_vals), 2, 3), dtype=np.float32)
            h_lines[:, 0, 0] = start_x - pad
            h_lines[:, 1, 0] = max_x + pad
            h_lines[:, :, 1] = y_vals[:, np.newaxis]
            h_lines[:, :, 2] = z_depth

            x_vals = np.arange(start_x, max_x + pad + 1, 100, dtype=np.float32)
            v_lines = np.zeros((len(x_vals), 2, 3), dtype=np.float32)
            v_lines[:, :, 0] = x_vals[:, np.newaxis]
            v_lines[:, 0, 1] = base_y - pad
            v_lines[:, 1, 1] = base_y + max_y + pad
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

    def draw_3d_ribbon(self, trace, start_x, base_y, z_depth, step_x, amplitude_y):
        """Render a 3D ribbon for a signal trace using horizontal segments
        and vertical connectors. Blank signals are ignored and not rendered.
        """
        if not trace:
            return

        t_arr = np.array(trace)
        # Filter out components that shouldn't exist yet before data begins
        valid_mask = t_arr != self.devices.BLANK
        if not np.any(valid_mask):
            return

        ribbon_thickness = 3.0
        trace_height = 1.5
        z1 = z_depth + ribbon_thickness
        z2 = z_depth - ribbon_thickness

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
            N = len(x_start)
            if N == 0:
                return
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

        # 1. Render flat ribbon segments only for populated data cycles
        add_box_vectorised(
            x1_arr[valid_mask],
            x2_arr[valid_mask],
            y1_arr[valid_mask],
            y2_arr[valid_mask],
        )

        # 2. Render vertical connectors strictly between adjacent valid signals
        valid_transitions = valid_mask[:-1] & valid_mask[1:]
        y_diff = y_arr[1:] - y_arr[:-1]
        change_idx = np.where((y_diff != 0) & valid_transitions)[0]

        if len(change_idx) > 0:
            cx = x2_arr[change_idx]
            cy1 = y_arr[change_idx]
            cy2 = y_arr[change_idx + 1]
            cx1_arr = cx - 0.5
            cx2_arr = cx + 0.5
            cy_min_arr = np.minimum(cy1, cy2) - trace_height
            cy_max_arr = np.maximum(cy1, cy2) + trace_height
            add_box_vectorised(cx1_arr, cx2_arr, cy_min_arr, cy_max_arr)

        if not vertices:
            return

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
        if self.IsShownOnScreen():
            self.SetCurrent(self.context)

        self.camera_pitch = 25.0
        self.camera_yaw = -35.0
        self._calculate_focal_and_zoom()

    def snap_front_view(self):
        """Set the camera to a flat front view and recalculate framing.

        This shows the planes without perspective rotation.
        """
        if self.IsShownOnScreen():
            self.SetCurrent(self.context)

        self.camera_pitch = 0.0
        self.camera_yaw = 0.0
        self._calculate_focal_and_zoom()

    def draw_cycle_inspector_slice(
        self, inspector_x, layout_blocks, start_x, spacing_y, amplitude_y
    ):
        """Draw a translucent vertical slice mapped to the computed dynamic bounds."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        slice_colour = self.theme.get("canvas_trace", (0.2, 0.6, 1.0))
        GL.glColor4f(slice_colour[0], slice_colour[1], slice_colour[2], 0.25)

        if layout_blocks:
            z_front = max(b["z"] for b in layout_blocks) + 50
            z_back = min(b["z"] for b in layout_blocks) - 50
            y_bottom = min(b["base_y"] for b in layout_blocks) - 30
            y_top = max(b["base_y"] + b["max_y"] for b in layout_blocks) + 30
        else:
            z_front, z_back, y_bottom, y_top = 50, -50, -30, 30

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

        for block in layout_blocks:
            for label, trace, y in block["signals"]:
                if self.cycle_inspector_index < len(trace):
                    value_text = self.signal_to_display_text(
                        trace[self.cycle_inspector_index]
                    )
                else:
                    value_text = "-"

                self.render_text(
                    value_text,
                    inspector_x + 6,
                    y + amplitude_y / 2.0,
                    block["z"] + 20,
                    colour=self.theme.get("canvas_text"),
                )

        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def _calculate_focal_and_zoom(self):
        """Recalculate framing dynamically using computed hierarchical layout bounds."""
        size = self.GetClientSize()
        if size.width < 50 or size.height < 50:
            self._needs_framing_on_show = True
            return

        layout_blocks = self._compute_layout()
        if not layout_blocks:
            self.focal_z = -150.0
            self.focal_y = 0.0
            self.focal_x = 0.0
            self.init = False
            self.Refresh()
            return

        z_depths = [b["z"] for b in layout_blocks]
        if not z_depths:
            z_depths = [0.0]
        self.focal_z = (min(z_depths) + max(z_depths)) / 2.0

        min_y = min(b["base_y"] for b in layout_blocks) - 40.0
        max_y = max(b["base_y"] + b["max_y"] for b in layout_blocks) + 15.0

        total_height = max_y - min_y
        self.focal_y = min_y + (total_height / 2.0)

        step_x = 20.0
        start_x = -150.0
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

        z_depth_spread = (max(z_depths) - min(z_depths)) / 2.0

        self.camera_distance = max(proj_dist_x, proj_dist_y, 250.0) + z_depth_spread

        self.init = False
        self.Refresh()

    def on_key(self, event):
        """Handle keyboard shortcuts for the 3D camera presets.

        Keys F select front, R reset view, and B cycle background mode.
        """
        keycode = event.GetKeyCode()

        if keycode == ord("F"):
            self.snap_front_view()
        elif keycode == ord("R"):
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
        """Handle mouse interaction for orbiting, panning and zooming the 3D view."""
        if not self.IsShownOnScreen():
            event.Skip()
            return
        self.SetCurrent(self.context)

        if not hasattr(self, "_drag_initialised"):
            self._drag_initialised = False

        if event.ButtonDown():
            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
            self._drag_initialised = True
            self.SetFocus()

        if event.ButtonUp() or event.Leaving():
            self._drag_initialised = False

        if event.Dragging():
            if not getattr(self, "_drag_initialised", False):
                self.last_mouse_x = event.GetX()
                self.last_mouse_y = event.GetY()
                self._drag_initialised = True
                return

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

            # Clamp zoom to prevent clipping through the near-plane and causing projection inversion
            if self.camera_distance * factor > 20.0:
                self.camera_distance *= factor
                if hit:
                    self.focal_x = self.focal_x + (hit[0] - self.focal_x) * (
                        1.0 - factor
                    )
                    self.focal_y = self.focal_y + (hit[1] - self.focal_y) * (
                        1.0 - factor
                    )
                self.init = False

        self.Refresh()
