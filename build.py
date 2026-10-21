"""Build (and optionally render) the i10 boot intro.

  Blender -b --factory-startup -P build.py -- --layout badge|equal --light glow|reflect
          [--quality mock|final] [--fps 30|60] [--stills 10,30,60] [--render] [--save]

Layout "badge": HYUNDAI caps are half the height of the "10".
Layout "equal": HYUNDAI caps are as tall as the "10".
Light "glow": a visible soft glow where the light is.
Light "reflect": the light is never in shot, only its reflection in the chrome.

The badges lie flat in the XY plane facing +Z; the camera looks straight down -Z.
Chrome on black reflects nothing, so two camera-invisible emitters above the badges
give the chrome something to reflect: a narrow tilted strip that travels with the
light (the moving highlight) and a wide fill plane whose lit area grows behind the
light (the glow the chrome keeps after the light has passed).
"""
import argparse
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Matrix

ROOT = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--layout", choices=["badge", "equal"], default="badge")
    p.add_argument("--light", choices=["glow", "reflect"], default="glow")
    p.add_argument("--quality", choices=["mock", "final"], default="mock")
    p.add_argument("--fps", type=int, choices=[30, 60], default=30)
    p.add_argument("--stills", default="")
    p.add_argument("--render", action="store_true")
    p.add_argument("--save", action="store_true")
    return p.parse_args(argv)


ARGS = parse_args()
# The timing below is in 30 fps frames (frame 1 = 0 s), as it was designed: LENGTH of
# them, 5 s. The clip is rendered at FPS, TICK clip frames to each timing frame.
LENGTH = 150
FPS = ARGS.fps
TICK = FPS / 30
FRAMES = round(LENGTH * TICK)

FRAME_W = 10.0                 # visible width at the badge plane
GROUP_W = FRAME_W * 0.86       # HYUNDAI + gap + i10
LENS, SENSOR = 100.0, 36.0
CAM_D = FRAME_W * LENS / SENSOR

# How far away the light is (1.0 = mockup round 2). Its size scales with the
# distance, so it keeps the same apparent size seen from the badges, and its power
# scales with the distance squared, so it keeps the same brightness.
LIGHT_DIST = 2.0
STRIP_Z = 10.0 * LIGHT_DIST    # height of the moving highlight strip
FILL_Z = 8.0                   # height of the fill plane
STRIP_K = 1 + STRIP_Z / CAM_D  # badge x -> strip x for a mirror face
FILL_K = 1 + FILL_Z / CAM_D
KEY_Z = 4.5 * LIGHT_DIST       # height of the key light above the badges
# Round 9, after a frame-by-frame study of the Lucasfilm logo. The chrome is dark and
# polished: its faces mirror a dim room, and the light itself only shows as bright
# lines along the letter edges. So the key is a short horizontal strip north of the
# badges, out of the faces' mirror path: the top edges under it catch it as lines,
# and those lines travel with it. The room lights up around and behind the light.
KEY_LEN, KEY_WIDTH = 2.4, 0.6   # strip size (x, y)
# How far north (and south) of the badges' edge the strips sit. Far enough out that
# the flat faces barely pick up their sheen, so the faces keep the room's brightness
# after the light has passed; the rounded edges still catch them.
KEY_Y_OFF = 6.5
KEY_POWER = 10000.0
SOUTH_SHARE = 0.5   # a weaker twin strip south of the badges lights the bottom edges
CORE_POWER, CORE_RADIUS = 2000.0, 0.08  # a small hot core in the north strip: sparkles
# The lights are focused: each one only reaches the letters near it, so the glints
# follow the light instead of every edge that faces it lighting up at once.
BEAM = 35.0   # beam angle, degrees


def smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


# The light's path and brightness, as (frame, value) keys, one per frame. Frames up to
# START and from END on are black. The light comes in from the left of the H, crosses
# both badges and leaves past the end of the 0, a little slower at the start and end
# (SPEED_EASE: 0 = even speed, 1 = full ease in and out).
START, END = 6, LENGTH - 6
# The fully lit logo is held for HOLD frames at FADE, then fades out as before. The
# sweep itself is timed without the hold, from START to SWEEP_END.
HOLD = 30
SWEEP_END = END - HOLD
X_FROM, X_TO = -6.0, 8.0
SPEED_EASE = 0.45
# Brightness builds the whole way across until PEAK, then fades out by END. The build
# is a power curve (GAMMA) so it looks even on screen, not fast then flat.
PEAK, FADE = 96, 100
GAMMA = 2.2


