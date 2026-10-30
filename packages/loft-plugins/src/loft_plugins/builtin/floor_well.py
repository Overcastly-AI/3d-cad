"""A floor on walls, with a framed stairwell (SECOND-FLOOR, RESEARCH §23).

``loft.floor`` 1.4.0 is 1.3.0 plus two things a second storey needs, each
1.3.0's floor member for member when left at its default:

* **On walls** (a pick of ``loft.wall`` features, Revit's Pick Walls as the
  roof takes them). The floor bears on the picked walls' top plates: its
  base elevation is their plate (the top of the top plate) and it has no
  sill plates, its rims and end joists standing on the plates, as Chief
  Architect's Build Floor frames the floor of the level above on the walls
  below it and Revit hosts a floor on a level. The plan stays the floor's own
  (its outline or typed rectangle); every picked wall must stand under it,
  all at one plate height (:func:`~loft_plugins.builtin.house.floor_on_walls`).
  Walls then stand on this floor (``loft.wall``'s On floor reads its top),
  and a roof on those walls.
* **Stairwell** (None, or a Framed opening typed in the floor's own frame:
  its near corner along the width and depth from the start corner, and its
  size each way), as Chief's Auto Stairwell and Revit's shaft opening cut a
  floor. The opening is framed as IRC R502.10 and every framing guide frame
  it: TRIMMERS doubled along both sides parallel to the joists, rim to rim;
  HEADERS doubled across both ends, between the inner trimmers, hung on them;
  and TAIL JOISTS from each header to the rim, on the joist layout. A layout
  joist that lands exactly where an outer trimmer ply goes IS that ply (B7's
  joists at X 16 and 64, "each doubled inside"), keeping its id; one inside
  the opening is cut into its two tails; one that would collide with a
  trimmer is left out (the trimmer carries its load). The subfloor's panels
  are cut round the opening (``sheathing.rect_minus_rects``: a panel the
  opening cuts in two is two panels).

Trimmers and headers are doubled at every size, as builders frame a
stairwell; IRC R502.10 requires it above a 4 ft header span and hangers above
6 ft. The hangers (a tail on its header, a doubled header on its trimmer) are
not listed yet (BACKLOG Notes, FLOOR-HANGERS).

**Ids.** The framing keeps 1.3.0's slots: a layout joist is ``joist/k+1``
wherever it survives. ``trimmer/0`` and ``/1`` are the inner and outer plies
at the opening's near side (along the rims), ``/2`` and ``/3`` at its far
side (an outer ply that is a layout joist is not emitted); ``header/0`` and
``/1`` the inner and outer plies at the near end (along the joists), ``/2``
and ``/3`` at the far end; layout joist ``joist/m``'s tails are
``tail_joist/2m`` (near) and ``tail_joist/2m+1`` (far). The subfloor's
panels keep their ``row/<r>/<c>`` names, a split panel's pieces
``row/<r>/<c>/<k>``.
"""

import dataclasses
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    FeatureRef,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import (
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    FeatureListInput,
    LengthInput,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin import floor as floor_v1
from loft_plugins.builtin import sheathing
from loft_plugins.builtin.building_outline import FLOOR_MANIFEST_V1_3
from loft_plugins.builtin.house import floor_values_v1_4

_DIGITS: Final = 9
_EPS: Final = 1e-9
#: The most picks a floor bears on (an outline wall counts once).
MAX_FLOOR_WALLS: Final = 16


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def _inches(name: str, inputs: ExpandInputs) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _DIGITS)


# --- Manifest ----------------------------------------------------------------------

WALLS_PICK = FeatureListInput(
    kind="features",
    name="walls",
    label="On walls",
    description="The walls the floor bears on (the storey below's): its rims "
    "and end joists stand on their top plates, with no sill plates. Each "
    "stands under the floor, all at one plate height. None: on its "
    "foundation at the base elevation.",
    feature_types=["custom"],
    plugin_ids=["loft.wall"],
    min_items=0,
    max_items=MAX_FLOOR_WALLS,
)

