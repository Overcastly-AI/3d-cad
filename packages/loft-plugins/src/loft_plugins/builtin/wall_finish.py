"""Wall 1.5.0: an Exterior finish of siding and trim over the sheathing
(SIDING-TRIM, RESEARCH §23).

Chief Architect's wall types carry a siding layer outside the sheathing, and
its Materials List counts the siding by area net of the openings, with the
corner boards and the exterior casing as lines of their own. ``loft.wall``
1.5.0 is 1.4.0 member for member, then, when **Exterior finish** is not
None (the default, as Chief's wall type is picked: siding is a material
the user chooses; Lap, fibre cement 8-1/4 in at 7 in exposure; Vinyl,
double 4 in, by the square; Cedar bevel 1/2 x 8), each wall's:

* **Siding**: one body per connected region of the wall's face, drawn at
  the product's thickness on the sheathing's outer face (a wall with no
  exterior sheathing takes no finish and warns ``wall_finish_no_sheathing``),
  from the FOUNDATION TOP to the top of the
  top plate: on a floor, the floor's underside (its sills' bearing), so the
  siding covers the rim too; on a slab or on no floor, the wall's own base.
  Every cased opening and corner board is cut out of it, and it is bought
  by that measured net area with the wall's **Siding waste** allowance
  (:mod:`loft_wire.siding`).
* **Corner boards**: a 5/4x4 on each face of every outside corner of an
  outline, foundation top to plate top. The fitted wall's laps the through
  wall's edge, as its sheathing laps the through wall's end (so one face
  shows 3-1/2 in and the other 4-1/2 in, the common butt corner of two
  identical boards).
* **Casing**: 5/4x4 picture-frame casing round every window and door UNIT
  (its frame, as ``loft.window``/``loft.door`` draw it, drawn or not), its
  inside edge on the unit's outside edge: a window's four pieces mitred at
  the corners, a door's head mitred onto two legs that stand on the wall's
  base.

The trim stands 1 in proud of the sheathing and the siding butts it, so
nothing overlaps: the siding is cut out round the casing's outer edge and
stops at the corner boards' inner edges. At an inside corner of an outline
(no board: inside-corner trim is a later rung) the through wall's siding
runs to the other wall's sheathing and the fitted wall's starts at the
through wall's siding face. A typed (line) wall's face is sided from end to
end, its corners left open (its corner boards are a later rung). An eave
wall's siding and corner boards run to the plate's top under the rafter
tails, which the roof notches out of them as it does the sheathing
(``roof_sheathing.notches``). A gable's triangle is the roof's: ``loft.roof``
1.8.0 carries the end walls' finish up it, as 1.7.0 carries their
sheathing (``roof_gable``).

Refused, naming the opening: a casing that would meet a corner board, run
past the siding into the wall an inside corner meets, reach below the
siding, or meet another opening's casing.
"""

import dataclasses
import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from loft_wire.features import (
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import MM_PER_INCH, lumber_profile
from loft_wire.plugin_warning import WALL_FINISH_NO_SHEATHING
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    ChoiceInput,
    ChoiceOption,
    CountInput,
    MemberMetadata,
    PluginInput,
    PluginMemberRole,
)
from loft_wire.siding import (
    DEFAULT_SIDING_WASTE_PERCENT,
    MAX_SIDING_WASTE_PERCENT,
    SIDING_PRODUCTS,
    SIDING_PRODUCTS_BY_KEY,
    TRIM_PROFILE,
    TRIM_THICKNESS_IN,
    TRIM_WIDTH_IN,
    SidingProduct,
    SidingTakeoff,
)

from loft_plugins.api import ExpandInputs, Hosted, Member, Plugin, PluginError
from loft_plugins.builtin import house, interior_wall, sheathing
from loft_plugins.builtin import wall as wall_v1
from loft_plugins.builtin.openings import unit_bodies

