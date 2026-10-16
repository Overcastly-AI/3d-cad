"""Twisted prism: the deprecated extrude twist, as a plugin (RESEARCH §23).

The extrude twist is read-only legacy (``loft_wire.legacy_twist``): Fusion
360, SolidWorks and Onshape twist a Sweep along a path, never an extrude. This
plugin gives the twisted prism back as one tool and one tree node, expanding
to exactly the base features a user would build by hand:

1. ``axis_plane/0`` (only when the twist axis is off the origin plane): an
   offset datum that contains the twist axis;
2. ``path/0``: a sketch holding one line, from the profile along its normal
   (or against it) for the distance, through the twist axis;
3. ``sweep/0``: a Sweep of the profile along that path with the twist.

A Sweep with twist along a straight path perpendicular to the profile builds
through the extrude twist's own kernel call, so the twisted prism and a stored
twisted extrude with the same numbers are the same solid
(``services/geometry/goldens/plugin-twisted-prism-*``).

v1 places the path exactly, with no kernel, when the profile's sketch sits on
an origin plane or a chain of offset planes (every frame axis-aligned). A
profile on a face, a midplane or an angled plane is ``plugin_input_unsupported``.
"""

from typing import Literal

from loft_wire.features import (
    MAX_TWIST_ANGLE_DEG,
    DatumFeature,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumPlaneRef,
    FeatureRef,
    GeomRef,
    SketchFeature,
    SketchParamsV1,
    SweepFeature,
    SweepParamsV1,
)
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    AngleInput,
    ChoiceInput,
    ChoiceOption,
    LengthInput,
    PluginManifest,
    PluginMemberRole,
    ProfileInput,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError

Vec = tuple[float, float, float]
PlaneName = Literal["XY", "XZ", "YZ"]
#: A plane frame: origin, x_dir, y_dir, z_dir (build123d's ``Plane`` fields).
Frame = tuple[Vec, Vec, Vec, Vec]

#: The origin datums exactly as build123d defines them (``Plane.XY`` ...).
ORIGIN_FRAMES: dict[PlaneName, Frame] = {
    "XY": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "XZ": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
    "YZ": ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
}
#: The order a path plane is chosen in: the first whose normal is
#: perpendicular to the profile's (an XY profile's path is drawn on XZ).
PATH_PLANES: tuple[PlaneName, ...] = ("XZ", "YZ", "XY")
#: How many offset datums a profile plane may chain through.
MAX_PLANE_CHAIN = 64


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _offset(frame: Frame, offset_mm: float, flip: bool) -> Frame:
    """``geometry.kernel.datum.offset_plane``: slide along z, then flip z and
    y keeping x."""
    origin, x, y, z = frame
    origin = _add(origin, _scale(z, offset_mm))
    if flip:
        return (origin, x, _scale(y, -1.0), _scale(z, -1.0))
    return (origin, x, y, z)


def _unsupported(why: str) -> PluginError:
    return PluginError(
        PLUGIN_INPUT_UNSUPPORTED,
        "The twisted prism needs its profile sketched on an origin plane or an "
        f"offset plane; {why}. Use Sweep with twist along a straight path.",
        input="profile",
    )


def plane_frame(plane: GeomRef, inputs: ExpandInputs) -> Frame:
    """The world frame of a sketch plane: an origin datum or a chain of offset
    datums (every one axis-aligned, so the arithmetic is exact)."""
    chain: list[DatumOffsetParams | DatumOffsetFromParams] = []
    while not isinstance(plane, DatumPlaneRef):
        datum = inputs.resolve(plane)
        if not isinstance(datum, DatumFeature):
            raise _unsupported("the profile's plane is not a datum")
        params = datum.params
        if not isinstance(params, DatumOffsetParams | DatumOffsetFromParams):
            raise _unsupported(f"its plane is a {params.kind!r} datum")
        chain.append(params)
        if len(chain) > MAX_PLANE_CHAIN:
            raise _unsupported("its plane chains through too many datums")
        if isinstance(params, DatumOffsetParams):
            plane = DatumPlaneRef(kind="datum_plane", plane=params.base)
        else:
            plane = params.base
    frame = ORIGIN_FRAMES[plane.plane]
    for params in reversed(chain):
        frame = _offset(frame, params.offset_mm, params.flip)
    return frame


