"""Geometry boundary DTOs — the only shapes that cross the service boundary.

Single source of truth (CLAUDE.md DRY rule) for the models served by the
geometry service AND proxied by the gateway under ``/api/v1/geometry/*`` —
neither side hand-duplicates them. Pydantic models only (CLAUDE.md service
boundaries): kernel types (TopoDS/build123d) never appear in these
definitions. These models drive the OpenAPI contract (``just gen``).

Units: millimetres for lengths, mm^2 / mm^3 for area / volume. The GLB
payload itself is in metres per the glTF specification.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

#: Default tessellation linear deflection (mm) — viewport-quality meshes.
DEFAULT_LINEAR_DEFLECTION = 0.1

#: Default angular deflection (rad) between adjacent tessellation segments.
#: Single source for the fixed tessellation setting AND the STL export
#: default, so "default quality" means the same mesh on both paths.
DEFAULT_ANGULAR_DEFLECTION = 0.1

#: Response header carrying compact-JSON ``TessellationMetadata`` next to a GLB.
PROPERTIES_HEADER = "X-Loft-Properties"

#: Media type of the binary glTF tessellation payload.
GLB_MEDIA_TYPE = "model/gltf-binary"

#: Supported export file formats (``POST /api/v1/export``).
ExportFormat = Literal["step", "stl"]

#: Media type per export format. STEP part 21 is IANA ``model/step``;
#: binary STL is IANA ``model/stl``.
EXPORT_MEDIA_TYPES: dict[str, str] = {
    "step": "model/step",
    "stl": "model/stl",
}


def tessellate_responses(description: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` block for a binary-GLB tessellate route.

    Single source of truth (DRY) for the geometry service and the gateway
    proxy: a 200 with a ``model/gltf-binary`` body and compact-JSON
    ``TessellationMetadata`` in the ``X-Loft-Properties`` header. Only the
    ``description`` differs per route, so it is the one parameter.
    """
    return {
        200: {
            "description": description,
            "content": {
                GLB_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}
            },
            "headers": {
                PROPERTIES_HEADER: {
                    "description": "TessellationMetadata as compact JSON",
                    "schema": {"type": "string"},
                }
            },
        }
    }


class BoxParams(BaseModel):
    """Axis-aligned box dimensions (mm); the min corner sits at the origin."""

    x: float = Field(gt=0, description="Size along X (mm)")
    y: float = Field(gt=0, description="Size along Y (mm)")
    z: float = Field(gt=0, description="Size along Z (mm)")


class CylinderParams(BaseModel):
    """Right circular cylinder (mm): base disc centred at the origin in the
    XY plane, axis along +Z."""

    radius: float = Field(gt=0, description="Radius (mm)")
    height: float = Field(gt=0, description="Height along +Z (mm)")


#: Supported parametric shape kinds (wire discriminator of ``ShapeRequest``).
ShapeKind = Literal["box", "cylinder"]

#: Union of per-shape parameter models. Field sets are disjoint by design so
#: pydantic union validation is unambiguous; the shape/params pairing itself
#: is enforced by ``ShapeRequest``.
ShapeParams = BoxParams | CylinderParams


class ShapeRequest(BaseModel):
    """Parametric shape selection — the base every evaluation request shares.

    ``TessellateRequest`` and ``ExportRequest`` extend it, so a shape that can
    be tessellated can always be exported with the same params (DRY: one
    shape/params contract, two artifact kinds). ``shape`` and ``params`` must
    agree (``box`` ↔ ``BoxParams``, ``cylinder`` ↔ ``CylinderParams``);
    mismatches fail validation with a 422.
    """

    shape: ShapeKind = Field(description="Shape kind; must match the params model")
    params: ShapeParams = Field(description="Parameters of the selected shape kind")

    @model_validator(mode="after")
    def _params_match_shape(self) -> Self:
        """Reject a ``shape`` kind paired with another kind's params."""
        match self.shape:  # exhaustive: pyright flags new kinds added to ShapeKind
            case "box":
                expected: type[BoxParams] | type[CylinderParams] = BoxParams
            case "cylinder":
                expected = CylinderParams
        if not isinstance(self.params, expected):
            raise ValueError(
                f"shape {self.shape!r} requires {expected.__name__} params, "
                f"got {type(self.params).__name__}"
            )
        return self


class TessellateRequest(ShapeRequest):
    """Build a parametric shape and tessellate it to GLB."""

    linear_deflection: float = Field(
        default=DEFAULT_LINEAR_DEFLECTION,
        gt=0,
        description=(
            "Max distance (mm) between a curve and its tessellation; lower = finer mesh"
        ),
    )


class ExportRequest(ShapeRequest):
    """Build a parametric shape and export it as a downloadable CAD file.

    STEP exports the exact B-rep — the deflection fields are meaningless for
    it and ignored. STL is a faceted approximation; its quality fields default
    to the tessellation defaults so the exported mesh matches what the
    viewport shows.
    """

    format: ExportFormat = Field(
        description="Export file format: STEP (exact B-rep) or STL (faceted mesh)"
    )
    linear_deflection: float = Field(
        default=DEFAULT_LINEAR_DEFLECTION,
        gt=0,
        description=(
            "STL facet linear deflection (mm), same semantics as tessellation; "
            "ignored for STEP (exact B-rep)"
        ),
    )
    angular_deflection: float = Field(
        default=DEFAULT_ANGULAR_DEFLECTION,
        gt=0,
        description=(
            "STL facet angular deflection (rad) between adjacent segments; "
            "ignored for STEP (exact B-rep)"
        ),
    )


def export_filename(request: ExportRequest) -> str:
    """Deterministic download filename for an export (Content-Disposition)."""
    return f"{request.shape}.{request.format}"


def export_responses(description: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` block for the binary export route.

    Shared (DRY) between the geometry service and the future gateway proxy: a
    200 whose body is the exported file in one of the export media types, with
    a ``Content-Disposition`` attachment filename.
    """
    binary = {"schema": {"type": "string", "format": "binary"}}
    return {
        200: {
            "description": description,
            "content": {media: binary for media in EXPORT_MEDIA_TYPES.values()},
            "headers": {
                "Content-Disposition": {
                    "description": 'attachment; filename="<shape>.<format>"',
                    "schema": {"type": "string"},
                }
            },
        }
    }


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
