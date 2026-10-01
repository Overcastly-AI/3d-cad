"""Dimension placement: signature matching, label text and annotation geometry.

Split out of :mod:`geometry.drawings.compose` (SPLIT-COMPOSE); a faithful port of
``apps/web/src/drawing/dimensions.ts``. See the ``compose`` module docstring for the
port-parity and determinism contract this module shares.
"""

# The drawings modules were split out of one file (SPLIT-COMPOSE) and share their
# underscore helpers and tokens: underscore here means private to the drawings
# package, not to one module.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from loft_wire.drawings import (
    AngularDimensionParams,
    ComposedArrow,
    ComposedDimension,
    ComposedDimensionError,
    ComposedDimLine,
    ComposedDimText,
    ComposedMeasuredDimension,
    ComposedPoint,
    DiameterDimensionParams,
    DimensionParams,
    EdgeToEdgeMeasurement,
    LinearDimensionParams,
    MeasuredDimension,
    PointToPointMeasurement,
    ProjectedViewEdge,
)
from loft_wire.features import EdgeSignature

from geometry.drawings.layout import (
    _AL,
    _ARC_R,
    _AW,
    _GAP,
    _O,
    _OVER,
    _TXT,
    SvgRect,
    ToSvg,
    Vec2,
    _add,
    _dot,
    _hyp,
    _mul,
    _neg,
    _p2,
    _perp,
    _sub,
    _unit,
)


# ---------------------------------------------------------------------------------
# Signature matching + endpoint correspondence — port of dimensions.ts / layout.ts.
# ---------------------------------------------------------------------------------
def _r3(n: float) -> str:
    return f"{n:.3f}"


def edge_signature_key(sig: EdgeSignature) -> str:
    """Rounded, orientation-independent key for a signature (dimensions.ts)."""

    def pt(p: object) -> str:
        # Vec3 (features.py) — x/y/z full-precision, rounded to 3dp for the key.
        return f"{_r3(p.x)},{_r3(p.y)},{_r3(p.z)}"  # type: ignore[attr-defined]

    return f"{sig.curve}|{pt(sig.end_a)}|{pt(sig.end_b)}|{pt(sig.midpoint)}"


def find_matching_edge(
    edges: Sequence[ProjectedViewEdge], sig: EdgeSignature
) -> ProjectedViewEdge | None:
    """The projected edge whose model source matches ``sig`` (dimensions.ts)."""
    key = edge_signature_key(sig)
    for edge in edges:
        if edge.source_edge is not None and edge_signature_key(edge.source_edge) == key:
            return edge
    return None


def anchored_signature(
    authored: EdgeSignature | None,
    measured: MeasuredDimension,
    *,
    secondary: bool = False,
) -> EdgeSignature | None:
    """The signature to match against the PROJECTED edges — re-anchored (audit N1).

    A dimension names its model edge by the signature the user authored. After a
    rebuild that CHANGED that edge (the plate widened, the hole grew) the authored
    signature no longer describes anything on the sheet, so looking the projected edge
    up by it fails and the dimension vanishes — even once the value itself re-measures
    (:mod:`geometry.drawings.anchor`). So placement uses the CURRENT signature the
    measurement resolved to (:class:`~loft_wire.drawings.DimensionAnchor`,
    ``primary``/``secondary``), falling back to the authored one when the caller
    supplies no anchor (a hand-built :class:`MeasuredDimension` in a unit test, an
    older client) — which keeps every previously-composed sheet byte-identical.
    """
    if measured.anchor is not None:
        resolved = measured.anchor.secondary if secondary else measured.anchor.primary
        if resolved is not None:
            return resolved
    return authored


def dimension_edge_signature(params: DimensionParams) -> EdgeSignature | None:
    """The primary model edge a dimension references (dimensions.ts)."""
    if params.type in ("diameter", "radius"):
        return params.edge  # type: ignore[union-attr]
    if params.type == "linear":
        measurement = params.measurement  # type: ignore[union-attr]
        if measurement.mode == "edge_length":
            return measurement.edge
        if measurement.mode == "edge_to_edge":
            return measurement.edge_a
        return measurement.a.signature
    if params.type == "angular":
        return params.edge_a  # type: ignore[union-attr]
    return None


