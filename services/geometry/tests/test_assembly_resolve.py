"""Mate-geometry-ref resolution against REAL OCCT bodies (design ``assemblies.md``
§2.1, §4 step 2) — the item #3 seam.

This is where the assemblies pillar first touches real geometry: item #2 proved
the solver math on SYNTHETIC ``(point, normal)`` / ``(point, direction)`` pairs;
here those pairs are derived from real evaluated part bodies via the SAME stage-1
signature resolvers the ``on_face`` datum (faces) and fillet/chamfer picks
(edges) already use, then fed through the shipped ``AssemblySolver``.

The HEADLINE test is the first real bolted solve: two plates each with two holes,
authored placements, a ``coincident`` (mating faces) + two ``concentric`` (hole
axes) resolved into an :class:`AssemblySolveInput` and solved — asserting the
free plate lands at the analytically-known bolted pose (faces flush, hole axes
collinear). Two holes fully locate the joint (a single bolt would leave the spin
DOF; design §2.2, the #2 author's note), so the solve is ``well_constrained``.

Tolerances are the documented per-model :data:`RESOLVE_TOL`, never ad-hoc inline
epsilons (CLAUDE.md geometry conventions): a box + cylindrical hole is B-rep
exact in OCCT, so residuals are round-off only.

The OCP wheel ships no type stubs, so the raw ``BRepAdaptor_Curve`` / ``gp_Pnt``
calls used to locate a hole rim are opaque to pyright; the directives scope that
relaxation to this test only (matching the kernel modules it exercises), and the
fully-typed resolved-geometry / solve-result DTOs keep the assertions honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import struct
import uuid

import numpy as np
import pytest
from build123d import GeomType, Location, Solid
from geometry.assembly import (
    AssemblyDefinitionError,
    AssemblySolveResult,
    ResolvableInstance,
    ResolvableMate,
    ResolvedAxis,
    ResolvedFace,
    RigidBodyAssemblySolver,
    build_assembly_solve_input,
    resolve_mate_geometry,
)
from geometry.assembly.transform import Pose
from geometry.kernel.edges import edge_signature_dto
from geometry.kernel.faces import face_signature_dto, planar_faces
from OCP.BRepAdaptor import BRepAdaptor_Curve
from py_kit.schemas.assemblies import (
    CoincidentMate,
    ConcentricMate,
    MateAxisRef,
    MateFaceRef,
    Placement,
    Quat,
)
from py_kit.schemas.features import EdgeSignature, PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

#: Per-model resolution/solve tolerance (mm for positions, dimensionless for
#: normals / quaternion components). B-rep exact geometry → round-off residuals;
#: the numeric solve converges well below this. Documented once, used throughout.
RESOLVE_TOL = 1e-6

SOLVER = RigidBodyAssemblySolver()

# --- the real part: a plate with two through-holes ------------------------------

_HOLE_R = 2.5
_HOLE_1 = (10.0, 10.0)
_HOLE_2 = (30.0, 10.0)
_PLATE = (40.0, 20.0, 5.0)  # x, y, z (thickness)


def plate_with_holes() -> Solid:
    """A 40x20x5 plate (corner at origin) with two vertical Ø5 through-holes at
    (10, 10) and (30, 10) — the canonical bolted-plate part, in LOCAL frame."""
    body = Solid.make_box(*_PLATE)
    for cx, cy in (_HOLE_1, _HOLE_2):
        drill = Solid.make_cylinder(_HOLE_R, _PLATE[2] + 2.0).located(
            Location((cx, cy, -1.0))
        )
        body = body.cut(drill)
    # A box minus vertical through-cylinders is a single solid (never a compound).
    assert isinstance(body, Solid)
    return body


def _face_sig_by_normal(body: Solid, nz: float) -> PlanarFaceSignature:
    """The signature of the planar face whose outward normal is ~ (0, 0, ``nz``).

    Captured with the pick-side ``face_signature_dto`` — byte-for-byte what the
    selection overlay hands a client, so the resolver matches the same face."""
    for record in planar_faces(body):
        sig = record.signature
        if abs(sig.normal.z - nz) < RESOLVE_TOL and abs(sig.normal.x) < RESOLVE_TOL:
            got = face_signature_dto(record.face)
            assert got is not None
            return got
    raise AssertionError(f"no planar face with normal z ~ {nz}")


def _circle_centre(edge: object) -> tuple[float, float, float]:
    loc = BRepAdaptor_Curve(edge.wrapped).Circle().Location()
    return (float(loc.X()), float(loc.Y()), float(loc.Z()))


def _hole_rim_sig(body: Solid, cx: float, cy: float, cz: float) -> EdgeSignature:
    """The signature of the circular hole-rim edge centred at ``(cx, cy, cz)``.

    Captured with the pick-side ``edge_signature_dto`` — the same enumeration the
    resolver matches against (pick side == resolve side)."""
    for edge in body.edges():
        if edge.geom_type != GeomType.CIRCLE:
            continue
        gx, gy, gz = _circle_centre(edge)
        if (
            abs(gx - cx) < RESOLVE_TOL
            and abs(gy - cy) < RESOLVE_TOL
            and abs(gz - cz) < RESOLVE_TOL
        ):
            return edge_signature_dto(edge)
    raise AssertionError(f"no circular edge centred at ({cx}, {cy}, {cz})")


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _placement(pos: tuple[float, float, float]) -> Placement:
    return Placement(position=Vec3(x=pos[0], y=pos[1], z=pos[2]))


# --- single-ref resolution ------------------------------------------------------


def test_resolve_top_face_gives_centroid_and_outward_normal() -> None:
    """A MateFaceRef for the plate's +Z top face resolves to a point ON the face
    (its area centroid) and the OUTWARD unit normal (+Z) — the sign the
    coincident residual's `flush` expects (design §2.3)."""
    body = plate_with_holes()
    ref = MateFaceRef(instance_id=iid(1), signature=_face_sig_by_normal(body, 1.0))

    resolved = resolve_mate_geometry(body, ref)

    assert isinstance(resolved, ResolvedFace)
    # top face centroid: plate midpoint in x/y (holes are symmetric), z = thickness
    assert resolved.point.x == pytest.approx(20.0, abs=RESOLVE_TOL)
    assert resolved.point.y == pytest.approx(10.0, abs=RESOLVE_TOL)
    assert resolved.point.z == pytest.approx(5.0, abs=RESOLVE_TOL)
    assert resolved.normal.x == pytest.approx(0.0, abs=RESOLVE_TOL)
    assert resolved.normal.y == pytest.approx(0.0, abs=RESOLVE_TOL)
    assert resolved.normal.z == pytest.approx(1.0, abs=RESOLVE_TOL)


