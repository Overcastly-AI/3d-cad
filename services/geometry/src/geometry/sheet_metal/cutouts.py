"""Through-features carried INTO the flat pattern (DXF-4).

The defect this module closes, in the product audit's words: a bracket with four
Ø5.5 through holes exported a flat pattern with *six entities, zero CIRCLEs* — four
outline lines and two fold lines. Sent to a laser that is a blank rectangle with two
scribe lines and no holes, and the shop cuts scrap. The unfold developed the OUTER
boundary and nothing else; the DXF writer was innocent (the on-screen Flat Pattern
showed the same bare rectangle, because both read the SAME
:class:`~geometry.sheet_metal.FlatPattern` — one derivation, two renderers).

**What this module is.** The unfold's layout paths are analytic: they place a base
flange and its legs from scalars (developed length, width, bend allowance) and emit a
rectilinear outline. Nothing in that arithmetic ever looks at the interior of a face.
So a layout path that wants its interior cuts developed publishes, per FLAT region of
the blank, the rigid map from that region's 3D plane into the developed ``(u, v)``
frame it placed the region at (:class:`DevelopedRegion`) — and this module maps the
region's faces' INNER WIRES through it. The layout arithmetic is untouched, which is
why every hole-free golden stays byte-identical.

**Never a silently wrong blank (sheet-metal.md §5).** A blank whose holes are missing
is more dangerous than no blank at all, because it looks finished. So the accounting
here is TOTAL: every inner wire on every planar face of the body must be developed, or
the unfold refuses with a typed :class:`UnfoldCutoutError`. Every refusal is a case
where the developed position would be a GUESS:

* a cut on a layout path that publishes no regions (the depth-2 tree, the relieved
  tray, the partial-width star — documented follow-ons);
* a cut whose loops lie on a CURVED face — through a bend, or through a rolled section:
  no flat run contains it, so it has no developed position;
* a cut on a planar face that belongs to no published region (a cut through the sheet's
  thickness edge);
* a cut on a face TWO regions can honestly claim, where a 180-degree fold lands one
  flat run back on top of another (a hem);
* a BLIND cut — a pocket, an emboss, a countersink — which appears on one face of the
  sheet and not the other, and is not a cut path at all;
* a loop this module cannot express (a spline / ellipse interior).

**Through-ness is measured, not assumed.** A through cut breaks BOTH faces of the
sheet, and because the drill axis is normal to the sheet, the two loops land on the
same developed ``(u, v)`` — bit-identical in the axis-aligned case and FP-close in
general. So the loops are paired: each developed loop must have exactly one partner
within :data:`CUT_MATCH_TOL_MM`, and one copy of the pair is emitted. A pocket has no
partner and refuses; that is the same posture as the WF-1 fold-back cross-check, which
proves a developed FOLD against the live body rather than trusting the development.

Determinism (RESEARCH §9): OCCT's face and wire iteration order is not part of the
contract, so every loop is reduced to a canonical tuple of floats and the emitted
edges are sorted by it. The output is a pure function of the geometry.
"""

from __future__ import annotations

# The OCP wheel ships no type stubs, so build123d's ``Vector``/``Edge`` members are
# opaque to pyright. The directives scope that relaxation to this file only — exactly
# as :mod:`geometry.sheet_metal.unfold` does — and the frozen DTOs this module emits
# keep the boundary honest.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
from dataclasses import dataclass
from typing import NamedTuple

from build123d import CenterOf, Edge, Face, GeomType, Vector, Wire

from geometry.kernel.types import BodyShape
from geometry.sheet_metal.flat_pattern import FlatCutEdge2D
from geometry.sheet_metal.resolve import SheetMetalUnfoldError

Vec3f = tuple[float, float, float]


class UnfoldCutoutError(SheetMetalUnfoldError):
    """An interior cut exists that this unfold cannot place in the developed blank.

    Typed so the flat-pattern view degrades to ``flat_pattern_failed`` (a per-view
    error inside a 200) rather than shipping a blank with the holes missing.
    """


