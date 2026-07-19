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

import math
from collections.abc import Sequence

from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from geometry.kernel.types import BodyShape
from geometry.schemas import BoundingBox, ShapeProperties, TopologyCounts, Vec3


def measure_shape(shape: BodyShape) -> ShapeProperties:
    """Compute volume, surface area, centroid, exact AABB, topology counts.

    *shape* is any part body — a single :class:`~build123d.Solid` or a
    :class:`~build123d.Compound` of a multi-body part's disjoint solids (§MB-0).
    OCCT GProp integrates volume / surface / centroid over every subshape solid
    and ``.faces()`` / ``.edges()`` / ``.shells()`` count across them, so a
    compound measures to the same analytic roll-up :func:`combine_properties`
    produces per-body — the STEP round-trip re-measures a multi-solid part this
    way.
    """
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


def combine_properties(parts: Sequence[ShapeProperties]) -> ShapeProperties:
    """Analytic roll-up of a part's multiple disjoint bodies (multi-body §MB-0).

    A part may now end with more than one body (design docs/design/multi-body.md
    §MB-0); its combined mass properties are composed ANALYTICALLY over the body
    set — NO re-mesh, NO boolean — reusing the assembly ``_combine_properties``
    pattern (``geometry.assembly.evaluate``) with identity placements, since a
    part's bodies already share one frame: total volume = Σ per-body volumes;
    combined centroid = volume-weighted Σ of each body's centroid; combined AABB
    = union of the per-body AABBs; surface area + topology counts (faces / edges /
    shells) are summed. Deterministic: a fixed-order float64 reduction over the
    tree-ordered body set (RESEARCH §9). Callers gate on a non-empty set (a part
    with a single body measures that solid directly — byte-identical to before).
    """
    if not parts:
        raise ValueError("combine_properties requires at least one body's properties")
    total_volume = 0.0
    total_area = 0.0
    cx = cy = cz = 0.0
    faces = edges = shells = 0
    min_x = min_y = min_z = math.inf
    max_x = max_y = max_z = -math.inf
    for part in parts:
        total_volume += part.volume
        total_area += part.surface_area
        cx += part.volume * part.centroid.x
        cy += part.volume * part.centroid.y
        cz += part.volume * part.centroid.z
        faces += part.topology.faces
        edges += part.topology.edges
        shells += part.topology.shells
        box = part.bounding_box
        min_x, min_y, min_z = (
            min(min_x, box.min.x),
            min(min_y, box.min.y),
            min(min_z, box.min.z),
        )
        max_x, max_y, max_z = (
            max(max_x, box.max.x),
            max(max_y, box.max.y),
            max(max_z, box.max.z),
        )
    if total_volume != 0.0:
        cx, cy, cz = cx / total_volume, cy / total_volume, cz / total_volume
    return ShapeProperties(
        volume=total_volume,
        surface_area=total_area,
        centroid=Vec3(x=cx, y=cy, z=cz),
        bounding_box=BoundingBox(
            min=Vec3(x=min_x, y=min_y, z=min_z),
            max=Vec3(x=max_x, y=max_y, z=max_z),
        ),
        topology=TopologyCounts(faces=faces, edges=edges, shells=shells),
    )
