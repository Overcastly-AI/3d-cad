"""GEOM-3 at the FEATURE-TREE level — the boss whose disappearance went unnoticed.

The kernel-level gates for the outer-wire re-match live in ``test_faces.py``; this
file exercises the path the product takes, because GEOM-3 is a property of an EDIT
made to a document and not of one resolver call. A reference placed on a boss top
whose face is then gone must be reported (``subshape_unresolved``, the feature and
everything downstream of it visibly red). What §12a's inferred band did instead, on
a plate 40.7 % open, was silently re-anchor onto the plate underneath and hand back
a part that is quietly wrong. A visible failure the user can act on is strictly
better than a wrong body they cannot see, which is the trade §12 refused and §12b
puts back.

**Which edit makes the boss top vanish matters, and pinning it down corrected the
ticket's framing twice.** First, "delete the boss" does NOT reach the matcher at all:
a subshape reference names the feature that created the face, so deleting that
feature leaves a dangling ``feature_id``, and SUPPRESSING it is caught just as early
by the ``references_suppressed`` guard — both come back ``error``, not
``subshape_unresolved`` (measured while writing this file, and gated at the bottom).
The product is already safe against the literal deletion. Second, an edit that leaves
ANY +Z face on the boss top's own plane is absorbed by tier 2, correctly and by
design: resize the boss 75x75 -> 40x40 and the reference resolves onto the smaller
boss top, because tier 2 frees the area and the in-plane centroid and pins only the
supporting plane (FINDINGS #3). So the hazard needs the face's whole PLANE to empty
while the feature that made it stays alive, and the ordinary edit that does that is
toggling the extrude's operation: the protrusion the sketch was placed on becomes a
window through the plate.

The control matters as much as the failure, and there are two: with the extrude still
adding, the same reference resolves clean (so the refusal is about the edit, not
about the tier being broken), and the SAME edit against a legacy three-field selector
still resolves (so the fix is the stored contract, not a tightened bound).
"""

import copy
import math
import uuid
from typing import Any

import pytest
from geometry.features import evaluate_tree
from geometry.kernel.faces import planar_faces
from py_kit.schemas.features import EvaluateTreeRequest

PART_ID = uuid.UUID("00000000-0000-0000-0000-000000003000")
PLATE_SKETCH = uuid.UUID("00000000-0000-0000-0000-000000003001")
PLATE_EXTRUDE = uuid.UUID("00000000-0000-0000-0000-000000003002")
VENT_SKETCH = uuid.UUID("00000000-0000-0000-0000-000000003003")
VENT_CUT = uuid.UUID("00000000-0000-0000-0000-000000003004")
BOSS_SKETCH = uuid.UUID("00000000-0000-0000-0000-000000003005")
BOSS_EXTRUDE = uuid.UUID("00000000-0000-0000-0000-000000003006")
DATUM_ON_BOSS = uuid.UUID("00000000-0000-0000-0000-000000003007")
PIN_SKETCH = uuid.UUID("00000000-0000-0000-0000-000000003008")
PIN_EXTRUDE = uuid.UUID("00000000-0000-0000-0000-000000003009")

PLATE_W = 100.0
PLATE_T = 10.0
VENT_N = 8
VENT_R = 4.5
BOSS_SIDE = 75.0
BOSS_H = 8.0
BOSS_TOP_Z = PLATE_T + BOSS_H

#: The plate's open-area fraction, which is what §12a's band degrades with. Named
#: here because the whole ticket turns on how ORDINARY this number is.
OPEN_FRACTION = VENT_N**2 * math.pi * VENT_R**2 / (PLATE_W * PLATE_W)


def _rect(entity_prefix: str, x0: float, y0: float, x1: float, y1: float) -> list[Any]:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [
        {
            "id": f"{entity_prefix}{i + 1}",
            "kind": "line",
            "start": {"x": corners[i][0], "y": corners[i][1]},
            "end": {"x": corners[(i + 1) % 4][0], "y": corners[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]


def _sketch(feature_id: uuid.UUID, entities: list[Any], plane: Any) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {"plane": plane, "entities": entities, "constraints": []},
        },
    }


def _extrude(
    feature_id: uuid.UUID, profile: uuid.UUID, distance: float, operation: str
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile)},
                "distance_mm": distance,
                "operation": operation,
                "direction": "normal",
            },
        },
    }