def _endpoint_projected(edge: ProjectedViewEdge, endpoint: str) -> Vec2 | None:
    """The projected point of a named endpoint of a straight edge (layout.ts)."""
    if (
        edge.primitive != "line"
        or not edge.dimensionable
        or edge.source_edge is None
        or edge.start_is_end_a is None
    ):
        return None
    start_is_a = edge.start_is_end_a
    start_label = "end_a" if start_is_a else "end_b"
    end_label = "end_b" if start_is_a else "end_a"
    if endpoint == start_label:
        return _p2(edge.start)
    if endpoint == end_label:
        return _p2(edge.end)
    return None


def _perpendicular_foot(p: Vec2, a: Vec2, b: Vec2) -> Vec2 | None:
    """The foot of the perpendicular from *p* onto the infinite line through a-b.

    The across-the-wall span an ``edge_to_edge`` dimension draws (FB-10): the second
    projected edge's SUPPORTING LINE is what the distance is measured to, so the
    witness line lands square on it even where the two edges do not overlap (a wall
    whose inner face is shorter than its outer). ``None`` when a-b is degenerate in
    this view (the edge projects end-on) — the caller then stamps the honest
    "cannot be placed in this view" marker rather than drawing a zero-length span.
    """
    d = _sub(b, a)
    if _hyp(d) < 1e-9:
        return None
    u = _unit(d)
    return _add(a, _mul(u, _dot(_sub(p, a), u)))


# ---------------------------------------------------------------------------------
# Value formatting — port of dimensions.ts.
# ---------------------------------------------------------------------------------
def _number_text(value: float, unit: str | None) -> str:
    """Format a measured value — a faithful port of dimensions.ts ``numberText``.

    JS ``Number.prototype.toFixed`` rounds half-UP (ES spec: "ties pick the larger
    n") on the EXACT IEEE-754 value; Python's ``f"{v:.3f}"`` rounds half-to-EVEN.
    They diverge on dyadic ties (``0.0625`` → JS ``"0.063"`` vs Python ``"0.062"``),
    which would stamp a DIFFERENT number in the SVG than the on-screen sheet shows
    for the same dimension. ``Decimal(value)`` uses the EXACT binary value (not
    ``Decimal(str(value))``, whose shortest-repr rounding diverges from ``toFixed``
    for values like ``1.005``), so the composed value stays byte-identical to the
    screen through the DE-1c cutover. Measured values are non-negative, so
    half-away-from-zero == half-up == ``toFixed``'s "larger n".
    """
    exp = Decimal("0.1") if unit == "deg" else Decimal("0.001")
    return str(Decimal(value).quantize(exp, rounding=ROUND_HALF_UP))


def format_dimension_label(dim_type: str, value: float, unit: str | None) -> str:
    """The stamped label with its drafting prefix/suffix (dimensions.ts)."""
    n = _number_text(value, unit)
    if dim_type == "diameter":
        return f"Ø{n}"  # Ø
    if dim_type == "radius":
        return f"R{n}"
    if dim_type == "angular":
        return f"{n}°"  # °
    return n


#: Plain-language sheet phrase per typed dimension-failure code (audit N1). A machinist
#: reads the print, not our error taxonomy, so the sheet says what happened and what to
#: do; the machine-readable ``code`` rides alongside on the wire. An unknown code
#: degrades to its own words rather than to nothing.
_DIM_ERROR_PHRASE: dict[str, str] = {
    "subshape_unresolved": "REFERENCE LOST - RE-PICK THE EDGE",
    "subshape_ambiguous": "REFERENCE AMBIGUOUS - RE-PICK THE EDGE",
    "dimension_wrong_type": "WRONG EDGE TYPE FOR THIS DIMENSION",
    # FB-10: the edges converge, so a "thickness" between them does not exist. The
    # sheet says so in the machinist's words rather than carrying a plausible number.
    "dimension_not_parallel": "EDGES NOT PARALLEL - NO PERPENDICULAR DISTANCE",
    "unmeasured": "NOT MEASURED",
    "dimension_not_placeable": "CANNOT BE PLACED IN THIS VIEW - RE-PICK IT",
}

