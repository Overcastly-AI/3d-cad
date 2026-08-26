"""Pattern v2 — the ``features`` SCOPE (docs/design/pattern-scope.md).

WHY THIS FILE EXISTS. v1's pattern had ONE field (``pattern``) and INFERRED its
SEED from the body chain, in two places — ``_pattern_cut_tools`` (repeat the
previous feature's removal tool only if that cut is the IMMEDIATE predecessor) and
the kernel's VACUOUS-CUT FALLBACK (repeat the whole body when no placed tool copy
can reach it). Each rule is individually defensible and was individually reviewed.
Together they mean **the same dialog with the same numbers in it produces two
different KINDS of result, and reports `ok` either way** — which three product
audits reported and no downstream check could catch, because the wrong body is a
closed, valid, `BRepCheck`-clean solid whose mesh, STEP round-trip and mass
properties are all exact properties of the wrong body.

The numbers this module pins, all measured (2026-08-26, build123d 0.11.1 / OCCT
7.9) and all reproducible from a clean tree:

* **FLIP A** — plate + Ø8 hole + pattern(+X, 12, 3) is `28984.071052553798`
  (three holes, the bolt row asked for). Insert an unrelated corner FILLET between
  the hole and the pattern, change nothing else, and the identical pattern params
  give `50040.17702849742`: the whole plate replicated three times, bbox X 40 ->
  64, every feature `ok`.
* **FLIP B** — plate + Ø8 hole at x=34 + pattern(+X, count 2): `spacing_mm` 8
  gives `30798.15119907386` (two holes, bbox X 0..40) and `spacing_mm` 12 gives
  `40594.69035085126` (two PLATES, bbox X 0..52). One number in one field changes
  what the feature MEANS. Every feature `ok`.
* **THE FIX** — with `scope: {kind: features, features: [hole]}` the intervening
  fillet is irrelevant (`28829.55773019996` = the filleted plate minus the same
  three bores, bbox X unchanged), and the unreachable repeat is an honest
  `pattern_feature_unreachable` pinned to the hole instead of a doubled body.

The two characterisation tests at the top deliberately assert the WRONG numbers,
because the `body` scope keeps the v1 reading verbatim (design §2.1/§9) and that
is what makes every persisted document and all four shipped pattern goldens
byte-identical. They exist so a future "improvement" to the inference cannot
quietly move a persisted document's geometry — and so the next reader finds the
defect documented rather than rediscovering it.

**Every assertion here is on the resulting GEOMETRY** — volume, bounding box,
topology counts, and material probed at the instance positions — never on a
feature's own status. `Up to date` on a wrong body is the failure shape this whole
file exists to make impossible; a gate that asked the feature how it did would
have passed throughout.

Golden: ``pattern-features-pocket-3x-boss-40x40x20``.

Tolerances are the two documented golden tiers, reused verbatim — never ad-hoc.
"""

# reportPrivateUsage: the capture-set and store tests deliberately assert on the
# evaluator's INTERNAL seams (`_tool_scope_ids`, `EvaluationState`'s slots) — that
# wiring is the risk this suite exists to pin and it is invisible from the public
# boundary. reportUnknownMemberType: build123d's boolean ops carry Shape[Unknown]
# type params upstream, the same gap tessellate.py documents for export_gltf.
# pyright: reportPrivateUsage=false, reportUnknownMemberType=false

import math
import uuid
from typing import Any

import pytest
from build123d import Vector
from geometry.features import evaluate_tree
from geometry.kernel import build_box, measure_shape
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    PatternBodyScope,
    PatternFeature,
    PatternFeaturesScope,
    PatternParamsV1,
)
from pydantic import ValidationError

#: The two REVIEWED golden tolerance tiers (docs/GEOMETRY-QA.md), reused verbatim:
#: planar-only compositions, and anything carrying a cylindrical face. Never an
#: ad-hoc epsilon (CLAUDE.md conventions).
PLANAR_TOL = 1e-9
CURVED_TOL = 1e-8

PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000c0de")
XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}


# --- Tree-authoring DSL (this module owns its own; --import-mode=importlib) -------


def _fid(n: int) -> uuid.UUID:
    """A stable, readable feature id (deterministic — no uuid4 anywhere)."""
    return uuid.UUID(f"00000000-0000-0000-0000-{n:012d}")


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
                    {
                        "id": f"e{i + 1}",
                        "kind": "line",
                        "start": {"x": corners[i][0], "y": corners[i][1]},
                        "end": {
                            "x": corners[(i + 1) % 4][0],
                            "y": corners[(i + 1) % 4][1],
                        },
                    }
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


