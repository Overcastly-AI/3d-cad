"""Timber frame: bents of posts and tie beams, girts between them, every
joint a pegged blind mortise and tenon (TIMBER-FRAME, RESEARCH §23).

What Cadwork, hsbCAD and the SketchUp timber framing extensions build: the
frame's members as S4S timbers, and each joint as ONE placement that cuts
both members, a mortise in the post, a tenon on the beam, and a peg hole
bored through both, with the peg itself a member of the cut list.
``docs/reference-parts/buildings.md`` B6 is the default frame exactly.

This is a FRAMING MODEL with a cut list, not a structural design: no span,
load, joint capacity or relish rule is checked (buildings.md). Plates,
braces, rafters, other joints and the drawbore offset are later rungs.

**Frame.** World X runs across the bents (the width), Y along the building
(the length), Z up; the frame occupies X 0..width, Y 0..length, with the
posts standing on Z 0. Bents stand at equal spacing along Y, the first flush
at Y 0 and the last at Y ``length``. Each bent is two posts at X 0 and X
``width`` (flush with the outside) and a tie beam between them, its top
flush with the post tops. Girts run along Y between neighbouring bents on
both sides, their tops at ``girt_height``. Beams (tie beams and girts) are
flush with the outside of the frame; an inner bent's tie beam is centred on
its posts.

**Members.** Every member is one body: a plan rectangle sketched on a level
(an ``XY`` datum at its bottom) and extruded up (``merge: false``), exactly
as ``loft.deck`` builds. Members never fuse, so the cut list measures each.

**Joints.** Each joint is emitted after the members, as base features:

* the TENON: a box extruded from one sketch, fused onto the beam's end
  (``boolean`` union, the tenon body consumed);
* the MORTISE: a second extrude of that SAME sketch, subtracted from the
  post, so mortise and tenon are one box by construction;
* the BORE: a Ø1 circle on a side datum through the post, at the tenon's
  mid-height and 2 in from the shoulder, extruded the post's full depth
  twice and subtracted from the post and from the beam (the holes are
  coaxial; the drawbore offset is not modelled);
* the PEG: a third extrude of the bore's circle, a white oak member.

**Fit (the clearance convention).** Joinery is modelled LINE TO LINE: the
tenon is exactly its mortise and the peg exactly its holes, so mating faces
coincide and touch, and no two bodies share volume. That is how hsbCAD and
Cadwork draw a joint with their clearances at zero, and why B6's volume is
the members' shoulder boxes. A shop's clearances (a mortise 1/16 in deep of
its tenon, a hole 1/32 in over its peg) are a later input.

**Decisions** (timber framing practice and buildings.md B6; RESEARCH §23):

* Tenons are 1.5 thick, the beam's depth less 1.5 wide (3/4 in of relish
  above and below), 4 long, centred on the beam's width; blind, so a post
  must be deeper than its tenons.
* An inner bent's post takes a girt from each side at the same height; the
  two tenons are each shortened to half the post less 1/4 in (3.5 in an 8x8)
  so their ends stand 1/2 in apart. A tenon shorter than 3 in (the peg's
  2 in and a diameter) is refused, as is a post narrower than its beams.
* Girts sit wholly below the tie beams, so a post's mortises never meet.
* Posts are square timbers; beams any timber with the larger face vertical.

Inputs are millimetres on the wire (their names end ``_mm``) and inches
inside, rounded to 1e-9 in as ``loft.deck`` does.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from loft_wire.features import (
    BooleanFeature,
    BooleanParamsV1,
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import MM_PER_INCH, LumberProfile, LumberProfileKey
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    CountInput,
    LengthInput,
    MaterialInput,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchCircle, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError, lumber_options

#: Joint constants (in): buildings.md B6.
TENON_THICKNESS = 1.5
TENON_RELISH = 0.75  # the tenon is the beam's depth less twice this
TENON_LENGTH = 4.0
PEG_DIAMETER = 1.0
PEG_FROM_SHOULDER = 2.0
#: Gap between the ends of two tenons meeting in one post (in).
OPPOSED_TENON_GAP = 0.5
#: The shortest tenon: the peg's offset and one diameter (in).
MIN_TENON = PEG_FROM_SHOULDER + PEG_DIAMETER
#: The shortest beam between shoulders (in).
MIN_SHOULDER_LENGTH = 24.0
#: The peg's section, as the cut list names it.
PEG_PROFILE = "Ø1"
#: Rounding of an input's inch value (see ``loft.deck``).
_INCH_DIGITS = 9

_FRAME_WOOD: MaterialKey = "dfl_lumber"
_PEG_WOOD: MaterialKey = "white_oak"
_POSTS: list[LumberProfileKey] = ["us_6x6", "us_8x8", "us_10x10", "us_12x12"]
_BEAMS: list[LumberProfileKey] = [
    "us_6x6",
    "us_6x8",
    "us_8x8",
    "us_8x10",
    "us_8x12",
    "us_10x10",
    "us_10x12",
    "us_12x12",
]


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def _inches(name: str, inputs: ExpandInputs) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _INCH_DIGITS)


def _length(
    name: str, label: str, default_in: float, low_in: float, high_in: float, text: str
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=text,
        default=_mm(default_in),
        minimum=_mm(low_in),
        maximum=_mm(high_in),
    )


def _profiles(
    name: str,
    label: str,
    keys: list[LumberProfileKey],
    default: LumberProfileKey,
    text: str,
) -> ChoiceInput:
    return ChoiceInput(
        kind="choice",
        name=name,
        label=label,
        description=text,
        options=lumber_options(keys),
        default=default,
    )


def _material(name: str, label: str, default: MaterialKey, text: str) -> MaterialInput:
    return MaterialInput(
        kind="material", name=name, label=label, default=default, description=text
    )


#: The most bents a frame may have: 8 bents are 44 joints and about 560
#: features, built in well under the gateway's budget (RESEARCH §23).
MAX_BENTS = 8

MANIFEST_V1 = PluginManifest(
    id="loft.timber_frame",
    version="1.0.0",
    title="Timber frame",
    description="Bents of posts and tie beams with girts between them, every "
    "joint a pegged mortise and tenon, with a cut list (Cadwork, hsbCAD).",
    inputs=[
        _length(
            "width_mm",
            "Width",
            144.0,
            72.0,
            480.0,
            "Across the bents (X), outside of the posts.",
        ),
        _length(
            "length_mm",
            "Length",
            192.0,
            72.0,
            960.0,
            "Along the building (Y), outside of the end bents.",
        ),
        CountInput(
            kind="count",
            name="bent_count",
            label="Bents",
            description="Bents at equal spacing, the first and last flush "
            "with the ends.",
            default=2,
            minimum=2,
            maximum=MAX_BENTS,
        ),
        _length(
            "post_height_mm",
            "Post height",
            96.0,
            48.0,
            288.0,
            "From Z 0 to the post tops; the tie beams' tops are flush with them.",
        ),
        _profiles("post_profile", "Posts", _POSTS, "us_8x8", "Post size (S4S)."),
        _profiles(
            "beam_profile",
            "Beams",
            _BEAMS,
            "us_8x8",
            "Tie beam and girt size (S4S), the larger face vertical.",
        ),
        _length(
            "girt_height_mm",
            "Girt height",
            60.0,
            6.0,
            288.0,
            "Top of the girts above Z 0; they must sit below the tie beams.",
        ),
        _material(
            "frame_material",
            "Frame material",
            _FRAME_WOOD,
            "Library material of the posts and beams (their mass and cut list).",
        ),
        _material(
            "peg_material",
            "Peg material",
            _PEG_WOOD,
            "Library material of the pegs.",
        ),
    ],
    members=[
        PluginMemberRole(role="level", title="Level"),
        PluginMemberRole(role="plane", title="Plane"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(role="post", title="Post"),
        PluginMemberRole(role="tie_beam", title="Tie beam"),
        PluginMemberRole(role="girt", title="Girt"),
        PluginMemberRole(role="tenon", title="Tenon"),
        PluginMemberRole(role="mortise", title="Mortise"),
        PluginMemberRole(role="bore", title="Peg hole"),
        PluginMemberRole(role="joint", title="Joint"),
        PluginMemberRole(role="peg", title="Peg"),
    ],
)


# --- Layout (pure, inches) ---------------------------------------------------------


@dataclass(frozen=True)
class Box:
    """An axis-aligned box (in)."""

    x0: float
    x1: float
    y0: float
    y1: float
    z0: float
    z1: float


#: The world axis a peg runs along.
Axis = Literal["x", "y"]
#: A beam member's role.
BeamRole = Literal["tie_beam", "girt"]


@dataclass(frozen=True)
class Peg:
    """A peg through a post: along *axis* from *start* to *end*, centred at
    (*across*, *z*), *across* being X for a peg along Y and Y along X."""

    axis: Axis
    across: float
    z: float
    start: float
    end: float


@dataclass(frozen=True)
class Joint:
    """One mortise and tenon: the post (by index) and the beam (role, index)
    it joins, the tenon's box (which is the mortise's), and the peg."""

    post: int
    beam_role: BeamRole
    beam: int
    tenon: Box
    peg: Peg


@dataclass(frozen=True)
class Frame:
    posts: list[Box]
    tie_beams: list[Box]
    girts: list[Box]
    joints: list[Joint]


def _unsupported(message: str, input_name: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=input_name)


def bent_positions(length: float, bents: int, post: float) -> list[float]:
    """Each bent's low-Y post face: equal spacing, the last flush at *length*."""
    pitch = (length - post) / (bents - 1)
    return [length - post if k == bents - 1 else pitch * k for k in range(bents)]


