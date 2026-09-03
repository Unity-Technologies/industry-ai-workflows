"""
dependency_vocab.py — named vocabularies for the free-text `dependencyType` field.

🔴 **`dependencyType` is FREE TEXT, not an enum.** Probed value-by-value against the live
API: 22 candidate values were submitted to
`POST /projects/{pid}/assets/{aid}/references` and **every one was accepted**, including
values invented on the spot (`unity_dependency`, `nested_prefab`, `link`). Zero rejections.

So the seven values the SDK and dashboard suggest are exactly that — suggestions. The API
enforces nothing and will never tell you that an edge is mislabelled.

## Why this module exists rather than a default

Because the field is free text, a client that emits `unity_material` is not picking a value
from an enum — it is **inventing a vocabulary**. Publishing that makes it a de facto standard
that other people's tooling has to understand, which is a platform decision and not a
client's to take silently.

So vocabularies here are **named and opt-in**:

* pass an explicit `dependency_type` and it is sent verbatim — always, no mapping, no
  validation. Raw passthrough is the escape hatch and it is never taken away.
* pass a `vocabulary` name and the type is derived from the file extensions.
* pass neither and **nothing is sent**.

Nothing writes a term unless a caller asked for it by name. If the AM backend later defines
`dependencyType` properly, a vocabulary can be deprecated in favour of the platform's own
without a breaking change to any call site.

⚠️ The coarse `type` field (`Dependency` | `Compound` | `Converted`) is separate and
server-set. The UPA Get-asset app's dependency traversal follows THAT, not `dependencyType`,
so choosing values here does not affect it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

# --------------------------------------------------------------------------------------
# Extension sets
# --------------------------------------------------------------------------------------

TEXTURE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".psd", ".exr", ".hdr",
    ".bmp", ".gif", ".svg", ".ktx", ".dds",
})
MATERIAL_EXTS = frozenset({".mat"})
SHADER_EXTS = frozenset({".shader", ".shadergraph", ".cginc", ".hlsl", ".compute"})
MODEL_EXTS = frozenset({".fbx", ".obj", ".dae", ".3ds", ".blend", ".gltf", ".glb", ".ply",
                        ".stl", ".3mf"})
SCRIPT_EXTS = frozenset({".cs", ".asmdef", ".inputactions"})
ANIMATION_EXTS = frozenset({".anim", ".controller", ".overridecontroller", ".mask",
                            ".playable", ".signal"})
AUDIO_EXTS = frozenset({".wav", ".mp3", ".ogg", ".aiff", ".aif", ".flac", ".mixer"})
FONT_EXTS = frozenset({".ttf", ".otf", ".fontsettings"})
PREFAB_EXTS = frozenset({".prefab"})
SCENE_EXTS = frozenset({".unity"})
USD_EXTS = frozenset({".usd", ".usda", ".usdc", ".usdz"})

# Raw DCC / authoring files. A Unity import of one of these is the SOURCE the engine-side
# asset was made from, which is a different relationship from referencing a mesh.
DCC_EXTS = frozenset({".blend", ".c4d", ".max", ".ma", ".mb", ".fbx", ".3ds", ".dae",
                      ".skp", ".lxo", ".jas"})

# CAD assembly formats — used by the `cad` vocabulary to tell a sub-assembly from a part.
CAD_ASSEMBLY_EXTS = frozenset({".sldasm", ".asm", ".catproduct", ".iam", ".prt.asm"})
CAD_PART_EXTS = frozenset({".sldprt", ".catpart", ".ipt", ".prt", ".step", ".stp",
                           ".iges", ".igs", ".jt", ".x_t", ".x_b", ".3dxml"})


def _ext(path: str) -> str:
    return PurePosixPath((path or "").replace("\\", "/")).suffix.lower()


# --------------------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Vocabulary:
    """One named set of `dependencyType` values, plus the rule that assigns them."""

    name: str
    summary: str
    values: tuple[str, ...]

    def classify(self, source_path: str, target_path: str) -> str:
        raise NotImplementedError


class _UnityVocabulary(Vocabulary):
    """Unity engine relationships, named for WHAT THE TARGET IS.

    That is the question a person actually asks of a dependency list — "what does this
    prefab pull in?" — textures, materials, a model. The exception is prefab→prefab, where
    the RELATIONSHIP (nesting) is the interesting part rather than the file type.

    Every value is `unity_`-prefixed on purpose: a project can hold CAD, USD and Unity
    content side by side, and `assembly_component` from a Pixyz import should stay
    distinguishable from `unity_material` at a glance. Neither vocabulary has to win.

    ORDER IS SIGNIFICANT — most specific first. See the branch comments.
    """

    def classify(self, source_path: str, target_path: str) -> str:
        source_ext = _ext(source_path)
        target_ext = _ext(target_path)

        # 1. USD targets keep the platform's own composition terms. They describe real USD
        #    composition, are widely understood, and are not Unity concepts to rename.
        if target_ext in USD_EXTS:
            return "usd_sublayer" if source_ext in USD_EXTS else "usd_reference"

        # 2. Textures first — the highest-value edge in AM's UI, and true of any source.
        if target_ext in TEXTURE_EXTS:
            return "unity_texture"
        # 3. Named for the target.
        if target_ext in MATERIAL_EXTS:
            return "unity_material"
        if target_ext in SHADER_EXTS:
            return "unity_shader"
        if target_ext in SCRIPT_EXTS:
            return "unity_script"
        if target_ext in ANIMATION_EXTS:
            return "unity_animation"
        if target_ext in AUDIO_EXTS:
            return "unity_audio"
        if target_ext in FONT_EXTS:
            return "unity_font"

        # 4/5. Prefab relationships. Nesting and scene-placement are genuinely
        #      different things and get different terms; collapsing them into one
        #      loses the distinction.
        if source_ext in PREFAB_EXTS and target_ext in PREFAB_EXTS:
            return "unity_nested_prefab"
        if source_ext in SCENE_EXTS and target_ext in PREFAB_EXTS:
            return "unity_prefab_instance"

        # 6. Geometry. A raw DCC file is the source the engine asset was imported FROM.
        if target_ext in MODEL_EXTS:
            return "unity_source_file" if target_ext in DCC_EXTS else "unity_model"

        # 7. Deliberately vague rather than wrong. An honest "there is an edge here" beats
        #    mislabelling it as something specific — nothing will ever correct the mistake.
        return "unity_dependency"


class _UsdVocabulary(Vocabulary):
    """USD composition arcs only — for pipelines whose content is USD end to end."""

    def classify(self, source_path: str, target_path: str) -> str:
        source_ext = _ext(source_path)
        target_ext = _ext(target_path)
        if target_ext in USD_EXTS:
            return "usd_sublayer" if source_ext in USD_EXTS else "usd_reference"
        if target_ext in TEXTURE_EXTS:
            return "usd_texture"
        return "usd_dependency"


class _CadVocabulary(Vocabulary):
    """The CAD/assembly terms AM's own dashboard and the Pixyz ingest path already use.

    These are the right words for CAD content. They describe CAD assemblies, so do not
    reach for them to describe relationships between *Unity* content.
    """

    def classify(self, source_path: str, target_path: str) -> str:
        target_ext = _ext(target_path)
        if target_ext in TEXTURE_EXTS:
            return "texture_dependency"
        if target_ext in CAD_ASSEMBLY_EXTS:
            return "sub_assembly"
        if target_ext in CAD_PART_EXTS:
            return "assembly_component"
        if target_ext in DCC_EXTS:
            return "source_file"
        # An engine-format model (glb/gltf/obj/…) hanging off CAD content is the
        # OUTPUT of a conversion, not a component of the assembly — this is the
        # edge the Pixyz ingest path records between a CAD asset and its export.
        if target_ext in MODEL_EXTS:
            return "converted"
        return "assembly_component"


UNITY = _UnityVocabulary(
    name="unity",
    summary="Unity engine relationships (unity_material, unity_texture, unity_nested_prefab, …)",
    values=(
        "unity_texture", "unity_material", "unity_shader", "unity_model",
        "unity_nested_prefab", "unity_prefab_instance", "unity_script", "unity_animation",
        "unity_audio", "unity_font", "unity_source_file", "unity_dependency",
        "usd_sublayer", "usd_reference",
    ),
)

USD = _UsdVocabulary(
    name="usd",
    summary="USD composition arcs (usd_sublayer, usd_reference, usd_texture)",
    values=("usd_sublayer", "usd_reference", "usd_texture", "usd_dependency"),
)

CAD = _CadVocabulary(
    name="cad",
    summary="CAD/assembly terms as used by the Pixyz ingest path and the AM dashboard",
    values=("assembly_component", "sub_assembly", "texture_dependency", "source_file",
            "converted"),
)

VOCABULARIES: dict[str, Vocabulary] = {v.name: v for v in (UNITY, USD, CAD)}


class UnknownVocabulary(ValueError):
    """Raised for a vocabulary name that is not registered.

    A typo must not fall back to a default: silently writing the wrong vocabulary's terms is
    exactly the failure this module exists to prevent, and the API will not reject them.
    """


def describe_vocabularies() -> list[dict[str, object]]:
    """Every registered vocabulary, for a `list_dependency_vocabularies` style tool."""
    return [
        {"name": v.name, "summary": v.summary, "values": list(v.values)}
        for v in VOCABULARIES.values()
    ]


def resolve_dependency_type(
    dependency_type: str = "",
    vocabulary: str = "",
    source_path: str = "",
    target_path: str = "",
) -> str:
    """Decide the `dependencyType` string to send, or "" to send none.

    Precedence, and the reason for it:

    1. **An explicit `dependency_type` always wins, verbatim.** The field is free text, so
       there is no vocabulary this server is entitled to impose on a caller who named a
       value. This is the raw passthrough path.
    2. **A named `vocabulary` classifies from the paths.** Opt-in: the caller asked for
       these terms by name.
    3. **Neither → "".** No type is written. Never invent one.

    Raises UnknownVocabulary for an unregistered name.
    """
    if dependency_type:
        return dependency_type
    if not vocabulary:
        return ""

    key = vocabulary.strip().lower()
    if key not in VOCABULARIES:
        raise UnknownVocabulary(
            f"Unknown dependency vocabulary '{vocabulary}'. "
            f"Registered: {', '.join(sorted(VOCABULARIES))}. "
            f"Pass dependency_type=... to send a value of your own instead."
        )

    # Classification is derived from file extensions, so with no paths there is nothing to
    # classify. Returning "" beats guessing — an unlabelled edge is recoverable, a wrongly
    # labelled one reads as fact forever.
    if not source_path and not target_path:
        return ""

    return VOCABULARIES[key].classify(source_path, target_path)
