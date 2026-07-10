"""Geometry boundary DTOs — the only shapes that cross the service boundary.

Single source of truth (CLAUDE.md DRY rule) for the models served by the
geometry service AND proxied by the gateway under ``/api/v1/geometry/*`` —
neither side hand-duplicates them. Pydantic models only (CLAUDE.md service
boundaries): kernel types (TopoDS/build123d) never appear in these
definitions. These models drive the OpenAPI contract (``just gen``).

Units: millimetres for lengths, mm^2 / mm^3 for area / volume. The GLB
payload itself is in metres per the glTF specification.
"""

from typing import Literal

from pydantic import BaseModel, Field

#: Default tessellation linear deflection (mm) — viewport-quality meshes.
DEFAULT_LINEAR_DEFLECTION = 0.1

#: Response header carrying compact-JSON ``TessellationMetadata`` next to a GLB.
PROPERTIES_HEADER = "X-Loft-Properties"

#: Media type of the binary glTF tessellation payload.
GLB_MEDIA_TYPE = "model/gltf-binary"


class BoxParams(BaseModel):
    """Axis-aligned box dimensions (mm); the min corner sits at the origin."""

    x: float = Field(gt=0, description="Size along X (mm)")
    y: float = Field(gt=0, description="Size along Y (mm)")
    z: float = Field(gt=0, description="Size along Z (mm)")


class TessellateRequest(BaseModel):
    """Build a parametric shape and tessellate it to GLB."""

    shape: Literal["box"] = Field(description="Shape kind (parametric box only, today)")
    params: BoxParams
    linear_deflection: float = Field(
        default=DEFAULT_LINEAR_DEFLECTION,
        gt=0,
        description=(
            "Max distance (mm) between a curve and its tessellation; lower = finer mesh"
        ),
    )


class Vec3(BaseModel):
    """A 3D point/vector in model space (mm)."""

    x: float
    y: float
    z: float


class BoundingBox(BaseModel):
    """Axis-aligned bounding box (mm), exact (not mesh-inflated)."""

    min: Vec3
    max: Vec3


class TopologyCounts(BaseModel):
    """B-rep entity counts — asserted exactly by the golden-model suite."""

    faces: int
    edges: int
    shells: int


class ShapeProperties(BaseModel):
    """Mass properties + topology of the evaluated B-rep shape."""

    volume: float = Field(description="Volume (mm^3)")
    surface_area: float = Field(description="Total surface area (mm^2)")
    centroid: Vec3 = Field(description="Centre of mass (mm)")
    bounding_box: BoundingBox
    topology: TopologyCounts


class MeshStats(BaseModel):
    """Statistics of the tessellated GLB artifact."""

    vertices: int
    triangles: int
    glb_bytes: int = Field(description="Size of the binary glTF payload in bytes")


class TessellationMetadata(BaseModel):
    """Everything about a tessellation except the mesh itself.

    Returned as JSON by the ``.../tessellate/meta`` routes and carried,
    compact-serialized, in the ``X-Loft-Properties`` response header of the
    binary ``.../tessellate`` routes (geometry service and gateway proxy).
    """

    properties: ShapeProperties
    mesh: MeshStats
