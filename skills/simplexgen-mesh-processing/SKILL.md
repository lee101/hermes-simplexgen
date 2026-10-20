---
name: simplexgen-mesh-processing
description: Simplify (decimate), repair, voxelize, remesh and texture GLB/OBJ/STL/PLY meshes with SimplexGen, including uploading local files and building LOD chains. Use when the user wants to reduce polycount, fix a broken or non-watertight mesh, make a voxel version, retopologize, or paint textures onto a model.
---

# SimplexGen mesh processing

Tools come from the `simplexgen` MCP server (`mcp__simplexgen__*`). Mesh tools
take a public `model_url` and return a new `model_url`; the input is never
modified.

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

| Tool | Key args | Use for |
|---|---|---|
| `simplify_mesh` | `model_url`, `ratio` (fraction of faces kept, 0.01-0.99) | Polycount reduction, LODs, web/mobile budgets. Returns `stats.original_faces` / `simplified_faces` |
| `repair_mesh` | `model_url`, `output_format` | Fix normals, merge duplicate vertices, drop degenerate faces, fill holes. Falls back to a convex hull if still not watertight, so compare the result before using it for printing |
| `voxelize_mesh` | `model_url`, `voxel_size` (model units), `output_format` | Blocky/voxel art versions. Smaller size = more cubes; start near 1/50 of the model's longest side |
| `run_generation_tool` slug `remeshing` | `object_url*`, `faces`, `output_format` | Clean quad/tri retopology to a target face count (spends credits) |
| `run_generation_tool` slug `mesh-texturing`, `async: true` | `model_url*`, `prompt` or `image_url`, `resolution` (1024 or 2048) | Paint a texture onto an untextured mesh; poll `get_tool_job` |

Mesh ops accept `.glb .obj .stl .ply` (not multi-file `.gltf`). `simplify_mesh`
keeps the input format; repair and voxelize can convert with `output_format`.

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
