"""Sketch profile → face → linear extrusion → boolean against the body.

The kernel half of the extrude feature (feature-tree design §4.3): the
feature layer hands in *solved* sketch entities (pydantic DTOs from
:mod:`py_kit.schemas.sketch` — positions already through the solver) plus the
datum plane and scalar parameters; this module owns every OCCT/build123d
call. Failures raise the typed exceptions below with **sanitized messages**
(no kernel internals) — the feature layer maps them 1:1 onto ``FeatureError``
codes, so geometry outcomes stay values at the boundary.

Determinism (RESEARCH §9): profile edges are built in the entity list order,
wire assembly and booleans are pure OCCT algorithms on identical inputs, and
no iteration over unordered containers participates.

v1 profile rules (documented limits, not accidents):

- Entities flagged ``construction`` are reference-only (centerlines, symmetry
  axes, diagonals): they solve and can be constrained/referenced upstream, but
  are **excluded here** — the single profile-exclusion point for every
  body-affecting feature. ``point`` entities never bound a profile either.
- All remaining curve entities must form **one or more closed wires**. A
  single closed wire is a plain face (the original path, byte-identical). Two
  or more closed wires are a **face with holes**: the loop of largest area is
  the OUTER boundary and every other loop is an inner boundary (a hole)
  subtracted from the face — so one sketch of an outer boundary + N inner
  circles extrudes/cuts to a plate with N through-holes (a bolt circle). See
  :func:`build_profile_face` for the v1 classification rule and its documented
  limits (single outer boundary; disjoint, strictly-interior holes only).
  Marking a real profile edge construction opens its loop, so an open or
  broken chain raises :class:`ProfileNotClosedError`; a configuration outside
  the single-outer / disjoint-interior-holes rule raises
  :class:`ProfileUnsupportedError`.
- The extrusion is a single body chain (design §7.6): a boolean whose result
  is not exactly one solid raises :class:`BooleanError`.
"""

import math
from collections.abc import Sequence
from typing import Literal

from build123d import Edge, Face, Plane, Solid, Vector, Wire
from py_kit.schemas.sketch import (
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSpline,
)

#: Wire-assembly tolerance (mm) for chaining profile edges. Solved coincident
#: endpoints are bitwise identical (solver gate, RESEARCH §2), so this is a
#: numerical formality, aligned with the kernel linear tolerance (1e-7 m,
#: CLAUDE.md — model units are mm).
PROFILE_WIRE_TOLERANCE = 1e-4


class ProfileNotClosedError(ValueError):
    """The sketch's curve entities do not form a closed wire."""


class ProfileUnsupportedError(ValueError):
    """The profile's loops are all closed but their arrangement is outside v1
    support: disjoint outer boundaries (a multi-region / multi-body sketch), a
    hole that crosses the outer boundary, or holes that overlap or nest."""


class BooleanError(RuntimeError):
    """A boolean against the body failed or left an unsupported result."""


def _to_world(plane: Plane, point: Point2D) -> Vector:
    """Map sketch-local (x, y) mm onto *plane* in world coordinates."""
    return plane.origin + plane.x_dir * point.x + plane.y_dir * point.y


def plane_point_to_world(plane: Plane, point: Point2D) -> Vector:
    """Map a solved sketch (x, y) mm onto its sketch *plane* in world coordinates.

    The single public entry to the plane→world mapping the profile builder uses
    internally, so a feature that needs a sketch point in world space (e.g.
    revolve's axis endpoints) shares the EXACT mapping the profile is built with
    (CLAUDE.md DRY rule) — the axis and the profile can never disagree on where
    the sketch plane sits in the world. *plane* is the resolved
    :class:`~build123d.Plane` (origin datum or offset ``datum`` feature —
    docs/design/datum-planes.md §3a), so an offset plane's origin is honoured.
    """
    return _to_world(plane, point)


