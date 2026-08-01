"""Mirror v2 — the ``features`` SCOPE (docs/design/mirror-semantics.md).

WHY THIS FILE EXISTS. v1's mirror had ONE field (``plane``) and INFERRED the
semantic from the body chain; §1 of the design proves with three measured numbers
that no inference rule can be right for every chain, because three legitimate
intents map onto the SAME tree shape and demand three different volumes. v2 does
not add a cleverer heuristic — it adds a ``scope`` to the DTO so the tree STATES
the intent, exactly as SolidWorks ("Features to Mirror"), Fusion (Mirror → Type:
Features) and Onshape do.

The four numbers this module pins, all measured (2026-07-29), each traceable to
§1's table and to the composition matrix's CM-1 entry:

* **30629.3807** — chain A with ``features: [hole, boss]``: the hole mirrored AND
  the boss duplicated. Unreachable under ANY v1 rule.
* **30309.3807** — the SAME chain as a bare ``mirror {plane}``: the ``body`` scope,
  which is what every pre-v2 persisted mirror normalises to. Locked deliberately:
  30629.3807 from an implicit mirror would require guessing "hole and boss" over
  "hole", the guess §1 proves unmakeable.
* **29600.0** — chain B, reachable BOTH ways (``body`` scope's most-recent-cut
  reading, and ``features: [pocket B]``). The two paths agreeing where they
  overlap is the strongest evidence the v2 mechanism means what v1 meant.
* **28800.0** — chain B' with ``features: [pocket A, pocket B]``. Under v1 this was
  the *symptom* of a rejected rule; under v2 it is the correct answer to "make the
  plate symmetric", and 29600.0 is the correct answer to "put pocket B on the other
  side". The mutual exclusion dissolves in the DTO, not in the kernel.

Everything else here guards the mechanism: TREE-order application (§8.1), the
per-feature tool store widened to every mirrorable verb WITHOUT moving the two v1
readers (§6.2 — the highest-risk hunk), reflected PLACEMENTS for a pattern (§4.5 —
the chirality argument), nested quadrant mirrors (§4.6), and one typed refusal per
refused kind (§4.7). Goldens: ``mirror-features-hole-boss-plate-40x40x20``,
``mirror-features-pocket-b-only-40x40x20``,
``mirror-features-both-pockets-40x40x20``.

Tolerances are the two documented golden tiers, reused verbatim — never ad-hoc.
"""

# reportPrivateUsage: the §6.2 store-separation and §4.5 drift-lock tests
# deliberately assert on the evaluator's INTERNAL seams (`_pattern_contribution`,
# `_mirror_scope_ids`, `EvaluationState`'s slots) — that separation is the whole
# risk this suite exists to pin, and it is invisible from the public boundary.
# reportUnknownMemberType: build123d's boolean ops carry Shape[Unknown] type params
# upstream, the same gap tessellate.py documents for export_gltf.
# pyright: reportPrivateUsage=false, reportUnknownMemberType=false

import copy
import hashlib
import math
import uuid
from typing import Any

import pytest
from build123d import Plane, Solid, Vector
from geometry.features import evaluate_tree
from geometry.features.evaluate import (
    EvaluationState,
    RecordedToolGroup,
    _apply_pattern,
    _pattern_contribution,
)
from geometry.kernel import build_box, measure_shape
from geometry.kernel.mirror import (
    MirrorUnreachableError,
    cut_reflected_tools,
    fuse_reflected_tools,
    reflect_tools,
)
from py_kit.schemas.features import (
    CircularPatternParamsV1,
    EvaluateTreeRequest,
    LinearPatternParamsV1,
    MirrorBodyScope,
    MirrorFeature,
    MirrorFeaturesScope,
    MirrorParamsV1,
)
from pydantic import ValidationError

#: The two REVIEWED golden tolerance tiers (docs/GEOMETRY-QA.md), reused verbatim:
#: planar-only compositions, and anything carrying a cylindrical face or a rotated
#: placement. Never an ad-hoc epsilon (CLAUDE.md conventions).
PLANAR_TOL = 1e-9
CURVED_TOL = 1e-8

PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000c0de")
XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}


# --- Tree-authoring DSL (this module owns its own; --import-mode=importlib) -------


def _fid(n: int) -> uuid.UUID:
    """A stable, readable feature id (deterministic — no uuid4 anywhere)."""
    return uuid.UUID(f"00000000-0000-0000-0000-{n:012d}")


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def rect_sketch(
    feature_id: uuid.UUID,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    plane: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A closed rectangle, unconstrained (the solver returns the authored
    positions bitwise, so any deviation is the KERNEL's)."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(plane or XY_PLANE),
                "entities": [
                    _line(f"e{i + 1}", corners[i], corners[(i + 1) % 4])
                    for i in range(4)
                ],
                "constraints": [],
            },
        },
    }


def extrude(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    distance_mm: float,
    operation: str = "add",
    *,
    merge: bool = True,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": operation,
                "direction": "normal",
                "merge": merge,
            },
        },
    }


def top_face(
    anchor_id: uuid.UUID, centroid: tuple[float, float, float], area_mm2: float
) -> dict[str, Any]:
    """A stage-1 planar-face ``SubshapeRef`` on a +Z face."""
    return {
        "kind": "subshape",
        "feature_id": str(anchor_id),
        "subshape_type": "face",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "face",
                "surface": "plane",
                "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                "centroid": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
                "area_mm2": area_mm2,
            },
        },
    }


def hole(
    feature_id: uuid.UUID,
    face: dict[str, Any],
    position: tuple[float, float, float],
    diameter_mm: float,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": face,
                "position": {"x": position[0], "y": position[1], "z": position[2]},
                "diameter_mm": diameter_mm,
                "depth": {"kind": "through_all"},
            },
        },
    }


def datum_offset(feature_id: uuid.UUID, base: str, offset_mm: float) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": base, "offset_mm": offset_mm, "flip": False},
        },
    }


def fillet(feature_id: uuid.UUID, radius_mm: float) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {"kind": "axis_parallel", "axis": "Z"},
                "radius_mm": radius_mm,
            },
        },
    }


def linear_pattern(
    feature_id: uuid.UUID,
    direction: tuple[float, float, float],
    spacing_mm: float,
    count: int,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "linear",
                    "direction": {
                        "x": direction[0],
                        "y": direction[1],
                        "z": direction[2],
                    },
                    "spacing_mm": spacing_mm,
                    "count": count,
                }
            },
        },
    }


