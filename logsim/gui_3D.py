"""Implement the 3D graphical user interface for the Logic Simulator.

This module provides a highly efficient 3D OpenGL canvas that categorises
and renders logic simulator traces along the Z-axis to visualise data flow
(Inputs -> Nets -> Outputs).

Classes:
--------
Canvas3D - handles all 3D canvas drawing, categorisation, and interactions.
"""

import math

import numpy as np
import wx
import wx.glcanvas as wxcanvas
from OpenGL import GL, GLU, GLUT

# To avoid repeated initialisation warnings on some platforms
GLUT_INITIALISED = False


def initialise_glut_once():
    """Initialise GLUT once per process safely."""
    global GLUT_INITIALISED
    if not GLUT_INITIALISED:
        try:
            GLUT.glutInit()
            GLUT_INITIALISED = True
        except Exception:
            pass


class Canvas3D(wxcanvas.GLCanvas):
    """Handle all 3D drawing operations and data-flow visualisation.

    This canvas projects the 2D logic traces into a 3D perspective space,
    separating signals onto physical Z-planes based on their causal origin:
    Inputs (Z=0), Nets (Z=-100), and Outputs (Z=-200).

    Parameters
    ----------
    parent: parent window.
    devices: instance of the devices.Devices() class.
    monitors: instance of the monitors.Monitors() class.
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

        # Simulator State
        self.devices = devices
        self.monitors = monitors

        # UI state (synced from main GUI)
        self.cycle_offset = 0
        self.cycle_inspector_enabled = False
        self.cycle_inspector_index = 0
        self.render_size_override = None

        # Fallback theme (will be overwritten by the main GUI theme)
        self.theme = {
            "canvas_bg": (0.08, 0.09, 0.10),
            "canvas_text": (0.88, 0.90, 0.94),
            "canvas_grid": (0.18, 0.20, 0.24),
            "canvas_trace": (0.42, 0.68, 1.0),
        }

        # 3D depth planes configuration
        self.z_planes = {"INPUTS": 0.0, "NETS": -150.0, "OUTPUTS": -300.0}

        # Camera & Navigation State
        self.pan_x = 0
        self.pan_y = 0
        self.zoom = 1.0
        self.depth_offset = 250  # Start pushed back so Z=0 is visible
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.scene_rotate = np.identity(4, "f")
        self.snap_side_view()  # Start in a clean, readable default angle

        # Bind Event Handlers
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.on_mouse)
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def initialise_gl(self):
        """Configure and initialise the OpenGL 3D context."""
        size = self.GetClientSize()
        if size.width == 0 or size.height == 0:
            return

        self.SetCurrent(self.context)

        # Clear background to theme color
        bg = self.theme.get("canvas_bg", (0, 0, 0))
        GL.glClearColor(bg[0], bg[1], bg[2], 1.0)

        # Setup Perspective Projection
        GL.glViewport(0, 0, size.width, size.height)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(45, size.width / size.height, 10, 10000)

        # Setup ModelView & Lighting
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()

        # Lighting configuration
        ambient_light = [0.2, 0.2, 0.2, 1.0]
        diffuse_light = [0.8, 0.8, 0.8, 1.0]
        light_pos = [100.0, 200.0, 100.0, 0.0]

        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, ambient_light)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, diffuse_light)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, light_pos)

        # Materials and depth
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glShadeModel(GL.GL_SMOOTH)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_NORMALIZE)
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glCullFace(GL.GL_BACK)

        # Transform camera (pan, zoom, rotate)
        GL.glTranslatef(0.0, 0.0, -self.depth_offset)
        GL.glTranslatef(self.pan_x, self.pan_y, 0.0)
        GL.glMultMatrixf(self.scene_rotate)
        GL.glScalef(self.zoom, self.zoom, self.zoom)

    def categorise_signals(self):
        """Group active monitors into data flow planes (inputs, nets, outputs)."""
        inputs, nets, outputs = [], [], []

        for name, monitor in self.monitors.monitors_dictionary.items():
            device = self.devices.get_device(monitor.device_id)
            if device is None:
                continue

            # Determine origin
            is_input = device.device_kind in [self.devices.SWITCH, self.devices.CLOCK]

            # Maintenance addition compatibility:
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
        """Handle the core 3D drawing loop."""
        self.SetCurrent(self.context)
        if not self.init:
            self.initialise_gl()
            self.init = True

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        if not self.monitors.monitors_dictionary:
            self.render_text(
                "No active monitors. Add signals to see 3D Data Flow.",
                -50,
                0,
                0,
                color=self.theme.get("canvas_text"),
            )
            GL.glFlush()
            self.SwapBuffers()
            return

        # Layout parameters
        step_x = 20  # Time gap
        amplitude_y = 15  # Height of HIGH signal
        spacing_y = 30  # Vertical gap between different signals
        start_x = -150  # Offset so the start isn't off-screen left

        signal_groups = self.categorise_signals()

        # Calculate max bounds to size the transparent grids perfectly
        max_trace_len = max(
            len(m.trace) for m in self.monitors.monitors_dictionary.values()
        )
        max_x = start_x + (max_trace_len * step_x)

        # Render each Z-plane
        global_max_y = 0
        for group_name, signals in signal_groups.items():
            if not signals:
                continue

            z_depth = self.z_planes[group_name]
            max_y_for_plane = len(signals) * spacing_y
            global_max_y = max(global_max_y, max_y_for_plane)

            # 1. Draw the transparent grouping shelf
            self.draw_z_plane(group_name, z_depth, start_x, max_x, max_y_for_plane)

            # 2. Draw axes and labels for this shelf
            self.draw_axes(group_name, z_depth, start_x, max_x, max_trace_len, step_x)

            # 3. Draw the solid 3D signal ribbons
            current_y = 0
            for name, monitor in signals:
                trace_color = self.theme.get("canvas_trace", (0.2, 0.6, 1.0))
                GL.glColor3f(*trace_color)

                # Draw the name tag floating in front of the ribbon
                self.render_text(
                    name,
                    start_x - 60,
                    current_y + 4,
                    z_depth + 4,
                    self.theme.get("canvas_text"),
                )

                # Render the highly efficient continuous 3D ribbon
                self.draw_3d_ribbon(
                    monitor.trace, start_x, current_y, z_depth, step_x, amplitude_y
                )
                current_y += spacing_y

        # 4. Render the 3D Cycle Inspector Plane if enabled
        if self.cycle_inspector_enabled and max_trace_len > 0:
            inspector_x = (
                start_x + (self.cycle_inspector_index * step_x) + (step_x / 2.0)
            )
            self.draw_cycle_inspector_slice(inspector_x, global_max_y)

        GL.glFlush()
        self.SwapBuffers()

    def draw_z_plane(self, name, z_depth, start_x, max_x, max_y):
        """Draw a semi-transparent coloured floor grid for a specific data plane."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        # Tint planes based on logic depth
        if name == "INPUTS":
            GL.glColor4f(0.3, 0.8, 0.4, 0.1)  # Green tint
        elif name == "NETS":
            GL.glColor4f(0.9, 0.6, 0.2, 0.1)  # Orange tint
        else:
            GL.glColor4f(0.9, 0.3, 0.3, 0.1)  # Red tint

        pad = 20
        # Main plane floor
        GL.glBegin(GL.GL_QUADS)
        GL.glVertex3f(start_x - pad, -pad, z_depth)
        GL.glVertex3f(max_x + pad, -pad, z_depth)
        GL.glVertex3f(max_x + pad, max_y + pad, z_depth)
        GL.glVertex3f(start_x - pad, max_y + pad, z_depth)
        GL.glEnd()

        # Grid lines (x/y)
        grid_col = self.theme.get("canvas_grid", (0.5, 0.5, 0.5))
        GL.glColor4f(grid_col[0], grid_col[1], grid_col[2], 0.3)
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
            x += 100  # Major grid intervals
        GL.glEnd()

        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def draw_axes(self, group_name, z_depth, start_x, max_x, trace_length, step_x):
        """Draw cycle numbers and the massive layer label."""
        GL.glDisable(GL.GL_LIGHTING)
        col = self.theme.get("canvas_text", (1, 1, 1))

        # Giant plane label
        self.render_text(f"[{group_name}]", start_x - 80, -40, z_depth, col)

        # Cycle axis line
        GL.glColor3f(col[0] * 0.5, col[1] * 0.5, col[2] * 0.5)
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(start_x, -10, z_depth)
        GL.glVertex3f(max_x, -10, z_depth)
        GL.glEnd()

        # Cycle numbers
        for cycle in range(0, trace_length + 1):
            if cycle % 5 == 0:  # Only label every 5 cycles to prevent clustering
                x_pos = start_x + (cycle * step_x)
                self.render_text(
                    str(cycle + self.cycle_offset), x_pos - 2, -25, z_depth, col
                )

                # Axis tick marks
                GL.glBegin(GL.GL_LINES)
                GL.glVertex3f(x_pos, -10, z_depth)
                GL.glVertex3f(x_pos, -15, z_depth)
                GL.glEnd()

        GL.glEnable(GL.GL_LIGHTING)

    def draw_3d_ribbon(self, trace, start_x, base_y, z_depth, step_x, amplitude_y):
        """Vectorised-style rendering of a 3D signal track using quad strips."""
        ribbon_thickness = 2.0
        z_front = z_depth + ribbon_thickness
        z_back = z_depth - ribbon_thickness

        GL.glBegin(GL.GL_QUAD_STRIP)
        for i, val in enumerate(trace):
            x = start_x + (i * step_x)

            # Determine Y based on signal state
            if val in [self.devices.HIGH, self.devices.RISING]:
                y = base_y + amplitude_y
            elif val in [self.devices.LOW, self.devices.FALLING]:
                y = base_y
            else:
                y = base_y + (
                    amplitude_y / 2.0
                )  # Floating mid-state for blank/undefined

            # Current segment vertices
            GL.glNormal3f(0, 1, 0)
            GL.glVertex3f(x, y, z_front)
            GL.glVertex3f(x, y, z_back)
            GL.glVertex3f(x + step_x, y, z_front)
            GL.glVertex3f(x + step_x, y, z_back)

            # Connecting vertical face to next value
            if i + 1 < len(trace):
                next_val = trace[i + 1]
                if next_val in [self.devices.HIGH, self.devices.RISING]:
                    next_y = base_y + amplitude_y
                elif next_val in [self.devices.LOW, self.devices.FALLING]:
                    next_y = base_y
                else:
                    next_y = base_y + (amplitude_y / 2.0)

                if next_y != y:
                    # Draw vertical connector
                    if next_y > y:
                        GL.glNormal3f(1, 0, 0)
                    else:
                        GL.glNormal3f(-1, 0, 0)

                    GL.glVertex3f(x + step_x, next_y, z_front)
                    GL.glVertex3f(x + step_x, next_y, z_back)

        GL.glEnd()

    def draw_cycle_inspector_slice(self, inspector_x, max_y):
        """Draws a glowing 3D plane that slices through all Z-layers at a specific cycle."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        # High-visibility glowing gold
        GL.glColor4f(1.0, 0.8, 0.2, 0.3)

        z_front = 50
        z_back = self.z_planes["OUTPUTS"] - 50
        y_bottom = -30
        y_top = max_y + 30
        thickness = 1.0

        # Draw volumetric pillar
        GL.glBegin(GL.GL_QUADS)
        # Left Face
        GL.glVertex3f(inspector_x - thickness, y_bottom, z_front)
        GL.glVertex3f(inspector_x - thickness, y_top, z_front)
        GL.glVertex3f(inspector_x - thickness, y_top, z_back)
        GL.glVertex3f(inspector_x - thickness, y_bottom, z_back)

        # Right Face
        GL.glVertex3f(inspector_x + thickness, y_bottom, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_back)
        GL.glVertex3f(inspector_x + thickness, y_bottom, z_back)

        # Top Face
        GL.glVertex3f(inspector_x - thickness, y_top, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_front)
        GL.glVertex3f(inspector_x + thickness, y_top, z_back)
        GL.glVertex3f(inspector_x - thickness, y_top, z_back)
        GL.glEnd()

        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def render_text(self, text, x, y, z, color=(1.0, 1.0, 1.0)):
        """Draw 3D spatial text utilising GLUT."""
        if not GLUT_INITIALISED:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glColor3f(color[0], color[1], color[2])
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
        """Camera shortcut: look down the Z-axis (isometric slant)."""
        self.scene_rotate = np.identity(4, "f")
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glRotatef(30, 1, 0, 0)  # Pitch down 30 deg
        GL.glRotatef(-45, 0, 1, 0)  # Yaw left 45 deg
        GL.glGetFloatv(GL.GL_MODELVIEW_MATRIX, self.scene_rotate)
        self.pan_x = 0
        self.pan_y = 0
        self.zoom = 0.8
        self.init = False
        self.Refresh()

    def snap_front_view(self):
        """Camera shortcut: flat 2D-style view of the front plane."""
        self.scene_rotate = np.identity(4, "f")
        self.pan_x = 0
        self.pan_y = 0
        self.zoom = 1.0
        self.init = False
        self.Refresh()

    def snap_top_view(self):
        """Camera shortcut: look down the Y-axis to see depth separation."""
        self.scene_rotate = np.identity(4, "f")
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glRotatef(90, 1, 0, 0)  # Pitch down 90 deg
        GL.glGetFloatv(GL.GL_MODELVIEW_MATRIX, self.scene_rotate)
        self.pan_x = 0
        self.pan_y = -150
        self.zoom = 0.7
        self.init = False
        self.Refresh()

    def on_key(self, event):
        """Handle keyboard shortcuts for camera snapping."""
        keycode = event.GetKeyCode()
        if keycode == ord("1") or keycode == ord("F"):
            self.snap_front_view()
        elif keycode == ord("2") or keycode == ord("S"):
            self.snap_side_view()
        elif keycode == ord("3") or keycode == ord("T"):
            self.snap_top_view()
        event.Skip()

    def on_paint(self, event):
        """Trigger render loop on paint event."""
        self.render()

    def on_size(self, event):
        """Handle canvas resize gracefully."""
        self.init = False
        event.Skip()

    def on_mouse(self, event):
        """Handle 3D spatial navigation (rotate, pan, zoom)."""
        self.SetCurrent(self.context)

        if event.ButtonDown():
            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
            self.SetFocus()  # Required to capture keyboard shortcuts

        if event.Dragging():
            dx = event.GetX() - self.last_mouse_x
            dy = event.GetY() - self.last_mouse_y

            if event.LeftIsDown():
                # 3D matrix rotation
                GL.glMatrixMode(GL.GL_MODELVIEW)
                GL.glLoadIdentity()
                # Rotate around axis perpendicular to drag direction
                speed = 0.5
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 0:
                    GL.glRotatef(dist * speed, dy, dx, 0)
                GL.glMultMatrixf(self.scene_rotate)
                GL.glGetFloatv(GL.GL_MODELVIEW_MATRIX, self.scene_rotate)

            elif event.RightIsDown():
                # 3D x/y panning
                self.pan_x += dx * 0.5
                self.pan_y -= dy * 0.5

            self.last_mouse_x = event.GetX()
            self.last_mouse_y = event.GetY()
            self.init = False

        # Z-axis zooming via scroll wheel
        wheel = event.GetWheelRotation()
        if wheel != 0:
            factor = 1.1 if wheel > 0 else 0.9
            self.zoom *= factor
            self.init = False

        self.Refresh()