def _vent_entities() -> list[Any]:
    pitch = PLATE_W / VENT_N
    return [
        {
            "id": f"v{i * VENT_N + j + 1}",
            "kind": "circle",
            "center": {"x": pitch * (i + 0.5), "y": pitch * (j + 0.5)},
            "radius": VENT_R,
        }
        for i in range(VENT_N)
        for j in range(VENT_N)
    ]


PIN_H = 5.0
#: The pin square, in the DATUM's own 2D frame. Its origin is the anchored stored
#: centroid (50, 50) and its x_dir is world +X, so this rectangle spans world x 4-30,
#: y 47-53. It deliberately STRADDLES the block's edge at x = 12.5, so it is attached
#: to material in BOTH outcomes: standing on the boss it overlaps the boss top from
#: 12.5 to 30, and standing on the plate it overlaps the surviving frame from 4 to
#: 12.5. That is what lets the WRONG answer produce a valid part rather than an
#: error, which is the whole point of the defect — it is silent.
PIN_U0, PIN_U1 = -46.0, -20.0
PIN_V0, PIN_V1 = -3.0, 3.0


def _seat(signature: dict[str, Any]) -> list[dict[str, Any]]:
    """A datum ON the picked face, a sketch on that datum, and a 5 mm pin extruded up.

    A DATUM rather than a hole, deliberately. A hole needs material under the drill
    point, and the point that is on the boss top is inside the window once the block
    is cut — so a hole would fail for the wrong reason and prove nothing about the
    matcher. A datum needs only the PLANE, and the pin standing on it turns the
    resolved offset into a number anyone can read off the part: the top of the pin is
    at z = 23 when the reference lands on the boss top it was picked on, and at
    z = 15 when it silently lands on the plate 8 mm below."""
    return [
        {
            "id": str(DATUM_ON_BOSS),
            "feature": {
                "type": "datum",
                "version": 1,
                "params": {
                    "kind": "on_face",
                    "face": {
                        "kind": "subshape",
                        "feature_id": str(BOSS_EXTRUDE),
                        "subshape_type": "face",
                        "selector": {
                            "selector_version": 1,
                            "signature": signature,
                        },
                    },
                    "offset_mm": 0.0,
                },
            },
        },
        _sketch(
            PIN_SKETCH,
            _rect("p", PIN_U0, PIN_V0, PIN_U1, PIN_V1),
            {"kind": "feature", "feature_id": str(DATUM_ON_BOSS)},
        ),
        _extrude(PIN_EXTRUDE, PIN_SKETCH, PIN_H, "add"),
    ]


def _evaluate(features: list[dict[str, Any]], tree_version: int) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(PART_ID),
                "tree_version": tree_version,
                "features": features,
                "linear_deflection": 0.5,
            }
        )
    )


def _prefix(operation: str = "add") -> list[dict[str, Any]]:
    """Vented plate + a 75x75 block centred on it, ADDED (a boss) or CUT (a window).

    The two states this file compares are one keystroke apart in the UI, which is the
    point: same feature, same sketch, one dropdown. Added, it is a boss whose top is a
    planar +Z face at z = 18 that a hole gets placed on. Cut, that plane is empty and
    the only +Z candidate left is the vented plate top at z = 10.

    The block is drawn on XY and extruded the FULL height rather than seated on the
    plate top: a sketch's plane reference is an origin datum or an earlier feature,
    and the origin-datum variant takes no offset. The 75 mm side puts the block's
    edges at 12.5 and 87.5, in the web BETWEEN vent columns (a Ø9 vent centred at 6.25
    spans 1.75-10.75, the next at 18.75 spans 14.25-23.25), so neither state depends
    on a boundary that grazes a vent."""
    inset = (PLATE_W - BOSS_SIDE) / 2.0
    return [
        _sketch(
            PLATE_SKETCH,
            _rect("e", 0.0, 0.0, PLATE_W, PLATE_W),
            {"kind": "datum_plane", "plane": "XY"},
        ),
        _extrude(PLATE_EXTRUDE, PLATE_SKETCH, PLATE_T, "add"),
        _sketch(VENT_SKETCH, _vent_entities(), {"kind": "datum_plane", "plane": "XY"}),
        _extrude(VENT_CUT, VENT_SKETCH, PLATE_T, "cut"),
        _sketch(
            BOSS_SKETCH,
            _rect("b", inset, inset, inset + BOSS_SIDE, inset + BOSS_SIDE),
            {"kind": "datum_plane", "plane": "XY"},
        ),
        _extrude(BOSS_EXTRUDE, BOSS_SKETCH, BOSS_TOP_Z, operation),
    ]


