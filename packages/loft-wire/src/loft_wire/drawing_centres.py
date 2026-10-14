"""Hole centres on a drawing: the centre-mark primitive and the centre dimensions.

QA-DRAWING-CENTRE-MARKS. A drawing that shows a hole only as a circle can give it a
diameter, never a POSITION, and a hole's position is most of what a shop needs from
a print. Fusion 360, SolidWorks and Onshape all solve it the same way, and so does
this module:

* every circle seen end-on gets an automatic CENTRE MARK (ISO 128-20 / ASME Y14.2:
  a thin cross through the centre, carried a short way past the circle), and
* that centre is a dimension ANCHOR: a linear dimension runs from a straight edge to
  a hole centre, or between two hole centres.

A centre is named through its CIRCULAR EDGE — the shipped
:class:`~loft_wire.features.EdgeSignature` of the hole's rim — exactly as a
point-to-point endpoint is named through its edge
(:class:`~loft_wire.drawings.DimensionEndpointRef`). So it resolves through the same
durable anchor tiers and name guard as every other drawing reference, and follows the
hole when a part edit moves it. Nothing new is persisted beyond the signature.

Both measurement modes are measured IN THE VIEW PLANE. A hole's two rims project to
one centre, and the user cannot tell which rim they picked; the in-plane distance is
the only value that does not depend on it. It is also what the drafting convention
means: a horizontal hole-position dimension in a top view is the distance along the
view's horizontal axis, whatever depth the two features sit at.

Split into its own module (FILE-SIZE-RATCHET) and re-exported from
:mod:`loft_wire.drawings`, which joins the two measurements to its
``LinearMeasurement`` union additively — every stored drawing loads unchanged.
"""

from typing import Literal

from pydantic import BaseModel, Field

from loft_wire.features import EdgeSignature

#: How a centre-to-centre dimension is drawn and measured (the Fusion / SolidWorks
#: linear-dimension orientations): ``horizontal`` and ``vertical`` measure along the
#: view's own x / y axis, ``aligned`` the straight in-plane distance.
LinearOrientation = Literal["aligned", "horizontal", "vertical"]


class EdgeToCentreMeasurement(BaseModel):
    """The perpendicular distance from a straight edge to a hole centre, in the view.

    The hole-position dimension: the plate's left edge to the hole's centre. Measured
    in the VIEW PLANE (the module docstring says why), perpendicular to the edge as
    the view draws it, so a vertical edge gives a horizontal dimension and a
    horizontal edge a vertical one — the Fusion behaviour for a line-to-point
    dimension. An edge seen end-on in the view has no direction there, and is refused
    as ``dimension_not_placeable`` rather than measured.
    """

    mode: Literal["edge_to_centre"] = "edge_to_centre"
    edge: EdgeSignature = Field(description="The straight model edge measured from")
    centre: EdgeSignature = Field(
        description="The circular model edge (a hole rim) whose CENTRE is measured to"
    )


class CentreToCentreMeasurement(BaseModel):
    """The distance between two hole centres, in the view.

    ``orientation`` is the drafting choice the user makes by where they place the
    dimension: ``horizontal`` / ``vertical`` measure along the view's x / y axis (the
    hole-pattern pitch), ``aligned`` the straight distance between the centres.
    """

    mode: Literal["centre_to_centre"] = "centre_to_centre"
    a: EdgeSignature = Field(description="First circular model edge (its centre)")
    b: EdgeSignature = Field(description="Second circular model edge (its centre)")
    orientation: LinearOrientation = Field(
        default="aligned",
        description="'horizontal' / 'vertical' measure along the view's x / y axis; "
        "'aligned' (default) the straight in-plane distance",
    )


class ComposedCentreLine(BaseModel):
    """One drawn segment of a centre mark (final sheet-SVG space, mm)."""

    x1: float
    y1: float
    x2: float
    y2: float


class ComposedCentreMark(BaseModel):
    """A placed centre mark on a circle seen end-on (ISO 128-20 / ASME Y14.2).

    A thin chain-style cross: a short dash crossing at the centre, a gap, then a long
    dash carried 3 mm past the circle on each of the four arms — or one continuous
    thin line per axis on a circle too small for the gap to read (ISO 128-24 permits
    it). The segments are explicit geometry, not a dash pattern, so SVG, PDF and DXF
    draw the same marks.

    One mark per distinct centre: the rims of a through hole and a counterbore's two
    circles share one, sized to the largest. ``edge_index`` points into the view's
    ``edges`` (and the canonically-aligned evaluate edges) at the circle the mark
    stands for — a visible, dimensionable one where there is one — which is how the
    sheet turns a pick on the mark into the circle's signature.
    """

    cx: float = Field(description="Centre x (sheet-SVG mm)")
    cy: float = Field(description="Centre y (sheet-SVG mm, y-down)")
    r: float = Field(description="Radius of the largest circle on this centre (mm)")
    edge_index: int = Field(
        ge=0, description="Index into the view's `edges` of the circle it marks"
    )
    lines: list[ComposedCentreLine] = Field(
        description="The mark's drawn segments, horizontal arm first"
    )