def datum_offset(feature_id: uuid.UUID, base: str, offset_mm: float) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": base, "offset_mm": offset_mm, "flip": False},
        },
    }


def _scope(selection: list[uuid.UUID] | None, explicit_body: bool) -> dict[str, Any]:
    """The ``scope`` key of a pattern's params, or NOTHING at all.

    Returns the enclosing ``{"scope": ...}`` mapping rather than the scope object,
    so a caller can splat it into ``params`` and the pre-v2 case (no ``scope`` key
    whatsoever — what every persisted row carries) is the empty dict.
    """
    if selection is not None:
        return {
            "scope": {
                "kind": "features",
                "features": [
                    {"kind": "feature", "feature_id": str(fid)} for fid in selection
                ],
            }
        }
    return {"scope": {"kind": "body"}} if explicit_body else {}


def linear_pattern(
    feature_id: uuid.UUID,
    direction: tuple[float, float, float],
    spacing_mm: float,
    count: int,
    selection: list[uuid.UUID] | None = None,
    *,
    explicit_body_scope: bool = False,
) -> dict[str, Any]:
    """A linear pattern. ``selection=None`` emits the params a PRE-V2 row carries
    (no ``scope`` key at all); ``explicit_body_scope`` emits the same meaning
    spelled out, which the byte-identity test compares against."""
    params: dict[str, Any] = {
        "pattern": {
            "kind": "linear",
            "direction": {"x": direction[0], "y": direction[1], "z": direction[2]},
            "spacing_mm": spacing_mm,
            "count": count,
        },
        **_scope(selection, explicit_body_scope),
    }
    return {
        "id": str(feature_id),
        "feature": {"type": "pattern", "version": 1, "params": params},
    }


def circular_pattern(
    feature_id: uuid.UUID,
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
    count: int,
    selection: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "pattern": {
            "kind": "circular",
            "axis_point": {"x": axis_point[0], "y": axis_point[1], "z": axis_point[2]},
            "axis_direction": {
                "x": axis_direction[0],
                "y": axis_direction[1],
                "z": axis_direction[2],
            },
            "angle_deg": angle_deg,
            "count": count,
        },
        **_scope(selection, False),
    }
    return {
        "id": str(feature_id),
        "feature": {"type": "pattern", "version": 1, "params": params},
    }


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


class Measured:
    """The GEOMETRY a tree produced — never a feature's own status.

    Deliberately carries no ``status`` field. Every assertion in this module goes
    through this object, so "the pattern reported ok" is not expressible here: the
    defect being gated reports ``ok`` on a wrong body, so a suite that could ask
    would eventually ask (docs/design/pattern-scope.md §1.3).
    """

    def __init__(self, features: list[dict[str, Any]], label: str) -> None:
        evaluation = evaluate(features)
        bad = [
            (str(r.feature_id), r.status, r.error.code if r.error else None)
            for r in evaluation.result.features
            if r.status != "ok"
        ]
        assert not bad, f"{label}: tree did not evaluate clean: {bad}"
        properties = evaluation.result.properties
        assert properties is not None, f"{label}: evaluated ok but produced no body"
        body = evaluation.body
        assert body is not None, f"{label}: evaluated ok but produced no kernel body"
        self.label = label
        self.volume: float = properties.volume
        self.surface_area: float = properties.surface_area
        self.faces: int = properties.topology.faces
        self.edges: int = properties.topology.edges
        self.bbox_x: tuple[float, float] = (
            properties.bounding_box.min.x,
            properties.bounding_box.max.x,
        )
        self.centroid_x: float = properties.centroid.x
        self._body: BodyShape = body
        # Hold the evaluation: it owns the kernel shapes (docs/PERF.md fix #1).
        self._evaluation = evaluation

    def material_at(
        self, center: tuple[float, float, float], size: float = 2.0
    ) -> float:
        """The volume of *size*-cube of material centred on *center*.

        The POSITIONAL assertion. Volume alone says how much material a tree has;
        this says WHERE, which is what distinguishes "three holes in one plate"
        from "three plates" when the totals happen to be close, and what catches a
        pattern that placed its instances correctly in count and wrongly in space.
        Exact: an axis-aligned box intersected with an axis-aligned solid.
        """
        probe = build_box(size, size, size).translate(
            Vector(center[0] - size / 2, center[1] - size / 2, center[2] - size / 2)
        )
        # `intersect` carries ShapeList[Unknown] type params upstream (the same gap
        # tessellate.py documents for export_gltf) and returns None for an EMPTY
        # intersection — which is precisely the "there is a void here" answer this
        # probe is usually asked for.
        common: Any = self._body.intersect(probe)  # pyright: ignore[reportUnknownVariableType]
        if common is None:
            return 0.0
        solids: list[Any] = list(common.solids())
        if not solids:
            return 0.0
        return sum(measure_shape(solid).volume for solid in solids)