def entity_edges(plane: Plane, entity: SketchEntity) -> list[Edge]:
    """The kernel edge(s) contributed by one solved sketch entity.

    THE single per-entity edge-construction point (CLAUDE.md DRY rule): the
    profile builder (:func:`build_profile_face`, closed wire) and the sweep path
    builder (:func:`geometry.kernel.sweep.build_path_wire`, open wire) both go
    through here, so a profile and a path can never disagree on how a sketch
    entity becomes a kernel edge. Construction geometry is excluded by each
    caller BEFORE this point (the single profile/path-exclusion points), so
    points map to no edges here only as a defensive default.
    """
    match entity:
        case SketchPoint():
            return []  # construction geometry — never part of the profile
        case SketchLine():
            return [
                Edge.make_line(
                    _to_world(plane, entity.start), _to_world(plane, entity.end)
                )
            ]
        case SketchCircle():
            return [
                Edge.make_circle(
                    entity.radius,
                    Plane(
                        origin=_to_world(plane, entity.center),
                        x_dir=plane.x_dir,
                        z_dir=plane.z_dir,
                    ),
                )
            ]
        case SketchArc():
            radius = math.hypot(
                entity.start.x - entity.center.x, entity.start.y - entity.center.y
            )
            if radius <= 0.0:
                raise ProfileNotClosedError(
                    f"Arc '{entity.id}' is degenerate (zero radius) and cannot "
                    "bound a profile."
                )
            start_angle = math.degrees(
                math.atan2(
                    entity.start.y - entity.center.y, entity.start.x - entity.center.x
                )
            )
            end_angle = math.degrees(
                math.atan2(
                    entity.end.y - entity.center.y, entity.end.x - entity.center.x
                )
            )
            return [
                Edge.make_circle(
                    radius,
                    Plane(
                        origin=_to_world(plane, entity.center),
                        x_dir=plane.x_dir,
                        z_dir=plane.z_dir,
                    ),
                    start_angle=start_angle,
                    end_angle=end_angle,
                )
            ]
        case SketchSpline():
            # Fit-point spline: an interpolating C2 B-spline through the ordered
            # fit points (OCCT GeomAPI_Interpolate via Edge.make_spline), so a
            # closed profile wire containing a spline edge extrudes/revolves like
            # any curve. Deterministic across processes (OCCT interpolation is
            # seed-free; verified in-process AND across interpreter restart by the
            # spline golden's determinism gates). Coincident consecutive fit
            # points make interpolation degenerate: reject with a legible profile
            # error (the degenerate-arc precedent above) rather than let OCCT
            # raise an opaque kernel failure.
            for prev, nxt in zip(entity.points, entity.points[1:], strict=False):
                if math.isclose(prev.x, nxt.x, abs_tol=1e-9) and math.isclose(
                    prev.y, nxt.y, abs_tol=1e-9
                ):
                    raise ProfileNotClosedError(
                        f"Spline '{entity.id}' has coincident consecutive fit "
                        f"points at ({prev.x}, {prev.y}); each fit point must be "
                        "distinct from the previous one."
                    )
            return [
                Edge.make_spline([_to_world(plane, point) for point in entity.points])
            ]


#: Points sampled along each inner loop's perimeter to test that it lies
#: strictly inside the outer boundary (v1 containment classification). A whole
#: loop poking outside the outer boundary is caught when any sample lands
#: outside; OCCT's own face validity check (:attr:`Face.is_valid`) is the
#: geometry-exact backstop for anything sampling between points might miss, so
#: no malformed arrangement can slip through as a bad body. 64 is dense enough
#: to separate the analytic loops v1 authors while staying cheap.
_INNER_CONTAINMENT_SAMPLES = 64


def _wire_area(wire: Wire) -> float:
    """Planar area enclosed by a closed *wire* (via its bare face)."""
    return Face(wire).area


def _wire_sort_key(wire: Wire) -> tuple[float, float, float, float]:
    """A deterministic ordering key for inner (hole) wires (RESEARCH §9).

    Independent of :meth:`Wire.combine`'s output order: sort holes by enclosed
    area then centre-of-area coordinates, so the same sketch always feeds the
    same inner-wire order into ``Face(outer, inners)`` — and therefore the same
    tessellation bytes across processes (verified by the plate-with-holes
    golden's determinism gates).
    """
    face = Face(wire)
    centre = face.center()
    return (face.area, centre.X, centre.Y, centre.Z)