def light_x(f):
    """Past SWEEP_END the light keeps going right at the speed it ends the sweep with."""
    t = (f - START) / (SWEEP_END - START)
    return X_FROM + (X_TO - X_FROM) * ((1 - SPEED_EASE) * t + SPEED_EASE * smoothstep(t))


def light_on(f):
    if f <= PEAK:
        return min(1.0, max(0.0, (f - START) / (PEAK - START))) ** GAMMA
    if f <= FADE:
        return 1.0
    return (1.0 - smoothstep((f - FADE) / (SWEEP_END - FADE))) ** GAMMA


# The strips and core dim as they move past the end of the 0, so at the peak the
# whole logo is lit evenly by the room instead of the i10 still getting the light.
EXIT_X, EXIT_W, EXIT_DIM = 4.4, 2.5, 0.65


def key_on(f, x):
    return light_on(f) * (1.0 - EXIT_DIM * smoothstep((x - EXIT_X) / EXIT_W))


def sweep_frame(f):
    """The frame of the brightness shown at clip frame f: it stops at FADE for HOLD
    frames. The light itself keeps moving."""
    return f if f <= FADE else max(FADE, f - HOLD)


def clip_frame(u):
    """The clip frame shown at timing frame u."""
    return 1 + (u - 1) * TICK


def timing(f):
    """The timing frame at clip frame f."""
    return 1 + (f - 1) / TICK


# One key on every clip frame from the light coming on to the end of the fade.
KEY_FRAMES = range(round(clip_frame(START)), round(clip_frame(END)) + 1)
LIGHT_X = [(f, light_x(timing(f))) for f in KEY_FRAMES]
LIGHT_ON = [(f, light_on(sweep_frame(timing(f)))) for f in KEY_FRAMES]
KEY_ON = [(f, key_on(sweep_frame(timing(f)), light_x(timing(f)))) for f in KEY_FRAMES]
FILL_ON = LIGHT_ON
# The room: lit around the light, and it stays lit behind the light (TRAIL), so the
# badges light up from left to right. Widths are on the badge plane.
AHEAD_W = 1.6     # how far ahead of the light the room is lit
BEHIND_W = 3.0    # how far behind the light it stays fully lit
TRAIL = 1.0       # the room stays fully lit once the light has passed
ROOM_MIN = 0.04   # the room far ahead of the light
# Only the part of the room above the badges is lit. Without this, edges that tilt
# towards the left mirror the far left of the room, which the light has already lit,
# so every outline shows before the light gets there.
ROOM_HALF, ROOM_SOFT = 4.7, 1.5
FILL_STRENGTH = 0.85
# Only the edge highlights are bright enough to bloom, so they glisten.
BLOOM_THRESHOLD, BLOOM_STRENGTH = 1.5, 0.45


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.lights, bpy.data.cameras, bpy.data.materials):
        for block in list(coll):
            coll.remove(block)


def key(owner, path, keys, index=-1, linear=False):
    edit = bpy.context.preferences.edit
    old = edit.keyframe_new_interpolation_type
    edit.keyframe_new_interpolation_type = "LINEAR" if linear else "BEZIER"
    for frame, value in keys:
        if index >= 0:
            getattr(owner, path)[index] = value
        else:
            setattr(owner, path, value)
        owner.keyframe_insert(path, frame=frame, index=index)
    edit.keyframe_new_interpolation_type = old


def scaled(keys, k, offset=0.0):
    return [(f, v * k + offset) for f, v in keys]


# ---------------------------------------------------------------- outlines