def circular_pattern(
    feature_id: uuid.UUID,
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
    count: int,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "circular",
                    "axis_point": {
                        "x": axis_point[0],
                        "y": axis_point[1],
                        "z": axis_point[2],
                    },
                    "axis_direction": {
                        "x": axis_direction[0],
                        "y": axis_direction[1],
                        "z": axis_direction[2],
                    },
                    "angle_deg": angle_deg,
                    "count": count,
                }
            },
        },
    }


def mirror(
    feature_id: uuid.UUID,
    plane: dict[str, Any],
    selection: list[uuid.UUID] | None = None,
    *,
    explicit_body_scope: bool = False,
) -> dict[str, Any]:
    """A mirror feature. ``selection=None`` emits the params a PRE-V2 row carries
    (no ``scope`` key at all); ``explicit_body_scope`` emits the same meaning
    spelled out, which the byte-identity test compares against."""
    params: dict[str, Any] = {"plane": plane}
    if selection is not None:
        params["scope"] = {
            "kind": "features",
            "features": [
                {"kind": "feature", "feature_id": str(fid)} for fid in selection
            ],
        }
    elif explicit_body_scope:
        params["scope"] = {"kind": "body"}
    return {
        "id": str(feature_id),
        "feature": {"type": "mirror", "version": 1, "params": params},
    }


def _at(solid: Solid, origin: tuple[float, float, float]) -> Solid:
    """*solid* translated so its min corner sits at *origin* (build_box builds at
    the world origin)."""
    moved = solid.translate(Vector(*origin))
    assert isinstance(moved, Solid)
    return moved


def evaluate(features: list[dict[str, Any]]) -> Any:
    """Evaluate through the SAME path the REST route and the worker share."""
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(PART_ID),
                "tree_version": 1,
                "features": features,
                "linear_deflection": 0.1,
            }
        )
    )


def volume_of(features: list[dict[str, Any]], label: str) -> float:
    evaluation = evaluate(features)
    bad = [
        (str(r.feature_id), r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
        if r.status != "ok"
    ]
    assert not bad, f"{label}: tree did not evaluate clean: {bad}"
    props = evaluation.result.properties
    assert props is not None, f"{label}: evaluated ok but produced no body"
    return props.volume


def error_of(
    features: list[dict[str, Any]], label: str
) -> tuple[str, uuid.UUID | None]:
    """The ONE per-feature error of a tree that must degrade honestly, plus its
    ``upstream_feature_id`` (the offending SELECTED feature — what lets the UI
    name the true cause instead of blaming the mirror)."""
    evaluation = evaluate(features)
    errors = [r.error for r in evaluation.result.features if r.error is not None]
    assert len(errors) == 1, f"{label}: expected exactly one error, got {errors}"
    error = errors[0]
    return error.code, error.upstream_feature_id


def fingerprint(features: list[dict[str, Any]]) -> tuple[str, str]:
    """Byte-strength identity: the GLB's sha256 plus the exact repr of every mass
    property and topology count."""
    evaluation = evaluate(features)
    assert evaluation.glb is not None
    props = evaluation.result.properties
    assert props is not None
    return (
        hashlib.sha256(evaluation.glb).hexdigest(),
        repr(
            (
                props.volume,
                props.surface_area,
                (props.centroid.x, props.centroid.y, props.centroid.z),
                props.topology.model_dump(),
            )
        ),
    )


# --- The shipped fixtures: §1's chain A and chain B -------------------------------

S_BASE, F_BASE = _fid(1), _fid(2)
D_BOSS, S_BOSS, F_BOSS = _fid(13), _fid(11), _fid(12)
F_HOLE = _fid(31)
S_PA, F_PA, S_PB, F_PB = _fid(21), _fid(22), _fid(23), _fid(24)
D_MID, F_MIRROR = _fid(52), _fid(53)
D_CLEAR, F_MIRROR2, D_XZ_MID = _fid(51), _fid(54), _fid(55)
F_FILLET, F_PATTERN = _fid(61), _fid(41)

#: The 40x40x20 plate every chain below starts from (V = 32000 mm^3).
PLATE: list[dict[str, Any]] = [
    rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0),
    extrude(F_BASE, S_BASE, 20.0),
]
PLATE_VOLUME = 32000.0
#: The plate's pristine +Z face (area 1600, centroid (20,20,20)).
TOP = top_face(F_BASE, (20.0, 20.0, 20.0), 1600.0)
#: A YZ-parallel datum at x=20 — the plate's x-midplane — and its plane ref.
MIDPLANE = datum_offset(D_MID, "YZ", 20.0)
MIDPLANE_REF: dict[str, Any] = {"kind": "feature", "feature_id": str(D_MID)}

#: r4 through-bore removal, and the 8x8x5 boss addition (chain A's two deltas).
BORE_DV = math.pi * 4.0**2 * 20.0
BOSS_DV = 8.0 * 8.0 * 5.0

#: CHAIN A (mirror-semantics §1): plate -> hole Ø8 @(10,20) -> boss 8x8x5 at
#: x in [30,38] on a datum at z=20 -> datum YZ@20. The mirror is appended per case.
CHAIN_A: list[dict[str, Any]] = [
    *PLATE,
    hole(F_HOLE, TOP, (10.0, 20.0, 20.0), 8.0),
    datum_offset(D_BOSS, "XY", 20.0),
    rect_sketch(
        S_BOSS, 30.0, 30.0, 38.0, 38.0, {"kind": "feature", "feature_id": str(D_BOSS)}
    ),
    extrude(F_BOSS, S_BOSS, 5.0),
    MIDPLANE,
]

#: 4x20 pockets cut 10 mm deep from XY: A at x in [4,8], B at x in [14,18].
POCKET_DV = 4.0 * 20.0 * 10.0
CHAIN_B: list[dict[str, Any]] = [
    *PLATE,
    rect_sketch(S_PA, 4.0, 10.0, 8.0, 30.0),
    extrude(F_PA, S_PA, 10.0, "cut"),
    rect_sketch(S_PB, 14.0, 10.0, 18.0, 30.0),
    extrude(F_PB, S_PB, 10.0, "cut"),
    MIDPLANE,
]


# =================================================================================
# SECTION 1 — the four numbers (mirror-semantics §5)
# =================================================================================


