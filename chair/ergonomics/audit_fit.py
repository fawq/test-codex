"""Read the finished chair and report functional geometry, without resizing it.

blender --background --python-exit-code 1 --python ergonomics/audit_fit.py
Measurements describe unloaded mesh geometry, not tested sitting comfort.
"""
import base64
import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view

HERE=Path(__file__).resolve().parent
MODEL=HERE.parent/'output/chair.blend'
bpy.ops.wm.open_mainfile(filepath=str(MODEL))
scene=bpy.context.scene
assert scene.unit_settings.system=='METRIC' and scene.unit_settings.scale_length==1
objects=[o for c in bpy.data.collections['REFERENCE_CHAIR'].children
         if not c.name.startswith('05') for o in c.objects]


def named(prefix):
    found=[o for o in objects if o.name.startswith(prefix) and not o.name.endswith(' | welt')]
    assert len(found)==1, (prefix,[o.name for o in found])
    return found[0]


def bbox(ob):
    ps=[ob.matrix_world@v.co for v in ob.data.vertices]
    return [min(p[k] for p in ps) for k in range(3)],[max(p[k] for p in ps) for k in range(3)]


def tree(ob):
    return BVHTree.FromPolygons([ob.matrix_world@v.co for v in ob.data.vertices],
                               [tuple(p.vertices) for p in ob.data.polygons])


seat=named('Seat | sunken inner cushion')
front=named('Seat | inflated rounded front bolster')
back=named('Back panel |')
head=named('Headrest | loose rectangular pillow')
left=named('Left | gathered continuous bolster')
right=named('Right | gathered continuous bolster')
ts,tf,tb,th,tl,tr=[tree(o) for o in [seat,front,back,head,left,right]]


def ray(t,origin,direction):
    p,n,face,dist=t.ray_cast(Vector(origin),Vector(direction),4)
    return p


seat_lo,seat_hi=bbox(seat)
seat_y=(seat_lo[1]+seat_hi[1])/2
seat_p=ray(ts,(0,seat_y,2),(0,0,-1))
assert seat_p is not None
seat_z=seat_p.z
clearance_z=seat_z+.065
l=ray(tl,(0,seat_y,clearance_z),(-1,0,0))
r=ray(tr,(0,seat_y,clearance_z),(1,0,0))
clear_width=r.x-l.x if l is not None and r is not None else None

# Both endpoints are sampled at the same explicitly recorded height. This is a
# repeatable geometric clearance, not a standard or a loaded-seat measurement.
depth_plane=seat_z+.050
front_p=ray(tf,(0,2,depth_plane),(0,-1,0))
back_p=ray(tb,(0,-2,depth_plane),(0,1,0))
clear_depth=back_p.y-front_p.y if front_p is not None and back_p is not None else None
roll_lo,roll_hi=bbox(front)
roll_center_samples=[ray(tf,(0,roll_lo[1]+(roll_hi[1]-roll_lo[1])*i/160,2),(0,0,-1)) for i in range(161)]
roll_center_top=max(p.z for p in roll_center_samples if p is not None)

head_lo,head_hi=bbox(head)
head_z=(head_lo[2]+head_hi[2])/2
head_p=ray(th,(0,-2,head_z),(0,1,0))
assert head_p is not None
b0=ray(tb,(0,-2,.65),(0,1,0))
b1=ray(tb,(0,-2,.85),(0,1,0))
assert b0 is not None and b1 is not None
tilt=math.atan2(b1.y-b0.y,b1.z-b0.z)

shoulders=[]
for z in [.75,.85,.95]:
    p=ray(tb,(0,-2,z),(0,1,0))
    if p is None:
        continue
    y=p.y-.025
    a=ray(tl,(0,y,z),(-1,0,0))
    b=ray(tr,(0,y,z),(1,0,0))
    shoulders.append({'z_m':z,'y_m':y,'gap_m':b.x-a.x if a is not None and b is not None else None})

