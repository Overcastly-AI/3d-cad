"""Parametric shape builders (build123d over OCCT).

Every builder takes validated scalar parameters and returns a build123d
``Shape``. Kernel objects never leave ``geometry.kernel`` — callers hand the
shape straight to :mod:`geometry.kernel.properties` /
:mod:`geometry.kernel.tessellate` and ship DTOs/bytes outward.
"""

from build123d import Solid


def build_box(x: float, y: float, z: float) -> Solid:
    """Build an axis-aligned box, min corner at the origin (dimensions in mm).

    Deterministic: same parameters produce identical topology and mass
    properties (RESEARCH §9).

    Raises:
        ValueError: if any dimension is not strictly positive (the API layer
            rejects these at validation time; this guards direct kernel use).
    """
    if x <= 0 or y <= 0 or z <= 0:
        raise ValueError(f"Box dimensions must be strictly positive, got {(x, y, z)}")
    return Solid.make_box(x, y, z)


def build_cylinder(radius: float, height: float) -> Solid:
    """Build a right circular cylinder: base disc centred at the origin in
    the XY plane, axis along +Z (dimensions in mm).

    First curved primitive — its golden (``goldens/cylinder-r10-h25``) locks
    GProp integration over an analytic quadric surface, curved-face
    tessellation deflection, and STEP re-approximation of curved geometry.
    OCCT models the closed cylinder as 3 faces (lateral + 2 caps), 3 edges
    (2 cap circles + 1 lateral seam edge — the parametric closure of the
    cylindrical surface), 1 shell.

    Deterministic: same parameters produce identical topology and mass
    properties (RESEARCH §9).

    Raises:
        ValueError: if radius or height is not strictly positive (the API
            layer rejects these at validation time; this guards direct
            kernel use).
    """
    if radius <= 0 or height <= 0:
        raise ValueError(
            "Cylinder dimensions must be strictly positive, got "
            f"radius={radius}, height={height}"
        )
    return Solid.make_cylinder(radius, height)