#: The inputs the walls' plate replaces.
_ON_WALLS: Final = frozenset(
    {"elevation_mm", "sill_plate", "sill_profile", "sill_material"}
)


def _well_length(
    name: str, label: str, default_in: float, description: str
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=description,
        default=_mm(default_in),
        minimum=_mm(0.0 if name.endswith("_at_mm") else 12.0),
        maximum=_mm(960.0),
        superseded_by="stairwell",
        superseded_unless="framed",
    )


STAIRWELL_INPUTS: list[PluginInput] = [
    ChoiceInput(
        kind="choice",
        name="stairwell",
        label="Stairwell",
        description="A framed opening for a stair: doubled trimmers and "
        "headers, and tail joists to the rims (IRC R502.10).",
        options=[
            ChoiceOption(value="none", label="None"),
            ChoiceOption(value="framed", label="Framed opening"),
        ],
        default="none",
    ),
    _well_length(
        "well_width_at_mm",
        "Opening from start, along width",
        18.25,
        "The clear opening's near side, from the floor's start corner along "
        "its width (on an outline, from its least X).",
    ),
    _well_length(
        "well_depth_at_mm",
        "Opening from start, along depth",
        36.0,
        "The clear opening's near end, from the floor's start corner along "
        "its depth (on an outline, from its least Y).",
    ),
    _well_length(
        "well_width_mm",
        "Opening along width",
        43.5,
        "Clear, between the framing, along the floor's width.",
    ),
    _well_length(
        "well_depth_mm",
        "Opening along depth",
        120.0,
        "Clear, between the framing, along the floor's depth.",
    ),
]


def _inputs_v1_4() -> list[PluginInput]:
    out: list[PluginInput] = []
    for item in FLOOR_MANIFEST_V1_3.inputs:
        if item.name in _ON_WALLS:
            item = item.model_copy(update={"superseded_by": "walls"})
        out.append(item)
        if item.name == "outline":
            out.append(WALLS_PICK)
    return [*out, *STAIRWELL_INPUTS]


FLOOR_MANIFEST_V1_4 = PluginManifest(
    id="loft.floor",
    version="1.4.0",
    title=FLOOR_MANIFEST_V1_3.title,
    description="A framed platform floor on a foundation or on the walls of "
    "the storey below: sill plates (on a foundation), rim joists, joists "
    "spanning between the walls they bear on, a framed stairwell and a "
    "subfloor, with a cut list (Chief Architect, Revit, Medeek Foundation).",
    inputs=_inputs_v1_4(),
    members=[
        *FLOOR_MANIFEST_V1_3.members,
        PluginMemberRole(
            role="trimmer",
            title="Trimmer",
            description="A stairwell trimmer ply, rim to rim beside the "
            "opening: /0 and /2 the inner plies, /1 and /3 the outer.",
        ),
        PluginMemberRole(
            role="header",
            title="Header",
            description="A stairwell header ply across the opening's end, "
            "between the inner trimmers: /0 and /2 the inner plies.",
        ),
        PluginMemberRole(
            role="tail_joist",
            title="Tail joist",
            description="A layout joist cut by the opening, from a header to "
            "the rim: tail_joist/2m and /2m+1 are joist/m's.",
        ),
    ],
)


# --- The stairwell (pure, inches) --------------------------------------------------


@dataclass(frozen=True)
class Stairwell:
    """The clear opening in the floor's ``(a, b)`` frame: ``a`` along the
    rims (across the joists), ``b`` along the joists."""

    a0: float
    a1: float
    b0: float
    b1: float

    @property
    def rect(self) -> sheathing.Rect:
        return (self.a0, self.a1, self.b0, self.b1)


def _unsupported(message: str, input_name: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=input_name)


