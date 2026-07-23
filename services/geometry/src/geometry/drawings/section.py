"""Planar full section of a single-body part — the section-view kernel op.

docs/design/drawings-section.md (v1: a single PLANAR FULL section of a single-body
part, cut by a plane whose NORMAL is a principal axis). Given the evaluated body
and a resolved cutting :class:`~build123d.Plane`, this module:

1. resolves the flip/normal/half-space convention ONCE
   (:func:`resolve_section_frame`, design §4) — the standard view direction the cut
   normal maps to plus the sign of the half-space to remove;
2. builds the half-space tool SIZED AND POSITIONED from the body's world bounding
   box on the eye side of the plane (design §3 / audit 🟡3 — never centred at the
   plane origin, or an off-centre datum notches instead of halving);
3. cuts through the SHIPPED disjoint-tolerant boolean surface
   (``boolean_bodies(..., allow_disjoint=True)``, §MB-4) — a valid section legitimately
   severs the body into lumps, all of which are kept and ``clean()``ed (design §2);
4. extracts the coplanar section face(s) from the cleaned lumps and canonicalises
   their boundary loops into byte-stable projected 2D polylines (design §6) — the
   region the compose layer hatches (design §5).

Pure, deterministic, kernel-only (RESEARCH §9): same body + plane + flip ⇒
byte-identical remaining body, view direction, and section loops. The drawings
evaluate layer maps the result to neutral DTOs — no kernel type crosses the
service boundary (CLAUDE.md).

Honest degradation (design §7): the axis guard, a plane that misses the solid, and
a whole-body removal are each a typed error caught BEFORE HLR — never a crash,
never a silently-wrong section.
"""
# The OCP wheel ships no type stubs, so the raw build123d face/wire calls below are
# opaque to pyright; scope that relaxation to this file (the project.py / edges.py
# posture). The fully-typed BodyShape input + Point2D output keep the boundary honest.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownParameterType=false

from __future__ import annotations

from dataclasses import dataclass

from build123d import Face, Plane, Pos, Solid, Wire

from geometry.drawings.project import Point2D, ViewDirection, project_point
from geometry.kernel.boolean import BooleanEmptyError, boolean_bodies
from geometry.kernel.types import BodyShape

#: v1 axis-aligned-normal guard (design §1): the cut normal must be within this of a
#: principal axis (``max|N.axis| >= 1 - tol``), so N is already a standard view
#: direction and no ``project_view`` frame generalisation is needed. Sized to the
#: kernel linear/direction tolerance (1e-7), the ``project.py`` axis-parallel twin.
_AXIS_PARALLEL_TOL = 1e-7

#: Coplanar section-face tolerances (design §2 step 3, the spike's proven bounds):
#: a face is a section face iff its normal is parallel to the cut normal (angular
#: ``|.n.| within`` this of 1) AND a point on it satisfies the plane equation
#: (linear, mm). The kernel 1e-7 / 1e-6 pair, never an ad-hoc epsilon.
_FACE_NORMAL_TOL = 1e-7
_FACE_PLANE_TOL = 1e-6

#: Volume-equality bound (mm^3) separating a plane that MISSES the body (the cut
#: removed nothing → remaining volume equals the body's) from a coincident-face
#: degenerate section (design §7). Sized well above kernel volume jitter and well
#: below any authored feature volume — the same dead-middle posture as the datum
#: parallel bound (kernel/datum.py).
_MISS_VOLUME_TOL = 1e-6

#: Per-wire sample count for a section face's boundary loop → projected polyline
#: (design §6). Fixed (not ad-hoc) so the polyline — and therefore the hatch clip
#: over it — is byte-deterministic; a curved (bored) loop samples smooth, a straight
#: loop over-samples harmlessly (collinear points never change the scanline spans).
_LOOP_SAMPLES = 128

#: Cut normal axis (0=X, 1=Y, 2=Z) → the standard view direction whose pinned frame
#: normal shares that axis (design §4). Front is viewed along Y, Top along Z, Right
#: along X — keyed off the AXIS, never the datum's arbitrary normal SIGN.
_AXIS_TO_VIEW: dict[int, ViewDirection] = {0: "right", 1: "front", 2: "top"}