def _wire_strictly_inside(inner: Wire, outer_face: Face) -> bool:
    """Whether *inner* lies strictly inside *outer_face* (v1 containment test).

    THE single containment predicate (CLAUDE.md DRY rule) shared by the
    single-region classifier (:func:`_build_face_with_holes`) and the
    multi-region partition (:func:`_group_regions`): a whole loop poking outside
    the boundary is caught when any of the ``_INNER_CONTAINMENT_SAMPLES``
    perimeter samples lands outside, with OCCT's own face-validity check the
    geometry-exact backstop for anything between samples.
    """
    return all(
        outer_face.is_inside(
            inner.position_at(index / _INNER_CONTAINMENT_SAMPLES),
            tolerance=PROFILE_WIRE_TOLERANCE,
        )
        for index in range(_INNER_CONTAINMENT_SAMPLES)
    )


def _region_face(outer_wire: Wire, inner_wires: Sequence[Wire]) -> Face:
    """Build ONE region's face from its outer boundary + interior holes.

    Shared final step of the single-region classifier
    (:func:`_build_face_with_holes`) and the multi-region CUT partition
    (:func:`_group_regions`): holes are subtracted in the deterministic
    inner-wire order (RESEARCH §9), and OCCT's own validity check is the
    geometry-exact backstop for a hole that crosses the boundary, overlaps
    another hole, or nests. A region with no holes is a plain face (a bare loop
    in a ring of disjoint cut regions).
    """
    if not inner_wires:
        return Face(outer_wire)
    try:
        face = Face(outer_wire, sorted(inner_wires, key=_wire_sort_key))
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise ProfileUnsupportedError(
            "Sketch holes could not be subtracted from the outer boundary; "
            "each inner loop must be a simple, interior, non-overlapping hole."
        ) from exc

    if not face.is_valid:
        raise ProfileUnsupportedError(
            "Sketch holes cross the outer boundary, overlap one another, or "
            "nest; v1 supports one outer boundary with disjoint interior holes."
        )
    return face


def _build_face_with_holes(wires: Sequence[Wire]) -> Face:
    """Classify 2+ closed loops into ONE outer boundary + inner holes → face.

    v1 classification rule (documented limit, not an accident): the loop of
    **largest enclosed area** is the OUTER boundary; every other loop is a hole
    subtracted from it. Each hole must lie **strictly inside** the outer
    boundary and the holes must be **mutually disjoint** — a single outer
    boundary with N non-overlapping, non-nested interior holes (the bolt-circle
    / plate-with-holes case). Anything else is rejected as
    :class:`ProfileUnsupportedError` with a legible message, never a 500:

    * a loop not contained by the outer boundary ⇒ the sketch has disjoint
      outer boundaries (a multi-region / multi-body sketch) — supported for a
      CUT via :func:`build_profile_faces`, still an error for ADD/revolve/loft/
      sweep (a single body is one outer boundary with interior holes);
    * a hole crossing the outer boundary, or holes that overlap or nest, leave
      OCCT with an invalid face — caught by :func:`_region_face`'s backstop.
    """
    outer_wire = max(wires, key=_wire_area)
    outer_face = Face(outer_wire)
    inner_wires = [wire for wire in wires if wire is not outer_wire]

    for inner in inner_wires:
        if not _wire_strictly_inside(inner, outer_face):
            raise ProfileUnsupportedError(
                f"Sketch profile has {len(wires)} closed loops that are not all "
                "enclosed by a single outer boundary (a loop lies outside it or "
                "crosses it); extrude builds one body from one outer boundary "
                "with interior holes in v1 — separate regions (multi-body) and "
                "boundary-crossing loops are a later item."
            )
    return _region_face(outer_wire, inner_wires)


