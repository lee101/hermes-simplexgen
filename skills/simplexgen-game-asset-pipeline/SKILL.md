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
LODs at 0.5 and 0.25 of that result's source. Use `remeshing` instead when the
user needs clean, even topology (animation, sculpting).

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
