"""Zero-width-slit predicate (finding SH-1) — the ONE shared degeneracy probe.

:mod:`geometry.kernel.degenerate` answers "does this body contain two coincident
faces with no material between them?", and this module pins the three things a
caller relies on:

* it FIRES on the only body the kernel is known to produce one on (the pinched
  shell of the CM-4 layout) with the measured area and position;
* it does NOT fire on sound bodies — including **every shipped golden body**,
  which is the cross-verb sibling gate: the predicate lives in one place, and if
  any verb (sheet-metal folds, booleans, patterns, mirrors, imports) ever starts
  shipping a slit, this test names it instead of a STEP round-trip failing three
  layers away;
* the documented scope holds — a cross-LUMP face touch is a legitimate
  multi-body configuration, not a slit (the same call
  :mod:`geometry.kernel.interference` makes), and the report is ordered
  largest-first regardless of OCCT's face traversal.

The one OBSERVED LIMIT this module used to pin — a closed hem authored with a bend
radius below the kernel linear tolerance shipping a slit body, because the
sheet-metal fold path did not ask this predicate — is CLOSED as of HEM-1
(2026-08-28) and its test is now the guard it documented: the fold refuses that
radius outright (``hem_gap_degenerate``). A hem's layers sit exactly
``2 * bend_radius`` apart, so the degeneracy is arithmetic on an input; the check
therefore fires before the fuse rather than probing the body afterwards.
"""

import json
import uuid
from pathlib import Path

import pytest
from build123d import Axis, Face, Solid, Vector
from geometry.features.evaluate import evaluate_tree
from geometry.kernel.degenerate import (
    SLIT_AREA_FLOOR_MM2,
    find_zero_width_slits,
)
from geometry.kernel.healing import conform_solid
from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.shell import shell_body
from py_kit.schemas.features import EvaluateTreeRequest

#: The CM-4 / SH-1 layout, kernel-level: 40x40x10 plate, [4,12]x[10,30]
#: through-pocket, r3 on every Z-parallel edge. The rib between the outer wall and
#: the pocket wall is 4.0 mm, so a 2.0 mm shell pinches its cavity to zero width.
_PLATE = (40.0, 40.0, 10.0)
_POCKET = (4.0, 10.0, 8.0, 20.0)  # x0, y0, dx, dy
_FILLET_R = 3.0
_PINCH_THICKNESS = 2.0

#: The slit that pinch produces, hand-checked against the geometry: the dilated
#: pocket's flat left face is (30 - 10) - 2 x 3 = 14 mm long in y and the cavity is
#: 10 - 2 = 8 mm tall, so 14 x 8 = 112.0 mm^2 of coincident face at x = t = 2,
#: centred on the pocket's own y centre (20) and the cavity's mid-height (6).
_SLIT_AREA_MM2 = 112.0
_SLIT_AT = (2.0, 20.0, 6.0)

GOLDEN_ROOTS = (
    Path(__file__).resolve().parent.parent / "goldens",
    Path(__file__).resolve().parent.parent / "goldens-sheet-metal",
)


def _pocketed_and_filleted() -> Solid:
    """The SH-1 body up to (not including) the shell — a valid, slit-free solid."""
    plate = Solid.make_box(*_PLATE)
    x0, y0, dx, dy = _POCKET
    cutter = Solid.make_box(dx, dy, _PLATE[2]).translate(Vector(x0, y0, 0.0))
    pocketed: Solid = (plate - cutter).solids()[0]
    edges = pocketed.edges().filter_by(Axis.Z)
    return pocketed.fillet(_FILLET_R, edges).solids()[0]  # pyright: ignore[reportUnknownMemberType]


def _top_face(body: Solid) -> list[Face]:
    """The +Z top face of *body* (the shell's open face)."""
    return [
        f
        for f in body.faces()
        if abs(f.center().Z - _PLATE[2]) < 1e-9 and abs(f.normal_at().Z - 1.0) < 1e-9
    ]


def _raw_pinched_hollow() -> Solid:
    """OCCT's hollow at the pinch thickness, with no guard and no healing."""
    body = _pocketed_and_filleted()
    return body.hollow(_top_face(body), -_PINCH_THICKNESS).solids()[0]  # pyright: ignore[reportUnknownMemberType]


def _tree_goldens() -> list[Path]:
    """Every feature-TREE golden's model.json (shape goldens carry no tree)."""
    models: list[Path] = []
    for root in GOLDEN_ROOTS:
        for model in sorted(root.glob("*/model.json")):
            if "features" in json.loads(model.read_text(encoding="utf-8")):
                models.append(model)
    return models


TREE_GOLDENS = _tree_goldens()