def test_resolve_hole_edge_gives_centre_and_axis() -> None:
    """A MateAxisRef for a hole's top rim resolves to the circle CENTRE (a point
    on the axis line) and the axis unit direction (the circle normal, ~±Z)."""
    body = plate_with_holes()
    sig = _hole_rim_sig(body, _HOLE_1[0], _HOLE_1[1], 5.0)
    ref = MateAxisRef(instance_id=iid(1), signature=sig)

    resolved = resolve_mate_geometry(body, ref)

    assert isinstance(resolved, ResolvedAxis)
    assert resolved.point.x == pytest.approx(_HOLE_1[0], abs=RESOLVE_TOL)
    assert resolved.point.y == pytest.approx(_HOLE_1[1], abs=RESOLVE_TOL)
    assert resolved.point.z == pytest.approx(5.0, abs=RESOLVE_TOL)
    # the axis is the circle normal — vertical, unit length (sign is seed-resolved)
    assert abs(resolved.direction.z) == pytest.approx(1.0, abs=RESOLVE_TOL)
    assert resolved.direction.x == pytest.approx(0.0, abs=RESOLVE_TOL)
    assert resolved.direction.y == pytest.approx(0.0, abs=RESOLVE_TOL)


# --- the headline: first real bolted solve --------------------------------------


