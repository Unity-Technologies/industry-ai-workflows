"""UPA Execute custom script: bake an ambient-occlusion map into the scene's
materials and export the result.

Uses algo.combineMaterials with a BakeOption that toggles only the AO bake.
This is the supported high-level path — the bake AND the material wiring
happen in one call, so an exported GLB will carry the AO map in its
material's `ao` slot.

Conventions:
  - argparse for all inputs (UPA passes them via the action's `parameters`)
  - no SDK init — UPA handles it
  - the input scene must already have UVs unless --regenerate-uvs is set
  - output format is inferred from the extension; .glb embeds the AO texture
"""

import argparse
import os

import pxz
from pxz import core, io, algo


def process_asset(
    input_path: str,
    output_path: str,
    resolution: int,
    padding: int,
    singularize: bool,
    regenerate_uvs: bool,
) -> None:
    print(f"Importing: {input_path}")
    root = io.importScene(input_path)

    maps = algo.BakeMaps(
        diffuse=False, normal=False, roughness=False, metallic=False,
        opacity=False, ambientOcclusion=True, emissive=False,
    )
    options = algo.BakeOption(resolution=resolution, padding=padding, textures=maps)

    print(
        f"Combining materials with AO bake "
        f"(resolution={resolution}, padding={padding}, "
        f"singularizeOnAO={singularize}, overrideExistingUVs={regenerate_uvs})..."
    )
    algo.combineMaterials(
        [root],
        options,
        overrideExistingUVs=regenerate_uvs,
        singularizeOnAO=singularize,
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"Exporting: {output_path}")
    io.exportScene(output_path, root)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UPA: bake AO into materials via combineMaterials, then export.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input", required=True,
        help="Input scene path. Must already have UVs unless --regenerate-uvs is set.",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output path. Use .glb to embed the baked AO into the GLTF.",
    )
    parser.add_argument("--resolution", type=int, default=1024, help="AO map resolution (px)")
    parser.add_argument("--padding",    type=int, default=2,    help="Padding around UV islands (px)")
    parser.add_argument(
        "--singularize", action="store_true",
        help="Create per-occurrence material copies before baking. Use when shared "
             "materials would otherwise cause AO from one instance to bleed onto another.",
    )
    parser.add_argument(
        "--regenerate-uvs", action="store_true",
        help="Override existing UVs with a fresh atlas. Default: keep the existing UV channel.",
    )
    args = parser.parse_args()

    print(f"Asset Transformer version: {core.getVersion()}")
    process_asset(
        os.path.abspath(args.input),
        os.path.abspath(args.output),
        args.resolution,
        args.padding,
        args.singularize,
        args.regenerate_uvs,
    )


if __name__ == "__main__":
    main()
