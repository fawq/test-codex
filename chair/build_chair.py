"""Photo-inspired lounge chair, real-world metric dimensions, Blender 4.3+.

GUI: open this script in Blender's Text Editor and Run Script.
CLI: blender --background --python build_chair.py -- --output ./output
All dimensions are assumptions from a single perspective image, not measurements.
Only this generator's collection is replaced when rerun; other scene data survives.
"""

import argparse
import base64
import json
import math
import os
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "output" if "__file__" in globals() else Path(bpy.path.abspath("//")) / "chair_output"
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
parser.add_argument("--no-render", action="store_true")
parser.add_argument("--samples", type=int, default=96)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)

# Editable finished envelope, metres. Front = -Y, up = +Z.
WIDTH, DEPTH, HEIGHT = 0.90, 1.10, 1.15
SHELL_THICKNESS = 0.022
NAME = "REFERENCE_CHAIR"
# Work in a dedicated scene; leave any pre-existing scene (including default cube)
# untouched and out of the model's renders.
scene = bpy.data.scenes.get("Chair | Studio") or bpy.data.scenes.new("Chair | Studio")
bpy.context.window.scene = scene
if NAME in bpy.data.collections:
    old = bpy.data.collections[NAME]
    for obj in list(old.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for child in list(old.children):
        bpy.data.collections.remove(child)
    bpy.data.collections.remove(old)
root = bpy.data.collections.new(NAME)
bpy.context.scene.collection.children.link(root)


def collection(name):
    c = bpy.data.collections.new(name)
    root.children.link(c)
    return c


shell_col = collection("01 | Ivory structural shell")
pad_col = collection("02 | Rust upholstery")
detail_col = collection("03 | Seams and hardware")
base_col = collection("04 | Pedestal")
studio_col = collection("05 | Studio (not part of chair)")
CHAIR_COLS = [shell_col, pad_col, detail_col, base_col]


def move_to(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def material(name, color, rough=0.5, metallic=0.0, fabric=False):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bs = nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Metallic"].default_value = metallic
    if fabric:
        bs.inputs["Sheen Weight"].default_value = 0.04
        bs.inputs["Sheen Roughness"].default_value = 0.78
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 115
        tex.inputs["Detail"].default_value = 3
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = .15
        ramp.color_ramp.elements[0].color = (*(c * .67 for c in color), 1)
        ramp.color_ramp.elements[1].position = .85
        ramp.color_ramp.elements[1].color = (*(min(1, c * 1.22) for c in color), 1)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bs.inputs["Base Color"])
        weave = nodes.new("ShaderNodeTexNoise")
        weave.inputs["Scale"].default_value = 520
        weave.inputs["Detail"].default_value = 2
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = .20
        bump.inputs["Distance"].default_value = .00022
        links.new(weave.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    else:
        bs.inputs["Coat Weight"].default_value = .15 if metallic < .5 else .03
    return m


ivory = material("Warm ivory | satin shell", (.64, .61, .48), .32)
rust = material("Burnt sienna | woven velvet", (.22, .018, .002), .84, fabric=True)
rust_dark = material("Rust | welt cord", (.19, .031, .009), .85, fabric=True)
thread = material("Ochre | topstitch", (.48, .21, .075), .8)
dark = material("Charcoal | pedestal", (.025, .031, .029), .32, .65)
rubber = material("Black | rubber sole", (.012, .015, .013), .87)
metal = material("Brushed brass | fasteners", (.31, .25, .13), .32, .8)
floor_mat = material("Studio | warm limestone", (.22, .24, .23), .84)


def mesh_object(name, verts, faces, mat, col):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    if mat:
        me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def curve_object(name, paths, radius, mat, col=detail_col, cyclic=False):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 2
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    for points in paths:
        sp = cu.splines.new("POLY")
        sp.points.add(len(points) - 1)
        for p, xyz in zip(sp.points, points):
            p.co = (*xyz, 1)
        sp.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, cu)
    col.objects.link(ob)
    cu.materials.append(mat)
    return ob


# Centreline loft: s, Y, Z, half-width, lateral rise, lateral Y setback.
# Continuous bucket surface rather than intersecting rectangular seat/back slabs.
PROFILE = [
    (0.00, -.490, .315, .330, .055, .055),
    (0.10, -.412, .298, .420, .240, .075),
    (0.27, -.190, .294, .435, .275, .025),
    (0.43,  .045, .325, .405, .270, -.045),
    (0.54,  .180, .465, .371, .205, -.068),
    (0.69,  .286, .728, .354, .126, -.065),
    (0.85,  .397, .978, .356, .055, -.045),
    (0.94,  .443, 1.100, .341, -.002, -.035),
    (1.00,  .460, 1.145, .301, -.030, -.025),
]


def profile(s):
    s = max(0, min(1, s))
    i = next((i for i in range(len(PROFILE)-1) if PROFILE[i][0] <= s <= PROFILE[i+1][0]), len(PROFILE)-2)
    a, b = PROFILE[i], PROFILE[i+1]
    h = b[0]-a[0]
    t = (s-a[0])/h
    vals = []
    for k in range(1, 6):
        pa = PROFILE[max(0, i-1)]
        pb = PROFILE[min(len(PROFILE)-1, i+2)]
        m0 = (b[k]-pa[k])/(b[0]-pa[0])
        m1 = (pb[k]-a[k])/(pb[0]-a[0])
        vals.append((2*t**3-3*t*t+1)*a[k] + (t**3-2*t*t+t)*h*m0 + (-2*t**3+3*t*t)*b[k] + (t**3-t*t)*h*m1)
    return vals


def surface(s, v):
    y, z, w, rise, setback = profile(s)
    a = v * math.pi/2
    bowl = 1-math.cos(a)
    return Vector((w*math.sin(a), y+setback*bowl, z+rise*bowl))


def normal(s, v):
    ds = surface(min(1, s+.0002), v)-surface(max(0, s-.0002), v)
    dv = surface(s, min(1, v+.0002))-surface(s, max(-1, v-.0002))
    return dv.cross(ds).normalized()


def grid_faces(nu, nv):
    return [(i*(nv+1)+j, i*(nv+1)+j+1, (i+1)*(nv+1)+j+1, (i+1)*(nv+1)+j)
            for i in range(nu) for j in range(nv)]


nu, nv = 100, 64
verts = [surface(i/nu, 2*j/nv-1) for i in range(nu+1) for j in range(nv+1)]
shell = mesh_object("Shell | continuous seat-back bucket | nominal 22 mm", verts, grid_faces(nu, nv), ivory, shell_col)
sub = shell.modifiers.new("Fair loft", "SUBSURF")
sub.levels = sub.render_levels = 1
sol = shell.modifiers.new("Wall | 22 mm before envelope calibration", "SOLIDIFY")
sol.thickness = SHELL_THICKNESS
sol.offset = -1
sol.use_even_offset = False
bev = shell.modifiers.new("Soft manufactured edges", "BEVEL")
bev.width = .007
bev.segments = 3
shell["purpose"] = "Visual structural envelope; not an engineered plywood laminate"

# Continuous soft cream rim around the entire open bucket.
rim = ([surface(0, -1+2*i/90) for i in range(91)] +
       [surface(i/140, 1) for i in range(1, 141)] +
       [surface(1, 1-2*i/90) for i in range(1, 91)] +
       [surface(1-i/140, -1) for i in range(1, 140)])
curve_object("Shell | rounded perimeter lip", [rim], .009, ivory, shell_col, True)


def padded_patch(name, s0, s1, v0, v1, loft, seed, nu=68, nv=54):
    """Closed, shaped sewn pad. Geometry includes edge gathering and panel pulls."""
    def sv(t, r):
        return s0+(s1-s0)*t, v0+(v1-v0)*r

    def position(t, r, back=False):
        s, v = sv(t, r)
        n = normal(s, v)
        if back:
            h = .005
        else:
            arch = max(0, math.sin(math.pi*t)*math.sin(math.pi*r)) ** .46
            h = .014 + loft*arch
            # Soft bunching from the sewn perimeter, gently irregular and symmetric.
            edge = min(t, 1-t, r, 1-r)
            waves = (math.sin(74*t+13*r+seed) + .4*math.sin(143*t-21*r+seed*2))
            h += .0045 * math.exp(-edge/.105) * math.sin(math.pi*min(edge/.08, 1)) * waves
            if "Headrest" in name:
                h += .0045 * math.exp(-min(r,1-r)/.13) * math.sin(113*t+16*r) * math.sin(math.pi*t)
            # Centre back has two softly pulled channels, not hard sculpted grooves.
            if "Back panel" in name:
                fade = math.sin(math.pi*t)**.7
                for rr in [.32, .68]:
                    h -= .009*math.exp(-((r-rr)/.032)**2)*fade
            if "Seat" in name:
                h -= .019*math.exp(-((t-.65)/.3)**2-((r-.5)/.30)**2)
                h += .035*math.exp(-((t-.21)/.17)**2)*math.sin(math.pi*r)**.5
        return surface(s, v)+n*h

    verts = [position(i/nu, j/nv, back) for back in [False, True]
             for i in range(nu+1) for j in range(nv+1)]
    faces = grid_faces(nu, nv)
    count = (nu+1)*(nv+1)
    faces += [tuple(count+idx for idx in reversed(face)) for face in grid_faces(nu, nv)]
    # Boundary loop in the winding of the top surface.
    boundary = list(range(nv+1))
    boundary += [i*(nv+1)+nv for i in range(1, nu+1)]
    boundary += [nu*(nv+1)+j for j in range(nv-1, -1, -1)]
    boundary += [i*(nv+1) for i in range(nu-1, 0, -1)]
    for k, a in enumerate(boundary):
        b = boundary[(k+1)%len(boundary)]
        faces.append((b, a, a+count, b+count))
    ob = mesh_object(name, verts, faces, rust, pad_col)
    sub = ob.modifiers.new("Soft sewn envelope", "SUBSURF")
    sub.levels = sub.render_levels = 1
    uv = ob.data.uv_layers.new(name="Pattern coordinates (concept, not cutting pattern)")
    for poly in ob.data.polygons:
        for li in poly.loop_indices:
            idx = ob.data.loops[li].vertex_index % count
            uv.data[li].uv = (idx% (nv+1)/nv, idx//(nv+1)/nu)
    seam = [verts[i]+normal(*sv((i//(nv+1))/nu, (i%(nv+1))/nv))*.001 for i in boundary]
    curve_object(name+" | welt", [seam], .0022, rust_dark, cyclic=True)
    ob["part"] = "Upholstery volume, with seam coordinates; needs foam and fabric pattern development"
    return ob


# Broad central cushion and continuous side bolsters follow the same shell loft.
padded_patch("Seat | deeply padded basin with waterfall front", .012, .535, -.87, .87, .128, 1)
padded_patch("Back panel | reclined central cushion", .50, .875, -.65, .65, .094, 3)
padded_patch("Headrest | wide soft pillow", .81, .977, -.78, .78, .125, 6)


def bolster(side):
    """Plump, closed swept cushion with elliptical sections and softly gathered skin."""
    ns, na = 176, 40
    def frame(t):
        def centre(t):
            s = .09+.862*t
            v = side*(.80-.18*min(1,t/.65))
            n = normal(s,v)
            return surface(s,v)+n*.060,n
        p,n = centre(t)
        a, b = max(0,t-.0001), min(1,t+.0001)
        pa,pb = centre(a)[0],centre(b)[0]
        tang = (pb-pa).normalized()
        n = (n-tang*n.dot(tang)).normalized()
        u = tang.cross(n).normalized()
        return p,n,u
    def point(t,a):
        p,n,u = frame(t)
        end = min(1,t/.065,(1-t)/.065)
        taper = math.sin(end*math.pi/2)
        width = .059+.010*math.sin(math.pi*t)
        depth = .063+.010*math.sin(math.pi*t)
        gather = .0035*(math.sin(111*t+2*math.sin(a))+.30*math.sin(183*t-4*a))
        gather *= math.sin(a)**2 * math.sin(math.pi*t)**.4
        return p+u*(width*taper*math.cos(a))+n*((depth+gather)*taper*math.sin(a))
    vs = [frame(0)[0]]
    for i in range(1,ns):
        for j in range(na):
            vs.append(point(i/ns,2*math.pi*j/na))
    vs.append(frame(1)[0])
    fs=[]
    for j in range(na):
        fs.append((0,1+(j+1)%na,1+j))
    for i in range(ns-2):
        start=1+i*na
        for j in range(na):
            fs.append((start+j,start+(j+1)%na,start+na+(j+1)%na,start+na+j))
    end=len(vs)-1
    start=1+(ns-2)*na
    for j in range(na):
        fs.append((end,start+j,start+(j+1)%na))
    name=("Left" if side<0 else "Right")+" | gathered continuous bolster"
    ob=mesh_object(name,vs,fs,rust,pad_col)
    sub=ob.modifiers.new("Rounded gathered cushion",'SUBSURF')
    sub.levels=sub.render_levels=1
    seam=[point(i/ns,0 if side>0 else math.pi) for i in range(1,ns)]
    curve_object(name+" | outer welt",[seam],.0022,rust_dark)


bolster(-1)
bolster(1)

# Narrow ivory arm caps integrated with the outer shell; under-arm shadow joints.
for side in [-1, 1]:
    points = [surface(.135+.29*i/65, side)+normal(.135+.29*i/65, side)*.002 for i in range(66)]
    curve_object(("Left" if side<0 else "Right")+" | rolled ivory arm edge", [points], .016, ivory, shell_col)


def cylinder(name, radius, depth, loc, mat, col, scale=(1,1,1), bevel=.005):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=radius, depth=depth, location=loc)
    ob = move_to(bpy.context.object, col)
    ob.name = name
    ob.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = len(p.vertices)==4
    be = ob.modifiers.new("Machined edge", "BEVEL")
    be.width, be.segments = bevel, 3
    ob.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return ob


# Low, set-back oval pedestal visible beneath the floating bucket in the image.
cylinder("Base | oval rubber sole", .315, .022, (0,.075,.019), rubber, base_col, (1,1.24,1), .008)
cylinder("Base | ivory lower ring", .325, .027, (0,.075,.043), ivory, base_col, (1,1.24,1), .011)
cylinder("Base | recessed oval plinth", .297, .104, (0,.075,.105), dark, base_col, (1,1.24,1), .012)
cylinder("Base | ivory upper ring", .316, .027, (0,.075,.169), ivory, base_col, (1,1.24,1), .010)
cylinder("Base | swivel column", .127, .124, (0,.110,.226), dark, base_col, (1,1,1), .010)
cylinder("Base | upper load plate", .215, .023, (0,.110,.284), dark, base_col, (1,1.1,1), .009)

# Subtle exterior fasteners, placed on the true shell surface.
for side in [-1,1]:
    for s in [.23,.43,.68,.88]:
        p, n = surface(s, side*.988), normal(s, side*.988)
        ob = cylinder("Shell | recessed fastener", .005, .0025, p-n*.021, metal, detail_col, bevel=.0008)
        ob.rotation_euler = Vector((0,0,1)).rotation_difference(n).to_euler()


def chair_objects():
    return [o for c in CHAIR_COLS for o in c.objects]


def bounds(objects):
    deps = bpy.context.evaluated_depsgraph_get()
    pts = [o.matrix_world @ v.co for o in objects for v in o.evaluated_get(deps).data.vertices]
    return Vector(tuple(min(p[k] for p in pts) for k in range(3))), Vector(tuple(max(p[k] for p in pts) for k in range(3)))


# Bake the loft and wall first so the final envelope can be exactly calibrated.
# The small axis correction also affects wall thickness; final statistics record it.
for ob in chair_objects():
    if ob.type == "MESH":
        deps = bpy.context.evaluated_depsgraph_get()
        old_mesh = ob.data
        ob.data = bpy.data.meshes.new_from_object(ob.evaluated_get(deps), depsgraph=deps)
        ob.modifiers.clear()
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
    elif ob.type == "CURVE":
        deps = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(ob.evaluated_get(deps), depsgraph=deps)
        matrix = ob.matrix_world.copy()
        name = ob.name
        col = ob.users_collection[0]
        bpy.data.objects.remove(ob, do_unlink=True)
        ob = bpy.data.objects.new(name, mesh)
        col.objects.link(ob)
        ob.matrix_world = matrix

bpy.context.view_layer.update()
lo, hi = bounds(chair_objects())
stretch = Vector((WIDTH/(hi.x-lo.x), DEPTH/(hi.y-lo.y), HEIGHT/(hi.z-lo.z)))
centre = Vector(((hi.x+lo.x)/2,(hi.y+lo.y)/2,lo.z))
for ob in chair_objects():
    matrix = ob.matrix_world.copy()
    for vert in ob.data.vertices:
        p = matrix @ vert.co - centre
        vert.co = Vector((p.x*stretch.x,p.y*stretch.y,p.z*stretch.z))
    ob.matrix_world.identity()
    ob.data.update()
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(ob.data)
    bm.free()

scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = "CENTIMETERS"
scene["Design status"] = "Photo interpretation. Assumed size, NOT measured; no fabrication approval."
scene["Envelope metres"] = [WIDTH, DEPTH, HEIGHT]
scene["Axes"] = "X width, -Y front, +Z up; ground Z=0"

# Studio lighting and cameras, isolated in their own collection.
bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,-.003))
plane = move_to(bpy.context.object, studio_col)
plane.name = "Studio | ground"
plane.data.materials.append(floor_mat)


def aim(ob, point):
    ob.rotation_euler = (Vector(point)-ob.location).to_track_quat('-Z','Y').to_euler()


def area(name, loc, power, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.shape, data.size, data.color = power, 'DISK', size, color
    ob = bpy.data.objects.new(name, data)
    studio_col.objects.link(ob)
    ob.location = loc
    aim(ob,(0,0,.55))


area("Studio | large warm key", (-2,-2.8,3.5), 240, 3.0, (1,.88,.75))
area("Studio | soft cool fill", (2.8,-.8,2.2), 140, 2.5, (.78,.87,1))
area("Studio | back rim", (.5,2.5,3), 330, 2.0, (1,.92,.8))
world = bpy.data.worlds.new("Chair studio")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (.19,.22,.24,1)
world.node_tree.nodes["Background"].inputs[1].default_value = .25
scene.world = world


def camera(name, loc, target, ortho=None, lens=52):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = .01
    ob = bpy.data.objects.new(name, data)
    studio_col.objects.link(ob)
    ob.location = loc
    aim(ob,target)
    if ortho:
        data.type, data.ortho_scale = "ORTHO", ortho
    return ob


hero = camera("Camera | three-quarter", (1.85,-2.5,1.65), (0,.015,.59), lens=57)
front = camera("Camera | front orthographic", (0,-4,.575), (0,0,.575), 1.50)
side = camera("Camera | right orthographic", (4,0,.575), (0,0,.575), 1.50)
rear = camera("Camera | rear three-quarter", (-1.9,2.3,1.6), (0,0,.59), lens=57)
top = camera("Camera | plan orthographic", (0,0,4), (0,0,0), 1.50)
scene.camera = hero
scene.render.engine = 'CYCLES'
scene.cycles.samples = args.samples
# Some Linux Blender packages omit OpenImageDenoise. Sampling works on all builds.
scene.cycles.use_denoising = False
scene.cycles.max_bounces = 6
scene.render.resolution_x = 1100
scene.render.resolution_y = 1100
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "AgX"
scene.render.film_transparent = False

# Make the saved file immediately useful when opened interactively.
for ob in bpy.context.selected_objects:
    ob.select_set(False)
shell.select_set(True)
bpy.context.view_layer.objects.active = shell
for screen in bpy.data.screens:
    for a in screen.areas:
        if a.type == 'VIEW_3D':
            a.spaces.active.region_3d.view_distance = 2.7
            a.spaces.active.region_3d.view_location = (0,0,.57)
            a.spaces.active.clip_start = .01

bpy.context.view_layer.update()
lo, hi = bounds(chair_objects())
actual = hi-lo
assert all(abs(actual[i]-[WIDTH,DEPTH,HEIGHT][i])<1e-5 for i in range(3)), list(actual)
assert all(abs(o.scale[i]-1)<1e-6 for o in chair_objects() for i in range(3))
stats = {
    "units": "metres; 1 Blender unit = 1 m", "dimension_basis": "assumed from one perspective image",
    "target_dimensions_m": {"width":WIDTH,"depth":DEPTH,"height":HEIGHT},
    "measured_envelope_m": list(actual), "minimum_m": list(lo), "maximum_m": list(hi),
    "nominal_shell_wall_before_calibration_m": SHELL_THICKNESS,
    "envelope_calibration_xyz": list(stretch),
    "shell_wall_estimated_range_m": [SHELL_THICKNESS*min(stretch),SHELL_THICKNESS*max(stretch)],
    "mesh_objects": len(chair_objects()),
    "vertices": sum(len(o.data.vertices) for o in chair_objects()),
    "fabrication_status": "visual concept only; no load calculations, joints, or CNC cut patterns",
}
(OUT/"model_info.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
readme = bpy.data.texts.new("READ ME | metric photo reconstruction")
readme.write("Chair model: assumed 900 x 1100 x 1150 mm. 1 BU = 1 metre.\n"
             "Front = -Y. Components and studio separated in numbered collections.\n"
             "Single-photo interpretation: unseen geometry is invented. Blanket omitted.\n"
             "22 mm nominal shell is a visual envelope, not a verified plywood structure.\n"
             "No CNC fabrication or strength claims. See README.md and model_info.json.\n")

# Export only the chair, with metric geometry baked and all object scales equal 1.
for ob in bpy.context.selected_objects:
    ob.select_set(False)
for ob in chair_objects():
    ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/"chair.glb"), use_selection=True, use_active_scene=True, export_format='GLB', export_yup=True)
for ob in bpy.context.selected_objects:
    ob.select_set(False)
shell.select_set(True)
bpy.context.view_layer.objects.active = shell
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"chair.blend"), compress=True)

if not args.no_render:
    for cam, filename in [(hero,"perspective"),(front,"front"),(side,"side"),(rear,"rear"),(top,"top")]:
        scene.camera = cam
        scene.render.filepath = str(OUT/(filename+".png"))
        bpy.ops.render.render(write_still=True)
    scene.camera = hero
    scene.render.filepath = str(OUT/"perspective.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"chair.blend"), compress=True)

    # A vector dimension sheet, with actual orthographic renders embedded.
    # Sheet is fitted to a page; the model itself, not the page, is at 1:1 scale.
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="850" viewBox="0 0 1800 850">',
           '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse"><path d="M0 0L8 4L0 8" fill="none" stroke="#333e3c"/></marker></defs>',
           '<rect width="1800" height="850" fill="#edf0eb"/>',
           '<g font-family="sans-serif" fill="#263b37">',
           '<text x="45" y="56" font-size="30" font-weight="bold">FOTEL / STUDIUM FORMY</text>',
           '<text x="45" y="91" font-size="18">Gabaryty przyjęte: 900 × 1100 × 1150 mm · Model metryczny 1:1 · Interpretacja jednego zdjęcia</text>']
    def line(x1,y1,x2,y2,arrows=False):
        attr=' marker-start="url(#arrow)" marker-end="url(#arrow)"' if arrows else ''
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#333e3c" stroke-width="1.3"{attr}/>')
    def label(x,y,text,rotate=False):
        attr=f' transform="rotate(-90 {x} {y})"' if rotate else ''
        svg.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-size="19"{attr}>{text}</text>')
    for index,(file,title) in enumerate([('front','PRZÓD'),('side','PRAWY BOK'),('top','Z GÓRY')]):
        x,y,size=45+index*585,140,550
        data=base64.b64encode((OUT/(file+'.png')).read_bytes()).decode('ascii')
        svg.append(f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="data:image/png;base64,{data}"/>')
        label(x+size/2,126,title)
        span=(WIDTH if index!=1 else DEPTH)/1.5*size
        x1,x2=x+(size-span)/2,x+(size+span)/2
        dimy=722
        line(x1,y+size-25,x1,dimy+8)
        line(x2,y+size-25,x2,dimy+8)
        line(x1,dimy,x2,dimy,True)
        label((x1+x2)/2,dimy-10,f'{round((WIDTH if index!=1 else DEPTH)*1000)} mm')
        if index in [0,2]:
            h=(HEIGHT if index==0 else DEPTH)/1.5*size
            yc=y+size/2
            y1,y2=yc-h/2,yc+h/2
            dx=x+size-12
            line(dx,y1,dx,y2,True)
            line(dx-12,y1,dx+5,y1)
            line(dx-12,y2,dx+5,y2)
            label(dx-10,yc,f'{round((HEIGHT if index==0 else DEPTH)*1000)} mm',True)
    svg.append('<text x="45" y="787" font-size="18">Wymiary są założeniem projektowym, nie pomiarem oryginału. Koc pominięto. Tył i podstawa są interpretacją.</text>')
    svg.append('<text x="45" y="816" font-size="16">Arkusz poglądowy dopasowany do strony. Nie jest szablonem do wycinania ani dokumentacją CNC.</text></g></svg>')
    (OUT/'dimensions.svg').write_text('\n'.join(svg),encoding='utf-8')
print("CHAIR_COMPLETE", json.dumps(stats))