def test_the_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the sibling gate, never silently pass it."""
    assert len(TREE_GOLDENS) > 40, f"only {len(TREE_GOLDENS)} tree goldens discovered"


def test_a_sound_body_has_no_slit() -> None:
    """The no-op path on the two simplest real bodies: a box and a shelled tray."""
    box = Solid.make_box(40.0, 25.0, 10.0)
    assert find_zero_width_slits(box) == []
    tray = shell_body(box, _top_face(Solid.make_box(40.0, 25.0, 10.0)), 2.0)
    assert find_zero_width_slits(tray) == []


def test_the_pinched_shell_reports_the_measured_slit() -> None:
    """It FIRES where it must, with the hand-checked area and position (SH-1).

    ``_SLIT_AREA_MM2`` / ``_SLIT_AT`` are derived from the layout (see their
    comment), not recorded from this call — an exact 112.0 mm^2 at x=2 is the
    geometry saying the two offsets landed on the same plane.
    """
    slits = find_zero_width_slits(_raw_pinched_hollow())
    assert len(slits) == 1, slits
    assert slits[0].area_mm2 == pytest.approx(_SLIT_AREA_MM2, abs=1e-9)
    assert slits[0].at == pytest.approx(_SLIT_AT, abs=1e-9)


def test_slits_are_reported_largest_first() -> None:
    """Determinism (RESEARCH §9): the report is ordered by area, so the message a
    caller quotes at the user never depends on OCCT's face order.

    The HEALED pinched body carries two coincident pairs (``ShapeFix`` splits the
    larger face along the T-junction, which is why healing is not a fix — SH-1),
    so it is the fixture with something to order.
    """
    slits = find_zero_width_slits(conform_solid(_raw_pinched_hollow()))
    assert len(slits) == 2, slits
    assert [s.area_mm2 for s in slits] == sorted(
        (s.area_mm2 for s in slits), reverse=True
    )
    assert slits[-1].area_mm2 == pytest.approx(_SLIT_AREA_MM2, abs=1e-9)


def test_a_cross_lump_face_touch_is_not_a_slit() -> None:
    """Documented scope: two lumps of a multi-body part that touch face-to-face are
    a legitimate configuration, so the pair is never probed.

    This is the SAME call :mod:`geometry.kernel.interference` makes (a
    coincident-face touch is NO clash, ``CLASH_VOLUME_FLOOR_MM3``); disagreeing
    would refuse valid multi-body parts.
    """
    left = Solid.make_box(10.0, 10.0, 10.0)
    right = Solid.make_box(10.0, 10.0, 10.0).translate(Vector(10.0, 0.0, 0.0))
    body = assemble_lumps([left, right])
    assert len(body.solids()) == 2
    assert find_zero_width_slits(body) == []


def test_the_area_floor_is_one_kernel_tolerance_square() -> None:
    """The floor is derived, not chosen: a pair whose overlap is smaller than a
    kernel-tolerance square (1e-4 mm)^2 is a grazing edge/corner contact, not a
    crack — the area-dimension twin of the interference probe's tolerance cube."""
    assert pytest.approx(1e-8, rel=1e-12) == SLIT_AREA_FLOOR_MM2
    assert _SLIT_AREA_MM2 > SLIT_AREA_FLOOR_MM2 * 1e6


@pytest.mark.parametrize(
    "model", TREE_GOLDENS, ids=[m.parent.name for m in TREE_GOLDENS]
)
def test_every_shipped_golden_body_is_slit_free(model: Path) -> None:
    """THE CROSS-VERB SIBLING GATE (the brief's "check the sibling verbs").

    Every golden body — extrude, boolean, fillet/chamfer, draft, hole, pattern,
    mirror, revolve/sweep/loft, STEP import, shell, and every sheet-metal flange /
    hem / corner-relief / flat-pattern body — is rebuilt and probed (44 under
    `goldens/` + 16 under `goldens-sheet-metal/`). All 60 were slit-free when the
    predicate landed (worst probe 3.6 ms, on the 54-face hemmed tray), so this is a
    zero-false-positive baseline as much as a regression gate:
    the day a verb starts pinching, the failure names that verb here instead of
    surfacing as a STEP round-trip drift or a wrong mass three layers away.
    """
    request = EvaluateTreeRequest.model_validate(
        json.loads(model.read_text(encoding="utf-8"))
    )
    evaluation = evaluate_tree(request)
    assert [r.status for r in evaluation.result.features] == [
        "ok" for _ in evaluation.result.features
    ], f"{model.parent.name}: golden did not evaluate clean"
    body = evaluation.body
    assert body is not None
    assert find_zero_width_slits(body) == [], (
        f"{model.parent.name}: shipped golden body contains a zero-width slit"
    )


def test_a_sub_tolerance_hem_gap_is_refused_not_shipped() -> None:
    """PROMOTED GUARD (HEM-1, 2026-08-28): the fold path now REFUSES the body this
    file used to record as a live limit.

    A hem's two layers are ``2 * bend_radius_mm`` apart and the schema only requires
    ``> 0``, so ``bend_radius_mm = 1e-6`` gives a 2e-6 mm gap — a tenth of a percent
    of the 1e-4 mm tolerance at which this kernel calls two faces the same place.
    Until HEM-1 the hem reported ``ok`` and shipped a body this predicate called
    degenerate (``ZeroWidthSlit(area_mm2=300.0, at=(42.5, 10.0, 2.0))`` — 300 mm^2
    of coincident face over the 15 mm return). The docstring of the limit said "if
    the fold path or the schema starts refusing it, this test fails and gets
    promoted to the guard it documents"; this is that promotion.

    The refusal is arithmetic on the resolved radius (``hem_gap_degenerate``), so it
    fires BEFORE the kernel spends a fuse on a body that must be thrown away — the
    predicate is what DEFINES the floor, not what detects the failure after the
    fact. Same posture as ``find_zero_width_slits``' other callers (RESEARCH §9):
    detect, degrade to a typed error naming the fix, never ship the cracked body.
    """
    model = json.loads(
        (GOLDEN_ROOTS[1] / "closed-hem-plate" / "model.json").read_text(
            encoding="utf-8"
        )
    )
    hem = model["features"][-1]["feature"]
    assert hem["type"] == "sheet_metal_hem"
    hem["params"]["bend_radius_mm"] = 1e-6
    model["part_id"] = str(uuid.uuid4())

    evaluation = evaluate_tree(EvaluateTreeRequest.model_validate(model))
    assert [r.status for r in evaluation.result.features] == ["ok", "ok", "error"]
    error = evaluation.result.features[-1].error
    assert error is not None and error.code == "hem_gap_degenerate", error
    # Refused, so the last GOOD body is the plain plate — and it carries no slit.
    body = evaluation.body
    assert body is not None
    assert find_zero_width_slits(body) == []
