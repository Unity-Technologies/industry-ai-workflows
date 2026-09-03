"""In-process import -> repair -> tessellate -> repair mesh -> export GLB.

Written for the Asset Transformer MCP `run_python` tool. `pxz` is already a
global and the SDK is already initialized, so this script:
  - does NOT `import pxz` or call `pxz.initialize()`
  - takes inputs as literals (edit INPUT_PATH / OUTPUT_PATH) rather than argparse
  - operates on the live, stateful session and prints what it did

For the pipeline (UPA "Execute custom script") equivalent — argparse, /workspace
paths, main() guard — see the at-upa-scripting skill.
"""

# --- edit these two, or wire them to whatever the caller provides ---
INPUT_PATH = r"C:\models\bracket.step"
OUTPUT_PATH = r"C:\out\bracket.glb"

# pxz is global here. `from pxz import ...` is optional sugar; pxz.<module> works too.
from pxz import core, io, algo, scene

print(f"Asset Transformer version: {core.getVersion()}")

# Import into the live scene. Returns the root occurrence of the imported model.
model = io.importScene(INPUT_PATH)
print(f"imported occurrence id: {model}")

# Repair BRep before tessellation so the mesh is clean and oriented.
algo.repairCAD([model], tolerance=0.1, orient=True)

# Tessellate relative to the model's AABB — sagRatio scales with model size, so
# this behaves sensibly even when the source units/scale are unknown.
algo.tessellateRelativelyToAABB(
    [model],
    maxSag=-1,          # -1 => driven entirely by sagRatio
    sagRatio=0.0005,
    maxLength=-1,
    maxAngle=15.0,
    createNormals=True,
    uvMode=algo.UVGenerationMode.NoUV,
    keepBRepShape=False,  # drop exact BRep once tessellated; smaller session
)

# Clean up mesh topology after tessellation.
algo.repairMesh([model], tolerance=0.1, crackNonManifold=True, orient=False)

tris = scene.getPolygonCount([model], asTriangleCount=True)
print(f"triangles after prep: {tris}")

# Format is inferred from the .glb extension — there is no format= keyword.
io.exportScene(OUTPUT_PATH, model)
print(f"exported: {OUTPUT_PATH}")
