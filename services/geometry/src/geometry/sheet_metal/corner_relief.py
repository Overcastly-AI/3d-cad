"""Sheet-metal corner relief — cut a RECTANGULAR notch at a bend intersection.

The 3D half of the corner-relief feature (docs/design/sheet-metal.md §4.4): a
small material cutout at the shared corner of two adjacent edge flanges so the
sheet doesn't tear/interfere when folded. v1 ships the **rectangular** relief
(§4.4.1) — axis-aligned box booleans located by the two bends' provenance (§5)
— the manufacturable 3D notch.

**Fold-back consistency (the invariant this feature MUST hold, §4.4.4).** The
flat pattern is the authoritative manufacturing deliverable and is computed
ANALYTICALLY from the same :class:`~geometry.sheet_metal.unfold.CornerRelief`
spec (:func:`geometry.sheet_metal.unfold.unfold_sheet_metal`). This 3D cut must
remove *the material that, unfolded, IS that flat notch* — otherwise "fold the
flat blank and you get the modeled body" is a lie. It does: for EACH flange the
tool is a slot of width ``size`` along that flange's bend axis, running from the
base corner THROUGH the full bend arc and ``size`` up the folded wall (a LOCAL
corner notch — the wall stays full width above it). Because the slot cuts the
whole arc over a constant-width band, its unfolded image is exactly the flat
pattern's near-corner notch: the relieved body's bend cylindrical-face width
equals the flat ``bend_widths_mm``, and the removed volume equals removed flat
area x thickness up to the neutral-vs-mean-radius bend term (both asserted in
the fold-back cross-consistency test). Both halves model the SAME physical
removal — consistent by construction, and by test.

Reuse (§7): the notch is ordinary boolean subtraction (``body - Box``), the same
cut primitive extrude/shell already use — no new kernel geometry. The corner and
each flange's wall/base/axis directions are read from the two bends' resolved
cylindrical faces (axis + area centroid), never guessed. v1 scopes to
axis-aligned perpendicular edge flanges; a non-axis-aligned corner is a typed
:class:`CornerReliefError` (honest degradation, §5).

The OCP wheel ships no type stubs, so the raw build123d calls are opaque to
pyright; the directives scope that relaxation to this file only, and the typed
DTOs at the boundary keep it honest.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

from build123d import Box, Part, Solid, Vector
from build123d.geometry import BoundBox

from geometry.kernel.types import BodyShape
from geometry.sheet_metal.resolve import (
    SheetMetalUnfoldError,
    resolve_cylindrical_face,
)
from geometry.sheet_metal.unfold import CornerRelief

#: The two bend axes of a v1 relievable corner are PERPENDICULAR to within this
#: |dot| residual (authored trays are axis-aligned, so residuals are ulp-scale).
_PERP_TOL = 1e-7
#: A v1 relievable corner is axis-aligned: each derived direction (bend axis, wall
#: outboard, fold-up) must land on a world axis to within this residual, else the
#: corner is out of the rectangular-notch scope and is a typed reject (§4.4).
_AXIS_ALIGN_TOL = 1e-6


class CornerReliefError(SheetMetalUnfoldError):
    """The corner relief could not be applied — the two named bends do not meet at
    a resolvable perpendicular corner (v1 rectangular relief scope, §4.4)."""


def _closest_point_between_lines(
    p_a: Vector, d_a: Vector, p_b: Vector, d_b: Vector
) -> Vector:
    """Midpoint of the shortest segment between two lines (the shared corner point).

    For perpendicular axis-aligned bend axes this is the exact crossing point of
    their XY projections; the general least-distance solve keeps it robust to
    kernel jitter without assuming axis alignment for the LOCATION step."""
    r = p_a - p_b
    a = d_a.dot(d_a)
    b = d_a.dot(d_b)
    c = d_b.dot(d_b)
    d = d_a.dot(r)
    e = d_b.dot(r)
    denom = a * c - b * b
    if abs(denom) < 1e-12:
        # Parallel axes: no isolated corner (caller guards this as an error).
        s = 0.0
        t = e / c if abs(c) > 1e-12 else 0.0
    else:
        s = (b * e - c * d) / denom
        t = (a * e - b * d) / denom
    ca = p_a + d_a * s
    cb = p_b + d_b * t
    return (ca + cb) * 0.5


def _world_axis(v: Vector) -> tuple[int, int]:
    """The world axis (index 0/1/2) and sign a near-unit direction lands on.

    v1 rectangular relief scopes to axis-aligned corners, so every derived
    direction is ``±X/±Y/±Z``; a direction whose off-axis components exceed the
    alignment tolerance is out of scope and a typed reject (never a mislaid cut)."""
    comps = (v.X, v.Y, v.Z)
    idx = max(range(3), key=lambda i: abs(comps[i]))
    for i in range(3):
        if i != idx and abs(comps[i]) > _AXIS_ALIGN_TOL:
            raise CornerReliefError(
                "A corner-relief direction is not axis-aligned; v1 rectangular relief "
                "scopes to axis-aligned perpendicular edge flanges (§4.4)."
            )
    return idx, 1 if comps[idx] > 0 else -1


def _flange_notch_box(
    axis_origin: Vector,
    bend_centroid: Vector,
    d: Vector,
    corner: Vector,
    normal: Vector,
    bbox: BoundBox,
    size: float,
) -> Part:
    """The box that cuts ONE flange's corner notch, as the folded image of the flat
    notch (§4.4.4).

    A slot of width ``size`` along the bend axis *d*, running from the shared corner
    THROUGH the full bend arc and ``size`` up the folded wall: on the bend-axis it
    is the ``size`` band on the flange-material side of the corner; on the outboard
    horizontal it spans ``size`` into the base (the corner square) out past the wall;
    on the fold-up axis it spans from below the base to ``size`` above the wall
    bottom, leaving the wall FULL width above the notch. Because it removes the whole
    arc over a constant-width band, its unfolded image is exactly the analytic flat
    notch (width ``size`` x developed depth ``BA + size``). The bend's INNER
    cylindrical-face area *bend_centroid* fixes the outboard + fold-up directions
    (it bulges toward the base plate from the axis)."""
    delta = bend_centroid - axis_origin
    delta_perp = delta - d * delta.dot(d)  # drop the along-axis component
    vertical = delta_perp.dot(normal)
    # Fold-up (wall) direction: opposite the arc's bulge toward the base plate.
    rise = normal * (-1.0 if vertical > 0.0 else 1.0)
    outward = delta_perp - normal * vertical  # outboard horizontal (toward the wall)
    if outward.length < _AXIS_ALIGN_TOL:
        raise CornerReliefError(
            "A corner-relief flange has no resolvable outboard direction; v1 scopes "
            "to axis-aligned perpendicular edge flanges (§4.4)."
        )
    outward = outward.normalized()
    sd, _sds = _world_axis(d)
    sw, sws = _world_axis(outward)
    sr, srs = _world_axis(rise)
    if len({sd, sw, sr}) != 3:
        raise CornerReliefError(
            "A corner relief's bend axis, wall, and fold-up directions do not form a "
            "world-axis frame; v1 scopes to axis-aligned perpendicular flanges (§4.4)."
        )
    center = (bbox.min + bbox.max) * 0.5
    lo = [float(bbox.min.X) - 1.0, float(bbox.min.Y) - 1.0, float(bbox.min.Z) - 1.0]
    hi = [float(bbox.max.X) + 1.0, float(bbox.max.Y) + 1.0, float(bbox.max.Z) + 1.0]
    c = (float(corner.X), float(corner.Y), float(corner.Z))
    ctr = (float(center.X), float(center.Y), float(center.Z))
    # Bend-axis: the `size` band on the flange-material (body-interior) side.
    if ctr[sd] >= c[sd]:
        lo[sd], hi[sd] = c[sd], c[sd] + size
    else:
        lo[sd], hi[sd] = c[sd] - size, c[sd]
    # Outboard horizontal: `size` into the base (corner square) out past the wall.
    if sws > 0:
        lo[sw] = c[sw] - size
    else:
        hi[sw] = c[sw] + size
    # Fold-up: from below the base to `size` above the wall bottom (wall full above).
    if srs > 0:
        hi[sr] = c[sr] + size
    else:
        lo[sr] = c[sr] - size
    return Box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]).translate(
        ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0)
    )


def corner_relief_tools(
    reference: BodyShape, relief: CornerRelief
) -> tuple[Part, Part]:
    """Resolve *relief*'s two bends against *reference* and build the two notch tools.

    Split out from :func:`apply_corner_relief` (the cut) so a relief can resolve its
    bends against a body OTHER than the one it cuts — specifically a **clean,
    un-notched** reference with ALL bends. This is what lets a SECOND relief that
    shares a flange with an earlier relief still resolve (§4.4.4): an earlier notch
    shortens the shared flange's bend cylinder and shifts its area centroid past the
    signature match tolerance, so resolving against the LIVE (already-notched) body
    would miss the shared bend (``subshape_unresolved``). Resolving every relief
    against the same un-notched geometry sidesteps that entirely; the accumulated
    tools are then cut from the live body by :func:`cut_relief_tools`.

    Resolves both bends by provenance (§5), locates their shared corner (the closest
    point between the two bend axes) and the base normal (their cross product, the
    fold-up axis), then builds ONE slot per flange (:func:`_flange_notch_box`): each
    is ``size`` wide along its bend axis and cuts from the base corner through the
    full bend arc and ``size`` up the folded wall (the folded image of the analytic
    flat notch, §4.4.4). Every value is a closed-form function of the resolved axes +
    the relief size (deterministic, RESEARCH §9).

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *reference* (§5 honest degradation).
        CornerReliefError: the two bend axes are parallel (no isolated corner) or the
            corner is not axis-aligned (out of v1 rectangular-notch scope).
    """
    inner_a = resolve_cylindrical_face(reference, relief.bend_a)
    inner_b = resolve_cylindrical_face(reference, relief.bend_b)
    d_a = inner_a.axis_dir.normalized()
    d_b = inner_b.axis_dir.normalized()
    if abs(d_a.dot(d_b)) > _PERP_TOL:
        raise CornerReliefError(
            "A corner relief's two bends are not perpendicular; v1 rectangular relief "
            "applies at the intersection of two PERPENDICULAR edge flanges (§4.4)."
        )
    corner = _closest_point_between_lines(
        inner_a.axis_origin, d_a, inner_b.axis_origin, d_b
    )
    normal = d_a.cross(d_b).normalized()  # base normal = the fold-up axis
    bbox = reference.bounding_box()
    size = relief.size_mm
    tool_a = _flange_notch_box(
        inner_a.axis_origin, inner_a.centroid, d_a, corner, normal, bbox, size
    )
    tool_b = _flange_notch_box(
        inner_b.axis_origin, inner_b.centroid, d_b, corner, normal, bbox, size
    )
    return tool_a, tool_b


def cut_relief_tools(body: BodyShape, tools: list[tuple[Part, Part]]) -> Solid:
    """Cut the accumulated per-relief notch *tools* from *body*, returning one solid.

    The tools are built by :func:`corner_relief_tools` against a clean reference; this
    subtracts every relief's two slots from the LIVE body and requires the result to
    stay ONE connected shell (a sheet-metal part is one body — a notch must not sever
    it, §4.4). Multiple reliefs on the SAME flange cut disjoint corner bites at
    opposite ends of that flange, so they stack without severing (the canonical
    all-four-corners pan). Deterministic: the tools arrive in the reliefs' evaluation
    order and the subtraction is order-independent up to floating point.

    Raises:
        CornerReliefError: the boolean failed in the kernel, or the cut produced
            other than exactly one solid (an out-of-scope / severing geometry).
    """
    try:
        cut: BodyShape = body
        for tool_a, tool_b in tools:
            cut = cut - tool_a - tool_b
        cut = cut.clean()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise CornerReliefError(
            f"Corner-relief boolean failed in the kernel ({type(exc).__name__})."
        ) from exc
    solids = cut.solids()
    if len(solids) != 1:
        raise CornerReliefError(
            f"Corner relief produced {len(solids)} solids; a sheet-metal part stays "
            "one connected body (the notch must not sever the sheet, §4.4)."
        )
    return solids[0]


def apply_corner_relief(body: BodyShape, relief: CornerRelief) -> Solid:
    """Cut *relief*'s rectangular notch at the two named bends' shared corner.

    The single-relief composition of :func:`corner_relief_tools` +
    :func:`cut_relief_tools`, resolving AND cutting against the same *body* — the
    unit-level entry point (the feature pipeline instead resolves against a clean
    reference and accumulates, §4.4.4). Subtracts ONE slot per flange
    (:func:`_flange_notch_box`): each is ``size`` wide along its bend axis and cuts
    from the base corner through the full bend arc and ``size`` up the folded wall.
    This is the folded image of the analytic flat notch — the removed material,
    unfolded, IS the flat pattern's near-corner notch — so the two halves model the
    SAME removal (§4.4.4): the relieved body's bend-face width equals the flat
    ``bend_widths_mm`` and the removed volume equals removed flat area x thickness up
    to the bend's neutral-vs-mean-radius term.

    Deterministic (RESEARCH §9): every value is a closed-form function of the
    resolved axes + the relief size — no unordered iteration, no RNG. Returns the
    single relieved solid.

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *body* (§5 honest degradation).
        CornerReliefError: the two bend axes are parallel (no isolated corner), the
            corner is not axis-aligned (out of v1 rectangular-notch scope), or the
            cut did not produce exactly one solid (an out-of-scope geometry).
    """
    tools = corner_relief_tools(body, relief)
    return cut_relief_tools(body, [tools])