def test_chain_a_with_an_explicit_selection_mirrors_the_hole_and_the_boss() -> None:
    """**30629.3807** — chain A, ``features: [hole, boss]`` (§5, golden
    ``mirror-features-hole-boss-plate-40x40x20``).

    The number NO v1 rule can produce. In tree order the hole's bore tool reflects
    to x=30 and is CUT (-320pi), then the boss prism reflects to x in [2,10] and is
    FUSED (+320): 31314.6904 -> 30309.3807 -> 30629.3807. Reaching it by inference
    would need "union the reflected body then re-subtract every tool set", which
    welds chain B's pocket A shut at 30400.0 (`test_seed4` in the composition
    matrix) — mutually exclusive under one rule, trivially separable in the DTO.
    """
    volume = volume_of(
        [*CHAIN_A, mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE, F_BOSS])],
        "chain A features [hole, boss]",
    )
    assert volume == pytest.approx(
        PLATE_VOLUME - 2 * BORE_DV + 2 * BOSS_DV, abs=CURVED_TOL
    )
    assert volume == pytest.approx(30629.380701702532, abs=CURVED_TOL)


def test_chain_a_without_a_scope_is_still_the_v1_body_semantic() -> None:
    """**30309.3807** — the SAME chain as a bare ``mirror {plane}`` (§5).

    Deliberate, not a shortfall: the DTO carries no selection, so it normalises to
    ``scope: body`` and runs the unchanged v1 path — the hole mirrored, the boss
    NOT duplicated. 30629.3807 from an implicit mirror would require GUESSING that
    the user meant hole-and-boss rather than hole. Locked so that a future
    "helpful" default (§3.3 refuses one) is a visible, reviewed test change.
    """
    volume = volume_of(
        [*CHAIN_A, mirror(F_MIRROR, MIDPLANE_REF)], "chain A implicit body scope"
    )
    assert volume == pytest.approx(PLATE_VOLUME - 2 * BORE_DV + BOSS_DV, abs=CURVED_TOL)
    assert volume == pytest.approx(30309.380701702525, abs=CURVED_TOL)


@pytest.mark.parametrize(
    ("label", "selection"),
    [
        ("body scope (v1, unchanged)", None),
        ("features [pocket B]", [F_PB]),
    ],
)
def test_chain_b_agrees_at_29600_in_both_spellings(
    label: str, selection: list[uuid.UUID] | None
) -> None:
    """**29600.0** — chain B, reachable BOTH ways (§5, golden
    ``mirror-features-pocket-b-only-40x40x20``).

    ``body`` scope runs v1's most-recent-cut reading (the 29600.0 that
    ``test_mirror_preserves_a_cut_that_precedes_the_mirrored_one`` has locked since
    `fa30220`, needing no edit); ``features: [pocket B]`` reaches the same value by
    the v2 mechanism. The two paths agreeing where they overlap is the strongest
    available evidence that v2 means what v1 meant — which is why this is
    parametrized over both spellings rather than asserted once.
    """
    volume = volume_of(
        [*CHAIN_B, mirror(F_MIRROR, MIDPLANE_REF, selection)], f"chain B {label}"
    )
    assert volume == pytest.approx(PLATE_VOLUME - 3 * POCKET_DV, abs=PLANAR_TOL)
    assert volume == pytest.approx(29600.0, abs=PLANAR_TOL)


def test_chain_b_prime_mirrors_both_pockets_at_28800() -> None:
    """**28800.0** — chain B', ``features: [pocket A, pocket B]`` (§5, golden
    ``mirror-features-both-pockets-40x40x20``).

    Under v1 this number was the SYMPTOM of a rejected rule ("reflect every tracked
    cut" broke the 29600.0 lock). Under v2 it is simply the answer to a DIFFERENT
    request — "make the plate symmetric" — and 29600.0 is the answer to "put pocket
    B on the other side". Four notches at x in [4,8], [14,18], [22,26], [32,36].
    """
    volume = volume_of(
        [*CHAIN_B, mirror(F_MIRROR, MIDPLANE_REF, [F_PA, F_PB])],
        "chain B' features [A, B]",
    )
    assert volume == pytest.approx(PLATE_VOLUME - 4 * POCKET_DV, abs=PLANAR_TOL)
    assert volume == pytest.approx(28800.0, abs=PLANAR_TOL)


def test_the_two_chain_b_readings_are_genuinely_different_bodies() -> None:
    """The point of the contract, asserted directly: one field distinguishes two
    intended solids from the same tree. 29600.0 vs 28800.0 — 800 mm^3 and 5 faces
    apart, so no tolerance could confuse them."""
    one = evaluate([*CHAIN_B, mirror(F_MIRROR, MIDPLANE_REF, [F_PB])])
    both = evaluate([*CHAIN_B, mirror(F_MIRROR, MIDPLANE_REF, [F_PA, F_PB])])
    assert one.result.properties is not None and both.result.properties is not None
    assert one.result.properties.volume - both.result.properties.volume == (
        pytest.approx(POCKET_DV, abs=PLANAR_TOL)
    )
    assert one.result.properties.topology.faces == 21
    assert both.result.properties.topology.faces == 26


def test_complete_the_half_agrees_by_value_but_not_by_bytes() -> None:
    """**60000.0** two ways (§5 / §6.1) — and the honest limit of the agreement.

    ``body`` scope runs the untouched union fallback; ``features: [base, pocket]``
    reaches the same VALUE by a different boolean sequence (one fuse of a reflected
    body vs. two booleans of reflected tools). Equal volume and equal topology
    counts are asserted; byte identity is NOT, because the two paths hand OCCT
    different boolean sequences and the tessellator walks faces in OCCT's order.
    That measured non-equality is exactly why §6.1 REFUSES to re-express the v1
    semantic as a special case of the v2 mechanism — it would trade a structural
    byte-identity guarantee for a hoped-for one.
    """
    chain = [
        *PLATE,
        rect_sketch(S_PA, 10.0, 10.0, 20.0, 30.0),
        extrude(F_PA, S_PA, 10.0, "cut"),
        datum_offset(D_CLEAR, "YZ", 40.0),
    ]
    plane_ref: dict[str, Any] = {"kind": "feature", "feature_id": str(D_CLEAR)}
    body_scope = evaluate([*chain, mirror(F_MIRROR, plane_ref)])
    features_scope = evaluate([*chain, mirror(F_MIRROR, plane_ref, [F_BASE, F_PA])])
    for label, evaluation in (("body", body_scope), ("features", features_scope)):
        props = evaluation.result.properties
        assert props is not None, label
        assert props.volume == pytest.approx(60000.0, abs=PLANAR_TOL), label
        assert props.bounding_box.max.x == pytest.approx(80.0, abs=PLANAR_TOL), label
        assert props.topology.model_dump() == {"faces": 16, "edges": 36, "shells": 1}