class SectionError(RuntimeError):
    """Base class for a section that cannot be produced honestly (design §7)."""


class SectionPlaneNotPrincipalError(SectionError):
    """The cut normal is not (within tol of) a principal axis — out of v1 scope.

    v1 constrains N to a standard view direction so no ``project_view`` frame
    refactor is needed (design §0/§1); an oblique datum becomes valid when the §11
    frame refactor lands. Maps to the typed ``section_plane_not_principal`` per-view
    error — fails fast, never a bad frame silently projected.
    """


class SectionMissesBodyError(SectionError):
    """The cutting plane does not intersect the solid (design §7).

    The half-space removed nothing (the plane is offset past the body), so there is
    no cross-section to hatch. Maps to the typed ``section_plane_misses_body``.
    """


class SectionEmptyError(SectionError):
    """The section removed all material, or left no cross-section face (design §7).

    Either the eye-side half-space swallowed the whole body (``boolean_bodies`` raised
    :class:`BooleanEmptyError`), or the plane sits coincident with a face and produces
    no cut face. Maps to the typed ``section_empty``.
    """


@dataclass(frozen=True)
class SectionLoop2D:
    """One section-face boundary as canonical projected 2D polylines (design §6).

    ``outer`` is the face's outer wire; ``holes`` the interior (bore) wires — each a
    closed polyline in the view plane (view mm at the request scale), pinned to a
    deterministic start vertex and a fixed winding (outer CCW, holes CW in the view
    frame) so the emitted geometry is byte-stable regardless of OCCT's edge order.
    """

    outer: tuple[Point2D, ...]
    holes: tuple[tuple[Point2D, ...], ...]


@dataclass(frozen=True)
class SectionCut:
    """The result of a section cut (design §2) — kernel-only, never crosses a boundary.

    ``remaining`` is the body behind the cut (the eye-side half removed) fed to the
    shipped HLR seam; ``view`` is the standard view direction the cut normal maps to
    (design §4); ``loops`` are the canonical projected cross-section boundaries the
    compose layer hatches (design §5/§6).
    """

    remaining: BodyShape
    view: ViewDirection
    loops: tuple[SectionLoop2D, ...]


def resolve_section_frame(plane: Plane, flip: bool) -> tuple[ViewDirection, int, int]:
    """The single-sourced flip / normal / half-space convention (design §4).

    Returns ``(view, axis, tool_sign)``:

    * ``axis`` = ``argmax(|N.X|, |N.Y|, |N.Z|)`` — the principal axis of the cut
      normal ``N = plane.z_dir`` (guarded to be axis-aligned, §1);
    * ``view`` = the standard view direction whose frame normal shares ``axis``
      (:data:`_AXIS_TO_VIEW`) — keyed off the AXIS, not the datum's normal sign, so
      the convention is single-valued (``Plane.XZ`` has ``z_dir=+Y`` yet is viewed
      from the ``front`` eye at ``-Y``);
    * ``tool_sign`` = ``+1`` if ``not flip`` else ``-1`` — ``+1`` removes the
      EYE-side half (the standard "cut away what is between you and the plane"),
      ``-1`` the far side.

    Everything downstream (which half the tool occupies, the view direction) DERIVES
    from this triple — the pre-audit two-way statement collapses to one function.

    Raises:
        SectionPlaneNotPrincipalError: ``N`` is not within tol of a principal axis.
    """
    n = plane.z_dir.normalized()
    comps = (abs(n.X), abs(n.Y), abs(n.Z))
    axis = max(range(3), key=lambda i: comps[i])
    if comps[axis] < 1.0 - _AXIS_PARALLEL_TOL:
        raise SectionPlaneNotPrincipalError(
            "The section cutting plane's normal is not aligned with a principal axis "
            f"(|N.axis| = {comps[axis]:.6f} < 1). v1 supports a section whose normal "
            "is X, Y, or Z (a principal or axis-aligned offset datum); an oblique "
            "cutting plane is deferred (drawings-section.md §11)."
        )
    return _AXIS_TO_VIEW[axis], axis, (1 if not flip else -1)


