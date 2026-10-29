"""Stair: a straight run of cut stringers, treads, risers and a handrail
(STAIRS, RESEARCH §23).

What Chief Architect's Stair tool and Revit's Stair by Component do, in their
order: count the risers from the total rise and a maximum riser height
(``ceil(rise / max)``, every riser equal), lay one tread fewer than risers at
the tread depth, and frame it (Chief's Build Framing cuts the stringers). A
stair is HOSTED on a deck edge (it picks an earlier ``loft.deck`` and reads
the deck's stored inputs; the deck is never changed) or FREE, at a typed
total rise, top nosing point and direction (an interior stair).

This is a FRAMING MODEL with a cut list, not a structural design; the IRC
R311.7 layout rules (riser, tread, nosing, width, handrail, headroom, open
risers) are checked because a builder lays a stair out by them, and a stair
that breaks one is refused with the section that names the reason.

**Frame.** Every member is laid out in the stair's own frame: ``u``
horizontal along the run, from the top nosing line (the deck's decking edge,
or the free stair's typed point) down the stair; ``s`` across it, from its
left edge looking down the stair, 0..width; ``z`` up from the stair's foot
(grade under a deck, the typed bottom elevation for a free stair). The four
walking directions map ``(s, u)`` to world X, Y.

**Layout** (n risers of R, n - 1 treads of run T, tread thickness t, tread
boards w wide with gap g, P = k w + (k - 1) g the fewest k boards covering T):

* Treads' tops stand at ``j R`` (j = 1..n-1, from the bottom); the deck's
  top (or the floor above) is the n-th. Tread j's stringer seat is at
  ``j R - t`` from ``u = a_j`` to ``a_j + T``, ``a_j = a_top + (n - 1 - j) T``.
* A tread's boards butt the riser board above it (closed risers, 3/4 in) or
  the stringer's riser cut (open), so each nosing sits ``c = P`` (open) or
  ``0.75 + P`` (closed) past its riser line. The top riser line is placed at
  ``a_top = T - c``, so every nosing-to-nosing depth, the deck's edge to the
  top tread's nosing included, is T exactly (R311.7.5.2). Under a deck the
  top riser line may not pass the framing face (the decking overhang ``o``):
  where ``T - c < -o`` it is ``-o`` and the top step is deeper by the
  difference, refused past R311.7.5.2's 3/8 in variance.
* **Stringers** are cut 2x12s (``d`` deep), at most 18 in on centres with
  both outer ones flush (AWC DCA6). The board's top edge passes through every
  tooth's point ``(a_j + T, j R - t)``; its bottom edge is parallel, d below
  (``d L / T`` vertically, ``L = sqrt(R^2 + T^2)``). The THROAT, the board
  left under each notch's inside corner, is ``d - R T / L`` (B1: 11.25 -
  82.5 / sqrt(177.25) = 5.0533 in). The foot is cut level on the stair's
  foot from the bottom riser line; under a deck the head is cut level under
  the decking and plumb against the rim (or end joist) face it hangs on; a
  free stair's head is cut plumb at the top riser line (the header's face).
  Each stringer is ONE profile on a vertical datum plane, extruded 1.5 in
  across the run: real B-rep, notched as cut.
* **Treads** are whole boards across the full width (the stringers' outside
  faces). **Risers** (closed) are 1x8 boards ripped to ``R - t``, from the
  top of the tread below to the underside of the tread above, nailed to the
  riser cuts; a free stair has no top riser board (that face is the upper
  floor's header, not modelled).
* **Handrail** (R311.7.8, required from 4 risers): a 2x2 (Type I graspable,
  6 in perimeter, R311.7.8.5) over the left or right stringer, its top
  ``handrail height`` above the nosing line, plumb-cut over the top nosing
  and over the lowest tread's nosing (continuous for the flight,
  R311.7.8.4). It is fastened to 4x4 posts outside that stringer, standing
  on the stair's foot at both ends and no more than 6 ft apart, each up to
  the rail's top over it.

**Refusals** (``plugin_input_unsupported``, the message leading with the
section): R311.7.1 width under 36 in; R311.7.5.1 a riser over 7-3/4 in or
open risers whose 4 in sphere test fails above 30 in; R311.7.5.2 a tread
under 10 in or a top step more than 3/8 in off the others; R311.7.5.3 a
nosing outside 3/4..1-1/4 in where the tread is under 11 in (over 1-1/4 in
always); R311.7.8 no handrail on 4 or more risers, R311.7.8.1 a handrail
outside 34..38 in; R311.7.2 headroom under 6 ft 8 in below a typed stairwell
opening. **Warnings** (:func:`stair_notes`, documents' ``plugin_warnings``):
a throat under DCA6's 5 in, open sides more than 30 in up without a guard
(R312.1.1), and a deck whose guard runs across the stair's head (the deck's
guard opening is a later deck release; this stair never changes the deck).

Inputs are millimetres on the wire, inches inside, each rounded to 1e-9 in.
"""