def error_of(
    features: list[dict[str, Any]], label: str
) -> tuple[str, uuid.UUID | None]:
    """The ONE per-feature error of a tree that must degrade honestly, plus its
    ``upstream_feature_id`` (the offending SELECTED feature — what lets the UI
    name the true cause instead of blaming the pattern)."""
    evaluation = evaluate(features)
    errors = [r.error for r in evaluation.result.features if r.error is not None]
    assert len(errors) == 1, f"{label}: expected exactly one error, got {errors}"
    return errors[0].code, errors[0].upstream_feature_id


# --- Fixtures: the defect's own trees ---------------------------------------------

S_BASE, F_BASE = _fid(1), _fid(2)
F_HOLE, F_PATTERN, F_FILLET = _fid(31), _fid(41), _fid(61)
D_BOSS, S_BOSS, F_BOSS = _fid(71), _fid(72), _fid(73)
F_PATTERN2 = _fid(42)

#: The 40x40x20 plate every chain below starts from (V = 32000 mm^3).
PLATE: list[dict[str, Any]] = [
    rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0),
    extrude(F_BASE, S_BASE, 20.0),
]
PLATE_VOLUME = 32000.0
#: The plate's pristine +Z face (area 1600, centroid (20,20,20)).
TOP = top_face(F_BASE, (20.0, 20.0, 20.0), 1600.0)
#: Ø8 through-bore removal from a 20 mm plate.
BORE_DV = math.pi * 4.0**2 * 20.0

#: The bolt row: a Ø8 hole at (8,20) and a 3-up +X pattern at 12 mm pitch, so the
#: bores land at x = 8, 20, 32 — all interior, none touching another.
HOLE_AT_8 = hole(F_HOLE, TOP, (8.0, 20.0, 20.0), 8.0)
ROW = ((1.0, 0.0, 0.0), 12.0, 3)
#: Flip B's fixture: the same hole slid to x=34 so its tool spans x in [30,38] and
#: a copy at +12 clears the +X face entirely.
HOLE_AT_34 = hole(F_HOLE, TOP, (34.0, 20.0, 20.0), 8.0)

#: An 8x8x5 boss on the plate's top face — a body-affecting NON-cut, i.e. the
#: shadowing feature of the golden. Kept all-planar so its volume is exact.
BOSS: list[dict[str, Any]] = [
    datum_offset(D_BOSS, "XY", 20.0),
    rect_sketch(
        S_BOSS, 30.0, 30.0, 38.0, 38.0, {"kind": "feature", "feature_id": str(D_BOSS)}
    ),
    extrude(F_BOSS, S_BOSS, 5.0),
]


# --- The defect, characterised (the `body` scope keeps the v1 reading) ------------


def test_flip_a_an_unrelated_fillet_changes_what_a_body_scope_pattern_repeats() -> None:
    """FLIP A (design §1.1) — identical pattern params, two different KINDS of body.

    The `body` scope's seed inference reads the IMMEDIATELY-preceding
    body-affecting feature, so a fillet the user added for an unrelated reason
    shadows the recorded cut and the request silently changes from "three holes"
    to "three plates". Asserted here as a CHARACTERISATION, not an endorsement:
    the v1 reading is kept verbatim so persisted documents and the four shipped
    pattern goldens are byte-identical (design §2.1), and this test is what stops
    a future tweak to the inference from moving their geometry unnoticed.
    """
    row = Measured([*PLATE, HOLE_AT_8, linear_pattern(F_PATTERN, *ROW)], "no fillet")
    assert row.volume == pytest.approx(PLATE_VOLUME - 3 * BORE_DV, abs=CURVED_TOL)
    assert row.bbox_x == (0.0, 40.0)

    shadowed = Measured(
        [*PLATE, HOLE_AT_8, fillet(F_FILLET, 3.0), linear_pattern(F_PATTERN, *ROW)],
        "fillet between",
    )
    # The whole plate, three times: 24 mm longer than the part the user drew.
    assert shadowed.volume == pytest.approx(50040.17702849742, abs=CURVED_TOL)
    assert shadowed.bbox_x[1] == pytest.approx(64.0, abs=PLANAR_TOL)
    assert shadowed.volume > 1.7 * row.volume


