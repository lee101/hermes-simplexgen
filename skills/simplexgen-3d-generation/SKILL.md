---
name: simplexgen-3d-generation
description: Generate 3D meshes (GLB) from a text prompt or an image with SimplexGen, picking the right generator, running slow jobs asynchronously and polling them. Use when the user wants a 3D model, prop, character or asset created from words or a picture.
---

# SimplexGen 3D generation

Tools come from the `simplexgen` MCP server (`mcp__simplexgen__*`). Every
generation spends credits on the user's SimplexGen account and asks for
approval; read-only tools (`account`, `list_generation_tools`, `search_objects`,
`get_tool_job`) run without asking.

## Before generating

1. `search_objects` with the subject first. The catalogue already holds many
   generated and library models; reusing one costs nothing.
2. `account` to see the plan and remaining credits when the job is large or
   the user is cost-sensitive.
3. `list_generation_tools` for current slugs, inputs (`*` = required) and
   credit cost. Costs change; do not quote them from memory.

## Choosing a path

| Goal | Tool | Notes |
|---|---|---|
| Fast draft from text or image | `generate_3d` (`prompt` or `image_url`) | Synchronous, 1 credit, returns `model_url` + `thumbnail_url` |
| Best image-to-3D | `run_generation_tool` slug `pixal3d-image-to-3d` | `image_url*`, `texture_size` sets tier, `decimation_target` caps faces |
| Clean topology image-to-3D | `trellis2-image-to-3d` | `image_url*`, `resolution` |
| Text-to-3D with PBR | `hunyuan-text-to-3d` | `prompt*`, `enable_pbr` |
| Image-to-3D (Hunyuan) | `hunyuan-image-to-3d` | `input_image_url*` |
| High detail, face budget | `hi3d-image-to-3d` | `face_count`, `enable_texture` |
| Text/image multi-view | `rodin-hyper3d` | `prompt`, `input_image_urls`, `quality`, `tier` |
| VRM avatar | `vrm-character-creator` | `name*`, `prompt*` |
| Terrain | `terrain-generator` | |

Text-only requests usually look better as text -> image -> 3D: run
`generate_image` with a prompt describing one object, centred, plain
background, three-quarter view, then feed `image_url` to an image-to-3D tool.
Show the user the image before spending more credits on 3D.

## Slow tools: run async

Image-to-3D, texturing and high-resolution jobs can take minutes. Use
`run_generation_tool` with `async: true`; it returns `job_id`. Poll
`get_tool_job` every 10-20 s until `status` is `done`, then read `result`
(`code` is the HTTP status of the finished run). At most 3 jobs run per account
at once (HTTP 429 beyond that). Jobs are dropped an hour after they finish, so
save the URLs you need.

## Inputs and outputs

- Image inputs must be public URLs. For a local file, upload it first (see the
  `simplexgen-mesh-processing` skill, "Uploading local files").
- Outputs are URLs (usually GLB). Download with
  `curl -fL -o <name>.glb "<model_url>"` when the user wants the file locally.
- Errors: 401 bad key, 402 `subscription required` or `insufficient credits`
  (tell the user; do not retry), 429 too many running jobs.

## No API key?

If the hosted `simplexgen` tools are not in your tool list, no key is configured: you cannot generate here. Load the `simplexgen-free-local-3d` skill: say once, briefly, that generation needs a SimplexGen API key (https://simplexgen.com/account, paid plan), then offer what works free now (blockout with `local_mesh_primitive`, or inspecting and fixing a mesh the user already has). Do not claim you ran a generator.