def frame_layout(
    width: float,
    length: float,
    bents: int,
    height: float,
    girt_top: float,
    post: LumberProfile,
    beam: LumberProfile,
) -> Frame:
    """The frame's members and joints (module docstring), or a typed refusal."""
    d = post.width_in
    bt, bd = beam.thickness_in, beam.width_in
    if bt > d:
        raise _unsupported(
            f"A {beam.name} beam is wider than a {post.name} post: choose a "
            "larger post or a narrower beam.",
            "beam_profile",
        )
    if d <= TENON_LENGTH:
        raise _unsupported(
            f"A {post.name} post is too small for a {TENON_LENGTH:g} in blind "
            "tenon: choose a larger post.",
            "post_profile",
        )
    opposed = min(TENON_LENGTH, (d - OPPOSED_TENON_GAP) / 2)
    if bents > 2 and opposed < MIN_TENON:
        raise _unsupported(
            f"An inner bent's {post.name} post takes two girt tenons that would "
            f"be {opposed:g} in long, under {MIN_TENON:g}: choose a larger post "
            "or two bents.",
            "post_profile",
        )
    if width - 2 * d < MIN_SHOULDER_LENGTH:
        raise _unsupported(
            f"The tie beams would be under {MIN_SHOULDER_LENGTH:g} in between "
            "the posts: widen the frame.",
            "width_mm",
        )
    ys = bent_positions(length, bents, d)
    if ys[1] - d < MIN_SHOULDER_LENGTH:
        raise _unsupported(
            f"The girts would be under {MIN_SHOULDER_LENGTH:g} in between the "
            "posts: lengthen the frame or use fewer bents.",
            "length_mm",
        )
    if bd >= height:
        raise _unsupported(
            "The posts are shorter than the tie beams are deep.", "post_height_mm"
        )
    if girt_top > height - bd:
        raise _unsupported(
            f"The girts must sit below the tie beams: their top at most "
            f"{height - bd:g} in.",
            "girt_height_mm",
        )
    if girt_top < bd:
        raise _unsupported(
            f"The girts would reach below Z 0: their top at least {bd:g} in.",
            "girt_height_mm",
        )

    sides = (0.0, width - d)  # each post's low-X face
    posts: list[Box] = []
    post_index: dict[tuple[int, int], int] = {}
    for k, y in enumerate(ys):
        for s, x in enumerate(sides):
            post_index[(k, s)] = len(posts)
            posts.append(Box(x, x + d, y, y + d, 0.0, height))

    joints: list[Joint] = []
    half = TENON_THICKNESS / 2

    # Tie beams: one per bent, X between the posts, flush outside.
    ties: list[Box] = []
    tz0, tz1 = height - bd, height
    for k, y in enumerate(ys):
        if k == 0:
            b0 = y
        elif k == bents - 1:
            b0 = y + d - bt
        else:
            b0 = y + (d - bt) / 2
        index = len(ties)
        ties.append(Box(d, width - d, b0, b0 + bt, tz0, tz1))
        centre = b0 + bt / 2
        for s, shoulder, sign in ((0, d, -1.0), (1, width - d, 1.0)):
            tip = shoulder + sign * TENON_LENGTH
            tenon = Box(
                min(shoulder, tip),
                max(shoulder, tip),
                centre - half,
                centre + half,
                tz0 + TENON_RELISH,
                tz1 - TENON_RELISH,
            )
            peg = Peg(
                "y", shoulder + sign * PEG_FROM_SHOULDER, (tz0 + tz1) / 2, y, y + d
            )
            joints.append(Joint(post_index[(k, s)], "tie_beam", index, tenon, peg))

    # Girts: between neighbouring bents on both sides, flush outside.
    girts: list[Box] = []
    gz0, gz1 = girt_top - bd, girt_top
    for k in range(bents - 1):
        lo, hi = ys[k] + d, ys[k + 1]
        for s, x in enumerate(sides):
            g0 = x if s == 0 else x + d - bt
            index = len(girts)
            girts.append(Box(g0, g0 + bt, lo, hi, gz0, gz1))
            centre = g0 + bt / 2
            for bent, shoulder, sign in ((k, lo, -1.0), (k + 1, hi, 1.0)):
                inner = 0 < bent < bents - 1
                tip = shoulder + sign * (opposed if inner else TENON_LENGTH)
                tenon = Box(
                    centre - half,
                    centre + half,
                    min(shoulder, tip),
                    max(shoulder, tip),
                    gz0 + TENON_RELISH,
                    gz1 - TENON_RELISH,
                )
                peg = Peg(
                    "x",
                    shoulder + sign * PEG_FROM_SHOULDER,
                    (gz0 + gz1) / 2,
                    x,
                    x + d,
                )
                joints.append(Joint(post_index[(bent, s)], "girt", index, tenon, peg))
    return Frame(posts, ties, girts, joints)


