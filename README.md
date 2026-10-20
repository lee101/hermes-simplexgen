# SimplexGen for Hermes

Generate images and 3D meshes, then simplify, repair, voxelize, remesh and
texture them from Hermes Agent, through [SimplexGen](https://simplexgen.com)'s
hosted MCP server. Ships three skills that teach the agent the workflows.

## What you get

**MCP server `simplexgen`** (`https://simplexgen.com/mcp`, Streamable HTTP):

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
| `simplify_mesh` | no | Decimate to a fraction of faces |
| `repair_mesh` | no | Fix normals, holes, duplicates, degenerate faces |
| `voxelize_mesh` | no | Voxel version of a mesh |

**Skills**

- `simplexgen-3d-generation` - choosing a generator, text -> image -> 3D, async jobs
- `simplexgen-mesh-processing` - uploads, simplify/repair/voxelize/remesh/texture, LOD chains, print prep
- `simplexgen-game-asset-pipeline` - idea to game-ready assets with cost checks

## Install

```bash
hermes plugins install simplexgen          # from the catalog
# or: hermes plugins install lee101/hermes-simplexgen --no-enable
hermes plugins enable simplexgen
```

Set the key under **Settings -> Plugins -> SimplexGen** in the Desktop app, or
add `SIMPLEXGEN_API_KEY=sg_...` to your profile `.env`. Create a key under
Account -> API at <https://simplexgen.com/account> (paid plan required).

## Disclosure

- **Network:** every tool call goes to `https://simplexgen.com/mcp` with your
  `SIMPLEXGEN_API_KEY` as a Bearer token. Prompts, image URLs and model URLs you
  pass are sent to SimplexGen; generators may forward them to model providers
  (fal.ai, RunPod).
- **Cost:** generation and texturing tools spend credits on your SimplexGen
  account (auto top-up applies if you enabled it). The server is declared
  `trust: untrusted`, so Hermes asks before every tool not annotated read-only
  and refuses them in unattended runs (cron).
- **Uploads:** to process a local file the agent asks for a single-use upload
  URL and runs `curl -T <file> <url>`; the file is stored on SimplexGen's
  storage under your account. The API key never appears in shell commands.
- **Shell:** skills suggest `curl` to upload and download files. No code from
  this package runs locally; it contains only manifests and Markdown.
- No telemetry.

## REST API

The same key works on the REST API (`/api/v1/tools/<slug>`,
`/api/v1/generate-image`, `/api/v1/generate-3d`, `/api/v1/mesh/{simplify,repair,voxelize}`,
`/api/v1/upload`, `/api/v1/upload-url`, `/api/v1/account`). Docs: <https://simplexgen.com/api>.

## License

MIT