def _boss_top_signature(features: list[dict[str, Any]]) -> dict[str, Any]:
    """The signature the overlay hands a client for the BOSS TOP of this prefix.

    Produced the way the product produces it — the pick side's own output for the
    body the preceding features build — so every expectation below is derived
    independently of it."""
    evaluation = _evaluate(features, 1)
    assert evaluation.body is not None, [
        (str(r.feature_id), r.status, r.error) for r in evaluation.result.features
    ]
    tops = [
        r
        for r in planar_faces(evaluation.body)
        if r.signature.normal.z > 0.5
        and abs(r.signature.centroid.z - BOSS_TOP_Z) <= 1e-9
    ]
    assert len(tops) == 1
    return tops[0].signature.model_dump(mode="json")


def _legacy(signature: dict[str, Any]) -> dict[str, Any]:
    """*signature* as a selector persisted BEFORE §12b — three fields, no outer wire."""
    return {
        key: signature[key]
        for key in ("subshape_type", "surface", "normal", "centroid", "area_mm2")
    }


def _statuses(evaluation: Any) -> dict[str, str]:
    return {
        str(result.feature_id): result.status for result in evaluation.result.features
    }


def _windowed_plate_top_area() -> float:
    """Closed form for the +Z face left after the block is CUT: the 100x100 plate
    minus the 75x75 window minus the 28 vents whose centres fall outside it."""
    outside = VENT_N**2 - 6**2
    return PLATE_W * PLATE_W - BOSS_SIDE**2 - outside * math.pi * VENT_R**2


def test_the_plate_is_an_ORDINARY_grille_not_a_pathological_one() -> None:
    """The premise, measured, because the whole ticket turns on it. An 8x8 grid of
    Ø9 holes in a 100x100 plate is a grille or a lightened web — 40.7 % open — and
    §12a's inferred band, whose lower end is ``2*current - outer``, degrades linearly
    with exactly that fraction. On the bare grille it already reaches down to
    1857 mm^2; on the WINDOWED plate this file actually matches against it goes
    NEGATIVE, which is §12a's own stated limiting case ("in the limit of a face that
    is half holes it admits any stored area at all"). At that point the tier has only
    the normal sense and the containment test left, and the 5625 mm^2 boss top sits
    comfortably inside it."""
    open_fraction = OPEN_FRACTION
    assert open_fraction == pytest.approx(0.407, abs=0.001)
    grille = PLATE_W * PLATE_W * (1.0 - open_fraction)
    assert grille == pytest.approx(5928.5, abs=0.1)
    assert 2.0 * grille - PLATE_W * PLATE_W == pytest.approx(1857.0, abs=0.5)

    windowed = _windowed_plate_top_area()
    assert windowed == pytest.approx(2593.7, abs=0.1)
    lower_bound = 2.0 * windowed - PLATE_W * PLATE_W
    assert lower_bound < 0.0
    boss_top_area = BOSS_SIDE**2
    assert lower_bound < boss_top_area  # ... so the old band admitted it


def _top_of_part(features: list[dict[str, Any]], tree_version: int) -> float:
    """The evaluated part's highest z — where the pin's top face ends up."""
    evaluation = _evaluate(features, tree_version)
    assert evaluation.result.properties is not None, _statuses(evaluation)
    return evaluation.result.properties.bounding_box.max.z


def test_the_pin_stands_on_the_boss_while_the_extrude_still_ADDS() -> None:
    """The control, and the number the failure below is measured against. With the
    block still a boss, the datum resolves to the boss top at z = 18 and the 5 mm pin
    reaches z = 23. Without this the refusal would be satisfied by a matcher that
    refuses everything, and the 8 mm error would have nothing to be 8 mm from."""
    authored = [*_prefix()]
    authored += _seat(_boss_top_signature(authored))
    assert set(_statuses(_evaluate(authored, 2)).values()) == {"ok"}
    assert _top_of_part(authored, 2) == pytest.approx(BOSS_TOP_Z + PIN_H, abs=1e-9)


