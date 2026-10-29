"""Roof 1.7.0's gable ends: the studs and sheathing over each end wall
(GABLE-END-STUDS, RESEARCH §23).

A gable's end walls stop at their top plates, leaving the triangle under
the end rafters open. Chief Architect's Build Framing frames a gable wall
up to the roof with its studs in line with the wall below, and carries the
wall's layers up with it; ``loft.roof`` 1.7.0 adds **Gable ends** to a gable
on picked walls (an outline):

* **Studs and sheathing** (the default): on each end wall's top plate, a
  stud at each of the wall's INNER layout centres (its start and end studs
  have no triangle over them: they stand under the eave walls' rafters),
  the wall's stud profile and material, the wall's depth deep. Each is cut
  on the slope to the rafters' UNDERSIDE plane, ``plate - heel + run x
  slope`` at ``run`` from its eave wall's outside face, long point up: the
  gable-end rafter, flush with the wall's outside face, bears on the cut
  tops face to face. A stud under the ridge board (a span that puts a
  layout centre at the ridge) is cut square to the board's underside, as a
  ridge post. Then the wall's sheathing, in the wall's product, carried up
  from its top in the wall's own columns (its 48 in strips from its start
  and the corner rips past its ends) to the rafters' TOP plane, the plane
  the roof deck lies on: it covers the end rafter's outside face, as a
  framer sheathes a gable with no rake overhang, and meets nothing (it is
  outside the framing).
* **None**: 1.6.0's roof exactly.

A layout ceiling joist that would lie on an end wall's top plate (a common
hard by the end rafter, over the wall) is not framed when the gable ends
are: the end wall carries the ceiling edge there, as at the end rafters.

A roof on its typed bearing knows no end walls, and a hip has none: both
frame no gable ends.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from loft_wire.features import (
    ExtrudeFeature,
    ExtrudeParamsV1,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import (
    ChoiceInput,
    ChoiceOption,
    MemberMetadata,
    PluginInput,
    PluginMemberRole,
    member_id,
)
from loft_wire.sheet_goods import SheetGood
from loft_wire.sketch import Point2D

from loft_plugins.api import ExpandInputs, Member
from loft_plugins.builtin import wall as wall_v1
from loft_plugins.builtin.house import OutlineWall
from loft_plugins.builtin.roof import GablePlace, Rafter
from loft_plugins.builtin.sheathing import (
    PANEL_WIDTH,
    FacePlane,
    face_plane,
    loops_entities,
    strips,
)

GABLE_STUDS = "studs_sheathing"
GABLE_NONE = "none"
#: A stud shorter than this at its short point (in) is not framed: it would
#: be a sliver under the rafter, below the kernel's tolerance.
MIN_STUD_IN = 1.0 / 16.0
#: Rounding of a coordinate (the inputs' 1e-9 in).
_DIGITS = 9

GABLE_INPUTS: list[PluginInput] = [
    ChoiceInput(
        kind="choice",
        name="gable_ends",
        label="Gable ends",
        description="Gable on picked walls: Studs and sheathing frames each end "
        "wall's gable, a stud at each of the wall's layout centres cut on the "
        "slope to the rafters' underside, and carries the wall's sheathing up "
        "to the roof plane. A roof on its typed bearing, or a hip, frames none.",
        options=[
            ChoiceOption(value=GABLE_STUDS, label="Studs and sheathing"),
            ChoiceOption(value=GABLE_NONE, label="None"),
        ],
        default=GABLE_STUDS,
    ),
]

GABLE_ROLES = [
    PluginMemberRole(role="gable_stud", title="Gable stud"),
    PluginMemberRole(
        role="gable_sheathing",
        title="Sheathing",
        description="An end wall's sheathing carried up its gable.",
    ),
]


def _mm(value: float) -> float:
    return value * MM_PER_INCH


@dataclass(frozen=True)
class GableSection:
    """The roof over an end wall, across the span from the low eave wall's
    outside face (``a``, inches), heights in world Z."""

    rafter: Rafter
    span: float
    ridge_half: float  # half the ridge board's thickness
    ridge_bottom: float

    def underside(self, a: float) -> float:
        """The rafters' underside over *a*: the nearer eave's plane."""
        return min(self.rafter.bottom(a), self.rafter.bottom(self.span - a))

    def top(self, a: float) -> float:
        """The rafters' top plane over *a* (the roof deck's underside)."""
        return self.underside(a) + self.rafter.plumb_depth

    @property
    def peak(self) -> float:
        return self.span / 2

    def under_ridge(self, a0: float, a1: float) -> bool:
        lo, hi = self.peak - self.ridge_half, self.peak + self.ridge_half
        return min(a1, hi) - max(a0, lo) > 1e-9


def clear_of_gables(
    walls: Sequence[OutlineWall], place: GablePlace
) -> list[tuple[float, float]]:
    """The end walls' extents along the ridge (world, inches): what a
    ceiling joist must keep off when the gable ends are framed."""
    out: list[tuple[float, float]] = []
    for wall in walls:
        frame = wall_v1.WallFrame.of(wall.spec)
        ends = [frame.plan(0.0, v) for v in (0.0, wall.spec.thickness)]
        along = [p[0] if place.along_x else p[1] for p in ends]
        out.append((min(along), max(along)))
    return out


def gable_ends(
    inputs: ExpandInputs,
    members: Sequence[Member],
    wall_id: uuid.UUID,
    walls: Sequence[OutlineWall],
    good: SheetGood | None,
    section: GableSection,
    place: GablePlace,
) -> list[Member]:
    """Each end wall's gable studs, then its sheathing (module docstring),
    numbered after the roof's *members* of each role. *walls* are the
    outline walls that do not define the slope, in outline order; *good*
    their sheathing (``None``: studs only)."""
    used = {
        role: sum(1 for m in members if m.role == role)
        for role in ("plane", "section", "gable_stud", "gable_sheathing")
    }
    out: list[Member] = []

    def index(role: str) -> int:
        return used[role] + sum(1 for m in out if m.role == role)

    for wall in walls:
        spec = wall.spec
        frame = wall_v1.WallFrame.of(spec)
        plane = face_plane(spec)
        datums, ref = plane.members(
            inputs, f"gable/{wall.line_id}/", index("plane"), role="plane"
        )
        out += datums
        outward: Literal["normal", "reverse"] = "reverse" if plane.reverse else "normal"
        inward: Literal["normal", "reverse"] = (
            "normal" if outward == "reverse" else "reverse"
        )
        plate = spec.elevation + spec.height  # world Z of the plate's top

        def across(u: float, frame: wall_v1.WallFrame = frame) -> float:
            px, py = frame.plan(u, 0.0)
            return round((py - place.y0) if place.along_x else (px - place.x0), _DIGITS)

        def sketch(
            points: list[tuple[float, float]],
            spec: wall_v1.WallSpec = spec,
            plane: FacePlane = plane,
        ) -> list[Point2D]:
            # (u, world Z) -> the face plane's sketch, Z above the wall's base.
            return [plane.sketch_point(u, z - spec.elevation) for u, z in points]

        # The studs: the wall's inner layout centres.
        t = spec.stud.thickness_in
        centres = wall_v1.stud_centres(spec.length, spec.spacing, t)
        slots = wall_v1.stud_slots(spec.length, spec.spacing, t)
        meta = MemberMetadata(profile=spec.stud.name, material=spec.stud_material)
        for centre, slot in list(zip(centres, slots, strict=True))[1:-1]:
            u0, u1 = centre - t / 2, centre + t / 2
            a0, a1 = across(u0), across(u1)
            if section.under_ridge(min(a0, a1), max(a0, a1)):
                z0 = z1 = section.ridge_bottom
            else:
                z0, z1 = section.underside(a0), section.underside(a1)
            if min(z0, z1) - plate < MIN_STUD_IN:
                continue
            name = f"{wall.line_id}/{slot}"
            section_name = f"gable_stud/{name}"
            outline = sketch([(u0, plate), (u1, plate), (u1, z1), (u0, z0)])
            out.append(
                Member(
                    "section",
                    index("section"),
                    SketchFeature(
                        type="sketch",
                        version=1,
                        params=SketchParamsV1(
                            plane=ref,
                            entities=list(loops_entities([outline])),
                            constraints=[],
                        ),
                    ),
                    name=section_name,
                )
            )
            out.append(
                Member(
                    "gable_stud",
                    index("gable_stud"),
                    ExtrudeFeature(
                        type="extrude",
                        version=1,
                        params=ExtrudeParamsV1(
                            profile=inputs.ref(
                                "section", index("section") - 1, section_name
                            ),
                            distance_mm=_mm(spec.thickness),
                            operation="add",
                            merge=False,
                            direction=inward,
                        ),
                    ),
                    meta,
                    name=name,
                )
            )

        if good is None:
            continue
        # The sheathing: the wall's columns, and its corner rips where it
        # has them, carried up to the rafters' top plane.
        columns: list[tuple[str, float, float]] = [
            (f"exterior/{k}", u0, u1)
            for k, (u0, u1) in enumerate(strips(spec.length, PANEL_WIDTH))
        ]
        rip = spec.thickness + good.thickness_in
        for end, u0, u1 in (
            ("start", -rip, 0.0),
            ("end", spec.length, spec.length + rip),
        ):
            panel = member_id(wall_id, "sheathing", 0, f"{wall.line_id}/corner/{end}")
            if panel in inputs.earlier:
                columns.append((f"corner/{end}", u0, u1))
        panel_meta = MemberMetadata(profile=good.name, material=good.material)
        for col, u0, u1 in columns:
            a0, a1 = across(u0), across(u1)
            points = [(u0, plate), (u1, plate), (u1, section.top(a1))]
            lo, hi = min(a0, a1), max(a0, a1)
            if lo + 1e-9 < section.peak < hi - 1e-9:
                # The peak's u: a runs linearly with u along the wall.
                u = u0 + (section.peak - a0) / (a1 - a0) * (u1 - u0)
                points.append((round(u, _DIGITS), section.top(section.peak)))
            points.append((u0, section.top(a0)))
            name = f"{wall.line_id}/{col}"
            section_name = f"gable_sheathing/{name}"
            out.append(
                Member(
                    "section",
                    index("section"),
                    SketchFeature(
                        type="sketch",
                        version=1,
                        params=SketchParamsV1(
                            plane=ref,
                            entities=list(loops_entities([sketch(points)])),
                            constraints=[],
                        ),
                    ),
                    name=section_name,
                )
            )
            out.append(
                Member(
                    "gable_sheathing",
                    index("gable_sheathing"),
                    ExtrudeFeature(
                        type="extrude",
                        version=1,
                        params=ExtrudeParamsV1(
                            profile=inputs.ref(
                                "section", index("section") - 1, section_name
                            ),
                            distance_mm=good.thickness_mm,
                            operation="add",
                            merge=False,
                            direction=outward,
                        ),
                    ),
                    panel_meta,
                    name=name,
                )
            )
    return out
