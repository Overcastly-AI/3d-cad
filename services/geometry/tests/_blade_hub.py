"""The blade-hub bodies the in-place and isolation tests share: the QA blade
(a ruled loft, so its sides are B-splines) fused to a cylinder hub (r 22) or a
cone hub (r 24 -> 20), the hub's seam turned *seam_deg*.

Loaded by file path (importlib import-mode: test modules cannot import each
other by name; root pyproject.toml)."""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false

from typing import Any

from build123d import (
    Axis,
    Cylinder,
    Face,
    GeomType,
    Plane,
    Polyline,
    Pos,
    Solid,
    loft,
    make_face,
)

HUB_R = 22.0


def blade() -> Any:
    root = [(18.0, -1.0), (50.0, -8.0), (50.0, -6.0), (18.0, 1.0)]
    tip = [(18.0, -1.0), (50.0, -14.0), (50.0, -12.0), (18.0, 1.0)]
    return loft(
        [
            make_face(Plane.XY.offset(2) * Polyline(*root, close=True)),
            make_face(Plane.XY.offset(18) * Polyline(*tip, close=True)),
        ],
        ruled=True,
    )


def cylinder_hub(seam_deg: float) -> Solid:
    hub = (Pos(0, 0, 10) * Cylinder(HUB_R, 20)).rotate(Axis.Z, seam_deg)
    (solid,) = hub.fuse(blade()).clean().solids()
    return solid


def cone_hub(seam_deg: float) -> Solid:
    hub = Solid.make_cone(24, 20, 20).rotate(Axis.Z, seam_deg)
    (solid,) = hub.fuse(blade()).clean().solids()
    return solid


def round_face(body: Solid) -> Face:
    """The hub's cylinder or cone face."""
    (face,) = [
        f for f in body.faces() if f.geom_type in (GeomType.CYLINDER, GeomType.CONE)
    ]
    return face