def test_flip_b_spacing_alone_changes_what_a_body_scope_pattern_repeats() -> None:
    """FLIP B (design §1.2) — one number in one field, two different KINDS of body.

    At 8 mm the placed tool still overlaps the plate, so the pattern repeats the
    HOLE. At 12 mm it clears the +X face, the VACUOUS-CUT FALLBACK fires, and the
    pattern repeats the BODY. The honest answer to "put the second hole 12 mm to
    the right" on a part that ends 6 mm to the right is an error; §4's
    ``pattern_feature_unreachable`` is that answer, and it is reachable only from
    an explicit scope, because the `body` scope is genuinely guessing.
    """
    near = Measured(
        [*PLATE, HOLE_AT_34, linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 8.0, 2)],
        "spacing 8",
    )
    far = Measured(
        [*PLATE, HOLE_AT_34, linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 12.0, 2)],
        "spacing 12",
    )
    assert near.volume == pytest.approx(30798.15119907386, abs=CURVED_TOL)
    assert near.bbox_x == (0.0, 40.0)
    assert far.volume == pytest.approx(40594.69035085126, abs=CURVED_TOL)
    assert far.bbox_x[1] == pytest.approx(52.0, abs=PLANAR_TOL)


# --- The fix: an explicit selection cannot flip ------------------------------------


def test_a_features_scope_repeats_the_same_thing_across_an_intervening_feature() -> (
    None
):
    """FLIP A, stated away — the assertion that would have caught the wrong scope.

    Same selection, same pattern params, two trees differing only by a fillet the
    pattern has nothing to do with. The pattern's CONTRIBUTION must be identical:
    two extra bores, the plate's own X extent untouched, and material absent at
    exactly the three bore centres and present between them. Comparing the two
    trees' contributions rather than their absolute volumes is deliberate — the
    fillet legitimately changes the base volume, and a test that could only read
    a total would have to choose between missing that or hard-coding it.
    """
    base_plain = Measured([*PLATE, HOLE_AT_8], "plain base")
    base_filleted = Measured(
        [*PLATE, HOLE_AT_8, fillet(F_FILLET, 3.0)], "filleted base"
    )

    plain = Measured(
        [*PLATE, HOLE_AT_8, linear_pattern(F_PATTERN, *ROW, [F_HOLE])],
        "features scope, no fillet",
    )
    filleted = Measured(
        [
            *PLATE,
            HOLE_AT_8,
            fillet(F_FILLET, 3.0),
            linear_pattern(F_PATTERN, *ROW, [F_HOLE]),
        ],
        "features scope, fillet between",
    )

    for measured, base in ((plain, base_plain), (filleted, base_filleted)):
        # Exactly two more bores removed — the instances the pattern was asked for.
        assert base.volume - measured.volume == pytest.approx(
            2 * BORE_DV, abs=CURVED_TOL
        ), measured.label
        # The plate was not replicated: its X extent is the one the user drew.
        assert measured.bbox_x == (0.0, 40.0) or measured.bbox_x[1] == pytest.approx(
            40.0, abs=PLANAR_TOL
        ), measured.label
        # WHERE the material went: a void at each bore centre, metal between them.
        for x in (8.0, 20.0, 32.0):
            assert measured.material_at((x, 20.0, 10.0)) == pytest.approx(
                0.0, abs=PLANAR_TOL
            ), f"{measured.label}: no bore at x={x}"
        for x in (14.0, 26.0):
            assert measured.material_at((x, 20.0, 10.0)) == pytest.approx(
                8.0, abs=PLANAR_TOL
            ), f"{measured.label}: material missing between bores at x={x}"

    # And the absolute number, so the fixture itself cannot drift silently.
    assert filleted.volume == pytest.approx(28829.55773019996, abs=CURVED_TOL)


