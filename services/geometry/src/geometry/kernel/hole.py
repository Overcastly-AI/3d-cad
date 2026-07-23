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
  removed volume is short of ``pi * r**2 * depth_mm``, so the depth exceeds the
  available material (the drill broke through the far side) or the bore overhangs
  the face edge. Use a through-all hole, reduce the depth, or move the point.
* :class:`geometry.kernel.extrude.BooleanError` — the kernel boolean failed or
  the cut severed / changed the body's lump count (``combine_body``'s invariant).

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

from build123d import Plane, Solid, Vector

from geometry.kernel.extrude import combine_body
from geometry.kernel.types import BodyShape

#: A real hole strictly REMOVES material, so a drill that reduces the volume by
#: no more than this fraction of the body removed nothing — the point is off the
#: face or the direction is wrong (:class:`HoleOffBodyError`). Orders of
#: magnitude below the material any non-degenerate bore removes (whole mm^3),
#: while absorbing GProp float noise — the shell material-removed posture.
_REMOVED_REL_TOL = 1e-9

#: A fully-embedded blind pocket removes EXACTLY ``pi * r**2 * depth`` (measured
#: exact to ~3e-15 relative, build123d 0.11.1 / OCCT 7.9). A removed volume below
#: this relative margin of that analytic pocket means the pocket could not form —
#: the depth exceeds the material or the bore overhangs the face edge
#: (:class:`HoleTooDeepError`). Loose enough to never false-trip on boolean
#: noise, tight enough that a broke-through / overhanging bore always trips
#: (mm-scale relative tolerance, the kernel 1e-7 m posture).
_POCKET_REL_TOL = 1e-6


class HoleError(ValueError):
    """Base: a hole could not be drilled (a per-feature error, never a 500)."""


class HoleOffBodyError(HoleError):
    """The drill removed no material — the point is off the face / off the body."""


class HoleTooDeepError(HoleError):
    """A blind hole could not form its full pocket (over-deep / edge-overhang).

    Also raised by a counterbore / countersink recess whose depth exceeds the
    available material (the recess would break through / overhangs the face edge).
    """


class HoleRecessInvalidError(HoleError):
    """A counterbore/countersink recess is not larger than the bore it seats.

    The recess (counterbore cylinder or countersink cone mouth) must be strictly
    WIDER than the bore diameter — a recess no larger than the bore removes no
    extra material and is a meaningless seat. Mapped 1:1 by the feature layer onto
    ``hole_cbore_invalid`` / ``hole_csink_invalid`` (per the hole type).
    """


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


def bore_hole(
    body: BodyShape,
    face_plane: Plane,
    position: tuple[float, float, float],
    diameter_mm: float,
    *,
    through_all: bool,
    depth_mm: float | None,
) -> BodyShape:
    """Drill a cylindrical hole into *body* at *position* on *face_plane*.

    *face_plane* is the resolved placement face's plane (origin at the face
    centroid, ``z_dir`` the OUTWARD normal — from :func:`resolve_face_plane`).
    *position* is a world-space point projected onto that plane to fix the drill
    axis. The drill cuts INTO the solid (``-z_dir``); ``through_all`` cuts fully
    through, otherwise a blind pocket ``depth_mm`` deep (``depth_mm`` must be a
    positive float when ``through_all`` is False — the feature layer's discriminated
    depth union guarantees it).

    Returns the drilled body (lump-count-preserving, via ``combine_body``).

    Raises:
        HoleOffBodyError: the drill removed no material (off face / bad direction).
        HoleTooDeepError: a blind pocket could not fully form (over-deep / overhang).
        BooleanError: the kernel cut failed or changed the body's lump count.
    """
    radius = diameter_mm / 2.0
    # The projected axis + outward normal + bounding-box span (shared with every
    # recess cut): start the tool OUTSIDE the face and drill inward, so no ad-hoc
    # epsilon and no coincident-face boolean at the opening.
    center, normal, span = _drill_axis(body, face_plane, position)
    start = center + normal * span
    height = 3.0 * span if through_all else span + (depth_mm or 0.0)
    into = -normal
    tool: Solid = Solid.make_cylinder(
        radius, height, Plane(origin=start, x_dir=face_plane.x_dir, z_dir=into)
    )

    before = float(body.volume)
    result = combine_body(body, tool, "cut")
    removed = before - float(result.volume)

    if removed <= before * _REMOVED_REL_TOL:
        raise HoleOffBodyError(
            "The hole removed no material: the placement point lies off the face "
            "(outside the body), or the cut direction points into empty space. "
            "Re-place the hole on the face."
        )
    if not through_all:
        assert depth_mm is not None, "a blind hole carries a positive depth_mm"
        expected = math.pi * radius * radius * depth_mm
        if removed < expected * (1.0 - _POCKET_REL_TOL):
            raise HoleTooDeepError(
                "The blind hole could not form its full depth: the removed "
                f"material is short of a diameter-{diameter_mm}mm, {depth_mm}mm-deep "
                "pocket. The depth exceeds the available material (the drill would "
                "break through), or the bore overhangs the face edge. Use a "
                "through-all hole, reduce the depth, or move the hole inward."
            )
    return result


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
    tool: Solid = Solid.make_cylinder(
        radius,
        span + cbore_depth_mm,
        Plane(origin=start, x_dir=face_plane.x_dir, z_dir=into),
    )

    before = float(body.volume)
    result = combine_body(body, tool, "cut")
    removed = before - float(result.volume)

    expected = math.pi * (radius * radius - bore_radius * bore_radius) * cbore_depth_mm
    if removed < expected * (1.0 - _POCKET_REL_TOL):
        raise HoleTooDeepError(
            "The counterbore recess could not form its full depth: the removed "
            f"material is short of a {cbore_depth_mm}mm-deep, diameter-"
            f"{cbore_diameter_mm}mm recess. The depth exceeds the available material "
            "(the recess would break through), or it overhangs the face edge. "
            "Reduce the counterbore depth or diameter, or move the hole inward."
        )
    return result


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
    tool: Solid = Solid.make_cone(
        mouth_radius,
        bore_radius,
        span + cone_depth,
        Plane(origin=origin, x_dir=face_plane.x_dir, z_dir=into),
    )

    before = float(body.volume)
    result = combine_body(body, tool, "cut")
    removed = before - float(result.volume)

    expected = (
        math.pi
        * cone_depth
        / 3.0
        * (radius * radius + radius * bore_radius - 2.0 * bore_radius * bore_radius)
    )
    if removed < expected * (1.0 - _POCKET_REL_TOL):
        raise HoleTooDeepError(
            "The countersink recess could not form its full cone: the removed "
            f"material is short of a diameter-{csink_diameter_mm}mm, "
            f"{csink_angle_deg}deg countersink. The implied cone depth exceeds the "
            "available material (it would break through), or it overhangs the face "
            "edge. Reduce the countersink diameter/angle, or move the hole inward."
        )
    return result
