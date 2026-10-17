"""A fixture plugin for the cut list: ``test.deck_b1``, the B1 deck's framing.

``docs/reference-parts/buildings.md`` B1, built from base features with the
member metadata the DECK plugin will carry, so the cut list can be checked
against the spec before that plugin exists (CUT-LIST). Never registered in
:data:`loft_plugins.REGISTRY`: a test installs its own registry with it, and
the geometry golden ``b1-deck-framing-16ft`` is its expansion at the default
width (``packages/loft-plugins/tests/test_deck_fixture.py`` pins the two).

Each member is a rectangle sketch of its section and a new-body extrude of
its length; members are separate bodies (RESEARCH §23). Units are inches in
the spec and millimetres here (x 25.4). X runs along the house, Y away from
it, Z up. The guard is left out, as it is from the spec's volume.

Roles emit in the cut-list table's order (ledger, rim, beam, joist, post,
deck), which is the order the cut list lists them.
"""

import math
from collections.abc import Iterator

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
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import (
    LengthInput,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


#: Deck constants from the spec (inches).
_PROJECTION = 144.0
_JOIST_DEPTH = 9.25
_PLY = 1.5
_JOIST_BOTTOM = 19.75
_JOIST_TOP = 29.0
_BEAM_Y = 126.0
_BEAM_BOTTOM = 10.5
_POST = 5.5
_BOARD = 5.5
_BOARD_PITCH = 5.625
_BOARDS = 26
_SPACING = 16.0
_MATERIAL = "southern_pine_pt"

_MANIFEST = PluginManifest(
    id="test.deck_b1",
    version="1.0.0",
    title="Deck (B1 fixture)",
    description="The B1 deck's framing and decking (a cut-list test fixture).",
    inputs=[
        LengthInput(
            kind="length",
            name="width_mm",
            label="Width",
            default=_mm(192.0),
            minimum=_mm(48.0),
            maximum=_mm(240.0),
        ),
    ],
    members=[
        PluginMemberRole(role="plane", title="Plane"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(role="ledger", title="Ledger"),
        PluginMemberRole(role="rim", title="Rim"),
        PluginMemberRole(role="beam", title="Beam"),
        PluginMemberRole(role="joist", title="Joist"),
        PluginMemberRole(role="post", title="Post"),
        PluginMemberRole(role="deck", title="Deck"),
    ],
)


def _rectangle(u0: float, u1: float, v0: float, v1: float) -> list[SketchLine]:
    corners = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=Point2D(x=_mm(corners[i][0]), y=_mm(corners[i][1])),
            end=Point2D(x=_mm(corners[(i + 1) % 4][0]), y=_mm(corners[(i + 1) % 4][1])),
        )
        for i in range(4)
    ]


class _Builder:
    """Emits section sketches and member extrudes with running indices."""

    def __init__(self, inputs: ExpandInputs) -> None:
        self.inputs = inputs
        self.sections = 0
        self.counts: dict[str, int] = {}

    def member(
        self,
        role: str,
        profile: str,
        plane: DatumPlaneRef | FeatureRef,
        rect: tuple[float, float, float, float],
        length: float,
        *,
        reverse: bool = False,
    ) -> Iterator[Member]:
        section = self.sections
        self.sections += 1
        index = self.counts.get(role, 0)
        self.counts[role] = index + 1
        yield Member(
            "section",
            section,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane, entities=list(_rectangle(*rect)), constraints=[]
                ),
            ),
        )
        yield Member(
            role,
            index,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=self.inputs.ref("section", section),
                    distance_mm=_mm(length),
                    operation="add",
                    direction="reverse" if reverse else "normal",
                    merge=False,
                ),
            ),
            MemberMetadata(profile=profile, material=_MATERIAL),
        )


def joist_centres(width: float) -> list[float]:
    """Joist centre X (in): both end joists flush, a 16 in layout between."""
    last = width - _PLY / 2
    inner = [_SPACING * n for n in range(1, int((last - 1e-9) // _SPACING) + 1)]
    return [_PLY / 2, *[x for x in inner if x < last], last]


def post_centres(width: float) -> list[float]:
    """Post centre X (in): both ends, equally spaced, no more than 8 ft apart."""
    first, last = _POST / 2, width - _POST / 2
    bays = max(1, math.ceil((last - first) / 96.0 - 1e-9))
    return [first + (last - first) * n / bays for n in range(bays + 1)]


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    width = inputs.number("width_mm") / MM_PER_INCH
    yz = DatumPlaneRef(kind="datum_plane", plane="YZ")  # u=+Y, v=+Z, normal +X
    xy = DatumPlaneRef(kind="datum_plane", plane="XY")  # u=+X, v=+Y, normal +Z
    # XZ's normal is -Y, so an offset of -1.5 in lands at Y = +1.5 (RESEARCH §12)
    # and a REVERSE extrude runs the joists away from the house (+Y).
    yield Member(
        "plane",
        0,
        DatumFeature(
            type="datum",
            version=1,
            params=DatumOffsetParams(base="XZ", offset_mm=-_mm(_PLY)),
        ),
    )
    joist_plane = inputs.ref("plane", 0)
    b = _Builder(inputs)
    yield from b.member(
        "ledger", "2x10", yz, (0.0, _PLY, _JOIST_BOTTOM, _JOIST_TOP), width
    )
    yield from b.member(
        "rim",
        "2x10",
        yz,
        (_PROJECTION - _PLY, _PROJECTION, _JOIST_BOTTOM, _JOIST_TOP),
        width,
    )
    for y0 in (_BEAM_Y - _PLY, _BEAM_Y):
        yield from b.member(
            "beam", "2x10", yz, (y0, y0 + _PLY, _BEAM_BOTTOM, _JOIST_BOTTOM), width
        )
    for x in joist_centres(width):
        yield from b.member(
            "joist",
            "2x10",
            joist_plane,
            (x - _PLY / 2, x + _PLY / 2, _JOIST_BOTTOM, _JOIST_TOP),
            _PROJECTION - 2 * _PLY,
            reverse=True,
        )
    for x in post_centres(width):
        yield from b.member(
            "post",
            "6x6",
            xy,
            (x - _POST / 2, x + _POST / 2, _BEAM_Y - _POST / 2, _BEAM_Y + _POST / 2),
            _BEAM_BOTTOM,
        )
    for i in range(_BOARDS):
        y0 = _BOARD_PITCH * i
        yield from b.member(
            "deck", "5/4x6", yz, (y0, y0 + _BOARD, _JOIST_TOP, _JOIST_TOP + 1.0), width
        )


DECK_B1 = Plugin(_MANIFEST, expand)