def test_a_features_scope_refuses_an_unreachable_repeat_not_double_the_body() -> None:
    """FLIP B, stated away (design §4).

    The identical tree that silently returns a 52 mm-long doubled plate under the
    `body` scope is a typed `pattern_feature_unreachable`, pinned to the HOLE the
    user selected — so the UI can say which feature could not be repeated instead
    of blaming the pattern. The strict-prefix rule then tessellates the last-good
    body, which is the pre-pattern plate, not a wrong one.
    """
    code, upstream = error_of(
        [
            *PLATE,
            HOLE_AT_34,
            linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 12.0, 2, [F_HOLE]),
        ],
        "unreachable repeat",
    )
    assert code == "pattern_feature_unreachable"
    assert upstream == F_HOLE

    # The reachable spacing on the SAME tree still works, so this is a refusal of
    # an impossible request, not of the feature.
    near = Measured(
        [
            *PLATE,
            HOLE_AT_34,
            linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 8.0, 2, [F_HOLE]),
        ],
        "reachable repeat",
    )
    assert near.volume == pytest.approx(30798.15119907386, abs=CURVED_TOL)
    assert near.bbox_x == (0.0, 40.0)


def test_selecting_the_base_extrude_repeats_its_prism_not_the_body_so_far() -> None:
    """Repeating the whole part is still expressible — and it is a DIFFERENT request.

    The point of the design is not that repeating the body is wrong; it is that it
    must be requested. Naming the base extrude repeats what THAT FEATURE
    contributed — its pristine 40x40x20 prism — and fuses it, so the union spans
    x in [0,52] and the copy FILLS the later hole: exactly 52*40*20 = 41600.0.

    The `body` scope's fallback on the same tree gives 40594.69035085126 instead,
    because it replicates the body-SO-FAR, hole included. Both are legitimate
    requests, and this test pins the distinction rather than papering over it:
    "copy this feature" and "copy everything built so far" are different sentences,
    and a contract that could not tell them apart is how v1 got here. Selecting the
    body-so-far is the unbuilt `kind: "bodies"` member (design §9).
    """
    asked = Measured(
        [
            *PLATE,
            HOLE_AT_34,
            linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 12.0, 2, [F_BASE]),
        ],
        "features scope naming the base",
    )
    assert asked.volume == pytest.approx(41600.0, abs=PLANAR_TOL)
    assert asked.bbox_x[1] == pytest.approx(52.0, abs=PLANAR_TOL)
    # The bore is gone — filled by the base feature's own pristine prism.
    assert asked.material_at((34.0, 20.0, 10.0)) == pytest.approx(8.0, abs=PLANAR_TOL)

    inferred = Measured(
        [*PLATE, HOLE_AT_34, linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 12.0, 2)],
        "body scope on the same tree",
    )
    assert inferred.volume == pytest.approx(40594.69035085126, abs=CURVED_TOL)
    assert asked.volume > inferred.volume


def test_a_boss_between_the_cut_and_the_pattern_is_the_goldens_tree() -> None:
    """The golden's fixture, asserted here too (design §8).

    A pocket, then a BOSS (a body-affecting non-cut — the same shadowing v1's
    inference falls for), then `features: [pocket]`. 29920.0 mm^3 with the plate
    still 40 long; delete the scope and the identical tree is 51359.99999999999
    with bbox X 0..64 and every feature `ok`. Both bodies have 26 faces and 60
    edges, so TOPOLOGY DOES NOT DISCRIMINATE THEM — only the volume, the bbox and
    the material positions do, which is why this suite asserts all three.
    """
    S_POCKET, F_POCKET = _fid(81), _fid(82)
    tree = [
        *PLATE,
        rect_sketch(S_POCKET, 4.0, 10.0, 8.0, 30.0),
        extrude(F_POCKET, S_POCKET, 10.0, "cut"),
        *BOSS,
    ]
    scoped = Measured(
        [*tree, linear_pattern(F_PATTERN, *ROW, [F_POCKET])], "features: [pocket]"
    )
    inferred = Measured([*tree, linear_pattern(F_PATTERN, *ROW)], "body scope")

    assert scoped.volume == pytest.approx(29920.0, abs=PLANAR_TOL)
    assert scoped.bbox_x == (0.0, 40.0)
    assert inferred.volume == pytest.approx(51359.99999999999, abs=PLANAR_TOL)
    assert inferred.bbox_x[1] == pytest.approx(64.0, abs=PLANAR_TOL)
    # The trap this fixture documents: same counts, different solids.
    assert (scoped.faces, scoped.edges) == (inferred.faces, inferred.edges) == (26, 60)
    # Where the three pockets are, and are not.
    for x in (6.0, 18.0, 30.0):
        assert scoped.material_at((x, 20.0, 2.0), 1.0) == pytest.approx(
            0.0, abs=PLANAR_TOL
        )
    for x in (12.0, 24.0):
        assert scoped.material_at((x, 20.0, 2.0), 1.0) == pytest.approx(
            1.0, abs=PLANAR_TOL
        )