_DIGITS = 9
#: Two faces closer than this meet (in): the inputs' rounding.
_TOL = 1e-6
FINISH_NONE = "none"
#: The release of ``loft.wall`` with an Exterior finish.
WALL_FINISH_VERSION = (1, 5, 0)


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


# --- Inputs and roles -----------------------------------------------------------------

FINISH_INPUTS: list[PluginInput] = [
    ChoiceInput(
        kind="choice",
        name="exterior_finish",
        label="Exterior finish",
        description="Siding over the exterior sheathing (a warning without it) "
        "from "
        "the foundation top to the top plate, with 5/4x4 corner boards on the "
        "outside corners and "
        "picture-frame casing round each window and door, bought by the "
        "area net of the cased openings (Chief Architect's siding layer).",
        options=[
            ChoiceOption(value=FINISH_NONE, label="None"),
            *(ChoiceOption(value=p.key, label=p.label) for p in SIDING_PRODUCTS),
        ],
        default=FINISH_NONE,
    ),
    CountInput(
        kind="count",
        name="siding_waste_percent",
        label="Siding waste (%)",
        description="Ordered over the siding's net area for cuts and laps, "
        "then rounded up to whole boards or squares.",
        default=DEFAULT_SIDING_WASTE_PERCENT,
        minimum=0,
        maximum=MAX_SIDING_WASTE_PERCENT,
    ),
]

FINISH_ROLES = [
    PluginMemberRole(role="siding_plane", title="Plane"),
    PluginMemberRole(role="siding_section", title="Section"),
    PluginMemberRole(
        role="siding",
        title="Siding",
        description="The siding on one region of a wall's face, the cased "
        "openings and corner boards cut out.",
    ),
    PluginMemberRole(
        role="corner_board",
        title="Corner board",
        description="A 5/4x4 corner board on one face of an outside corner.",
    ),
    PluginMemberRole(
        role="casing",
        title="Casing",
        description="One piece of an opening's 5/4x4 picture-frame casing.",
    ),
]


def finish_product(inputs: ExpandInputs) -> SidingProduct | None:
    """The wall's Exterior finish, or ``None``: None, a release without one,
    or a wall with no exterior sheathing (the finish goes over it;
    :func:`finish_note` warns)."""
    if "exterior_finish" not in inputs.values:
        return None
    if sheathing.sheet_good(inputs, "sheathing") is None:
        return None
    value = inputs.choice("exterior_finish")
    if value == FINISH_NONE:
        return None
    product = SIDING_PRODUCTS_BY_KEY.get(value)
    if product is None:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"Exterior finish: {value!r} is not a siding product.",
            input="exterior_finish",
        )
    return product


def finish_note(inputs: ExpandInputs) -> str | None:
    """The stored wall's ``wall_finish_no_sheathing`` message, or None: it
    asks for an Exterior finish but has no exterior sheathing, so
    :func:`finish_product` gives it none and it builds bare. Pure."""
    if "exterior_finish" not in inputs.values:
        return None
    value = inputs.choice("exterior_finish")
    if value == FINISH_NONE or sheathing.sheet_good(inputs, "sheathing") is not None:
        return None
    product = SIDING_PRODUCTS_BY_KEY.get(value)
    name = product.label if product is not None else value
    return (
        f"Exterior finish is {name}, but this wall has no sheathing: no siding "
        "without sheathing; turn sheathing on, or set Exterior finish to None."
    )


def finish_notes(inputs: ExpandInputs) -> list[tuple[str, str]]:
    """The stored wall's warnings, as (code, message), as ``stair_notes``."""
    note = finish_note(inputs)
    return [] if note is None else [(WALL_FINISH_NO_SHEATHING, note)]


def waste_percent(inputs: ExpandInputs) -> int:
    if "siding_waste_percent" not in inputs.values:
        return DEFAULT_SIDING_WASTE_PERCENT
    return inputs.count("siding_waste_percent")


