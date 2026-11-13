# Optimisation recipes

Field-tested patterns for getting heavy CAD down to a real-time budget. Every
snippet below is written for the in-process `run_python` tool (`pxz` is a
global). For the UPA custom-script action, wrap the same calls in the
`at-upa-scripting` structure.

Each recipe is marked:

- **Verified** — run against a live, licensed SDK (2026.4) and the result checked.
- **Guidance** — the calls exist in `pxz-api-reference.md` and are used this way
  in the field, but the outcome depends on the model; check it on yours.

Before scripting any of these, check whether a tool already does it (see
[Tools vs. `run_python`](SKILL.md#tools-vs-run_python)). The tools add undo
steps, guard rails and a `script_equivalent` you can copy.

## Decimation selectors: the two keys that work

**Verified.** `algo.decimateTarget(occurrences, targetStrategy)` takes a
two-item selector list. Only two keys are accepted:

| Selector | Meaning |
|---|---|
| `["triangleCount", n]` | Keep `n` triangles across the given occurrences (per mesh if `processMeshIndependently=True`). |
| `["ratio", pct]` | Keep `pct` **percent** of the triangles: `50.0` halves the mesh, `0.5` keeps one in two hundred. |

> **An unknown key does not raise.** `["targetCount", n]` and `["polygonCount", n]`
> are accepted silently and decimate the mesh to **0 triangles**. Always read
> `scene.getPolygonCount(occs, True)` after a decimation and compare it with
> what you asked for.

```python
s = pxz.scene.getChildren(pxz.scene.getRoot())[0]
before = pxz.scene.getPolygonCount([s], True)
pxz.algo.decimateTarget([s], ["triangleCount", 20000])
after = pxz.scene.getPolygonCount([s], True)
assert 0 < after <= 20000, (before, after)
print(before, "->", after)
```

## Spend a triangle budget where it shows

**Verified.** A uniform ratio starves the large, visible surfaces and wastes
triangles on screws. To avoid that, share the budget out per part in
proportion to how much of the model each part covers, and give every part a
small floor so nothing collapses.

The `decimate_to_budget` tool does this, with name weights and a
`within_budget` report. The core of it, if you need to adapt it:

```python
sc, root = pxz.scene, pxz.scene.getRoot()
budget, floor = 250_000, 12
parts = sc.getPartOccurrences(root)
tris = [int(sc.getPolygonCount([p], True)) for p in parts]

def area(p):  # AABB surface area: the SDK has no mesh-area call
    a = sc.getAABB([p]); dx, dy, dz = a.high.x - a.low.x, a.high.y - a.low.y, a.high.z - a.low.z
    return 2 * (dx * dy + dy * dz + dz * dx)

# Reserve each part's floor first, then water-fill the rest by area,
# never giving a part more than it already has.
alloc = [min(floor, t) for t in tris]
room = [t - a for t, a in zip(tris, alloc)]
left = budget - sum(alloc)
active = [i for i, r in enumerate(room) if r > 0]
w = [area(p) for p in parts]
while active and left > 0:
    tot = sum(w[i] for i in active) or len(active)
    capped = [i for i in active if left * (w[i] or 1) / tot >= room[i]]
    if not capped:
        for i in active: alloc[i] += int(left * (w[i] or 1) / tot)
        break
    for i in capped: alloc[i] += room[i]; left -= room[i]
    active = [i for i in active if i not in capped]

for p, have, want in zip(parts, tris, alloc):
    if 0 < want < have:
        pxz.algo.decimateTarget([p], ["triangleCount", want])
print("total:", sc.getPolygonCount([root], True), "budget:", budget)
```

Instanced parts share one mesh, so decimating one instance decimates them all.
Run `instance_similar_parts` (or `convertSimilarPartOccurrencesToInstances`)
first, and budget the prototypes, not every copy.

## LOD chain to triangle budgets

**Verified (copy step)** / **Guidance (budgets).** To produce LODs at fixed
budgets (for example 200k / 50k / 10k), duplicate the source and decimate each
copy with `triangleCount`.

> **Do not duplicate with `scene.prototypeSubTree`.** The copy shares the
> original's mesh, so decimating it also decimates the original, even after
> `makeInstanceUnique`. A `.pxz` round-trip gives a fully independent copy.
> `generate_lods` uses that same round-trip.

```python
import os, tempfile
sc, root = pxz.scene, pxz.scene.getRoot()
src = sc.getChildren(root)[0]
budgets = [200_000, 50_000, 10_000]

with tempfile.TemporaryDirectory() as tmp:
    pxz_file = os.path.join(tmp, "lod_src.pxz")
    pxz.io.exportScene(pxz_file, src)
    for i, budget in enumerate(budgets, start=1):
        lod = pxz.io.importScene(pxz_file)
        sc.setOccurrenceName(lod, f"LOD{i}")
        pxz.algo.decimateTarget([lod], ["triangleCount", budget])
        print(f"LOD{i}", pxz.scene.getPolygonCount([lod], True))
```

For a budget per part inside each LOD, apply the budget recipe above to each
copy instead of a single `decimateTarget`.

## Perforated plates, grilles and meshes with many holes

**Verified (call sequence)** / **Guidance (results).** Sheet metal with
hundreds of punched holes is one of the worst cases for decimation. Every hole
rim is a boundary the decimator protects, so the triangle count barely moves,
and seams from UV islands pin even more vertices. Clear those constraints
first:

```python
sc, al, poly = pxz.scene, pxz.algo, pxz.polygonal
plate = 1234  # the plate occurrence

al.removeUV([plate])                          # 1. UV seams stop pinning vertices
al.removeHoles([plate], True, True, False, 5.0)   # 2. through + blind holes up to 5 units across
mask = poly.TopologyCategoryMask(poly.TopologyDimensionMask.FACE,
                                 poly.TopologyConnectivityMask.BOUNDARY)
al.mergeVertices([plate], 0.01, mask)         # 3. weld the open boundaries left behind
al.decimateTarget([plate], ["triangleCount", 2000])   # 4. now the decimator can work
print(sc.getPolygonCount([plate], True))
```

- `removeHoles(occs, throughHoles, blindHoles, surfacicHoles, maxDiameter)`:
  `maxDiameter=-1` removes every hole. Set a real diameter so that bolt holes
  you want to keep survive.
- Only remove UVs when you will re-unwrap them (`automaticUVMapping`) or do not
  need them, for example on flat-shaded vertex-colour output.
- `cleanup_mesh(merge_vertices=True)` and `fix_normals_uv(remove_uv=True)` are
  the tool equivalents of steps 1 and 3.

## Centre a part on the world origin (world-matrix maths)

**Verified.** Matrices are row-major 4×4 `list[list[float]]`, with the
translation in column 3 (`m[0][3]`, `m[1][3]`, `m[2][3]`).
`scene.setLocalMatrix` is relative to the parent. To move a part in **world**
space, express the world-space change in the parent's frame:

```
new_local = inverse(parent_global) @ T_world @ current_global
```

`numpy` is available in the AT process:

```python
import numpy as np
sc = pxz.scene
part = 1234
parent = sc.getParent(part)

a = sc.getAABB([part])
centre = [(a.low.x + a.high.x) / 2, (a.low.y + a.high.y) / 2, (a.low.z + a.high.z) / 2]
T = np.eye(4); T[:3, 3] = [-c for c in centre]          # world-space translation

G = np.array(sc.getGlobalMatrix(part))
PG = np.array(sc.getGlobalMatrix(parent))
sc.setLocalMatrix(part, (np.linalg.inv(PG) @ T @ G).tolist())
```

Writing `T @ local` instead is only correct when every ancestor has an
identity transform. Under a scaled or rotated parent it moves the part by the
wrong amount, in the wrong direction.

## Inside-out rims and flipped faces on open shells

**Verified (call)** / **Guidance (results).** Wheel rims, thin covers and
other open shells often import with mixed face orientation. With no closed
volume, `orientPolygonFaces` has no inside to reason about, and
back-face-culled viewers then show holes. Orient the faces toward a camera
placed outside, where the viewer will be, then rebuild the normals:

```python
G, al = pxz.geom, pxz.algo
rim = 1234
al.orientPolygonFacesFromCamera(
    [rim],
    G.Point3(0, 0, 2000),   # camera position, outside the part
    G.Point3(0, 0, -1),     # looking at it
    G.Point3(0, 1, 0),      # up
    1024,                   # resolution
)
al.createNormals([rim], 25, True)   # sharp-edge angle in degrees, override existing
```

For parts seen from several sides, run it once per main viewing direction,
or use `orientPolygonFaces` on closed parts. The `cleanup_mesh(orient_faces=True)`
tool uses `orientPolygonFaces`.

## Baking from a high-poly source: what transfers

**Verified (signature).** `algo.bakeVertexAttributes(destination, source,
skinnedMesh, positions, useCurrentPositionAsTPose=False)` transfers **joint
weights** (`skinnedMesh=True`) and **vertex positions** (`positions=True`).
It does **not** transfer normals, UVs or colours. After a decimated copy
inherits positions or skinning, rebuild its normals yourself:

```python
pxz.algo.bakeVertexAttributes([low], [high], False, True)
pxz.algo.createNormals([low], 25, True)
```

To carry surface detail from the high-poly onto the low-poly, bake **maps**
instead: `algo.beginBakingSession` + `algo.bakeNormalMap` (and so on) +
`algo.endBakingSession`, documented in `pxz-api-reference.md`.

## Hidden interior geometry

**Verified.** Internal brackets, fasteners and the inner walls of housings
often account for half of a CAD model's triangles and are never seen.
`remove_hidden_geometry` renders the model from a ring of outside viewpoints
(plus top and underbody) with
`algo.removeOccludedGeometriesFromViewPoints`, then deletes whatever no view
saw. `parts_only=True` removes whole parts only, which is the safe first
pass. Without it, the tool also removes hidden patches and polygons.

Run it **before** decimating, so the budget is not spent on interiors. Use
`consider_transparent_opaque=True` only if glass should hide what is behind
it.