def stairwell(inputs: ExpandInputs, floor: floor_v1.FloorSpec) -> Stairwell | None:
    """The typed opening in the floor's frame, or ``None``; refused where its
    doubled trimmers or headers would not fit inside the end joists and rims."""
    if "stairwell" not in inputs.values or inputs.choice("stairwell") != "framed":
        return None
    w0 = _inches("well_width_at_mm", inputs)
    d0 = _inches("well_depth_at_mm", inputs)
    w1 = round(w0 + _inches("well_width_mm", inputs), _DIGITS)
    d1 = round(d0 + _inches("well_depth_mm", inputs), _DIGITS)
    if floor.joists_along == "depth":
        well = Stairwell(w0, w1, d0, d1)
        a_names, b_names = (
            ("well_width_at_mm", "well_width_mm"),
            (
                "well_depth_at_mm",
                "well_depth_mm",
            ),
        )
    else:
        well = Stairwell(d0, d1, w0, w1)
        a_names, b_names = (
            ("well_depth_at_mm", "well_depth_mm"),
            (
                "well_width_at_mm",
                "well_width_mm",
            ),
        )
    t = floor.joist.thickness_in
    la, lb = floor.span_a, floor.span_b
    if well.a0 - 2 * t < t - _EPS:
        raise _unsupported(
            "Stairwell: its doubled trimmer runs into the floor's end joist; "
            f"keep the opening at least {3 * t:g} in from the floor's edge.",
            a_names[0],
        )
    if well.a1 + 2 * t > la - t + _EPS:
        raise _unsupported(
            "Stairwell: its doubled trimmer runs into the floor's far end "
            f"joist; keep the opening at least {3 * t:g} in from the edge.",
            a_names[1],
        )
    if well.b0 - 2 * t < t - _EPS:
        raise _unsupported(
            "Stairwell: its doubled header runs into the rim; keep the "
            f"opening at least {3 * t:g} in from the floor's edge.",
            b_names[0],
        )
    if well.b1 + 2 * t > lb - t + _EPS:
        raise _unsupported(
            "Stairwell: its doubled header runs into the far rim; keep the "
            f"opening at least {3 * t:g} in from the edge.",
            b_names[1],
        )
    return well


def well_pieces(floor: floor_v1.FloorSpec, well: Stairwell) -> list[floor_v1.Piece]:
    """The floor's members with the stairwell framed (module docstring), in
    the cut list's order: joists, tail joists, trimmers, headers, rims, sills."""
    pieces = floor_v1.floor_pieces(floor)
    t = floor.joist.thickness_in
    lb = floor.span_b
    near_outer, far_outer = (
        (well.a0 - 2 * t, well.a0 - t),
        (well.a1 + t, well.a1 + 2 * t),
    )

    def at(piece: floor_v1.Piece, a: tuple[float, float]) -> bool:
        return abs(piece.a0 - a[0]) <= _EPS and abs(piece.a1 - a[1]) <= _EPS

    joists: list[floor_v1.Piece] = []
    cut: list[floor_v1.Piece] = []
    supplied = {"near": False, "far": False}
    for piece in pieces:
        if piece.role != "joist":
            continue
        layout = piece.index >= 2
        if layout and piece.a0 >= well.a0 - _EPS and piece.a1 <= well.a1 + _EPS:
            cut.append(piece)
        elif layout and at(piece, near_outer):
            supplied["near"] = True
            joists.append(piece)
        elif layout and at(piece, far_outer):
            supplied["far"] = True
            joists.append(piece)
        elif (
            layout
            and piece.a1 > near_outer[0] + _EPS
            and piece.a0 < far_outer[1] - _EPS
        ):
            continue  # it would collide with a trimmer ply: the trimmer bears
        else:
            joists.append(piece)
    first = pieces[0]
    joist, mat, z0, z1 = first.profile, first.material, first.z0, first.z1
    b_in, b_out = t, lb - t
    head_near, head_far = well.b0 - 2 * t, well.b1 + 2 * t
    tails: list[floor_v1.Piece] = []
    for piece in cut:
        if head_near - b_in > _EPS:
            tails.append(
                dataclasses.replace(
                    piece,
                    role="tail_joist",
                    index=2 * piece.index,
                    b0=b_in,
                    b1=head_near,
                )
            )
        if b_out - head_far > _EPS:
            tails.append(
                dataclasses.replace(
                    piece,
                    role="tail_joist",
                    index=2 * piece.index + 1,
                    b0=head_far,
                    b1=b_out,
                )
            )
    trimmers = [
        floor_v1.Piece(
            "trimmer", 0, joist, mat, well.a0 - t, well.a0, b_in, b_out, z0, z1
        )
    ]
    if not supplied["near"]:
        trimmers.append(
            floor_v1.Piece("trimmer", 1, joist, mat, *near_outer, b_in, b_out, z0, z1)
        )
    trimmers.append(
        floor_v1.Piece(
            "trimmer", 2, joist, mat, well.a1, well.a1 + t, b_in, b_out, z0, z1
        )
    )
    if not supplied["far"]:
        trimmers.append(
            floor_v1.Piece("trimmer", 3, joist, mat, *far_outer, b_in, b_out, z0, z1)
        )
    a0, a1 = well.a0, well.a1
    headers = [
        floor_v1.Piece("header", 0, joist, mat, a0, a1, well.b0 - t, well.b0, z0, z1),
        floor_v1.Piece("header", 1, joist, mat, a0, a1, head_near, well.b0 - t, z0, z1),
        floor_v1.Piece("header", 2, joist, mat, a0, a1, well.b1, well.b1 + t, z0, z1),
        floor_v1.Piece("header", 3, joist, mat, a0, a1, well.b1 + t, head_far, z0, z1),
    ]
    rest = [p for p in pieces if p.role != "joist"]
    return [*joists, *tails, *trimmers, *headers, *rest]


