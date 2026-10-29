"""Roof 1.6.0's ceiling joists: the rafter ties of a gable (CEILING-JOISTS,
IRC R802.5.2, RESEARCH §23).

A gable's rafters thrust their feet outward; ceiling joists nailed to each
rafter pair at the plates tie them, so the walls do not spread. Chief
Architect's Build Framing lays ceiling joists out with the roof framing, in
the rafter direction, one beside each common rafter. ``loft.roof`` 1.6.0
adds **Ceiling joists** to a gable on picked walls (an outline):

* **Beside each common** (the default): one joist on the bearing walls'
  plates, face-nailed to the far face (the face the rafter is extruded to:
  +X for a ridge along X, +Y along Y) of every INNER common pair. The
  gable-end rafters get none: the gable wall under them carries the ceiling
  edge. A layout common so near the end rafter that its far face leaves no
  room takes its joist on its near face instead.
* **None**: 1.5.0's roof exactly.

A joist is ONE piece from the outside face of one bearing wall to the other
(the span), its bottom on the plates' top. Its two top corners are snipped
to the rafters' top plane, as a framer cuts them so the roof sheathing lies
flat: the plane is ``plate - heel + plumb depth`` high at the wall's outside
face and rises at the pitch, so the snip is ``delta = depth + heel - plumb``
down the end and ``delta / slope`` along the top (B7: 1.560920 and 3.121840).

A joist whose top would pass the ridge board's underside (a low pitch, a
deep joist) does not fit: the roof is built without joists, and the stored
roof carries ``ceiling_joists_omitted`` naming why and the deepest joist
that fits (:func:`joist_misfit`). Chief warns there; it does not block the
roof.

A roof on its typed bearing, or a Hip, frames none: Chief builds ceiling
joists from the rooms its walls enclose, and a typed bearing knows no walls;
a hip's joists stop at the hips' jacks (a later rung, BACKLOG note
CEILING-JOISTS-HIP).
"""

from collections.abc import Sequence
from typing import Literal

