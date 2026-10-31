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
parser.add_argument("--resolution", type=int, default=1100)
parser.add_argument("--views", nargs="+", choices=["perspective", "reference", "front", "side", "rear", "top"],
                    default=["perspective", "reference", "front", "side", "rear", "top"])
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
        tex.inputs["Scale"].default_value = 18
        tex.inputs["Detail"].default_value = 3
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = .15
        ramp.color_ramp.elements[0].color = (*(c * .82 for c in color), 1)
        ramp.color_ramp.elements[1].position = .85
        ramp.color_ramp.elements[1].color = (*(min(1, c * 1.10) for c in color), 1)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bs.inputs["Base Color"])
        weave = nodes.new("ShaderNodeTexNoise")
        weave.inputs["Scale"].default_value = 520
        weave.inputs["Detail"].default_value = 2
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = .15
        bump.inputs["Distance"].default_value = .00012
        links.new(weave.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    else:
        bs.inputs["Coat Weight"].default_value = .15 if metallic < .5 else .03
    return m


ivory = material("Warm ivory | satin shell", (.64, .61, .48), .47)
rust = material("Burnt sienna | woven velvet", (.27, .038, .006), .82, fabric=True)
rust_dark = material("Rust | welt cord", (.15, .020, .003), .85, fabric=True)
thread = material("Ochre | topstitch", (.48, .21, .075), .8)
dark = material("Charcoal | pedestal", (.018, .021, .019), .56, .25)
rubber = material("Black | rubber sole", (.012, .015, .013), .87)
dark.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0
rubber.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0
metal = material("Brushed brass | fasteners", (.31, .25, .13), .32, .8)
floor_mat = material("Studio | warm limestone", (.22, .24, .23), .84)
floor_mat.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0


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
    (0.00, -.500, .315, .370, .050, .130),
    (0.10, -.425, .298, .433, .240, .090),
    (0.27, -.180, .285, .440, .275, .025),
    (0.43,  .045, .310, .410, .275, -.045),
    (0.54,  .175, .450, .375, .205, -.068),
    (0.69,  .280, .720, .375, .130, -.065),
    (0.85,  .385, .970, .375, .065, -.045),
    (0.94,  .430, 1.100, .369, -.005, -.035),
    (1.00,  .450, 1.145, .340, -.035, -.025),
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
bev.width = .003
bev.segments = 3
shell["purpose"] = "Visual structural envelope; not an engineered plywood laminate"

# Continuous soft cream rim around the entire open bucket.
rim = ([surface(0, -1+2*i/90) for i in range(91)] +
       [surface(i/140, 1) for i in range(1, 141)] +
       [surface(1, 1-2*i/90) for i in range(1, 91)] +
       [surface(1-i/140, -1) for i in range(1, 140)])
curve_object("Shell | small perimeter radius", [rim], .0045, ivory, shell_col, True)


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
            h += .007 * math.exp(-edge/.13) * math.sin(math.pi*min(edge/.08, 1)) * waves
            # Centre back has two softly pulled channels, not hard sculpted grooves.
            if "Back panel" in name:
                fade = math.sin(math.pi*t)**.7
                for rr in [.32, .68]:
                    h -= .006*math.exp(-((r-rr)/.055)**2)*fade
                h += .007*math.sin(31*r+5*t)*math.sin(math.pi*r)*math.sin(math.pi*t)
            if "Seat" in name:
                h -= .040*math.exp(-((t-.58)/.33)**2-((r-.5)/.30)**2)
                h += .008*math.sin(27*r+5*t)*math.sin(math.pi*r)*math.sin(math.pi*t)
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
padded_patch("Seat | sunken inner cushion", .090, .545, -.81, .81, .118, 1)
padded_patch("Back panel | full padded back behind loose pillow", .50, .947, -.67, .67, .077, 3)


def swept_cushion(name, frame, width_fn, depth_fn, seed, ns=176, na=40, seam_angle=0):
    """Closed elliptical sweep; geometry gathers toward its sewn outer edge."""
    def point(t,a):
        p,n,u=frame(t)
        end=min(1,t/.055,(1-t)/.055)
        taper=math.sin(end*math.pi/2)
        edge=(.55+.45*abs(math.cos(a)))
        gather=.009*(math.sin(102*t+3*math.sin(a)+seed)+.32*math.sin(171*t-5*a+seed))
        gather*=edge*math.sin(math.pi*t)**.4
        # Compression at the hidden underside stays subtle; visible skin carries folds.
        gather*=.15+.85*max(0,math.sin(a))
        depth=depth_fn(t)+gather
        return p+u*(width_fn(t)*taper*math.cos(a))+n*(depth*taper*math.sin(a))
    vs=[frame(0)[0]]
    for i in range(1,ns):
        vs.extend(point(i/ns,2*math.pi*j/na) for j in range(na))
    vs.append(frame(1)[0])
    fs=[(0,1+(j+1)%na,1+j) for j in range(na)]
    for i in range(ns-2):
        start=1+i*na
        fs.extend((start+j,start+(j+1)%na,start+na+(j+1)%na,start+na+j) for j in range(na))
    end,start=len(vs)-1,1+(ns-2)*na
    fs.extend((end,start+j,start+(j+1)%na) for j in range(na))
    ob=mesh_object(name,vs,fs,rust,pad_col)
    sub=ob.modifiers.new("Soft upholstered section",'SUBSURF')
    sub.levels=sub.render_levels=1
    seam=[point(i/ns,seam_angle) for i in range(1,ns)]
    curve_object(name+" | welt",[seam],.0020,rust_dark)
    return ob


def front_roll_frame(t):
    x=.742*(t-.5)
    f=x/.371
    p=Vector((x,-.438+.125*f*f,.420+.081*f*f))
    tangent=Vector((1,.250*x/(.371**2),.162*x/(.371**2))).normalized()
    n=Vector((0,0,1))
    n=(n-tangent*n.dot(tangent)).normalized()
    u=tangent.cross(n).normalized()
    return p,n,u


swept_cushion("Seat | inflated rounded front bolster", front_roll_frame,
              lambda t:.087+.008*math.sin(math.pi*t),
              lambda t:.079+.008*math.sin(math.pi*t),2,ns=144,seam_angle=-.70)


def top_roll_frame(t):
    v=-.68+1.36*t
    n=normal(.921,v)
    p=surface(.921,v)+n*.048
    tang=(surface(.921,min(.69,v+.001))-surface(.921,max(-.69,v-.001))).normalized()
    n=(n-tang*n.dot(tang)).normalized()
    return p,n,tang.cross(n).normalized()


swept_cushion("Back | padded top surround",top_roll_frame,
              lambda t:.052,lambda t:.066,5,ns=112,seam_angle=math.pi)


def loose_head_pillow():
    """A separate rounded rectangular pillow, suspended in front of the back pad."""
    s=.815
    n=normal(s,0)
    up=(surface(s+.001,0)-surface(s-.001,0)).normalized()
    across=Vector((1,0,0))
    origin=surface(s,0)+n*.123
    nu,nv=48,88
    def point(t,r,back=False):
        u,v=2*r-1,2*t-1
        x=.285*u*math.sqrt(1-.16*v*v)
        z=.106*v*math.sqrt(1-.30*u*u)
        arch=max(0,(1-u*u)*(1-v*v))**.38
        if back:
            h=-.014-.025*arch
        else:
            h=.015+.073*arch
            edge=min(r,1-r)
            pull=math.exp(-edge/.16)*math.sin(math.pi*min(edge/.07,1))
            h+=.009*pull*math.sin(59*t+9*r+2*math.sin(17*t))
            h+=.003*math.sin(17*r+3*t)*math.sin(math.pi*r)*math.sin(math.pi*t)
        return origin+across*x+up*z+n*h
    vs=[point(i/nu,j/nv,back) for back in [False,True] for i in range(nu+1) for j in range(nv+1)]
    count=(nu+1)*(nv+1)
    fs=grid_faces(nu,nv)
    fs += [tuple(count+k for k in reversed(face)) for face in grid_faces(nu,nv)]
    boundary=list(range(nv+1))+[i*(nv+1)+nv for i in range(1,nu+1)]
    boundary += [nu*(nv+1)+j for j in range(nv-1,-1,-1)]+[i*(nv+1) for i in range(nu-1,0,-1)]
    for k,a in enumerate(boundary):
        b=boundary[(k+1)%len(boundary)]
        fs.append((b,a,a+count,b+count))
    ob=mesh_object("Headrest | loose rectangular pillow",vs,fs,rust,pad_col)
    sub=ob.modifiers.new("Rounded pillow corners",'SUBSURF')
    sub.levels=sub.render_levels=1
    curve_object("Headrest | perimeter welt",[[vs[k] for k in boundary]],.0018,rust_dark,cyclic=True)
    ob["reference_feature"]="Separate full pillow below the padded top surround"


loose_head_pillow()


def bolster(side):
    """Plump, closed swept cushion with elliptical sections and softly gathered skin."""
    ns, na = 192, 40
    def frame(t):
        def centre(t):
            s = .075+.864*t
            v = side*(.81-.22*min(1,t/.65))
            n = normal(s,v)
            return surface(s,v)+n*.067,n
        p,n = centre(t)
        a, b = max(0,t-.0001), min(1,t+.0001)
        pa,pb = centre(a)[0],centre(b)[0]
        tang = (pb-pa).normalized()
        n = (n-tang*n.dot(tang)).normalized()
        u = tang.cross(n).normalized()
        return p,n,u
    name=("Left" if side<0 else "Right")+" | gathered continuous bolster"
    return swept_cushion(name,frame,
                         lambda t:.071+.014*math.sin(math.pi*t),
                         lambda t:.075+.013*math.sin(math.pi*t),
                         2 if side<0 else 4,ns=ns,na=na,seam_angle=0 if side>0 else math.pi)


bolster(-1)
bolster(1)

# Flat ivory arm ledges instead of a second tubular trim around the opening.
for side in [-1, 1]:
    vs=[]
    for i in range(61):
        t=i/60
        p=surface(.115+.31*t,side)
        width=.036*(.55+.45*math.sin(math.pi*t))
        for j in range(5):
            r=j/4
            vs.append(p+Vector((side*(-width+(width+.008)*r),0,.006)))
    faces=grid_faces(60,4)
    if side<0:
        faces=[tuple(reversed(face)) for face in faces]
    ob=mesh_object(("Left" if side<0 else "Right")+" | flat ivory arm ledge",vs,faces,ivory,shell_col)
    sol=ob.modifiers.new("Arm ledge thickness",'SOLIDIFY')
    sol.thickness=.016
    sol.offset=-1
    be=ob.modifiers.new("Rounded ledge edges",'BEVEL')
    be.width=.006
    be.segments=3


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
cylinder("Base | recessed rubber sole", .272, .017, (0,.11,.013), rubber, base_col, (1,1.25,1), .006)
cylinder("Base | narrow aged ivory lower rim", .283, .012, (0,.11,.028), ivory, base_col, (1,1.25,1), .004)
cylinder("Base | dark low oval plinth", .274, .118, (0,.11,.091), dark, base_col, (1,1.25,1), .010)
cylinder("Base | dark upper transition", .274, .010, (0,.11,.151), dark, base_col, (1,1.25,1), .003)
# Recessed, tapered mount: the reference shows a low plinth, not a second drum.
profile_mount=[(.145,.235),(.162,.230),(.187,.190),(.222,.139),(.250,.116),(.285,.113)]
vs=[]
for z,radius in profile_mount:
    for j in range(96):
        a=2*math.pi*j/96
        vs.append((radius*math.cos(a),.105+1.24*radius*math.sin(a),z))
fs=[]
for i in range(len(profile_mount)-1):
    for j in range(96):
        fs.append((i*96+j,i*96+(j+1)%96,(i+1)*96+(j+1)%96,(i+1)*96+j))
fs += [tuple(reversed(range(96))),tuple((len(profile_mount)-1)*96+j for j in range(96))]
mount=mesh_object("Base | recessed tapered mount",vs,fs,dark,base_col)
be=mount.modifiers.new("Soft mounting transitions",'BEVEL')
be.width,be.segments=.006,3
mount.modifiers.new("Mount weighted normals",'WEIGHTED_NORMAL')

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
reference = camera("Camera | reference-facing left three-quarter", (-1.10,-3.05,1.65), (0,0,.59), lens=59)
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
scene.render.resolution_x = args.resolution
scene.render.resolution_y = args.resolution
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
    "revision": 2,
    "reference_changes": ["separate rectangular head pillow", "inflated front seat roll", "gathered side cushions", "broader upper back", "flat ivory arm ledges", "recessed low pedestal"],
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
    cameras={"perspective":hero,"reference":reference,"front":front,"side":side,"rear":rear,"top":top}
    for filename in args.views:
        cam=cameras[filename]
        scene.camera = cam
        scene.render.filepath = str(OUT/(filename+".png"))
        bpy.ops.render.render(write_still=True)
    scene.camera = hero
    scene.render.filepath = str(OUT/"perspective.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"chair.blend"), compress=True)

if not args.no_render and {"front","side","top"}.issubset(args.views):
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
