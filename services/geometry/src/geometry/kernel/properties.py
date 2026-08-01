"""Mass properties and topology counts of a B-rep shape (OCCT GProp).

Measurements come from the exact B-rep (GProp integration + optimal AABB),
never from a tessellation — mesh quality cannot perturb them.

MASS lives here too (docs/design/materials.md): ``mass = volume x density`` is
computed from the very volume this module just measured, in the same function,
so the two cannot drift. A body whose caller passes no density reports
``mass_g=None`` — absent, never ``0.0``.

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
from py_kit.schemas.materials import mass_g

from geometry.kernel.types import BodyShape
from geometry.schemas import BoundingBox, ShapeProperties, TopologyCounts, Vec3


def measure_shape(
    shape: BodyShape, *, density_kg_m3: float | None = None
) -> ShapeProperties:
    """Compute volume, surface area, centroid, exact AABB, topology counts.

    *shape* is any part body — a single :class:`~build123d.Solid` or a
    :class:`~build123d.Compound` of a multi-body part's disjoint solids (§MB-0).
    OCCT GProp integrates volume / surface / centroid over every subshape solid
    and ``.faces()`` / ``.edges()`` / ``.shells()`` count across them, so a
    compound measures to the same analytic roll-up :func:`combine_properties`
    produces per-body — the STEP round-trip re-measures a multi-solid part this
    way.

    *density_kg_m3* is the body's material density (``None`` = no material
    assigned, the default). With a density the result carries ``mass_g`` =
    volume x density and a ``center_of_mass``; the shape passed here is ONE
    body of ONE material, so its centre of mass IS its volume centroid — the
    mass weighting only becomes visible when bodies of different materials are
    combined (:func:`combine_properties`). Without a density both fields stay
    ``None``: absent, not zero (docs/design/materials.md).
    """
    if shape.wrapped is None:
        raise ValueError("Cannot measure an empty shape")

    volume_props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, volume_props)
    surface_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, surface_props)

    centroid = volume_props.CentreOfMass()
    bbox = shape.bounding_box(optimal=True)

    volume = float(volume_props.Mass())
    centre = Vec3(x=float(centroid.X()), y=float(centroid.Y()), z=float(centroid.Z()))
    mass = mass_g(volume, density_kg_m3)

    return ShapeProperties(
        volume=volume,
        surface_area=float(surface_props.Mass()),
        centroid=centre,
        # One body, one material: the centre of mass coincides with the volume
        # centroid exactly. Reported only when a material says so.
        mass_g=mass,
        center_of_mass=centre if mass is not None else None,
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

    MASS composes the same way and is where the volume/mass distinction stops
    being academic (docs/design/materials.md §3): total mass = Σ per-body masses,
    and the combined ``center_of_mass`` is weighted by MASS, not volume — a steel
    body and an aluminium body of equal volume do not balance at their midpoint.
    Both are ``None`` unless EVERY body has a material: a partial sum would
    understate the mass of the part while looking like a complete answer, which
    is the lie this whole field exists to avoid. ``centroid`` stays
    volume-weighted and is always reported.
    """
    if not parts:
        raise ValueError("combine_properties requires at least one body's properties")
    total_volume = 0.0
    total_area = 0.0
    cx = cy = cz = 0.0
    # Mass roll-up: known only while every body so far has one (see docstring).
    total_mass: float | None = 0.0
    mx = my = mz = 0.0
    faces = edges = shells = 0
    min_x = min_y = min_z = math.inf
    max_x = max_y = max_z = -math.inf
    for part in parts:
        total_volume += part.volume
        total_area += part.surface_area
        cx += part.volume * part.centroid.x
        cy += part.volume * part.centroid.y
        cz += part.volume * part.centroid.z
        if part.mass_g is None or part.center_of_mass is None:
            total_mass = None
        elif total_mass is not None:
            total_mass += part.mass_g
            mx += part.mass_g * part.center_of_mass.x
            my += part.mass_g * part.center_of_mass.y
            mz += part.mass_g * part.center_of_mass.z
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
    center_of_mass: Vec3 | None = None
    if total_mass is not None:
        # A zero total mass can only come from zero total volume (density > 0),
        # in which case the mass-weighted average is undefined; fall back to the
        # volume centroid rather than dividing by zero.
        center_of_mass = (
            Vec3(x=mx / total_mass, y=my / total_mass, z=mz / total_mass)
            if total_mass != 0.0
            else Vec3(x=cx, y=cy, z=cz)
        )
    return ShapeProperties(
        volume=total_volume,
        surface_area=total_area,
        centroid=Vec3(x=cx, y=cy, z=cz),
        mass_g=total_mass,
        center_of_mass=center_of_mass,
        bounding_box=BoundingBox(
            min=Vec3(x=min_x, y=min_y, z=min_z),
            max=Vec3(x=max_x, y=max_y, z=max_z),
        ),
        topology=TopologyCounts(faces=faces, edges=edges, shells=shells),
    )
