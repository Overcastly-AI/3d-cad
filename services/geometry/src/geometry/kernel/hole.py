"""Cylindrical hole (drill) — a face-placed blind pocket or through cut.

The kernel half of the Hole feature (slice 1 — the simple hole). The feature
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
    """A blind hole could not form its full pocket (over-deep / edge-overhang)."""


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
    normal = face_plane.z_dir
    point = Vector(*position)
    # Project the placement point onto the face plane so the axis is perpendicular
    # to the face and the bore is clean even if the pick lands a hair off-plane.
    center = point - normal * (point - face_plane.origin).dot(normal)

    # Start the tool OUTSIDE the face and drill inward. A bounding-box diagonal is
    # a pure, deterministic function of the body and always clears it, so no
    # ad-hoc epsilon and no coincident-face boolean at the opening.
    span = body.bounding_box().diagonal
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
