import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy import sparse
from scipy.sparse import csgraph

FORMATS = ("glb", "gltf", "obj", "stl", "ply")
MAX_BYTES = 500 * 1024 * 1024
HERE = Path(__file__).resolve().parent

KEY_NOTE = (
    "Paid SimplexGen tools need SIMPLEXGEN_API_KEY (paid plan, https://simplexgen.com/account). "
    "If the hosted `simplexgen` tools (account, generate_3d, ...) are not in your tool list, no key "
    "is configured: say so once in one sentence, name the specific paid tool that would help, and "
    "carry on with the local tools. Never claim you ran or can run a paid tool without them."
)

PAID = {
    "retopo": {
        "tool": "retopo_mesh", "credits": 3,
        "why": "clean evenly sized quads for animation, sculpting or subdivision (local alternative: local_blender_op quadremesh if Blender is installed)",
    },
    "uv": {
        "tool": "parameterize_mesh", "credits": 2,
        "why": "rectangle-aligned seam-aware UV charts for texturing and baking (local alternative: local_blender_op uv_smart if Blender is installed)",
    },
    "texture": {
        "tool": "run_generation_tool mesh-texturing", "credits": None,
        "why": "AI texture painting from a prompt or reference image; no local equivalent",
    },
    "generate": {
        "tool": "generate_3d / run_generation_tool (Pixal3D, TRELLIS.2, Hunyuan 3D, Hi3D, Rodin)",
        "credits": None,
        "why": "text or image to 3D mesh and image generation; no local equivalent",
    },
    "blender_hosted": {
        "tool": "blender_mesh_op", "credits": 1,
        "why": "the same Blender ops without installing Blender locally",
    },
}


def paid(key, **extra):
    return {**PAID[key], "needs": "SIMPLEXGEN_API_KEY", **extra}


def resolve_input(path):
    p = Path(os.path.expanduser(str(path))).resolve()
    if not p.is_file():
        raise ValueError(f"not a file: {p}")
    ext = p.suffix.lower().lstrip(".")
    if ext not in FORMATS:
        raise ValueError(f"unsupported format .{ext}; supported: {', '.join(FORMATS)}")
    if p.stat().st_size > MAX_BYTES:
        raise ValueError("file larger than 500 MB")
    return p


def out_path(src, tag, fmt=None, output=None):
    fmt = (fmt or src.suffix.lstrip(".")).lower()
    if fmt not in FORMATS or fmt == "gltf":
        raise ValueError(f"output format must be one of glb, obj, stl, ply (got {fmt})")
    if output:
        p = Path(os.path.expanduser(str(output))).resolve()
        if p.suffix.lower().lstrip(".") not in FORMATS:
            raise ValueError("output must end in .glb .obj .stl or .ply")
    else:
        p = src.with_name(f"{src.stem}.{tag}.{fmt}")
    if p == src:
        raise ValueError("refusing to overwrite the input file")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load(path):
    loaded = trimesh.load(str(path), process=False)
    if isinstance(loaded, trimesh.Scene):
        parts = [g for g in loaded.dump(concatenate=False) if isinstance(g, trimesh.Trimesh)]
    elif isinstance(loaded, trimesh.Trimesh):
        parts = [loaded]
    else:
        parts = []
    if not parts or sum(len(p.faces) for p in parts) == 0:
        raise ValueError("no triangle mesh found in file")
    textured = any(getattr(p.visual, "kind", None) == "texture" for p in parts)
    mesh = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
    return loaded, mesh, {"parts": len(parts), "textured": textured}


def geometry_only(mesh):
    return trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float64).copy(),
        faces=np.asarray(mesh.faces, dtype=np.int64).copy(),
        process=False,
    )


def weld(vertices, faces, tol):
    keys = np.round(vertices / tol).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    merged = len(vertices) - len(first)
    return vertices[first], inverse[faces], merged