# Illustrative 2 m skeleton: explicitly assumed segments, not author measurements
# and not a percentile database. Only use it to see which dimensions need checking.
parts={'sole_to_ankle':.06,'lower_leg':.50,'thigh':.51,'hip_to_neck':.69,'neck_to_crown':.24}
assert abs(sum(parts.values())-2.0)<1e-8
hip_y=(back_p.y-.075) if back_p is not None else .025
hip=Vector((0,hip_y,seat_z+.075))
axis=Vector((0,math.sin(tilt),math.cos(tilt)))
neck=hip+axis*parts['hip_to_neck']
crown=neck+axis*parts['neck_to_crown']
head_center=neck+axis*(parts['neck_to_crown']/2)
knee=hip+Vector((0,-math.sqrt(parts['thigh']**2-.020**2),-.020))
dz=knee.z-parts['sole_to_ankle']
assert 0<dz<parts['lower_leg']
ankle=knee+Vector((0,-math.sqrt(parts['lower_leg']**2-dz**2),-dz))
toe=ankle+Vector((0,-.25,-parts['sole_to_ankle']))

report={
    'model':'chair/output/chair.blend; revision 2',
    'model_sha256':hashlib.sha256(MODEL.read_bytes()).hexdigest(),
    'side_render_sha256':hashlib.sha256((HERE.parent/'output/side.png').read_bytes()).hexdigest(),
    'units':'metres; angles degrees',
    'status':'geometric audit only; no comfort, load or medical validation',
    'definitions':{
        'seat_center':'vertical top-surface ray at X=0 and midpoint of inner cushion Y bounds',
        'seat_clear_width':'between side bolsters at seat-centre Y and 65 mm above uncompressed centre surface',
        'seat_clear_depth':'horizontal gap from inside of front roll to back panel, 50 mm above uncompressed seat centre',
        'headrest_center':'midpoint of loose pillow Z bounds, front surface at X=0',
        'back_tilt':'front back-panel surface at Z=650 and 850 mm, measured from vertical',
    },
    'measurements':{
        'seat_center_xyz_m':list(seat_p),
        'uncompressed_seat_center_height_m':seat_z,
        'seat_width_probe_z_m':clearance_z,
        'seat_clear_width_m':clear_width,
        'seat_depth_probe_z_m':depth_plane,
        'seat_clear_depth_m':clear_depth,
        'front_roll_top_height_m':bbox(front)[1][2],
        'front_roll_top_on_centerline_m':roll_center_top,
        'headrest_center_xyz_m':list(head_p),
        'headrest_bottom_height_m':head_lo[2],
        'headrest_top_height_m':head_hi[2],
        'headrest_center_above_seat_m':head_z-seat_z,
        'back_tilt_from_vertical_deg':math.degrees(tilt),
        'back_width_probes':shoulders,
    },
    'illustrative_person':{
        'stature_m':2.0,'segment_assumptions_m':parts,
        'not_measured_from_author':True,
        'hip_xyz_m':list(hip),'head_center_xyz_m':list(head_center),'crown_xyz_m':list(crown),
        'head_center_minus_pillow_center_height_m':head_center.z-head_z,
    },
    'reference_repository':{
        'url':'https://github.com/zurekpiotr/Fotel',
        'inspection':'private, confirmed by user; Git HTTP 403, public page HTTP 404, existing GitHub CLI API request Forbidden; contents not read and author dimensions unknown',
    },
}
(HERE/'current_fit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

# Technical overlay on the existing orthographic render; no new model or resized
# chair is saved. The skeleton is in the same metric camera projection as the mesh.
cam=bpy.data.objects['Camera | right orthographic']
ox,oy,size=300,130,1100


def project(p):
    v=world_to_camera_view(scene,cam,Vector(p))
    return ox+size*v.x,oy+size*(1-v.y)


svg=['<svg xmlns="http://www.w3.org/2000/svg" width="2100" height="1380" viewBox="0 0 2100 1380">',
     '<rect width="2100" height="1380" fill="#eef0eb"/>',
     '<g font-family="sans-serif">',
     '<text x="50" y="48" font-size="30" font-weight="bold" fill="#263b37">FOTEL V2 / KONTROLA DOPASOWANIA DO 200 cm</text>',
     '<text x="50" y="84" font-size="19" fill="#263b37">Manekin z założonych proporcji. Nie jest pomiarem autora ani potwierdzeniem komfortu.</text>']
data=base64.b64encode((HERE.parent/'output/side.png').read_bytes()).decode('ascii')
svg.append(f'<image x="{ox}" y="{oy}" width="{size}" height="{size}" href="data:image/png;base64,{data}"/>')
points=[toe,ankle,knee,hip,neck,crown]
coords=' '.join(f'{x:.2f},{y:.2f}' for x,y in map(project,points))
svg.append(f'<polyline points="{coords}" fill="none" stroke="#ffd269" stroke-width="8" stroke-linejoin="round"/>')
for p in [ankle,knee,hip,neck]:
    x,y=project(p)
    svg.append(f'<circle cx="{x}" cy="{y}" r="9" fill="#263b37" stroke="#ffd269" stroke-width="4"/>')
x,y=project(head_center)
radius=.120/1.5*size
svg.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="#ffd269" fill-opacity=".15" stroke="#ffd269" stroke-width="6"/>')

for num,p in [(1,seat_p),(2,head_p)]:
    x,y=project(p)
    svg.append(f'<circle cx="{x}" cy="{y}" r="14" fill="#65e7ed"/>')
    svg.append(f'<text x="{x}" y="{y+6}" text-anchor="middle" font-size="19" font-weight="bold" fill="#18322f">{num}</text>')


def text_line(text,y,size=23,color='#263b37'):
    svg.append(f'<text x="1460" y="{y}" font-size="{size}" fill="{color}">{text}</text>')


def mm(x):
    return str(round(x*1000)) if x is not None else 'brak przecięcia'


text_line('WYMIARY GEOMETRII V2',180,26)
text_line(f'1. Środek siedziska: {mm(seat_z)} mm',230)
text_line(f'2. Środek poduszki głowy: {mm(head_z)} mm',275)
text_line(f'Poduszka nad siedziskiem: {mm(head_z-seat_z)} mm',320)
text_line(f'Prześwit siedziska: {mm(clear_width)} mm',365)
text_line(f'Głębokość między wałkiem a tyłem: {mm(clear_depth)} mm',410)
text_line(f'Pochylenie oparcia: {math.degrees(tilt):.1f}° od pionu',455)
text_line('MANEKIN POGLĄDOWY',545,26)
text_line('Żółta linia: umowna osoba 200 cm.',590,21)
text_line('Proporcje segmentów są założone;',625,21)
text_line('rzeczywista osoba może mieć inne.',660,21)
text_line(f'Środek głowy: {mm(head_center.z)} mm',710)
text_line(f'Różnica względem poduszki: {mm(head_center.z-head_z)} mm',755)
text_line('Siedzisko i pianka bez obciążenia.',845,21)
text_line('Prześwity zależą od wysokości sondy.',880,21)
text_line('Brak testu ugięcia i nacisków.',915,21)
text_line('To materiał do wyboru wymiarów,',985,21)
text_line('nie gotowy projekt ergonomiczny.',1020,21)
text_line('Poza nie rozwiązuje kolizji z pianką',1070,21)
text_line('ani rzeczywistego ułożenia ciała.',1105,21)
svg += ['<text x="50" y="1310" font-size="22" fill="#263b37">1 BU = 1 m. Fotel pozostaje w wymiarach 900 × 1100 × 1150 mm. Model fotela nie został zmieniony.</text>',
        '</g></svg>']
(HERE/'fit_200cm.svg').write_text('\n'.join(svg),encoding='utf-8')
print('FIT_AUDIT',json.dumps(report['measurements']))
print('ILLUSTRATIVE_PERSON',json.dumps(report['illustrative_person']))
