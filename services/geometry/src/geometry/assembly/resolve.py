"""Mate-geometry-ref resolution — the item #3 seam (design ``assemblies.md``
§2.1, §4 step 2).

Item #2 proved the solver numerics against SYNTHETIC resolved geometry; this
module derives that same resolved geometry from REAL evaluated OCCT part bodies,
so the ``(point, normal)`` / ``(point, direction)`` pairs handed to
:class:`~geometry.assembly.protocol.SolverMate.geometry` come from the kernel,
not a test fixture. It reuses — never reimplements — the stage-1 signature
resolvers topological naming already ships:

- a :class:`~py_kit.schemas.assemblies.MateFaceRef` resolves through
  :func:`geometry.kernel.faces.resolve_face_plane` (the SAME machinery an
  ``on_face`` datum uses): the matched planar face's area centroid is a point ON
  the face and its deterministic plane's ``z_dir`` is the OUTWARD unit normal —
  the sign convention the solver's ``coincident`` residual expects (``flush`` ⇒
  ``n_a + n_b = 0``, the two outward normals anti-parallel, design §2.3).
- a :class:`~py_kit.schemas.assemblies.MateAxisRef` (``curve == "circle"``)
  resolves through :func:`geometry.kernel.edges.resolve_edge`, then the circle's
  centre and axis direction come from the exact B-rep (``BRepAdaptor_Curve`` →
  ``gp_Circ``) — a hole rim or a shaft rim. The centre lies ON the axis line and
  the axis direction is the circle's normal, which is what ``concentric`` needs
  (its ± sense is resolved by the seed inside the solver, design §2.2).

All resolved geometry is in the instance's LOCAL part frame (the part body is
evaluated in its own frame); the solver transforms it to world by the instance's
pose for residual evaluation (design §2.3).

**Error posture — exactly-one-or-honest-error, mirroring the sketch/subshape
resolvers (§4 step 2).** A stale/ambiguous signature (zero or multiple matching
faces/edges), a non-circular edge where an axis is expected, or a ref to an
instance absent from the assembly is a malformed *input* — a clean
:class:`~geometry.assembly.protocol.AssemblyDefinitionError` (the solver's
exception-vs-status contract), never a crash or a wrong resolution. The
originating subshape error is chained (``from``) so a later evaluation layer (#5)
can still map it onto a per-mate ``subshape_unresolved`` / ``subshape_ambiguous``
code by inspecting ``__cause__``. A ``MateFaceRef`` carries a
``PlanarFaceSignature`` which is planar-only by construction, so a non-planar
face simply resolves to zero matches (an honest unresolved), never a wrong plane.

Determinism (RESEARCH §9): every routine is a pure function of the body — the
signature resolvers filter a deterministic enumeration, and the ``gp_Circ``
extraction is a fixed B-rep query — so the same body + ref yields identical
resolved geometry, and :func:`build_assembly_solve_input` emits mates in
``(order_index, mate_id)`` order regardless of input order.

The OCP wheel ships no type stubs, so the raw ``BRepAdaptor_Curve`` / ``gp_Circ``
calls are opaque to pyright; the directives scope that relaxation to this file
only, and the fully-typed resolved-geometry DTOs keep the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from build123d import GeomType, Solid, Vector
from OCP.BRepAdaptor import BRepAdaptor_Curve
from py_kit.schemas.assemblies import (
    LockMate,
    MateAxisRef,
    MateFaceRef,
    MateGeometryRef,
    MateParams,
    Placement,
    mate_instance_ids,
)
from py_kit.schemas.geometry import Vec3

from geometry.assembly.protocol import (
    AssemblyDefinitionError,
    AssemblySolveInput,
    ResolvedAxis,
    ResolvedFace,
    ResolvedMateGeometry,
    SolverInstance,
    SolverMate,
)
from geometry.kernel.edges import resolve_edge
from geometry.kernel.faces import (
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    resolve_face_plane,
)

# The stage-1 resolvers raise exactly these two on a zero/multiple match; both
# become AssemblyDefinitionError at this boundary (the solver's malformed-input
# contract), chaining the original so #5 can still recover the specific code.
_SUBSHAPE_ERRORS = (SubshapeUnresolvedError, SubshapeAmbiguousError)


@dataclass(frozen=True)
class ResolvableInstance:
    """One assembly instance as the resolver sees it: identity, its evaluated
    part BODY (a kernel solid, LOCAL frame), authored seed pose, grounded flag.

    Kernel-internal — the ``body`` is a ``Solid`` and never crosses the service
    boundary (CLAUDE.md). The caller (evaluation #5) evaluates each unique part
    once and hands the same body to every instance of that part.
    """

    instance_id: uuid.UUID
    body: Solid
    placement: Placement
    grounded: bool = False


@dataclass(frozen=True)
class ResolvableMate:
    """One authored mate plus the persisted-row identity the solver needs.

    ``order_index`` fixes the deterministic processing order and ``mate_id``
    names the mate in diagnosis — both come from the persisted mate row (design
    §1.5). ``mate`` is the validated discriminated union member.
    """

    mate_id: uuid.UUID
    order_index: int
    mate: MateParams


def _vec3(vector: Vector) -> Vec3:
    """A build123d ``Vector`` (instance-local mm) as a boundary :class:`Vec3`."""
    return Vec3(x=float(vector.X), y=float(vector.Y), z=float(vector.Z))


def _resolve_face(body: Solid, ref: MateFaceRef) -> ResolvedFace:
    """Resolve a planar-face ref to ``(centroid point, outward unit normal)``.

    Delegates to the ``on_face`` datum's :func:`resolve_face_plane` (offset 0):
    the resolved plane's origin is the face area centroid (a point on the face)
    and its ``z_dir`` is the outward face normal (the sign the ``coincident``
    residual's ``flush`` expects). Exactly-one-or-error is enforced by the
    resolver; a zero/multiple match becomes :class:`AssemblyDefinitionError`.
    """
    try:
        plane = resolve_face_plane(body, ref.signature, 0.0)
    except _SUBSHAPE_ERRORS as exc:
        raise AssemblyDefinitionError(
            f"mate face ref for instance {ref.instance_id} did not resolve to "
            f"exactly one planar face: {exc}"
        ) from exc
    return ResolvedFace(point=_vec3(plane.origin), normal=_vec3(plane.z_dir))


def _resolve_axis(body: Solid, ref: MateAxisRef) -> ResolvedAxis:
    """Resolve a circular-edge ref to ``(circle centre, axis unit direction)``.

    Resolves the edge with :func:`resolve_edge` (exactly-one-or-error), then
    requires it be a CIRCLE and reads the centre + axis direction from the exact
    B-rep (``BRepAdaptor_Curve`` → ``gp_Circ``). The centre lies on the axis line
    and the axis direction is the circle's normal — the ``concentric`` residual
    resolves the ± sense from the seed pose (design §2.2). A non-circular edge is
    a legible :class:`AssemblyDefinitionError`, never a wrong axis.
    """
    try:
        edge = resolve_edge(body, ref.signature)
    except _SUBSHAPE_ERRORS as exc:
        raise AssemblyDefinitionError(
            f"mate axis ref for instance {ref.instance_id} did not resolve to "
            f"exactly one edge: {exc}"
        ) from exc
    if edge.geom_type != GeomType.CIRCLE:
        raise AssemblyDefinitionError(
            f"mate axis ref for instance {ref.instance_id} resolved to a "
            f"{edge.geom_type.name.lower()} edge, not a circle; a v1 axis mate "
            "requires a circular edge (a hole/shaft rim)"
        )
    circle = BRepAdaptor_Curve(edge.wrapped).Circle()
    centre = circle.Location()
    direction = circle.Axis().Direction()
    return ResolvedAxis(
        point=Vec3(x=centre.X(), y=centre.Y(), z=centre.Z()),
        direction=Vec3(x=direction.X(), y=direction.Y(), z=direction.Z()),
    )


def resolve_mate_geometry(body: Solid, ref: MateGeometryRef) -> ResolvedMateGeometry:
    """Resolve one :class:`MateGeometryRef` against a part body (LOCAL frame).

    A :class:`MateFaceRef` → :class:`ResolvedFace`; a :class:`MateAxisRef` →
    :class:`ResolvedAxis`. The single entry point #4/#5 call per mate slot.
    """
    if isinstance(ref, MateFaceRef):
        return _resolve_face(body, ref)
    return _resolve_axis(body, ref)


def _body_for(ref: MateGeometryRef, body_of: dict[uuid.UUID, Solid]) -> Solid:
    """The evaluated body of the instance a ref names, or a clean error.

    A ref to an instance absent from the assembly is malformed input — an
    :class:`AssemblyDefinitionError`, never a crash (design §4 step 2).
    """
    body = body_of.get(ref.instance_id)
    if body is None:
        raise AssemblyDefinitionError(
            f"mate references unknown instance {ref.instance_id}"
        )
    return body


def _resolve_mate_pair(
    mate: MateParams, body_of: dict[uuid.UUID, Solid]
) -> tuple[ResolvedMateGeometry, ResolvedMateGeometry] | None:
    """Resolve a mate's ``a``/``b`` slots into the solver's geometry pair.

    ``lock`` names instances directly (no picked geometry) and derives its
    target relative pose from the seeds inside the solver, so its geometry is
    ``None`` — but its two instances are still membership-checked here. Every
    other mate resolves both geometry-ref slots against the correct instance's
    body, in ``(a, b)`` order (the slot order the solver's residual expects).
    """
    if isinstance(mate, LockMate):
        for instance_id in mate_instance_ids(mate):
            if instance_id not in body_of:
                raise AssemblyDefinitionError(
                    f"lock mate references unknown instance {instance_id}"
                )
        return None
    return (
        resolve_mate_geometry(_body_for(mate.a, body_of), mate.a),
        resolve_mate_geometry(_body_for(mate.b, body_of), mate.b),
    )


def build_assembly_solve_input(
    instances: Sequence[ResolvableInstance],
    mates: Sequence[ResolvableMate],
) -> AssemblySolveInput:
    """Assemble the full :class:`AssemblySolveInput` from evaluated bodies + mates.

    Resolves every mate's ``a``/``b`` refs against the correct instance's part
    body (by ``instance_id``) into :class:`SolverMate.geometry` pairs, leaving
    ``lock`` mates' geometry ``None``. Mates are emitted in ``(order_index,
    mate_id)`` order so the output is deterministic regardless of input order
    (RESEARCH §9); the solver re-sorts by the same key.

    Raises:
        AssemblyDefinitionError: a duplicate instance id, a ref to an instance
            not in the assembly, a stale/ambiguous signature, or a non-circular
            edge where an axis is expected (design §4 step 2).
    """
    body_of: dict[uuid.UUID, Solid] = {}
    for inst in instances:
        if inst.instance_id in body_of:
            raise AssemblyDefinitionError(f"duplicate instance id {inst.instance_id}")
        body_of[inst.instance_id] = inst.body

    solver_instances = [
        SolverInstance(
            instance_id=inst.instance_id,
            grounded=inst.grounded,
            placement=inst.placement,
        )
        for inst in instances
    ]

    ordered = sorted(mates, key=lambda m: (m.order_index, str(m.mate_id)))
    solver_mates = [
        SolverMate(
            mate_id=m.mate_id,
            order_index=m.order_index,
            mate=m.mate,
            geometry=_resolve_mate_pair(m.mate, body_of),
        )
        for m in ordered
    ]
    return AssemblySolveInput(instances=solver_instances, mates=solver_mates)
