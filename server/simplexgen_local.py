# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "trimesh==5.1.1",
#   "numpy==2.5.4",
#   "scipy==1.18.1",
#   "networkx==3.7",
#   "fast-simplification==0.2.0",
#   "pillow==12.3.0",
# ]
# ///
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import meshcore as mc  # noqa: E402
import trimesh  # noqa: E402
from minimcp import MiniMCP  # noqa: E402

INSTRUCTIONS = (
    "Free local 3D mesh tools (no account, no network): inspect with defect report, repair, simplify, convert, "
    "transform, voxelize, preview, primitives, combine, and Blender ops when Blender is installed. Start with local_mesh_inspect on any "
    "mesh. Each defect names its local fix and, only where it genuinely beats local tools, a paid SimplexGen tool. "
    "Paid tools (generation, AI texturing, retopo, UV charts) need SIMPLEXGEN_API_KEY: " + mc.KEY_NOTE
)

app = MiniMCP("simplexgen-local", INSTRUCTIONS)
RO = True
WRITE = False


def _fail(e):
    return json.dumps({"ok": False, "error": str(e)})


def _stats_line(s):
    return {k: s[k] for k in ("faces", "vertices", "boundary_edges", "holes", "nonmanifold_edges", "watertight", "components")}


@app.tool(RO)
def local_status() -> str:
    """What free local tools work on this machine and what only the paid SimplexGen cloud can do. Call once when the user asks for 3D work, especially if no hosted simplexgen tools are in your tool list."""
    exe = mc.find_blender()
    return json.dumps({
        "local_free": {
            "always": ["local_mesh_inspect", "local_mesh_repair", "local_mesh_simplify", "local_mesh_convert",
                       "local_mesh_transform", "local_mesh_voxelize", "local_mesh_preview", "local_mesh_primitive", "local_mesh_combine"],
            "blender": {
                "available": bool(exe),
                "version": mc.blender_version(exe) if exe else None,
                "tool": "local_blender_op",
                "ops": list(mc.BLENDER_OPS),
                "install_hint": None if exe else "Install Blender (free, blender.org) to unlock bevel, solidify, mirror, remesh, quadremesh, subdivide and UV-preserving decimate/repair.",
            },
            "formats": list(mc.FORMATS),
        },
        "paid_only": [
            mc.paid("generate"), mc.paid("texture"),
            *([] if exe else [mc.paid("retopo"), mc.paid("uv"), mc.paid("blender_hosted")]),
        ],
        "key_note": mc.KEY_NOTE,
    })