# --- Composition: a pattern of a pattern is a real grid ---------------------------


def test_a_pattern_of_a_pattern_places_a_grid_not_a_row_of_bodies() -> None:
    """§3.1 — the inner pattern's PLACEMENTS are what the outer one repeats.

    A bore at (8,10), three along +X at 12 mm pitch, then three copies of BOTH
    contributions along +Y at 12 mm pitch: nine bores in one plate on a 3x3 grid at
    x = 8/20/32 and y = 10/22/34, every one fully interior, with the plate's own
    extents untouched. Under the `body` scope the outer pattern would have
    replicated the whole plate (the inner pattern is not a cut, so it shadows the
    hole exactly as a boss does), so this is also the cheapest available answer to
    the 2-direction gap — though the one-command rectangular pattern is still its
    own item (design §9).
    """
    hole_low = hole(F_HOLE, TOP, (8.0, 10.0, 20.0), 8.0)
    grid = Measured(
        [
            *PLATE,
            hole_low,
            linear_pattern(F_PATTERN, *ROW, [F_HOLE]),
            linear_pattern(F_PATTERN2, (0.0, 1.0, 0.0), 12.0, 3, [F_HOLE, F_PATTERN]),
        ],
        "3x3 grid",
    )
    assert grid.volume == pytest.approx(PLATE_VOLUME - 9 * BORE_DV, abs=CURVED_TOL)
    assert grid.bbox_x == (0.0, 40.0)
    for x in (8.0, 20.0, 32.0):
        for y in (10.0, 22.0, 34.0):
            assert grid.material_at((x, y, 10.0)) == pytest.approx(
                0.0, abs=PLANAR_TOL
            ), f"no bore at ({x}, {y})"


def test_a_circular_features_scope_pattern_makes_a_bolt_circle() -> None:
    """The bolt-circle flow, asked for rather than inferred.

    A Ø8 hole 12 mm off the plate centre, then `features: [hole]` about the plate's
    Z axis, 4-up over 360 degrees: four bores at 90-degree spacing, the plate's own
    extents untouched. Rotation is a proper isometry, so unlike a reflected ring
    (mirror-semantics §4.5) there is no chirality trap here — but the placements
    are still what is recorded and repeated, so the two verbs cannot drift.
    """
    ring = Measured(
        [
            *PLATE,
            hole(F_HOLE, TOP, (32.0, 20.0, 20.0), 8.0),
            circular_pattern(
                F_PATTERN, (20.0, 20.0, 0.0), (0.0, 0.0, 1.0), 360.0, 4, [F_HOLE]
            ),
        ],
        "bolt circle",
    )
    assert ring.volume == pytest.approx(PLATE_VOLUME - 4 * BORE_DV, abs=CURVED_TOL)
    assert ring.bbox_x == (0.0, 40.0)
    for center in ((32.0, 20.0), (20.0, 32.0), (8.0, 20.0), (20.0, 8.0)):
        assert ring.material_at((center[0], center[1], 10.0)) == pytest.approx(
            0.0, abs=PLANAR_TOL
        )


# --- Determinism: TREE order, never array order -----------------------------------