# =================================================================================
# SECTION 2 — the DTO: additive, legacy-compatible, no silent no-ops
# =================================================================================


def test_absent_scope_normalises_to_the_body_scope() -> None:
    """A persisted pre-v2 params blob (``{plane}`` only) reads as ``scope: body``
    — the additive migration of §3.2, so ``param_version`` stays 1 and no data
    migration is needed. Same for an explicitly-null scope, so a client that
    round-trips an omitted optional as ``null`` is not a 422."""
    for payload in (
        {"plane": {"kind": "datum_plane", "plane": "YZ"}},
        {"plane": {"kind": "datum_plane", "plane": "YZ"}, "scope": None},
    ):
        params = MirrorParamsV1.model_validate(payload)
        assert isinstance(params.scope, MirrorBodyScope)
        assert params.scope.kind == "body"


def test_absent_and_explicit_body_scope_are_byte_identical() -> None:
    """The legacy normalisation is BYTE-neutral: the same tree with no ``scope``
    key and with ``scope: {"kind": "body"}`` spelled out produce the identical GLB
    and identical mass properties.

    This is the permanent form of the "shipped goldens stay byte-identical"
    guarantee (§3.2): rather than pinning a GLB digest (which a glTF-writer upgrade
    would break for no geometric reason — the goldens deliberately do not pin
    ``glb_bytes``), it asserts the property that must hold FOREVER, namely that
    reading a pre-v2 row costs nothing. The one-off cross-version check — all 39
    goldens' GLB sha256 identical between this commit and the pre-v2 kernel — is
    recorded in docs/GEOMETRY-QA.md.
    """
    for label, chain in (("chain A", CHAIN_A), ("chain B", CHAIN_B)):
        absent = fingerprint([*chain, mirror(F_MIRROR, MIDPLANE_REF)])
        explicit = fingerprint(
            [*chain, mirror(F_MIRROR, MIDPLANE_REF, explicit_body_scope=True)]
        )
        assert absent == explicit, f"{label}: naming the v1 scope changed the body"


def test_an_empty_or_duplicated_selection_is_a_validation_error() -> None:
    """``min_length=1`` and the duplicate check are 422s at the boundary (§3.1 /
    §8.1), never a degradation to "did nothing" or a silent dedup: an empty
    selection is authoring nonsense, and naming a feature twice leaves the intent
    (twice? once?) unstated — the mistake v1 made."""
    ref = {"kind": "feature", "feature_id": str(F_HOLE)}
    with pytest.raises(ValidationError):
        MirrorFeaturesScope.model_validate({"kind": "features", "features": []})
    with pytest.raises(ValidationError) as duplicate:
        MirrorFeaturesScope.model_validate({"kind": "features", "features": [ref, ref]})
    assert "more than once" in str(duplicate.value)


def test_the_selection_joins_the_dependency_graph() -> None:
    """Each selected ``FeatureRef`` materialises into ``feature_dependencies``
    with the BODY-AFFECTING allowed-target rule (§3.1), which is what buys the
    write-time guarantees for free: deleting a mirrored feature is a
    409-with-dependents, a reorder re-checks strict-backward, and a
    forward/self/``sketch`` selection is a 422 before it can be an evaluation
    error."""
    from py_kit.schemas.features import (
        BODY_AFFECTING_FEATURE_TYPES,
        feature_references,
    )

    envelope = MirrorFeature.model_validate(
        mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE, F_BOSS])["feature"]
    )
    references = feature_references(envelope)
    scoped = [r for r in references if r.slot.startswith("scope.features")]
    assert [r.ref.feature_id for r in scoped] == [F_HOLE, F_BOSS]
    assert all(r.allowed_types == BODY_AFFECTING_FEATURE_TYPES for r in scoped)
    # The plane keeps its own datum-only rule.
    assert [r.slot for r in references if r.slot == "plane"] == ["plane"]


# =================================================================================
# SECTION 3 — determinism: TREE order, never array order (§8.1)
# =================================================================================


def test_array_order_does_not_change_the_result() -> None:
    """The reflected tools apply in the EVALUATION order of the selected features,
    so a permuted array is BYTE-identical (§8.1).

    Array order is UI-incidental — it depends on the order the user ctrl-clicked —
    so honouring it would make identical models tessellate to different bytes,
    breaking the RESEARCH §9 contract that a rebuild is a pure function of the
    tree. Chain A is the case with teeth: cut-then-fuse and fuse-then-cut are
    different boolean sequences on overlapping ground.
    """
    forward = fingerprint([*CHAIN_A, mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE, F_BOSS])])
    reversed_array = fingerprint(
        [*CHAIN_A, mirror(F_MIRROR, MIDPLANE_REF, [F_BOSS, F_HOLE])]
    )
    assert forward == reversed_array


def test_rebuilding_the_same_features_scope_mirror_is_byte_deterministic() -> None:
    """Gate 3 over the new path: three rebuilds, one fingerprint."""
    tree = [*CHAIN_A, mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE, F_BOSS])]
    assert len({fingerprint(tree) for _ in range(3)}) == 1


# =================================================================================
# SECTION 4 — §6.2, the highest-risk hunk: the v1 readers must not move
# =================================================================================