# --- Emission ----------------------------------------------------------------------


def _rectangle(box: Box) -> list[SketchLine]:
    corners = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
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
    """Members with running indices per role; datums emitted once each."""

    def __init__(self, inputs: ExpandInputs) -> None:
        self.inputs = inputs
        self._next: dict[str, int] = {}
        self._planes: dict[tuple[str, float], DatumPlaneRef | FeatureRef] = {}

    def add(
        self,
        role: str,
        feature: DatumFeature | SketchFeature | ExtrudeFeature | BooleanFeature,
        metadata: MemberMetadata | None = None,
    ) -> tuple[Member, FeatureRef]:
        index = self._next.get(role, 0)
        self._next[role] = index + 1
        return Member(role, index, feature, metadata), self.inputs.ref(role, index)

    def plane(
        self, base: Literal["XY", "XZ", "YZ"], offset_in: float
    ) -> Iterator[Member]:
        """Emit the datum *offset_in* along *base*'s normal, once."""
        offset_in += 0.0  # never a -0.0 on the wire
        key = (base, offset_in)
        if key in self._planes:
            return
        if offset_in == 0.0:
            self._planes[key] = DatumPlaneRef(kind="datum_plane", plane=base)
            return
        member, ref = self.add(
            "level" if base == "XY" else "plane",
            DatumFeature(
                type="datum",
                version=1,
                params=DatumOffsetParams(base=base, offset_mm=_mm(offset_in)),
            ),
        )
        self._planes[key] = ref
        yield member

    def sketch(
        self,
        base: Literal["XY", "XZ", "YZ"],
        offset_in: float,
        entities: list[SketchLine] | list[SketchCircle],
    ) -> Iterator[Member | FeatureRef]:
        """Emit the plane (if new) and a sketch on it; yields the sketch's
        reference last."""
        yield from self.plane(base, offset_in)
        member, ref = self.add(
            "section",
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=self._planes[(base, offset_in + 0.0)],
                    entities=list(entities),
                    constraints=[],
                ),
            ),
        )
        yield member
        yield ref

    def extrude(
        self,
        role: str,
        profile: FeatureRef,
        distance_in: float,
        metadata: MemberMetadata | None = None,
    ) -> tuple[Member, FeatureRef]:
        return self.add(
            role,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=profile,
                    distance_mm=_mm(distance_in),
                    operation="add",
                    merge=False,
                ),
            ),
            metadata,
        )

    def boolean(
        self,
        operation: Literal["union", "subtract"],
        target: FeatureRef,
        tool: FeatureRef,
    ) -> Member:
        member, _ = self.add(
            "joint",
            BooleanFeature(
                type="boolean",
                version=1,
                params=BooleanParamsV1(operation=operation, target=target, tool=tool),
            ),
        )
        return member