import math
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from loft_wire.features import (
    CustomFeature,
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import MM_PER_INCH, LumberProfile, lumber_profile
from loft_wire.materials import MaterialKey
from loft_wire.plugin_warning import (
    STAIR_DECK_GUARD,
    STAIR_GUARD_REQUIRED,
    STAIR_STRINGER_SPAN,
    STAIR_THROAT_THIN,
)
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    FeatureReferenceInput,
    LengthInput,
    MaterialInput,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError, lumber_options
from loft_plugins.builtin.deck import board_count, equal_centres

STAIR: Final = "loft.stair"
DECK: Final = "loft.deck"

#: IRC R311.7 limits and AWC DCA6 practice, in inches.
MAX_RISER: Final = 7.75  # R311.7.5.1
MIN_TREAD: Final = 10.0  # R311.7.5.2
VARIANCE: Final = 0.375  # R311.7.5.1 / R311.7.5.2: greatest less smallest
NOSING_FREE_TREAD: Final = 11.0  # R311.7.5.3 exception: no nosing needed
MIN_NOSING: Final = 0.75  # R311.7.5.3
MAX_NOSING: Final = 1.25  # R311.7.5.3
MIN_WIDTH: Final = 36.0  # R311.7.1
MIN_HEADROOM: Final = 80.0  # R311.7.2: 6 ft 8 in
HANDRAIL_RISERS: Final = 4  # R311.7.8: a handrail from 4 risers
MIN_HANDRAIL: Final = 34.0  # R311.7.8.1
MAX_HANDRAIL: Final = 38.0
OPEN_RISER_SPHERE: Final = 4.0  # R311.7.5.1: open risers above 30 in
GUARD_HEIGHT_ABOVE: Final = 30.0  # R312.1.1 and R311.7.5.1's 30 in
MAX_STRINGER_SPACING: Final = 18.0  # DCA6: cut stringers at most 18 in o.c.
MIN_THROAT: Final = 5.0  # DCA6: 5 in of stringer under each notch
#: DCA6's stair detail: cut stringers span at most 6'-0" horizontally
#: between supports (the 2013 southern-pine values took it from 7 ft).
MAX_CUT_STRINGER_SPAN: Final = 72.0
HANDRAIL_POST_SPACING: Final = 72.0  # the deck guard's 6 ft post rule

_INCH_DIGITS = 9
_EPS = 1e-9
_PT_PINE: MaterialKey = "southern_pine_pt"
_RISER_BOARD = lumber_profile("us_1x8")
_HANDRAIL = lumber_profile("us_2x2")
_POST = lumber_profile("us_4x4")

Vec2 = tuple[float, float]
Edge = Literal["front", "left", "right"]


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def _inches(name: str, inputs: ExpandInputs) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _INCH_DIGITS)


def _length(
    name: str,
    label: str,
    default_in: float,
    low_in: float,
    high_in: float,
    description: str,
    *,
    superseded: bool = False,
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=description,
        default=_mm(default_in),
        minimum=_mm(low_in),
        maximum=_mm(high_in),
        superseded_by="deck" if superseded else None,
    )


def _choice(
    name: str,
    label: str,
    options: list[tuple[str, str]],
    description: str,
    *,
    superseded: bool = False,
) -> ChoiceInput:
    return ChoiceInput(
        kind="choice",
        name=name,
        label=label,
        description=description,
        options=[ChoiceOption(value=v, label=t) for v, t in options],
        default=options[0][0],
        superseded_by="deck" if superseded else None,
    )


def _material(name: str, label: str) -> MaterialInput:
    return MaterialInput(
        kind="material",
        name=name,
        label=label,
        default=_PT_PINE,
        description="Library material of these members (their mass and cut list).",
    )


