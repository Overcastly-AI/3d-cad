"""Mass properties and topology counts of a B-rep shape (OCCT GProp).

Measurements come from the exact B-rep (GProp integration + optimal AABB),
never from a tessellation — mesh quality cannot perturb them.

The OCP wheel ships no type stubs, so the raw GProp calls below are opaque
to pyright; the directives scope that relaxation to this file only, and the
fully-typed :class:`ShapeProperties` DTO keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

from build123d import Solid
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from geometry.schemas import BoundingBox, ShapeProperties, TopologyCounts, Vec3


def measure_shape(shape: Solid) -> ShapeProperties:
    """Compute volume, surface area, centroid, exact AABB, topology counts."""
    if shape.wrapped is None:
        raise ValueError("Cannot measure an empty shape")

    volume_props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, volume_props)
    surface_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, surface_props)

    centroid = volume_props.CentreOfMass()
    bbox = shape.bounding_box(optimal=True)

    return ShapeProperties(
        volume=float(volume_props.Mass()),
        surface_area=float(surface_props.Mass()),
        centroid=Vec3(
            x=float(centroid.X()), y=float(centroid.Y()), z=float(centroid.Z())
        ),
        bounding_box=BoundingBox(
            min=Vec3(x=bbox.min.X, y=bbox.min.Y, z=bbox.min.Z),
            max=Vec3(x=bbox.max.X, y=bbox.max.Y, z=bbox.max.Z),
        ),
        topology=TopologyCounts(
            faces=len(shape.faces()),
            edges=len(shape.edges()),
            shells=len(shape.shells()),
        ),
    )
