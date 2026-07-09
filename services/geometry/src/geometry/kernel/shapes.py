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
