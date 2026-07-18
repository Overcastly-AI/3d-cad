"""Datum-plane resolution math — offset (origin or chained) and midplane.

One home for the pure plane functions the ``datum`` feature kinds resolve
through (docs/design/datum-planes.md §3a/§7/§7a). Everything here is a pure
function of already-resolved :class:`~build123d.Plane` inputs and scalar
params — no picked geometry, no state, no iteration order — so resolution is
DETERMINISTIC (RESEARCH §9): same inputs, bitwise-identical plane.

Conventions (the load-bearing decisions, documented once here and in
datum-planes §7a):

* **Offset** (:func:`offset_plane`): the parent plane slid ``offset_mm`` along
  its OWN normal (``Plane.offset`` shifts ``origin`` by ``z_dir * amount``,
  preserving ``x_dir``/``z_dir``); ``flip`` negates ``z_dir`` keeping ``x_dir``
  (sketch +u unchanged, +v flips). Chained offsets compose hop by hop — the
  evaluator passes the parent datum's RESOLVED plane in, so a chain from a
  flipped parent offsets along the FLIPPED normal (the composite is what the
  chain literally reads).
* **Midplane** (:func:`midplane_between`): see its docstring for the
  parallel / angular / identical conventions and the normal-sign rule.
* **Basis**: a midplane's ``x_dir`` is pinned purely from its normal by
  :func:`geometry.kernel.faces.deterministic_x_dir` — the SAME rule the
  ``on_face`` datum basis uses (one basis rule, never OCCT parametrisation).

The parallel/angular classification bound below is a DOCUMENTED tolerance
(CLAUDE.md: never ad-hoc): resolved plane normals are either exact (origin /
offset datums — pure double math) or kernel-derived unit vectors with ulp-scale
noise (face planes), so genuinely-parallel sides land many orders below the
bound, while the smallest authorable real angle (even 1e-3 degrees ~ 1.7e-5 in
``|n_a x n_b|``) lands far above it. The gap is ~10 orders of magnitude wide;
nothing real lives near the bound.
"""

from typing import Literal

from build123d import Plane

from geometry.kernel.faces import deterministic_x_dir

#: The three origin datum planes (design §2.1), by their wire name. Local
#: sketch (x, y) coordinates map through ``x_dir``/``y_dir``; the extrusion
#: normal is ``z_dir``. Single source for plane orientation — the sketch and
#: extrude features must agree on it.
DATUM_PLANES: dict[str, Plane] = {
    "XY": Plane.XY,
    "XZ": Plane.XZ,
    "YZ": Plane.YZ,
}

#: Documented parallelism bound for midplane classification: two sides are
#: PARALLEL iff ``|n_a x n_b| <= MIDPLANE_PARALLEL_TOLERANCE`` (the sine of the
#: angle between unit normals). Sized per the module note: ulp-scale noise on
#: genuinely-parallel resolved normals (< 1e-12) vs the smallest authorable
#: real angle (> 1e-5) — the bound sits in the dead middle of a ~10-order gap.
MIDPLANE_PARALLEL_TOLERANCE = 1e-9


def offset_plane(parent: Plane, offset_mm: float, flip: bool) -> Plane:
    """Slide *parent* ``offset_mm`` along its own normal, optionally flipped.

    The one offset rule both offset datum kinds share (datum-planes §3a/§7):
    ``Plane.offset`` shifts ``origin`` by ``z_dir * offset_mm`` preserving
    ``x_dir``/``z_dir``; ``flip`` then negates ``z_dir`` keeping ``x_dir`` (so
    sketch +u is unchanged and +v flips) — a valid orthonormal frame.
    ``offset_mm = 0, flip = False`` reproduces *parent* exactly. Pure and
    total: any finite offset of a valid plane is a valid plane.
    """
    plane = parent.offset(offset_mm)
    if flip:
        return Plane(origin=plane.origin, x_dir=plane.x_dir, z_dir=-plane.z_dir)
    return plane


def build_datum_plane(
    base: Literal["XY", "XZ", "YZ"], offset_mm: float, flip: bool
) -> Plane:
    """Resolve an ``offset`` datum's params to a concrete plane.

    The v1 datum plane (docs/design/datum-planes.md §3a): an origin datum slid
    along its own normal — :func:`offset_plane` over :data:`DATUM_PLANES`.
    ``offset_mm = 0`` and ``flip = False`` reproduce the origin datum exactly,
    so an existing origin-datum sketch resolves to the byte-identical plane.
    Pure function of ``(base, offset_mm, flip)`` — deterministic, naming-free
    (RESEARCH §9).
    """
    return offset_plane(DATUM_PLANES[base], offset_mm, flip)


def midplane_between(a: Plane, b: Plane, flip: bool) -> Plane:
    """The plane midway between two resolved planes (datum-planes §7a).

    TOTAL over any two valid planes — every case yields a plane, so a midplane
    datum never carries a rebuild error of its own (its failures are all
    upstream reference resolution). The documented conventions:

    * **Parallel** (``|n_a x n_b| <=`` :data:`MIDPLANE_PARALLEL_TOLERANCE`,
      anti-parallel normals included — e.g. a box's outward top +Z and bottom
      -Z): the midway plane. Normal = side ``a``'s normal (the documented sign
      rule: side order signs the result). Origin = the midpoint of the two
      resolved origins — for parallel planes ANY point at the mean signed
      distance lies on the midplane, and the origin midpoint is a pure,
      deterministic choice. **Identical/coplanar sides degenerate cleanly**: the
      midpoint lies on the shared plane, so the midplane IS that plane (with
      the canonical basis below).
    * **Non-parallel**: the angular-bisector plane through the two planes'
      intersection line. Normal = ``normalize(n_a + n_b)`` — well-defined for
      every non-parallel pair (the sum only vanishes anti-parallel, which is
      the parallel branch), perpendicular sides included, so the perpendicular
      "which bisector?" ambiguity is settled by the rule, not a guess; flipping
      one side's normal (a flipped datum / the opposite face) selects the other
      bisector. Origin = the point of the intersection line NEAREST THE WORLD
      ORIGIN — the minimum-norm solution ``s·n_a + t·n_b`` of the two plane
      equations, a pure closed form of the inputs.
    * **Basis**: ``z_dir`` = the convention normal, ``x_dir`` =
      :func:`~geometry.kernel.faces.deterministic_x_dir` of it (the on_face
      rule; sign-symmetric, so ``flip`` keeps +u and flips +v exactly like
      :func:`offset_plane`).
    """
    n_a = a.z_dir.normalized()
    n_b = b.z_dir.normalized()
    if n_a.cross(n_b).length <= MIDPLANE_PARALLEL_TOLERANCE:
        # PARALLEL (incl. anti-parallel and identical/coplanar sides).
        origin = (a.origin + b.origin) * 0.5
        normal = n_a
    else:
        # NON-PARALLEL: bisector through the intersection line. Solve
        # p = s*n_a + t*n_b with n_a·p = d_a, n_b·p = d_b (min-norm point).
        d_a = n_a.dot(a.origin)
        d_b = n_b.dot(b.origin)
        cos_ab = n_a.dot(n_b)
        denom = 1.0 - cos_ab * cos_ab
        s = (d_a - cos_ab * d_b) / denom
        t = (d_b - cos_ab * d_a) / denom
        origin = n_a * s + n_b * t
        normal = (n_a + n_b).normalized()
    if flip:
        normal = -normal
    return Plane(origin=origin, x_dir=deterministic_x_dir(normal), z_dir=normal)