def test_turning_the_boss_into_a_WINDOW_leaves_an_HONEST_error() -> None:
    """THE GEOM-3 GATE at the tree level. The extrude's operation is toggled add ->
    cut: the protrusion the datum was placed on becomes a window through the plate.
    The feature is still there, so the reference is well-formed and reaches the
    matcher — and the face it described is gone, with nothing left on its plane at
    all. The only +Z candidate is the vented plate top 8 mm below, which by then is
    74 % open, so §12a's inferred band has no lower end left (it evaluates NEGATIVE)
    and ADMITTED the stored 5625 mm^2. The stored signature now carries the boss
    top's OWN outer wire — 5625 mm^2 and 300 mm about (50, 50) — against the plate's
    10000 and 400, so there is nothing to infer, the datum fails honestly, and the
    two features seated on it are stranded by the strict-prefix rule rather than
    quietly built in the wrong place."""
    authored = [*_prefix()]
    stored = _boss_top_signature(authored)
    assert stored["outer_area_mm2"] == pytest.approx(BOSS_SIDE**2, abs=1e-9)
    assert stored["outer_perimeter_mm"] == pytest.approx(4.0 * BOSS_SIDE, abs=1e-9)

    revised = [*_prefix("cut"), *_seat(stored)]
    result = next(
        r
        for r in _evaluate(revised, 3).result.features
        if str(r.feature_id) == str(DATUM_ON_BOSS)
    )
    assert result.error is not None
    assert result.error.code == "subshape_unresolved"


def test_the_SAME_edit_silently_drops_the_pin_8mm_for_a_LEGACY_selector() -> None:
    """The residual exposure, gated as a NUMBER rather than described. A document
    saved before the outer invariants existed carries only ``(normal, centroid,
    area_mm2)``, and a stateless geometry service cannot upgrade a selector it does
    not own — so that document still takes the inferred band and still gets the wrong
    answer on this exact edit. Not an error: a clean, all-ok rebuild of a part whose
    pin now stands at z = 15 instead of z = 23. That 8 mm is what "silent wrong
    geometry" means, and it is why the contract had to change rather than the bound.
    The legacy population is closed and shrinks on every re-pick, but it does not
    empty itself; closing it needs a document-side re-emit (§12b). This test is what
    makes that statement checkable, and what goes red the day it is fixed."""
    authored = [*_prefix()]
    legacy = _legacy(_boss_top_signature(authored))
    revised = [*_prefix("cut"), *_seat(legacy)]
    assert set(_statuses(_evaluate(revised, 4)).values()) == {"ok"}
    assert _top_of_part(revised, 4) == pytest.approx(PLATE_T + PIN_H, abs=1e-9)


def test_deleting_or_suppressing_the_boss_never_reaches_the_matcher_at_all() -> None:
    """The framing correction, asserted so it cannot get lost. The ticket describes
    "delete the boss", and a literal deletion is caught BEFORE any face matching: the
    reference names the feature that made the face, so removing it is a dangling
    reference, and suppressing it trips ``references_suppressed``. Both are honest
    errors already and neither is the GEOM-3 hazard — which is why the gate above is
    written around an operation toggle instead. Recorded here because a future reader
    would otherwise reasonably expect the deletion case to be the one under test."""
    authored = [*_prefix()]
    stored = _boss_top_signature(authored)

    suppressed = copy.deepcopy(authored)
    for feature in suppressed:
        if feature["id"] == str(BOSS_EXTRUDE):
            feature["feature"]["suppressed"] = True
    suppressed += _seat(stored)
    result = next(
        r
        for r in _evaluate(suppressed, 5).result.features
        if str(r.feature_id) == str(DATUM_ON_BOSS)
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "references_suppressed"

    deleted = [
        *(f for f in authored if f["id"] != str(BOSS_EXTRUDE)),
        *_seat(stored),
    ]
    assert _statuses(_evaluate(deleted, 6))[str(DATUM_ON_BOSS)] != "ok"