def _half_space_tool(
    body: BodyShape, plane: Plane, axis: int, tool_sign: int
) -> Solid | None:
    """The eye-side half-space subtract tool, sized/positioned from the body bbox.

    v1's cut normal is axis-aligned (the §1 guard), so the tool is an axis-aligned
    world box that covers the body's full extent in the two off-axis directions
    (padded) and, along the cut axis, spans from the cut plane's coordinate out past
    the body on the side selected by ``tool_sign`` times the plane's normal sign (design
    §3/§4). Positioning from the PROJECTED bbox — never the plane origin — is what
    makes an off-centre (offset / midplane) datum a clean HALF cut, not a notch
    (audit 🟡3). Subtracting it keeps the far half with the cut face exposed at the
    plane.

    Returns ``None`` when the removal region does not reach the body at all (the
    plane is offset PAST the body on the removed side): the cut is then a no-op and
    the caller reports an honest ``section_plane_misses_body`` (design §7) — never a
    degenerate/negative-extent box.
    """
    bb = body.bounding_box()
    lo = (bb.min.X, bb.min.Y, bb.min.Z)
    hi = (bb.max.X, bb.max.Y, bb.max.Z)
    origin = (plane.origin.X, plane.origin.Y, plane.origin.Z)
    normal = plane.z_dir.normalized()
    normal_sign = 1.0 if (normal.X, normal.Y, normal.Z)[axis] >= 0 else -1.0
    # Which world direction along `axis` the removed half occupies: tool_sign selects
    # eye vs far relative to the plane's own normal sign (a single derived sign, §4).
    remove_dir = tool_sign * normal_sign
    pad = (bb.max - bb.min).length + 1.0  # provably exceeds the body in every axis

    box_min = [lo[i] - pad for i in range(3)]
    box_max = [hi[i] + pad for i in range(3)]
    cut = origin[axis]
    # Clamp the removed half to the padded bbox interval along the cut axis. A cut
    # coordinate beyond the padded body on the removed side collapses the interval →
    # the tool would remove nothing (the plane missed): return None.
    if remove_dir >= 0:
        box_min[axis] = cut  # box starts at the plane, extends +axis past the body
    else:
        box_max[axis] = cut  # box ends at the plane, extends -axis past the body
    if box_max[axis] - box_min[axis] <= 0.0:
        return None
    size = [box_max[i] - box_min[i] for i in range(3)]
    return Solid.make_box(size[0], size[1], size[2]).locate(
        Pos(box_min[0], box_min[1], box_min[2])
    )


def _coplanar_section_faces(remaining: BodyShape, plane: Plane) -> list[Face]:
    """The faces of *remaining* lying ON *plane* — the cross-section to hatch (§2).

    A face is a section face iff its normal is parallel to the cut normal AND a point
    on it satisfies the plane equation (kernel tolerances). Enumerated over the
    CLEANED lumps of the cut (spike-proven), in OCCT face order — the caller
    canonicalises each into a byte-stable loop, so the enumeration order does not
    leak into the output.
    """
    n = plane.z_dir.normalized()
    d = n.dot(plane.origin)
    out: list[Face] = []
    for face in remaining.faces():
        fn = face.normal_at()
        if abs(abs(fn.dot(n)) - 1.0) > _FACE_NORMAL_TOL:
            continue
        if abs(n.dot(face.center()) - d) > _FACE_PLANE_TOL:
            continue
        out.append(face)
    return out


def _signed_area(pts: list[Point2D]) -> float:
    """The shoelace signed area of a closed 2D polyline (CCW positive)."""
    area = 0.0
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        area += a.x * b.y - b.x * a.y
    return 0.5 * area