def _edge_keys(f, n):
    d = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    lo, hi = d.min(axis=1), d.max(axis=1)
    return d, lo.astype(np.int64) * n + hi, d[:, 0].astype(np.int64) * n + d[:, 1]


def _face_metrics(v, f):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    cross = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    sq = (
        np.sum((b - a) ** 2, axis=1) + np.sum((c - b) ** 2, axis=1) + np.sum((a - c) ** 2, axis=1)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        quality = np.where(sq > 0, 4 * math.sqrt(3) * area / sq, 0.0)
    return area, quality, np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0


def analyze(mesh, info):
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f0 = np.asarray(mesh.faces, dtype=np.int64)
    extents = (v.max(axis=0) - v.min(axis=0)) if len(v) else np.zeros(3)
    longest = float(extents.max()) if len(v) else 0.0
    tol = max(longest * 1e-6, 1e-12)
    wv, wf, merged = weld(v, f0, tol)
    collapsed = (wf[:, 0] == wf[:, 1]) | (wf[:, 1] == wf[:, 2]) | (wf[:, 2] == wf[:, 0])
    wf = wf[~collapsed]
    area, quality, volume = _face_metrics(wv, wf)
    tiny = area <= (longest ** 2) * 1e-12
    degenerate = int(collapsed.sum() + tiny.sum())
    sliver = int(((quality < 0.01) & ~tiny).sum())
    dup_faces = int(len(wf) - len(np.unique(np.sort(wf, axis=1), axis=0))) if len(wf) else 0

    n = max(len(wv), 1)
    directed, ukeys, dkeys = _edge_keys(wf, n)
    _, ucounts = np.unique(ukeys, return_counts=True)
    _, dcounts = np.unique(dkeys, return_counts=True)
    boundary_edges = int((ucounts == 1).sum())
    nonmanifold_edges = int((ucounts > 2).sum())
    inconsistent_edges = int((dcounts > 1).sum())

    holes = 0
    if boundary_edges:
        uk, uc = np.unique(ukeys, return_counts=True)
        bk = uk[uc == 1]
        a, b = bk // n, bk % n
        g = sparse.coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
        holes = int(csgraph.connected_components(g, directed=False)[0] - (n - len(np.unique(np.concatenate([a, b])))))

    g = sparse.coo_matrix(
        (np.ones(len(wf) * 2), (np.concatenate([wf[:, 0], wf[:, 1]]), np.concatenate([wf[:, 1], wf[:, 2]]))),
        shape=(n, n),
    )
    ncomp, labels = csgraph.connected_components(g, directed=False)
    face_comp = labels[wf[:, 0]] if len(wf) else np.zeros(0, dtype=int)
    sizes = np.bincount(face_comp, minlength=ncomp)
    sizes = sizes[sizes > 0]
    floor = max(8, int(0.005 * len(wf)))
    floaters = int(((sizes < floor) & (len(sizes) > 1)).sum()) if len(sizes) else 0

    watertight = boundary_edges == 0 and nonmanifold_edges == 0 and len(wf) > 0
    consistent = inconsistent_edges == 0
    return {
        "vertices": int(len(v)),
        "faces": int(len(f0)),
        "welded_vertices": int(len(wv)),
        "extents": [round(float(e), 5) for e in extents],
        "longest_side": round(longest, 5),
        "parts": info["parts"],
        "textured": info["textured"],
        "duplicate_vertices": int(merged),
        "degenerate_faces": degenerate,
        "sliver_faces": sliver,
        "duplicate_faces": dup_faces,
        "boundary_edges": boundary_edges,
        "holes": holes,
        "nonmanifold_edges": nonmanifold_edges,
        "inconsistent_winding_edges": inconsistent_edges,
        "components": int(len(sizes)),
        "floater_components": floaters,
        "watertight": bool(watertight),
        "winding_consistent": bool(consistent),
        "inside_out": bool(watertight and consistent and volume < 0),
        "volume": round(float(volume), 6) if watertight and consistent else None,
    }


def tier(faces):
    for limit, name in (
        (1500, "LOD3 / icon"), (8000, "mobile prop"), (40000, "game prop"),
        (150000, "desktop or web hero asset"), (600000, "high detail"),
    ):
        if faces <= limit:
            return name
    return "raw scan or AI output; decimate before engine use"


def defects(s, blender):
    out = []
    bl = " (Blender found)" if blender else " (needs Blender installed)"

    def add(id_, sev, count, why, local, paid_opts=()):
        out.append({"id": id_, "severity": sev, "count": count, "why": why, "fix_local": local, "fix_paid": list(paid_opts)})

    if s["degenerate_faces"]:
        add("degenerate_faces", "warn", s["degenerate_faces"], "zero-area triangles break shading, UV baking and slicers",
            "local_mesh_repair")
    if s["duplicate_faces"]:
        add("duplicate_faces", "warn", s["duplicate_faces"], "coincident faces z-fight and double-count volume", "local_mesh_repair")
    if s["duplicate_vertices"] and not s["textured"]:
        add("duplicate_vertices", "info", s["duplicate_vertices"], "unwelded seams; many exporters split vertices on purpose, so this only matters for printing or decimation",
            "local_mesh_repair")
    if s["boundary_edges"]:
        add("open_boundary", "error", s["boundary_edges"], f"{s['holes']} hole(s) / open border; not watertight, unprintable, bad for booleans and voxelizing",
            "local_mesh_repair (fills loops up to max_hole_edges)" if not s["textured"] else f"local_blender_op fill_holes{bl}")
    if s["nonmanifold_edges"]:
        add("nonmanifold_edges", "error", s["nonmanifold_edges"], "edges shared by 3+ faces; slicers and booleans fail",
            f"local_blender_op weld then fill_holes{bl}, or local_blender_op remesh (voxel, changes topology)")
    if s["inconsistent_winding_edges"]:
        add("flipped_normals", "error", s["inconsistent_winding_edges"], "neighbouring faces disagree on orientation; shading and inside/outside break",
            "local_mesh_repair" if not s["textured"] else f"local_blender_op recalc_normals{bl}")
    if s["inside_out"]:
        add("inside_out", "error", 1, "closed mesh with negative volume; renders dark and prints hollow", "local_mesh_repair")
    if s["floater_components"]:
        add("floaters", "warn", s["floater_components"], "tiny disconnected shells, typical of AI generation noise",
            "local_mesh_repair with remove_floaters=true")
    if s["sliver_faces"] > 0.02 * max(s["faces"], 1):
        add("slivers", "warn", s["sliver_faces"], "needle triangles from bad triangulation; hurt simplification and subdivision",
            f"local_blender_op remesh{bl} or local_mesh_simplify",
            [paid("retopo")])
    if s["faces"] > 150000:
        add("heavy", "warn", s["faces"], f"{s['faces']} faces is {tier(s['faces'])}", "local_mesh_simplify",
            [paid("retopo")] if s["faces"] > 600000 else [])
    if not s["textured"]:
        add("untextured", "info", 0, "no UV texture; fine for printing or flat shading",
            f"local_blender_op uv_smart{bl} for UVs only", [paid("uv"), paid("texture")])
    longest = s["longest_side"]
    if longest and (longest < 0.01 or longest > 1000):
        add("odd_scale", "warn", 1, f"longest side {longest}; likely wrong units (m vs mm vs cm)", "local_mesh_transform target_size")
    return out


def verdict(s):
    if not s["watertight"] or not s["winding_consistent"] or s["inside_out"]:
        return "needs_repair"
    if s["components"] > 1 and s["floater_components"]:
        return "needs_cleanup"
    return "clean"


def print_ready(s):
    return bool(s["watertight"] and s["winding_consistent"] and not s["inside_out"] and s["components"] >= 1 and (s["volume"] or 0) > 0)


def fill_holes(v, f, max_edges):
    n = len(v)
    d, ukeys, _ = _edge_keys(f, n)
    uk, inv, uc = np.unique(ukeys, return_inverse=True, return_counts=True)
    boundary = uc[inv] == 1
    nxt = {}
    for (a, b), is_b in zip(d, boundary):
        if is_b:
            nxt.setdefault(int(a), []).append(int(b))
    seen = set()
    new_v, new_f = [], []
    filled = 0
    for start in list(nxt):
        if start in seen:
            continue
        loop, cur, ok = [start], start, True
        while True:
            outs = nxt.get(cur, [])
            if len(outs) != 1:
                ok = False
                break
            cur = outs[0]
            if cur == start:
                break
            if cur in loop or len(loop) > max_edges:
                ok = False
                break
            loop.append(cur)
        seen.update(loop)
        if not ok or len(loop) < 3 or len(loop) > max_edges:
            continue
        if len(loop) == 3:
            new_f.append([loop[1], loop[0], loop[2]])
        else:
            c = v[loop].mean(axis=0)
            ci = n + len(new_v)
            new_v.append(c)
            for i, a in enumerate(loop):
                new_f.append([loop[(i + 1) % len(loop)], a, ci])
        filled += 1
    if new_f:
        if new_v:
            v = np.vstack([v, np.array(new_v)])
        f = np.vstack([f, np.array(new_f, dtype=np.int64)])
    return v, f, filled


def repair(mesh, max_hole_edges=64, remove_floaters=False):
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.faces, dtype=np.int64)
    longest = float((v.max(axis=0) - v.min(axis=0)).max())
    wv, wf, _ = weld(v, f, max(longest * 1e-6, 1e-12))
    collapsed = (wf[:, 0] == wf[:, 1]) | (wf[:, 1] == wf[:, 2]) | (wf[:, 2] == wf[:, 0])
    wf = wf[~collapsed]
    area, _, _ = _face_metrics(wv, wf)
    wf = wf[area > (longest ** 2) * 1e-12]
    wf = wf[np.sort(np.unique(np.sort(wf, axis=1), axis=0, return_index=True)[1])]
    removed_floaters = 0
    if remove_floaters:
        n = len(wv)
        g = sparse.coo_matrix(
            (np.ones(len(wf) * 2), (np.concatenate([wf[:, 0], wf[:, 1]]), np.concatenate([wf[:, 1], wf[:, 2]]))),
            shape=(n, n),
        )
        ncomp, labels = csgraph.connected_components(g, directed=False)
        fc = labels[wf[:, 0]]
        sizes = np.bincount(fc, minlength=ncomp)
        if (sizes > 0).sum() > 1:
            keep = sizes[fc] >= max(8, int(0.005 * len(wf)))
            removed_floaters = int((~keep).sum())
            wf = wf[keep]
    m = trimesh.Trimesh(vertices=wv, faces=wf, process=False)
    m.remove_unreferenced_vertices()
    try:
        trimesh.repair.fix_normals(m, multibody=True)
    except Exception:
        pass
    wv2, wf2, filled = fill_holes(np.asarray(m.vertices), np.asarray(m.faces), max_hole_edges)
    m = trimesh.Trimesh(vertices=wv2, faces=wf2, process=False)
    try:
        trimesh.repair.fix_normals(m, multibody=True)
    except Exception:
        pass
    return m, {"holes_filled": filled, "floater_faces_removed": removed_floaters}