def import_outline(svg_name):
    """Import an SVG as one flat 2D curve with its transform applied."""
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=os.path.join(ROOT, "assets", svg_name))
    new = [o for o in bpy.data.objects if o not in before and o.type == "CURVE"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    obj.data.dimensions = "2D"
    obj.data.fill_mode = "BOTH"
    return obj


def spline_boxes(obj):
    boxes = []
    for s in obj.data.splines:
        xs = [p.co.x for p in s.bezier_points] + [p.handle_left.x for p in s.bezier_points] + [p.handle_right.x for p in s.bezier_points]
        ys = [p.co.y for p in s.bezier_points] + [p.handle_left.y for p in s.bezier_points] + [p.handle_right.y for p in s.bezier_points]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes


def place(obj, scale, dx, dy):
    obj.data.transform(Matrix.Translation((dx, dy, 0)) @ Matrix.Scale(scale, 4))


def measure_i10(obj):
    """Return (left, baseline, right, top, h10) of the traced i10.

    The tallest spline is the outer "0", the next tallest is the "1"; the "10"
    height is the 0's height and the baseline is the bottom of the 1.
    """
    boxes = spline_boxes(obj)
    by_height = sorted(boxes, key=lambda b: b[3] - b[1], reverse=True)
    zero, one = by_height[0], by_height[1]
    left = min(b[0] for b in boxes)
    right = max(b[2] for b in boxes)
    top = max(b[3] for b in boxes)
    return left, one[1], right, top, zero[3] - zero[1]


def build_badges(layout):
    hy = import_outline("hyundai.svg")
    i10 = import_outline("i10.svg")
    hy.name, i10.name = "HYUNDAI", "i10"

    hb = spline_boxes(hy)
    hy_l, hy_b = min(b[0] for b in hb), min(b[1] for b in hb)
    hy_r, hy_t = max(b[2] for b in hb), max(b[3] for b in hb)
    hy_aspect = (hy_r - hy_l) / (hy_t - hy_b)

    i_l, i_base, i_r, i_t, i_h10 = measure_i10(i10)
    i_w_per_h10 = (i_r - i_l) / i_h10
    i_top_per_h10 = (i_t - i_base) / i_h10

    cap_ratio = 0.5 if layout == "badge" else 1.0
    gap = 0.5
    h10 = GROUP_W / (hy_aspect * cap_ratio + gap + i_w_per_h10)
    cap = h10 * cap_ratio

    # Centre the pair: the i10 is the taller of the two in both layouts.
    group_h = max(i_top_per_h10 * h10, cap)
    base_y = -group_h / 2
    x0 = -GROUP_W / 2

    s = cap / (hy_t - hy_b)
    place(hy, s, x0 - hy_l * s, base_y - hy_b * s)
    s = h10 / i_h10
    place(i10, s, x0 + (hy_aspect * cap + gap * h10) - i_l * s, base_y - i_base * s)

    for obj, ref in ((hy, cap), (i10, h10)):
        c = obj.data
        bevel = 0.03 * ref
        c.bevel_mode = "ROUND"
        c.bevel_depth = bevel
        c.bevel_resolution = 6
        c.offset = -bevel
        c.extrude = max(0.0, 0.045 * ref - bevel)
        c.resolution_u = 24
        c.materials.clear()  # drop the importer's flat SVG colour
        for sp in c.splines:
            sp.use_smooth = True
            for p in sp.bezier_points:
                p.radius = 1.0  # Curve.transform scales radii, which scales the bevel
    print(f"layout {layout}: h10={h10:.3f} cap={cap:.3f} group_h={group_h:.3f}")
    hb, ib = spline_boxes(hy), spline_boxes(i10)
    info = {
        "group_h": group_h,
        "hy_y": (min(b[1] for b in hb), max(b[3] for b in hb)),
        "i10_y": (min(b[1] for b in ib), max(b[3] for b in ib)),
        "split_x": (max(b[2] for b in hb) + min(b[0] for b in ib)) / 2,
    }
    return hy, i10, info


# ---------------------------------------------------------------- materials

def chrome_material():
    m = bpy.data.materials.new("Chrome")
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.86, 0.87, 0.89, 1)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.05
    return m


def emitter_material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m, nt, em


def mnode(nt, op, a, b):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for sock, v in ((n.inputs[0], a), (n.inputs[1], b)):
        if isinstance(v, (int, float)):
            sock.default_value = v
        else:
            nt.links.new(v, sock)
    return n.outputs[0]


def value_node(nt, keys, linear=False):
    n = nt.nodes.new("ShaderNodeValue")
    key(n.outputs[0], "default_value", keys, linear=linear)
    return n.outputs[0]