#: The typed code for an authored dimension that MEASURED fine but whose annotation
#: cannot be drawn on this view (QA-4). Reasons, all one honest bucket because the
#: fix is the same in every case — re-pick the edge in a view that shows it:
#: the (re-anchored) model edge is not among the view's projected edges at all; it is
#: drawn as a primitive this dimension type cannot annotate (a bore rim seen edge-on
#: projects to a LINE, so there is no circle for a Ø to span); a point-to-point
#: endpoint has no projected correspondence; or the placement itself is degenerate
#: (two parallel edges for an angular dimension, a zero-length projected span).
#:
#: Before QA-4 every one of those returned ``None`` and the composer SKIPPED the
#: dimension — the authored dimension vanished from the print with no marker, no
#: caption and no error anywhere in the artifact, which is the one failure mode a
#: shop cannot catch: a drawing that has silently lost a dimension looks exactly like
#: a complete one. It is now a stamped :class:`ComposedDimensionError` like any other
#: (docs/design/drawings.md §3.4).
DIMENSION_NOT_PLACEABLE = "dimension_not_placeable"

#: Offset (mm) of the error caption from its marker: clear of the 2.6 mm marker circle
#: to its right, on the marker's centre line.
_DIM_ERROR_TEXT_DX = 4.2
_DIM_ERROR_TEXT_DY = 0.9

#: Cap height (mm) of the stamped error caption — one notch under the dimension value
#: text (`_TXT`), so a broken dimension speaks without shouting over good ones.
_DIM_ERROR_TEXT_MM = 2.4


def dimension_error_caption(dim_type: str, code: str) -> str:
    """The short, upper-case sheet caption for an unmeasurable dimension (audit N1).

    "LINEAR DIM: REFERENCE LOST - RE-PICK THE EDGE" — the type of dimension that broke
    and, in words, why plus the fix. Stamped beside the marker by all three serializers;
    the 2.6 mm dashed circle with a bare ``!`` was the whole diagnostic before."""
    phrase = _DIM_ERROR_PHRASE.get(code, code.replace("_", " ").upper())
    return f"{dim_type.upper()} DIM: {phrase}"


def _dimension_error(
    dim_type: str, dim_id: object, marker_at: Vec2, code: str
) -> ComposedDimensionError:
    """THE single stamped-error construction (CLAUDE.md DRY): marker + caption.

    Every unmeasurable AND every unplaceable dimension goes through here, so the
    machine-readable ``code``, the plain-words ``message`` and the caption OFFSET are
    identical whichever way a dimension failed — one thing for a serializer to draw
    and one thing for a UI to badge."""
    return ComposedDimensionError(
        dimension_id=dim_id,  # type: ignore[arg-type]
        dimension_type=dim_type,  # type: ignore[arg-type]
        at=ComposedPoint(x_mm=marker_at.x, y_mm=marker_at.y),
        code=code,
        # Words beside the view, not a bare "!" (audit N1) — the dimension-level
        # twin of the typed per-view reason a failed view stamps (FINDINGS #15).
        message=dimension_error_caption(dim_type, code),
        text=ComposedPoint(
            x_mm=marker_at.x + _DIM_ERROR_TEXT_DX,
            y_mm=marker_at.y + _DIM_ERROR_TEXT_DY,
        ),
    )


# ---------------------------------------------------------------------------------
# Annotation geometry — port of dimensions.ts.
# ---------------------------------------------------------------------------------
def _arrow(tip: Vec2, direction: Vec2, to_svg: ToSvg) -> ComposedArrow:
    """An arrowhead triangle: tip at ``tip``, barb pointing ``direction``."""
    base = _sub(tip, _mul(direction, _AL))
    wing = _mul(_perp(direction), _AW)
    a = to_svg(tip)
    b = to_svg(_add(base, wing))
    c = to_svg(_sub(base, wing))
    return ComposedArrow(
        points=[
            ComposedPoint(x_mm=a.x, y_mm=a.y),
            ComposedPoint(x_mm=b.x, y_mm=b.y),
            ComposedPoint(x_mm=c.x, y_mm=c.y),
        ]
    )


