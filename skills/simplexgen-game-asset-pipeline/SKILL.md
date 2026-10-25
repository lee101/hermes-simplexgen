---
name: simplexgen-game-asset-pipeline
description: End-to-end pipeline from an idea to game-ready 3D assets with SimplexGen - concept image, image-to-3D, texturing, simplification to a face budget, LODs and local download, with a cost check before each paid step. Use when the user asks for a set of props, a game-ready model, or assets for Unity, Unreal, Godot, three.js or Blender.
---

# Idea to game-ready asset

Combine the `simplexgen-3d-generation` and `simplexgen-mesh-processing` skills.
Every paid step needs approval, so batch the plan up front and tell the user
what it will spend.

## 1. Plan

- Pin down: object list, style (low-poly, stylized, realistic), target engine,
  face budget per asset (e.g. mobile prop 1-5k, PC prop 10-30k, hero 50k+),
  texture size.
- `account` for credits; `list_generation_tools` for current costs. Give the
  user a per-asset estimate and total before generating.
- `search_objects` for each item; offer free catalogue matches first.

## 2. Concept image

`generate_image` per asset: "<object>, <style>, single object, centred, plain
light background, three-quarter view, no text". Show the images; regenerate
only the rejected ones.

## 3. Image to 3D

`run_generation_tool` with `async: true`, slug `pixal3d-image-to-3d` (default)
or `trellis2-image-to-3d` (cleaner topology, hard-surface). Pass
`decimation_target` near the face budget when the tool supports it. Start all
assets (max 3 running at once), then poll `get_tool_job` for each.

## 4. Texture (if the mesh came back untextured)

`run_generation_tool` slug `mesh-texturing`, `async: true`, with the concept
`image_url` (keeps the look consistent) and `resolution` 1024 for props, 2048
for hero assets.

## 5. Budget and LODs

`simplify_mesh` with `ratio = budget / original_faces` (clamp 0.01-0.99), then
LODs at 0.5 and 0.25 of that result's source (1 credit each). Use `retopo_mesh`
(3 credits) instead when the user needs clean, even quads (animation,
sculpting), and `parameterize_mesh` (2 credits) for clean UVs before texturing.

## 6. Deliver

Download every final URL into a project folder:

```bash
mkdir -p assets/<name>
curl -fL -o assets/<name>/<name>.glb "<model_url>"
curl -fL -o assets/<name>/<name>_lod1.glb "<lod1_url>"
```

Summarise per asset: source tool, face counts per LOD, files written, credits
spent (from `credits_remaining` deltas). GLB imports directly into Godot,
three.js, Blender and Unreal; for Unity mention glTFast or converting to FBX
in Blender.

## No API key?

If the hosted `simplexgen` tools are not in your tool list, no key is configured: you cannot generate here. Load the `simplexgen-free-local-3d` skill: say once, briefly, that generation needs a SimplexGen API key (https://simplexgen.com/account, paid plan), then offer what works free now (blockout with `local_mesh_primitive`, or inspecting and fixing a mesh the user already has). Do not claim you ran a generator.

## Free local alternatives first

`simplify_mesh`, `repair_mesh`, `voxelize_mesh` and `blender_mesh_op` have free local equivalents in the `simplexgen-free-local-3d` skill (`local_mesh_simplify`, `local_mesh_repair`, `local_mesh_voxelize`, `local_blender_op`) that need no key and no upload. Run `local_mesh_inspect` first and reach for the paid tool only for what the local ones cannot do: clean quad `retopo_mesh` and `parameterize_mesh` charts without Blender installed, and AI `mesh-texturing`. With no hosted tools in your tool list, no key is configured: use the local tools and mention the paid option once, only if it matters.
