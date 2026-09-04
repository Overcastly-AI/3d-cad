"""SHEET-FACE GUARD — an edge flange may not be folded off a THICKNESS edge.

Gate for EDGEFLANGE-1 (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass
today)" S-4). On the audit's 120 x 60 x 2 plate, `new-edge-flange` offered the
four 2 mm-long THICKNESS edges alongside the sheet's real boundary edges and, on
accepting one, built a 25 x 2 mm sliver tab folded off the corner (V 14400 ->
14525.13 mm^3, faces 6 -> 11) while the feature tree read `OK`, the panel read
`Solved` and the inspector read `Up to date`. There is no material in a 2 mm cut
edge to bend a flange out of; SolidWorks refuses the selection and Fusion filters
it out of the pick set. Loft now REFUSES it with a typed error naming the rule
(:class:`~geometry.sheet_metal.edge_flange.EdgeFlangeEdgeError` ->
``edge_flange_bad_edge``), so a user who tries it learns why rather than finding
the pick silently missing.

Four halves, in the order the defect is argued:

* **The reproduction, now a refusal** — all four thickness edges of the audit's
  own plate are refused, and the message names the rule.
* **The regression the guard must not cause** — all eight real sheet-face
  boundary edges of that SAME plate still fold, to the analytic volume. Pinned
  end-to-end (build + FLATTEN + STEP round-trip) by the new golden
  ``goldens-sheet-metal/sheet-face-guard-bracket-edge-flange``, the audit's exact
  bracket, which also rides the whole ``*-edge-flange`` battery in
  ``test_sheet_metal_edge_flange.py``.
* **The sign is the predicate** — the walls of a gauge-WIDE slot are also
  anti-parallel and exactly one gauge apart, but with AIR between them rather
  than material. A distance-only classifier would call them sheet faces; the
  signed test refuses them, and the negative control here proves the distance
  alone would not have.
* **Wider than the ticket** — the HEM folds through the same
  :func:`~geometry.sheet_metal.edge_flange.build_edge_flange`, so it inherits the
  guard. Asserted rather than assumed.
"""

import math
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

