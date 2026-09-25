"""Geometry-QA round 2 for offset-surface shells: re-verification of `7139ec2`
(the per-face Gauss-Legendre volume route) and `bd6037d` (offset_edges), by
geometry QA, independently of the builder (docs/GEOMETRY-QA.md 2026-09-25,
"Round 2").

Truths come from test_offset_surface_qa's polygon derivation (shoelace polygons
through the spline and its exact inward offset, Richardson-extrapolated), which
agrees with a 40-digit mpmath derivation to 1e-13 on the golden. Bodies are
built through the kernel's own ``shell_body``, the function the tree's shell
feature dispatches to.

Pinned here:

* the fix holds on bodies the builder did not measure: the case-2 spline
  shelled 1.5 mm (its rim edge was 7.8e-4 mm loose) and the golden's spline
  shelled 2 mm;
* a SEALED hollow (no face opened, the UI's default) of the golden's spline
  reads its true volume through the NURBS fallback, within the fallback's
  measured accuracy;
* R2-F1 (strict xfail): a sealed hollow is not deterministic. OCCT returns the
  cavity shell's faces in a different order on every build (even a plain box),
  so GLB bytes differ per rebuild;
* R2-F2 (strict xfail): a shell whose open face is INCLINED leaves the wall's
  rim edge 1.1e-2 mm loose. That edge is not an isoline, so offset_edges cannot
  rebuild it, and the volume reads 1.3e-3 mm^3 high;
* R2-F4 (strict xfail): a sealed hollow's offset wall has an extrusion basis
  with no knots, so the Gauss-Legendre route never converges on it and every
  sealed spline shell takes the approximate fallback;
* R2-F5 (strict xfail): case 2 still round-trips STEP 8e-7 mm^3 apart, above
  ROUNDTRIP_TOL, because its cavity-floor edges (3.6e-6 mm) are left loose.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import importlib.util
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest
from build123d import Box, Edge, Face, Keep, Plane, Solid, Vector, Wire, extrude
from geometry.kernel import export_step_bytes
from geometry.kernel.imports import import_step_solid
from geometry.kernel.properties import (
    _checked_offset_moments,
    _is_offset,
    isoline_rectangle,
    volume_properties,
)
from geometry.kernel.shell import shell_body
from geometry.kernel.types import BodyShape
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pnt

TESTS = Path(__file__).resolve().parent

#: The class's documented volume bound (the golden's 5e-7). Measured at
#: bd6037d: case-2 spline t1.5 -4.26e-7, golden spline t2 -2.41e-8.
CLASS_TOL = 5e-7

#: The NURBS fallback's error on the sealed golden spline, measured +5.73e-6
#: (+6.45e-6 forced on the open golden, +4.10e-5 forced on case 2): the
#: fallback's accuracy scales with the part, it is not a fixed bound.
FALLBACK_TOL = 2e-5


@cache
def _qa() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "offset_qa_round1", TESTS / "test_offset_surface_qa.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _golden_fit() -> tuple[tuple[float, float], ...]:
    fit: tuple[tuple[float, float], ...] = _qa()._golden_fit()
    return fit


def _prism(width: float, height: float, fit: tuple[tuple[float, float], ...]) -> Solid:
    wire = Wire(
        [
            Edge.make_line((0, 0, 0), (width, 0, 0)),
            Edge.make_line((width, 0, 0), (width, fit[0][1], 0)),
            Edge.make_spline([Vector(x, y, 0) for x, y in fit]),
            Edge.make_line((0, fit[-1][1], 0), (0, 0, 0)),
        ]
    )
    return extrude(Face(wire), height).solids()[0]


def _top(body: BodyShape) -> Face:
    return max(body.faces(), key=lambda f: f.center().Z)


def _shelled(
    width: float,
    height: float,
    wall: float,
    fit: tuple[tuple[float, float], ...],
    *,
    sealed: bool = False,
) -> BodyShape:
    prism = _prism(width, height, fit)
    return shell_body(prism, [] if sealed else [_top(prism)], wall)


def _areas(
    width: float, wall: float, fit: tuple[tuple[float, float], ...]
) -> tuple[float, float]:
    """(A, A_in): the profile and its inner parallel region at *wall*."""
    truth = _qa()._polygon_truth(width, 10.0, wall, fit)
    return float(truth.area), float(truth.area_in)


def _x_moments(
    width: float, wall: float, fit: tuple[tuple[float, float], ...]
) -> tuple[float, float]:
    """(int x dA over the profile, over its inner parallel region), recovered
    exactly from the open-shell truth at two heights: its centroid satisfies
    cx V(H) = Mx H - Mx_in (H - t), linear in (Mx, Mx_in)."""
    rows = []
    for height in (10.0, 20.0):
        truth = _qa()._polygon_truth(width, height, wall, fit)
        rows.append((height, height - wall, truth.centroid[0] * truth.volume))
    (h1, c1, r1), (h2, c2, r2) = rows
    det = -h1 * c2 + h2 * c1
    mx = (-r1 * c2 + r2 * c1) / det
    mx_in = (h1 * r2 - h2 * r1) / det
    return mx, mx_in


# --- the fix, on bodies the builder did not measure ---------------------------


@pytest.mark.parametrize(
    ("width", "height", "wall", "which"),
    [(40.0, 20.0, 1.5, "case2"), (30.0, 10.0, 2.0, "golden")],
    ids=["case2-spline-t1.5", "golden-spline-t2"],
)
def test_a_shelled_spline_prism_reads_its_true_volume(
    width: float, height: float, wall: float, which: str
) -> None:
    fit = tuple(_qa().CASE2_FIT) if which == "case2" else _golden_fit()
    truth = _qa()._polygon_truth(width, height, wall, fit).volume
    body = _shelled(width, height, wall, fit)
    assert volume_properties(body).volume == pytest.approx(truth, abs=CLASS_TOL)


def test_a_sealed_spline_hollow_reads_its_true_volume_through_the_fallback() -> None:
    area, area_in = _areas(30.0, 1.0, _golden_fit())
    truth = area * 10.0 - area_in * (10.0 - 2 * 1.0)
    body = _shelled(30.0, 10.0, 1.0, _golden_fit(), sealed=True)
    assert len(body.shells()) == 2
    assert volume_properties(body).volume == pytest.approx(truth, abs=FALLBACK_TOL)


# --- R2-F1: sealed hollows are not deterministic ------------------------------


def _face_order(body: BodyShape) -> list[tuple[float, ...]]:
    return [tuple(round(c, 6) for c in tuple(f.center())) for f in body.faces()]


@pytest.mark.xfail(
    strict=True,
    reason="GEOMETRY-QA 2026-09-25 R2-F1: OCCT's hollow with no opened face returns "
    "the cavity shell's faces in a different order on every build (4/4 distinct)",
)
def test_a_sealed_hollow_rebuilds_in_the_same_face_order() -> None:
    orders = [
        _face_order(shell_body(Box(40, 25, 10).solids()[0], [], 2.0)) for _ in range(6)
    ]
    assert all(order == orders[0] for order in orders)


# --- R2-F2: an inclined open face leaves the rim loose ------------------------

SLOPE, RIM_Z0 = 0.2, 10.0


def _inclined() -> BodyShape:
    prism = _prism(30.0, 25.0, _golden_fit())
    cut = prism.split(
        Plane(origin=(0, 0, RIM_Z0), z_dir=(-SLOPE, 0, 1)), keep=Keep.BOTTOM
    )
    assert cut is not None
    solid = cut.solids()[0]
    return shell_body(solid, [_top(solid)], 1.0)


def _inclined_truth() -> float:
    """Top plane z = RIM_Z0 + SLOPE x; cavity from z = t up to it over A_in."""
    area, area_in = _areas(30.0, 1.0, _golden_fit())
    mx, mx_in = _x_moments(30.0, 1.0, _golden_fit())
    return RIM_Z0 * area + SLOPE * mx - ((RIM_Z0 - 1.0) * area_in + SLOPE * mx_in)


def test_the_inclined_case_is_the_shell_it_claims_to_be() -> None:
    """Guards R2-F2's xfail against failing for the wrong reason."""
    body = _inclined()
    assert (len(body.faces()), len(body.edges())) == (11, 24)
    [wall] = [f for f in body.faces() if _is_offset(f)]
    assert isoline_rectangle(wall) is None  # the fallback route, by construction
    # Wrong by the defect (~1e-3 mm^3), never by a missing cavity (~3000 mm^3).
    assert volume_properties(body).volume == pytest.approx(_inclined_truth(), abs=0.01)