# --- The face, in the wall's (u, z) (pure, inches) ------------------------------------

#: A rectangle in the wall's frame: u0, u1, z0, z1.
Rect = tuple[float, float, float, float]
Points = list[tuple[float, float]]


@dataclass(frozen=True)
class Cased:
    """One opening's unit outline in its wall's ``(u, z)`` and its casing."""

    kind: Literal["door", "window"]
    name: str
    feature_id: uuid.UUID
    unit: Rect

    @property
    def outer(self) -> Rect:
        """The casing's outer edge: the unit plus the trim's face each way,
        a door's legs standing on the wall's base."""
        u0, u1, z0, z1 = self.unit
        w = TRIM_WIDTH_IN
        return (
            _r(u0 - w),
            _r(u1 + w),
            z0 if self.kind == "door" else _r(z0 - w),
            _r(z1 + w),
        )

    def pieces(self) -> list[tuple[str, Points]]:
        """The casing's pieces as ``(side, polygon)``: the head, then a
        window's sill, then the legs from the wall's start (left) to its end
        (right); mitred where two meet (each piece's long point is the
        casing's outer edge)."""
        u0, u1, z0, z1 = self.unit
        a0, a1, b0, b1 = self.outer
        out: list[tuple[str, Points]] = [
            ("head", [(a0, b1), (u0, z1), (u1, z1), (a1, b1)]),
        ]
        if self.kind == "window":
            out.append(("sill", [(a0, b0), (a1, b0), (u1, z0), (u0, z0)]))
            out.append(("left", [(a0, b0), (u0, z0), (u0, z1), (a0, b1)]))
            out.append(("right", [(u1, z0), (a1, b0), (a1, b1), (u1, z1)]))
        else:
            out.append(("left", [(a0, z0), (u0, z0), (u0, z1), (a0, b1)]))
            out.append(("right", [(u1, z0), (a1, z0), (a1, b1), (u1, z1)]))
        return out


@dataclass(frozen=True)
class Face:
    """One wall's exterior finish laid out in its ``(u, z)``: the siding's
    extent along the wall, its bottom and top, its corner boards and its
    cased openings."""

    first: float
    last: float
    bottom: float
    top: float
    corners: tuple[tuple[str, float, float], ...]
    cased: tuple[Cased, ...]

    def regions(self) -> list[sheathing.Region]:
        """The siding: the face less every cased opening, as connected
        regions, ordered from the bottom, then along the wall."""
        found = sheathing.rect_minus_rects(
            (self.first, self.last, self.bottom, self.top),
            [c.outer for c in self.cased],
        )
        found.sort(
            key=lambda r: (min(z for _, z in r.outer), min(u for u, _ in r.outer))
        )
        return found


def _refuse(name: str, why: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_INVALID, f"{name}: {why}", input="offset_mm")


def _check(face: Face) -> None:
    """Each casing clear of the corner boards, within the siding's run (an
    inside corner's other wall beyond it), above the siding's bottom, and
    clear of the other casings (module docstring)."""
    boards = [(u0, u1) for _, u0, u1 in face.corners]
    ordered = sorted(face.cased, key=lambda c: (c.outer[0], c.name))
    for c in ordered:
        a0, a1, b0, _ = c.outer
        for u0, u1 in boards:
            if a0 < u1 - _TOL and a1 > u0 + _TOL:
                raise _refuse(
                    c.name,
                    f"its casing ({a0:g} to {a1:g} in along the wall) meets the "
                    f"corner board ({u0:g} to {u1:g} in); move it along the wall.",
                )
        if a0 < face.first - _TOL or a1 > face.last + _TOL:
            raise _refuse(
                c.name,
                f"its casing ({a0:g} to {a1:g} in along the wall) runs past the "
                f"siding ({face.first:g} to {face.last:g} in) into the wall it "
                "meets; move it along the wall.",
            )
        if b0 < face.bottom - _TOL:
            raise _refuse(
                c.name,
                f"its casing reaches {b0:g} in, below the siding's bottom "
                f"({face.bottom:g} in); raise the window.",
            )
    for k in range(1, len(ordered)):
        before, now = ordered[k - 1].outer, ordered[k].outer
        if now[0] < before[1] - _TOL:
            raise _refuse(
                ordered[k].name,
                f"its casing overlaps {ordered[k - 1].name}'s; move them "
                f"{before[1] - now[0]:g} in further apart.",
            )