@app.tool(RO)
def local_mesh_inspect(path: str) -> str:
    """Analyse a local GLB/GLTF/OBJ/STL/PLY file and report quality defects: open borders and holes, non-manifold edges, flipped normals, inside-out volume, degenerate/duplicate faces, floaters, slivers, scale/unit problems, face-budget tier, print readiness. Each defect lists the local fix tool and any paid SimplexGen alternative. Free, read-only; run this before repairing, simplifying or printing anything."""
    try:
        p = mc.resolve_input(path)
        _, mesh, info = mc.load(p)
        s = mc.analyze(mesh, info)
        exe = mc.find_blender()
        d = mc.defects(s, bool(exe))
        errs = [x["id"] for x in d if x["severity"] == "error"]
        paid_opts = {x["tool"]: x for item in d for x in item["fix_paid"]}
        return json.dumps({
            "ok": True, "file": str(p), "stats": s, "budget_tier": mc.tier(s["faces"]),
            "verdict": mc.verdict(s), "print_ready": mc.print_ready(s), "defects": d,
            "next": ("local_mesh_repair" if errs and not s["textured"] else ("local_blender_op (keeps UVs)" if errs else "none needed")),
            "blender_available": bool(exe),
            "paid_options": list(paid_opts.values()),
            "key_note": mc.KEY_NOTE if paid_opts else None,
        })
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_repair(path: str, output: str = "", max_hole_edges: int = 64, remove_floaters: bool = False, drop_texture: bool = False) -> str:
    """Free local repair: weld duplicate vertices, drop degenerate and duplicate faces, fix flipped normals and inside-out volume, fill holes up to max_hole_edges boundary edges, optionally remove tiny floating shells. Writes <name>.repaired.<ext> beside the input (never overwrites it) and reports before/after defects honestly, including what is still broken. Geometry-only: textured meshes are refused unless drop_texture=true; use local_blender_op (weld, fill_holes, recalc_normals) to keep UVs."""
    try:
        p = mc.resolve_input(path)
        _, mesh, info = mc.load(p)
        if info["textured"] and not drop_texture:
            return _fail("mesh has a texture/UVs and this tool is geometry-only; use local_blender_op (weld, fill_holes, recalc_normals) to keep them, or pass drop_texture=true")
        before = mc.analyze(mesh, info)
        fixed, report = mc.repair(mc.geometry_only(mesh), max(3, min(int(max_hole_edges), 512)), remove_floaters)
        dst = mc.out_path(p, "repaired", output=output or None)
        fixed.export(str(dst))
        after = mc.analyze(fixed, {"parts": 1, "textured": False})
        remaining = [x["id"] for x in mc.defects(after, bool(mc.find_blender())) if x["severity"] == "error"]
        return json.dumps({
            "ok": True, "output": str(dst), "before": _stats_line(before), "after": _stats_line(after), **report,
            "watertight": after["watertight"], "still_broken": remaining,
            "note": None if not remaining else "Not fully fixed. Try local_blender_op weld then fill_holes, or local_blender_op remesh (voxel; changes topology). Say so plainly; do not call it print-ready.",
        })
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_simplify(path: str, ratio: float = 0.0, target_faces: int = 0, output: str = "", drop_texture: bool = False) -> str:
    """Free local quadric decimation. Give ratio (fraction of faces kept, 0.01-0.99) or target_faces. Writes <name>.simplified.<ext> beside the input. Geometry-only: UVs/textures are dropped, so textured meshes are refused unless drop_texture=true; for those use local_blender_op decimate (keeps UVs). Good for LOD chains: derive each LOD from the original, not from the previous LOD."""
    try:
        p = mc.resolve_input(path)
        _, mesh, info = mc.load(p)
        if info["textured"] and not drop_texture:
            return _fail("mesh has a texture/UVs and quadric decimation drops them; use local_blender_op decimate to keep UVs, or pass drop_texture=true")
        n = len(mesh.faces)
        r = (target_faces / n) if target_faces else ratio
        if not 0.01 <= r <= 0.99:
            return _fail("give ratio in 0.01-0.99 or a target_faces below the current face count")
        out = mc.simplify(mc.geometry_only(mesh), r)
        dst = mc.out_path(p, "simplified", output=output or None)
        out.export(str(dst))
        return json.dumps({"ok": True, "output": str(dst), "faces_before": n, "faces_after": int(len(out.faces)),
                           "kept": round(len(out.faces) / n, 4), "tier": mc.tier(len(out.faces))})
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_convert(path: str, format: str, output: str = "") -> str:
    """Free local format conversion between glb, obj, stl and ply (gltf can be read, not written). Keeps materials and UVs where the target format supports them. Writes <name>.converted.<format> beside the input unless output is given."""
    try:
        p = mc.resolve_input(path)
        loaded, _, _ = mc.load(p)
        dst = mc.out_path(p, "converted", format, output or None)
        loaded.export(str(dst))
        return json.dumps({"ok": True, "output": str(dst), "bytes": dst.stat().st_size})
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_transform(path: str, center: bool = False, ground: bool = False, target_size: float = 0.0, scale: float = 0.0,
                         rotate_x: float = 0.0, rotate_y: float = 0.0, rotate_z: float = 0.0, output: str = "") -> str:
    """Free local transform, keeping materials and UVs: rotate (degrees, applied x then y then z), scale by a factor or to target_size (longest side, in the model's units), center on the origin, then ground (rest the lowest point on the floor; floor axis is Y for glb/gltf, Z otherwise). Use it to fix wrong units and orientation before printing or importing into an engine. Writes <name>.transformed.<ext> beside the input."""
    try:
        import numpy as np

        p = mc.resolve_input(path)
        loaded, mesh, _ = mc.load(p)
        up = 1 if p.suffix.lower() in (".glb", ".gltf") else 2
        m = trimesh.transformations.identity_matrix()
        for axis, deg in (((1, 0, 0), rotate_x), ((0, 1, 0), rotate_y), ((0, 0, 1), rotate_z)):
            if deg:
                m = trimesh.transformations.rotation_matrix(np.radians(deg), axis) @ m
        verts = trimesh.transform_points(mesh.vertices, m)
        longest = float((verts.max(axis=0) - verts.min(axis=0)).max())
        s = scale if scale > 0 else (target_size / longest if target_size > 0 and longest > 0 else 1.0)
        m = trimesh.transformations.scale_matrix(s) @ m
        verts = trimesh.transform_points(mesh.vertices, m)
        lo, hi = verts.min(axis=0), verts.max(axis=0)
        t = np.zeros(3)
        if center:
            t = -(lo + hi) / 2
        if ground:
            t[up] = -lo[up]
            if not center:
                t[[i for i in range(3) if i != up]] = 0
        m = trimesh.transformations.translation_matrix(t) @ m
        if isinstance(loaded, trimesh.Scene):
            loaded.apply_transform(m)
        else:
            loaded.apply_transform(m)
        dst = mc.out_path(p, "transformed", output=output or None)
        loaded.export(str(dst))
        ext = (trimesh.transform_points(mesh.vertices, m))
        size = (ext.max(axis=0) - ext.min(axis=0))
        return json.dumps({"ok": True, "output": str(dst), "scale_applied": round(s, 6), "extents": [round(float(x), 5) for x in size]})
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_voxelize(path: str, voxel_size: float = 0.0, resolution: int = 32, solid: bool = True, output: str = "") -> str:
    """Free local voxel version of a mesh as a cube mesh (blocky/Minecraft style). voxel_size is in model units; if 0, resolution sets cubes along the longest side (default 32). solid=true fills the interior. Capped at 150000 cubes. Writes <name>.voxel.<ext> beside the input."""
    try:
        p = mc.resolve_input(path)
        _, mesh, _ = mc.load(p)
        g = mc.geometry_only(mesh)
        pitch = voxel_size if voxel_size > 0 else float((g.bounds[1] - g.bounds[0]).max()) / max(4, min(int(resolution), 256))
        boxes, count = mc.voxelize(g, pitch, solid)
        dst = mc.out_path(p, "voxel", output=output or None)
        boxes.export(str(dst))
        return json.dumps({"ok": True, "output": str(dst), "voxel_size": round(pitch, 6), "cubes": count})
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_preview(path: str, output: str = "", highlight_defects: bool = True, up_axis: str = "") -> str:
    """Free local 4-view preview PNG (front, side, top, iso, flat-shaded) with open-border edges drawn in red so holes are visible. Open the PNG with your image/vision tool to visually check a generated or repaired mesh. Large meshes are decimated for the picture only. up_axis y or z; default y for glb/gltf, z otherwise."""
    try:
        p = mc.resolve_input(path)
        _, mesh, _ = mc.load(p)
        dst = Path(output).expanduser().resolve() if output else p.with_name(p.stem + ".preview.png")
        up = (up_axis or ("y" if p.suffix.lower() in (".glb", ".gltf") else "z")).lower()
        mc.render(mesh, str(dst), up=up, highlight=highlight_defects)
        return json.dumps({"ok": True, "output": str(dst), "note": "red lines are open borders" if highlight_defects else None})
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_primitive(kind: str, output: str, size: str = "1,1,1", radius: float = 0.5, height: float = 1.0, sections: int = 32, position: str = "0,0,0") -> str:
    """Free local primitive generator for blockouts, kitbashing and placeholders: box (size "x,y,z"), sphere (radius), cylinder (radius, height), cone (radius, height), capsule (radius, height), torus (radius = major, height = minor tube radius). position is "x,y,z" of the centre. output is the .glb/.obj/.stl/.ply path to write. Combine several with local_mesh_combine. Not a substitute for generated assets: for organic or detailed models see the paid generate_3d tool (needs SIMPLEXGEN_API_KEY)."""
    try:
        import numpy as np

        def vec(text):
            vals = [float(x) for x in text.split(",")]
            if len(vals) != 3:
                raise ValueError(f"expected x,y,z, got {text!r}")
            return vals

        sec = max(8, min(int(sections), 128))
        cr = trimesh.creation
        makers = {
            "box": lambda: cr.box(extents=vec(size)),
            "sphere": lambda: cr.icosphere(subdivisions=3 if sec < 64 else 4, radius=radius),
            "cylinder": lambda: cr.cylinder(radius=radius, height=height, sections=sec),
            "cone": lambda: cr.cone(radius=radius, height=height, sections=sec),
            "capsule": lambda: cr.capsule(radius=radius, height=height, count=[sec // 2, sec]),
            "torus": lambda: cr.torus(major_radius=radius, minor_radius=height, major_sections=sec, minor_sections=max(8, sec // 2)),
        }
        if kind not in makers:
            return _fail(f"kind must be one of {', '.join(makers)}")
        m = makers[kind]()
        m.apply_translation(vec(position))
        dst = Path(output).expanduser().resolve()
        if dst.suffix.lower().lstrip(".") not in ("glb", "obj", "stl", "ply"):
            return _fail("output must end in .glb .obj .stl or .ply")
        dst.parent.mkdir(parents=True, exist_ok=True)
        m.export(str(dst))
        return json.dumps({"ok": True, "output": str(dst), "faces": int(len(m.faces))})
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_mesh_combine(paths: list[str], output: str) -> str:
    """Free local merge of several mesh files into one file at their existing world positions (position them first with local_mesh_transform or local_mesh_primitive position). Materials are kept in glb output. output is the .glb/.obj/.stl/.ply path to write; it must differ from every input."""
    try:
        if len(paths) < 2:
            return _fail("give at least two paths")
        scene = trimesh.Scene()
        for i, q in enumerate(paths):
            p = mc.resolve_input(q)
            loaded, _, _ = mc.load(p)
            geoms = loaded.dump(concatenate=False) if isinstance(loaded, trimesh.Scene) else [loaded]
            for j, g in enumerate(geoms):
                scene.add_geometry(g, geom_name=f"{p.stem}_{i}_{j}")
        dst = Path(output).expanduser().resolve()
        if dst.suffix.lower().lstrip(".") not in ("glb", "obj", "stl", "ply"):
            return _fail("output must end in .glb .obj .stl or .ply")
        if dst in {mc.resolve_input(q) for q in paths}:
            return _fail("refusing to overwrite an input file")
        dst.parent.mkdir(parents=True, exist_ok=True)
        scene.export(str(dst))
        return json.dumps({"ok": True, "output": str(dst), "parts": len(scene.geometry)})
    except Exception as e:
        return _fail(e)


@app.tool(WRITE)
def local_blender_op(path: str, op: str, params: str = "{}", output: str = "") -> str:
    """Free local headless Blender operation (needs Blender installed; local_status says if it is). Ops: info (stats, read-only), decimate {ratio}, planar {angle}, remesh {voxel_size}, quadremesh {target_faces}, smooth {angle}, flat, mirror {axis}, bevel {width,segments,angle}, solidify {thickness,offset}, subdivide {levels}, weld {distance}, recalc_normals, fill_holes {max_sides}, uv_smart {angle,margin}, center {size}. params is a JSON object string. Unlike the geometry-only local_mesh_* tools this keeps UVs. All meshes in the file are joined into one object. Writes <name>.<op>.<ext> beside the input."""
    try:
        exe = mc.find_blender()
        if not exe:
            return json.dumps({
                "ok": False, "error": "Blender is not installed",
                "free_fix": "Install Blender (free, blender.org); the geometry-only local_mesh_* tools work without it.",
                "paid_alternative": mc.paid("blender_hosted"), "key_note": mc.KEY_NOTE,
            })
        if op not in mc.BLENDER_OPS:
            return _fail(f"unknown op {op}; one of {', '.join(mc.BLENDER_OPS)}")
        p = mc.resolve_input(path)
        args = json.loads(params or "{}")
        if not isinstance(args, dict):
            return _fail("params must be a JSON object")
        dst = mc.out_path(p, op, output=output or None)
        res = mc.blender_run(exe, p, dst, op, args)
        return json.dumps({"ok": True, "output": None if op == "info" else str(dst), **res})
    except Exception as e:
        return _fail(e)


if __name__ == "__main__":
    app.run()
