"""B-rep healing (CM-4) — a shelled body is CONFORMAL before it ever leaves.

The gate that CM-4's STEP round-trip rides on lives in
``test_composition_matrix.py``; this module pins the kernel contract underneath
it (``geometry.kernel.healing``), so a regression names the cause instead of
surfacing three layers up as "the round-trip gained two edges":

* a ``BRepCheck``-valid solid comes back UNTOUCHED (identity) — every golden
  body takes that path, so their topology and byte-identical exports are
  unaffected by the heal existing;
* the pinched-cavity shell (the CM-4 fixture, built here from raw kernel ops)
  is INVALID out of OCCT and VALID out of :func:`shell_body`;
* healing preserves material — asserted against
  :data:`~geometry.kernel.healing.CONFORM_VOLUME_TOL_MM3`, the planar golden
  tier, never an ad-hoc epsilon — and is deterministic + idempotent (RESEARCH §9).

The OCP wheel ships no type stubs, so the raw ``BRepCheck_Analyzer`` probe is
opaque to pyright; the directives scope that relaxation to this file (the same
posture :mod:`geometry.kernel.healing` itself takes).
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false

import pytest
from build123d import Axis, Face, Solid, Vector
from geometry.kernel.healing import CONFORM_VOLUME_TOL_MM3, conform_solid
from geometry.kernel.shell import shell_body
from OCP.BRepCheck import BRepCheck_Analyzer

#: The CM-4 chain, kernel-level: 40x40x10 plate, [4,12]x[10,30] through-pocket,
#: r3 on every Z-parallel edge, 2 mm shell with the top open. The shell offsets
#: the outer wall (x=0 -> x=2) and the pocket wall (x=4 -> x=2) onto the SAME
#: plane, so the 4 mm rib between them stays solid and the cavity pinches to zero
#: width — the configuration that produces the non-conformal T-junction.
_PLATE = (40.0, 40.0, 10.0)
_POCKET = (4.0, 10.0, 8.0, 20.0)  # x0, y0, dx, dy
_FILLET_R = 3.0
_THICKNESS = 2.0


def _pocketed_and_filleted() -> Solid:
    """The CM-4 body up to (not including) the shell — a valid solid."""
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


def _raw_hollow(body: Solid) -> Solid:
    """OCCT's hollow with NO healing — what ``shell_body`` used to return."""
    return body.hollow(_top_face(body), -_THICKNESS).solids()[0]  # pyright: ignore[reportUnknownMemberType]


def _valid(body: Solid) -> bool:
    return BRepCheck_Analyzer(body.wrapped).IsValid()


def test_a_valid_solid_is_returned_unchanged() -> None:
    """The no-op path: a valid body is returned AS IS (identity, not a rebuilt
    copy), so no existing golden's topology or export bytes can shift because
    healing exists."""
    box = Solid.make_box(10.0, 20.0, 30.0)
    assert _valid(box)
    assert conform_solid(box) is box


def test_the_pinched_shell_is_non_conformal_out_of_occt() -> None:
    """The CM-4 root cause, pinned at its source: OCCT's hollow returns the right
    material in a body ``BRepCheck`` rejects — the smaller coincident face's
    corners sit mid-edge on the larger face's edge instead of splitting it. If
    OCCT ever stops doing this, this test fails and the heal becomes dead code
    (which we then delete) — it must not silently stop being exercised."""
    raw = _raw_hollow(_pocketed_and_filleted())
    assert not _valid(raw), (
        "the pinched-cavity shell is conformal out of OCCT now; the CM-4 heal is "
        "no longer exercised by this fixture"
    )


def test_healing_the_pinched_shell_yields_a_valid_solid_of_the_same_material() -> None:
    """Heal = topology only. The invalid body becomes valid with the same face
    count and a volume inside the planar golden tier (measured delta -2.7e-12
    mm^3 on a 6171 mm^3 solid)."""
    raw = _raw_hollow(_pocketed_and_filleted())
    healed = conform_solid(raw)
    assert _valid(healed)
    assert len(healed.faces()) == len(raw.faces())
    assert healed.volume == pytest.approx(raw.volume, abs=CONFORM_VOLUME_TOL_MM3)


def test_healing_is_deterministic_and_idempotent() -> None:
    """RESEARCH §9: two independent builds heal to the same topology counts, and
    healing an already-healed body is a no-op (it is valid, so it takes the
    identity path)."""
    first = conform_solid(_raw_hollow(_pocketed_and_filleted()))
    second = conform_solid(_raw_hollow(_pocketed_and_filleted()))

    def counts(body: Solid) -> tuple[int, int, int]:
        return len(body.faces()), len(body.edges()), len(body.vertices())

    assert counts(first) == counts(second)
    assert conform_solid(first) is first


def test_shell_body_never_returns_a_non_conformal_solid() -> None:
    """The contract the CM-4 gate depends on: whatever OCCT hands back,
    ``shell_body`` returns a valid solid — so what we export is what we can
    re-import."""
    body = _pocketed_and_filleted()
    shelled = shell_body(body, _top_face(body), _THICKNESS).solids()[0]
    assert _valid(shelled)
    assert shelled.volume < body.volume