@pytest.mark.xfail(
    strict=True,
    reason="GEOMETRY-QA 2026-09-25 R2-F2: the inclined rim edge is 1.1e-2 mm loose "
    "(not an isoline, so offset_edges skips it); the volume reads +1.28e-3 mm^3",
)
def test_an_inclined_open_shell_reads_its_true_volume() -> None:
    assert volume_properties(_inclined()).volume == pytest.approx(
        _inclined_truth(), abs=CLASS_TOL
    )


@pytest.mark.xfail(
    strict=True,
    reason="GEOMETRY-QA 2026-09-25 R2-F2: the same loose rim edge (1.1e-2 mm)",
)
def test_an_inclined_open_shell_has_no_edge_beyond_the_kernel_tolerance() -> None:
    worst = max(BRep_Tool.Tolerance_s(e.wrapped) for e in _inclined().edges())
    assert worst <= 1e-4


# --- R2-F4: the sealed wall never takes the exact route -----------------------


@pytest.mark.xfail(
    strict=True,
    reason="GEOMETRY-QA 2026-09-25 R2-F4: a sealed hollow's offset wall has an "
    "extrusion basis with no knot breaks; order 16 vs 24 disagree by 5.3e-3",
)
def test_a_sealed_spline_wall_takes_the_exact_route() -> None:
    body = _shelled(30.0, 10.0, 1.0, _golden_fit(), sealed=True)
    [wall] = [f for f in body.faces() if _is_offset(f)]
    assert _checked_offset_moments(wall, gp_Pnt(0, 0, 0)) is not None


# --- R2-F5: the class does not meet ROUNDTRIP_TOL -----------------------------


@pytest.mark.xfail(
    strict=True,
    reason="GEOMETRY-QA 2026-09-25 R2-F5: case 2 round-trips +8.1e-7 mm^3; its "
    "cavity-floor edges (3.6e-6 mm) are left as the shell fitted them",
)
def test_case_2_round_trips_within_roundtrip_tol(roundtrip_tol: float) -> None:
    body = _shelled(40.0, 20.0, 2.0, tuple(_qa().CASE2_FIT))
    reimported = import_step_solid(export_step_bytes(body).decode())
    delta = volume_properties(reimported).volume - volume_properties(body).volume
    assert abs(delta) <= roundtrip_tol