#: Pairing tolerance for the two loops one through-cut leaves on the two faces of the
#: sheet (mm). Documented, NOT ad-hoc (CLAUDE.md / §9): both loops are the trace of ONE
#: cutting tool whose axis is normal to the sheet, so their developed ``(u, v)`` differ
#: only by floating-point residue in the shared rigid map — measured at 0.0 exactly for
#: the axis-aligned goldens and bounded by the map's own conditioning otherwise. This is
#: the same measurement class as ``unfold._FOLD_BACK_WIDTH_TOL_MM`` (1e-6 mm, the
#: subshape linear tolerance class): ample FP headroom, yet four-plus orders below any
#: real feature — no two distinct holes in a real part sit a micron apart.
CUT_MATCH_TOL_MM = 1e-6

#: Containment slack when deciding which region a cut-bearing face belongs to (mm).
#: A cut lies strictly inside its region; the slack only absorbs the same FP residue
#: the map above carries, so it is the same documented number.
REGION_CONTAINS_TOL_MM = 1e-6

#: ``1 - |dot|`` between unit normals still considered parallel — the module-wide
#: direction tolerance the rest of the sheet-metal code uses (``unfold._PARALLEL_TOL``
#: / ``resolve._PARALLEL_TOL``), repeated here rather than imported to keep this module
#: free of a cycle back into :mod:`geometry.sheet_metal.unfold`.
PARALLEL_TOL = 1e-9


@dataclass(frozen=True)
class DevelopedRegion:
    """The rigid map from ONE flat 3D region of the sheet into developed ``(u, v)``.

    A "region" is a flat run of the sheet that the layout placed as a unit: the base
    flange, or one flange leg. Its two faces (the sheet's two skins, ``thickness`` mm
    apart) share this map, because a through cut's two loops must develop to the same
    place — mapping each skin in its own frame is exactly the second placement path
    the DXF module's ``_DxfFrame`` docstring warns about, in a different coordinate
    system.

    The map is::

        u = u_anchor + u_sign * (p . u_dir - u_ref)
        v = v_anchor +          (p . v_dir - v_ref)

    ``u_sign`` is ``-1`` for a leg the layout placed on the DECREASING-u side of the
    base (a left flange in the 1D strip), where developed distance grows as the 3D
    coordinate shrinks. There is no ``v_sign``: a fold preserves the coordinate along
    its own bend axis, so every region of a parallel star shares one ``v`` direction.

    The developed frame is right-handed with the base flange's outward normal as
    ``+z`` (``u = axis x n``, ``v = axis``), so the blank is always seen from the side
    the flanges fold TOWARD. That makes the frame invariant to the sign OCCT happens
    to give the bend axis: flipping the axis rotates the blank 180 degrees, it never
    MIRRORS it — and a mirrored cut path is scrap, while a rotated one is a nesting
    detail.
    """

    normal: Vec3f
    plane_point: Vec3f
    thickness_mm: float
    u_dir: Vec3f
    v_dir: Vec3f
    u_ref: float
    u_anchor: float
    u_sign: float
    v_ref: float
    v_anchor: float
    u_span: tuple[float, float]
    v_span: tuple[float, float]
    #: The developed area the LAYOUT charged for this region — the exact B-rep area of
    #: the face it measured, on the unfold's CLEAN reference body. Recorded so the
    #: blank's ``flat_area_mm2`` can be reconciled against the LIVE body: the reference
    #: body is frozen at the last fold, so a hole drilled after the last flange is
    #: missing from it and the developed area would over-count the material by exactly
    #: that hole. Where the two bodies agree (every hole-free part, and every part whose
    #: cuts predate its last fold) the reconciliation is exactly 0.0 and the pattern is
    #: byte-identical.
    layout_area_mm2: float = 0.0

    def develop(self, point: Vector) -> tuple[float, float]:
        """One 3D point of this region as a developed ``(u, v)`` (mm)."""
        pu = point.X * self.u_dir[0] + point.Y * self.u_dir[1] + point.Z * self.u_dir[2]
        pv = point.X * self.v_dir[0] + point.Y * self.v_dir[1] + point.Z * self.v_dir[2]
        return (
            self.u_anchor + self.u_sign * (pu - self.u_ref),
            self.v_anchor + (pv - self.v_ref),
        )

    def holds(self, face_normal: Vector, face_centroid: Vector) -> bool:
        """True iff a planar face is one of THIS region's two skins.

        Three tests, all necessary: the face is parallel to the region's plane (a
        thickness edge or a bend-adjacent chamfer is not); it lies within one sheet
        thickness of that plane (the far skin does, the flange's own rim does not);
        and its centroid develops INSIDE the region's placed extent (the other legs of
        the star are parallel and one thickness apart only in a fold-back, so the
        extent is what separates them).
        """
        n = Vector(*self.normal)
        if 1.0 - abs(face_normal.dot(n)) > PARALLEL_TOL:
            return False
        origin = Vector(*self.plane_point)
        if abs((face_centroid - origin).dot(n)) > self.thickness_mm + CUT_MATCH_TOL_MM:
            return False
        u, v = self.develop(face_centroid)
        tol = REGION_CONTAINS_TOL_MM
        return (
            self.u_span[0] - tol <= u <= self.u_span[1] + tol
            and self.v_span[0] - tol <= v <= self.v_span[1] + tol
        )

    def is_measured_skin(self, face_normal: Vector, face_centroid: Vector) -> bool:
        """True iff a face is the skin the LAYOUT measured — same side, not the far one.

        The two skins of a fold's flanking region do not have to develop to the same
        length (the inner one runs to a different tangent line), so the reconciliation
        of :attr:`layout_area_mm2` has to compare like with like.
        """
        n = Vector(*self.normal)
        return face_normal.dot(n) > 0.0 and self.holds(face_normal, face_centroid)