def _cased(hosted: Hosted, spec: wall_v1.WallSpec, opening: wall_v1.Opening) -> Cased:
    """*opening*'s unit frame (``loft.window``/``loft.door``'s, drawn or not)."""
    size = wall_v1.unit_size(opening.kind, hosted.inputs)
    frame = unit_bodies(opening.kind, spec, opening, size)[0]
    u0, u1, z0, z1 = frame.outer
    return Cased(opening.kind, opening.name, opening.feature_id, (u0, u1, z0, z1))


def outline_cased(
    inputs: ExpandInputs, walls: Sequence[house.OutlineWall]
) -> dict[str, list[Cased]]:
    """The hosted doors and windows' units, by the line of the wall they sit
    in (as ``building_outline._openings`` reads them)."""
    specs = {wall.line_id: wall.spec for wall in walls}
    out: dict[str, list[Cased]] = {line: [] for line in specs}
    for hosted in inputs.hosted:
        if hosted.plugin_id not in wall_v1.OPENING_PLUGINS:
            continue
        picked = hosted.inputs.segments("wall_segment")
        if len(picked) != 1 or picked[0] not in out:
            continue  # the wall's framing refuses it first
        opening = wall_v1.Opening.from_hosted(hosted, specs[picked[0]])
        if opening is not None:
            out[picked[0]].append(_cased(hosted, specs[picked[0]], opening))
    return out


def line_cased(inputs: ExpandInputs, spec: wall_v1.WallSpec) -> list[Cased]:
    """A line wall's hosted doors and windows' units."""
    out: list[Cased] = []
    for hosted in inputs.hosted:
        opening = wall_v1.Opening.from_hosted(hosted, spec)
        if opening is not None:
            out.append(_cased(hosted, spec, opening))
    return out


def foundation_top(inputs: ExpandInputs, spec: wall_v1.WallSpec) -> float:
    """Where the siding starts, in the wall's frame (in): the picked floor's
    underside, else the wall's base (a slab's top, or none)."""
    if "floor" not in inputs.values:
        return 0.0
    ref = inputs.optional_feature("floor")
    if ref is None or house.picked_slab(inputs) is not None:
        return 0.0
    floor = house.floor_of(ref, inputs)
    return _r(floor.spec.elevation - spec.elevation)


def outline_face(
    wall: house.OutlineWall,
    sheathed: float,
    product: SidingProduct,
    bottom: float,
    cased: Sequence[Cased],
) -> Face:
    """One outline wall's finish (module docstring): *sheathed* is the
    sheathing's thickness (0 unsheathed)."""
    spec = wall.spec
    t, s, ts = spec.thickness, sheathed, product.thickness_in
    w, d = TRIM_WIDTH_IN, TRIM_THICKNESS_IN
    length = spec.length
    corners: list[tuple[str, float, float]] = []
    if wall.convex_start:
        if wall.through:
            start = -s
            corners.append(("start", start, start + w))
            first = start + w
        else:
            start = -(t + s) - d  # lapping the through wall's board
            corners.append(("start", start, start + w))
            first = start + w
    else:
        first = t + s if wall.through else s + ts
    if wall.convex_end:
        end = length + s if wall.through else length + t + s + d
        corners.append(("end", end - w, end))
        last = end - w
    else:
        last = length - t - s if wall.through else length - s - ts
    return Face(
        _r(first),
        _r(last),
        bottom,
        spec.height,
        tuple((name, _r(u0), _r(u1)) for name, u0, u1 in corners),
        tuple(cased),
    )