def test_widening_the_tool_store_leaves_the_v1_readers_untouched() -> None:
    """§6.2 — the v2 per-feature store never writes the v1 CUT slot.

    The v1 cut slot has TWO readers with two different documented rules
    (``_mirror_cut_tools``: the most recent cut however far back;
    ``_pattern_cut_tools``: the immediate predecessor only), so a v2 store that
    poured ADDITIVE tools into it would silently change what a ``body``-scope
    mirror and a pattern replicate. The two stores are therefore separate, and this
    asserts the separation at the state level: recording an additive tool for a
    captured feature must not touch ``last_cut_tools`` / ``last_cut_feature_id`` /
    ``last_cut_body_id``, and a feature NOT in the capture set must not be recorded
    at all.

    WHAT CHANGED 2026-07-30 (CM-5), and what did not. v2 shipped with the cut slot
    frozen at its two v1 write sites (extrude-cut + Hole) because widening it was a
    behaviour change with no golden; the documented cost was that a ``body``-scope
    mirror after a revolve/sweep/loft cut still FILLED that void — FINDINGS #2 for
    three verbs, measured as the literal featureless brick. That is now fixed by
    ADDING those three verbs to the slot in the shared ``_cut_active`` funnel. The
    invariant this test protects is unchanged and still exactly right: the ADDITIVE
    v2 records must never reach the cut slot. What is no longer true is only the
    claim that the cut slot has exactly TWO write sites — it has five (three of them
    through one funnel), and the "v1 readers return an identical tool list on every
    pre-existing chain" guarantee moved from structural to MEASURED: 242 reader
    calls across the mirror/pattern/goldens/multibody/provenance suites, all 42
    goldens and the ten locked chains, byte-identical before and after
    (docs/GEOMETRY-QA.md 2026-07-30).
    """
    body_id = _fid(2)
    state = EvaluationState(
        linear_deflection=0.1, mirror_scope_ids=frozenset({_fid(9)})
    )
    state.start_body(body_id, build_box(10.0, 10.0, 10.0))
    tool = build_box(2.0, 2.0, 2.0)

    state.record_feature_tools(_fid(9), "fuse", [tool])
    assert state.last_cut_tools is None, "an additive record leaked into the v1 slot"
    assert state.last_cut_feature_id is None
    assert state.last_cut_body_id is None
    assert set(state.feature_tools) == {_fid(9)}

    state.record_feature_tools(_fid(8), "cut", [tool])
    assert set(state.feature_tools) == {_fid(9)}, "an uncaptured feature was recorded"
    assert state.last_cut_tools is None, "the v2 store wrote the v1 slot"

    # The v1 write path still writes ONLY the v1 slot.
    state.record_cut_tools(_fid(7), [tool])
    assert state.last_cut_tools == [tool]
    assert state.last_cut_feature_id == _fid(7)
    assert state.last_cut_body_id == body_id
    assert set(state.feature_tools) == {_fid(9)}


def test_a_tree_without_a_features_scope_mirror_records_nothing() -> None:
    """The opt-in gate of §9, asserted end to end: no ``features``-scope mirror in
    the tree means an EMPTY capture set, so no intermediate tool solid is retained
    and an existing document's rebuild cost cannot regress."""
    from geometry.features.evaluate import _mirror_scope_ids

    request = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(PART_ID),
            "tree_version": 1,
            "features": [*CHAIN_A, mirror(F_MIRROR, MIDPLANE_REF)],
            "linear_deflection": 0.1,
        }
    )
    assert _mirror_scope_ids(request) == frozenset()

    with_scope = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(PART_ID),
            "tree_version": 1,
            "features": [*CHAIN_A, mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE, F_BOSS])],
            "linear_deflection": 0.1,
        }
    )
    assert _mirror_scope_ids(with_scope) == frozenset({F_HOLE, F_BOSS})


def test_the_earlier_cut_lock_holds_under_both_spellings() -> None:
    """The CM-1/§6.2 non-regression, restated where a reader will look for it: the
    locked 29600.0 (pocket A intact, 21 faces) survives the widening in the
    ``body`` spelling AND is reproduced by ``features: [pocket B]``. A welded-shut
    pocket A reads 30400.0 / 16 faces, so both halves discriminate."""
    for label, selection in (("body", None), ("features [B]", [F_PB])):
        evaluation = evaluate([*CHAIN_B, mirror(F_MIRROR, MIDPLANE_REF, selection)])
        props = evaluation.result.properties
        assert props is not None, label
        assert props.volume == pytest.approx(29600.0, abs=PLANAR_TOL), label
        assert props.topology.faces == 21, label
        assert props.topology.shells == 1, label


# =================================================================================
# SECTION 5 — per-kind coverage: the verbs §4.7 claims
# =================================================================================


def test_a_revolve_cut_is_reflectable() -> None:
    """§6.2's coverage gap, closed: ``revolve``/``sweep``/``loft`` cuts recorded
    NOTHING before, so a kind §4.7 claims would have surfaced
    ``mirror_feature_not_evaluated`` — an error where the user is entitled to
    geometry. All three share the ``_cut_active`` funnel, so recording lands for
    all three at once; revolve is the representative here.

    A r3 groove revolved into the plate's y=0 edge at x=10 (a half-cylinder notch,
    z in [15,20]) reflects about x=20 to x=30: two half-cylinders =
    2 * (pi*3^2*5)/2 = 45pi removed.
    """
    s_rev, f_rev = _fid(93), _fid(94)
    profile = [(7.0, 15.0), (10.0, 15.0), (10.0, 21.0), (7.0, 21.0)]
    entities = [
        _line(f"e{i + 1}", profile[i], profile[(i + 1) % 4])
        for i in range(len(profile))
    ]
    entities.append({**_line("ax", (10.0, 15.0), (10.0, 21.0)), "construction": True})
    volume = volume_of(
        [
            *PLATE,
            {
                "id": str(s_rev),
                "feature": {
                    "type": "sketch",
                    "version": 1,
                    "params": {
                        "plane": {"kind": "datum_plane", "plane": "XZ"},
                        "entities": entities,
                        "constraints": [],
                    },
                },
            },
            {
                "id": str(f_rev),
                "feature": {
                    "type": "revolve",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": str(s_rev)},
                        "axis": {"kind": "sketch_line", "entity": "ax"},
                        "angle_deg": 360.0,
                        "operation": "cut",
                    },
                },
            },
            MIDPLANE,
            mirror(F_MIRROR, MIDPLANE_REF, [f_rev]),
        ],
        "revolve-cut selection",
    )
    assert volume == pytest.approx(
        PLATE_VOLUME - math.pi * 3.0**2 * 5.0, abs=CURVED_TOL
    )


def test_a_linear_cut_pattern_reflects_all_its_placements() -> None:
    """§4.5 — a pattern's contribution is its N-1 PLACED instances, so reflecting
    ``[hole, pattern]`` gives 4 bores, not 2.

    Chain: plate -> hole Ø8 @(8,8) -> linear pattern +Y/12/2 (bores at y=8 and
    y=20) -> mirror about x=20 naming both. Reflected: x=32 at both y. 4 * 320pi.
    """
    volume = volume_of(
        [
            *PLATE,
            hole(F_HOLE, TOP, (8.0, 8.0, 20.0), 8.0),
            linear_pattern(F_PATTERN, (0.0, 1.0, 0.0), 12.0, 2),
            MIDPLANE,
            mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE, F_PATTERN]),
        ],
        "linear cut pattern selection",
    )
    assert volume == pytest.approx(PLATE_VOLUME - 4 * BORE_DV, abs=CURVED_TOL)


