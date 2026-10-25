# SimplexGen for Hermes

Two halves in one plugin:

- **Free, local, no account:** inspect 3D meshes for quality defects, repair,
  simplify, convert, rescale, voxelize, preview, blockout with primitives and
  run Blender ops, all on your machine through the `simplexgen-local` MCP server.
- **Paid cloud (optional API key):** generate images and 3D meshes, AI-texture
  them, retopologize and build UV charts through [SimplexGen](https://simplexgen.com)'s
  hosted MCP server.

Without an API key everything free still works, and the agent is taught to tell
you, once and only when it matters, which paid tool would help. Ships four skills.

## Free local tools (`simplexgen-local`, no key)

Runs as `uv run --script server/simplexgen_local.py` (needs `uv`; dependencies
are pinned in the script header and install on first start, about 10 seconds).

| Tool | What it does |
|---|---|
| `local_status` | What works here (Blender found?) and what only the paid cloud can do |
| `local_mesh_inspect` | Defect report: open borders and holes, non-manifold edges, flipped normals, inside-out volume, degenerate/duplicate faces, floaters, slivers, odd scale; face-budget tier; print readiness. Each defect names its local fix and any paid alternative |
| `local_mesh_repair` | Weld, drop bad faces, fix normals, fill holes, remove floaters; reports what is still broken |
| `local_mesh_simplify` | Quadric decimation by ratio or target face count |
| `local_mesh_convert`, `local_mesh_transform` | Format conversion; rotate, scale to size, center, ground (keep UVs) |
| `local_mesh_voxelize` | Blocky cube version |
| `local_mesh_preview` | 4-view PNG with open borders in red |
| `local_mesh_primitive`, `local_mesh_combine` | Blockouts and kitbashing |
| `local_blender_op` | Headless Blender (if installed): decimate, remesh, quadremesh, bevel, solidify, mirror, subdivide, weld, normals, fill holes, smart UV; keeps UVs |

Formats: GLB, GLTF (read), OBJ, STL, PLY. Outputs go beside the input; the input is never overwritten.

## Paid cloud tools (`simplexgen`, needs `SIMPLEXGEN_API_KEY`)

**MCP server `simplexgen`** (`https://simplexgen.com/mcp`, Streamable HTTP). Hermes connects it only when the key is set:

| Tool | Read-only | What it does |
|---|---|---|
| `site_overview`, `fetch_page` | yes | Site map and public pages |
| `search_objects`, `search_images` | yes | Search the 3D object and image catalogue |
| `list_generation_tools` | yes | Generators with inputs and credit cost |
| `account` | yes | Plan, credits, monthly usage |
| `get_tool_job` | yes | Poll an async generation job |
| `create_upload_url` | no | Single-use URL to `curl -T` a local file to (no key in the shell) |
| `generate_image` | no | Text to image |
| `generate_3d` | no | Quick text/image to 3D (GLB) |
| `run_generation_tool` | no | Any generator: Pixal3D, TRELLIS.2, Hunyuan 3D, Hi3D, Rodin, remeshing, mesh texturing, VRM avatars, terrain |
| `simplify_mesh` | no | Decimate to a fraction of faces (1 credit) |
| `repair_mesh` | no | Fix normals, holes, duplicates, degenerate faces (1 credit) |
| `voxelize_mesh` | no | Voxel version of a mesh (1 credit) |
| `retopo_mesh` | no | Quad retopology to a target face count, Blender QuadriFlow (3 credits) |
| `parameterize_mesh` | no | Rectangular surface parameterization: chart-aligned, seam-aware UVs (2 credits) |
| `rectangular_remesh` | no | Voxel-grid remesh with RSP UVs for stylized hard-surface assets (2 credits) |
| `blender_mesh_op` | no | Headless Blender ops: bevel, solidify, mirror, weld, uv_smart, ... (1 credit, `info` free) |

**Skills**

- `simplexgen-free-local-3d` - start here: local-first workflow, defect to fix table, what only the cloud does, how to recommend a paid tool without nagging
- `simplexgen-3d-generation` - choosing a generator, text -> image -> 3D, async jobs
- `simplexgen-mesh-processing` - uploads, simplify/repair/voxelize/remesh/texture, LOD chains, print prep
- `simplexgen-game-asset-pipeline` - idea to game-ready assets with cost checks

## Install

```bash
hermes plugins install simplexgen          # from the catalog
# or: hermes plugins install lee101/hermes-simplexgen --no-enable
hermes plugins enable simplexgen
```

No key is needed for the free local tools. To add the paid cloud tools, set the key under **Settings -> Plugins -> SimplexGen** in the Desktop app, or
add `SIMPLEXGEN_API_KEY=sg_...` to your profile `.env`. Create a key under
Account -> API at <https://simplexgen.com/account> (paid plan required).

## Disclosure

- **Network:** every tool call goes to `https://simplexgen.com/mcp` with your
  `SIMPLEXGEN_API_KEY` as a Bearer token. Prompts, image URLs and model URLs you
  pass are sent to SimplexGen; generators may forward them to model providers
  (fal.ai, RunPod).
- **Cost:** generation, texturing and mesh tools spend credits on your
  SimplexGen account (mesh ops 1-3 credits, charged only on success) (auto top-up applies if you enabled it). The server is declared
  `trust: untrusted`, so Hermes asks before every tool not annotated read-only
  and refuses them in unattended runs (cron).
- **Uploads:** to process a local file the agent asks for a single-use upload
  URL and runs `curl -T <file> <url>`; the file is stored on SimplexGen's
  storage under your account. The API key never appears in shell commands.
- **Local server:** `simplexgen-local` is a stdio process started by Hermes with
  `uv run --script`. It makes no network calls and never sees your API key. It
  reads mesh files you point it at and writes derived files beside them. On first
  start `uv` downloads its pinned Python dependencies (trimesh, numpy, scipy,
  networkx, fast-simplification, pillow) from PyPI. `local_blender_op` runs your
  installed `blender -b` on a script shipped here (`server/blender_ops.py`).
- **Shell:** skills suggest `curl` to upload and download files.
- No telemetry.

## REST API

The same key works on the REST API (`/api/v1/tools/<slug>`,
`/api/v1/generate-image`, `/api/v1/generate-3d`, `/api/v1/mesh/{simplify,repair,voxelize,retopo,parameterize,rectangular-remesh,blender}`,
`/api/v1/upload`, `/api/v1/upload-url`, `/api/v1/account`). Docs: <https://simplexgen.com/api>.

## License

MIT