def _group_regions(wires: Sequence[Wire]) -> list[tuple[Wire, list[Wire]]]:
    """Partition 2+ closed loops into DISJOINT regions (outer + interior holes).

    The multi-region generalization of :func:`_build_face_with_holes`, consumed
    ONLY by the CUT extrude path (:func:`build_profile_faces`). Each region is
    one outer boundary and the holes strictly inside it; the regions are
    mutually disjoint — so N separate loops (a ring of lightening holes) become
    N independent removal tools, while one outer boundary + interior holes stays
    a single region (byte-identical to the plate-with-holes face). Containment
    uses the SAME :func:`_wire_strictly_inside` test the single-region
    classifier uses; ordering is deterministic (RESEARCH §9) — regions and holes
    both sort by :func:`_wire_sort_key`, so the same sketch always feeds the same
    cut-tool order.

    Raises:
        ProfileUnsupportedError: a loop nested more than one level deep (a hole
            inside a hole) — outside v1's one-level outer/hole model.
    """
    faces = [Face(wire) for wire in wires]
    containers: list[list[int]] = [
        [
            j
            for j, outer_face in enumerate(faces)
            if j != i and _wire_strictly_inside(wire, outer_face)
        ]
        for i, wire in enumerate(wires)
    ]

    roots = [i for i, conts in enumerate(containers) if not conts]
    holes_by_root: dict[int, list[int]] = {root: [] for root in roots}
    for i, conts in enumerate(containers):
        if not conts:
            continue
        # A hole has exactly one container, and that container must itself be a
        # region root (depth 0): >1 container, or a container that is itself a
        # hole, is a loop nested two deep — outside v1.
        if len(conts) > 1 or conts[0] not in holes_by_root:
            raise ProfileUnsupportedError(
                f"Sketch profile has {len(wires)} closed loops with a loop "
                "nested more than one level deep (a hole inside a hole); a CUT "
                "supports disjoint regions of one outer boundary with interior "
                "holes, not deeper nesting."
            )
        holes_by_root[conts[0]].append(i)

    regions = [
        (wires[root], [wires[hole] for hole in holes_by_root[root]]) for root in roots
    ]
    regions.sort(key=lambda region: _wire_sort_key(region[0]))
    return regions


def _profile_wires(plane: Plane, entities: Sequence[SketchEntity]) -> list[Wire]:
    """Assemble solved sketch entities into their CLOSED profile wires.

    The shared front half of :func:`build_profile_face` and
    :func:`build_profile_faces` (CLAUDE.md DRY rule): construction geometry is
    excluded exactly once, edges are built in entity-list order (determinism,
    RESEARCH §9 — filtering does not reorder), and every combined wire must
    close.

    Raises:
        ProfileNotClosedError: no curve entities, or some loop does not close.
    """
    edges: list[Edge] = []
    for entity in entities:
        # THE single profile-exclusion point (design §2.4 semantics): every
        # body-affecting feature that consumes a sketch profile builds it
        # through here, so construction geometry is dropped exactly once.
        if entity.construction:
            continue
        edges.extend(entity_edges(plane, entity))

    if not edges:
        raise ProfileNotClosedError(
            "Sketch contains no profile curves (only construction geometry "
            "and/or points); nothing to extrude."
        )

    wires = Wire.combine(edges, tol=PROFILE_WIRE_TOLERANCE)
    for wire in wires:
        if not wire.is_closed:
            raise ProfileNotClosedError(
                "Sketch profile is not a closed loop; close the boundary (e.g. "
                "with coincident constraints) before extruding."
            )
    return list(wires)


def build_profile_face(plane: Plane, entities: Sequence[SketchEntity]) -> Face:
    """Assemble solved sketch entities into a closed profile face.

    A single closed loop is a plain face (byte-identical to the original
    single-loop path). Two or more closed loops are a **face with holes**: the
    largest-area loop is the outer boundary and every other loop is a hole
    subtracted from it — one sketch of an outer boundary + N inner circles
    extrudes/cuts to a plate with N through-holes (see
    :func:`_build_face_with_holes` for the classification rule and its v1
    limits). Every body-affecting feature (extrude/revolve/sweep/loft) consumes
    this face, so they all gain holes for free.

    *plane* is the resolved sketch :class:`~build123d.Plane` (origin datum or
    offset ``datum`` feature — docs/design/datum-planes.md §3a); the name→Plane
    lookup lives up in the feature layer's ``resolve_sketch_plane`` funnel now,
    so every body-affecting builder takes a concrete plane.

    Raises:
        ProfileNotClosedError: no curve entities, or some loop does not close.
        ProfileUnsupportedError: the loops do not form one outer boundary with
            disjoint, strictly-interior holes (disjoint outer boundaries /
            crossing / overlapping / nested holes — all legible, never a 500).
    """
    wires = _profile_wires(plane, entities)
    if len(wires) == 1:
        return Face(wires[0])
    return _build_face_with_holes(wires)