#: A loop reduced to a canonical, sortable tuple of floats: ``(edge_count, then each
#: edge's descriptor)``. Two loops of the same cut agree on it to FP residue.
_LoopKey = tuple[float, ...]


def _developed_edge(
    region: DevelopedRegion, edge: Edge
) -> tuple[FlatCutEdge2D, tuple[float, ...]]:
    """One kernel edge of an interior wire as a developed cut edge + its sort key.

    Both the emitted edge and the key are made ORIENTATION- and SEAM-independent,
    which matters more here than anywhere else in the unfold: the two loops being
    matched bound OPPOSITE-facing faces, so OCCT walks them in opposite directions and
    an edge's ``start`` and ``end`` swap between them. Left raw, a rectangular cutout
    would fail to pair and be reported as a blind pocket — a correct part refused for a
    bookkeeping reason. So a segment's endpoints are stored in lexicographic order (a
    cut path has no direction), and a full circle's are DERIVED from its developed
    centre and radius rather than taken from wherever OCCT parked the seam vertex.
    """
    kind = edge.geom_type
    start = region.develop(edge.start_point())
    end = region.develop(edge.end_point())
    mid = region.develop(edge @ 0.5)
    if start > end:
        start, end = end, start
    if kind == GeomType.CIRCLE:
        centre = region.develop(edge.arc_center)
        radius = float(edge.radius)
        if edge.is_closed:
            # Seam-free: the loop IS the centre and the radius. Endpoints coincide at
            # +u of the centre and the "midpoint" sits half a turn away, which is what
            # a diameter dimension and an arc sampler both expect of a full circle.
            return (
                FlatCutEdge2D(
                    kind="circle",
                    x1=centre[0] + radius,
                    y1=centre[1],
                    x2=centre[0] + radius,
                    y2=centre[1],
                    xm=centre[0] - radius,
                    ym=centre[1],
                    cx=centre[0],
                    cy=centre[1],
                    r=radius,
                ),
                (0.0, centre[0], centre[1], radius, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            )
        cut = FlatCutEdge2D(
            kind="arc",
            x1=start[0],
            y1=start[1],
            x2=end[0],
            y2=end[1],
            xm=mid[0],
            ym=mid[1],
            cx=centre[0],
            cy=centre[1],
            r=radius,
        )
        key = (
            1.0,
            centre[0],
            centre[1],
            radius,
            start[0],
            start[1],
            end[0],
            end[1],
            mid[0],
            mid[1],
        )
        return cut, key
    if kind == GeomType.LINE:
        cut = FlatCutEdge2D(
            kind="line",
            x1=start[0],
            y1=start[1],
            x2=end[0],
            y2=end[1],
            xm=mid[0],
            ym=mid[1],
        )
        key = (2.0, start[0], start[1], end[0], end[1], mid[0], mid[1], 0.0, 0.0, 0.0)
        return cut, key
    curve = str(kind).split(".")[-1].lower()
    raise UnfoldCutoutError(
        f"An interior cut in this part is bounded by a {curve} curve; the flat pattern "
        "develops straight, circular and arc cut edges only, so developing this blank "
        "would either drop the cut or approximate it. Replace the cut with lines and "
        "arcs, or export the folded body."
    )


def _developed_loop(
    region: DevelopedRegion, wire: Wire
) -> tuple[tuple[FlatCutEdge2D, ...], _LoopKey]:
    """One interior wire as developed cut edges, in canonical (sorted) order."""
    developed = [_developed_edge(region, edge) for edge in wire.edges()]
    developed.sort(key=lambda item: item[1])
    key: list[float] = [float(len(developed))]
    for _cut, edge_key in developed:
        key.extend(edge_key)
    return tuple(cut for cut, _k in developed), tuple(key)


def _keys_match(a: _LoopKey, b: _LoopKey) -> bool:
    """Two developed loops are the SAME cut seen from the sheet's two skins."""
    if len(a) != len(b):
        return False
    return all(abs(x - y) <= CUT_MATCH_TOL_MM for x, y in zip(a, b, strict=True))


class DevelopedCuts(NamedTuple):
    """The blank's interior cut edges plus the developed-area correction they imply."""

    edges: tuple[FlatCutEdge2D, ...] = ()
    #: ``live region area - layout region area``, summed. Zero (exactly) whenever the
    #: unfold's reference body and the live body agree about the blank's material.
    area_delta_mm2: float = 0.0


def _planar_faces(body: BodyShape) -> list[tuple[Face, Vector, Vector, list[Wire]]]:
    """``(face, outward normal, area centroid, inner wires)`` per planar face.

    A NON-planar face carrying an interior loop refuses here rather than being skipped.
    Only a FLAT region of the sheet has a rigid map into the developed blank, so a
    curved face's interior loop has no developed position at all — but skipping it is
    indistinguishable, to everything downstream, from the face having no loop, and the
    result is a blank that looks finished with a cut missing from it. That is DXF-4
    itself, so the accounting has to be over EVERY face of the body, not over the ones
    this module knows how to develop. Measured: a Ø2 cut through the bend region of the
    ``holed-bracket`` fixture leaves its two loops entirely on the bend's cylindrical
    skins, and a planar-only scan developed the four drilled holes and shipped the
    fifth cut as a blank rectangle of bend.
    """
    found: list[tuple[Face, Vector, Vector, list[Wire]]] = []
    for face in body.faces():
        if face.geom_type != GeomType.PLANE:
            if face.inner_wires():
                raise UnfoldCutoutError(
                    "An interior cut passes through a CURVED region of this part (a "
                    "bend, or a rolled section): its loops lie on a surface the blank "
                    "does not develop as a flat run, so the cut has no developed "
                    "position. The blank is refused rather than exported with the cut "
                    "missing from it (sheet-metal.md §5). Move the cut clear of the "
                    "bend, or export the folded body."
                )
            continue
        centroid = face.center(CenterOf.MASS)
        found.append(
            (face, face.normal_at(centroid), centroid, list(face.inner_wires()))
        )
    return found


def _area_reconciliation(
    planar: list[tuple[Face, Vector, Vector, list[Wire]]],
    regions: tuple[DevelopedRegion, ...],
) -> float:
    """How much the LIVE body disagrees with the layout about the blank's material.

    See :attr:`DevelopedRegion.layout_area_mm2`. A region whose measured skin cannot be
    found on the live body contributes nothing — the layout's own number stands, which
    is the honest answer when the live body no longer carries that face at all.
    """
    delta = 0.0
    for region in regions:
        skins = [
            face
            for face, normal, centroid, _inner in planar
            if region.is_measured_skin(normal, centroid)
        ]
        if len(skins) > 1:
            raise UnfoldCutoutError(
                "Two faces of the live body occupy the same developed region of the "
                "blank (a fold that lands material back on itself). The developed "
                "position of any cut there is ambiguous, so the blank is refused "
                "rather than exported with the cuts stacked (sheet-metal.md §5)."
            )
        if skins:
            delta += float(skins[0].area) - region.layout_area_mm2
    return delta


def develop_cutouts(
    body: BodyShape, regions: tuple[DevelopedRegion, ...]
) -> DevelopedCuts:
    """Develop every interior cut of *body* into the blank, or refuse (DXF-4).

    *regions* is what the layout path published; an empty tuple means the path has no
    developed map yet, which is a refusal the moment the body actually has a cut (and a
    no-op — an empty result, every golden byte-identical — when it does not).

    Raises:
        UnfoldCutoutError: a cut exists that cannot be placed in the developed blank —
            unmapped region, blind pocket, or an unsupported curve. Never returns a
            blank with a cut missing from it.
    """
    planar = _planar_faces(body)
    bearing = [entry for entry in planar if entry[3]]
    if not bearing:
        return DevelopedCuts()
    if not regions:
        raise UnfoldCutoutError(
            "This part has interior cuts (holes / cutouts) and its blank develops "
            "through a layout that cannot yet place them — a relieved tray, a "
            "partial-width flange, or a depth-2 bend chain. A flat pattern missing its "
            "holes is scrap at the laser, so it is refused rather than exported "
            "(sheet-metal.md §5)."
        )

    loops: list[tuple[_LoopKey, tuple[FlatCutEdge2D, ...], int]] = []
    for face_index, (_face, normal, centroid, inner) in enumerate(bearing):
        holders = [r for r in regions if r.holds(normal, centroid)]
        if not holders:
            raise UnfoldCutoutError(
                "An interior cut sits on a face the flat pattern does not develop as "
                "part of the blank — a cut through a bend region or through the "
                "sheet's thickness. The developed position of such a cut is not "
                "defined by this unfold, so the blank is refused rather than exported "
                "with the cut in a guessed place (sheet-metal.md §5)."
            )
        if len(holders) > 1:
            # A 180-degree fold (a hem, or a flange folded flat back over its base) puts
            # two flat runs one thickness apart AND overlapping in developed (u, v), so
            # a face can honestly belong to either. Taking the first would place the cut
            # on whichever run OCCT happened to enumerate first — a coin flip, and the
            # DXF-4 defect in a subtler form. Refuse instead.
            raise UnfoldCutoutError(
                "An interior cut sits where two flat runs of the blank fold back onto "
                "each other (a hem, or a flange folded flat over its base), so which "
                "run the cut belongs to is ambiguous. The blank is refused rather than "
                "exported with the cut on a guessed run (sheet-metal.md §5)."
            )
        region = holders[0]
        for wire in inner:
            cuts, key = _developed_loop(region, wire)
            loops.append((key, cuts, face_index))

    # Pair the two skins' loops. Sorting by the canonical key puts a cut's two traces
    # adjacent, because they agree to FP residue and nothing else in a real part is
    # within a micron of them.
    loops.sort(key=lambda item: item[0])
    emitted: list[FlatCutEdge2D] = []
    index = 0
    while index < len(loops):
        key, cuts, face_index = loops[index]
        if index + 1 >= len(loops) or not _keys_match(key, loops[index + 1][0]):
            raise UnfoldCutoutError(
                "This part has a BLIND interior feature (a pocket, an emboss or a "
                "counterbore): it breaks one face of the sheet and not the other, so "
                "it is not a cut path. A flat pattern is what the laser cuts; a blind "
                "feature has to be formed, not cut, and cannot be exported as an "
                "outline (sheet-metal.md §5)."
            )
        if loops[index + 1][2] == face_index:
            raise UnfoldCutoutError(
                "Two coincident interior cuts develop to the same place on the SAME "
                "face of the sheet; the blank would be ambiguous, so it is refused "
                "rather than exported with one of them dropped (sheet-metal.md §5)."
            )
        emitted.extend(cuts)
        index += 2
    return DevelopedCuts(tuple(emitted), _area_reconciliation(planar, regions))


def parallel_star_regions(
    *,
    base_face: Face,
    base_normal: Vector,
    u_axis: Vector,
    v_axis: Vector,
    thickness_mm: float,
    base_u_anchor: float,
    base_len: float,
    base_area: float,
    base_width: float,
    legs: tuple[tuple[Face, Vector, Vector, float, float, float], ...],
) -> tuple[DevelopedRegion, ...]:
    """The developed regions of a 1D-strip (all-parallel) star — base + each leg.

    *legs* is one entry per bend: ``(flange face, its outward normal, the bend axis
    ORIGIN, the developed u of the leg's bend-adjacent end, the leg's u sign, the
    developed area the layout charged for it)``. The
    bend axis origin is what fixes the leg's own origin without guessing: a flange face
    is TANGENT to the bend cylinder, and the foot of the perpendicular from the axis to
    a tangent plane has the SAME in-plane ``u`` as the axis itself — so the tangent line
    (where the leg meets its bend allowance strip) is exactly at ``axis_origin . u``.
    That holds at any fold angle, where "the end nearer the base plane" does not (a
    fold-back past 90 degrees brings both ends to a similar height).
    """
    base_u = [Vector(v.X, v.Y, v.Z).dot(u_axis) for v in base_face.vertices()]
    base_v = [Vector(v.X, v.Y, v.Z).dot(v_axis) for v in base_face.vertices()]
    u_ref, v_ref = min(base_u), min(base_v)
    base_centroid = base_face.center(CenterOf.MASS)
    regions = [
        DevelopedRegion(
            normal=(base_normal.X, base_normal.Y, base_normal.Z),
            plane_point=(base_centroid.X, base_centroid.Y, base_centroid.Z),
            thickness_mm=thickness_mm,
            u_dir=(u_axis.X, u_axis.Y, u_axis.Z),
            v_dir=(v_axis.X, v_axis.Y, v_axis.Z),
            u_ref=u_ref,
            u_anchor=base_u_anchor,
            u_sign=1.0,
            v_ref=v_ref,
            v_anchor=0.0,
            u_span=(base_u_anchor, base_u_anchor + base_len),
            v_span=(0.0, base_width),
            layout_area_mm2=base_area,
        )
    ]
    for face, normal, axis_origin, dev_anchor, dev_sign, leg_area in legs:
        leg_u_axis = v_axis.cross(normal).normalized()
        projected = [Vector(v.X, v.Y, v.Z).dot(leg_u_axis) for v in face.vertices()]
        lo, hi = min(projected), max(projected)
        tangent = axis_origin.dot(leg_u_axis)
        # The leg runs AWAY from the tangent line; whichever extreme is not the tangent
        # end is the far end, so the 3D direction of "away" is decided by measurement.
        away = 1.0 if abs(hi - tangent) > abs(lo - tangent) else -1.0
        near = lo if away > 0.0 else hi
        length = abs(hi - lo)
        centroid = face.center(CenterOf.MASS)
        u_lo = min(dev_anchor, dev_anchor + dev_sign * length)
        regions.append(
            DevelopedRegion(
                normal=(normal.X, normal.Y, normal.Z),
                plane_point=(centroid.X, centroid.Y, centroid.Z),
                thickness_mm=thickness_mm,
                u_dir=(leg_u_axis.X, leg_u_axis.Y, leg_u_axis.Z),
                v_dir=(v_axis.X, v_axis.Y, v_axis.Z),
                u_ref=near,
                u_anchor=dev_anchor,
                u_sign=dev_sign * away,
                v_ref=v_ref,
                v_anchor=0.0,
                u_span=(u_lo, u_lo + length),
                v_span=(0.0, base_width),
                layout_area_mm2=leg_area,
            )
        )
    return tuple(regions)
