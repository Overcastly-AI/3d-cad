"""Sketch closed profile + path wire → swept solid → boolean.

The kernel half of the sweep feature (feature-tree design §4.3; BACKLOG #7) —
the first NON-PRISMATIC body-affecting feature. The feature layer hands in the
*solved* sketch entities (pydantic DTOs from :mod:`loft_wire.sketch`) of a
CLOSED profile plus a SECOND, OPEN path sketch and its datum plane; this module
owns every OCCT/build123d call. Failures raise the typed exceptions below with
**sanitized messages** (no kernel internals) — the feature layer maps them 1:1
onto ``FeatureError`` codes so geometry outcomes stay values at the boundary.

The profile is built by the SHARED
:func:`geometry.kernel.extrude.build_profile_face` (construction geometry
excluded there, the single profile-exclusion point) and the ``add``/``cut``
boolean is the SHARED :func:`geometry.kernel.extrude.combine_body`; the path
wire is assembled here from the SAME per-entity edge builder the profile uses
(``entity_edges`` — one edge-construction point, CLAUDE.md DRY rule), so a
sweep path and an extrude profile can never disagree on how a sketch entity
becomes a kernel edge. Sweep owns only the open-path assembly and the
sweep-along-path step.

Path contract (v1 DESIGN DECISION, docs/design/feature-tree.md §2.1/§2.2): the
path is a whole earlier SKETCH feature (referenced by id at the feature layer)
whose entities
form a single wire — never a picked sub-edge, so this is independent of
topological naming (#1). Construction geometry is excluded from the path exactly
as it is from the profile. Disjoint loops (:class:`PathNotConnectedError`) or a
path with no curve entities (:class:`PathEmptyError`) are rejected up front. An
OPEN path is anchored at the profile: build123d applies the path as a relative
trajectory from the profile's location (its absolute position is unused in v1).
A CLOSED path (SWEEP-CLOSED-PATH) must be tangent-continuous at every joint
(:class:`~geometry.kernel.sweep_closed.PathCornerError` otherwise) and sweeps
through :func:`~geometry.kernel.sweep_closed.sweep_closed_profile`.

Determinism (RESEARCH §9): path edges are built in entity list order, wire
assembly is a pure OCCT algorithm on identical inputs, and the sweep + boolean
are pure functions of their inputs — no unordered iteration participates.
"""

from collections.abc import Sequence

from build123d import Face, Plane, Solid, Wire
from loft_wire.sketch import SketchEntity

from geometry.kernel.extrude import (
    PROFILE_WIRE_TOLERANCE,
    entity_edges,
)
from geometry.kernel.healing import clean_shape
from geometry.kernel.sweep_check import check_not_self_intersecting
from geometry.kernel.sweep_closed import (
    ClosedSweepError,
    check_closed_path_tangent,
    sweep_closed_profile,
)


class PathEmptyError(ValueError):
    """The path sketch has no curve entities (only construction/points); there
    is no trajectory to sweep along."""


class PathNotConnectedError(ValueError):
    """The path entities form more than one disjoint wire; a sweep path is a
    single connected chain in v1."""


class SweepError(RuntimeError):
    """The OCCT sweep failed or produced an unsupported result (e.g. a path
    corner tighter than the profile, sweeping material through itself)."""


def build_path_wire(plane: Plane, entities: Sequence[SketchEntity]) -> Wire:
    """Assemble a path sketch's solved entities into a single wire.

    The path sibling of :func:`geometry.kernel.extrude.build_profile_face`:
    it collects edges through the SAME per-entity builder (construction geometry
    excluded, input order preserved for determinism) but requires the result to
    be exactly one chain — the sweep trajectory, open or closed. A closed chain
    must be tangent-continuous at every joint. *plane* is the resolved sketch
    plane (origin datum or offset ``datum`` feature).

    Raises:
        PathEmptyError: no curve entities (only construction geometry/points).
        PathNotConnectedError: the edges form more than one disjoint wire.
        PathCornerError: the wire is closed and a joint is not G1 (it names
            the joint).
    """
    edges = [
        edge
        for entity in entities
        if not entity.construction
        for edge in entity_edges(plane, entity)
    ]
    if not edges:
        raise PathEmptyError(
            "Path sketch contains no curve entities (only construction geometry "
            "and/or points); there is no trajectory to sweep along."
        )

    wires = Wire.combine(edges, tol=PROFILE_WIRE_TOLERANCE)
    if len(wires) > 1:
        raise PathNotConnectedError(
            f"Path sketch forms {len(wires)} separate wires; a sweep path is a "
            "single connected chain."
        )
    wire = wires[0]
    if wire.is_closed:
        check_closed_path_tangent(plane, entities)
    return wire


def sweep_profile(face: Face, path: Wire, path_plane: Plane) -> Solid:
    """Sweep the closed profile *face* along the *path* wire.

    An open path is anchored at the profile (build123d applies *path* as a
    relative trajectory from the profile's location — its absolute position is
    unused). A closed path sweeps once around the loop, seated where it passes
    nearest the profile, with *path_plane*'s normal as the fixed binormal
    (:func:`~geometry.kernel.sweep_closed.sweep_closed_profile`). ``clean()``
    collapses the redundant seams the operation leaves behind, keeping topology
    counts meaningful (and golden-assertable).

    Raises:
        SweepError: the OCCT sweep failed or left other than exactly one solid
            (single body chain per part in v1, design §7.6) — e.g. a path corner
            tighter than the profile, sweeping material through itself.
        SweepSelfIntersectingError: the swept solid passes through itself (a
            path that crosses itself); the feature layer's
            ``sweep_self_intersecting``.
    """
    if path.is_closed:
        try:
            return sweep_closed_profile(face, path, path_plane.z_dir)
        except ClosedSweepError as exc:
            raise SweepError(str(exc)) from exc
    try:
        result = Solid.sweep(face, path)
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise SweepError(
            f"Sweep failed in the kernel ({type(exc).__name__}); the path may "
            "self-intersect or turn tighter than the profile can follow."
        ) from exc

    if len(solids) != 1:
        raise SweepError(
            f"Sweep produced {len(solids)} solids; parts are a single body in "
            "v1 (design §7.6)."
        )
    check_not_self_intersecting(solids[0])
    return clean_shape(solids[0])