def build_profile_faces(plane: Plane, entities: Sequence[SketchEntity]) -> list[Face]:
    """Assemble solved sketch entities into ONE OR MORE disjoint region faces.

    The multi-region sibling of :func:`build_profile_face`, consumed ONLY by the
    **CUT** extrude path: N disjoint closed loops become N independent removal
    regions (a ring of lightening holes cut in a single feature — showcase F2),
    with **no shared outer boundary required**. A single-region sketch (one
    loop, or one outer boundary + interior holes) returns a one-element list
    whose face is byte-identical to :func:`build_profile_face`, so the
    plate-with-holes cut path is unchanged. ADD/revolve/loft/sweep still resolve
    through :func:`build_profile_face`, which rejects disjoint loops as a
    multi-body sketch — the add-vs-cut distinction lives at the feature layer,
    which calls this only for ``operation == "cut"``.

    Region ordering is deterministic (RESEARCH §9): :func:`_group_regions` sorts
    the regions (and their holes) by :func:`_wire_sort_key`, so the same sketch
    always yields the same cut-tool sequence.

    Raises:
        ProfileNotClosedError: no curve entities, or some loop does not close.
        ProfileUnsupportedError: a loop nested more than one level deep, or a
            region's holes cross/overlap/nest (all legible, never a 500).
    """
    wires = _profile_wires(plane, entities)
    if len(wires) == 1:
        return [Face(wires[0])]
    return [_region_face(outer, holes) for outer, holes in _group_regions(wires)]


def extrude_face(
    face: Face,
    plane: Plane,
    distance_mm: float,
    reverse: bool,
) -> Solid:
    """Linear-extrude *face* along the sketch *plane* normal (mm).

    ``reverse`` extrudes along the negative normal (``direction: "reverse"``).
    *plane* is the resolved sketch plane, so an offset datum's normal (and, with
    ``flip``, its reversed sense) drives the extrusion direction.
    """
    if distance_mm <= 0:
        raise ValueError(f"distance_mm must be > 0, got {distance_mm}")
    normal = plane.z_dir
    direction = normal * (-distance_mm if reverse else distance_mm)
    return Solid.extrude(face, direction)


def combine_body(
    body: Solid | None, tool: Solid, operation: Literal["add", "cut"]
) -> Solid:
    """Boolean *tool* against *body*; returns the new single-solid body.

    ``add`` with no prior body starts the body chain with *tool*. ``cut``
    with no prior body is a **feature-layer** error (``no_prior_body``) and
    never reaches here — asserting that keeps the contract explicit.

    Raises:
        BooleanError: the kernel boolean failed, produced no solid (e.g. a
            cut that consumed the whole body), or produced multiple disjoint
            solids (single body chain per part in v1, design §7.6).
    """
    if body is None:
        assert operation == "add", "cut without a body is handled by the caller"
        return tool

    try:
        # fuse/cut signatures carry Shape[Unknown] type params upstream (same
        # gap tessellate.py documents for export_gltf) — scoped ignores only.
        result = (
            body.fuse(tool)  # pyright: ignore[reportUnknownMemberType]
            if operation == "add"
            else body.cut(tool)  # pyright: ignore[reportUnknownMemberType]
        )
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise BooleanError(
            f"Boolean {operation} failed in the kernel "
            f"({type(exc).__name__}); the profile may self-intersect or "
            "graze the body."
        ) from exc

    if len(solids) == 0:
        raise BooleanError(
            f"Boolean {operation} left no material — the cut consumed the entire body."
        )
    if len(solids) > 1:
        raise BooleanError(
            f"Boolean {operation} produced {len(solids)} disjoint solids; "
            "parts are a single body in v1."
        )
    # clean() removes redundant seam faces/edges a boolean can leave behind,
    # keeping topology counts meaningful (and golden-assertable).
    return solids[0].clean()
