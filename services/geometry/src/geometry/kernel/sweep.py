"""Sketch closed profile + open path wire → swept solid → boolean.

The kernel half of the sweep feature (feature-tree design §4.3; BACKLOG #7) —
the first NON-PRISMATIC body-affecting feature. The feature layer hands in the
*solved* sketch entities (pydantic DTOs from :mod:`py_kit.schemas.sketch`) of a
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
form a single OPEN wire — never a picked sub-edge, so this is independent of
topological naming (#1). Construction geometry is excluded from the path exactly
as it is from the profile. A closed path (:class:`PathClosedError`), disjoint
loops (:class:`PathNotConnectedError`), or a path with no curve entities
(:class:`PathEmptyError`) are rejected up front. The sweep is anchored at the
profile: build123d applies the path as a relative trajectory from the profile's
location (its absolute position is unused in v1).

Determinism (RESEARCH §9): path edges are built in entity list order, wire
assembly is a pure OCCT algorithm on identical inputs, and the sweep + boolean
are pure functions of their inputs — no unordered iteration participates.
"""

from collections.abc import Sequence

from build123d import Face, Plane, Solid, Wire
from py_kit.schemas.sketch import SketchEntity

from geometry.kernel.extrude import (
    PROFILE_WIRE_TOLERANCE,
    entity_edges,
)
from geometry.kernel.healing import clean_shape


class PathEmptyError(ValueError):
    """The path sketch has no curve entities (only construction/points); there
    is no trajectory to sweep along."""


class PathNotConnectedError(ValueError):
    """The path entities form more than one disjoint wire; a sweep path is a
    single connected chain in v1."""


class PathClosedError(ValueError):
    """The path wire is closed; a sweep path must be an OPEN wire in v1 (a
    closed path would sweep the profile back onto itself)."""


class SweepError(RuntimeError):
    """The OCCT sweep failed or produced an unsupported result (e.g. a path
    corner tighter than the profile, sweeping material through itself)."""


def build_path_wire(plane: Plane, entities: Sequence[SketchEntity]) -> Wire:
    """Assemble a path sketch's solved entities into a single OPEN wire.

    The open-wire sibling of :func:`geometry.kernel.extrude.build_profile_face`:
    it collects edges through the SAME per-entity builder (construction geometry
    excluded, input order preserved for determinism) but requires the result to
    be exactly one **open** chain — the sweep trajectory. *plane* is the resolved
    sketch plane (origin datum or offset ``datum`` feature).

    Raises:
        PathEmptyError: no curve entities (only construction geometry/points).
        PathNotConnectedError: the edges form more than one disjoint wire.
        PathClosedError: the single wire is closed (a sweep path must be open).
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
            "single connected open chain in v1."
        )
    wire = wires[0]
    if wire.is_closed:
        raise PathClosedError(
            "Path sketch forms a closed loop; a sweep path must be an OPEN wire "
            "in v1 (open the loop, or use a revolve for a closed sweep)."
        )
    return wire


def sweep_profile(face: Face, path: Wire) -> Solid:
    """Sweep the closed profile *face* along the open *path* wire.

    Anchored at the profile (build123d applies *path* as a relative trajectory
    from the profile's location — its absolute position is unused). ``clean()``
    collapses the redundant seams the operation leaves behind, keeping topology
    counts meaningful (and golden-assertable).

    Raises:
        SweepError: the OCCT sweep failed or left other than exactly one solid
            (single body chain per part in v1, design §7.6) — e.g. a path corner
            tighter than the profile, sweeping material through itself.
    """
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
    return clean_shape(solids[0])
