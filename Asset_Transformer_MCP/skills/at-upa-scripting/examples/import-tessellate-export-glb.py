"""Import a CAD file, tessellate relative to its bounding box, repair the mesh,
and export to GLB.

Validated reference script for the UPA "Execute custom script" action
(Asset Transformer). Safe to copy verbatim into the action's `script` field —
adjust only the argparse defaults / processing steps for your workflow.

Conventions this example follows:
  - argparse for all inputs (UPA passes them via the action's `parameters` field)
  - no SDK init — UPA handles it
  - prints SDK version early for log diagnostics
  - writes outputs to a path the user supplies; chain an Asset Manager action
    downstream if you need to push the result back into Asset Manager
"""

import argparse
import os

import pxz
from pxz import core, io, algo, scene


def process_asset(input_path: str, output_path: str) -> None:
    print(f"Importing: {input_path}")
    root = io.importScene(input_path)

    print("Tessellating...")
    algo.tessellateRelativelyToAABB(
        [root],
        maxSag=0.1,
        sagRatio=0.0002,
        maxLength=-1,
        maxAngle=15,
        createNormals=True,
        uvMode=algo.UVGenerationMode.NoUV,
        uvChannel=0,
        uvPadding=0.0,
        createTangents=False,
        createFreeEdges=False,
        keepBRepShape=False,
        overrideExistingTessellation=False,
    )

    print("Repairing mesh...")
    algo.repairMesh([root], tolerance=0.1, crackNonManifold=True, orient=False)

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"Exporting GLB: {output_path}")
    io.exportScene(output_path, root)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import, tessellate and export to GLB using Asset Transformer SDK"
    )
    parser.add_argument("--input", required=True, help="Input CAD/3D file path")
    parser.add_argument(
        "--output", required=True, help="Output GLB file path (e.g. /workspace/output/model.glb)"
    )

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output)

    print(f"Asset Transformer version: {core.getVersion()}")
    process_asset(input_path, output_path)


if __name__ == "__main__":
    main()