# --- Emission ----------------------------------------------------------------------


def _subfloor(
    inputs: ExpandInputs, floor: floor_v1.FloorSpec, well: Stairwell
) -> Iterator[Member]:
    """1.1.0's subfloor panels with the opening cut out of them."""
    good = sheathing.sheet_good(inputs, "subfloor")
    if good is None:
        return
    frame = floor_v1.FloorFrame.of(floor)
    z = frame.base + floor.framing_top
    plane: DatumPlaneRef | FeatureRef
    if round(z, _DIGITS) + 0.0 == 0.0:
        plane = DatumPlaneRef(kind="datum_plane", plane="XY")
    else:
        yield Member(
            "subfloor_level",
            0,
            DatumFeature(
                type="datum",
                version=1,
                params=DatumOffsetParams(base="XY", offset_mm=_mm(z)),
            ),
            name="top",
        )
        plane = inputs.ref("subfloor_level", 0, "top")
    index = 0
    for name, rect in sheathing.placed_subfloor_panels(floor):
        regions = sheathing.rect_minus_rects(rect, [well.rect])
        for k, region in enumerate(regions):
            loops = [
                [
                    Point2D(x=_mm(x), y=_mm(y))
                    for x, y in map(lambda p: frame.plan(*p), loop)
                ]
                for loop in (region.outer, *region.holes)
            ]
            piece = name if len(regions) == 1 else f"{name}/{k}"
            yield from sheathing.panel_members(
                inputs,
                ("subfloor_section", "subfloor"),
                index,
                plane,
                loops,
                good,
                False,
                piece,
            )
            index += 1


def expand_floor_v1_4(inputs: ExpandInputs) -> Iterator[Member]:
    """1.3.0's floor, on the picked walls' plate when walls are picked, its
    stairwell framed when one is typed."""
    values = floor_values_v1_4(inputs)
    floor = floor_v1.FloorSpec.from_inputs(values)
    well = stairwell(values, floor)
    if well is None:
        yield from sheathing.expand_floor_v1_1(values)
        return
    frame = floor_v1.FloorFrame.of(floor)
    yield from floor_v1.emit(values, frame, well_pieces(floor, well))
    yield from _subfloor(values, floor, well)


FLOOR_V1_4 = Plugin(FLOOR_MANIFEST_V1_4, expand_floor_v1_4)