# Upstream export/import signatures carry Shape[Unknown]/PathLike[Unknown] type
# params (the same gap tests/test_step_roundtrip.py documents) — scoped ignores.
from build123d import (
    Box,
    CenterOf,
    Edge,
    GeomType,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.features.evaluate import evaluate_tree
from geometry.kernel import measure_shape
from geometry.kernel.edges import enumerate_edges
from geometry.kernel.types import BodyShape
from geometry.schemas import ShapeProperties
from geometry.sheet_metal import build_edge_flange
from geometry.sheet_metal.edge_flange import (
    EdgeFlangeEdgeError,
    _is_sheet_face,  # pyright: ignore[reportPrivateUsage]
)
from py_kit.schemas.features import EvaluateTreeRequest

_GOLDEN_DIR = (
    Path(__file__).resolve().parent.parent
    / "goldens-sheet-metal"
    / "sheet-face-guard-bracket-edge-flange"
)

#: The audit's fixture, to the millimetre (S-4): a 120 x 60 mm blank at 2 mm gauge.
_LENGTH_MM = 120.0
_WIDTH_MM = 60.0
_GAUGE_MM = 2.0
#: The audit's fold: 25 mm leg, 90 deg, the part's 3 mm inherited bend radius.
_LEG_MM = 25.0
_ANGLE_DEG = 90.0
_RADIUS_MM = 3.0

#: Kernel-side comparison bound for the analytic volumes below. NOT an ad-hoc
#: epsilon: it is the ``volume_tolerance`` the sibling edge-flange goldens
#: document (``goldens-sheet-metal/*-edge-flange/expected.json``) for exactly this
#: quantity on exactly this kernel, and the residual measured on these bodies is
#: 0.0 (2026-08-24, build123d 0.11.1 / OCCT 7.9).
_VOLUME_TOL_MM3 = 1e-6


def _plate() -> BodyShape:
    """The audit's plate, centred so its four thickness edges sit at the corners."""
    return Box(_LENGTH_MM, _WIDTH_MM, _GAUGE_MM).translate((0.0, 0.0, _GAUGE_MM / 2.0))


def _straight_edges(body: BodyShape) -> list[Edge]:
    """Every straight edge of *body*, in a deterministic (length, midpoint) order."""
    records = [r for r in enumerate_edges(body) if r.signature.curve == "line"]
    return [
        r.edge
        for r in sorted(
            records,
            key=lambda r: (
                round(float(r.edge.length), 9),
                r.signature.midpoint.x,
                r.signature.midpoint.y,
                r.signature.midpoint.z,
            ),
        )
    ]


def _thickness_edges(body: BodyShape) -> list[Edge]:
    return [e for e in _straight_edges(body) if abs(float(e.length) - _GAUGE_MM) < 1e-9]


def _sheet_boundary_edges(body: BodyShape) -> list[Edge]:
    return [
        e for e in _straight_edges(body) if abs(float(e.length) - _GAUGE_MM) >= 1e-9
    ]


def _flange_volume(base_leg_edge_len: float) -> float:
    """Analytic volume of the plate + one full-width 90 deg flange off it.

    plate + (straight leg cross-section + quarter annulus) swept the bend width."""
    section = _LEG_MM * _GAUGE_MM + (math.pi / 4.0) * (
        (_RADIUS_MM + _GAUGE_MM) ** 2 - _RADIUS_MM**2
    )
    return _LENGTH_MM * _WIDTH_MM * _GAUGE_MM + section * base_leg_edge_len


# --------------------------------------------------------------------------- #
# The reproduction, now a refusal                                             #
# --------------------------------------------------------------------------- #


def test_the_audit_plate_really_has_four_thickness_edges() -> None:
    """Fixture guard: a discovery change must fail this file, never empty it."""
    plate = _plate()
    assert len(_thickness_edges(plate)) == 4
    assert len(_sheet_boundary_edges(plate)) == 8
    assert plate.volume == pytest.approx(14400.0, abs=_VOLUME_TOL_MM3)


@pytest.mark.parametrize("index", range(4))
def test_thickness_edge_is_refused_with_a_typed_error(index: int) -> None:
    """S-4's exact pick: each 2 mm cut edge is an EdgeFlangeEdgeError, not a tab."""
    plate = _plate()
    edge = _thickness_edges(plate)[index]
    with pytest.raises(EdgeFlangeEdgeError) as excinfo:
        build_edge_flange(plate, edge, _LEG_MM, _ANGLE_DEG, _RADIUS_MM, _GAUGE_MM)
    message = str(excinfo.value)
    # The refusal must teach the rule, not merely deny the pick (EDGEFLANGE-1 FIX).
    assert "cut (thickness) faces" in message
    assert "2 mm sheet" in message
    assert "flat face" in message


def test_the_sliver_tab_the_audit_measured_is_no_longer_reachable() -> None:
    """The specific wrong body S-4 recorded (V 14525.13 mm^3, 11 faces) cannot be
    produced from any thickness edge of the plate."""
    plate = _plate()
    for edge in _thickness_edges(plate):
        with pytest.raises(EdgeFlangeEdgeError):
            build_edge_flange(plate, edge, _LEG_MM, _ANGLE_DEG, _RADIUS_MM, _GAUGE_MM)


# --------------------------------------------------------------------------- #
# The regression the guard must not cause                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("index", range(8))
def test_every_real_boundary_edge_of_the_same_plate_still_folds(index: int) -> None:
    """The other half of the acceptance: the guard narrows the pick set to exactly
    the thickness edges and touches nothing else. Volume is analytic, not recorded."""
    plate = _plate()
    edge = _sheet_boundary_edges(plate)[index]
    result = build_edge_flange(plate, edge, _LEG_MM, _ANGLE_DEG, _RADIUS_MM, _GAUGE_MM)
    assert len(result.body.solids()) == 1
    assert result.body.volume == pytest.approx(
        _flange_volume(float(edge.length)), abs=_VOLUME_TOL_MM3
    )
    assert result.cyl_signature.radius_mm == pytest.approx(_RADIUS_MM, abs=1e-6)


def test_guard_golden_survives_step_roundtrip(
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[[str, ShapeProperties, ShapeProperties], None],
) -> None:
    """The new golden's folded body survives STEP export→import with its mass
    properties (``ROUNDTRIP_TOL``) and topology (exact) intact, as ONE solid.

    The shared round-trip gate (``tests/test_sheet_metal_step_roundtrip.py``)
    parametrizes over the ``*-flat-pattern-view`` inventory only, so this golden —
    an ``*-edge-flange`` one — would otherwise have build + flatten coverage but no
    export coverage. It uses the SAME conftest fixture, so the one documented
    kernel bound stays the single source of truth."""
    request = EvaluateTreeRequest.model_validate_json(
        (_GOLDEN_DIR / "model.json").read_text(encoding="utf-8")
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
    assert evaluation.body is not None
    original = measure_shape(evaluation.body)

    step_path = tmp_path / "sheet-face-guard-bracket.step"
    assert export_step(evaluation.body, step_path), "STEP export failed"
    imported = import_step(step_path)
    solids = imported.solids()
    assert len(solids) == 1, f"expected 1 solid after import, got {len(solids)}"
    assert_roundtrip_preserved(
        "sheet-face-guard-bracket-edge-flange", measure_shape(solids[0]), original
    )


def test_the_two_skins_are_sheet_faces_and_the_four_rims_are_not() -> None:
    """The predicate itself, face by face: exactly the top and bottom skins of the
    plate classify as sheet faces; all four cut (rim) faces do not."""
    plate = _plate()
    skins = [f for f in plate.faces() if _is_sheet_face(plate, f, _GAUGE_MM)]
    assert len(skins) == 2
    # The two skins are the 120 x 60 flats, gauge apart along Z.
    areas = sorted(round(float(f.area), 9) for f in skins)
    assert areas == [_LENGTH_MM * _WIDTH_MM, _LENGTH_MM * _WIDTH_MM]
    zs = sorted(round(float(f.center(CenterOf.MASS).Z), 9) for f in skins)
    assert zs == [0.0, _GAUGE_MM]


# --------------------------------------------------------------------------- #
# The SIGN is the predicate, not the distance                                 #
# --------------------------------------------------------------------------- #


def _slotted_plate() -> BodyShape:
    """The audit's plate with a gauge-WIDE through slot: two anti-parallel walls
    exactly one gauge apart, with AIR between them instead of material."""
    slot = Box(_GAUGE_MM, 30.0, _GAUGE_MM * 3.0).translate((0.0, 0.0, _GAUGE_MM / 2.0))
    cut = _plate() - slot
    solids = cut.solids()
    assert len(solids) == 1
    return solids[0]


def test_a_gauge_wide_slot_wall_is_not_a_sheet_face() -> None:
    """The negative control for the sign test. The slot's two walls satisfy every
    part of the gauge-pair condition EXCEPT the sign — they face each other across
    the void rather than backing each other across the material — so a
    distance-only classifier would call them skins and let a flange fold out of a
    slot wall. This asserts both halves: the walls are one gauge apart, and they
    are still refused."""
    body = _slotted_plate()
    walls = [
        f
        for f in body.faces()
        if f.geom_type == GeomType.PLANE
        and abs(abs(float(f.normal_at(f.center(CenterOf.MASS)).X)) - 1.0) < 1e-9
        and abs(float(f.center(CenterOf.MASS).X)) < _GAUGE_MM
    ]
    assert len(walls) == 2, "expected the slot's two walls"
    # They ARE one gauge apart — the distance a distance-only test would match on.
    xs = sorted(float(f.center(CenterOf.MASS).X) for f in walls)
    assert xs[1] - xs[0] == pytest.approx(_GAUGE_MM, abs=1e-9)
    # And they are still not sheet faces.
    assert not any(_is_sheet_face(body, f, _GAUGE_MM) for f in walls)


def test_slot_corner_thickness_edges_are_refused_but_slot_end_edges_fold() -> None:
    """On the slotted plate the guard still discriminates: the four vertical edges
    at the slot corners border only cut faces and are refused, while the slot's own
    END edges are boundary edges of the skins and remain foldable."""
    body = _slotted_plate()
    refused = 0
    folded = 0
    for edge in _thickness_edges(body):
        mid = edge @ 0.5
        if abs(float(mid.X)) > _GAUGE_MM:
            continue  # a plate-corner edge, covered above
        try:
            build_edge_flange(body, edge, _LEG_MM, _ANGLE_DEG, _RADIUS_MM, _GAUGE_MM)
        except EdgeFlangeEdgeError:
            refused += 1
        else:
            folded += 1
    # Four vertical slot-corner edges (two walls x two ends) refused; the four
    # horizontal slot-end edges (top/bottom skin boundaries) still fold.
    assert (refused, folded) == (4, 4)


# --------------------------------------------------------------------------- #
# Wider than the ticket: the hem folds through the same machinery              #
# --------------------------------------------------------------------------- #

_SK = uuid.UUID("00000000-0000-0000-0000-0000000090a0")
_BF = uuid.UUID("00000000-0000-0000-0000-0000000090b0")
_FOLD = uuid.UUID("00000000-0000-0000-0000-0000000090c0")


def _rect(length: float, width: float) -> dict[str, object]:
    corners = [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width)]
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
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
    }


