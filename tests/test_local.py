import asyncio
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
import meshcore as mc  # noqa: E402


def sphere(**kw):
    return trimesh.creation.icosphere(subdivisions=3, **kw)


def info():
    return {"parts": 1, "textured": False}


def test_clean_sphere():
    s = mc.analyze(sphere(), info())
    assert s["watertight"] and s["winding_consistent"] and not s["inside_out"]
    assert s["holes"] == 0 and s["components"] == 1
    assert mc.verdict(s) == "clean" and mc.print_ready(s)


def test_hole_detected_and_filled():
    m = sphere()
    faces = m.faces[~(m.faces == 0).any(axis=1)]
    broken = trimesh.Trimesh(m.vertices, faces, process=False)
    s = mc.analyze(broken, info())
    assert not s["watertight"] and s["holes"] == 1 and s["boundary_edges"] > 3
    fixed, rep = mc.repair(broken)
    t = mc.analyze(fixed, info())
    assert rep["holes_filled"] == 1 and t["watertight"] and t["winding_consistent"] and not t["inside_out"]


def test_flipped_and_inside_out():
    m = sphere()
    inv = trimesh.Trimesh(m.vertices, m.faces[:, ::-1], process=False)
    s = mc.analyze(inv, info())
    assert s["inside_out"] and mc.verdict(s) == "needs_repair"
    fixed, _ = mc.repair(inv)
    assert not mc.analyze(fixed, info())["inside_out"]
    half = m.faces.copy()
    half[::2] = half[::2, ::-1]
    s = mc.analyze(trimesh.Trimesh(m.vertices, half, process=False), info())
    assert s["inconsistent_winding_edges"] > 0
    fixed, _ = mc.repair(trimesh.Trimesh(m.vertices, half, process=False))
    t = mc.analyze(fixed, info())
    assert t["winding_consistent"] and t["watertight"]


def test_degenerate_duplicate_and_floater():
    m = sphere()
    v = np.vstack([m.vertices, m.vertices[:1]])
    f = np.vstack([m.faces, [[0, 0, 1]], m.faces[:2]])
    small = trimesh.Trimesh([[0, 0, 0], [0.01, 0, 0], [0, 0.01, 0], [0, 0, 0.01]], [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], process=False)
    small.apply_translation([5, 0, 0])
    big = trimesh.Trimesh(v, f, process=False)
    cat = trimesh.util.concatenate([big, small])
    s = mc.analyze(cat, info())
    assert s["degenerate_faces"] >= 1 and s["duplicate_faces"] >= 2
    assert s["components"] == 2 and s["floater_components"] == 1
    fixed, rep = mc.repair(cat, remove_floaters=True)
    t = mc.analyze(fixed, info())
    assert t["components"] == 1 and t["degenerate_faces"] == 0 and t["duplicate_faces"] == 0
    assert rep["floater_faces_removed"] == 4


def test_simplify_and_voxelize():
    m = sphere()
    out = mc.simplify(m, 0.25)
    assert 0.15 < len(out.faces) / len(m.faces) < 0.35
    boxes, n = mc.voxelize(m, 0.25, True)
    assert n > 0 and len(boxes.faces) == n * 12 or len(boxes.faces) > 0


def test_defect_advice_paid_only_where_useful():
    s = mc.analyze(sphere(), info())
    ids = {d["id"]: d for d in mc.defects(s, False)}
    assert "open_boundary" not in ids
    assert ids["untextured"]["fix_paid"], "untextured mesh should advertise uv/texture options"
    assert all(o["needs"] == "SIMPLEXGEN_API_KEY" for o in ids["untextured"]["fix_paid"])
    sp = sphere()
    broken = trimesh.Trimesh(sp.vertices, sp.faces[~(sp.faces == 0).any(axis=1)], process=False)
    ids = {d["id"]: d for d in mc.defects(mc.analyze(broken, info()), False)}
    assert ids["open_boundary"]["fix_paid"] == []


def test_resolve_input_and_overwrite_guard(tmp_path):
    f = tmp_path / "a.glb"
    sphere().export(str(f))
    p = mc.resolve_input(f)
    with pytest.raises(ValueError):
        mc.out_path(p, "x", output=str(f))
    with pytest.raises(ValueError):
        mc.resolve_input(tmp_path / "missing.glb")
    bad = tmp_path / "a.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        mc.resolve_input(bad)


def test_mcp_roundtrip(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    src = tmp_path / "ball.glb"
    m = sphere()
    trimesh.Trimesh(m.vertices, m.faces[~(m.faces == 0).any(axis=1)], process=False).export(str(src))

    async def run():
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server" / "simplexgen_local.py")])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                assert "SIMPLEXGEN_API_KEY" in (init.instructions or "")
                names = {t.name for t in (await s.list_tools()).tools}
                assert {"local_status", "local_mesh_inspect", "local_mesh_repair", "local_blender_op"} <= names
                call = lambda n, a: s.call_tool(n, a)
                out = json.loads((await call("local_mesh_inspect", {"path": str(src)})).content[0].text)
                assert out["ok"] and out["verdict"] == "needs_repair" and not out["print_ready"]
                rep = json.loads((await call("local_mesh_repair", {"path": str(src)})).content[0].text)
                assert rep["ok"] and rep["watertight"] and Path(rep["output"]).exists()
                prev = json.loads((await call("local_mesh_preview", {"path": rep["output"]})).content[0].text)
                assert prev["ok"] and Path(prev["output"]).stat().st_size > 5000
                tr = json.loads((await call("local_mesh_transform", {"path": str(src), "target_size": 2.0, "ground": True, "center": True})).content[0].text)
                assert tr["ok"] and abs(max(tr["extents"]) - 2.0) < 1e-3
                prim = tmp_path / "cube.glb"
                pr = json.loads((await call("local_mesh_primitive", {"kind": "box", "output": str(prim), "size": "2,1,1", "position": "5,0,0"})).content[0].text)
                assert pr["ok"] and prim.exists()
                cb = json.loads((await call("local_mesh_combine", {"paths": [str(src), str(prim)], "output": str(tmp_path / "both.glb")})).content[0].text)
                assert cb["ok"] and cb["parts"] == 2
                bad = json.loads((await call("local_mesh_combine", {"paths": [str(src), str(prim)], "output": str(prim)})).content[0].text)
                assert not bad["ok"]
                st = json.loads((await call("local_status", {})).content[0].text)
                assert st["key_note"] and st["local_free"]["blender"]["tool"] == "local_blender_op"

    asyncio.run(run())
