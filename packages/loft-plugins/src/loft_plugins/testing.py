"""A fixture plugin for tests: ``test.blocks``, released twice. Never registered
in :data:`loft_plugins.REGISTRY`; a test builds its own registry with it.

1.0.0 lays ``count`` blocks along +X, each a rectangle sketch on XY extruded
``depth_mm`` up. 2.0.0 "fixes" them to extrude down instead: a release that
changes the expansion for existing inputs, so it is a new version, and a
feature pinned to 1.0.0 must keep its 1.0.0 expansion byte for byte.
"""

from loft_wire.features import (
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.plugins import (
    CountInput,
    LengthInput,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin


def _manifest(version: str) -> PluginManifest:
    return PluginManifest(
        id="test.blocks",
        version=version,
        title="Blocks",
        description="A row of rectangular blocks (a test fixture).",
        inputs=[
            LengthInput(
                kind="length",
                name="width_mm",
                label="Width",
                default=20.0,
                minimum=0.0,
                exclusive_minimum=True,
            ),
            LengthInput(
                kind="length",
                name="depth_mm",
                label="Depth",
                default=5.0,
                minimum=0.0,
                exclusive_minimum=True,
            ),
            CountInput(
                kind="count",
                name="count",
                label="Count",
                default=1,
                minimum=1,
                maximum=50,
            ),
        ],
        members=[
            PluginMemberRole(role="profile", title="Profile"),
            PluginMemberRole(role="block", title="Block"),
        ],
    )


def _rectangle(x0: float, x1: float, half: float) -> list[SketchLine]:
    corners = [(x0, -half), (x1, -half), (x1, half), (x0, half)]
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=Point2D(x=corners[i][0], y=corners[i][1]),
            end=Point2D(x=corners[(i + 1) % 4][0], y=corners[(i + 1) % 4][1]),
        )
        for i in range(4)
    ]


def _blocks(inputs: ExpandInputs, direction: str) -> list[Member]:
    width = inputs.number("width_mm")
    depth = inputs.number("depth_mm")
    members: list[Member] = []
    for n in range(inputs.count("count")):
        x0 = n * 2.0 * width
        members.append(
            Member(
                "profile",
                n,
                SketchFeature(
                    type="sketch",
                    version=1,
                    params=SketchParamsV1(
                        plane=DatumPlaneRef(kind="datum_plane", plane="XY"),
                        entities=list(_rectangle(x0, x0 + width, width / 2.0)),
                        constraints=[],
                    ),
                ),
            )
        )
        members.append(
            Member(
                "block",
                n,
                ExtrudeFeature(
                    type="extrude",
                    version=1,
                    params=ExtrudeParamsV1(
                        profile=inputs.ref("profile", n),
                        distance_mm=depth,
                        operation="add",
                        direction="normal" if direction == "up" else "reverse",
                        merge=False,
                    ),
                ),
                MemberMetadata(material="pla", nominal_size=f"{width:g}x{depth:g}"),
            )
        )
    return members


def expand_v1(inputs: ExpandInputs) -> list[Member]:
    return _blocks(inputs, "up")


def expand_v2(inputs: ExpandInputs) -> list[Member]:
    return _blocks(inputs, "down")


BLOCKS_V1 = Plugin(_manifest("1.0.0"), expand_v1)
BLOCKS_V2 = Plugin(_manifest("2.0.0"), expand_v2)