def test_the_selection_array_order_does_not_change_the_bytes() -> None:
    """§6 — array order is UI-incidental (it depends on the click order), so
    honouring it would make identical models tessellate to different bytes.

    THE FIXTURE IS THE TEST. Order can only matter where a selected cut and a
    selected fuse OVERLAP, so the first version of this test — a pocket at one end
    of the plate and a boss on top of the other — passed with the ordering
    DELIBERATELY BROKEN, because disjoint booleans commute. That is a gate that
    cannot fail, which this repo has shipped four of; the mutation run caught it.

    Here the pocket removes x in [4,8] and the PLUG prism spans x in [6,14], so
    their placed copies overlap: pockets at x in [16,20] and [28,32], plugs at
    x in [18,26] and [30,38]. In tree order the cuts land first and the fuses then
    refill x in [18,20] and [30,32], leaving 30800.0 mm^3; in array order
    [plug, pocket] the fuses are no-ops on solid material and the cuts remove the
    whole bands, leaving 30000.0. 800 mm^3 apart, so the assertion has something to
    hold on to — verified by running the mutation, not by reasoning about it.
    """
    S_POCKET, F_POCKET = _fid(81), _fid(82)
    S_PLUG, F_PLUG = _fid(83), _fid(84)
    tree = [
        *PLATE,
        rect_sketch(S_POCKET, 4.0, 10.0, 8.0, 30.0),
        extrude(F_POCKET, S_POCKET, 10.0, "cut"),
        rect_sketch(S_PLUG, 6.0, 10.0, 14.0, 30.0),
        extrude(F_PLUG, S_PLUG, 10.0, "add"),
    ]
    forward = evaluate([*tree, linear_pattern(F_PATTERN, *ROW, [F_POCKET, F_PLUG])])
    reverse = evaluate([*tree, linear_pattern(F_PATTERN, *ROW, [F_PLUG, F_POCKET])])
    assert forward.glb == reverse.glb
    assert forward.result.properties == reverse.result.properties
    # The number tree order produces, so the fixture cannot go quietly inert: a
    # future change that made both orders agree on the ARRAY-order answer would
    # keep the equality above and move this.
    properties = forward.result.properties
    assert properties is not None
    assert properties.volume == pytest.approx(30800.0, abs=PLANAR_TOL)


def test_a_features_scope_pattern_rebuilds_byte_identically() -> None:
    """RESEARCH §9 — same tree in, identical bytes out, twice in one process."""
    tree = [*PLATE, HOLE_AT_8, linear_pattern(F_PATTERN, *ROW, [F_HOLE])]
    first, second = evaluate(tree), evaluate(tree)
    assert first.glb == second.glb
    assert first.result.properties == second.result.properties


# --- Migration: a pre-v2 pattern is unchanged -------------------------------------


def test_a_scope_less_pattern_is_exactly_an_explicit_body_scope() -> None:
    """§2.1 — the additive migration, asserted at BYTE strength.

    Every persisted pattern row carries no `scope` key. It must mean what it
    always meant, and it must reach that meaning through the same code, or the
    four shipped pattern goldens would need re-derivation rather than being
    structurally unchanged.
    """
    legacy = evaluate([*PLATE, HOLE_AT_8, linear_pattern(F_PATTERN, *ROW)])
    spelled = evaluate(
        [*PLATE, HOLE_AT_8, linear_pattern(F_PATTERN, *ROW, explicit_body_scope=True)]
    )
    assert legacy.glb == spelled.glb
    assert legacy.result.properties == spelled.result.properties


@pytest.mark.parametrize("blob", [{}, {"scope": None}])
def test_absent_and_null_scope_both_normalise_to_the_body_reading(
    blob: dict[str, Any],
) -> None:
    """A client that round-trips an omitted optional as an explicit null is not a
    422 — the same normalisation ``MirrorParamsV1`` performs."""
    params = PatternParamsV1.model_validate(
        {
            "pattern": {
                "kind": "linear",
                "direction": {"x": 1.0, "y": 0.0, "z": 0.0},
                "spacing_mm": 12.0,
                "count": 3,
            },
            **blob,
        }
    )
    assert isinstance(params.scope, PatternBodyScope)


# --- Typed refusals, one per refused shape ----------------------------------------


def test_a_modifier_cannot_be_patterned() -> None:
    """§3 — a fillet has a RESULT and no tool. Refusing in writing beats
    approximating it with a `before.cut(after)` delta sliver, which is a valid,
    closed, plausible, WRONG body wherever the repeated side is not congruent."""
    code, upstream = error_of(
        [
            *PLATE,
            HOLE_AT_8,
            fillet(F_FILLET, 3.0),
            linear_pattern(F_PATTERN, *ROW, [F_FILLET]),
        ],
        "fillet selected",
    )
    assert code == "pattern_feature_unsupported"
    assert upstream == F_FILLET


def test_an_id_outside_this_prefix_is_reference_unresolved() -> None:
    """The eval-time backstop; documents 422s a forward/self/missing ref at write
    time, and geometry must not trust its callers."""
    missing = _fid(999)
    code, upstream = error_of(
        [*PLATE, HOLE_AT_8, linear_pattern(F_PATTERN, *ROW, [missing])],
        "unknown id selected",
    )
    assert code == "reference_unresolved"
    assert upstream == missing


