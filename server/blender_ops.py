import bpy
import bmesh
import json
import math
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst, op, raw = argv[0], argv[1], argv[2], argv[3] if len(argv) > 3 else "{}"
params = json.loads(raw)


def num(key, default):
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return default


def load(path):
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == "obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == "stl":
        bpy.ops.wm.stl_import(filepath=path)
    elif ext == "ply":
        bpy.ops.wm.ply_import(filepath=path)
    else:
        raise SystemExit("unsupported input " + ext)


def save(path):
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("glb", "gltf"):
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
    elif ext == "obj":
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
    elif ext == "stl":
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True)
    elif ext == "ply":
        bpy.ops.wm.ply_export(filepath=path, export_selected_objects=True)
    else:
        raise SystemExit("unsupported output " + ext)


def merged():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("no mesh in file")
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(max(obj.dimensions) * 1e-5, 1e-7))
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def counts(obj):
    me = obj.data
    return len(me.vertices), len(me.polygons)


def non_manifold(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    edges = sum(1 for e in bm.edges if not e.is_manifold)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    bm.free()
    return edges, loose


def modifier(obj, kind, **props):
    m = obj.modifiers.new(name=kind.lower(), type=kind)
    for k, v in props.items():
        setattr(m, k, v)
    bpy.ops.object.modifier_apply(modifier=m.name)


def remesh(obj):
    size = num("voxel_size", 0.02)
    if size <= 0:
        raise SystemExit("voxel_size must be positive")
    dims = max(obj.dimensions)
    if dims / size > 400:
        raise SystemExit("voxel_size too small for model extent")
    modifier(obj, "REMESH", mode="VOXEL", voxel_size=size, use_smooth_shade=True)
    return "voxel remesh %.4f" % size


def components(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    seen, n = set(), 0
    for v in bm.verts:
        if v.index in seen:
            continue
        n += 1
        stack = [v]
        while stack:
            c = stack.pop()
            if c.index in seen:
                continue
            seen.add(c.index)
            stack.extend(e.other_vert(c) for e in c.link_edges)
    bm.free()
    return n


def quadriflow(obj):
    target = int(num("target_faces", 5000))
    target = max(100, min(target, 200000))
    prep = ""
    if non_manifold(obj)[0] or components(obj) > 1:
        modifier(obj, "REMESH", mode="VOXEL", voxel_size=max(obj.dimensions) / min(140, max(60, math.sqrt(target) * 3)), use_smooth_shade=True)
        prep = " after voxel unify"
    recalc(obj)
    res = bpy.ops.object.quadriflow_remesh(
        target_faces=target,
        use_mesh_symmetry=bool(params.get("symmetry", False)),
        use_preserve_sharp=True,
        use_preserve_boundary=True,
        seed=0,
    )
    if "FINISHED" not in res:
        raise SystemExit("quadriflow failed: " + str(res))
    return "quadriflow target %d%s" % (target, prep)


def decimate(obj):
    ratio = min(0.99, max(0.01, num("ratio", 0.5)))
    modifier(obj, "DECIMATE", ratio=ratio)
    return "decimate ratio %.3f" % ratio


def planar(obj):
    modifier(obj, "DECIMATE", decimate_type="DISSOLVE", angle_limit=math.radians(num("angle", 5)))
    return "planar dissolve"


def smooth(obj):
    angle = math.radians(num("angle", 30))
    bpy.ops.object.shade_smooth_by_angle(angle=angle)
    return "smooth by angle %.0f" % math.degrees(angle)


def flat(obj):
    bpy.ops.object.shade_flat()
    return "flat shading"


def mirror(obj):
    axis = str(params.get("axis", "x")).lower()
    flags = [axis == "x", axis == "y", axis == "z"]
    if not any(flags):
        raise SystemExit("axis must be x, y or z")
    modifier(obj, "MIRROR", use_axis=flags, use_clip=True, use_mirror_merge=True, merge_threshold=num("merge", 0.001))
    return "mirror " + axis


def bevel(obj):
    modifier(obj, "BEVEL", width=num("width", 0.01), segments=int(num("segments", 2)), limit_method="ANGLE", angle_limit=math.radians(num("angle", 30)))
    return "bevel"


def solidify(obj):
    modifier(obj, "SOLIDIFY", thickness=num("thickness", 0.02), offset=num("offset", -1))
    return "solidify"


def subdivide(obj):
    levels = int(max(1, min(3, num("levels", 1))))
    modifier(obj, "SUBSURF", levels=levels, render_levels=levels)
    return "subdivision %d" % levels


def weld(obj):
    modifier(obj, "WELD", merge_threshold=num("distance", 0.0001))
    return "weld"


def recalc(obj):
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return "normals recalculated"


def fill_holes(obj):
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.mesh.select_non_manifold(extend=False, use_wire=False, use_boundary=True, use_multi_face=False, use_non_contiguous=False, use_verts=False)
    bpy.ops.mesh.fill_holes(sides=int(num("max_sides", 64)))
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return "holes filled"


def uv_smart(obj):
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(num("angle", 66)), island_margin=num("margin", 0.02))
    bpy.ops.object.mode_set(mode="OBJECT")
    return "smart uv project"


def center(obj):
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.location = (0, 0, 0)
    bpy.ops.object.transform_apply(location=True)
    dims = max(obj.dimensions)
    target = num("size", 1.0)
    if dims > 0:
        s = target / dims
        obj.scale = (s, s, s)
        bpy.ops.object.transform_apply(scale=True)
    return "centered and scaled to %.3f" % target


def info(obj):
    return "info"


OPS = {
    "remesh": remesh,
    "quadremesh": quadriflow,
    "decimate": decimate,
    "planar": planar,
    "smooth": smooth,
    "flat": flat,
    "mirror": mirror,
    "bevel": bevel,
    "solidify": solidify,
    "subdivide": subdivide,
    "weld": weld,
    "recalc_normals": recalc,
    "fill_holes": fill_holes,
    "uv_smart": uv_smart,
    "center": center,
    "info": info,
}

if op not in OPS:
    raise SystemExit("unknown blender op %s (%s)" % (op, ", ".join(sorted(OPS))))

bpy.ops.wm.read_factory_settings(use_empty=True)
load(src)
obj = merged()
before = counts(obj)
nm_before = non_manifold(obj)
message = OPS[op](obj)
obj = bpy.context.view_layer.objects.active
after = counts(obj)
nm_after = non_manifold(obj)
if op != "info":
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    save(dst)
print("RESULT:" + json.dumps({
    "message": message,
    "vertices_before": before[0],
    "faces_before": before[1],
    "vertices_after": after[0],
    "faces_after": after[1],
    "open_edges_before": nm_before[0],
    "open_edges_after": nm_after[0],
    "loose_vertices_after": nm_after[1],
    "dimensions": [round(d, 5) for d in obj.dimensions],
}))