def flat_plane(name, w, h, z, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    mesh.uv_layers.new()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location.z = z
    obj.data.materials.append(mat)
    # Only reflections see it, and it casts no shadow on the badges.
    obj.visible_camera = False
    obj.visible_shadow = False
    obj.visible_diffuse = False
    return obj


# ---------------------------------------------------------------- lights

def build_strip(strength):
    """Narrow, tilted, soft-edged strip that travels with the light."""
    m, nt, em = emitter_material("SweepStrip")
    em.inputs["Color"].default_value = (0.92, 0.96, 1.0, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    # Profile across the strip's width: 1 in the middle, 0 at the edges, sharpened.
    tri = mnode(nt, "SUBTRACT", 1.0, mnode(nt, "ABSOLUTE", mnode(nt, "SUBTRACT", mnode(nt, "MULTIPLY", sep.outputs["X"], 2.0), 1.0), 0.0))
    prof = mnode(nt, "POWER", tri, 1.5)
    level = value_node(nt, scaled(LIGHT_ON, strength))
    nt.links.new(mnode(nt, "MULTIPLY", prof, level), em.inputs["Strength"])
    obj = flat_plane("SweepStrip", 4.0 * LIGHT_DIST, 16.0 * LIGHT_DIST, STRIP_Z, m)
    obj.rotation_euler.z = math_radians(-18)
    key(obj, "location", scaled(LIGHT_X, STRIP_K), index=0, linear=True)
    return obj


def math_radians(d):
    return d * math.pi / 180


def build_fill(strength, info):
    """Wide plane that lights up with the light and stays lit behind it, with a
    vertical chrome gradient so the letter faces aren't one flat grey.

    A mirror face at badge x sees the plane at x * FILL_K, so the plane's left part
    is what HYUNDAI reflects and its right part is what i10 reflects. Each part gets
    its own gradient, fitted to that badge's height.
    """
    m, nt, em = emitter_material("Fill")
    em.inputs["Color"].default_value = (0.9, 0.94, 1.0, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])

    # Lit around the light, and still lit behind it: a bell ahead of the light times a
    # bell behind it that only falls to TRAIL.
    lx = value_node(nt, scaled(LIGHT_X, FILL_K), linear=True)
    dx = mnode(nt, "SUBTRACT", sep.outputs["X"], lx)

    def bell(x, w):
        d = mnode(nt, "DIVIDE", x, w * FILL_K)
        return mnode(nt, "EXPONENT", mnode(nt, "MULTIPLY", mnode(nt, "MULTIPLY", d, d), -1.0), 0.0)

    ahead = bell(mnode(nt, "MAXIMUM", dx, 0.0), AHEAD_W)
    behind = mnode(nt, "ADD", TRAIL, mnode(nt, "MULTIPLY", bell(mnode(nt, "MINIMUM", dx, 0.0), BEHIND_W), 1.0 - TRAIL))
    pool = mnode(nt, "ADD", ROOM_MIN, mnode(nt, "MULTIPLY", mnode(nt, "MULTIPLY", ahead, behind), 1.0 - ROOM_MIN))
    win = nt.nodes.new("ShaderNodeMapRange")
    win.interpolation_type = "SMOOTHSTEP"
    nt.links.new(mnode(nt, "ABSOLUTE", sep.outputs["X"], 0.0), win.inputs["Value"])
    win.inputs["From Min"].default_value = ROOM_HALF * FILL_K
    win.inputs["From Max"].default_value = (ROOM_HALF + ROOM_SOFT) * FILL_K
    win.inputs["To Min"].default_value = 1.0
    win.inputs["To Max"].default_value = 0.0
    pool = mnode(nt, "MULTIPLY", pool, win.outputs["Result"])


    def span(socket, lo, hi):
        n = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(socket, n.inputs["Value"])
        n.inputs["From Min"].default_value = lo
        n.inputs["From Max"].default_value = hi
        return n.outputs["Result"]

    t_hy = span(sep.outputs["Y"], info["hy_y"][0] * FILL_K, info["hy_y"][1] * FILL_K)
    t_i10 = span(sep.outputs["Y"], info["i10_y"][0] * FILL_K, info["i10_y"][1] * FILL_K)
    side = span(sep.outputs["X"], info["split_x"] * FILL_K - 0.01, info["split_x"] * FILL_K + 0.01)
    t = mnode(nt, "ADD", t_hy, mnode(nt, "MULTIPLY", side, mnode(nt, "SUBTRACT", t_i10, t_hy)))
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(t, ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    # bottom .. dark horizon .. bright edge above it .. top
    stops = [(0.0, 0.10), (0.40, 0.05), (0.48, 0.0), (0.52, 1.0), (0.75, 0.45), (1.0, 0.70)]
    els[0].position, els[0].color = stops[0][0], (stops[0][1],) * 3 + (1,)
    els[1].position, els[1].color = stops[-1][0], (stops[-1][1],) * 3 + (1,)
    for pos, v in stops[1:-1]:
        e = els.new(pos)
        e.color = (v,) * 3 + (1,)

    level = value_node(nt, scaled(FILL_ON, strength))
    s = mnode(nt, "MULTIPLY", mnode(nt, "MULTIPLY", pool, ramp.outputs["Color"]), level)
    nt.links.new(s, em.inputs["Strength"])
    return flat_plane("Fill", 60.0, 40.0, FILL_Z, m)


def build_key_light(group_h, power, visible_glow, glow_strength):
    """A short horizontal strip light north of the badges, aimed at them. Its x is
    scaled so that on screen it sits over the chrome it lights. The flat letter faces
    never mirror it, so it only shows on the bevelled edges: as lines along the top
    edges under it, and as hot spots where a curve turns to face it."""
    y = group_h / 2 + KEY_Y_OFF
    z = KEY_Z
    xs = scaled(LIGHT_X, (CAM_D - z) / CAM_D)

    def add_light(name, kind, ly, energy):
        ld = bpy.data.lights.new(name, kind)
        ld.color = (0.93, 0.96, 1.0)
        light = bpy.data.objects.new(name, ld)
        bpy.context.scene.collection.objects.link(light)
        light.location = (xs[0][1], ly, z)
        light.visible_camera = False
        key(light, "location", xs, index=0, linear=True)
        key(ld, "energy", scaled(KEY_ON, energy))
        return ld, light

    for name, ly, share in (("KeyLight", y, 1.0), ("KeyLightSouth", -y, SOUTH_SHARE)):
        ld, light = add_light(name, "AREA", ly, power * share)
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = KEY_LEN, KEY_WIDTH
        ld.spread = math_radians(BEAM)
        light.rotation_euler.x = -math.atan2(ly, z)  # face the badges
    ld, light = add_light("KeyCore", "SPOT", y, CORE_POWER)
    ld.shadow_soft_size = CORE_RADIUS
    ld.spot_size = math_radians(BEAM)
    ld.spot_blend = 1.0
    light.rotation_euler.x = -math.atan2(y, z)

    if not visible_glow:
        return
    # What the camera sees of the light: a wide soft glow with no hard core.
    # Only the camera sees it; the key light does the lighting.
    m = bpy.data.materials.new("Glow")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    add = nt.nodes.new("ShaderNodeAddShader")
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.92, 0.95, 1.0, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"  # 1 at the centre, 0 at radius 1
    nt.links.new(tc.outputs["Object"], grad.inputs["Vector"])
    falloff = mnode(nt, "POWER", grad.outputs["Fac"], 5.0)  # bell-shaped, no visible rim
    nt.links.new(mnode(nt, "MULTIPLY", falloff, value_node(nt, scaled(LIGHT_ON, glow_strength))), em.inputs["Strength"])
    nt.links.new(clear.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])

    bpy.ops.mesh.primitive_circle_add(vertices=64, radius=1.0, fill_type="TRIFAN", location=(xs[0][1], y, z))
    glow = bpy.context.active_object
    glow.name = "Glow"
    glow.scale = (2.6, 2.6, 1.0)
    glow.data.materials.append(m)
    glow.visible_shadow = False
    glow.visible_diffuse = False
    glow.visible_glossy = False
    key(glow, "location", xs, index=0, linear=True)


# ---------------------------------------------------------------- camera, world, render

def build_camera():
    cd = bpy.data.cameras.new("Camera")
    cd.lens = LENS
    cd.sensor_width = SENSOR
    cd.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Camera", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    # The push-in keeps its timing from before the hold was added; it settles during it.
    key(cam, "location", [(clip_frame(1), CAM_D), (clip_frame(SWEEP_END + 6), CAM_D * 0.98)], index=2)


def setup_world():
    w = bpy.data.worlds.new("Black")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0, 0, 0, 1)
    bg.inputs["Strength"].default_value = 0.0
    bpy.context.scene.world = w


