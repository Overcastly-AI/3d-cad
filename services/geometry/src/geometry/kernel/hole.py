"""Cylindrical hole (drill) — a face-placed blind pocket or through cut.

The kernel half of the Hole feature (slice 1 — the simple hole; slice 2 — the
counterbore / countersink recess). The feature
layer resolves the placement face's plane (:func:`geometry.kernel.faces.
resolve_face_plane` — the SAME stage-1 planar-face signature the ``on_face``
datum resolves, NOT a parallel taxonomy) and hands in that plane, the placement
point, the drill diameter, and the depth mode. This module owns only the
OCCT/build123d cylinder-cut: it builds a right-circular drill tool and subtracts
it from the body through the shared :func:`geometry.kernel.extrude.combine_body`
(the same lump-count-preserving boolean every cut feature uses — CLAUDE.md DRY),
so a hole is a first-class *feature*, never a hand-sketched circle.

CUT DIRECTION (the everyday-ergonomics correctness rule): the drill always cuts
INTO the solid — along ``-face_plane.z_dir`` (opposite the face's OUTWARD
normal). The placement point is projected onto the face plane, so a pick that
lands a hair off-plane still drills a clean, perpendicular hole. A THROUGH-ALL
hole cuts fully through the body: the tool starts well OUTSIDE the face (a
bounding-box diagonal above it) and spans several diagonals, so it clears the
body on both sides regardless of where the point sits — no coincident-face
boolean fragility, and no dependence on the local wall thickness. A BLIND hole
drills exactly ``depth_mm`` into the material (the tool likewise starts outside
the face, so only the depth INTO the solid removes material — the removed volume
is analytically ``pi * r**2 * depth_mm`` for a fully-embedded pocket).

TYPED DEGRADATION (never a 500, never a silently wrong body — the feature layer
maps these 1:1 onto ``hole_off_body`` / ``hole_too_deep`` / ``boolean_failed``):

* :class:`HoleOffBodyError` — the drill removed NO material. The placement point
  lies off the face (outside the body), or the resolved cut direction points
  into empty space. Caught by the material-removed invariant (a real hole
  strictly reduces the volume), the SAME posture the shell feature uses.
* :class:`HoleTooDeepError` — a BLIND hole could not form its full pocket: the
  material under the drill (``tool ∩ body``, :func:`_pocket`) is short of
  ``pi * r**2 * depth_mm``, so the depth exceeds the available material (the
  drill broke through the far side) or the bore overhangs the face edge. Use a
  through-all hole, reduce the depth, or move the point.
* :class:`geometry.kernel.extrude.BooleanError` — the kernel boolean failed or
  the cut severed / changed the body's lump count (``combine_body``'s invariant).

WHY THE POCKET IS MEASURED, NOT THE BODY (HOLE-BLIND-FALSE-DEEP). The check once
read ``volume(body) - volume(cut)``. Integration error scales with the BODY and
its face types, not the pocket: on a 60 000 mm^3 B-spline enclosure the two
fixed-order readings missed a Ø2.5 x 10 pocket by ~1.8 mm^3, and a valid hole
was refused. Integrating the common solid, whose faces are the drill's own
cylinder and disk plus the placement-face cap, reads the same pocket to 3e-9
relative on that body. The allowed shortfall is :func:`_pocket_slack`.

Determinism (RESEARCH §9): the drilled body is a pure function of
``(body, face_plane, position, diameter_mm, depth)`` — the bounding-box diagonal,
the plane projection, and the OCCT cut are all deterministic.

The OCP wheel ships no type stubs, so the raw build123d/OCCT geometry calls are
opaque to pyright; the directives scope that relaxation to this file only.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math

from build123d import Compound, Plane, Solid, Vector
from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance

from geometry.kernel.extrude import combine_body_measured
from geometry.kernel.properties import volume_properties
from geometry.kernel.types import BodyShape

#: A real hole strictly REMOVES material, so a drill that finds no more than
#: this fraction of the body's volume under it removed nothing — the point is off the
#: face or the direction is wrong (:class:`HoleOffBodyError`). Orders of
#: magnitude below the material any non-degenerate bore removes (whole mm^3),
#: while absorbing GProp float noise — the shell material-removed posture.
_REMOVED_REL_TOL = 1e-9

#: ``Precision::Confusion()`` (mm): OCCT's distance below which two points are
#: one. The floor of :func:`_pocket_slack`'s skin thickness.
_CONFUSION_MM = 1e-7

#: The ceiling of :func:`_pocket_slack`'s skin thickness (mm). A body whose
#: stored tolerance is inflated (a sloppy import) would otherwise widen the
#: slack until a visible breakthrough passed: at tolerance 1e-2 a 0.1 mm
#: breakthrough of a Ø2.5 x 10 blind hole read as a full pocket. Bodies Loft
#: builds peak near 1e-4 (spline shell; fillet 8e-5, sweep 4e-5), and the
#: B-spline pocket noise this slack absorbs needs about 5e-6.
_SLACK_CEILING_MM = 1e-4


class HoleError(ValueError):
    """Base: a hole could not be drilled (a per-feature error, never a 500)."""


class HoleOffBodyError(HoleError):
    """The drill removed no material — the point is off the face / off the body."""


class HoleTooDeepError(HoleError):
    """A blind hole could not form its full pocket (over-deep / edge-overhang).

    Also raised by a counterbore / countersink recess whose depth exceeds the
    available material (the recess would break through / overhangs the face edge).
    """


class HoleInvalidDiameterError(HoleError):
    """The bore diameter is not a positive length (defence-in-depth).

    A negative or zero diameter cannot form a drill: ``Solid.make_cylinder`` would
    raise a raw OCCT ``Standard_ConstructionError`` that escapes the feature
    layer's HoleError handlers as a 500. The API already rejects it
    (``HoleParamsV1.diameter_mm`` is ``Field(gt=0)``), so this guard is a
    belt-and-braces typed failure for the scripting / pattern-reconstruction paths
    that call the kernel past the schema — never a raw kernel raise, never a 500.
    """


class HoleRecessInvalidError(HoleError):
    """A counterbore/countersink recess is not larger than the bore it seats.

    The recess (counterbore cylinder or countersink cone mouth) must be strictly
    WIDER than the bore diameter — a recess no larger than the bore removes no
    extra material and is a meaningless seat. Mapped 1:1 by the feature layer onto
    ``hole_cbore_invalid`` / ``hole_csink_invalid`` (per the hole type).
    """


def _cut_drill(
    body: BodyShape,
    tool: Solid,
    off_body: HoleError,
    *,
    body_volume: float | None = None,
) -> tuple[BodyShape, float, float]:
    """Cut a drill/recess *tool* from *body*: ``(drilled body, removed, tolerance)``.

    *removed* and *tolerance* are :func:`_pocket` of ``(body, tool)``,
    the pocket the cut takes out, measured BEFORE the cut from the same common
    that answers "does the tool reach the body at all?". That question is the
    shared :func:`geometry.kernel.removal.removal_reaches_body` predicate (CM-3),
    which IS "does ``body ∩ tool`` hold a solid", so asking it and then measuring
    the pocket used to run the same whole-body boolean twice per drill: 6 % of a
    200-feature rebuild (RESEARCH §15). Asked once here, the answer is handed
    to :func:`~geometry.kernel.extrude.combine_body` as ``reaches``.

    A tool that misses the body is reported in the Hole's OWN vocabulary,
    *off_body* (``hole_off_body`` for the bore, ``hole_too_deep`` for a recess
    that forms none of its annulus), never the generic ``boolean_failed``. The
    caller's analytic checks on *removed* stay: they also catch a bore that
    removes a sliver, which "reaches the body" but is still off the face.

    Failure order is the one the two-boolean form had. The predicate answers
    "reaches" when its common RAISES (an OCCT anomaly must not turn a working
    feature into an error), so the cut still runs and reports its own
    ``BooleanError``; only then does the measurement's exception surface.

    *body_volume* is *body*'s volume when known, for the boolean integrity guard
    (:mod:`geometry.kernel.boolean_guard`).
    """
    pocket: tuple[float, float] | None = None
    measured = True
    try:
        pocket = _pocket(body, tool)
    except Exception:  # OCCT failure modes are not a stable taxonomy
        measured = False
    if measured and pocket is None:
        raise off_body
    result = combine_body_measured(
        body, tool, "cut", reaches=True, body_volume=body_volume
    ).shape
    if not measured:
        pocket = _pocket(body, tool)
    removed, tolerance = (0.0, 0.0) if pocket is None else pocket
    return result, removed, tolerance


def _pocket(body: BodyShape, tool: Solid) -> tuple[float, float] | None:
    """``(volume, tolerance)`` of the material the drill *tool* occupies in
    *body*, or ``None`` when ``body ∩ tool`` holds no solid (the tool does not
    reach the body: the shared removal predicate's ``False``).

    The common solid IS the pocket the cut removes, measured on its own scale
    rather than as the difference of two whole-body readings. *tolerance* is the
    largest vertex/edge/face tolerance OCCT gave that solid."""
    common = body.intersect(tool)
    solids = [] if common is None else list(common.solids())
    if not solids:
        return None
    pocket = solids[0] if len(solids) == 1 else Compound(children=solids)
    tolerance = ShapeAnalysis_ShapeTolerance().Tolerance(pocket.wrapped, 1)
    return volume_properties(pocket).volume, float(tolerance)


def _pocket_slack(tolerance: float, boundary_area: float) -> float:
    """The shortfall (mm^3) a fully-formed pocket may read: a skin ``t`` thick
    over its ``boundary_area`` (mm^2), with ``t`` the common solid's own OCCT
    tolerance floored at ``Precision::Confusion()`` and capped at
    :data:`_SLACK_CEILING_MM`.

    OCCT treats geometry within a shape's tolerance as coincident, so the
    boolean can place a pocket wall anywhere inside that band; a shortfall
    beyond the band is material the drill did not find. Measured (2026-10-01)
    on fully-embedded pockets: exact bodies read within 1e-13 relative (common
    tolerance 1e-7); B-spline bodies (common tolerance 5e-6, an approximated
    intersection curve) fall short by 6.7e-10 to 0.137 mm^3 from Ø0.1 x 0.2 to
    Ø400 x 600, i.e. a cap 1e-7 to 1.1e-6 mm low, which this slack covers by
    37x or more. On an exact Ø10 x 10 pocket it is 4.7e-5 mm^3, so a blind
    hole 1e-5 mm too deep is refused (the old 1e-6-of-pocket bound let it
    pass)."""
    return min(max(tolerance, _CONFUSION_MM), _SLACK_CEILING_MM) * boundary_area


def _require_full_pocket(
    removed: float,
    tolerance: float,
    expected: float,
    boundary_area: float,
    error: HoleError,
) -> None:
    """Raise *error* unless the measured pocket (*removed*, its *tolerance*,
    from :func:`_cut_drill`) is the whole analytic pocket *expected*."""
    if removed < expected - _pocket_slack(tolerance, boundary_area):
        raise error


def _drill_axis(
    body: BodyShape, face_plane: Plane, position: tuple[float, float, float]
) -> tuple[Vector, Vector, float]:
    """The coaxial drill axis shared by the bore and every recess cut.

    Returns ``(center, normal, span)``: *center* is *position* projected onto
    *face_plane* (so the axis is perpendicular to the face and clean even if the
    pick lands a hair off-plane), *normal* is the face's OUTWARD unit normal (the
    tool cuts along ``-normal``, INTO the solid), and *span* is the body's
    bounding-box diagonal — a pure, deterministic length that always clears the
    body, so a tool started ``span`` OUTSIDE the face needs no coincident-face
    boolean at the opening and no ad-hoc epsilon (RESEARCH §9 determinism)."""
    normal = face_plane.z_dir
    point = Vector(*position)
    center = point - normal * (point - face_plane.origin).dot(normal)
    span = body.bounding_box().diagonal
    return center, normal, span


def bore_tool(
    body: BodyShape,
    face_plane: Plane,
    position: tuple[float, float, float],
    diameter_mm: float,
    *,
    through_all: bool,
    depth_mm: float | None,
) -> Solid:
    """The right-circular drill TOOL a :func:`bore_hole` subtracts (no cut yet).

    Factored out (CLAUDE.md DRY rule) so a pattern / mirror of a Hole feature can
    RECONSTRUCT the exact removal solid it must replicate — the same cylinder,
    from the same projected axis + outward normal + bounding-box span — without
    re-running the cut. A pure function of ``(body, face_plane, position,
    diameter_mm, through_all, depth_mm)``: the tool starts a span OUTSIDE the face
    and drills inward, so it needs no coincident-face boolean and no ad-hoc epsilon
    (RESEARCH §9 determinism).

    Raises:
        HoleInvalidDiameterError: ``diameter_mm`` is not a positive length — a
            typed guard (defence-in-depth past the API's ``gt=0``) so a
            non-positive diameter never reaches the raw OCCT ``Solid.make_cylinder``
            as an untyped ``Standard_ConstructionError``."""
    if diameter_mm <= 0.0:
        raise HoleInvalidDiameterError(
            f"The hole diameter ({diameter_mm}mm) must be a positive length; a "
            "non-positive diameter cannot form a drill. Enter a diameter above 0."
        )
    radius = diameter_mm / 2.0
    center, normal, span = _drill_axis(body, face_plane, position)
    start = center + normal * span
    height = 3.0 * span if through_all else span + (depth_mm or 0.0)
    into = -normal
    return Solid.make_cylinder(
        radius, height, Plane(origin=start, x_dir=face_plane.x_dir, z_dir=into)
    )


def bore_hole(
    body: BodyShape,
    face_plane: Plane,
    position: tuple[float, float, float],
    diameter_mm: float,
    *,
    through_all: bool,
    depth_mm: float | None,
    body_volume: float | None = None,
) -> BodyShape:
    """Drill a cylindrical hole into *body* at *position* on *face_plane*.

    *face_plane* is the resolved placement face's plane (origin at the face
    centroid, ``z_dir`` the OUTWARD normal — from :func:`resolve_face_plane`).
    *position* is a world-space point projected onto that plane to fix the drill
    axis. The drill cuts INTO the solid (``-z_dir``); ``through_all`` cuts fully
    through, otherwise a blind pocket ``depth_mm`` deep (``depth_mm`` must be a
    positive float when ``through_all`` is False — the feature layer's discriminated
    depth union guarantees it). *body_volume* is *body*'s volume when the caller
    knows it (the evaluation's per-body memo), so it is not integrated again.

    Returns the drilled body (lump-count-preserving, via ``combine_body``).

    Raises:
        HoleOffBodyError: the drill removed no material (off face / bad direction).
        HoleTooDeepError: a blind pocket could not fully form (over-deep / overhang).
        BooleanError: the kernel cut failed or changed the body's lump count.
    """
    radius = diameter_mm / 2.0
    tool = bore_tool(
        body,
        face_plane,
        position,
        diameter_mm,
        through_all=through_all,
        depth_mm=depth_mm,
    )

    off_body = HoleOffBodyError(
        "The hole removed no material: the placement point lies off the face "
        "(outside the body), or the cut direction points into empty space. "
        "Re-place the hole on the face."
    )
    volume = float(body.volume) if body_volume is None else body_volume
    result, removed, tolerance = _cut_drill(body, tool, off_body, body_volume=volume)

    if removed <= volume * _REMOVED_REL_TOL:
        raise off_body
    if not through_all:
        assert depth_mm is not None, "a blind hole carries a positive depth_mm"
        expected = math.pi * radius * radius * depth_mm
        area = 2.0 * math.pi * radius * (depth_mm + radius)
        if removed < expected - _pocket_slack(tolerance, area):
            raise HoleTooDeepError(
                "The blind hole could not form its full depth: the removed "
                f"material is short of a diameter-{diameter_mm}mm, {depth_mm}mm-deep "
                "pocket. The depth exceeds the available material (the drill would "
                "break through), or the bore overhangs the face edge. Use a "
                "through-all hole, reduce the depth, or move the hole inward."
            )
    return result


def counterbore_tool(
    body: BodyShape,
    face_plane: Plane,
    position: tuple[float, float, float],
    *,
    bore_diameter_mm: float,
    cbore_diameter_mm: float,
    cbore_depth_mm: float,
) -> Solid:
    """The coaxial CYLINDRICAL counterbore recess TOOL (no cut yet).

    Factored out (DRY) so a pattern / mirror of a counterbored Hole can replicate
    the recess exactly. Validates the recess-larger-than-bore rule here (the same
    :class:`HoleRecessInvalidError` :func:`cut_counterbore` raised) so a
    reconstructed tool can never be a degenerate no-wider-than-bore cylinder."""
    bore_radius = bore_diameter_mm / 2.0
    radius = cbore_diameter_mm / 2.0
    if radius <= bore_radius:
        raise HoleRecessInvalidError(
            f"The counterbore diameter ({cbore_diameter_mm}mm) must be larger than "
            f"the bore diameter ({bore_diameter_mm}mm); a recess no wider than the "
            "bore seats nothing. Increase the counterbore diameter."
        )
    center, normal, span = _drill_axis(body, face_plane, position)
    start = center + normal * span
    into = -normal
    return Solid.make_cylinder(
        radius,
        span + cbore_depth_mm,
        Plane(origin=start, x_dir=face_plane.x_dir, z_dir=into),
    )


def cut_counterbore(
    body: BodyShape,
    face_plane: Plane,
    position: tuple[float, float, float],
    *,
    bore_diameter_mm: float,
    cbore_diameter_mm: float,
    cbore_depth_mm: float,
) -> BodyShape:
    """Sink a coaxial CYLINDRICAL counterbore recess into an already-drilled body.

    Cuts a flat-bottomed cylinder of ``cbore_diameter_mm`` to ``cbore_depth_mm``
    from *face_plane*, coaxial with the bore (the SAME projected axis + inward
    direction :func:`bore_hole` uses). *body* is the bore already drilled, so the
    recess removes only the ANNULAR difference beyond the bore radius: for a
    fully-embedded recess the removed material is exactly
    ``pi * (R**2 - r**2) * cbore_depth`` (``R`` = counterbore radius, ``r`` = bore
    radius). Returns the recessed body (lump-count-preserving, via ``combine_body``).

    Raises:
        HoleRecessInvalidError: the counterbore diameter is not larger than the bore.
        HoleTooDeepError: the recess removed less than its analytic annulus — the
            depth exceeds the material (broke through) or overhangs the face edge.
        BooleanError: the kernel cut failed or changed the body's lump count.
    """
    tool = counterbore_tool(
        body,
        face_plane,
        position,
        bore_diameter_mm=bore_diameter_mm,
        cbore_diameter_mm=cbore_diameter_mm,
        cbore_depth_mm=cbore_depth_mm,
    )
    bore_radius = bore_diameter_mm / 2.0
    radius = cbore_diameter_mm / 2.0

    too_deep = HoleTooDeepError(
        "The counterbore recess could not form its full depth: the removed "
        f"material is short of a {cbore_depth_mm}mm-deep, diameter-"
        f"{cbore_diameter_mm}mm recess. The depth exceeds the available material "
        "(the recess would break through), or it overhangs the face edge. "
        "Reduce the counterbore depth or diameter, or move the hole inward."
    )
    result, removed, tolerance = _cut_drill(body, tool, too_deep)
    expected = math.pi * (radius * radius - bore_radius * bore_radius) * cbore_depth_mm
    # Outer and inner walls plus the floor and the face-plane cap.
    area = (
        2.0
        * math.pi
        * (
            (radius + bore_radius) * cbore_depth_mm
            + radius * radius
            - bore_radius * bore_radius
        )
    )
    _require_full_pocket(removed, tolerance, expected, area, too_deep)
    return result


def countersink_tool(
    body: BodyShape,
    face_plane: Plane,
    position: tuple[float, float, float],
    *,
    bore_diameter_mm: float,
    csink_diameter_mm: float,
    csink_angle_deg: float,
) -> Solid:
    """The coaxial CONICAL countersink recess TOOL (no cut yet).

    Factored out (DRY) so a pattern / mirror of a countersunk Hole can replicate
    the cone exactly. Validates the mouth-larger-than-bore rule here (the same
    :class:`HoleRecessInvalidError` :func:`cut_countersink` raised)."""
    bore_radius = bore_diameter_mm / 2.0
    radius = csink_diameter_mm / 2.0
    if radius <= bore_radius:
        raise HoleRecessInvalidError(
            f"The countersink diameter ({csink_diameter_mm}mm) must be larger than "
            f"the bore diameter ({bore_diameter_mm}mm); a cone no wider than the "
            "bore seats nothing. Increase the countersink diameter."
        )
    slope = math.tan(math.radians(csink_angle_deg / 2.0))
    cone_depth = (radius - bore_radius) / slope
    center, normal, span = _drill_axis(body, face_plane, position)
    into = -normal
    # Extend the wide mouth `span` ABOVE the face along the cone's slope, so the
    # opening clears a coincident-face boolean while the radius is still exactly
    # `radius` at the surface and exactly `bore_radius` at `cone_depth` below it.
    mouth_radius = radius + span * slope
    origin = center + normal * span
    return Solid.make_cone(
        mouth_radius,
        bore_radius,
        span + cone_depth,
        Plane(origin=origin, x_dir=face_plane.x_dir, z_dir=into),
    )


def cut_countersink(
    body: BodyShape,
    face_plane: Plane,
    position: tuple[float, float, float],
    *,
    bore_diameter_mm: float,
    csink_diameter_mm: float,
    csink_angle_deg: float,
) -> BodyShape:
    """Sink a coaxial CONICAL countersink recess into an already-drilled body.

    Cuts a truncated cone coaxial with the bore: ``csink_diameter_mm`` wide at the
    face surface, tapering at the ``csink_angle_deg`` INCLUDED angle down to the
    bore diameter at the depth the angle implies
    (``h = (R - r) / tan(angle/2)``, ``R`` = countersink radius, ``r`` = bore
    radius). The cone mouth is extended a bounding-box span ABOVE the surface (so
    the opening needs no coincident-face boolean while the radius is still exactly
    ``R`` at the face). *body* is the bore already drilled, so the cone removes
    only the annular difference beyond the bore: for a fully-embedded recess the
    removed material is exactly ``pi * h / 3 * (R**2 + R*r - 2*r**2)`` (the frustum
    ``pi * h/3 * (R**2 + R*r + r**2)`` minus the already-bored ``pi * r**2 * h``).
    Returns the recessed body (lump-count-preserving, via ``combine_body``).

    Raises:
        HoleRecessInvalidError: the countersink mouth is not larger than the bore.
        HoleTooDeepError: the cone removed less than its analytic annulus — the
            implied depth exceeds the material or overhangs the face edge.
        BooleanError: the kernel cut failed or changed the body's lump count.
    """
    tool = countersink_tool(
        body,
        face_plane,
        position,
        bore_diameter_mm=bore_diameter_mm,
        csink_diameter_mm=csink_diameter_mm,
        csink_angle_deg=csink_angle_deg,
    )
    bore_radius = bore_diameter_mm / 2.0
    radius = csink_diameter_mm / 2.0
    slope = math.tan(math.radians(csink_angle_deg / 2.0))
    cone_depth = (radius - bore_radius) / slope

    too_deep = HoleTooDeepError(
        "The countersink recess could not form its full cone: the removed "
        f"material is short of a diameter-{csink_diameter_mm}mm, "
        f"{csink_angle_deg}deg countersink. The implied cone depth exceeds the "
        "available material (it would break through), or it overhangs the face "
        "edge. Reduce the countersink diameter/angle, or move the hole inward."
    )
    result, removed, tolerance = _cut_drill(body, tool, too_deep)
    expected = (
        math.pi
        * cone_depth
        / 3.0
        * (radius * radius + radius * bore_radius - 2.0 * bore_radius * bore_radius)
    )
    # Cone flank, the bore wall it surrounds, and the face-plane annulus.
    slant = math.hypot(radius - bore_radius, cone_depth)
    area = math.pi * (
        (radius + bore_radius) * slant
        + 2.0 * bore_radius * cone_depth
        + radius * radius
        - bore_radius * bore_radius
    )
    _require_full_pocket(removed, tolerance, expected, area, too_deep)
    return result
