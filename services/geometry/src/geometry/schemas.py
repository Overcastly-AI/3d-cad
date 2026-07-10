"""Geometry service DTOs — thin re-export of the shared py-kit models.

The boundary models live in :mod:`py_kit.schemas.geometry` (single source of
truth, CLAUDE.md DRY rule) so the gateway proxy types its routes with exactly
the models this service serves. This module stays as the service-local alias,
keeping kernel/API/worker/test imports stable.
"""

from py_kit.schemas.geometry import (
    DEFAULT_LINEAR_DEFLECTION,
    BoundingBox,
    BoxParams,
    MeshStats,
    ShapeProperties,
    TessellateRequest,
    TessellationMetadata,
    TopologyCounts,
    Vec3,
)

__all__ = [
    "DEFAULT_LINEAR_DEFLECTION",
    "BoundingBox",
    "BoxParams",
    "MeshStats",
    "ShapeProperties",
    "TessellateRequest",
    "TessellationMetadata",
    "TopologyCounts",
    "Vec3",
]
