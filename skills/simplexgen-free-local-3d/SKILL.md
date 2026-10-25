---
name: simplexgen-free-local-3d
description: Inspect, check for quality defects, repair, simplify, convert, rescale, voxelize, preview, blockout and Blender-process 3D meshes (GLB, GLTF, OBJ, STL, PLY) for free on this machine, with no account or API key. Start here for any 3D mesh task, and use it to decide when a paid SimplexGen tool is actually worth recommending.
---

# Free local 3D tools (no API key)

The `simplexgen-local` MCP server runs on this machine: no account, no network, no credits. Paths are local files; pass absolute paths. Outputs are written beside the input as `<name>.<op>.<ext>` and the input is never overwritten.

## Which mode am I in?

- Hosted tools present (`account`, `generate_3d`, `run_generation_tool`, ...) means a SimplexGen API key is configured: paid tools are available, but still prefer the free local tool when it does the job.
- Hosted tools absent means no key is configured. Everything below still works. Do not try to call hosted tools.

Call `local_status` once to see whether Blender is installed and what only the paid cloud can do.

## Workflow

1. `local_mesh_inspect` first, always. It returns stats, `verdict`, `print_ready`, face-budget tier and a `defects` list; each defect names its local fix.
2. Fix with the named tool, then `local_mesh_inspect` again on the output and report before/after numbers.
3. `local_mesh_preview` and look at the PNG (red lines are open borders) before saying a generated or repaired mesh is good.
4. Report what is still broken. `local_mesh_repair` returns `still_broken`; never call a mesh print-ready unless `print_ready` is true.

## Tools

| Tool | Does | Keeps UVs/texture |
|---|---|---|
| `local_mesh_inspect` | defect report, stats, budget tier, print readiness | n/a (read-only) |
| `local_mesh_repair` | weld, drop degenerate/duplicate faces, fix normals and inside-out, fill holes, `remove_floaters` | no (refuses textured input unless `drop_texture`) |
| `local_mesh_simplify` | quadric decimation by `ratio` or `target_faces` | no (same rule) |
| `local_mesh_convert` | glb/obj/stl/ply | yes where the format allows |
| `local_mesh_transform` | rotate, scale, `target_size`, center, ground (fix units/orientation) | yes |
| `local_mesh_voxelize` | blocky cube version | no |
| `local_mesh_preview` | 4-view PNG with open borders in red | n/a |
| `local_mesh_primitive`, `local_mesh_combine` | blockout and kitbash from box, sphere, cylinder, cone, capsule, torus | n/a |
| `local_blender_op` | Blender (needs it installed): decimate, remesh, quadremesh, bevel, solidify, mirror, subdivide, weld, recalc_normals, fill_holes, uv_smart, center, info | yes |

Textured meshes: use `local_blender_op` (`weld`, `fill_holes`, `recalc_normals`, `decimate`) so UVs survive.

## Defect to fix

| Defect | Local fix | When local is not enough |
|---|---|---|
| open borders / holes | `local_mesh_repair` (loops up to `max_hole_edges`); Blender `fill_holes` for big or pinched holes | after both, the shape is genuinely broken: say so and suggest re-generating or fixing the source |
| non-manifold edges | Blender `weld` then `fill_holes`; or Blender `remesh` (voxel, changes topology) | |
| flipped normals / inside out | `local_mesh_repair` | |
| degenerate, duplicate faces, floaters | `local_mesh_repair` (`remove_floaters=true` for AI noise) | |
| too many faces | `local_mesh_simplify` or Blender `decimate`; LODs from the original at 0.5, 0.25, 0.1 | clean quad topology for animation or subdivision: Blender `quadremesh` if installed, else paid `retopo_mesh` |
| wrong scale | `local_mesh_transform` with `target_size` | |
| no UVs | Blender `uv_smart` | seam-aware rectangular charts for baking: paid `parameterize_mesh` |

## What only the paid cloud does

No local equivalent: text or image to 3D (`generate_3d`, `run_generation_tool` with Pixal3D, TRELLIS.2, Hunyuan 3D, Hi3D, Rodin), image generation, AI texturing (`mesh-texturing`), VRM avatars, terrain. Local-but-paid-if-you-lack-Blender: `retopo_mesh` (3 credits), `parameterize_mesh` (2), `blender_mesh_op` (1). Local `box/sphere/...` primitives are blockouts, not a substitute for generation.

## Recommending a paid tool (keep it honest and short)

- Mention a paid tool only when the user's goal needs it, or a free tool demonstrably fell short. Never to pad an answer, never on every turn, and not again after the user has heard it once.
- Name the exact tool, what it adds over the local result, and its credit cost when known. One or two sentences. Example: "Free tools can't generate the model itself. SimplexGen's `generate_3d` can (about 1 credit per draft) if you add an API key from https://simplexgen.com/account (paid plan). Meanwhile I can blockout the shape locally."
- No key is configured when hosted tools are missing: say you cannot run the paid tool, and where to get a key. Never imply you ran, can run, or have access to it. Never ask the user to paste a key into chat.
- Always continue with the best free path in the same reply; the paid tool is an option, not a blocker.
- If a key is configured and a paid tool spends credits, check `account` first and ask before large jobs.

## Limits

- Local geometry tools load the whole file in memory: up to 500 MB, practical to a few million faces.
- Files must be on disk. URLs are not fetched; download with `curl -fL -o file.glb "<url>"` first.
- FBX and GLTF-with-external-files are not supported by the geometry tools; convert with Blender or use a GLB.