MANIFEST_V1 = PluginManifest(
    id=STAIR,
    version="1.0.0",
    title="Stair",
    description="A straight stair of cut stringers, treads, optional risers "
    "and a handrail, laid out to IRC R311.7, on a deck edge or at a typed "
    "rise (Chief Architect's Stair tool, Revit's Stair by Component).",
    inputs=[
        FeatureReferenceInput(
            kind="feature",
            name="deck",
            label="Deck",
            description="The deck whose edge the stair hangs from: it runs "
            "from the decking top to grade. Empty: a free stair at the "
            "typed rise.",
            feature_types=["custom"],
            plugin_ids=[DECK],
            optional=True,
        ),
        _choice(
            "edge",
            "Deck edge",
            [("front", "Front (the rim)"), ("left", "Left"), ("right", "Right")],
            "Which open edge of the deck the stair leaves from.",
        ),
        _length(
            "position_mm",
            "Position",
            96.0,
            0.0,
            480.0,
            "The stair's centre along the deck edge: from X 0 on the front, "
            "from the house on a side.",
        ),
        _length(
            "rise_mm",
            "Total rise",
            30.0,
            6.0,
            240.0,
            "Floor to floor: the bottom floor to the top of the upper floor.",
            superseded=True,
        ),
        _length(
            "x_mm",
            "Top X",
            0.0,
            -4800.0,
            4800.0,
            "The top nosing line's centre (X).",
            superseded=True,
        ),
        _length(
            "y_mm",
            "Top Y",
            0.0,
            -4800.0,
            4800.0,
            "The top nosing line's centre (Y).",
            superseded=True,
        ),
        _length(
            "bottom_mm",
            "Bottom elevation",
            0.0,
            -480.0,
            1200.0,
            "The floor the stair lands on (Z).",
            superseded=True,
        ),
        _choice(
            "direction",
            "Runs toward",
            [("pos_y", "+Y"), ("neg_y", "-Y"), ("pos_x", "+X"), ("neg_x", "-X")],
            "The way down the stair, from the top nosing.",
            superseded=True,
        ),
        _length(
            "width_mm",
            "Width",
            36.0,
            24.0,
            96.0,
            "Across the stringers' outside faces (IRC R311.7.1: at least 36 in).",
        ),
        _length(
            "max_riser_mm",
            "Maximum riser",
            MAX_RISER,
            4.0,
            9.0,
            "Risers are counted from the rise at this most and are all equal "
            "(IRC R311.7.5.1: at most 7-3/4 in).",
        ),
        _length(
            "tread_depth_mm",
            "Tread depth",
            11.0,
            8.0,
            14.0,
            "Nosing to nosing, the stringers' unit run "
            "(IRC R311.7.5.2: at least 10 in).",
        ),
        ChoiceInput(
            kind="choice",
            name="stringer_profile",
            label="Stringers",
            description="Cut stringer stock, at most 18 in on centres (AWC DCA6).",
            options=lumber_options(["us_2x10", "us_2x12"]),
            default="us_2x12",
        ),
        ChoiceInput(
            kind="choice",
            name="tread_profile",
            label="Treads",
            description="Tread boards, whole, as the decking is laid.",
            options=lumber_options(["us_5_4x6", "us_2x6"]),
            default="us_5_4x6",
        ),
        _length("tread_gap_mm", "Tread gap", 0.125, 0.0, 0.5, "Between boards."),
        _choice(
            "risers",
            "Risers",
            [("open", "Open"), ("closed", "Closed (1x8)")],
            "Closed risers are 1x8 boards ripped to the riser, on the riser cuts.",
        ),
        _choice(
            "handrail",
            "Handrail",
            [("left", "Left"), ("right", "Right"), ("none", "None")],
            "A 2x2 rail on 4x4 posts over the outer stringer on that side, "
            "looking down the stair (IRC R311.7.8: required from 4 risers).",
        ),
        _length(
            "handrail_height_mm",
            "Handrail height",
            36.0,
            30.0,
            42.0,
            "Above the nosing line (IRC R311.7.8.1: 34 to 38 in).",
        ),
        _length(
            "opening_length_mm",
            "Stairwell opening",
            0.0,
            0.0,
            480.0,
            "Length of the floor opening above, from the top nosing along the "
            "run, for the headroom check (IRC R311.7.2); 0: open above.",
            superseded=True,
        ),
        _length(
            "floor_depth_mm",
            "Floor above, depth",
            9.25,
            0.0,
            24.0,
            "The upper floor's depth at the opening's far edge, top to ceiling.",
            superseded=True,
        ),
        _material("stringer_material", "Stringer material"),
        _material("tread_material", "Tread and riser material"),
        _material("rail_material", "Handrail material"),
    ],
    members=[
        PluginMemberRole(role="level", title="Level"),
        PluginMemberRole(role="plane", title="Plane"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(
            role="stringer",
            title="Stringer",
            description="A cut stringer, one piece: notched for every tread.",
        ),
        PluginMemberRole(role="tread", title="Tread"),
        PluginMemberRole(role="riser", title="Riser"),
        PluginMemberRole(role="handrail", title="Handrail"),
        PluginMemberRole(role="handrail_post", title="Handrail post"),
    ],
)


# --- Layout (pure, inches) ---------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """Where the stair stands: its top nosing line's centre and walking
    direction in world plan, its foot elevation and rise, and what is above
    its head (a deck's decking)."""

    origin: Vec2
    direction: str  # "pos_y", "neg_y", "pos_x", "neg_x"
    bottom: float
    rise: float
    #: The decking's overhang past the framing face the stringers hang on
    #: (None: a free stair, hung on the header at the top riser line).
    overhang: float | None
    #: The decking's thickness (the stringers' head is cut level under it).
    decking: float
    #: The edge carries the deck's guard.
    guarded: bool
    #: A free stair's stairwell opening and the floor's depth (headroom).
    opening: float
    floor_depth: float


@dataclass(frozen=True)
class Layout:
    """The stair's numbers in its own frame (module docstring)."""

    risers: int
    riser: float
    tread: float
    width: float
    stringer: LumberProfile
    tread_board: LumberProfile
    gap: float
    boards: int
    closed: bool
    #: Each nosing past its riser line, and the top riser line.
    reach: float
    top_line: float
    #: The stringers' head: the plumb cut's u and the level cut's z (None:
    #: none), the stair foot being z 0.
    head_u: float
    head_z: float | None
    site: Site

    @property
    def treads(self) -> int:
        return self.risers - 1

    @property
    def run(self) -> float:
        """Nosing to nosing, the top nosing to the lowest tread's."""
        return self.treads * self.tread

    @property
    def slope_length(self) -> float:
        return math.hypot(self.riser, self.tread)

    @property
    def throat(self) -> float:
        return self.stringer.width_in - self.riser * self.tread / self.slope_length

    @property
    def nosing(self) -> float:
        """Each tread's projection past the riser (board) below it."""
        return self.pack - self.tread

    @property
    def pack(self) -> float:
        w = self.tread_board.width_in
        return self.boards * w + (self.boards - 1) * self.gap

    def seat(self, j: int) -> float:
        """Tread j's seat on the stringer (z, from the foot)."""
        return j * self.riser - self.tread_board.thickness_in

    def back(self, j: int) -> float:
        """``a_j``: tread j's riser line (u), j = 1..n-1 from the bottom."""
        return self.top_line + (self.risers - 1 - j) * self.tread

    def top_edge(self, u: float) -> float:
        """The stringer's top edge through every tooth's point (z at u)."""
        n, r, t = self.risers, self.riser, self.tread
        return n * r - self.tread_board.thickness_in - (u - self.top_line) * r / t

    def bottom_edge(self, u: float) -> float:
        drop = self.stringer.width_in * self.slope_length / self.tread
        return self.top_edge(u) - drop

    @property
    def foot_u(self) -> float:
        """The bottom riser line: tread 1's tooth point."""
        return self.back(1) + self.tread

    def nosing_line(self, u: float) -> float:
        return self.site.rise - u * self.riser / self.tread


def _unsupported(message: str, input_name: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=input_name)


@dataclass(frozen=True)
class DeckEdge:
    """One edge of a stored deck, read from its inputs (never its members)."""

    origin: Vec2  # the edge's nosing line at its start
    along: Vec2  # unit vector along the edge from its start
    direction: str  # walking down the stair
    length: float
    overhang: float
    framed: bool  # a rim or end joist the stringers hang on
    height: float
    decking: float
    guarded: bool


def deck_edge(deck: CustomFeature, edge: Edge) -> DeckEdge:
    """*edge* of *deck* (any ``loft.deck`` release: they share these inputs),
    with the decking's overhang there computed as the deck lays its boards
    (``loft_plugins.builtin.deck``)."""
    values = ExpandInputs(_DECK_ID, deck.params.inputs)
    width = _inches("width_mm", values)
    depth = _inches("depth_mm", values)
    height = _inches("height_mm", values)
    along_house = values.choice("joist_direction") == "along"
    attached = values.choice("attachment") == "ledger"
    rims = values.choice("rim_joists") == "yes"
    board = values.lumber("decking_profile")
    gap = _inches("decking_gap_mm", values)
    overhang = _inches("decking_overhang_mm", values)
    guarded = values.choice("guard") == "open_sides"
    w = board.width_in
    if along_house:
        # Boards run along Y in rows across X from X 0 (deck.py's b axis).
        rows_far = (board_count(width, overhang, w, gap) - 1) * (w + gap) + w
        front_o, left_o, right_o = overhang, 0.0, rows_far - width
        front_framed, side_framed = True, rims or attached
    else:
        rows_far = (board_count(depth, overhang, w, gap) - 1) * (w + gap) + w
        front_o, left_o, right_o = rows_far - depth, overhang, overhang
        front_framed, side_framed = rims, True
    if edge == "front":
        return DeckEdge(
            (0.0, depth + front_o), (1.0, 0.0), "pos_y", width, front_o,
            front_framed, height, board.thickness_in, guarded,
        )  # fmt: skip
    if edge == "left":
        return DeckEdge(
            (-left_o, 0.0), (0.0, 1.0), "neg_x", depth, left_o,
            side_framed, height, board.thickness_in, guarded,
        )  # fmt: skip
    return DeckEdge(
        (width + right_o, 0.0), (0.0, 1.0), "pos_x", depth, right_o,
        side_framed, height, board.thickness_in, guarded,
    )  # fmt: skip


#: ExpandInputs needs an id; the deck's inputs are only read through it.
_DECK_ID = uuid.UUID(int=0)


def site(inputs: ExpandInputs, width: float) -> Site:
    """The stair's site: on its picked deck's edge, or free (module docstring)."""
    # Canonical inputs leave an empty pick out; an expansion holds it as None.
    ref = inputs.optional_feature("deck") if "deck" in inputs.values else None
    if ref is None:
        return Site(
            origin=(_inches("x_mm", inputs), _inches("y_mm", inputs)),
            direction=inputs.choice("direction"),
            bottom=_inches("bottom_mm", inputs),
            rise=_inches("rise_mm", inputs),
            overhang=None,
            decking=0.0,
            guarded=False,
            opening=_inches("opening_length_mm", inputs),
            floor_depth=_inches("floor_depth_mm", inputs),
        )
    deck = inputs.resolve(ref)
    if not isinstance(deck, CustomFeature):
        raise PluginError(
            PLUGIN_INPUT_INVALID, "Deck: pick an earlier Deck.", input="deck"
        )
    edge_name = inputs.choice("edge")
    if edge_name not in ("front", "left", "right"):
        raise _unsupported(f"{edge_name!r} is not a deck edge", "edge")
    edge = deck_edge(deck, edge_name)
    if not edge.framed:
        raise _unsupported(
            "The stringers hang from a rim joist, and this deck has none on "
            "that edge: turn its rim joists on, or pick another edge.",
            "edge",
        )
    position = _inches("position_mm", inputs)
    if position - width / 2 < -_EPS or position + width / 2 > edge.length + _EPS:
        raise _unsupported(
            f"The {width:g} in stair centred at {position:g} in runs past the "
            f"deck's {edge.length:g} in edge: move it in.",
            "position_mm",
        )
    x0, y0 = edge.origin
    ax, ay = edge.along
    return Site(
        origin=(x0 + ax * position, y0 + ay * position),
        direction=edge.direction,
        bottom=0.0,
        rise=edge.height,
        overhang=edge.overhang,
        decking=edge.decking,
        guarded=edge.guarded,
        opening=0.0,
        floor_depth=0.0,
    )


def layout(inputs: ExpandInputs) -> Layout:
    """The stair's numbers, refused where they break IRC R311.7 (module
    docstring). Pure."""
    width = _inches("width_mm", inputs)
    if width < MIN_WIDTH - _EPS:
        raise _unsupported(
            f"IRC R311.7.1: a stair is at least {MIN_WIDTH:g} in wide; this "
            f"one is {width:g} in.",
            "width_mm",
        )
    where = site(inputs, width)
    most = _inches("max_riser_mm", inputs)
    tread = _inches("tread_depth_mm", inputs)
    risers = max(1, math.ceil(where.rise / most - _EPS))
    riser = where.rise / risers
    if riser > MAX_RISER + _EPS:
        raise _unsupported(
            f"IRC R311.7.5.1: risers of {riser:.4f} in are over the 7-3/4 in "
            "maximum; lower the maximum riser.",
            "max_riser_mm",
        )
    if risers < 2:
        raise _unsupported(
            f"A {where.rise:g} in rise is one step, not a stair: it needs two "
            "risers or more.",
            "rise_mm" if where.overhang is None else "deck",
        )
    if tread < MIN_TREAD - _EPS:
        raise _unsupported(
            f"IRC R311.7.5.2: treads are at least {MIN_TREAD:g} in deep, "
            f"nosing to nosing; this one is {tread:g} in.",
            "tread_depth_mm",
        )
    board = inputs.lumber("tread_profile")
    gap = _inches("tread_gap_mm", inputs)
    w = board.width_in
    boards = max(1, math.ceil((tread + gap) / (w + gap) - _EPS))
    pack = boards * w + (boards - 1) * gap
    nosing = pack - tread
    if nosing > MAX_NOSING + _EPS or (
        tread < NOSING_FREE_TREAD - _EPS and nosing < MIN_NOSING - _EPS
    ):
        raise _unsupported(
            f"IRC R311.7.5.3: {boards} {board.name} boards make a {pack:g} in "
            f"tread, a {nosing:g} in nosing on a {tread:g} in tread; a nosing "
            "is 3/4 to 1-1/4 in (none needed from 11 in): change the tread "
            "depth or the gap.",
            "tread_depth_mm",
        )
    closed = inputs.choice("risers") == "closed"
    reach = (_RISER_BOARD.thickness_in if closed else 0.0) + pack
    top_line = tread - reach
    head_u = top_line
    head_z: float | None = None
    if where.overhang is not None:
        if top_line < -where.overhang:
            top_line = head_u = -where.overhang
            deeper = top_line + reach - tread
            if deeper > VARIANCE + _EPS:
                raise _unsupported(
                    f"IRC R311.7.5.2: the top tread would be {deeper:g} in "
                    "deeper than the others (3/8 in at most): its nosing sits "
                    f"{reach - tread:g} in past its riser, and the decking "
                    f"overhangs the framing by only {where.overhang:g} in. "
                    + (
                        "Choose open risers, or let the decking overhang more."
                        if closed
                        else "Let the decking overhang more."
                    ),
                    "risers",
                )
        head_u = -where.overhang
        head_z = where.rise - where.decking
    if not closed:
        opening = riser - board.thickness_in
        # The highest open riser's opening sits on the top tread.
        sill = (risers - 1) * riser
        if opening > OPEN_RISER_SPHERE + _EPS and sill > GUARD_HEIGHT_ABOVE + _EPS:
            raise _unsupported(
                f"IRC R311.7.5.1: open risers more than 30 in above the floor "
                f"must not pass a 4 in sphere, and these open {opening:.4f} in "
                f"up to {sill:.4f} in: choose closed risers.",
                "risers",
            )
    rail = inputs.choice("handrail")
    if rail == "none" and risers >= HANDRAIL_RISERS:
        raise _unsupported(
            f"IRC R311.7.8: a flight of {risers} risers (4 or more) needs a "
            "handrail on at least one side.",
            "handrail",
        )
    height = _inches("handrail_height_mm", inputs)
    if rail != "none" and not (MIN_HANDRAIL - _EPS <= height <= MAX_HANDRAIL + _EPS):
        raise _unsupported(
            f"IRC R311.7.8.1: a handrail stands 34 to 38 in above the "
            f"nosings; this one is {height:g} in.",
            "handrail_height_mm",
        )
    if where.opening > _EPS:
        ceiling = where.rise - where.floor_depth
        walking = max(where.rise - where.opening * riser / tread, 0.0)
        headroom = ceiling - walking
        if headroom < MIN_HEADROOM - _EPS:
            raise _unsupported(
                f"IRC R311.7.2: {headroom:.4f} in of headroom under the "
                "stairwell's far edge, under the 6 ft 8 in minimum: lengthen "
                "the opening.",
                "opening_length_mm",
            )
    return Layout(
        risers=risers,
        riser=riser,
        tread=tread,
        width=width,
        stringer=inputs.lumber("stringer_profile"),
        tread_board=board,
        gap=gap,
        boards=boards,
        closed=closed,
        reach=reach,
        top_line=top_line,
        head_u=head_u,
        head_z=head_z,
        site=where,
    )


def stringer_profile(lay: Layout) -> list[Vec2]:
    """A cut stringer's side profile, ``(u, z)`` from the stair's foot,
    clockwise from its head (module docstring)."""
    n = lay.risers
    head = lay.head_u
    top: list[Vec2] = []
    if head < lay.top_line - _EPS:
        top += [(head, lay.top_edge(head)), (lay.top_line, lay.top_edge(lay.top_line))]
    for j in range(n - 1, 0, -1):
        a = lay.back(j)
        top += [(a, lay.seat(j)), (a + lay.tread, lay.seat(j))]
    foot = lay.foot_u
    outline = [
        *top,
        (foot, lay.bottom_edge(foot)),
        (head, lay.bottom_edge(head)),
    ]
    outline = _clip(outline, 0.0, above=True)
    if lay.head_z is not None:
        outline = _clip(outline, lay.head_z, above=False)
    return _tidy(outline)


def _clip(points: list[Vec2], level: float, *, above: bool) -> list[Vec2]:
    """*points* (a closed polygon) cut by the level line ``z == level``,
    keeping the side above (or below) it: one Sutherland-Hodgman pass."""
    inside: Callable[[Vec2], bool] = (
        (lambda p: p[1] >= level - _EPS) if above else (lambda p: p[1] <= level + _EPS)
    )

    def cross(p: Vec2, q: Vec2) -> Vec2:
        (u0, z0), (u1, z1) = p, q
        return (u0 + (u1 - u0) * (level - z0) / (z1 - z0), level)

    out: list[Vec2] = []
    for i, cur in enumerate(points):
        prev = points[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(cross(prev, cur))
            out.append(cur)
        elif inside(prev):
            out.append(cross(prev, cur))
    return out


def _tidy(points: list[Vec2]) -> list[Vec2]:
    """*points* without repeats and without a point on a straight run."""
    out: list[Vec2] = []
    for p in points:
        if not out or math.dist(out[-1], p) > 1e-9:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-9:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(cross) <= 1e-12:
                out.pop(i)
                changed = True
                break
    return out


def handrail_profile(lay: Layout, height: float) -> list[Vec2]:
    """The handrail's side profile ``(u, z)``: its top ``height`` above the
    nosing line, 1.5 in deep square to the slope, plumb over the top nosing
    (u 0) and the lowest tread's nosing (u = run)."""
    drop = _HANDRAIL.width_in * lay.slope_length / lay.tread
    u0, u1 = 0.0, lay.run
    t0, t1 = lay.nosing_line(u0) + height, lay.nosing_line(u1) + height
    return [(u0, t0 - drop), (u1, t1 - drop), (u1, t1), (u0, t0)]


def post_centres(lay: Layout) -> list[float]:
    """Handrail posts' centres along the run (u): at both ends of the rail,
    no more than 6 ft apart, equally spaced."""
    return equal_centres(lay.run, _POST.width_in, HANDRAIL_POST_SPACING)


def stringer_centres(lay: Layout) -> list[float]:
    """Stringer centres across the stair (s): both outer ones flush, at most
    18 in apart (DCA6), equally spaced."""
    return equal_centres(lay.width, lay.stringer.thickness_in, MAX_STRINGER_SPACING)


# --- World mapping -----------------------------------------------------------------

#: Walking direction -> (down-the-stair unit vector, rightward unit vector).
_FRAMES: Mapping[str, tuple[Vec2, Vec2]] = {
    "pos_y": ((0.0, 1.0), (1.0, 0.0)),
    "neg_y": ((0.0, -1.0), (-1.0, 0.0)),
    "pos_x": ((1.0, 0.0), (0.0, -1.0)),
    "neg_x": ((-1.0, 0.0), (0.0, 1.0)),
}


class _World:
    def __init__(self, lay: Layout) -> None:
        if lay.site.direction not in _FRAMES:
            raise _unsupported(
                f"{lay.site.direction!r} is not a direction", "direction"
            )
        self.down, self.right = _FRAMES[lay.site.direction]
        self.origin = lay.site.origin
        self.half = lay.width / 2
        self.bottom = lay.site.bottom
        self.along_y = self.down[0] == 0.0

    def point(self, s: float, u: float) -> Vec2:
        (dx, dy), (rx, ry) = self.down, self.right
        k = s - self.half
        return (
            self.origin[0] + u * dx + k * rx + 0.0,
            self.origin[1] + u * dy + k * ry + 0.0,
        )

    def rect(
        self, s0: float, s1: float, u0: float, u1: float
    ) -> tuple[float, float, float, float]:
        (xa, ya), (xb, yb) = self.point(s0, u0), self.point(s1, u1)
        return (min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb))

    def run(self, u: float) -> float:
        """The world coordinate along the run (Y or X) at u."""
        return self.point(self.half, u)[1 if self.along_y else 0]

    def side_face(self, s0: float, s1: float) -> float:
        """The low world coordinate (X or Y) of a board across s0..s1."""
        a, b = self.point(s0, 0.0), self.point(s1, 0.0)
        axis = 0 if self.along_y else 1
        return min(a[axis], b[axis])


# --- Emission ----------------------------------------------------------------------


def _number(value: float) -> str:
    return f"{value:.9f}".rstrip("0").rstrip(".") if value != 0 else "0"


def _polygon(points: list[Vec2]) -> list[SketchLine]:
    n = len(points)
    twice = sum(
        points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1]
        for i in range(n)
    )
    if twice < 0:
        points = list(reversed(points))
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=Point2D(x=_mm(points[i][0]), y=_mm(points[i][1])),
            end=Point2D(x=_mm(points[(i + 1) % n][0]), y=_mm(points[(i + 1) % n][1])),
        )
        for i in range(n)
    ]