def _bolted_problem() -> tuple[
    list[ResolvableInstance], list[ResolvableMate], Placement
]:
    """Two plates: A grounded at identity, B seeded displaced. A coincident
    (A-top ↔ B-bottom, flush) + two concentric (both holes) resolved from the
    REAL bodies. Analytic target for B: lifted +5 mm (bottom flush on A's top),
    no rotation, holes collinear."""
    body = plate_with_holes()

    top_sig = _face_sig_by_normal(body, 1.0)  # A's top face (+Z)
    bottom_sig = _face_sig_by_normal(body, -1.0)  # B's bottom face (-Z)
    hole1_sig = _hole_rim_sig(body, _HOLE_1[0], _HOLE_1[1], 5.0)
    hole2_sig = _hole_rim_sig(body, _HOLE_2[0], _HOLE_2[1], 5.0)

    a_id, b_id = iid(1), iid(2)
    instances = [
        ResolvableInstance(
            instance_id=a_id,
            body=body,
            placement=_placement((0.0, 0.0, 0.0)),
            grounded=True,
        ),
        # Seeded displaced (and slightly rotated) so the solve does real work; on
        # the correct side (above A) so `flush` pulls to the intended solution.
        ResolvableInstance(
            instance_id=b_id,
            body=body,
            placement=Placement(
                position=Vec3(x=2.0, y=1.0, z=12.0),
                orientation=Quat(x=0.0, y=0.0, z=0.06, w=0.998),
            ),
            grounded=False,
        ),
    ]
    mates = [
        ResolvableMate(
            mate_id=iid(1001),
            order_index=0,
            mate=CoincidentMate(
                a=MateFaceRef(instance_id=a_id, signature=top_sig),
                b=MateFaceRef(instance_id=b_id, signature=bottom_sig),
                flush=True,
            ),
        ),
        ResolvableMate(
            mate_id=iid(1002),
            order_index=1,
            mate=ConcentricMate(
                a=MateAxisRef(instance_id=a_id, signature=hole1_sig),
                b=MateAxisRef(instance_id=b_id, signature=hole1_sig),
            ),
        ),
        ResolvableMate(
            mate_id=iid(1003),
            order_index=2,
            mate=ConcentricMate(
                a=MateAxisRef(instance_id=a_id, signature=hole2_sig),
                b=MateAxisRef(instance_id=b_id, signature=hole2_sig),
            ),
        ),
    ]
    # Analytic target: B lifted so its bottom (local z=0) sits on A's top (z=5),
    # holes vertically aligned, no rotation.
    b_target = _placement((0.0, 0.0, 5.0))
    return instances, mates, b_target


def test_two_plates_bolt_together_at_the_analytic_pose() -> None:
    """The first real bolted solve: resolve coincident + two concentric from real
    bodies, solve, and land B at the hand-derived bolted pose (design §6.1)."""
    instances, mates, b_target = _bolted_problem()

    problem = build_assembly_solve_input(instances, mates)
    result = SOLVER.solve(problem)

    assert result.status == "well_constrained"
    assert result.diagnosis is None

    got = next(p.placement for p in result.placements if p.instance_id == iid(2))
    assert got.position.x == pytest.approx(b_target.position.x, abs=RESOLVE_TOL)
    assert got.position.y == pytest.approx(b_target.position.y, abs=RESOLVE_TOL)
    assert got.position.z == pytest.approx(b_target.position.z, abs=RESOLVE_TOL)
    # No rotation: the solved rotation matrix is the identity (immune to ±q).
    got_r = Pose.from_placement(got).matrix()
    assert got_r == pytest.approx(Pose.identity().matrix(), abs=RESOLVE_TOL)

    # Grounded A is untouched at its seed (identity).
    got_a = next(p.placement for p in result.placements if p.instance_id == iid(1))
    assert got_a.position.z == pytest.approx(0.0, abs=RESOLVE_TOL)


def test_bolted_faces_are_flush_and_axes_collinear() -> None:
    """The solved pose is physically a bolt: A's top and B's bottom faces are
    coplanar (flush) and each hole pair's axes are collinear."""
    instances, mates, _ = _bolted_problem()
    result = SOLVER.solve(build_assembly_solve_input(instances, mates))
    b_pose = Pose.from_placement(
        next(p.placement for p in result.placements if p.instance_id == iid(2))
    )

    body = plate_with_holes()
    # B's bottom face resolved locally, lifted to world by the solved pose.
    b_bottom = resolve_mate_geometry(
        body, MateFaceRef(instance_id=iid(2), signature=_face_sig_by_normal(body, -1.0))
    )
    assert isinstance(b_bottom, ResolvedFace)
    world_pt = b_pose.apply_point(
        np.array([b_bottom.point.x, b_bottom.point.y, b_bottom.point.z])
    )
    # A's top face sits at z = 5; B's bottom face is flush against it.
    assert world_pt[2] == pytest.approx(5.0, abs=RESOLVE_TOL)


# --- determinism (RESEARCH §9) --------------------------------------------------


def _pack(result: AssemblySolveResult) -> bytes:
    buf = bytearray()
    for p in result.placements:
        pl = p.placement
        for value in (
            pl.position.x,
            pl.position.y,
            pl.position.z,
            pl.orientation.x,
            pl.orientation.y,
            pl.orientation.z,
            pl.orientation.w,
        ):
            buf += struct.pack("<d", value)
    return bytes(buf)


def test_resolve_and_solve_is_deterministic() -> None:
    """Resolve + solve twice (fresh solver instances) → byte-identical placements
    (RESEARCH §9): resolution is a pure function of the body, the solve is pinned."""
    instances, mates, _ = _bolted_problem()
    first = _pack(
        RigidBodyAssemblySolver().solve(build_assembly_solve_input(instances, mates))
    )
    second = _pack(
        RigidBodyAssemblySolver().solve(build_assembly_solve_input(instances, mates))
    )
    assert first == second