def set_menu(sock, value):
    try:
        sock.default_value = value
    except (TypeError, ValueError) as e:
        print(f"menu {sock.name}={value!r} rejected: {e}")


def setup_compositor(glow):
    s = bpy.context.scene
    ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    out = ng.nodes.new("NodeGroupOutput")

    bloom = ng.nodes.new("CompositorNodeGlare")
    set_menu(bloom.inputs["Type"], "Bloom")
    set_menu(bloom.inputs["Quality"], "High")
    bloom.inputs["Threshold"].default_value = BLOOM_THRESHOLD
    bloom.inputs["Strength"].default_value = 0.35 if glow else BLOOM_STRENGTH
    bloom.inputs["Size"].default_value = 0.7
    ng.links.new(rl.outputs["Image"], bloom.inputs["Image"])
    ng.links.new(bloom.outputs["Image"], out.inputs[0])
    s.compositing_node_group = ng
    if hasattr(s.render, "use_compositing"):
        s.render.use_compositing = True


def setup_render(quality):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    s.cycles.device = "GPU"

    s.render.resolution_x, s.render.resolution_y = 1920, 1080
    s.render.resolution_percentage = 50 if quality == "mock" else 100
    s.render.fps = FPS
    s.frame_start, s.frame_end = 1, FRAMES
    s.render.use_persistent_data = True  # keep the static badges between frames: faster
    s.render.use_motion_blur = True
    s.render.motion_blur_shutter = 0.5
    s.render.film_transparent = False
    s.render.dither_intensity = 0.0  # dither noise would lift the black frames off 0

    s.cycles.samples = 64 if quality == "mock" else 384
    s.cycles.use_adaptive_sampling = True
    s.cycles.adaptive_threshold = 0.02 if quality == "mock" else 0.008
    s.cycles.use_denoising = True
    try:
        s.cycles.denoiser = "OPENIMAGEDENOISE"
    except TypeError as e:
        print("denoiser:", e)
    s.cycles.max_bounces = 6
    s.cycles.glossy_bounces = 4
    s.cycles.diffuse_bounces = 1
    s.cycles.transmission_bounces = 0
    s.cycles.volume_bounces = 0
    s.cycles.caustics_reflective = False
    s.cycles.caustics_refractive = False

    try:
        s.view_settings.view_transform = "AgX"
    except TypeError as e:
        print("view transform:", e)
    s.view_settings.look = "None"

    im = s.render.image_settings
    if "media_type" in im.bl_rna.properties.keys():
        im.media_type = "IMAGE"
    im.file_format = "PNG"
    im.color_mode = "RGB"
    im.color_depth = "8"


def main():
    args = ARGS
    addon_utils.enable("io_curve_svg", default_set=True)
    clear_scene()
    glow = args.light == "glow"

    hy, i10, info = build_badges(args.layout)
    chrome = chrome_material()
    for o in (hy, i10):
        o.data.materials.append(chrome)

    build_strip(strength=4.5)
    build_fill(strength=FILL_STRENGTH, info=info)
    build_key_light(info["group_h"], power=KEY_POWER, visible_glow=glow, glow_strength=1.4)
    build_camera()
    setup_world()
    setup_render(args.quality)
    setup_compositor(glow)

    variant = f"{args.layout}-{args.light}"
    folder = os.path.join(ROOT, "frames", f"{variant}-{args.quality}")
    os.makedirs(folder, exist_ok=True)
    s = bpy.context.scene

    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, f"i10-intro-{variant}.blend"))
    if args.stills:
        for f in [int(x) for x in args.stills.split(",")]:
            s.frame_set(f)
            s.render.filepath = os.path.join(folder, f"still_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    if args.render:
        s.render.filepath = os.path.join(folder, "")
        bpy.ops.render.render(animation=True)


main()
