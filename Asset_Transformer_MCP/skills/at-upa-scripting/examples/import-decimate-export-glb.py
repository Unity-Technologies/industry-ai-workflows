"""UPA Execute custom script: import a STEP (or other CAD) file, tessellate
at a chosen quality preset (or custom params), decimate to a target triangle
ratio, export as GLB.

Validated reference script for the UPA "Execute custom script" action
(Asset Transformer). More involved than `import-tessellate-export-glb.py`
because it adds polygon reduction and exposes a quality/custom-tuning surface.

Conventions:
  - argparse for all inputs (UPA passes them via the action's `parameters` field)
  - no SDK init — UPA handles it
  - prints the tessellation params actually applied so you can read them from
    the job log
  - tessellates BEFORE decimation because STEP / CAD inputs are BREP and the
    decimator needs polygons to operate on
"""

import argparse
import os

import pxz
from pxz import core, io, algo, scene


# Tessellation presets — sensible starting points for "unknown CAD → GLB".
# Tuning notes:
#   maxSag   — max chord deviation in scene units. Smaller = finer.
#   sagRatio — sag scaled to the model's bounding box (dimensionless).
#              The main quality knob; lower = finer.
#   maxAngle — max angle (deg) between adjacent normals. Smaller = finer
#              tessellation along curved surfaces.
TESSELLATION_PRESETS: dict[str, dict[str, float]] = {
    "low":    {"max_sag": 0.5,  "sag_ratio": 0.0008, "max_angle": 25.0},
    "medium": {"max_sag": 0.1,  "sag_ratio": 0.0003, "max_angle": 15.0},
    "high":   {"max_sag": 0.05, "sag_ratio": 0.0001, "max_angle": 10.0},
}

CUSTOM_DEFAULTS = TESSELLATION_PRESETS["medium"]


def resolve_tess_params(args: argparse.Namespace) -> dict[str, float]:
    """Pick tessellation params from preset, or merge custom overrides on top
    of the medium-preset defaults."""
    if args.quality != "custom":
        return TESSELLATION_PRESETS[args.quality]
    return {
        "max_sag":   args.max_sag   if args.max_sag   is not None else CUSTOM_DEFAULTS["max_sag"],
        "sag_ratio": args.sag_ratio if args.sag_ratio is not None else CUSTOM_DEFAULTS["sag_ratio"],
        "max_angle": args.max_angle if args.max_angle is not None else CUSTOM_DEFAULTS["max_angle"],
    }


def process_asset(
    input_path: str,
    output_path: str,
    ratio: float,
    tess: dict[str, float],
) -> None:
    print(f"Importing: {input_path}")
    root = io.importScene(input_path)

    print(
        f"Tessellating (maxSag={tess['max_sag']}, sagRatio={tess['sag_ratio']}, "
        f"maxAngle={tess['max_angle']})..."
    )
    algo.tessellateRelativelyToAABB(
        [root],
        maxSag=tess["max_sag"],
        sagRatio=tess["sag_ratio"],
        maxLength=-1,
        maxAngle=tess["max_angle"],
        createNormals=True,
        uvMode=algo.UVGenerationMode.NoUV,
        uvChannel=0,
        uvPadding=0.0,
        createTangents=False,
        createFreeEdges=False,
        keepBRepShape=False,
        overrideExistingTessellation=False,
    )

    poly_before = scene.getPolygonCount([root])
    print(f"Polygons after tessellation: {poly_before}")

    print(f"Decimating to {ratio * 100:.0f}% of triangles...")
    algo.decimateTarget([root], ["ratio", float(ratio)])

    poly_after = scene.getPolygonCount([root])
    if poly_before > 0:
        reduction = 100 * (poly_before - poly_after) / poly_before
        print(f"Polygons after decimation: {poly_after} ({reduction:.1f}% reduction)")

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"Exporting GLB: {output_path}")
    io.exportScene(output_path, root)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UPA: import CAD, tessellate, decimate, export GLB.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input",  required=True, help="Input CAD/3D file path")
    parser.add_argument("--output", required=True, help="Output GLB file path")
    parser.add_argument(
        "--ratio", type=float, default=0.30,
        help="Triangle ratio to keep after decimation (0.0–1.0)",
    )
    parser.add_argument(
        "--quality", choices=["low", "medium", "high", "custom"], default="medium",
        help=(
            "Tessellation preset. "
            "low: coarse, fast, smallest GLB — good for AR/mobile or distant LODs. "
            "medium: balanced default for most realtime use. "
            "high: fine detail, larger GLB — engineering review or hero assets. "
            "custom: tune --max-sag / --sag-ratio / --max-angle directly."
        ),
    )
    # Custom-only overrides — ignored unless --quality custom.
    parser.add_argument(
        "--max-sag", type=float, default=None,
        help=(
            "Max chord deviation in scene units. Smaller = finer. "
            f"Typical 0.05 (fine) – 0.5 (coarse). Custom default: {CUSTOM_DEFAULTS['max_sag']}"
        ),
    )
    parser.add_argument(
        "--sag-ratio", type=float, default=None,
        help=(
            "Sag relative to bounding box (dimensionless). Main quality knob. "
            f"Typical 0.0001 (fine) – 0.001 (coarse). Custom default: {CUSTOM_DEFAULTS['sag_ratio']}"
        ),
    )
    parser.add_argument(
        "--max-angle", type=float, default=None,
        help=(
            "Max angle (deg) between adjacent normals. Smaller = finer along curves. "
            f"Typical 10 (fine) – 30 (coarse). Custom default: {CUSTOM_DEFAULTS['max_angle']}"
        ),
    )
    args = parser.parse_args()

    if args.quality != "custom" and any(
        v is not None for v in (args.max_sag, args.sag_ratio, args.max_angle)
    ):
        print(
            f"Note: --max-sag/--sag-ratio/--max-angle ignored (--quality={args.quality}). "
            "Use --quality custom to apply them."
        )

    print(f"Asset Transformer version: {core.getVersion()}")
    process_asset(
        os.path.abspath(args.input),
        os.path.abspath(args.output),
        args.ratio,
        resolve_tess_params(args),
    )


if __name__ == "__main__":
    main()