def test_a_partial_circular_pattern_reflects_its_placements_not_its_parameters() -> (
    None
):
    """§4.5, the CHIRALITY case — the reason the mechanism reflects finished solids
    and never re-derives parameters.

    A reflection REVERSES handedness, so a mirror that re-derived a circular pattern
    from its axis and positive ``angle_deg`` would wind the ring the WRONG WAY. On a
    full symmetric ring that mistake is invisible; on a PARTIAL arc it is not. Here
    a 60x60x20 plate carries a Ø8 bore at (10,30) and a 90-degree / 3-instance ring
    about (30,30) — placements at 30 and 60 degrees, so the three bores sit at
    (10,30), (12.68,20), (20,12.68) — mirrored about x=30.

    The oracle is built independently in pure Python (reflect each placement),
    including the value the WRONG implementation would give: reflected placements
    put centroid.y at 30.8327, re-derived ones at exactly 30.0 — a 0.83 mm gap,
    ~8e7 x the tolerance. Radius 20 with 30-degree steps gives a 10.35 mm chord, so
    all six bores are disjoint (r4 each) and the volume is exactly 6 bores.
    """
    s_plate, f_plate = _fid(101), _fid(102)
    f_hole, f_pattern, d_mid, f_mirror = _fid(103), _fid(104), _fid(105), _fid(106)
    centre = (30.0, 30.0)

    def rotate(point: tuple[float, float], degrees: float) -> tuple[float, float]:
        angle = math.radians(degrees)
        dx, dy = point[0] - centre[0], point[1] - centre[1]
        return (
            centre[0] + dx * math.cos(angle) - dy * math.sin(angle),
            centre[1] + dx * math.sin(angle) + dy * math.cos(angle),
        )

    seed = (10.0, 30.0)
    placed = [seed, rotate(seed, 30.0), rotate(seed, 60.0)]
    bores = [*placed, *((60.0 - p[0], p[1]) for p in placed)]
    assert (
        min(math.dist(a, b) for i, a in enumerate(bores) for b in bores[i + 1 :]) > 8.0
    ), "the oracle's bores must be disjoint for the volume to be exactly 6 bores"

    plate_volume = 60.0 * 60.0 * 20.0
    expected_volume = plate_volume - 6 * BORE_DV
    expected_y = (
        plate_volume * 30.0 - BORE_DV * sum(p[1] for p in bores)
    ) / expected_volume
    wrong = [*placed, *(rotate((50.0, 30.0), d) for d in (0.0, 30.0, 60.0))]
    wrong_y = (
        plate_volume * 30.0 - BORE_DV * sum(p[1] for p in wrong)
    ) / expected_volume

    evaluation = evaluate(
        [
            rect_sketch(s_plate, 0.0, 0.0, 60.0, 60.0),
            extrude(f_plate, s_plate, 20.0),
            hole(
                f_hole,
                top_face(f_plate, (30.0, 30.0, 20.0), 3600.0),
                (10.0, 30.0, 20.0),
                8.0,
            ),
            circular_pattern(f_pattern, (30.0, 30.0, 0.0), (0.0, 0.0, 1.0), 90.0, 3),
            datum_offset(d_mid, "YZ", 30.0),
            mirror(
                f_mirror,
                {"kind": "feature", "feature_id": str(d_mid)},
                [f_hole, f_pattern],
            ),
        ]
    )
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(expected_volume, abs=CURVED_TOL)
    assert props.centroid.y == pytest.approx(expected_y, abs=CURVED_TOL)
    assert props.centroid.y == pytest.approx(30.832691948315738, abs=CURVED_TOL)
    assert wrong_y == pytest.approx(30.0, abs=CURVED_TOL), (
        "the oracle's WRONG value must differ, or this test has no teeth"
    )


def test_recorded_pattern_contribution_reproduces_the_pattern() -> None:
    """DRIFT LOCK on ``_pattern_contribution`` (§4.5).

    The recorded contribution is derived by mirroring ``_apply_pattern``'s branch
    structure — including its vacuous-cut fallback to whole-body copies — so the two
    could drift apart silently and a mirror would then reflect something the pattern
    never applied. This asserts the invariant that makes the recording sound:
    applying the recorded group to the PRE-pattern body reproduces the pattern's own
    result, for the add path, the cut path, and the cut path's fallback.
    """
    body = build_box(40.0, 40.0, 10.0)
    tool = _at(build_box(4.0, 4.0, 10.0), (4.0, 4.0, 0.0))
    pocketed = body.cut(tool)
    assert isinstance(pocketed, Solid)
    cases = [
        (
            "linear add",
            LinearPatternParamsV1(
                kind="linear",
                direction={"x": 1.0, "y": 0.0, "z": 0.0},  # pyright: ignore[reportArgumentType]
                spacing_mm=40.0,
                count=2,
            ),
            None,
        ),
        (
            "linear cut",
            LinearPatternParamsV1(
                kind="linear",
                direction={"x": 1.0, "y": 0.0, "z": 0.0},  # pyright: ignore[reportArgumentType]
                spacing_mm=10.0,
                count=3,
            ),
            [tool],
        ),
        (
            "linear cut, vacuous -> whole-body fallback",
            LinearPatternParamsV1(
                kind="linear",
                direction={"x": 1.0, "y": 0.0, "z": 0.0},  # pyright: ignore[reportArgumentType]
                spacing_mm=40.0,
                count=2,
            ),
            [tool],
        ),
        (
            "circular cut",
            CircularPatternParamsV1(
                kind="circular",
                axis_point={"x": 20.0, "y": 20.0, "z": 0.0},  # pyright: ignore[reportArgumentType]
                axis_direction={"x": 0.0, "y": 0.0, "z": 1.0},  # pyright: ignore[reportArgumentType]
                angle_deg=360.0,
                count=3,
            ),
            [tool],
        ),
    ]
    for label, geometry, tools in cases:
        source = pocketed if tools is not None else body
        applied = _apply_pattern(source, geometry, tools)
        group = _pattern_contribution(source, geometry, tools)
        if group.op == "cut":
            rebuilt = source.cut(*group.tools).clean()
        else:
            rebuilt = source.fuse(*group.tools).clean()
        assert measure_shape(applied).volume == pytest.approx(
            measure_shape(rebuilt).volume, abs=PLANAR_TOL
        ), f"{label}: the recorded contribution does not reproduce the pattern"