def _svg_line(a: Vec2, b: Vec2, role: str, to_svg: ToSvg) -> ComposedDimLine:
    p = to_svg(a)
    q = to_svg(b)
    return ComposedDimLine(x1=p.x, y1=p.y, x2=q.x, y2=q.y, role=role)  # type: ignore[arg-type]


def _upright_angle(a: Vec2, b: Vec2) -> float:
    """Keep stamped text reading left-to-right regardless of slope (dimensions.ts)."""
    deg = math.atan2(b.y - a.y, b.x - a.x) * 180 / math.pi
    if deg > 90:
        deg -= 180
    if deg < -90:
        deg += 180
    return deg


def _text_half_extent(label: str) -> Vec2:
    """Half-extents (SVG mm) of the value's paper halo (dimensions.ts / glyph)."""
    return Vec2((len(label) * _TXT * 0.62 + 1.8) / 2, (_TXT + 1.4) / 2)


def _annotation_bounds(anno: ComposedMeasuredDimension) -> SvgRect:
    """The SVG bounds an annotation occupies (dimensions.ts annotationBounds)."""
    min_x = min_y = math.inf
    max_x = max_y = -math.inf

    def acc(x: float, y: float) -> None:
        nonlocal min_x, min_y, max_x, max_y
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    for line in anno.lines:
        acc(line.x1, line.y1)
        acc(line.x2, line.y2)
    for arrow in anno.arrows:
        for p in arrow.points:
            acc(p.x_mm, p.y_mm)
    half = _text_half_extent(anno.text.value)
    acc(anno.text.x - half.x, anno.text.y - half.y)
    acc(anno.text.x + half.x, anno.text.y + half.y)
    return SvgRect(min_x, min_y, max_x, max_y)


def _rect_overlap(a: SvgRect, b: SvgRect) -> float:
    w = min(a.max_x, b.max_x) - max(a.min_x, b.min_x)
    h = min(a.max_y, b.max_y) - max(a.min_y, b.min_y)
    return w * h if w > 0 and h > 0 else 0.0


def _placement_penalty(
    bbox: SvgRect, obstacles: Sequence[SvgRect], sheet: Vec2 | None
) -> float:
    """How BADLY a candidate placement reads (dimensions.ts placementPenalty)."""
    penalty = 0.0
    for o in obstacles:
        penalty += _rect_overlap(bbox, o) * 10
    if sheet is not None:
        penalty += (
            max(0.0, -bbox.min_x)
            + max(0.0, -bbox.min_y)
            + max(0.0, bbox.max_x - sheet.x)
            + max(0.0, bbox.max_y - sheet.y)
        )
    return penalty


def _choose_by_penalty(
    preferred: ComposedMeasuredDimension,
    alternate: ComposedMeasuredDimension,
    obstacles: Sequence[SvgRect],
    sheet: Vec2 | None,
) -> ComposedMeasuredDimension:
    """Pick the cleaner-reading placement (dimensions.ts chooseByPenalty)."""
    p_pref = _placement_penalty(_annotation_bounds(preferred), obstacles, sheet)
    p_alt = _placement_penalty(_annotation_bounds(alternate), obstacles, sheet)
    return alternate if p_alt < p_pref else preferred


def _measured(
    dim_type: str,
    dim_id: object,
    lines: list[ComposedDimLine],
    arrows: list[ComposedArrow],
    text: ComposedDimText,
    foreshortened: bool,
) -> ComposedMeasuredDimension:
    return ComposedMeasuredDimension(
        dimension_id=dim_id,  # type: ignore[arg-type]
        dimension_type=dim_type,  # type: ignore[arg-type]
        lines=lines,
        arrows=arrows,
        text=text,
        foreshortened=foreshortened,
    )