class _Emitter:
    """Levels, side planes, sections and member extrudes, every one named by
    its place, so an edit elsewhere never renumbers a member."""

    def __init__(self, inputs: ExpandInputs) -> None:
        self.inputs = inputs
        self.indices: dict[str, int] = {}
        self.datums: dict[str, FeatureRef] = {}

    def _member(
        self,
        role: str,
        feature: DatumFeature | SketchFeature | ExtrudeFeature,
        name: str,
        metadata: MemberMetadata | None = None,
    ) -> tuple[Member, FeatureRef]:
        index = self.indices.get(role, 0)
        self.indices[role] = index + 1
        return Member(role, index, feature, metadata, name), self.inputs.ref(
            role, index, name
        )

    def _datum(
        self, base: Literal["XY", "XZ", "YZ"], offset_in: float
    ) -> Iterator[Member | DatumPlaneRef | FeatureRef]:
        offset_in = round(offset_in, _INCH_DIGITS) + 0.0
        if offset_in == 0.0:
            yield DatumPlaneRef(kind="datum_plane", plane=base)
            return
        role = "level" if base == "XY" else "plane"
        name = f"{base.lower()}/{_number(offset_in)}"
        if name not in self.datums:
            member, ref = self._member(
                role,
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(base=base, offset_mm=_mm(offset_in)),
                ),
                name,
            )
            self.datums[name] = ref
            yield member
        yield self.datums[name]

    def body(
        self,
        role: str,
        name: str,
        base: Literal["XY", "XZ", "YZ"],
        offset_in: float,
        outline: list[Vec2],
        distance_in: float,
        metadata: MemberMetadata,
        reverse: bool = False,
    ) -> Iterator[Member]:
        """One body: *outline* on the plane *base* offset *offset_in*,
        extruded *distance_in* along its normal (or against it)."""
        plane: DatumPlaneRef | FeatureRef | None = None
        for item in self._datum(base, offset_in):
            if isinstance(item, Member):
                yield item
            else:
                plane = item
        assert plane is not None
        section, profile = self._member(
            "section",
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane, entities=list(_polygon(outline)), constraints=[]
                ),
            ),
            f"{role}/{name}",
        )
        yield section
        member, _ = self._member(
            role,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=profile,
                    distance_mm=_mm(distance_in),
                    operation="add",
                    merge=False,
                    direction="reverse" if reverse else "normal",
                ),
            ),
            name,
            metadata,
        )
        yield member

    def box(
        self,
        role: str,
        name: str,
        rect: tuple[float, float, float, float],
        z0: float,
        z1: float,
        metadata: MemberMetadata,
    ) -> Iterator[Member]:
        x0, x1, y0, y1 = rect
        yield from self.body(
            role,
            name,
            "XY",
            z0,
            [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
            z1 - z0,
            metadata,
        )

    def side(
        self,
        world: _World,
        role: str,
        name: str,
        s0: float,
        thickness: float,
        outline: list[Vec2],
        metadata: MemberMetadata,
    ) -> Iterator[Member]:
        """A board standing across s0..s0 + thickness whose side profile is
        *outline* (u, z from the stair's foot)."""
        low = world.side_face(s0, s0 + thickness)
        points = [(world.run(u), world.bottom + z) for u, z in outline]
        if world.along_y:
            # YZ: (Y, Z) on the plane, normal +X.
            yield from self.body(role, name, "YZ", low, points, thickness, metadata)
        else:
            # XZ: (X, Z) on the plane, normal -Y: a plane at Y y is offset -y,
            # extruded against its normal toward +Y.
            yield from self.body(
                role, name, "XZ", -low, points, thickness, metadata, reverse=True
            )


def _ordinal(k: int, count: int) -> str:
    return "end" if k == count - 1 else str(k)


def _stringer_name(k: int, count: int) -> str:
    """The outer stringers by their side, looking down the stair; the inner
    ones by their number from the left (shared out across the width)."""
    return "left" if k == 0 else "right" if k == count - 1 else f"inner/{k}"


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    """1.0.0 (module docstring)."""
    lay = layout(inputs)
    world = _World(lay)
    e = _Emitter(inputs)
    stringer_mat = inputs.material("stringer_material")
    tread_mat = inputs.material("tread_material")
    rail_mat = inputs.material("rail_material")
    base = lay.site.bottom
    n, r = lay.risers, lay.riser
    t = lay.tread_board.thickness_in

    # Stringers, left to right.
    profile = stringer_profile(lay)
    meta = MemberMetadata(profile=lay.stringer.name, material=stringer_mat)
    centres = stringer_centres(lay)
    half = lay.stringer.thickness_in / 2
    for k, c in enumerate(centres):
        yield from e.side(
            world,
            "stringer",
            _stringer_name(k, len(centres)),
            c - half,
            lay.stringer.thickness_in,
            profile,
            meta,
        )

    # Treads, from the bottom, each its boards from the back.
    tread_meta = MemberMetadata(profile=lay.tread_board.name, material=tread_mat)
    start = _RISER_BOARD.thickness_in if lay.closed else 0.0
    w, g = lay.tread_board.width_in, lay.gap
    for j in range(1, n):
        a = lay.back(j) + start
        for b in range(lay.boards):
            u0 = a + b * (w + g)
            yield from e.box(
                "tread",
                f"step/{j}/{b}",
                world.rect(0.0, lay.width, u0, u0 + w),
                base + lay.seat(j),
                base + j * r,
                tread_meta,
            )

    # Closed risers, from the bottom: riser k under tread k (the deck's
    # decking for the top one; a free stair's top is the header).
    if lay.closed:
        riser_meta = MemberMetadata(profile=_RISER_BOARD.name, material=tread_mat)
        last = n if lay.site.overhang is not None else n - 1
        for k in range(1, last + 1):
            line = lay.back(k) + lay.tread if k < n else lay.top_line
            top = k * r - t if k < n else lay.site.rise - lay.site.decking
            yield from e.box(
                "riser",
                f"step/{k}",
                world.rect(0.0, lay.width, line, line + _RISER_BOARD.thickness_in),
                base + (k - 1) * r,
                base + top,
                riser_meta,
            )

    # The handrail over the outer stringer on its side, on its posts.
    side = inputs.choice("handrail")
    if side != "none":
        height = _inches("handrail_height_mm", inputs)
        rail_meta = MemberMetadata(profile=_HANDRAIL.name, material=rail_mat)
        s_rail = 0.0 if side == "left" else lay.width - _HANDRAIL.thickness_in
        yield from e.side(
            world,
            "handrail",
            side,
            s_rail,
            _HANDRAIL.thickness_in,
            handrail_profile(lay, height),
            rail_meta,
        )
        post_meta = MemberMetadata(profile=_POST.name, material=rail_mat)
        p = _POST.width_in
        s0 = -p if side == "left" else lay.width
        posts = post_centres(lay)
        for k, c in enumerate(posts):
            u0 = c - p / 2
            yield from e.box(
                "handrail_post",
                f"{side}/{_ordinal(k, len(posts))}",
                world.rect(s0, s0 + p, u0, u0 + p),
                base,
                base + lay.nosing_line(u0) + height,
                post_meta,
            )


def _feet_inches(inches: float) -> str:
    """*inches* as feet and inches to the nearest 1/16 (``11'-11"``)."""
    sixteenths = round(inches * 16)
    feet, rest = divmod(sixteenths, 12 * 16)
    whole, frac = divmod(rest, 16)
    if frac == 0:
        return f"{feet}'-{whole}\""
    g = math.gcd(frac, 16)
    return f"{feet}'-{whole} {frac // g}/{16 // g}\""


def stair_notes(inputs: ExpandInputs) -> list[tuple[str, str]]:
    """The stored stair's warnings, as (code, message): advice on a layout
    that builds (module docstring), none for one that is refused. Pure."""
    try:
        lay = layout(inputs)
    except PluginError:
        return []
    notes: list[tuple[str, str]] = []
    if lay.throat < MIN_THROAT - _EPS:
        notes.append(
            (
                STAIR_THROAT_THIN,
                f"AWC DCA6: the cut {lay.stringer.name} stringers keep a "
                f"{lay.throat:.4f} in throat under each notch, under the 5 in "
                "a cut stringer needs: "
                + (
                    "use 2x12 stringers, or a shallower riser or tread."
                    if lay.stringer.key != "us_2x12"
                    else "lower the maximum riser or the tread depth."
                ),
            )
        )
    span = lay.foot_u - lay.head_u
    if span > MAX_CUT_STRINGER_SPAN + _EPS:
        notes.append(
            (
                STAIR_STRINGER_SPAN,
                f"Cut stringers span {_feet_inches(span)} horizontally; DCA6 "
                "limits cut stringers to 6'-0\" between supports. Add a "
                "landing or an intermediate support, or use solid stringers.",
            )
        )
    top_tread = (lay.risers - 1) * lay.riser
    if top_tread > GUARD_HEIGHT_ABOVE + _EPS:
        notes.append(
            (
                STAIR_GUARD_REQUIRED,
                f"IRC R312.1.1: the top tread stands {top_tread:.4f} in above "
                "the floor below, over 30 in, so each open side needs a guard "
                "(with openings that stop a 4-3/8 in sphere, R312.1.3) or a "
                "wall; this stair frames neither.",
            )
        )
    if lay.site.guarded:
        notes.append(
            (
                STAIR_DECK_GUARD,
                "The deck's guard runs along this edge, across the head of "
                "the stair: a guard opening at the stair is a later deck "
                "release, and this stair never changes the deck. Turn the "
                "deck's guard off or leave the opening to the build.",
            )
        )
    return notes


#: Stringers and handrail posts are shared out across the width and along
#: the run: a write that moves a referenced one is refused.
STAIR_V1 = Plugin(
    MANIFEST_V1, expand, renumbered_roles=frozenset({"stringer", "handrail_post"})
)