def test_nested_mirrors_populate_all_four_quadrants() -> None:
    """§4.6 — the 4-fold quadrant workflow, the daily reason nesting matters.

    plate -> hole Ø8 @(10,10) -> mirror1 about x=20 ``features: [hole]`` (bores at
    x=10,30) -> mirror2 about y=20 ``features: [hole, mirror1]``. mirror2 reflects
    the hole's own tool (-> (10,30)) AND the tools mirror1 APPLIED — i.e. as PLACED
    at (30,10), giving (30,30). Four bores, 32000 - 4*320pi = 27978.7614, centroid
    exactly at the plate centre.

    Reflecting mirror1's SOURCES instead of its placements would re-cut (10,30) and
    leave the fourth quadrant empty (3 bores, 28984.07) — which is why
    ``reflect_tools`` is split out and the applied groups are recorded.
    """
    evaluation = evaluate(
        [
            *PLATE,
            hole(F_HOLE, TOP, (10.0, 10.0, 20.0), 8.0),
            MIDPLANE,
            mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE]),
            datum_offset(D_XZ_MID, "XZ", -20.0),
            mirror(
                F_MIRROR2,
                {"kind": "feature", "feature_id": str(D_XZ_MID)},
                [F_HOLE, F_MIRROR],
            ),
        ]
    )
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(PLATE_VOLUME - 4 * BORE_DV, abs=CURVED_TOL)
    assert props.volume == pytest.approx(27978.761403405064, abs=CURVED_TOL)
    assert props.centroid.x == pytest.approx(20.0, abs=CURVED_TOL)
    assert props.centroid.y == pytest.approx(20.0, abs=CURVED_TOL)
    assert props.topology.model_dump() == {"faces": 10, "edges": 24, "shells": 1}


# =================================================================================
# SECTION 6 — the typed refusals (§4.3/§4.4/§4.6, §8.2)
# =================================================================================


def test_a_modifier_selection_is_refused_not_approximated() -> None:
    """§4.3 — a fillet has a RESULT, not a tool, so it is REFUSED with a typed code.

    The tempting approximation is a delta solid (``body_before.cut(body_after)`` —
    the slivers the fillet removed), reflected and re-cut. It is only the right
    removal where the reflected side's material is CONGRUENT to the original's;
    elsewhere it cuts a groove that is a fillet of nothing — a valid, closed,
    plausible, WRONG body. That is the silent-retarget failure class reappearing in
    the boolean layer, and strictly worse than an error, because a user's own part
    has no golden. The error is pinned to the FILLET, so the UI can name the cause.
    """
    code, upstream = error_of(
        [
            *PLATE,
            hole(F_HOLE, TOP, (10.0, 20.0, 20.0), 8.0),
            fillet(F_FILLET, 3.0),
            MIDPLANE,
            mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE, F_FILLET]),
        ],
        "fillet selection",
    )
    assert code == "mirror_feature_unsupported"
    assert upstream == F_FILLET


def test_a_non_body_affecting_selection_is_refused() -> None:
    """§4.4 — a ``sketch``/``datum`` is not selectable. Documents rejects it at
    write time through the body-affecting allowed-target rule (§3.1); this is the
    geometry backstop, because geometry must not trust its callers."""
    code, upstream = error_of(
        [*PLATE, MIDPLANE, mirror(F_MIRROR, MIDPLANE_REF, [S_BASE])],
        "sketch selection",
    )
    assert code == "mirror_feature_unsupported"
    assert upstream == S_BASE


def test_a_body_scope_inner_mirror_cannot_be_nested() -> None:
    """§4.6 — an inner ``body``-scope mirror has NO tool list (its contribution is
    a whole-body reflection whose delta is not a tool), so naming it is refused.
    Honest and narrow: the user converts the inner mirror to a ``features`` scope
    and the nesting works (``test_nested_mirrors_populate_all_four_quadrants``)."""
    code, upstream = error_of(
        [
            *PLATE,
            hole(F_HOLE, TOP, (10.0, 20.0, 20.0), 8.0),
            MIDPLANE,
            mirror(F_MIRROR, MIDPLANE_REF),
            datum_offset(D_XZ_MID, "XZ", -20.0),
            mirror(
                F_MIRROR2, {"kind": "feature", "feature_id": str(D_XZ_MID)}, [F_MIRROR]
            ),
        ],
        "body-scope inner mirror",
    )
    assert code == "mirror_feature_unsupported"
    assert upstream == F_MIRROR


@pytest.mark.parametrize(
    ("label", "selection"),
    [("missing", [_fid(999)]), ("self", [F_MIRROR])],
)
def test_an_unresolvable_selection_is_reference_unresolved(
    label: str, selection: list[uuid.UUID]
) -> None:
    """A selected id that is not a feature of this evaluated prefix — missing,
    later, rolled back, or the mirror itself — is ``reference_unresolved`` pinned to
    the named id (§8.2). Documents 422s a forward/self reference at write time; this
    is the eval-time backstop."""
    code, upstream = error_of(
        [*PLATE, MIDPLANE, mirror(F_MIRROR, MIDPLANE_REF, selection)],
        f"{label} selection",
    )
    assert code == "reference_unresolved"
    assert upstream == selection[0]


def test_a_forward_selection_errors_and_skips_the_rest() -> None:
    """The strict-prefix contract over the new path (§4.3): a mirror naming a LATER
    feature errors, the following features are ``skipped``, and the last-good body
    (the plate) is still tessellated."""
    evaluation = evaluate(
        [
            *PLATE,
            MIDPLANE,
            mirror(F_MIRROR, MIDPLANE_REF, [F_HOLE]),
            hole(F_HOLE, TOP, (10.0, 20.0, 20.0), 8.0),
        ]
    )
    assert [r.status for r in evaluation.result.features] == [
        "ok",
        "ok",
        "ok",
        "error",
        "skipped",
    ]
    assert evaluation.result.last_good_feature_id == D_MID
    assert evaluation.result.properties is not None
    assert evaluation.result.properties.volume == pytest.approx(
        PLATE_VOLUME, abs=PLANAR_TOL
    )
    assert evaluation.result.mesh_glb_id is not None