from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import (
    LUMBER_PROFILES_BY_KEY,
    MM_PER_INCH,
    LumberProfileKey,
)
from loft_wire.plugins import (
    ChoiceInput,
    ChoiceOption,
    MemberMetadata,
    PluginInput,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, lumber_options
from loft_plugins.builtin.deck import joist_centres
from loft_plugins.builtin.roof import (
    GablePlace,
    Rafter,
    inches,
    layout_slots,
    material_input,
    number_name,
)

CEILING_BESIDE = "beside_common"
CEILING_NONE = "none"
#: A snip shallower than this (in) is left square: the joist's corner is
#: then at most this far above the rafters' top plane.
MIN_SNIP_IN = 1e-6
_JOISTS: list[LumberProfileKey] = [
    "us_2x4",
    "us_2x6",
    "us_2x8",
    "us_2x10",
    "us_2x12",
]

CEILING_INPUTS: list[PluginInput] = [
    ChoiceInput(
        kind="choice",
        name="ceiling_joists",
        label="Ceiling joists",
        description="Gable on picked walls: the rafter ties (IRC R802.5.2). "
        "Beside each common: a joist on the plates, nailed to the side of every "
        "inner common pair, its top corners snipped to the roof plane; the "
        "gable-end rafters get none. A roof on its typed bearing, or a hip, "
        "frames none.",
        options=[
            ChoiceOption(value=CEILING_BESIDE, label="Beside each common"),
            ChoiceOption(value=CEILING_NONE, label="None"),
        ],
        default=CEILING_BESIDE,
    ),
    ChoiceInput(
        kind="choice",
        name="ceiling_joist_profile",
        label="Ceiling joist size",
        description="Ceiling joist size: one piece from wall face to wall face.",
        options=lumber_options(_JOISTS),
        default="us_2x8",
    ),
]

CEILING_MATERIAL = material_input("ceiling_joist_material", "Ceiling joist material")

CEILING_ROLE = PluginMemberRole(role="ceiling_joist", title="Ceiling joist")


def _mm(value: float) -> float:
    return value * MM_PER_INCH


def joist_profile(
    rafter: Rafter, span: float, depth: float
) -> list[tuple[float, float]]:
    """A ceiling joist's side profile (across, Z) from the low wall's outside
    face (0) to the other's (*span*), counter-clockwise: the bottom on the
    plates, each top corner snipped to the rafters' top plane."""
    plate = rafter.plate_height
    top = plate + depth
    snip = top - (rafter.bottom(0.0) + rafter.plumb_depth)
    if snip <= MIN_SNIP_IN:
        return [(0.0, plate), (span, plate), (span, top), (0.0, top)]
    run = snip / rafter.slope
    return [
        (0.0, plate),
        (span, plate),
        (span, top - snip),
        (span - run, top),
        (run, top),
        (0.0, top - snip),
    ]


def _fits(rafter: Rafter, depth: float, ridge_depth: float) -> bool:
    """A joist *depth* deep on the plates clears the ridge board's underside
    (touching it is face to face)."""
    return rafter.plate_height + depth <= rafter.top_at_ridge - ridge_depth + 1e-9


def joist_misfit(inputs: ExpandInputs, rafter: Rafter) -> str | None:
    """Why the chosen ceiling joist cannot be framed under this gable, with
    what to pick instead, or ``None`` when it fits."""
    joist = inputs.lumber("ceiling_joist_profile")
    ridge = inputs.lumber("ridge_profile")
    if _fits(rafter, joist.width_in, ridge.width_in):
        return None
    top = rafter.plate_height + joist.width_in
    ridge_bottom = rafter.top_at_ridge - ridge.width_in
    fitting = [
        p.name
        for p in (LUMBER_PROFILES_BY_KEY[key] for key in _JOISTS)
        if _fits(rafter, p.width_in, ridge.width_in)
    ]
    pick = (
        f"choose a {fitting[-1]} or shallower ceiling joist, a steeper pitch or "
        "a deeper ridge board"
        if fitting
        else "choose a steeper pitch or a deeper ridge board"
    )
    return (
        f"Ceiling joists not framed: a {joist.name} joist's top (Z "
        f"{top:.3f} in) would pass the ridge board's underside (Z "
        f"{ridge_bottom:.3f} in) at this pitch, so the roof is built without "
        f"them. To tie the rafters, {pick}; or set Ceiling joists to None."
    )


def ceiling_joists(
    inputs: ExpandInputs,
    members: Sequence[Member],
    rafter: Rafter,
    span: float,
    length: float,
    place: GablePlace,
    notes: list[str] | None = None,
) -> list[Member]:
    """The gable's ceiling joists at *place* (none when the input is None),
    each a datum, a section and the joist, numbered after the roof's
    *members* of each role. A joist that does not fit under the ridge
    frames none, and why is appended to *notes* (the stored roof's
    warning, never a refusal)."""
    if inputs.choice("ceiling_joists") != CEILING_BESIDE:
        return []
    joist = inputs.lumber("ceiling_joist_profile")
    misfit = joist_misfit(inputs, rafter)
    if misfit is not None:
        if notes is not None:
            notes.append(misfit)
        return []
    t = inputs.lumber("rafter_profile").thickness_in
    tj = joist.thickness_in
    spacing = inches("spacing_mm", inputs)
    centres = joist_centres(length, spacing, t)
    slots = layout_slots(len(centres))
    start, across = (place.x0, place.y0) if place.along_x else (place.y0, place.x0)
    base: Literal["YZ", "XZ"] = "YZ" if place.along_x else "XZ"
    axis = base.lower()
    direction: Literal["normal", "reverse"] = "normal" if place.along_x else "reverse"
    outline = [(across + y, z) for y, z in joist_profile(rafter, span, joist.width_in)]
    meta = MemberMetadata(
        profile=joist.name, material=inputs.material("ceiling_joist_material")
    )
    end_face = length - t  # the far end rafter's near face, from the start
    used = {
        role: sum(1 for m in members if m.role == role)
        for role in ("plane", "section", "ceiling_joist")
    }
    out: list[Member] = []

    def index(role: str) -> int:
        return used[role] + sum(1 for m in out if m.role == role)

    for centre, slot in list(zip(centres, slots, strict=True))[1:-1]:
        x0 = centre - t / 2
        # The rafter's far face, as gable_on places the rafter: the joist's
        # face is on it, or (no room before the end rafter) a joist's
        # thickness before its near face.
        far = x0 + t
        x = far if far + tj <= end_face + 1e-9 else x0 - tj
        at = x if start == 0.0 else start + x
        plane_name = f"{axis}/{number_name(at)}"
        offset = _mm(at) if place.along_x else -_mm(at) + 0.0
        out.append(
            Member(
                "plane",
                index("plane"),
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(base=base, offset_mm=offset),
                ),
                name=plane_name,
            )
        )
        plane: DatumPlaneRef | FeatureRef = inputs.ref(
            "plane", index("plane") - 1, plane_name
        )
        section_name = f"ceiling_joist/{slot}"
        out.append(
            Member(
                "section",
                index("section"),
                SketchFeature(
                    type="sketch",
                    version=1,
                    params=SketchParamsV1(
                        plane=plane,
                        entities=list(_polygon(outline)),
                        constraints=[],
                    ),
                ),
                name=section_name,
            )
        )
        out.append(
            Member(
                "ceiling_joist",
                index("ceiling_joist"),
                ExtrudeFeature(
                    type="extrude",
                    version=1,
                    params=ExtrudeParamsV1(
                        profile=inputs.ref(
                            "section", index("section") - 1, section_name
                        ),
                        distance_mm=_mm(tj),
                        operation="add",
                        merge=False,
                        direction=direction,
                    ),
                ),
                meta,
                name=slot,
            )
        )
    return out


def _polygon(points: list[tuple[float, float]]) -> list[SketchLine]:
    n = len(points)
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=Point2D(x=_mm(points[i][0]), y=_mm(points[i][1])),
            end=Point2D(x=_mm(points[(i + 1) % n][0]), y=_mm(points[(i + 1) % n][1])),
        )
        for i in range(n)
    ]