def line_face(spec: wall_v1.WallSpec, bottom: float, cased: Sequence[Cased]) -> Face:
    """A line wall's finish: its face end to end, no corner boards."""
    return Face(0.0, spec.length, bottom, spec.height, (), tuple(cased))


# --- Emission -------------------------------------------------------------------------


def outer_plane(spec: wall_v1.WallSpec, v: float) -> sheathing.FacePlane:
    """The plane *v* in from the framing's exterior face (negative: outside
    it), parallel to it: the exterior face's plane slid along its normal."""
    plane = sheathing.face_plane(spec)
    px, py = plane.frame.plan(0.0, v)
    if plane.axis == "x":
        offset = -_mm(py) + 0.0
    elif plane.axis == "y":
        offset = _mm(px) + 0.0
    else:
        # The plane's y_dir is (n1, -n0), so its normal is (-y_dir[1], y_dir[0]).
        normal = (-plane.y_dir[1], plane.y_dir[0])
        offset = _mm(px) * normal[0] + _mm(py) * normal[1] + 0.0
    return dataclasses.replace(plane, offset_mm=offset)


def _extrude(
    inputs: ExpandInputs,
    role: str,
    index: int,
    section: int,
    name: str,
    plane: sheathing.FacePlane,
    ref: DatumPlaneRef | FeatureRef,
    loops: Sequence[Points],
    depth_in: float,
    meta: MemberMetadata,
) -> Iterator[Member]:
    yield Member(
        "siding_section",
        section,
        SketchFeature(
            type="sketch",
            version=1,
            params=SketchParamsV1(
                plane=ref,
                entities=list(
                    sheathing.loops_entities(
                        [[plane.sketch_point(u, z) for u, z in loop] for loop in loops]
                    )
                ),
                constraints=[],
            ),
        ),
        name=name,
    )
    yield Member(
        role,
        index,
        ExtrudeFeature(
            type="extrude",
            version=1,
            params=ExtrudeParamsV1(
                profile=inputs.ref("siding_section", section, name),
                distance_mm=_mm(depth_in),
                operation="add",
                direction="reverse" if plane.reverse else "normal",
                merge=False,
            ),
        ),
        meta,
        name=name,
    )


def face_members(
    inputs: ExpandInputs,
    spec: wall_v1.WallSpec,
    sheathed: float,
    product: SidingProduct,
    waste: int,
    face: Face,
) -> Iterator[Member]:
    """One wall's finish members under *inputs*' name prefix, each role
    numbered from 0 (the caller renumbers them across the walls): the plane
    on the sheathing's face, the siding, the corner boards, the casing."""
    _check(face)
    plane = outer_plane(spec, -sheathed)
    datums, ref = plane.members(inputs, "siding/", 0, "siding_plane")
    yield from datums
    counts: Counter[str] = Counter()

    def emit(
        role: str,
        name: str,
        loops: Sequence[Points],
        depth: float,
        meta: MemberMetadata,
    ) -> Iterator[Member]:
        section = counts["siding_section"]
        index = counts[role]
        counts["siding_section"] += 1
        counts[role] += 1
        yield from _extrude(
            inputs, role, index, section, name, plane, ref, loops, depth, meta
        )

    siding = MemberMetadata(
        profile=product.name,
        material=product.material,
        siding=SidingTakeoff(product=product.key, waste_percent=waste),
    )
    for k, region in enumerate(face.regions()):
        yield from emit(
            "siding",
            f"siding/{k}",
            [region.outer, *region.holes],
            product.thickness_in,
            siding,
        )
    trim = MemberMetadata(
        profile=lumber_profile(TRIM_PROFILE).name, material=product.trim_material
    )
    for end, u0, u1 in face.corners:
        box = [(u0, face.bottom), (u1, face.bottom), (u1, face.top), (u0, face.top)]
        yield from emit("corner_board", f"corner/{end}", [box], TRIM_THICKNESS_IN, trim)
    for c in sorted(face.cased, key=lambda c: (c.unit[0], c.name)):
        for side, points in c.pieces():
            yield from emit(
                "casing",
                f"casing/{c.feature_id}/{side}",
                [points],
                TRIM_THICKNESS_IN,
                trim,
            )


