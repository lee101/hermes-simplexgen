---
name: simplexgen-mesh-processing
description: Simplify (decimate), repair, voxelize, retopologize, UV-parameterize (RSP), remesh and texture GLB/OBJ/STL/PLY meshes with SimplexGen, including uploading local files and building LOD chains. Use when the user wants to reduce polycount, fix a broken or non-watertight mesh, make a voxel version, retopologize, or paint textures onto a model.
---

# SimplexGen mesh processing

Tools come from the `simplexgen` MCP server (`mcp__simplexgen__*`). Mesh tools
take a public `model_url` and return a new `model_url`; the input is never
modified. Every op spends credits only when it succeeds and reports
`credits_charged` / `credits_remaining`; check `account` before long chains.

## Uploading local files

The hosted server cannot read the user's disk. Get a single-use upload URL,
then send the file to it (no API key on the command line):

1. `create_upload_url` with `filename` (only the extension matters).
2. Run the returned command, e.g.
   `curl -fsS -T ./model.glb https://simplexgen.com/api/v1/upload/<token>`
3. The reply is `{"url": "https://..."}`; use that as `model_url` / `image_url`.

Accepted: `.glb .obj .stl .ply .fbx .png .jpg .jpeg .webp`, up to 100 MB. The
URL expires after 15 minutes and works once; request a new one per file.

## Operations

| Tool | Credits | Key args | Use for |
|---|---|---|---|
| `simplify_mesh` | 1 | `model_url`, `ratio` (fraction of faces kept, 0.01-0.99) | Polycount reduction, LODs, web/mobile budgets. Returns `stats.original_faces` / `simplified_faces` |
| `repair_mesh` | 1 | `model_url`, `output_format` | Fix normals, merge duplicate vertices, drop degenerate faces, fill holes. Falls back to a convex hull if still not watertight, so compare the result before using it for printing |
| `voxelize_mesh` | 1 | `model_url`, `voxel_size` (model units), `output_format` | Blocky/voxel art versions. Smaller size = more cubes; start near 1/50 of the model's longest side |
| `retopo_mesh` | 3 | `model_url`, `target_faces` (default 5000), `symmetry` | Clean, evenly sized quads for animation, sculpting or subdivision. Non-manifold or multi-part input is voxel-unified first |
| `parameterize_mesh` | 2 | `model_url`, `chart_angle`, `hard_edge_angle` | Rectangular surface parameterization: rectangle-aligned, seam-aware UV charts before texturing or baking. Keeps geometry. Max 60000 faces |
| `rectangular_remesh` | 2 | `model_url`, `voxel_size`, `subdivision_levels` | Axis-aligned hard-surface remesh with RSP UVs for stylized or blocky assets |
| `blender_mesh_op` | 1 (`info` free) | `model_url`, `op`, `params` | Bevel, solidify, mirror, weld, smooth, subdivide, uv_smart, fill_holes, center. Use `info` to inspect open edges for free |
| `run_generation_tool` slug `remeshing` | 1 | `object_url*`, `faces`, `output_format` | TripoSR remeshing |
| `run_generation_tool` slug `mesh-texturing`, `async: true` | `model_url*`, `prompt` or `image_url`, `resolution` (1024 or 2048) | Paint a texture onto an untextured mesh; poll `get_tool_job` |

Mesh ops accept `.glb .obj .stl .ply` (not multi-file `.gltf`). `simplify_mesh`
keeps the input format; repair, voxelize, retopo and Blender ops can convert with
`output_format`; `parameterize_mesh` and `rectangular_remesh` always return GLB
(UVs need it).

## Retopo then texture

For a scanned or generated mesh that needs to be textured or animated:

1. `blender_mesh_op` op `info` (free) to see faces and open edges.
2. `repair_mesh` if there are many open edges.
3. `retopo_mesh` with `target_faces` sized to the budget (2000-8000 for game props).
4. `parameterize_mesh` for clean UV charts.
5. `run_generation_tool` slug `mesh-texturing`, `async: true`.

If `parameterize_mesh` reports `uvMethod: rectangular-chart-fallback`, RSP did
not converge; the UVs are still valid but less regular. Mesh over 60000 faces?
`simplify_mesh` first.

## LOD chain

For game/web assets, derive LODs from the full-detail mesh, not from each
other:

1. `simplify_mesh` ratio 0.5 -> LOD1
2. `simplify_mesh` ratio 0.25 -> LOD2
3. `simplify_mesh` ratio 0.1 -> LOD3

Report face counts from `stats` for each level. If a ratio collapses thin parts
badly, raise it rather than repairing afterwards.

## 3D printing prep

`repair_mesh` with `output_format: stl`, then confirm the message reports
`Watertight: True`. If repair fell back to a convex hull, say so: the shape
changed and the user should fix the source mesh instead.

## Downloading results

`curl -fL -o out.glb "<model_url>"`. Result URLs may be signed and expire;
download anything the user wants to keep.

## Free local alternatives first

`simplify_mesh`, `repair_mesh`, `voxelize_mesh` and `blender_mesh_op` have free local equivalents in the `simplexgen-free-local-3d` skill (`local_mesh_simplify`, `local_mesh_repair`, `local_mesh_voxelize`, `local_blender_op`) that need no key and no upload. Run `local_mesh_inspect` first and reach for the paid tool only for what the local ones cannot do: clean quad `retopo_mesh` and `parameterize_mesh` charts without Blender installed, and AI `mesh-texturing`. With no hosted tools in your tool list, no key is configured: use the local tools and mention the paid option once, only if it matters.