def _place_linear_between(
    p: Vec2,
    q: Vec2,
    label: str,
    foreshortened: bool,
    view_center: Vec2,
    to_svg: ToSvg,
    obstacles: Sequence[SvgRect],
    sheet: Vec2 | None,
    dim_type: str,
    dim_id: object,
    authored_offset: float | None = None,
) -> ComposedMeasuredDimension | None:
    """A straight linear dimension between two projected points (dimensions.ts).

    ``authored_offset`` wires the authored :class:`DimensionPlacement.offset_mm`
    (design §3.1) — the signed perpendicular distance of the dimension line from the
    measured geometry. When ``None`` (the default — ``offset_mm == 0``, what every
    shipped drawing carries) the auto engine runs UNCHANGED: the dimension is placed
    at the token offset ``_O`` on the ``away`` side and the ``_neg(away)`` alternate,
    and the cleaner-reading one wins by :func:`_choose_by_penalty` (byte-identical to
    pre-wire). When authored (non-zero) the auto penalty is BYPASSED: the dimension
    line sits at ``abs(authored_offset)`` mm on the ``away`` side for a positive
    offset (the composer's canonical outward normal — the auto engine's preferred
    side) and the opposite side for a negative one, placed VERBATIM (a value large
    enough to fall off-sheet is placed as-authored and the viewer clips it — the same
    honest posture the auto engine takes for its own extremes and notes take off-sheet).
    """
    d = _unit(_sub(q, p))
    if _hyp(_sub(q, p)) < 1e-9:
        return None
    mid = _mul(_add(p, q), 0.5)
    n0 = _perp(d)
    away = n0 if _dot(n0, _sub(mid, view_center)) >= 0 else _neg(n0)

    def place(n: Vec2, o: float = _O) -> ComposedMeasuredDimension:
        dim_a = _add(p, _mul(n, o))
        dim_b = _add(q, _mul(n, o))
        ext_a = _svg_line(
            _add(p, _mul(n, _GAP)), _add(p, _mul(n, o + _OVER)), "extension", to_svg
        )
        ext_b = _svg_line(
            _add(q, _mul(n, _GAP)), _add(q, _mul(n, o + _OVER)), "extension", to_svg
        )
        lines = [ext_a, ext_b, _svg_line(dim_a, dim_b, "dimension", to_svg)]
        arrows = [_arrow(dim_a, _neg(d), to_svg), _arrow(dim_b, d, to_svg)]
        mid_dim = _mul(_add(dim_a, dim_b), 0.5)
        anchor = to_svg(_add(mid_dim, _mul(n, _TXT * 0.5 + 0.6)))
        angle = _upright_angle(to_svg(dim_a), to_svg(dim_b))
        return _measured(
            dim_type,
            dim_id,
            lines,
            arrows,
            ComposedDimText(x=anchor.x, y=anchor.y, angle=angle, value=label),
            foreshortened,
        )

    if authored_offset is not None:
        n = away if authored_offset >= 0 else _neg(away)
        return place(n, abs(authored_offset))
    return _choose_by_penalty(place(away), place(_neg(away)), obstacles, sheet)


def _line_intersection(a0: Vec2, a1: Vec2, b0: Vec2, b1: Vec2) -> Vec2 | None:
    """Intersection of the two infinite lines, or None if parallel (dimensions.ts)."""
    r = _sub(a1, a0)
    s = _sub(b1, b0)
    denom = r.x * s.y - r.y * s.x
    if abs(denom) < 1e-9:
        return None
    qp = _sub(b0, a0)
    t = (qp.x * s.y - qp.y * s.x) / denom
    return _add(a0, _mul(r, t))


def _signed_angle_between(a: Vec2, b: Vec2) -> float:
    """Signed angle (rad) in (-pi, pi] from ``a`` to ``b`` (dimensions.ts)."""
    return math.atan2(a.x * b.y - a.y * b.x, a.x * b.x + a.y * b.y)


