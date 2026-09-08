"""Reading DRAWN geometry back off a composed sheet — one walk, shared by the gates.

A `ComposedView` carries three edge kinds (`ComposedLineEdge`, `ComposedCircleEdge`,
`ComposedPolylineEdge` — a sampled arc or curve arrives as the last), and a reader
that handles only lines silently UNDER-measures any view whose outermost feature is
a hole or a curve. That blindness is not hypothetical here: it is why the sheet
border gate could not see ARC-BOUNDS-INFLATE-1, and it is the same shape as the
defect itself. Second real use (`test_drawings_compose.py` and
`test_drawings_canopy_sheets.py`), so it lives in one place rather than twice.
"""

from __future__ import annotations

from typing import NamedTuple

from py_kit.schemas.drawings import (
    ComposedCircleEdge,
    ComposedEdge,
    ComposedLineEdge,
    ComposedView,
)


class ContentRect(NamedTuple):
    """A view's DRAWN extent in final SVG mm (y-down), caption band excluded."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


def composed_edge_xy(edge: ComposedEdge) -> tuple[list[float], list[float]]:
    """One composed edge's drawn x/y coordinates, for ALL THREE emitted edge kinds."""
    if isinstance(edge, ComposedLineEdge):
        return [edge.x1, edge.x2], [edge.y1, edge.y2]
    if isinstance(edge, ComposedCircleEdge):
        return (
            [edge.cx - edge.r, edge.cx + edge.r],
            [edge.cy - edge.r, edge.cy + edge.r],
        )
    return [p.x_mm for p in edge.points], [p.y_mm for p in edge.points]


def composed_content_rect(view: ComposedView) -> ContentRect | None:
    """The box of everything a view actually DRAWS, or None if it drew nothing.

    Measured from the composed sheet's own emitted coordinates — what the serializers
    write — rather than by re-running the placement helpers, so an assertion over it
    is about the drawing and not about a re-derivation of the same arithmetic.
    """
    xs: list[float] = []
    ys: list[float] = []
    for edge in view.edges:
        edge_xs, edge_ys = composed_edge_xy(edge)
        xs += edge_xs
        ys += edge_ys
    if not xs:
        return None
    return ContentRect(min(xs), min(ys), max(xs), max(ys))