# --- clean errors (exactly-one-or-honest-error posture) -------------------------


def test_stale_face_signature_is_assembly_definition_error() -> None:
    """A face signature no face matches (wrong centroid) is a clean error, never a
    wrong face or a crash (the 'no longer exists after rebuild' path)."""
    body = plate_with_holes()
    stale = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=20.0, y=10.0, z=99.0),  # no face at z=99
        area_mm2=760.7,
    )
    with pytest.raises(AssemblyDefinitionError):
        resolve_mate_geometry(body, MateFaceRef(instance_id=iid(1), signature=stale))


def test_stale_axis_signature_is_assembly_definition_error() -> None:
    body = plate_with_holes()
    stale = EdgeSignature(
        curve="circle",
        end_a=Vec3(x=12.5, y=10.0, z=99.0),
        end_b=Vec3(x=12.5, y=10.0, z=99.0),
        midpoint=Vec3(x=7.5, y=10.0, z=99.0),
        length_mm=2 * 3.141592653589793 * _HOLE_R,
    )
    with pytest.raises(AssemblyDefinitionError):
        resolve_mate_geometry(body, MateAxisRef(instance_id=iid(1), signature=stale))


def test_ambiguous_axis_signature_is_assembly_definition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two edges matching one signature (a coincident boolean seam / non-manifold
    twin) is refused as ambiguous → a clean AssemblyDefinitionError, never a
    guess. The tie is forced through the shared enumeration, as in test_edges."""
    from geometry.kernel.edges import EdgeRecord

    body = plate_with_holes()
    sig = _hole_rim_sig(body, _HOLE_1[0], _HOLE_1[1], 5.0)
    circle_edge = next(e for e in body.edges() if e.geom_type == GeomType.CIRCLE)
    twin = EdgeRecord(index=0, signature=sig, edge=circle_edge)

    def _two_matching(_body: Solid) -> list[EdgeRecord]:
        return [twin, twin]

    monkeypatch.setattr("geometry.kernel.edges.enumerate_edges", _two_matching)
    with pytest.raises(AssemblyDefinitionError):
        resolve_mate_geometry(body, MateAxisRef(instance_id=iid(1), signature=sig))


def test_non_circular_axis_edge_is_legible_error() -> None:
    """A MateAxisRef whose signature names a straight (line) edge resolves the
    edge but rejects it: a v1 axis mate requires a circular edge (design §2.1)."""
    body = plate_with_holes()
    # a straight top edge of the plate at y=0, z=5, length 40 (curve == 'line')
    line_edge = next(
        e
        for e in body.edges()
        if e.geom_type == GeomType.LINE
        and abs((e @ 0.5).Z - 5.0) < RESOLVE_TOL
        and abs((e @ 0.5).Y) < RESOLVE_TOL
    )
    ref = MateAxisRef(instance_id=iid(1), signature=edge_signature_dto(line_edge))
    with pytest.raises(AssemblyDefinitionError, match="not a circle"):
        resolve_mate_geometry(body, ref)


def test_mate_referencing_unknown_instance_is_assembly_definition_error() -> None:
    """A mate slot naming an instance absent from the assembly is malformed input
    → a clean error before any solve (design §4 step 2)."""
    body = plate_with_holes()
    top_sig = _face_sig_by_normal(body, 1.0)
    bottom_sig = _face_sig_by_normal(body, -1.0)
    instances = [
        ResolvableInstance(
            instance_id=iid(1),
            body=body,
            placement=_placement((0.0, 0.0, 0.0)),
            grounded=True,
        )
    ]
    mates = [
        ResolvableMate(
            mate_id=iid(1001),
            order_index=0,
            mate=CoincidentMate(
                a=MateFaceRef(instance_id=iid(1), signature=top_sig),
                b=MateFaceRef(instance_id=iid(99), signature=bottom_sig),  # unknown
                flush=True,
            ),
        )
    ]
    with pytest.raises(AssemblyDefinitionError):
        build_assembly_solve_input(instances, mates)


def test_duplicate_instance_id_is_assembly_definition_error() -> None:
    body = plate_with_holes()
    inst = ResolvableInstance(
        instance_id=iid(1),
        body=body,
        placement=_placement((0.0, 0.0, 0.0)),
        grounded=True,
    )
    with pytest.raises(AssemblyDefinitionError):
        build_assembly_solve_input([inst, inst], [])
