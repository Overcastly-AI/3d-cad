"""B-rep healing (CM-4) — a shelled body is CONFORMAL before it ever leaves.

The gate that CM-4's STEP round-trip rides on lives in
``test_composition_matrix.py``; this module pins the kernel contract underneath
it (``geometry.kernel.healing``), so a regression names the cause instead of
surfacing three layers up as "the round-trip gained two edges":

* a ``BRepCheck``-valid solid comes back UNTOUCHED (identity) — every golden
  body takes that path, so their topology and byte-identical exports are
  unaffected by the heal existing;
* the pinched-cavity shell (the CM-4 fixture, built here from raw kernel ops)
  is INVALID out of OCCT and VALID out of :func:`conform_solid`;
* healing does NOT remove the zero-width slit that sits under that T-junction
  (finding SH-1), which is why :func:`shell_body` REFUSES this thickness rather
  than shipping the healed body — the boundary between the two modules, asserted
  here so neither can quietly move;
* healing preserves material — asserted against
  :data:`~geometry.kernel.healing.CONFORM_VOLUME_TOL_MM3`, the planar golden
  tier, never an ad-hoc epsilon — and is deterministic + idempotent (RESEARCH §9).

The second half of the module is CM-6 (docs/GEOMETRY-QA.md 2026-07-30, filed as
QA-1): the SIMPLIFICATION guard :func:`~geometry.kernel.healing.clean_shape` and
the validity predicate :func:`~geometry.kernel.healing.body_is_valid`. Same
posture — the end-to-end gate is a golden plus the composition matrix, and these
pin the kernel contract underneath so a regression names the cause instead of
reading as "the mirror golden lost 1072 mm^3".

The OCP wheel ships no type stubs, so the raw ``BRepCheck_Analyzer`` probe is
opaque to pyright; the directives scope that relaxation to this file (the same
posture :mod:`geometry.kernel.healing` itself takes).
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false

import math

import pytest
from build123d import Axis, Face, Plane, Solid, Vector
from geometry.kernel.degenerate import find_zero_width_slits
from geometry.kernel.healing import (
    CONFORM_VOLUME_TOL_MM3,
    body_is_valid,
    clean_shape,
    conform_solid,
)
from geometry.kernel.shell import ShellThicknessError, shell_body
from geometry.kernel.types import BodyShape
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


def test_healing_does_not_remove_the_zero_width_slit() -> None:
    """The boundary between healing and REFUSING (finding SH-1) — the assertion
    that keeps this module and :mod:`geometry.kernel.degenerate` from fighting.

    Under CM-4's T-junction the same body carries a zero-width slit: the pinched
    cavity's two coincident faces, with no material between them. ``ShapeFix``
    repairs topology, not missing material, so the slit SURVIVES the heal — which
    is why ``shell_body`` refuses the body instead of shipping the healed one. If
    a future OCCT/ShapeFix ever does remove it, this test fails and the refusal
    becomes reviewable (we would then prefer healing to refusing)."""
    raw = _raw_hollow(_pocketed_and_filleted())
    assert find_zero_width_slits(raw), "the CM-4 fixture is no longer pinched"
    healed = conform_solid(raw)
    assert _valid(healed)
    assert find_zero_width_slits(healed), (
        "ShapeFix removed the zero-width slit; shell_body's refusal (SH-1) should "
        "be revisited in favour of healing"
    )


def test_shell_body_refuses_the_pinched_shell_rather_than_healing_it() -> None:
    """SH-1: the pinched thickness is a typed feature error, not a cracked body.

    Replaces the pre-SH-1 assertion that ``shell_body`` returns a VALID solid for
    this input — it did (the heal made it conformal) but the returned body still
    contained the slit. The valid-output contract now rides the SOUND neighbour
    (0.1 mm thinner), which is also this module's proof that the guard
    discriminates rather than blanket-refusing the layout."""
    body = _pocketed_and_filleted()
    with pytest.raises(ShellThicknessError, match="zero-width slit"):
        shell_body(body, _top_face(body), _THICKNESS)

    sound = shell_body(body, _top_face(body), _THICKNESS - 0.1).solids()[0]
    assert _valid(sound)
    assert not find_zero_width_slits(sound)
    assert sound.volume < body.volume


# =================================================================================
# CM-6 — the simplification guard and the validity predicate (QA-1, 2026-07-30)
# =================================================================================

#: The CM-6 chain, kernel-level and provenance-exact: a 40x40x10 block with a
#: REVOLVED annular groove (r4..r8, z 2..10) whose axis sits at x=8, so the
#: groove's outer wall is exactly TANGENT to the block's own x=0 wall, mirrored
#: about the XZ plane the groove straddles. Both halves of that description are
#: load-bearing and were measured, not assumed:
#:
#: * move the axis to x=8.5 (or anywhere clear of the wall) and ``clean()`` is
#:   well-behaved — the mirrored body comes back at the same analytic volume with
#:   10 faces / 18 edges. The trigger is the tangency, NOT "a void that straddles
#:   the mirror plane" as the QA report's title read;
#: * build the same ring from two PRIMITIVE cylinders instead of a revolve and
#:   ``clean()`` is a no-op on the fused body (30793.6284, valid, 12 faces). The
#:   revolve's periodic/seamed faces are what the simplifier chokes on.
_CM6_BLOCK = (40.0, 40.0, 10.0)
_CM6_AXIS_X = 8.0
_CM6_RING = (4.0, 8.0, 2.0, 10.0)  # inner r, outer r, z0, z1

#: 32000 - pi * (8^2 - 4^2) * 8 — the block, doubled by the mirror, less the WHOLE
#: ring (half of which the mirror brings back into the material). Hand-derived; the
#: welded answer is 31865.9587, so this discriminates by 1072.330 mm^3.
_CM6_VOLUME = 32000.0 - math.pi * 384.0

#: Curved-geometry tolerance (the reviewed 1e-9 tier the revolve/sweep goldens
#: carry): two cylindrical walls go through GProp's Gauss quadrature. Measured
#: deviation on this body is 3.6e-12 mm^3.
_CM6_TOL = 1e-9


def _cm6_ring() -> Solid:
    """The REVOLVED annular groove tool (provenance matters — see _CM6_BLOCK)."""
    inner, outer, z0, z1 = _CM6_RING
    profile = Face.make_rect(
        z1 - z0,
        outer - inner,
        Plane(
            origin=(_CM6_AXIS_X + (inner + outer) / 2.0, 0.0, (z0 + z1) / 2.0),
            z_dir=(0.0, 1.0, 0.0),
        ),
    )
    box = profile.bounding_box()
    assert (_CM6_AXIS_X + inner, _CM6_AXIS_X + outer) == (box.min.X, box.max.X)
    assert (z0, z1) == (box.min.Z, box.max.Z)
    return Solid.revolve(  # pyright: ignore[reportUnknownMemberType]
        profile, 360.0, Axis((_CM6_AXIS_X, 0.0, 0.0), (0.0, 0.0, 1.0))
    ).solids()[0]


def _cm6_grooved_block() -> Solid:
    """The half body: block less the tangent revolved groove (a valid solid)."""
    return (Solid.make_box(*_CM6_BLOCK) - _cm6_ring()).solids()[0]


def _cm6_fused() -> BodyShape:
    """The mirrored-and-fused body, straight out of OCCT, BEFORE simplification."""
    body = _cm6_grooved_block()
    return body.fuse(body.mirror(Plane.XZ))


def test_clean_welds_the_tangent_groove_shut_out_of_occt() -> None:
    """CM-6's root cause, pinned at its source (the CM-4 fixture test's sibling).

    ``fuse`` is right and VALID; ``clean()`` then adds 1072.330 mm^3 — 3.48 % of a
    part — and leaves a body ``BRepCheck`` rejects, with the face count unchanged
    so nothing about the topology hints at it. If OCCT ever stops doing this, this
    test fails and :func:`clean_shape`'s rejection branch becomes dead code (which
    we then delete) — it must not silently stop being exercised.
    """
    fused = _cm6_fused()
    assert fused.volume == pytest.approx(_CM6_VOLUME, abs=_CM6_TOL)
    assert _valid(fused.solids()[0])

    welded = fused.clean()  # UNGUARDED — the raw build123d call
    assert welded.volume == pytest.approx(31865.958713446835, abs=_CM6_TOL), (
        "OCCT no longer welds the tangent groove shut; clean_shape's rejection "
        "branch is no longer exercised by this fixture"
    )
    assert not _valid(welded.solids()[0])


def test_clean_shape_discards_a_simplification_that_moves_material() -> None:
    """The guard: the same call through :func:`clean_shape` keeps the material.

    Returns the PRE-clean body — analytic volume, valid, and one redundant seam
    face (12, where a well-behaved clean would give 10) — which is the documented
    price of refusing the weld.
    """
    cleaned = clean_shape(_cm6_fused())
    assert cleaned.volume == pytest.approx(_CM6_VOLUME, abs=_CM6_TOL)
    solids = cleaned.solids()
    assert len(solids) == 1
    assert _valid(solids[0])
    assert len(cleaned.faces()) == 12


def test_clean_shape_keeps_a_well_behaved_simplification() -> None:
    """The other half — the guard must not become "never simplify".

    The SAME chain with the groove moved 0.5 mm clear of the block wall: no
    tangency, so ``clean()`` behaves and the guard returns the simplifier's own
    object, IDENTITY not a copy. That identity is what keeps every shipped
    golden's topology and export bytes unchanged by this guard existing — and it
    is the assertion that fails if the guard is ever "fixed" by never cleaning.
    """
    inner, outer, z0, z1 = _CM6_RING
    profile = Face.make_rect(
        z1 - z0,
        outer - inner,
        Plane(
            origin=(8.5 + (inner + outer) / 2.0, 0.0, (z0 + z1) / 2.0),
            z_dir=(0.0, 1.0, 0.0),
        ),
    )
    clear_ring = Solid.revolve(  # pyright: ignore[reportUnknownMemberType]
        profile, 360.0, Axis((8.5, 0.0, 0.0), (0.0, 0.0, 1.0))
    ).solids()[0]
    body = (Solid.make_box(*_CM6_BLOCK) - clear_ring).solids()[0]
    fused = body.fuse(body.mirror(Plane.XZ))

    cleaned = clean_shape(fused)
    assert cleaned is fused, "a well-behaved clean must take the identity path"
    assert cleaned.volume == pytest.approx(_CM6_VOLUME, abs=_CM6_TOL)
    assert len(cleaned.faces()) == 10
    assert _valid(cleaned.solids()[0])


def test_body_is_valid_discriminates() -> None:
    """The predicate the evaluator's body funnel asks: True for a sound body,
    False for the welded one. Asserted on both so it cannot degrade into a
    constant (a gate that always answers True is not a gate)."""
    assert body_is_valid(Solid.make_box(10.0, 20.0, 30.0))
    assert body_is_valid(_cm6_grooved_block())
    assert not body_is_valid(_cm6_fused().clean().solids()[0])