def test_a_count_one_features_scope_pattern_is_a_no_op_not_a_refusal() -> None:
    """§4 — a no-op pattern is not an empty selection, and the `body` scope has
    always treated count 1 as "leave the body alone"."""
    base = Measured([*PLATE, HOLE_AT_8], "base")
    noop = Measured(
        [
            *PLATE,
            HOLE_AT_8,
            linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 12.0, 1, [F_HOLE]),
        ],
        "count 1",
    )
    assert noop.volume == pytest.approx(base.volume, abs=CURVED_TOL)
    assert noop.faces == base.faces


def test_a_count_below_one_is_still_pattern_bad_count_in_a_features_scope() -> None:
    """The shared kernel guard runs on BOTH paths (``check_pattern_count``).
    Without it a `count = 0` selection would place nothing and read as a silent
    no-op — the exact failure shape the scope exists to remove."""
    code, _ = error_of(
        [
            *PLATE,
            HOLE_AT_8,
            linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 12.0, 0, [F_HOLE]),
        ],
        "count 0",
    )
    assert code == "pattern_bad_count"


def test_a_bad_spacing_is_still_pattern_bad_spacing_in_a_features_scope() -> None:
    """Likewise the placement helpers' own validation, reached through the same
    ``except`` ladder as the `body` scope rather than a second copy of it."""
    code, _ = error_of(
        [
            *PLATE,
            HOLE_AT_8,
            linear_pattern(F_PATTERN, (1.0, 0.0, 0.0), 0.0, 3, [F_HOLE]),
        ],
        "spacing 0",
    )
    assert code == "pattern_bad_spacing"


def test_an_empty_selection_is_a_422_not_a_no_op_pattern() -> None:
    """§2 — `min_length=1`. An empty "features to pattern" list is authoring
    nonsense; accepting it would put a silent no-op back in the contract."""
    with pytest.raises(ValidationError):
        PatternFeaturesScope.model_validate({"kind": "features", "features": []})


def test_a_duplicate_selection_is_a_422_not_a_silent_dedupe() -> None:
    """§2 — naming a feature twice leaves the intent (twice? once?) unstated,
    which is precisely the mistake v1 made."""
    ref = {"kind": "feature", "feature_id": str(F_HOLE)}
    with pytest.raises(ValidationError, match="more than once"):
        PatternFeaturesScope.model_validate(
            {"kind": "features", "features": [ref, ref]}
        )


# --- The capture set (§5) ----------------------------------------------------------


def test_the_capture_set_collects_pattern_selections_too() -> None:
    """§5 — the opt-in store is funded by BOTH `features`-scope verbs.

    A tree with no such verb must retain nothing extra (that is what keeps the
    widening free for existing documents); a tree with a `features`-scope pattern
    must retain exactly its selection, or the pattern would find no recorded tools
    and refuse a request it can serve.
    """
    from geometry.features.evaluate import _tool_scope_ids

    plain = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(PART_ID),
            "tree_version": 1,
            "features": [*PLATE, HOLE_AT_8, linear_pattern(F_PATTERN, *ROW)],
            "linear_deflection": 0.1,
        }
    )
    scoped = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(PART_ID),
            "tree_version": 1,
            "features": [
                *PLATE,
                HOLE_AT_8,
                linear_pattern(F_PATTERN, *ROW, [F_HOLE, F_BASE]),
            ],
            "linear_deflection": 0.1,
        }
    )
    assert _tool_scope_ids(plain) == frozenset()
    assert _tool_scope_ids(scoped) == frozenset({F_HOLE, F_BASE})


def test_a_features_scope_pattern_materialises_feature_dependencies() -> None:
    """feature-tree §2.3 — each selection IS a dependency, so deleting a patterned
    feature is a 409-with-dependents and a reorder re-checks strict-backward. The
    `body` scope carries no refs; tree order remains its only dependency."""
    from py_kit.schemas.features import feature_references

    scoped = PatternFeature.model_validate(
        {
            "type": "pattern",
            "version": 1,
            "params": linear_pattern(F_PATTERN, *ROW, [F_HOLE])["feature"]["params"],
        }
    )
    body = PatternFeature.model_validate(
        {
            "type": "pattern",
            "version": 1,
            "params": linear_pattern(F_PATTERN, *ROW)["feature"]["params"],
        }
    )
    assert [ref.ref.feature_id for ref in feature_references(scoped)] == [F_HOLE]
    assert feature_references(body) == ()