def expand_v1(inputs: ExpandInputs) -> list[Member]:
    """Twisted prism 1.0.0: [axis_plane/0], path/0, sweep/0."""
    profile = inputs.feature("profile")
    sketch = inputs.resolve(profile)
    if not isinstance(sketch, SketchFeature):
        raise PluginError(
            PLUGIN_INPUT_INVALID, "The profile must be a sketch.", input="profile"
        )
    origin, x, y, z = plane_frame(sketch.params.plane, inputs)
    distance = inputs.number("distance_mm")
    if inputs.choice("direction") == "reverse":
        z = _scale(z, -1.0)
    centre = _add(
        origin,
        _add(
            _scale(x, inputs.number("axis_x_mm")), _scale(y, inputs.number("axis_y_mm"))
        ),
    )
    end = _add(centre, _scale(z, distance))

    base: PlaneName = "XY"
    for base in PATH_PLANES:
        if _dot(ORIGIN_FRAMES[base][3], z) == 0.0:
            break
    _, path_x, path_y, path_z = ORIGIN_FRAMES[base]
    offset = _dot(centre, path_z) + 0.0
    members: list[Member] = []
    path_plane: GeomRef = DatumPlaneRef(kind="datum_plane", plane=base)
    if offset != 0.0:
        members.append(
            Member(
                "axis_plane",
                0,
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(
                        kind="offset", base=base, offset_mm=offset
                    ),
                ),
            )
        )
        path_plane = inputs.ref("axis_plane")
    line = SketchLine(
        id="p1",
        kind="line",
        start=Point2D(x=_dot(centre, path_x) + 0.0, y=_dot(centre, path_y) + 0.0),
        end=Point2D(x=_dot(end, path_x) + 0.0, y=_dot(end, path_y) + 0.0),
    )
    members.append(
        Member(
            "path",
            0,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=path_plane, entities=[line], constraints=[]
                ),
            ),
        )
    )
    operation = inputs.choice("operation")
    members.append(
        Member(
            "sweep",
            0,
            SweepFeature(
                type="sweep",
                version=1,
                params=SweepParamsV1(
                    profile=FeatureRef(kind="feature", feature_id=profile.feature_id),
                    path=inputs.ref("path"),
                    operation="cut" if operation == "cut" else "add",
                    merge=inputs.choice("body") == "merge",
                    twist_angle_deg=inputs.number("twist_angle_deg"),
                ),
            ),
        )
    )
    return members


MANIFEST_V1 = PluginManifest(
    id="loft.twisted_prism",
    version="1.0.0",
    title="Twisted prism",
    description="A profile carried straight along its normal while it turns "
    "about an axis: a Sweep with twist along a straight path.",
    inputs=[
        ProfileInput(kind="profile", name="profile", label="Profile"),
        LengthInput(
            kind="length",
            name="distance_mm",
            label="Distance",
            default=10.0,
            minimum=0.0,
            exclusive_minimum=True,
        ),
        AngleInput(
            kind="angle",
            name="twist_angle_deg",
            label="Twist angle",
            description="Total turn over the distance; positive is right-handed "
            "about the direction of travel.",
            default=30.0,
            minimum=-MAX_TWIST_ANGLE_DEG,
            maximum=MAX_TWIST_ANGLE_DEG,
        ),
        LengthInput(
            kind="length",
            name="axis_x_mm",
            label="Twist axis X",
            description="Where the twist axis pierces the profile's sketch (x).",
            default=0.0,
        ),
        LengthInput(
            kind="length",
            name="axis_y_mm",
            label="Twist axis Y",
            description="Where the twist axis pierces the profile's sketch (y).",
            default=0.0,
        ),
        ChoiceInput(
            kind="choice",
            name="direction",
            label="Direction",
            options=[
                ChoiceOption(value="normal", label="Along the sketch normal"),
                ChoiceOption(value="reverse", label="Reversed"),
            ],
            default="normal",
        ),
        ChoiceInput(
            kind="choice",
            name="operation",
            label="Operation",
            options=[
                ChoiceOption(value="add", label="Join"),
                ChoiceOption(value="cut", label="Cut"),
            ],
            default="add",
        ),
        ChoiceInput(
            kind="choice",
            name="body",
            label="Result",
            options=[
                ChoiceOption(value="merge", label="Merge into the body"),
                ChoiceOption(value="new_body", label="New body"),
            ],
            default="merge",
        ),
    ],
    members=[
        PluginMemberRole(
            role="axis_plane",
            title="Axis plane",
            description="Offset plane holding the path (only off the origin).",
        ),
        PluginMemberRole(role="path", title="Path"),
        PluginMemberRole(role="sweep", title="Twisted sweep"),
    ],
)

TWISTED_PRISM_V1 = Plugin(MANIFEST_V1, expand_v1)