def _canonical_loop(
    wire: Wire, view: ViewDirection, scale: float, *, outer: bool
) -> tuple[Point2D, ...]:
    """One boundary wire → a canonical projected 2D polyline (design §6).

    Sample the whole wire uniformly (``wire @ (i/N)`` — connected, ordered, a pure
    function of the wire) and project each point into the view plane through the SAME
    frame as the HLR edges (:func:`project_point`). Then pin determinism two ways:

    * **winding** — outer loops are forced CCW, holes CW in the view frame (a fixed
      sign, never OCCT's edge orientation);
    * **start vertex** — rotated so the lexicographically smallest projected point is
      first.

    So the polyline is byte-stable regardless of OCCT's edge-enumeration order.
    """
    pts = [
        project_point(view, _wire_point(wire, i / _LOOP_SAMPLES), scale)
        for i in range(_LOOP_SAMPLES)
    ]
    # Winding: outer CCW (area > 0), holes CW (area < 0) in the right-handed view
    # frame (x right, y up = N x x_dir). Reverse to the canonical sense if needed.
    area = _signed_area(pts)
    if (outer and area < 0.0) or (not outer and area > 0.0):
        pts.reverse()
    # Start-vertex pin: rotate so the lexicographically smallest (x, y) leads.
    k = min(range(len(pts)), key=lambda i: (pts[i].x, pts[i].y))
    return tuple(pts[k:] + pts[:k])


def _wire_point(wire: Wire, t: float) -> tuple[float, float, float]:
    """A world point at parameter ``t in [0, 1)`` along a wire (build123d ``@``)."""
    p = wire @ t
    return (float(p.X), float(p.Y), float(p.Z))


def section_cut(
    body: BodyShape, plane: Plane, *, flip: bool = False, scale: float = 1.0
) -> SectionCut:
    """Cut a single-body part with a principal-plane section (design §2).

    Resolves the §4 convention, removes the eye-side half through the shipped
    disjoint-tolerant boolean, and returns the remaining body (for HLR) + the view
    direction + the canonical projected cross-section loops (for hatch). Pure and
    deterministic (RESEARCH §9).

    Raises:
        SectionPlaneNotPrincipalError: the cut normal is not axis-aligned (§1/§11).
        SectionEmptyError: the cut removed all material, or left no cut face (§7).
        SectionMissesBodyError: the plane does not intersect the solid (§7).
    """
    view, axis, tool_sign = resolve_section_frame(plane, flip)
    tool = _half_space_tool(body, plane, axis, tool_sign)
    if tool is None:
        # The removed half never reaches the body — the plane is offset past it (§7).
        raise SectionMissesBodyError(
            "The section plane does not intersect the solid (it is offset past the "
            "body); there is no cross-section."
        )
    try:
        remaining = boolean_bodies(body, tool, "subtract", allow_disjoint=True)
    except BooleanEmptyError as exc:
        raise SectionEmptyError(
            "The section plane removed all material (the eye-side half-space "
            "swallowed the whole body); there is nothing to section."
        ) from exc

    faces = _coplanar_section_faces(remaining, plane)
    if not faces:
        # No cross-section face. If the cut removed nothing the plane missed the body;
        # otherwise it grazed a face coincidentally — both honest, never a wrong hatch.
        if abs(remaining.volume - body.volume) < _MISS_VOLUME_TOL:
            raise SectionMissesBodyError(
                "The section plane does not intersect the solid (it is offset past "
                "the body); there is no cross-section."
            )
        raise SectionEmptyError(
            "The section plane produced no cross-section face (it is coincident with "
            "a body face); there is nothing to hatch."
        )

    loops = tuple(
        SectionLoop2D(
            outer=_canonical_loop(face.outer_wire(), view, scale, outer=True),
            holes=tuple(
                _canonical_loop(w, view, scale, outer=False) for w in face.inner_wires()
            ),
        )
        for face in faces
    )
    # Sort loops by their canonical (already-pinned) leading vertex so the loop LIST
    # order is a pure function of geometry, not OCCT face enumeration (design §6).
    loops = tuple(sorted(loops, key=lambda lp: (lp.outer[0].x, lp.outer[0].y)))
    return SectionCut(remaining=remaining, view=view, loops=loops)
