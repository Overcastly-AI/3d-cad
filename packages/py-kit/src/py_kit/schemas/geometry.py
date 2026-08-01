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

#: FLOOR (mm) for any request-supplied linear deflection — a per-request work
#: bound (engineering audit 2026-07-24 G2: the rate limiter caps request
#: frequency, not cost). Tessellation segment count on a curved edge grows
#: ~1/sqrt(deflection) per curve direction, so triangle count on doubly-curved
#: faces grows ~1/deflection: an unbounded ``linear_deflection=1e-9`` is an
#: OOM/CPU blow-up in ONE authenticated request. 1e-3 mm (1 micron chord
#: error) is 100x finer than the 0.1 mm viewport default — ~10x the default's
#: segment density per direction, ~100x its triangles — and far beyond any
#: display or manufacturing need (machining tolerance is ~10 microns), so no
#: legitimate request feels the ceiling. Below the floor is a typed 422 at
#: parse, never a kernel blow-up.
MIN_LINEAR_DEFLECTION = 1e-3

#: FLOOR (rad) for any request-supplied angular deflection — the angular twin
#: of :data:`MIN_LINEAR_DEFLECTION` (audit G2). Segments per full circle are
#: ~2*pi/deflection: 1e-2 rad (~0.57 deg) caps a circle at ~628 segments, 10x
#: the ~63 of the 0.1 rad default — generous for any STL consumer while
#: bounding the mesh a single request can demand.
MIN_ANGULAR_DEFLECTION = 1e-2

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
        ge=MIN_LINEAR_DEFLECTION,
        description=(
            "Max distance (mm) between a curve and its tessellation; lower = "
            "finer mesh. Floored at MIN_LINEAR_DEFLECTION (work bound, audit G2)."
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
        ge=MIN_LINEAR_DEFLECTION,
        description=(
            "STL facet linear deflection (mm), same semantics as tessellation; "
            "ignored for STEP (exact B-rep). Floored at MIN_LINEAR_DEFLECTION "
            "(work bound, audit G2)."
        ),
    )
    angular_deflection: float = Field(
        default=DEFAULT_ANGULAR_DEFLECTION,
        ge=MIN_ANGULAR_DEFLECTION,
        description=(
            "STL facet angular deflection (rad) between adjacent segments; "
            "ignored for STEP (exact B-rep). Floored at MIN_ANGULAR_DEFLECTION "
            "(work bound, audit G2)."
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
    """Mass properties + topology of the evaluated B-rep shape.

    Two fields are honestly nullable (docs/design/materials.md): ``mass_g`` and
    ``center_of_mass`` are ``null`` whenever ANY contributing body has no
    material assigned. ``null`` means *unknown*, never zero — a body nobody has
    said the material of has no mass to report, and inventing one (0 g, or a
    default steel) is the overstated-surface defect this field exists to avoid.
    A consumer must render absence as absence and must not title a panel "mass"
    on the strength of a null.
    """

    volume: float = Field(description="Volume (mm^3)")
    surface_area: float = Field(description="Total surface area (mm^2)")
    centroid: Vec3 = Field(
        description="Centroid of VOLUME (mm) — the geometric centre. Equal to "
        "the centre of mass only when the whole shape is one material; for a "
        "multi-material roll-up read `center_of_mass` instead."
    )
    mass_g: float | None = Field(
        default=None,
        description="Mass (g) = volume x density, or null when a contributing "
        "body has NO material assigned. Null is 'unknown', NOT zero.",
    )
    center_of_mass: Vec3 | None = Field(
        default=None,
        description="Genuinely mass-weighted centre of mass (mm), or null when "
        "any contributing body has no material. For a single-material shape it "
        "equals `centroid`; for mixed materials it does not.",
    )
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
