"""Validate the generated deliverables with Blender, without modifying them.

blender --background --python-exit-code 1 --python validate_model.py -- output
"""
import json
import struct
import sys
from pathlib import Path

import bmesh
import bpy

out = Path(sys.argv[sys.argv.index("--")+1]).resolve()
bpy.ops.wm.open_mainfile(filepath=str(out/"chair.blend"))
scene = bpy.context.scene
assert scene.unit_settings.system == "METRIC"
assert scene.unit_settings.scale_length == 1
root = bpy.data.collections["REFERENCE_CHAIR"]
objects = [o for c in root.children if not c.name.startswith("05") for o in c.objects]
assert len(objects) >= 20
points = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
lo = [min(p[k] for p in points) for k in range(3)]
hi = [max(p[k] for p in points) for k in range(3)]
dimensions = [hi[k]-lo[k] for k in range(3)]
assert all(abs(a-b)<1e-5 for a,b in zip(dimensions,[.9,1.1,1.15])), dimensions
assert abs(lo[2])<1e-6
parts = []
for ob in objects:
    assert ob.type == 'MESH'
    assert all(abs(s-1)<1e-7 for s in ob.scale)
    assert len(ob.data.vertices)>0
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    non_manifold = sum(not e.is_manifold for e in bm.edges)
    volume = bm.calc_volume(signed=True)
    parts.append({"part":ob.name,"non_manifold_edges":non_manifold,"signed_volume_m3":volume})
    bm.free()
    assert non_manifold==0, parts[-1]
    assert volume>0, parts[-1]

data = (out/"chair.glb").read_bytes()
magic, version, length = struct.unpack_from('<4sII',data)
assert magic==b'glTF' and version==2 and length==len(data)
chunk_len, chunk_type = struct.unpack_from('<I4s', data, 12)
assert chunk_type==b'JSON'
gltf = json.loads(data[20:20+chunk_len])
assert len(gltf['meshes'])==len(objects)
assert not gltf.get('cameras'), 'Studio must not be exported'
assert not any('Studio' in n.get('name','') for n in gltf['nodes'])
# glTF is metres, Y-up: Blender Z height -> glTF Y; Blender depth -> glTF Z.
glb_lo, glb_hi = [float('inf')]*3, [-float('inf')]*3
for mesh in gltf['meshes']:
    for p in mesh['primitives']:
        a = gltf['accessors'][p['attributes']['POSITION']]
        for k in range(3):
            glb_lo[k] = min(glb_lo[k], a['min'][k])
            glb_hi[k] = max(glb_hi[k], a['max'][k])
glb_dims = [glb_hi[k]-glb_lo[k] for k in range(3)]
assert all(abs(a-b)<1e-5 for a,b in zip(glb_dims,[.9,1.15,1.1])), glb_dims
report={"status":"PASS", "blender_version":bpy.app.version_string,
        "blend_dimensions_xyz_m":dimensions, "glb_dimensions_xyz_m":glb_dims,
        "closed_meshes_with_positive_volume":len(parts), "parts":parts}
(out/"validation.json").write_text(json.dumps(report,indent=2),encoding='utf-8')
print('VALIDATION_PASS', json.dumps({k:v for k,v in report.items() if k!='parts'}))