def _place_angular(
    edge_a: ProjectedViewEdge,
    edge_b: ProjectedViewEdge,
    label: str,
    foreshortened: bool,
    to_svg: ToSvg,
    dim_id: object,
) -> ComposedMeasuredDimension | None:
    """Angular dimension between two straight projected edges (dimensions.ts)."""
    a0 = _p2(edge_a.start)
    a1 = _p2(edge_a.end)
    b0 = _p2(edge_b.start)
    b1 = _p2(edge_b.end)
    apex = _line_intersection(a0, a1, b0, b1)
    if apex is None:
        return None
    dir_a = _unit(_sub(_p2(edge_a.midpoint), apex))
    dir_b = _unit(_sub(_p2(edge_b.midpoint), apex))
    if _hyp(dir_a) < 1e-9 or _hyp(dir_b) < 1e-9:
        return None

    start_ang = math.atan2(dir_a.y, dir_a.x)
    delta = _signed_angle_between(dir_a, dir_b)  # short way, (-pi, pi]
    if abs(delta) < 1e-6:
        return None

    def arc_at(t: float) -> Vec2:
        ang = start_ang + delta * t
        return _add(apex, Vec2(math.cos(ang) * _ARC_R, math.sin(ang) * _ARC_R))

    segments = max(6, math.ceil(abs(delta) / (math.pi / 24)))
    lines: list[ComposedDimLine] = []
    for i in range(segments):
        lines.append(
            _svg_line(
                arc_at(i / segments), arc_at((i + 1) / segments), "dimension", to_svg
            )
        )
    for direction in (dir_a, dir_b):
        lines.append(
            _svg_line(
                _add(apex, _mul(direction, _GAP)),
                _add(apex, _mul(direction, _ARC_R + _OVER)),
                "extension",
                to_svg,
            )
        )

    tip_a = arc_at(0.0)
    tip_b = arc_at(1.0)
    arrows = [
        _arrow(tip_a, _unit(_sub(arc_at(0.01), tip_a)), to_svg),
        _arrow(tip_b, _unit(_sub(arc_at(0.99), tip_b)), to_svg),
    ]
    mid_ang = start_ang + delta / 2
    mid_dir = Vec2(math.cos(mid_ang), math.sin(mid_ang))
    anchor = to_svg(_add(apex, _mul(mid_dir, _ARC_R + _TXT * 0.7 + 1.8)))
    return _measured(
        "angular",
        dim_id,
        lines,
        arrows,
        ComposedDimText(x=anchor.x, y=anchor.y, angle=0.0, value=label),
        foreshortened,
    )