def _split(items: Iterator[Member | FeatureRef]) -> tuple[list[Member], FeatureRef]:
    """A sketch's members and its reference (yielded last)."""
    out = list(items)
    ref = out.pop()
    assert isinstance(ref, FeatureRef)
    return [m for m in out if isinstance(m, Member)], ref


def _box_sketch(b: _Builder, box: Box) -> tuple[list[Member], FeatureRef]:
    return _split(b.sketch("XY", box.z0, _rectangle(box)))


def _peg_sketch(b: _Builder, peg: Peg) -> tuple[list[Member], FeatureRef]:
    """The peg's circle at its start face: along Y on an XZ datum (normal -Y,
    so at world Y = -offset, at the peg's high end), along X on a YZ datum
    (normal +X, at its low end); both extrude the peg's length."""
    base: Literal["XZ", "YZ"] = "XZ" if peg.axis == "y" else "YZ"
    offset = -peg.end if peg.axis == "y" else peg.start
    circle = SketchCircle(
        id="c1",
        kind="circle",
        center=Point2D(x=_mm(peg.across), y=_mm(peg.z)),
        radius=_mm(PEG_DIAMETER / 2),
    )
    return _split(b.sketch(base, offset, [circle]))


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    post_p = inputs.lumber("post_profile")
    beam_p = inputs.lumber("beam_profile")
    frame = frame_layout(
        _inches("width_mm", inputs),
        _inches("length_mm", inputs),
        inputs.count("bent_count"),
        _inches("post_height_mm", inputs),
        _inches("girt_height_mm", inputs),
        post_p,
        beam_p,
    )
    yield from emit_frame(
        inputs,
        frame,
        post_p,
        beam_p,
        inputs.material("frame_material"),
        inputs.material("peg_material"),
    )


