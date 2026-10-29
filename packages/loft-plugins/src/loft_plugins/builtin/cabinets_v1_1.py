"""``loft.cabinets`` 1.1.0: a run on a wall's or a partition's FINISHED face
(CASEWORK-B10, RESEARCH §23).

1.0.0 (:mod:`~loft_plugins.builtin.cabinets`) puts a run's backs on a wall's
inside FRAMING, its Back gap standing in for the gypsum, and measures its
Distance from the framing's end, so a run against a corner whose other wall
is finished cuts into that wall's board. Mozaik places a run on the room's
finished walls; 1.1.0 does the same, and every box and panel is 1.0.0's:

* **Wall** may be a ``loft.wall`` (its inside face) or a
  ``loft.interior_wall``, its Wall line then the partition and **Face** the
  side of it, left or right looking along it from its start (the end its
  line was drawn from, as its gypsum's ``left`` and ``right``);
* the backs sit on that face's gypsum when it has one (a 1.4.0 wall's
  Inside gypsum, a partition's Gypsum), on its framing otherwise, plus the
  Back gap (0: on it);
* **Distance** runs from the end of the finished face: the board's end at
  a corner (it stops at the board of the wall it meets), else where the
  framing's face meets that wall (a through wall's a wall's depth in);
  the run must fit between the finished ends;
* a run that would pass a partition meeting its face (the partition with
  its boards) is refused, naming it.

1.0.0 expands byte for byte as it did: it keeps its own placement.
"""

from collections.abc import Iterator

from loft_wire.features import CustomFeature, FeatureRef
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    ChoiceInput,
    ChoiceOption,
    FeatureReferenceInput,
    PluginInput,
    SegmentsInput,
)

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin import cabinets as v1
from loft_plugins.builtin.interior_wall import (
    INTERIOR_WALL,
    FinishedFace,
    partition_faces_of,
    wall_faces_of,
)
from loft_plugins.builtin.wall import WallFrame

_TOL = 1e-6
_DIGITS = 9


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0


def _inches(inputs: ExpandInputs, name: str) -> float:
    return _r(inputs.number(name) / MM_PER_INCH)


def _input(item: PluginInput) -> PluginInput:
    """1.0.0's input as 1.1.0 reads it."""
    if isinstance(item, FeatureReferenceInput) and item.name == "wall":
        return item.model_copy(
            update={
                "description": "The wall the run's backs sit on, at its inside "
                "face, or the partitions (an Interior wall); empty for a typed "
                "position.",
                "plugin_ids": ["loft.wall", INTERIOR_WALL],
            }
        )
    if isinstance(item, SegmentsInput) and item.name == "wall_segment":
        return item.model_copy(
            update={
                "description": "When the wall is an outline wall: the line the "
                "run is on; when it is an Interior wall, the partition (its line)."
            }
        )
    if item.name == "offset_mm":
        return item.model_copy(
            update={
                "description": "From the end of the finished face (its gypsum's "
                "end at a corner, else the face of the wall it meets), along "
                "it, to the run's first box."
            }
        )
    if item.name == "gap_mm":
        return item.model_copy(
            update={
                "description": "From the face's gypsum (its framing when it has "
                "none) to the carcass backs: 0 to sit on it."
            }
        )
    return item


FACE = ChoiceInput(
    kind="choice",
    name="face",
    label="Face",
    description="On a partition: the face the run is on, looking along the "
    "partition from its start. A wall's run is on its inside face.",
    options=[
        ChoiceOption(value="left", label="Left"),
        ChoiceOption(value="right", label="Right"),
    ],
    default="left",
)


def _inputs() -> list[PluginInput]:
    out: list[PluginInput] = []
    for item in v1.INPUTS:
        out.append(_input(item))
        if item.name == "wall_segment":
            out.append(FACE)
    return out


MANIFEST_V1_1 = v1.MANIFEST.model_copy(
    update={
        "version": "1.1.0",
        "description": v1.MANIFEST.description
        + " Its backs sit on the finished face of a wall or a partition, its "
        "distance measured from that face's end.",
        "inputs": _inputs(),
    }
)


def _face(inputs: ExpandInputs, ref: FeatureRef) -> FinishedFace:
    host = inputs.resolve(ref)
    if not isinstance(host, CustomFeature) or host.params.plugin_id not in (
        "loft.wall",
        INTERIOR_WALL,
    ):
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Wall: pick an earlier Wall or Interior wall.",
            input="wall",
        )
    picked = inputs.segments("wall_segment")
    if host.params.plugin_id == INTERIOR_WALL:
        sides = partition_faces_of(
            ref.feature_id, host, inputs.earlier, inputs.parameters
        )
        if len(picked) != 1 or picked[0] not in sides:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                "Wall line: pick the partition the run is on.",
                input="wall_segment",
            )
        left, right = sides[picked[0]]
        return left if inputs.choice("face") == "left" else right
    faces = wall_faces_of(ref.feature_id, host, inputs.earlier, inputs.parameters)
    if None in faces:
        if picked:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                "Wall line: the wall is one wall, not an outline; leave it empty.",
                input="wall_segment",
            )
        return faces[None]
    if len(picked) != 1 or picked[0] not in faces:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Wall line: pick the line of the outline the run is on.",
            input="wall_segment",
        )
    return faces[picked[0]]


def finished_face(inputs: ExpandInputs, ref: FeatureRef) -> FinishedFace:
    """The finished face a run on *ref* stands on (the 1.0.0 -> 1.1.0 update
    map reads it). Raises :class:`PluginError` as the expansion would."""
    return _face(inputs, ref)


def placement_v1_1(inputs: ExpandInputs, run_length: float) -> v1.Placement:
    """The run's frame on the picked face (module docstring), or 1.0.0's
    typed position."""
    ref = inputs.optional_feature("wall")
    if ref is None:
        return v1.placement(inputs, run_length)
    face = _face(inputs, ref)
    frame = WallFrame.of(face.spec)
    offset = _inches(inputs, "offset_mm")
    length = _r(face.last - face.first)
    if offset + run_length > length + 1e-9:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"Distance: the {run_length:g} in run from {offset:g} in does not "
            f"fit the {length:g} in finished face.",
            input="offset_mm",
        )
    from_end = inputs.choice("measure_from") == "end"
    sign = -1.0 if from_end else 1.0
    u0 = face.last - offset if from_end else face.first + offset
    a, b = sorted((u0, u0 + sign * run_length))
    for name, m0, m1 in face.meeting:
        if min(b, m1) - max(a, m0) > _TOL:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                f"Distance: the run would pass {name}, which meets this face "
                f"{m0 - face.first:g} to {m1 - face.first:g} in from its start; "
                "shorten or move the run.",
                input="offset_mm",
            )
    gap = _inches(inputs, "gap_mm")
    x, y = frame.plan(u0, face.v + face.out * (face.finish + gap))
    along = (sign * frame.along[0] + 0.0, sign * frame.along[1] + 0.0)
    out = (face.out * frame.across[0] + 0.0, face.out * frame.across[1] + 0.0)
    return v1.Placement(_r(x), _r(y), along, out, frame.base)


def expand_v1_1(inputs: ExpandInputs) -> Iterator[Member]:
    return v1.expand_placed(inputs, placement_v1_1)


CABINETS_V1_1 = Plugin(MANIFEST_V1_1, expand_v1_1)