def _build_dimension_annotation_auto(
    dimension: DimensionParams,
    measured: MeasuredDimension,
    edges: Sequence[ProjectedViewEdge],
    view_center: Vec2,
    to_svg: ToSvg,
    obstacles: Sequence[SvgRect],
    sheet: Vec2 | None,
    dim_id: object,
) -> ComposedDimension:
    """Build the drafting annotation for one measured dimension (dimensions.ts).

    ALWAYS returns something to draw (QA-4). A dimension that cannot be PLACED — the
    (re-anchored) edge is not among this view's projected edges, it is drawn as a
    primitive this dimension type cannot annotate, a point-to-point endpoint has no
    projected correspondence, or the placement itself is degenerate (parallel angular
    edges, a zero-length span) — comes back as a stamped
    :class:`ComposedDimensionError` carrying :data:`DIMENSION_NOT_PLACEABLE`, exactly
    like a dimension that could not be MEASURED. It used to return ``None`` and the
    caller SKIPPED it: the authored dimension then vanished from the sheet and from
    every exported artifact without a mark, which is strictly the worst outcome — a
    print silently missing a dimension reads as a complete one.

    The auto-placement CORE. Honors the authored :class:`DimensionPlacement.offset_mm`
    for a LINEAR dimension (its design-§3.1 meaning — the signed offset of the
    dimension LINE from the geometry; a diameter/radius/angular has no such offset
    line, so ``offset_mm`` is inapplicable there in v1). The authored ``text_pos`` is
    applied by the public :func:`build_dimension_annotation` wrapper (it overrides the
    text of ANY placed dimension type). A default placement (``offset_mm == 0``,
    ``text_pos is None`` — what every shipped dimension carries) runs this core
    unchanged and byte-identical.
    """
    dim_type = dimension.type
    authored_offset = (
        dimension.placement.offset_mm if dimension.placement.offset_mm != 0.0 else None
    )
    # Match the projected edges against the RE-ANCHORED signature (audit N1): after an
    # edit to the measured feature the authored signature names geometry that is no
    # longer there, and the annotation would be dropped even though the value
    # re-measured fine.
    primary_sig = anchored_signature(dimension_edge_signature(dimension), measured)
    primary_edge = find_matching_edge(edges, primary_sig) if primary_sig else None
    marker_at = (
        to_svg(_p2(primary_edge.midpoint)) if primary_edge else to_svg(view_center)
    )

    def unplaceable() -> ComposedDimensionError:
        """This dimension measured, but there is nothing on this view to draw it on."""
        return _dimension_error(dim_type, dim_id, marker_at, DIMENSION_NOT_PLACEABLE)

    if measured.error is not None or measured.value is None:
        code = measured.error.code if measured.error is not None else "unmeasured"
        return _dimension_error(dim_type, dim_id, marker_at, code)

    value = measured.value
    label = ("~" if measured.foreshortened else "") + format_dimension_label(
        dim_type, value, measured.unit
    )

    if isinstance(dimension, LinearDimensionParams):
        measurement = dimension.measurement
        if isinstance(measurement, EdgeToEdgeMeasurement):
            # Across the wall: from the midpoint of the first projected edge, square
            # onto the second edge's supporting line. `_place_linear_between` then
            # runs its witness lines PARALLEL to the walls and the dimension line
            # across them — the standard thickness callout.
            sig_b = anchored_signature(measurement.edge_b, measured, secondary=True)
            edge_a = find_matching_edge(edges, primary_sig) if primary_sig else None
            edge_b = find_matching_edge(edges, sig_b) if sig_b else None
            if edge_a is None or edge_b is None:
                return unplaceable()
            if edge_a.primitive != "line" or edge_b.primitive != "line":
                return unplaceable()
            p = _p2(edge_a.midpoint)
            q = _perpendicular_foot(p, _p2(edge_b.start), _p2(edge_b.end))
            if q is None:
                return unplaceable()
            return (
                _place_linear_between(
                    p,
                    q,
                    label,
                    measured.foreshortened,
                    view_center,
                    to_svg,
                    obstacles,
                    sheet,
                    dim_type,
                    dim_id,
                    authored_offset,
                )
                or unplaceable()
            )
        if isinstance(measurement, PointToPointMeasurement):
            sig_b = anchored_signature(
                measurement.b.signature, measured, secondary=True
            )
            edge_a = find_matching_edge(edges, primary_sig) if primary_sig else None
            edge_b = find_matching_edge(edges, sig_b) if sig_b else None
            if edge_a is None or edge_b is None:
                return unplaceable()
            p = _endpoint_projected(edge_a, measurement.a.endpoint)
            q = _endpoint_projected(edge_b, measurement.b.endpoint)
            if p is None or q is None:
                return unplaceable()
            return (
                _place_linear_between(
                    p,
                    q,
                    label,
                    measured.foreshortened,
                    view_center,
                    to_svg,
                    obstacles,
                    sheet,
                    dim_type,
                    dim_id,
                    authored_offset,
                )
                or unplaceable()
            )
        edge = primary_edge
        if edge is None or edge.primitive != "line":
            return unplaceable()
        return (
            _place_linear_between(
                _p2(edge.start),
                _p2(edge.end),
                label,
                measured.foreshortened,
                view_center,
                to_svg,
                obstacles,
                sheet,
                dim_type,
                dim_id,
                authored_offset,
            )
            or unplaceable()
        )

    if isinstance(dimension, AngularDimensionParams):
        sig_b = anchored_signature(dimension.edge_b, measured, secondary=True)
        edge_a = find_matching_edge(edges, primary_sig) if primary_sig else None
        edge_b = find_matching_edge(edges, sig_b) if sig_b else None
        if edge_a is None or edge_b is None:
            return unplaceable()
        if edge_a.primitive != "line" or edge_b.primitive != "line":
            return unplaceable()
        return (
            _place_angular(
                edge_a, edge_b, label, measured.foreshortened, to_svg, dim_id
            )
            or unplaceable()
        )

    # Diameter | Radius (the only remaining members after the branches above).
    edge = primary_edge
    if edge is None or edge.center is None or edge.radius is None:
        return unplaceable()
    c = _p2(edge.center)
    rad = edge.radius
    if isinstance(dimension, DiameterDimensionParams):
        a = Vec2(c.x - rad, c.y)
        b = Vec2(c.x + rad, c.y)
        half = _text_half_extent(label).x

        def place(sign: float) -> ComposedMeasuredDimension:
            anchor = to_svg(Vec2(c.x + sign * (rad + 1.4 + half), c.y))
            return _measured(
                dim_type,
                dim_id,
                [_svg_line(a, b, "dimension", to_svg)],
                [
                    _arrow(a, Vec2(-1.0, 0.0), to_svg),
                    _arrow(b, Vec2(1.0, 0.0), to_svg),
                ],
                ComposedDimText(x=anchor.x, y=anchor.y, angle=0.0, value=label),
                measured.foreshortened,
            )

        sign = 1.0 if _dot(Vec2(1.0, 0.0), _sub(c, view_center)) >= 0 else -1.0
        return _choose_by_penalty(place(sign), place(-sign), obstacles, sheet)

    # radius: a leader from the centre out to the circle at 45 degrees.
    direction = _unit(Vec2(1.0, 1.0))
    edge_pt = _add(c, _mul(direction, rad))
    leader_out = 2.4 + _text_half_extent(label).x
    anchor = to_svg(_add(edge_pt, _mul(direction, leader_out)))
    return _measured(
        dim_type,
        dim_id,
        [_svg_line(c, edge_pt, "dimension", to_svg)],
        [_arrow(edge_pt, direction, to_svg)],
        ComposedDimText(x=anchor.x, y=anchor.y, angle=0.0, value=label),
        measured.foreshortened,
    )


