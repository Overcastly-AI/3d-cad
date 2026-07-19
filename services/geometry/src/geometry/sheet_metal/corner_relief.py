"""Sheet-metal corner relief — cut a RECTANGULAR notch at a bend intersection.

The 3D half of the corner-relief feature (docs/design/sheet-metal.md §4.4): a
small material cutout at the shared corner of two adjacent edge flanges so the
sheet doesn't tear/interfere when folded. v1 ships the **rectangular** relief
(§4.4.1) — an axis-aligned box boolean located by the two bends' provenance
(§5) — the manufacturable 3D notch. The flat-pattern notch is computed
ANALYTICALLY from the same :class:`~geometry.sheet_metal.unfold.CornerRelief`
spec (:func:`geometry.sheet_metal.unfold.unfold_sheet_metal`), so the folded
body and the developed blank are consistent by construction; the flat pattern —
not this 3D cut — is the authoritative manufacturing deliverable (§1).

Reuse (§7): the notch is an ordinary boolean subtraction (``body - Box``), the
same cut primitive extrude/shell already use — no new kernel geometry. The
corner is located from the two bends' resolved cylindrical axes (the closest
point between the two axis lines), never guessed.

The OCP wheel ships no type stubs, so the raw build123d calls are opaque to
pyright; the directives scope that relaxation to this file only, and the typed
DTOs at the boundary keep it honest.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

from build123d import Box, Solid, Vector

from geometry.kernel.types import BodyShape
from geometry.sheet_metal.resolve import (
    SheetMetalUnfoldError,
    resolve_cylindrical_face,
)
from geometry.sheet_metal.unfold import CornerRelief

#: The two bend axes of a v1 relievable corner are PERPENDICULAR to within this
#: |dot| residual (authored trays are axis-aligned, so residuals are ulp-scale).
_PERP_TOL = 1e-7


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


def apply_corner_relief(body: BodyShape, relief: CornerRelief) -> Solid:
    """Cut *relief*'s rectangular notch at the two named bends' shared corner.

    Resolves both bends by provenance (§5), locates their shared corner (the
    closest point between the two bend axes), and subtracts a square column of side
    ``2 * size_mm`` centred on that corner and spanning the body's full height — it
    removes the base's corner square (the interior quadrant) plus the near ends of
    both flanges' bend regions, the material that would tear/interfere when folded.

    Deterministic (RESEARCH §9): every value is a closed-form function of the
    resolved axes + the relief size — no unordered iteration, no RNG. Returns the
    single relieved solid.

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *body* (§5 honest degradation).
        CornerReliefError: the two bend axes are parallel (no isolated corner) or
            the cut did not produce exactly one solid (an out-of-scope geometry).
    """
    inner_a = resolve_cylindrical_face(body, relief.bend_a)
    inner_b = resolve_cylindrical_face(body, relief.bend_b)
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

    bbox = body.bounding_box()
    z_lo = float(bbox.min.Z) - 1.0
    z_hi = float(bbox.max.Z) + 1.0
    side = 2.0 * relief.size_mm
    height = z_hi - z_lo
    tool = Box(side, side, height).translate(
        (float(corner.X), float(corner.Y), (z_lo + z_hi) / 2.0)
    )
    try:
        cut = (body - tool).clean()
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