def _renamed(
    members: Iterator[Member], prefix: str, counts: Counter[str]
) -> Iterator[Member]:
    """*members* (emitted under the name prefix *prefix*) named under it and
    numbered on across the walls, as the outline walls' own are."""
    for member in members:
        assert member.name is not None
        yield dataclasses.replace(
            member, index=counts[member.role], name=f"{prefix}/{member.name}"
        )
        counts[member.role] += 1


def _sheathed(inputs: ExpandInputs) -> float:
    good = sheathing.sheet_good(inputs, "sheathing")
    return 0.0 if good is None else good.thickness_in


def exterior_finish(inputs: ExpandInputs) -> Iterator[Member]:
    """Every wall's exterior finish (module docstring), after 1.4.0's
    members: an outline's walls in its order, each under its line, the
    roles numbered on across them; a line wall's on its own."""
    product = finish_product(inputs)
    if product is None:
        return
    waste = waste_percent(inputs)
    s = _sheathed(inputs)
    outline = house.wall_outline(inputs)
    if outline is None:
        values = house.wall_values(inputs)
        spec = wall_v1.WallSpec.from_inputs(values)
        face = line_face(spec, foundation_top(inputs, spec), line_cased(inputs, spec))
        yield from face_members(inputs, spec, s, product, waste, face)
        return
    walls = house.outline_walls(inputs, outline)
    cased = outline_cased(inputs, walls)
    counts: Counter[str] = Counter()
    for wall in walls:
        sub = dataclasses.replace(inputs, name_prefix=wall.line_id)
        bottom = foundation_top(inputs, wall.spec)
        face = outline_face(wall, s, product, bottom, cased[wall.line_id])
        members = face_members(sub, wall.spec, s, product, waste, face)
        yield from _renamed(members, wall.line_id, counts)


# --- loft.wall 1.5.0 ----------------------------------------------------------------


def _inputs_v1_5() -> list[PluginInput]:
    return [*interior_wall.WALL_MANIFEST_V1_4.inputs, *FINISH_INPUTS]


WALL_MANIFEST_V1_5 = interior_wall.WALL_MANIFEST_V1_4.model_copy(
    update={
        "version": "1.5.0",
        "description": "Framed stud walls on a line, or one per line of an "
        "outline sketch joined at the corners, on a floor or slab if picked: "
        "plates, studs, openings, exterior sheathing and siding with corner "
        "boards and casing, with a cut list (Chief Architect, Revit, Medeek "
        "Wall). They frame the backing of the partitions that meet them and "
        "may be finished with gypsum inside.",
        "inputs": _inputs_v1_5(),
        "members": [*interior_wall.WALL_MANIFEST_V1_4.members, *FINISH_ROLES],
    }
)


def expand_wall_v1_5(inputs: ExpandInputs) -> Iterator[Member]:
    """1.4.0's members, then the exterior finish (module docstring)."""
    yield from interior_wall.expand_wall_v1_4(inputs)
    yield from exterior_finish(inputs)


WALL_V1_5 = Plugin(WALL_MANIFEST_V1_5, expand_wall_v1_5)

__all__ = [
    "FINISH_INPUTS",
    "FINISH_NONE",
    "FINISH_ROLES",
    "WALL_FINISH_VERSION",
    "WALL_V1_5",
    "Cased",
    "Face",
    "exterior_finish",
    "finish_note",
    "finish_notes",
    "finish_product",
    "line_face",
    "outer_plane",
    "outline_face",
    "waste_percent",
]