def simplify(mesh, ratio):
    import fast_simplification

    v, f = fast_simplification.simplify(
        np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64),
        target_reduction=float(1 - ratio),
    )
    return trimesh.Trimesh(vertices=v, faces=f, process=False)


def voxelize(mesh, pitch, solid, max_cells=2_000_000):
    ext = mesh.bounds[1] - mesh.bounds[0]
    if float(np.prod(np.maximum(ext / pitch, 1))) > max_cells:
        raise ValueError("voxel_size too small: more than 2M cells; raise it")
    vg = mesh.voxelized(pitch)
    if solid:
        vg = vg.fill()
    if vg.filled_count > 150_000:
        raise ValueError(f"{vg.filled_count} cubes; raise voxel_size (limit 150000)")
    return vg.as_boxes(), int(vg.filled_count)


def render(mesh, out_png, up="y", size=512, highlight=True, max_faces=12000):
    from PIL import Image, ImageDraw

    full = geometry_only(mesh)
    m = simplify(full, max_faces / len(full.faces)) if len(full.faces) > max_faces else full
    v = np.asarray(m.vertices, dtype=np.float64)
    f = np.asarray(m.faces)
    if up == "y":
        v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1)
    centre = (v.max(axis=0) + v.min(axis=0)) / 2
    radius = float((v.max(axis=0) - v.min(axis=0)).max()) / 2 or 1.0
    v = (v - centre) / radius
    tri = v[f]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 0)
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    shade = 0.2 + 0.8 * np.abs(nrm @ light)
    colors = np.stack([shade * 200, shade * 210, shade * 230], axis=1).astype(int)
    segs = None
    if highlight:
        d, ukeys, _ = _edge_keys(f, len(v))
        uk, inv, uc = np.unique(ukeys, return_inverse=True, return_counts=True)
        sel = np.where(uc[inv] == 1)[0]
        if len(sel) > 6000:
            sel = sel[:: len(sel) // 6000 + 1]
        segs = v[d[sel]] if len(sel) else None
    ss = 2
    px = size * ss
    sheet = Image.new("RGB", (px * 2, px * 2), (255, 255, 255))
    for i, (elev, azim) in enumerate(((0, -90), (0, 0), (89, -90), (25, -50))):
        el, az = math.radians(elev), math.radians(azim)
        cam = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
        right = np.cross([0, 0, 1], cam)
        right /= np.linalg.norm(right)
        upv = np.cross(cam, right)
        scale = px * 0.46
        def proj(p):
            return np.stack([px / 2 + (p @ right) * scale, px / 2 - (p @ upv) * scale], axis=-1)
        img = Image.new("RGB", (px, px), (255, 255, 255))
        dr = ImageDraw.Draw(img)
        depth = (tri @ cam).mean(axis=1)
        pts = proj(tri)
        for j in np.argsort(depth):
            dr.polygon([tuple(q) for q in pts[j]], fill=tuple(colors[j]))
        if segs is not None:
            sp = proj(segs)
            for a, b in sp:
                dr.line([tuple(a), tuple(b)], fill=(220, 0, 0), width=3 * ss)
        sheet.paste(img, ((i % 2) * px, (i // 2) * px))
    sheet.resize((size * 2, size * 2), Image.LANCZOS).save(out_png)


def find_blender():
    exe = shutil.which("blender")
    if exe:
        return exe
    for c in (
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/snap/bin/blender",
        "/usr/local/bin/blender",
        "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe",
        "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe",
        "C:/Program Files/Blender Foundation/Blender 5.0/blender.exe",
    ):
        if os.path.isfile(c):
            return c
    return None


_blender_version = {}


def blender_version(exe):
    if exe not in _blender_version:
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
            _blender_version[exe] = (r.stdout.splitlines() or ["unknown"])[0]
        except Exception:
            _blender_version[exe] = "unknown"
    return _blender_version[exe]


BLENDER_OPS = (
    "info", "decimate", "planar", "remesh", "quadremesh", "smooth", "flat", "mirror", "bevel", "solidify",
    "subdivide", "weld", "recalc_normals", "fill_holes", "uv_smart", "center",
)


def blender_run(exe, src, dst, op, params):
    cmd = [exe, "-b", "--factory-startup", "--python", str(HERE / "blender_ops.py"), "--", str(src), str(dst), op, json.dumps(params or {})]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    for line in r.stdout.splitlines():
        if line.startswith("RESULT:"):
            return json.loads(line[7:])
    tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
    raise RuntimeError("blender failed: " + " | ".join(tail))