def emit_frame(
    inputs: ExpandInputs,
    frame: Frame,
    post_p: LumberProfile,
    beam_p: LumberProfile,
    frame_mat: MaterialKey | None,
    peg_mat: MaterialKey | None,
) -> Iterator[Member]:
    """*frame*'s members, then its joints (module docstring). Public so the
    one-joint golden ``timber-mt-8x8`` is built by this exact code from a
    frame of one post and one beam."""
    peg_meta = MemberMetadata(profile=PEG_PROFILE, material=peg_mat)
    b = _Builder(inputs)

    refs: dict[str, list[FeatureRef]] = {"post": [], "tie_beam": [], "girt": []}
    for role, boxes, profile in (
        ("post", frame.posts, post_p),
        ("tie_beam", frame.tie_beams, beam_p),
        ("girt", frame.girts, beam_p),
    ):
        meta = MemberMetadata(profile=profile.name, material=frame_mat)
        for box in boxes:
            members, section = _box_sketch(b, box)
            yield from members
            member, ref = b.extrude(role, section, box.z1 - box.z0, meta)
            refs[role].append(ref)
            yield member

    for joint in frame.joints:
        post = refs["post"][joint.post]
        beam = refs[joint.beam_role][joint.beam]
        tenon = joint.tenon
        members, section = _box_sketch(b, tenon)
        yield from members
        depth = tenon.z1 - tenon.z0
        member, tenon_ref = b.extrude("tenon", section, depth)
        yield member
        yield b.boolean("union", beam, tenon_ref)
        member, mortise_ref = b.extrude("mortise", section, depth)
        yield member
        yield b.boolean("subtract", post, mortise_ref)
        members, circle = _peg_sketch(b, joint.peg)
        yield from members
        length = joint.peg.end - joint.peg.start
        for target in (post, beam):
            member, bore_ref = b.extrude("bore", circle, length)
            yield member
            yield b.boolean("subtract", target, bore_ref)
        member, _ = b.extrude("peg", circle, length, peg_meta)
        yield member


TIMBER_FRAME_V1 = Plugin(MANIFEST_V1, expand)