def test_a_reflected_cut_that_removes_nothing_is_an_honest_error() -> None:
    """§4.2 — with an explicit selection there is nothing to guess, so the
    reachability fallback becomes an ERROR.

    v1 falls back to ``mirror_union`` when the reflected tools cannot reach the
    body, because it had to guess which of two workflows the user meant. Naming a
    pocket and a plane whose reflection lands off the body means the user picked the
    wrong feature or the wrong plane: ``mirror_feature_unreachable``, pinned to the
    pocket. Explicit intent buys an honest error where implicit intent could only
    buy a fallback — and the SAME tree in the ``body`` spelling still completes the
    half at 60000.0 (``test_complete_the_half_agrees_by_value_but_not_by_bytes``).
    """
    code, upstream = error_of(
        [
            *PLATE,
            rect_sketch(S_PA, 10.0, 10.0, 20.0, 30.0),
            extrude(F_PA, S_PA, 10.0, "cut"),
            datum_offset(D_CLEAR, "YZ", 40.0),
            mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_CLEAR)}, [F_PA]),
        ],
        "unreachable reflected cut",
    )
    assert code == "mirror_feature_unreachable"
    assert upstream == F_PA


def test_a_selection_that_contributes_nothing_is_not_a_silent_no_op() -> None:
    """§8.2 — a ``count == 1`` pattern places no instances, so a mirror naming only
    it would do nothing. That degrades to ``mirror_feature_not_evaluated``, never a
    successful no-op (the same no-silent-no-op rule as ``min_length=1``)."""
    code, _upstream = error_of(
        [
            *PLATE,
            circular_pattern(F_PATTERN, (20.0, 20.0, 0.0), (0.0, 0.0, 1.0), 90.0, 1),
            MIDPLANE,
            mirror(F_MIRROR, MIDPLANE_REF, [F_PATTERN]),
        ],
        "count-1 pattern selection",
    )
    assert code == "mirror_feature_not_evaluated"


def test_material_never_crosses_between_bodies() -> None:
    """§4.4 / §MB-0 — a selection whose tools were recorded against a DIFFERENT body
    than the active one is ``mirror_feature_other_body``, generalising v1's
    ``last_cut_body_id`` guard. Chain: pocket body A, start body B with
    ``merge=False``, then mirror B about its own -X face while naming A's pocket."""
    s_second, f_second, d_clear = _fid(71), _fid(72), _fid(73)
    code, upstream = error_of(
        [
            *PLATE,
            rect_sketch(S_PA, 10.0, 10.0, 20.0, 30.0),
            extrude(F_PA, S_PA, 10.0, "cut"),
            rect_sketch(s_second, 60.0, 0.0, 80.0, 20.0),
            extrude(f_second, s_second, 10.0, merge=False),
            datum_offset(d_clear, "YZ", 60.0),
            mirror(F_MIRROR, {"kind": "feature", "feature_id": str(d_clear)}, [F_PA]),
        ],
        "cross-body selection",
    )
    assert code == "mirror_feature_other_body"
    assert upstream == F_PA


def test_a_suppressed_selection_is_references_suppressed() -> None:
    """DOCUMENTED DIVERGENCE from mirror-semantics §8.2, locked here so it is
    visible rather than accidental.

    The design argues a SUPPRESSED selected feature should be "skipped silently"
    because the matrix locks suppress == delete. The shipped behaviour is the
    GENERIC rule instead: ``_suppressed_reference_error`` walks EVERY ref kind
    (``iter_feature_refs``) and answers ``references_suppressed`` pinned to the
    suppressed feature. That is kept deliberately, for three reasons: (a) the
    delete analogy does not hold — deleting a feature a mirror names is a write-time
    409-with-dependents (§3.1), so "suppress == delete" cannot mean "silently
    reflect less"; (b) silently reflecting a SMALLER set is exactly the
    plausible-but-wrong-body class this design exists to close, and the user's
    intent (2 of 3 features) would go unstated — §8.2 itself flags the UI warning as
    an open question; (c) carving a per-field exception out of the generic ref walk
    would break the DRY property that a new ref-bearing field is covered without
    touching that check. The error is typed, pinned, and recoverable in one click.
    """
    features = [*CHAIN_B, mirror(F_MIRROR, MIDPLANE_REF, [F_PB])]
    suppressed = copy.deepcopy(features)
    for entry in suppressed:
        if entry["id"] == str(F_PB):
            entry["feature"]["suppressed"] = True
    evaluation = evaluate(suppressed)
    codes = [
        (r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
    ]
    assert codes[-1] == ("error", "references_suppressed")
    assert ("suppressed", None) in codes


# =================================================================================
# SECTION 7 — the kernel seam directly
# =================================================================================


def test_reflect_then_cut_and_reflect_then_fuse_at_the_kernel_level() -> None:
    """The kernel entry points, exercised without the feature layer.

    ``reflect_tools`` is the ONE reflection site both scopes use (which is what
    keeps the ``body`` path byte-identical); ``cut_reflected_tools`` raises
    :class:`MirrorUnreachableError` where v1's ``mirror_cut`` would fall back to a
    union; ``fuse_reflected_tools`` imposes NO lump-count invariant, because a
    reflected additive tool landing clear of the body is a legitimate new lump
    (§4.1).
    """
    plate = build_box(40.0, 40.0, 10.0)
    tool = _at(build_box(4.0, 20.0, 10.0), (4.0, 10.0, 0.0))
    plane = Plane.YZ.offset(20.0)

    reflected = reflect_tools([tool], plane)
    assert len(reflected) == 1
    cut = cut_reflected_tools(plate, reflected)
    assert measure_shape(cut).volume == pytest.approx(16000.0 - 800.0, abs=PLANAR_TOL)

    # A tool whose reflection lands off the body: an honest error, not a union.
    far = _at(build_box(4.0, 4.0, 10.0), (100.0, 100.0, 0.0))
    with pytest.raises(MirrorUnreachableError):
        cut_reflected_tools(plate, reflect_tools([far], plane))

    # A reflected ADD that clears the body legitimately makes a second lump.
    boss = _at(build_box(4.0, 4.0, 5.0), (50.0, 10.0, 0.0))
    fused = fuse_reflected_tools(plate, reflect_tools([boss], Plane.YZ))
    assert len(fused.solids()) == 2
    assert measure_shape(fused).volume == pytest.approx(16000.0 + 80.0, abs=PLANAR_TOL)


def test_a_recorded_group_is_a_frozen_value() -> None:
    """The store holds VALUES (frozen dataclasses), so a handler cannot mutate a
    recorded contribution after the fact — the FINDINGS #1/#3 discipline ("capture
    at eval time, never re-derive later") expressed in the type."""
    group = RecordedToolGroup("cut", [build_box(1.0, 1.0, 1.0)])
    with pytest.raises(Exception):  # noqa: B017 — dataclasses raise FrozenInstanceError
        group.op = "fuse"  # pyright: ignore[reportAttributeAccessIssue]