def build_dimension_annotation(
    dimension: DimensionParams,
    measured: MeasuredDimension,
    edges: Sequence[ProjectedViewEdge],
    view_center: Vec2,
    to_svg: ToSvg,
    obstacles: Sequence[SvgRect],
    sheet: Vec2 | None,
    dim_id: object,
) -> ComposedDimension:
    """Build the drafting annotation for one measured dimension (dimensions.ts).

    Wraps the auto-placement core (:func:`_build_dimension_annotation_auto`, which
    also honors an authored ``offset_mm`` for linear dims) and applies the authored
    :class:`DimensionPlacement.text_pos` (design §3.1): when present it OVERRIDES the
    auto-computed text anchor of a placed dimension of ANY type, verbatim in FINAL
    sheet-SVG space (mm, y-DOWN, top-left origin — the same space a note anchor uses,
    so no view transform / y-flip is re-applied; a point off the sheet is placed
    as-authored and the viewer clips it). ``None`` (the default every shipped
    dimension carries) leaves the auto text position untouched — byte-identical. The
    override touches only the text POSITION; the dimension/extension lines, arrows,
    stamped value, and text angle are the auto-placed geometry. A typed
    :class:`ComposedDimensionError` — unmeasurable OR unplaceable (QA-4) — is returned
    as-is (its caption sits beside its own marker; there is no measured text to move).
    """
    anno = _build_dimension_annotation_auto(
        dimension, measured, edges, view_center, to_svg, obstacles, sheet, dim_id
    )
    text_pos = dimension.placement.text_pos
    if text_pos is not None and isinstance(anno, ComposedMeasuredDimension):
        return anno.model_copy(
            update={
                "text": anno.text.model_copy(
                    update={"x": text_pos.x_mm, "y": text_pos.y_mm}
                )
            }
        )
    return anno