def _thickness_edge_ref() -> dict[str, object]:
    """A reference to the 2 mm cut edge at the (120, 0) corner of the plate."""
    return {
        "kind": "subshape",
        "feature_id": str(_BF),
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "curve": "line",
                "end_a": {"x": _LENGTH_MM, "y": 0.0, "z": 0.0},
                "end_b": {"x": _LENGTH_MM, "y": 0.0, "z": _GAUGE_MM},
                "midpoint": {"x": _LENGTH_MM, "y": 0.0, "z": _GAUGE_MM / 2.0},
                "length_mm": _GAUGE_MM,
            },
        },
    }


def _tree(*features: tuple[uuid.UUID, dict[str, object]]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.uuid4()),
            "tree_version": 1,
            "features": [{"id": str(fid), "feature": feat} for fid, feat in features],
        }
    )


def _base_flange() -> dict[str, object]:
    return {
        "type": "sheet_metal_base_flange",
        "version": 1,
        "params": {
            "profile": {"kind": "feature", "feature_id": str(_SK)},
            "thickness_mm": _GAUGE_MM,
            "bend_radius_mm": _RADIUS_MM,
        },
    }


@pytest.mark.parametrize(
    "fold",
    [
        pytest.param(
            {
                "type": "sheet_metal_edge_flange",
                "version": 1,
                "params": {
                    "edge": _thickness_edge_ref(),
                    "flange_length_mm": _LEG_MM,
                    "bend_angle_deg": _ANGLE_DEG,
                },
            },
            id="edge_flange",
        ),
        pytest.param(
            {
                "type": "sheet_metal_hem",
                "version": 1,
                "params": {
                    # No bend_radius_mm: a hem's radius comes from its type and the
                    # part's gauge (HEM-1). The old fixture overrode it to 1.0 mm,
                    # which on this 2 mm gauge is now an OPEN hem's radius under a
                    # 'closed' label — the subject here is the thickness-edge guard,
                    # so the fixture must not carry an unrelated parameter conflict.
                    "edge": _thickness_edge_ref(),
                    "length_mm": 6.0,
                },
            },
            id="hem",
        ),
    ],
)
def test_thickness_edge_degrades_to_edge_flange_bad_edge(
    fold: dict[str, object],
) -> None:
    """Through the evaluator, the audit's pick is a typed ``edge_flange_bad_edge``
    per-feature error — the tree can no longer report ``ok`` on it. Both folds are
    covered because the hem reuses ``build_edge_flange`` (parity §2), which is
    where the guard lives: the ticket names the edge flange, the defect reaches
    every feature that folds off a picked edge."""
    request = _tree(
        (_SK, _rect(_LENGTH_MM, _WIDTH_MM)),
        (_BF, _base_flange()),
        (_FOLD, fold),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    error = evaluation.result.features[2].error
    assert error is not None
    assert error.code == "edge_flange_bad_edge"
    assert "cut (thickness) faces" in error.message
    # Honest degradation (§5): no bend provenance is recorded for a refused fold.
    assert len(evaluation.bend_provenance) == 0
