"""Cut list: members grouped by profile, material and length (CUT-LIST).

The SolidWorks weldment cut list and the Chief Architect materials list: every
member of a part (each body) or of an assembly (every part at every level,
times its quantity) is one PIECE, and pieces with the same member role,
profile, material and length are one LINE with a quantity, a total length and
the shortest standard stock length it is cut from.

Where each fact comes from (RESEARCH §23, CLAUDE.md boundaries):

* **Lengths are measured, never read from metadata.** Geometry measures each
  body's extents in the body's own frame (:class:`BodyExtent`), so a member
  a plugin claims is 141 in long is listed at whatever its solid measures.
* **Role, profile and material** come from a plugin member's
  :class:`~loft_wire.plugins.MemberMetadata` (documents serves them,
  :class:`CutListMember`). The profile names the section, and the measured
  extent that is not that section is the length.
* **A body without metadata** is classified by its section: a straight prism
  (volume = the product of its extents) whose two smaller extents equal a
  library profile's actual size, to :data:`SECTION_TOLERANCE_MM`, is that
  profile; anything else is ``unclassified`` and listed with its measured
  section and length.

Material: a body's own override wins (what the user set on that body), then
the member's metadata, then the document default. Stock lengths are the US
lumber lengths its profile is sold in (:func:`~loft_wire.lumber.
stock_lengths_ft`: to 24 ft for dimension lumber, else 20 ft); the shortest
that covers the member is suggested, with the offcut it leaves. A member
longer than the longest stock is SPLICED from stock pieces, as a framer buys
a long plate (:func:`stock_splices`, RESEARCH §27): the pieces covering it
in the fewest pieces (joints), then with the least waste; when pricing, the
first such splice whose every piece the book prices, as a yard quotes it.
A member that SPANS between bearings (a joist, rafter, hip, header or beam,
:data:`ONE_PIECE_ROLES`) or stands as a column (a stud or post) is never
spliced (NO-SPLICE-SPANS): past the longest stock it has no stock and says
why (``stock_note``). A member no :data:`MAX_SPLICE_PIECES`-piece splice
covers, or one that is not lumber, has no stock suggestion.

**Sheet goods** (SHEATHING): a member whose ``profile`` names a sheet product
(:mod:`loft_wire.sheet_goods`, "7/16 OSB") is a PANEL. Its thickness is its
smallest measured extent and its net area its volume over that thickness
(openings cut out), and it is cut from the shortest sheet covering its other
two extents. Panels group by product, material and sheet (not by member or
size), and a line buys the sheets its panels are CUT from, as a yard sells
whole sheets (:func:`sheets_to_cut`, SHEET-COUNT-PIECES): each panel takes a
sheet unless an earlier offcut of the line covers it whole, largest panels
first (:mod:`loft_wire.sheet_nesting`), a saw kerf lost at every cut
(SHEET-KERF) and a piece up to 1/8 in short filling its panel in APA's panel
gap (SHEET-KERF-GAP). A floor panel keeps the sheet's strength axis across the
joists, so it is never turned to fit an offcut (SUBFLOOR-GRAIN); a wall
panel may be. Openings are not credited (framers sheathe over them and cut
them out), so a line's offcut area is its sheets' area less its net area.

**Order** (CUT-LIST-PANEL): lines are grouped by SYSTEM, as Chief
Architect's Materials List groups by category: Floor, Walls (with their doors
and windows, partitions and gypsum board), Roof, Sheathing (every structural
sheet good), then Deck, Frame and Other.
A plugin member's system is its plugin's (:func:`system_for_plugin`). Within a
system, lines run by member (in the order each first appears in the tree),
then profile and material (likewise), then length, shortest first, so one
member's lines sit together whichever walls they came from. Pieces with the
same system, member, profile, material and length are one line, summed across
features. The CSV writes the same order, each row naming its System.

**Window and door units** (OPENING-UNITS): a unit is bought whole, so its
bodies (a frame and its glazing, or a frame and a door's slab) are ONE piece,
listed on the body its metadata marks ``counted`` (the frame), the others
skipped. Units group by system (Walls, their plugin's), kind, size and
material, one Each line ("Window 3040 x 3"), priced by the book's entry for
their key (``window_3040``) and frame material. A custom size has no key and
stays unpriced.

**Foundation items** (SLAB, :mod:`loft_wire.foundation`): a concrete body
(its metadata's ``concrete``) is a POUR, listed by its MEASURED volume and
grouped by product, material and waste allowance across members, as sheets
are; the line orders ``net x (1 + waste)`` rounded up to 1/4 yd³ and is
priced per cubic yard ordered. Rebar and anchor bolts are listed, not drawn:
a pour's ``rebar`` runs are lines by centreline length, each run bought in
20 ft sticks lapped 24 in, and a plate with ``anchor_bolts`` adds its bolts,
counted from the plate's measured length (IRC R403.1.6), into one Each line.
All three sit under Foundation, the list's first system.

Prices (PRICE-BOOK, RESEARCH §27) come from the user's
:mod:`loft_wire.price_book`: each line is priced on the stock pieces bought
(:func:`price_lines`), in integer cents, and a line the book does not price
stays null (blank, never $0); the response totals the priced lines and counts
the rest.

This module is pure (no I/O, no kernel): the gateway assembles the cut list
with it, and the B1 acceptance test calls it on geometry's measurements.
"""

import math
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import combinations_with_replacement, permutations
from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from loft_wire.assemblies import RefDocumentKind
from loft_wire.features import EvaluateTreeRequest
from loft_wire.foundation import (
    FOUNDATION_ITEMS_BY_KEY,
    FoundationItemKind,
    anchor_bolt_count,
    concrete_order_yd3,
    foundation_item_for,
    rebar_sticks,
)
from loft_wire.lumber import (
    COMMON_MAX_STOCK_FT,
    COMMON_STOCK_LENGTHS_FT,
    LUMBER_PROFILES,
    MM_PER_INCH,
    STOCK_LENGTHS_FT,
    LumberProfile,
    stock_lengths_ft,
)
from loft_wire.materials import (
    MaterialAssignment,
    MaterialKey,
)
from loft_wire.opening_units import OpeningKind, OpeningUnitPart
from loft_wire.plugins import MemberMetadata, PluginId
from loft_wire.price_book import (
    EMPTY_PRICE_BOOK,
    Currency,
    PriceBookEntry,
    PriceBookResponse,
    PriceKey,
    PriceUnit,
)
from loft_wire.sheet_goods import (
    SheetMaterialKey,
    SheetSize,
    SheetSizeKey,
    covering_sheet,
    sheet_good_for,
)
from loft_wire.sheet_nesting import sheets_to_cut
from loft_wire.twist import is_none
from loft_wire.units import LengthUnit

#: Millimetres per foot, exactly.
MM_PER_FOOT: Final = 12 * MM_PER_INCH

#: How close a measured section must be to a profile's actual size (mm):
#: 0.01 mm, about 0.0004 in, far tighter than any dressed-size variation and
#: far looser than the kernel's 1e-7 mm modelling tolerance.
SECTION_TOLERANCE_MM: Final = 0.01

#: A body is a straight prism when its volume is the product of its extents
#: to this relative tolerance (a cut, notch or mitre fails it).
PRISM_TOLERANCE: Final = 1e-6

#: Lengths group when equal to this many decimals of a millimetre (1 um).
LENGTH_DECIMALS: Final = 3

#: The most stock pieces one member is spliced from: 5 x 24 ft covers 120 ft
#: of dimension lumber (5 x 20 ft, 100 ft, of the rest). A longer member (a
#: modelling slip more often than a real plate) has no stock, so it is listed
#: and left unpriced, never guessed at.
MAX_SPLICE_PIECES: Final = 5

#: Member roles that are ONE piece of stock, never spliced (NO-SPLICE-SPANS,
#: RESEARCH §27): members that span between bearings (joists, rafters and
#: their jacks, cripples, hips and valleys, headers, beams and a timber
#: frame's tie beams and girts), whose splice would be a hinge mid-span, and
#: columns (studs, kings, posts, balusters). Plates, sills, rims, ledgers,
#: ridges, rails and decking bear along their length (or are joined over a
#: support), so they may still splice; so may a body that is no plugin
#: member, whose role is unknown. Roles, not titles: the plugins' manifests
#: name them (``loft_plugins.builtin``).
ONE_PIECE_ROLES: Final[frozenset[str]] = frozenset(
    {
        # floor and deck
        "joist",
        "beam",
        "post",
        "guard_post",
        "baluster",
        # walls
        "stud",
        "king",
        "jack",
        "header",
        "cripple",
        "sill_cripple",
        # roofs
        "rafter",
        "common",
        "valley_jack",
        "hip",
        "valley",
        # timber frame
        "tie_beam",
        "girt",
    }
)

#: Sheet-good roles whose panels keep the sheet's strength axis (its length)
#: across their supports, so the count never turns one to fit an offcut
#: (SUBFLOOR-GRAIN: APA lays floor panels strength axis across the joists).
#: Wall sheathing may run either way, so its panels may turn.
GRAIN_LOCKED_ROLES: Final[frozenset[str]] = frozenset({"subfloor"})


#: How a piece was identified: from a plugin member's metadata, by matching
#: its section to a library profile, or not at all.
CutListClassification = Literal["member", "matched", "unclassified"]

#: The system a line belongs to (CUT-LIST-PANEL), in the order the list is
#: grouped: a materials list's categories.
CutListSystem = Literal[
    "foundation", "floor", "walls", "roof", "sheathing", "deck", "frame", "other"
]

#: :data:`CutListSystem` in list order.
SYSTEM_ORDER: Final[tuple[CutListSystem, ...]] = (
    "foundation",
    "floor",
    "walls",
    "roof",
    "sheathing",
    "deck",
    "frame",
    "other",
)

#: How a system is named in the CSV and the panel's group heads.
SYSTEM_LABELS: Final[Mapping[CutListSystem, str]] = {
    "foundation": "Foundation",
    "floor": "Floor",
    "walls": "Walls",
    "roof": "Roof",
    "sheathing": "Sheathing",
    "deck": "Deck",
    "frame": "Frame",
    "other": "Other",
}

#: The system each built-in plugin's members belong to. Doors and windows
#: frame into their wall, so their members are the walls' (a later Doors and
#: windows group would take them). A plugin not listed is "other".
PLUGIN_SYSTEMS: Final[Mapping[str, CutListSystem]] = {
    "loft.slab": "foundation",
    "loft.floor": "floor",
    "loft.wall": "walls",
    "loft.interior_wall": "walls",
    "loft.window": "walls",
    "loft.door": "walls",
    "loft.roof": "roof",
    "loft.deck": "deck",
    "loft.timber_frame": "frame",
}


def system_for_plugin(plugin_id: str | None) -> CutListSystem:
    """The system a plugin's members are listed under (:data:`PLUGIN_SYSTEMS`)."""
    return "other" if plugin_id is None else PLUGIN_SYSTEMS.get(plugin_id, "other")


def _is_false(value: object) -> bool:
    """``exclude_if`` predicate: a false flag is not serialized."""
    return value is False


def _drop_schema_default(schema: dict[str, Any]) -> None:
    """Keep a defaulted flag OPTIONAL in the generated ts-client."""
    schema.pop("default", None)


#: A direction in world coordinates.
Vec3 = tuple[float, float, float]


def sheet_system(material: SheetMaterialKey) -> CutListSystem:
    """The system a sheet good's panels are listed under: structural panels
    (OSB, plywood) are Sheathing; gypsum board is a wall finish, listed with
    the Walls it is hung on (INTERIOR-WALLS), as Chief Architect's materials
    list keeps wallboard with the walls."""
    return "walls" if material == "gypsum" else "sheathing"


# --- geometry -> gateway ------------------------------------------------------------


class BodyExtent(BaseModel):
    """One body's measured size (geometry, ``POST /api/v1/bodies/extents``).

    ``extents_mm`` is the body's exact extent along the three axes of its own
    frame (the normals of its two largest perpendicular planar faces, else its
    principal axes of inertia), longest first. For a straight member that is
    its length and its section, whatever its orientation in the part."""

    base_feature_id: uuid.UUID = Field(
        description="Id of the feature that created the body (its identity)."
    )
    extents_mm: tuple[float, float, float] = Field(
        description="Extents along the body's own axes (mm), longest first."
    )
    volume_mm3: float = Field(ge=0, description="The body's volume (mm^3).")
    axes: tuple[Vec3, Vec3, Vec3] | None = Field(
        default=None,
        exclude_if=is_none,
        description="The world direction of each extent (sign-free unit "
        "vectors), in extents_mm's order, so the cut list can tell which way "
        "a floor panel runs across the joists (SUBFLOOR-GRAIN). Absent from "
        "an older geometry service.",
    )


class BodyExtentsResult(BaseModel):
    """Every last-good body of an evaluated tree, measured, in tree order."""

    part_id: uuid.UUID
    tree_version: int = Field(ge=0)
    bodies: list[BodyExtent] = Field(default_factory=list[BodyExtent])


# --- documents -> gateway -----------------------------------------------------------


class CutListMember(BaseModel):
    """A plugin member that may create a body, with its cut-list metadata."""

    feature_id: uuid.UUID = Field(
        description="The member's id: the base feature id of the body it makes."
    )
    role: str = Field(max_length=64, description="Manifest role, e.g. 'joist'.")
    title: str = Field(
        max_length=80,
        description="The role's title, e.g. 'Joist' (from the manifest, or the "
        "role itself when this server lacks the plugin).",
    )
    plugin_id: PluginId | None = Field(
        default=None,
        # Absent, not null, when unknown: the goldens' members.json fixtures
        # predate the field and stay byte-identical.
        exclude_if=is_none,
        description="The plugin that generated the member ('loft.wall'): the "
        "cut list groups its lines by the plugin's system. Absent when "
        "unknown (listed under 'other').",
    )
    metadata: MemberMetadata


class CutListPartRequest(BaseModel):
    """What the gateway needs from documents to build one part's cut list."""

    part_id: uuid.UUID
    name: str
    length_unit: LengthUnit
    members: list[CutListMember] = Field(default_factory=list[CutListMember])
    evaluation: EvaluateTreeRequest


# --- gateway -> web -----------------------------------------------------------------


class CutListLine(BaseModel):
    """One line: pieces with the same system, member, profile, material and
    length; or window or door units of one size and material."""

    system: CutListSystem = Field(
        description="The group the line is listed under (Floor, Walls, Roof, "
        "Sheathing, ...): its members' plugin's system; a structural sheet "
        "good is 'sheathing' and gypsum board 'walls'; a body that is no "
        "plugin member is 'other'."
    )
    member: str | None = Field(
        description="Member role title (e.g. 'Joist'); null when the body is "
        "not a plugin member."
    )
    profile: str | None = Field(
        description="Section or sheet product as sold (e.g. '2x10', '7/16 "
        "OSB'); null when unclassified."
    )
    material: MaterialKey | None = Field(description="Library material, or null.")
    classification: CutListClassification
    quantity: int = Field(ge=1)
    length_mm: float = Field(
        ge=0,
        description="Measured length of each piece; for a sheet line, the "
        "sheet's length.",
    )
    total_length_mm: float = Field(
        ge=0,
        description="quantity x length; for a sheet line, the sheets' "
        "lengths (stock_quantity x length).",
    )
    section_mm: list[float] = Field(
        min_length=2,
        max_length=2,
        description="Measured section (mm): [thickness, width], smaller first; "
        "for a sheet line, [thickness, the sheet's width].",
    )
    sheet: SheetSizeKey | None = Field(
        default=None,
        description="A sheet line's sheet ('4x8', '4x9', '4x10', '4x12'): the "
        "shortest that covers each of its panels; null for lumber, or for "
        "panels no sheet covers.",
    )
    area_mm2: float | None = Field(
        default=None,
        ge=0,
        description="A sheet line's net area (mm^2): its panels' faces, "
        "openings cut out. Null for lumber.",
    )
    offcut_area_mm2: float | None = Field(
        default=None,
        ge=0,
        description="A sheet line's offcut (mm^2): its sheets' area less its "
        "net area (the offcuts and the openings cut out). Null for lumber, "
        "or for panels no sheet covers.",
    )
    stock_length_ft: int | None = Field(
        description="Shortest standard stock that covers the piece (ft); null "
        "for a piece that is not lumber, or is spliced (stock_pieces_ft), or "
        "is longer than any stock it may be bought in (stock_note)."
    )
    stock_pieces_ft: list[int] | None = Field(
        default=None,
        max_length=MAX_SPLICE_PIECES,
        description="The stock pieces ONE piece of the line is cut from (ft), "
        "longest first: [16] for one stock length, [12, 12] for a member "
        "spliced from two 12 ft pieces (longer than the longest stock); null "
        "with no stock.",
    )
    one_piece: bool = Field(
        default=False,
        exclude_if=_is_false,
        json_schema_extra=_drop_schema_default,
        description="True when each piece is one stock length, never spliced: "
        "a member that spans between bearings (a joist, rafter, header or "
        "beam) or a column (NO-SPLICE-SPANS). Omitted when false.",
    )
    stock_note: str | None = Field(
        default=None,
        exclude_if=is_none,
        max_length=160,
        description="Why a lumber line has no stock, when it is longer than "
        "any it may be bought in ('One piece, longer than 24 ft stock: a "
        "joist is not spliced'); absent otherwise.",
    )
    waste_mm: float | None = Field(
        description="Offcut of each piece from its stock (mm), a splice's "
        "pieces summed; null with no stock."
    )
    stock_quantity: int | None = Field(
        ge=0,
        description="Stock units bought for the line (the CSV's Stock qty): "
        "one per piece (until pieces are nested), a spliced piece's "
        "stock_pieces_ft counting as ONE set; for a sheet line, the sheets "
        "its panels are cut from (each panel a sheet unless an earlier "
        "offcut covers it whole); null with no stock length or sheet.",
    )
    unit_price_cents: int | None = Field(
        ge=0,
        description="Price of ONE stock unit (see stock_quantity) in the "
        "book's currency's cents: one stock piece, one splice set (its pieces "
        "summed, each rounded once) or one sheet. Null (blank, never 0) when "
        "the book has no price for the line or the line has no stock.",
    )
    price_unit: PriceUnit | None = Field(
        description="Which entry priced the line: 'each' for its stock "
        "length, else 'linear_foot', else 'board_foot'; null when unpriced."
    )
    extended_price_cents: int | None = Field(
        ge=0,
        description="unit_price_cents x stock_quantity, on every line, so a "
        "row multiplies out; null when unpriced.",
    )
    unit: OpeningKind | None = Field(
        default=None,
        description="A window or door unit line (OPENING-UNITS): 'window' or "
        "'door', its profile the call size ('3040'), one stock unit per "
        "piece, priced Each; null for lumber and sheets.",
    )
    unit_key: str | None = Field(
        default=None,
        description="A unit line's price-book key ('window_3040'); null for a "
        "custom size, or a line that is not a unit.",
    )
    item: FoundationItemKind | None = Field(
        default=None,
        description="A foundation line (SLAB): 'concrete' (its pours, by "
        "volume), 'rebar' (runs of one length, bought in 20 ft sticks: "
        "stock_quantity) or 'anchor_bolt' (Each). Null otherwise.",
    )
    volume_mm3: float | None = Field(
        default=None,
        ge=0,
        description="A concrete line's net volume (mm^3), measured; null otherwise.",
    )
    order_yd3: float | None = Field(
        default=None,
        ge=0,
        description="A concrete line's order (yd³): the net volume plus "
        "waste_percent, rounded up to 1/4 yd³; its unit price is per yd³ "
        "and its extended price that times this. Null otherwise.",
    )
    waste_percent: int | None = Field(
        default=None,
        ge=0,
        description="A concrete line's waste allowance (percent); null otherwise.",
    )


class CutListMissing(BaseModel):
    """A part the assembly still places but that was deleted: its pieces
    cannot be measured, so the list says so instead of dropping them."""

    ref_document_id: uuid.UUID
    quantity: int = Field(ge=1, description="Placements of the deleted part.")


class CutListResponse(BaseModel):
    """A part's or an assembly's cut list (``GET .../cut-list``)."""

    document_id: uuid.UUID
    document_kind: RefDocumentKind
    name: str
    length_unit: LengthUnit = Field(
        description="The document's display unit (the CSV is written in it)."
    )
    lines: list[CutListLine] = Field(default_factory=list[CutListLine])
    total_quantity: int = Field(ge=0, description="Sum of every line's quantity.")
    unclassified: int = Field(ge=0, description="How many pieces matched no profile.")
    missing: list[CutListMissing] = Field(
        default_factory=list[CutListMissing],
        description="Deleted parts an assembly still places: not measured, "
        "listed so the cut list is not silently short.",
    )
    currency: Currency = Field(description="The price book's ISO 4217 code.")
    total_price_cents: int | None = Field(
        ge=0,
        description="Sum of the priced lines' extended prices (cents); null "
        "when no line is priced.",
    )
    unpriced_lines: int = Field(
        ge=0,
        description="Lines with no price (no entry, or no stock length): the "
        "total leaves them out.",
    )


# --- classification -----------------------------------------------------------------


def lumber_for(profile: str | None) -> LumberProfile | None:
    """The library profile a metadata ``profile`` names, by key or nominal
    name (``us_2x10`` or ``2x10``), or ``None``."""
    if profile is None:
        return None
    for candidate in LUMBER_PROFILES:
        if profile in (candidate.key, candidate.name):
            return candidate
    return None


def _section_matches(a: float, b: float, profile: LumberProfile) -> bool:
    lo, hi = sorted((a, b))
    return (
        abs(lo - profile.thickness_mm) <= SECTION_TOLERANCE_MM
        and abs(hi - profile.width_mm) <= SECTION_TOLERANCE_MM
    )


def _split(
    extents: tuple[float, float, float], profile: LumberProfile
) -> tuple[float, tuple[float, float]] | None:
    """(length, section) when two of *extents* are *profile*'s section. The
    longest length wins (a 2x10 block shorter than 9.25 in still reads true)."""
    for i, j, k in permutations(range(3)):
        if j < k and _section_matches(extents[j], extents[k], profile):
            lo, hi = sorted((extents[j], extents[k]))
            return extents[i], (lo, hi)
    return None


def _is_prism(body: BodyExtent) -> bool:
    a, b, c = body.extents_mm
    box = a * b * c
    return box > 0 and abs(body.volume_mm3 - box) <= PRISM_TOLERANCE * box


def _covers(length_mm: float, feet: int) -> bool:
    return length_mm <= feet * MM_PER_FOOT + 1e-6


def stock_length_ft(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT
) -> int | None:
    """The shortest stock of *lengths* (ft, shortest first; every standard
    length by default) that covers *length_mm*, or ``None``."""
    for feet in lengths:
        if _covers(length_mm, feet):
            return feet
    return None


@lru_cache(maxsize=1024)
def _splice_tiers(
    length_mm: float, lengths: tuple[int, ...]
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Every 2 to :data:`MAX_SPLICE_PIECES`-piece splice of *lengths* that
    covers *length_mm*, in tiers (:func:`stock_splice_tiers`), whether or
    not one stock length covers it too."""
    tiers: dict[tuple[int, int], list[tuple[int, ...]]] = {}
    for pieces in range(2, MAX_SPLICE_PIECES + 1):
        for splice in combinations_with_replacement(
            sorted(lengths, reverse=True), pieces
        ):
            feet = sum(splice)
            if _covers(length_mm, feet):
                tiers.setdefault((pieces, feet), []).append(splice)
    return tuple(tuple(sorted(tiers[key], key=_evenness)) for key in sorted(tiers))


def _evenness(splice: tuple[int, ...]) -> tuple[int, ...]:
    """Sort key among equally good splices: the most even first (the longest
    shortest piece, then the shortest longest), then the longer pieces first,
    so 24 ft is 12 + 12, then 14 + 10, then 16 + 8."""
    return (-min(splice), max(splice), *(-feet for feet in splice))


def stock_splice_tiers(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Every splice that covers a member longer than the longest stock,
    grouped into tiers of equally good splices, the best tier first
    (RESEARCH §27).

    A framer splices a plate or rim longer than stock from stock pieces, the
    joints over studs or joists (Chief Architect's materials list buys it the
    same way). A splice is a combination of at most :data:`MAX_SPLICE_PIECES`
    stock pieces covering *length_mm*, each longest piece first; tiers are
    ordered by FEWEST PIECES (joints), then LEAST WASTE (the fewest feet
    bought), and within a tier most even first (:func:`_evenness`). Joints
    must land over a stud or joist and double top-plate joints be offset 24
    in (IRC R602.3.2), so a framer orders plates and rims in the longest
    lengths and cuts blocking from the offcut: 28 ft with 8, 10 and 16 ft
    stock is 2 x 16, not 10 + 10 + 8 (SPLICE-FEWEST-PIECES). The first tier
    is the choice (:func:`stock_splices`); the later ones let
    :func:`price_lines` buy what the book prices, as a yard quotes 28 ft as
    16 + 16 when it stocks no 14 ft. *lengths* are the stock lengths (ft)
    the member is sold in (every standard length by default). Empty for a
    member that one stock length covers, or that no splice covers."""
    if stock_length_ft(length_mm, lengths) is not None:
        return ()
    return _splice_tiers(length_mm, tuple(lengths))


def stock_splices(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT
) -> tuple[tuple[int, ...], ...]:
    """The equally good fewest-piece, least-waste splices for a member longer
    than the longest stock, best first: the first tier of
    :func:`stock_splice_tiers` (26 ft is 14 + 12, 16 + 10 or 18 + 8; 37 ft
    is 20 + 18). Empty for a member that one stock length covers, or that no
    splice covers."""
    tiers = stock_splice_tiers(length_mm, lengths)
    return tiers[0] if tiers else ()


def stock_pieces_ft(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT, *, splice: bool = True
) -> tuple[int, ...] | None:
    """The stock one member of *length_mm* is cut from: one stock length of
    *lengths*, else the best splice, or ``None`` when no splice covers it or
    the member may not be spliced (*splice* false, NO-SPLICE-SPANS)."""
    single = stock_length_ft(length_mm, lengths)
    if single is not None:
        return (single,)
    if not splice:
        return None
    splices = stock_splices(length_mm, lengths)
    return splices[0] if splices else None


def no_stock_note(member: str | None, lengths: Sequence[int], *, splice: bool) -> str:
    """Why a lumber piece has no stock (``stock_note``): a one-piece member
    past the longest stock, or any member past the longest splice."""
    longest = max(lengths)
    if not splice:
        what = (member or "member").lower()
        return f"One piece, longer than {longest} ft stock: a {what} is not spliced"
    return (
        f"Longer than {MAX_SPLICE_PIECES} x {longest} ft: no splice of stock covers it"
    )


def splice_label(pieces: Sequence[int]) -> str:
    """A member's stock as a framer writes it: ``16 ft``, ``2 x 12 ft``,
    ``14 ft + 12 ft``, ``2 x 20 ft + 8 ft`` (longest first), as the CSV writes it."""
    counts: dict[int, int] = {}
    for feet in sorted(pieces, reverse=True):
        counts[feet] = counts.get(feet, 0) + 1
    return " + ".join(
        f"{feet} ft" if n == 1 else f"{n} x {feet} ft" for feet, n in counts.items()
    )


@dataclass(frozen=True)
class CutListPiece:
    """One measured piece, before grouping (``count`` copies of it). A sheet
    panel carries its covering ``sheet`` (``None`` if none covers it) and its
    net ``area_mm2``; a stick of lumber has ``area_mm2`` ``None``."""

    member: str | None
    profile: str | None
    lumber: bool
    material: MaterialKey | None
    classification: CutListClassification
    length_mm: float
    section_mm: tuple[float, float]
    count: int = 1
    sheet: SheetSize | None = None
    area_mm2: float | None = None
    system: CutListSystem = "other"
    #: A window or door unit's body (OPENING-UNITS); ``None`` otherwise.
    unit: OpeningUnitPart | None = None
    #: One stock length, never spliced (:data:`ONE_PIECE_ROLES`).
    one_piece: bool = False
    #: A panel that keeps the sheet's strength axis (:data:`GRAIN_LOCKED_ROLES`).
    keep_grain: bool = False
    #: A grain-locked panel's face as ``(across its supports, along them)``
    #: (mm), the side that must lie along the sheet's length first
    #: (:func:`_across_along`); ``None`` for every other piece.
    grain_mm: tuple[float, float] | None = None
    #: A foundation item (SLAB): a pour, a rebar run or anchor bolts.
    item: FoundationItemKind | None = None
    #: A pour's measured volume (mm^3) and waste allowance (percent).
    volume_mm3: float | None = None
    waste_percent: int | None = None
    #: A rebar run is a closed loop.
    closed: bool = False

    @property
    def panel(self) -> bool:
        return self.area_mm2 is not None


def _material(
    body_id: uuid.UUID,
    metadata: MemberMetadata | None,
    materials: MaterialAssignment | None,
) -> MaterialKey | None:
    if materials is not None:
        for override in materials.bodies:
            if override.base_feature_id == body_id:
                return override.material
    if metadata is not None and metadata.material is not None:
        return metadata.material
    return None if materials is None else materials.default_material


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _across_along(body: BodyExtent, joist_axis: Vec3 | None) -> tuple[float, float]:
    """A floor panel's face as ``(across the joists, along them)`` (mm).

    The side across the joists is the face axis more nearly perpendicular to
    the part's joists (*joist_axis*, a joist's length direction), as measured
    by geometry (:attr:`BodyExtent.axes`). With no joist in the part, no
    axes, or a face axis no nearer perpendicular than the other, the longer
    side is taken as across, as the floor plugin lays its full panels."""
    long, short = body.extents_mm[0], body.extents_mm[1]
    if joist_axis is None or body.axes is None:
        return long, short
    first, second = (abs(_dot(axis, joist_axis)) for axis in body.axes[:2])
    if abs(first - second) <= 1e-6:
        return long, short
    return (long, short) if first < second else (short, long)


def classify_body(
    body: BodyExtent,
    member: CutListMember | None,
    materials: MaterialAssignment | None,
    count: int = 1,
    joist_axis: Vec3 | None = None,
) -> CutListPiece:
    """One body as a cut-list piece (module docstring). *joist_axis* is the
    length direction of the part's joists, which orients a floor panel
    (:func:`_across_along`)."""
    extents = body.extents_mm
    metadata = member.metadata if member is not None else None
    material = _material(body.base_feature_id, metadata, materials)
    default_section = (min(extents[1], extents[2]), max(extents[1], extents[2]))
    if member is not None and member.metadata.unit is not None:
        # A bought unit: listed by its kind and call size, measured as it is.
        unit = member.metadata.unit
        return CutListPiece(
            member=unit.kind.capitalize(),
            profile=member.metadata.profile,
            lumber=False,
            material=material,
            classification="member",
            length_mm=extents[0],
            section_mm=default_section,
            count=count,
            unit=unit,
            system=system_for_plugin(member.plugin_id),
        )
    if member is not None and member.metadata.concrete is not None:
        # A pour: listed by its measured volume (module docstring).
        pour = member.metadata.concrete
        return CutListPiece(
            member=member.title,
            profile=FOUNDATION_ITEMS_BY_KEY[pour.item].name,
            lumber=False,
            material=material,
            classification="member",
            length_mm=extents[0],
            section_mm=default_section,
            count=count,
            system=system_for_plugin(member.plugin_id),
            item="concrete",
            volume_mm3=body.volume_mm3,
            waste_percent=pour.waste_percent,
        )
    if member is not None:
        good = sheet_good_for(member.metadata.profile)
        if good is not None:
            # A panel: its thinnest extent through it, the other two its face.
            thickness = extents[2]
            keep = member.role in GRAIN_LOCKED_ROLES
            return CutListPiece(
                member=member.title,
                profile=good.name,
                lumber=False,
                material=material,
                classification="member",
                length_mm=extents[0],
                section_mm=(thickness, extents[1]),
                count=count,
                sheet=covering_sheet(extents[0], extents[1], good),
                area_mm2=body.volume_mm3 / thickness if thickness > 0 else 0.0,
                system=sheet_system(good.material),
                keep_grain=keep,
                grain_mm=_across_along(body, joist_axis) if keep else None,
            )
        lumber = lumber_for(member.metadata.profile)
        split = None if lumber is None else _split(extents, lumber)
        length, section = split if split is not None else (extents[0], default_section)
        return CutListPiece(
            member=member.title,
            profile=lumber.name if lumber is not None else member.metadata.profile,
            lumber=lumber is not None,
            material=material,
            classification="member",
            length_mm=length,
            section_mm=section,
            count=count,
            system=system_for_plugin(member.plugin_id),
            one_piece=member.role in ONE_PIECE_ROLES,
        )
    if _is_prism(body):
        for lumber in LUMBER_PROFILES:
            split = _split(extents, lumber)
            if split is not None:
                return CutListPiece(
                    member=None,
                    profile=lumber.name,
                    lumber=True,
                    material=material,
                    classification="matched",
                    length_mm=split[0],
                    section_mm=split[1],
                    count=count,
                )
    return CutListPiece(
        member=None,
        profile=None,
        lumber=False,
        material=material,
        classification="unclassified",
        length_mm=extents[0],
        section_mm=default_section,
        count=count,
    )


def listed_pieces(
    piece: CutListPiece, member: CutListMember | None
) -> list[CutListPiece]:
    """The items *member*'s body carries but does not draw (SLAB): a pour's
    rebar runs and a plate's anchor bolts, counted from *piece*, the body as
    measured. Listed under Foundation, after the body."""
    if member is None:
        return []
    metadata = member.metadata
    out: list[CutListPiece] = []
    for run in metadata.rebar or ():
        item = FOUNDATION_ITEMS_BY_KEY[run.item]
        out.append(
            CutListPiece(
                member="Rebar",
                profile=item.name,
                lumber=False,
                material=item.material,
                classification="member",
                length_mm=run.length_mm,
                section_mm=(0.0, 0.0),
                count=piece.count,
                system="foundation",
                item="rebar",
                closed=run.closed,
            )
        )
    if metadata.anchor_bolts is not None:
        item = FOUNDATION_ITEMS_BY_KEY[metadata.anchor_bolts.item]
        bolts = anchor_bolt_count(piece.length_mm / MM_PER_INCH)
        out.append(
            CutListPiece(
                member="Anchor bolt",
                profile=item.name,
                lumber=False,
                material=item.material,
                classification="member",
                length_mm=0.0,
                section_mm=(0.0, 0.0),
                count=piece.count * bolts,
                system="foundation",
                item="anchor_bolt",
            )
        )
    return out


def part_pieces(
    extents: BodyExtentsResult,
    members: Iterable[CutListMember],
    materials: MaterialAssignment | None,
    count: int = 1,
) -> list[CutListPiece]:
    """Every body of one part as pieces, in tree order (*count* of each),
    each followed by the items it lists but does not draw. The part's first
    joist with measured axes orients its floor panels (SUBFLOOR-GRAIN)."""
    by_id = {member.feature_id: member for member in members}
    joist_axis: Vec3 | None = None
    for body in extents.bodies:
        member = by_id.get(body.base_feature_id)
        if member is not None and member.role == "joist" and body.axes is not None:
            joist_axis = body.axes[0]
            break
    out: list[CutListPiece] = []
    for body in extents.bodies:
        member = by_id.get(body.base_feature_id)
        piece = classify_body(body, member, materials, count, joist_axis)
        out.append(piece)
        out.extend(listed_pieces(piece, member))
    return out


def _sheet_line(pieces: Sequence[CutListPiece], quantity: int) -> CutListLine:
    """Panels of one product, material and sheet as one line: their net area,
    the sheets they are cut from and the offcut (module docstring)."""
    first = pieces[0]
    members: list[str] = []
    for piece in pieces:
        if piece.member is not None and piece.member not in members:
            members.append(piece.member)
    area = sum((p.area_mm2 or 0.0) * p.count for p in pieces)
    sheet = first.sheet
    thickness = round(first.section_mm[0], 6)
    good = sheet_good_for(first.profile)
    if sheet is None:
        length = round(max(p.length_mm for p in pieces), 6)
        width = round(max(p.section_mm[1] for p in pieces), 6)
        sheets = None
        offcut = None
    elif good is not None and good.material == "gypsum":
        # By area, less an ulp (BACKLOG INTERIOR-WALLS-GYPSUM-COUNT).
        length, width = round(sheet.length_mm, 6), round(sheet.width_mm, 6)
        sheets = math.ceil(area / sheet.area_mm2 - 1e-9)
        offcut = round(max(sheets * sheet.area_mm2 - area, 0.0), 6)
    else:
        length, width = round(sheet.length_mm, 6), round(sheet.width_mm, 6)
        sheets = sheets_to_cut(
            (
                p.grain_mm or (p.length_mm, p.section_mm[1])
                for p in pieces
                for _ in range(p.count)
            ),
            sheet,
            turn=not any(p.keep_grain for p in pieces),
        )
        offcut = round(max(sheets * sheet.area_mm2 - area, 0.0), 6)
    return CutListLine(
        system="sheathing" if good is None else sheet_system(good.material),
        member=", ".join(members) or None,
        profile=first.profile,
        material=first.material,
        classification=first.classification,
        quantity=quantity,
        length_mm=length,
        total_length_mm=round(length * (sheets or 0), 6),
        section_mm=[thickness, width],
        sheet=None if sheet is None else sheet.key,
        area_mm2=round(area, 6),
        offcut_area_mm2=offcut,
        stock_length_ft=None,
        waste_mm=None,
        stock_quantity=sheets,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
    )


def _members_of(pieces: Sequence[CutListPiece]) -> str | None:
    members: list[str] = []
    for piece in pieces:
        if piece.member is not None and piece.member not in members:
            members.append(piece.member)
    return ", ".join(members) or None


def _concrete_line(pieces: Sequence[CutListPiece], quantity: int) -> CutListLine:
    """Pours of one product, material and allowance as one line: their
    measured volume, and the cubic yards that orders (module docstring)."""
    first = pieces[0]
    volume = sum((p.volume_mm3 or 0.0) * p.count for p in pieces)
    waste = first.waste_percent or 0
    length = round(max(p.length_mm for p in pieces), 6)
    return CutListLine(
        system=first.system,
        member=_members_of(pieces),
        profile=first.profile,
        material=first.material,
        classification=first.classification,
        quantity=quantity,
        length_mm=length,
        total_length_mm=round(sum(p.length_mm * p.count for p in pieces), 6),
        section_mm=[round(v, 6) for v in first.section_mm],
        stock_length_ft=None,
        waste_mm=None,
        stock_quantity=None,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        item="concrete",
        volume_mm3=round(volume, 6),
        order_yd3=float(concrete_order_yd3(volume, waste)),
        waste_percent=waste,
    )


#: The stick a rebar line is bought in (ft).
_REBAR_STICK_FT: Final = FOUNDATION_ITEMS_BY_KEY["rebar_4"].stock_length_ft


def _item_line(piece: CutListPiece, quantity: int) -> CutListLine:
    """Rebar runs of one length, bought in 20 ft sticks (each run lapped
    on its own), or anchor bolts, Each."""
    length = round(piece.length_mm, 6)
    rebar = piece.item == "rebar"
    sticks = (
        rebar_sticks(length / MM_PER_INCH, piece.closed) * quantity
        if rebar
        else quantity
    )
    return CutListLine(
        system=piece.system,
        member=piece.member,
        profile=piece.profile,
        material=piece.material,
        classification=piece.classification,
        quantity=quantity,
        length_mm=length,
        total_length_mm=round(length * quantity, 6),
        section_mm=[0.0, 0.0],
        stock_length_ft=_REBAR_STICK_FT if rebar else None,
        waste_mm=None,
        stock_quantity=sticks,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        item=piece.item,
    )


def _first_seen(order: dict[tuple[object, ...], int], key: tuple[object, ...]) -> int:
    return order.setdefault(key, len(order))


def order_lines(lines: Sequence[CutListLine]) -> list[CutListLine]:
    """*lines* (in the order each first appeared) by system, then member,
    profile and material in first-appearance order within it, then length,
    shortest first (module docstring, **Order**). Stable, so lines with equal
    keys keep the tree order."""
    seen: dict[tuple[object, ...], int] = {}
    keys: list[tuple[int, int, int, int, float]] = []
    for line in lines:
        system = line.system
        member = _first_seen(seen, ("member", system, line.member))
        profile = _first_seen(seen, ("profile", system, line.member, line.profile))
        material = _first_seen(
            seen, ("material", system, line.member, line.profile, line.material)
        )
        length = (
            0.0
            if line.area_mm2 is not None or line.item in ("concrete", "anchor_bolt")
            else line.length_mm
        )
        keys.append((SYSTEM_ORDER.index(system), member, profile, material, length))
    return [lines[i] for i in sorted(range(len(lines)), key=keys.__getitem__)]


def _unit_line(
    piece: CutListPiece, unit: OpeningUnitPart, quantity: int
) -> CutListLine:
    """Units of one kind, size and material as one Each line: one stock unit
    per unit, its measured extents as its size."""
    length = round(piece.length_mm, 6)
    thickness, width = (round(v, 6) for v in piece.section_mm)
    return CutListLine(
        system=piece.system,
        member=piece.member,
        profile=piece.profile,
        material=piece.material,
        classification=piece.classification,
        quantity=quantity,
        length_mm=length,
        total_length_mm=round(length * quantity, 6),
        section_mm=[thickness, width],
        stock_length_ft=None,
        waste_mm=None,
        stock_quantity=quantity,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        unit=unit.kind,
        unit_key=unit.key,
    )


def group_pieces(pieces: Iterable[CutListPiece]) -> list[CutListLine]:
    """Pieces grouped by system, member, profile, material and length; sheet
    panels by product, material and sheet. Ordered by system, then member,
    profile and material as each first appears in the tree, then length
    (:func:`order_lines`)."""
    groups: dict[tuple[object, ...], tuple[CutListPiece, int]] = {}
    panels: dict[tuple[object, ...], list[CutListPiece]] = {}
    pours: dict[tuple[object, ...], list[CutListPiece]] = {}
    for piece in pieces:
        if piece.item is not None:
            item_key: tuple[object, ...] = (
                "item",
                piece.item,
                piece.system,
                piece.profile,
                piece.material,
            )
            if piece.item == "concrete":
                item_key += (piece.waste_percent,)
                pours.setdefault(item_key, []).append(piece)
            elif piece.item == "rebar":
                item_key += (round(piece.length_mm, LENGTH_DECIMALS), piece.closed)
            first, count = groups.get(item_key, (piece, 0))
            groups[item_key] = (first, count + piece.count)
            continue
        if piece.unit is not None:
            if not piece.unit.counted:
                continue  # the unit is listed on its counted body
            unit_key: tuple[object, ...] = (
                "unit",
                piece.system,
                piece.unit.kind,
                piece.unit.key,
                piece.profile,
                piece.material,
            )
            first, count = groups.get(unit_key, (piece, 0))
            groups[unit_key] = (first, count + piece.count)
            continue
        if piece.panel:
            panel_key: tuple[object, ...] = (
                "sheet",
                piece.profile,
                piece.material,
                None if piece.sheet is None else piece.sheet.key,
                piece.keep_grain,
            )
            panels.setdefault(panel_key, []).append(piece)
            first, count = groups.get(panel_key, (piece, 0))
            groups[panel_key] = (first, count + piece.count)
            continue
        key: tuple[object, ...] = (
            piece.system,
            piece.member,
            piece.profile,
            piece.material,
            piece.classification,
            round(piece.length_mm, LENGTH_DECIMALS),
            piece.one_piece,
        )
        if piece.classification == "unclassified":
            key += tuple(round(v, LENGTH_DECIMALS) for v in piece.section_mm)
        first, count = groups.get(key, (piece, 0))
        groups[key] = (first, count + piece.count)
    lines: list[CutListLine] = []
    for group_key, (piece, quantity) in groups.items():
        if piece.item == "concrete":
            lines.append(_concrete_line(pours[group_key], quantity))
            continue
        if piece.item is not None:
            lines.append(_item_line(piece, quantity))
            continue
        if piece.panel:
            lines.append(_sheet_line(panels[group_key], quantity))
            continue
        if piece.unit is not None:
            lines.append(_unit_line(piece, piece.unit, quantity))
            continue
        length = round(piece.length_mm, 6)
        lengths = stock_lengths_ft(lumber_for(piece.profile))
        stock = (
            stock_pieces_ft(length, lengths, splice=not piece.one_piece)
            if piece.lumber
            else None
        )
        note = (
            no_stock_note(piece.member, lengths, splice=not piece.one_piece)
            if piece.lumber and stock is None
            else None
        )
        thickness, width = (round(v, 6) for v in piece.section_mm)
        # max(0.0, ...): never -0.0, as a stock exactly the length rounds to.
        waste = (
            None
            if stock is None
            else max(0.0, round(sum(stock) * MM_PER_FOOT - length, 6))
        )
        lines.append(
            CutListLine(
                system=piece.system,
                member=piece.member,
                profile=piece.profile,
                material=piece.material,
                classification=piece.classification,
                quantity=quantity,
                length_mm=length,
                total_length_mm=round(length * quantity, 6),
                section_mm=[thickness, width],
                stock_length_ft=(
                    stock[0] if stock is not None and len(stock) == 1 else None
                ),
                stock_pieces_ft=None if stock is None else list(stock),
                one_piece=piece.one_piece,
                stock_note=note,
                waste_mm=waste,
                stock_quantity=None if stock is None else quantity,
                unit_price_cents=None,
                price_unit=None,
                extended_price_cents=None,
            )
        )
    return order_lines(lines)


# --- prices (PRICE-BOOK) ------------------------------------------------------------


def nominal_size_in(profile: LumberProfile) -> tuple[Fraction, Fraction]:
    """A profile's NOMINAL thickness and width (in), exactly, from its name as
    sold: ``2x4`` is (2, 4), ``5/4x6`` is (5/4, 6). Board feet are counted on
    the nominal size, as yards sell them."""
    thickness, width = profile.name.split("x")
    return Fraction(thickness), Fraction(width)


def _round_half_up(value: Fraction) -> int:
    """*value* (cents, non-negative) to a whole cent, half up, as an invoice."""
    return math.floor(value + Fraction(1, 2))


def stock_piece_price(
    entry: PriceBookEntry, profile: LumberProfile, stock_length_ft: int
) -> int:
    """The price (cents) of ONE stock piece of *stock_length_ft* under *entry*,
    rounded once per piece: per foot x feet, or per board foot x nominal
    thickness x width x feet / 12."""
    if entry.unit == "each":
        return entry.price_cents
    if entry.unit == "linear_foot":
        return entry.price_cents * stock_length_ft
    thickness, width = nominal_size_in(profile)
    board_feet = thickness * width * stock_length_ft / 12
    return _round_half_up(board_feet * entry.price_cents)


#: Which unit wins when the book prices a line more than one way (lumber).
PRICE_PRECEDENCE: Final[tuple[PriceUnit, ...]] = ("each", "linear_foot", "board_foot")


def _price_stock(
    entries: Mapping[PriceKey, PriceBookEntry],
    material: MaterialKey,
    lumber: LumberProfile,
    options: Sequence[tuple[int, ...]],
) -> tuple[int, PriceUnit, tuple[int, ...]] | None:
    """The price (cents) of one member's stock, the unit that priced it and
    the stock it prices, from the equally good *options* (one stock length,
    or the tied splices, best first). Each prices a splice whose every piece
    has an 'each' entry, the cheapest such (ties: the first); else a per-foot
    entry prices the feet bought, else a per-board-foot entry, both on the
    first option. One unit per line; each piece rounded once."""

    def entry(unit: PriceUnit, feet: int | None) -> PriceBookEntry | None:
        return entries.get((material, lumber.key, unit, feet, None))

    best: tuple[int, int] | None = None
    for index, stock in enumerate(options):
        found = [entry("each", feet) for feet in stock]
        if all(e is not None for e in found):
            cents = sum(e.price_cents for e in found if e is not None)
            if best is None or (cents, index) < best:
                best = (cents, index)
    if best is not None:
        return best[0], "each", options[best[1]]
    for unit in PRICE_PRECEDENCE[1:]:
        found_entry = entry(unit, None)
        if found_entry is not None:
            stock = options[0]
            cents = sum(stock_piece_price(found_entry, lumber, ft) for ft in stock)
            return cents, unit, stock
    return None


def _stock_tiers(
    line: CutListLine, lengths: Sequence[int]
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """The stock a yard may sell one member of *line* as, in tiers of equally
    good options, the line's own choice first. A length not every yard
    stocks (18, 22 or 24 ft) falls to the next longer, up to the first that
    every yard does (:data:`~loft_wire.lumber.COMMON_STOCK_LENGTHS_FT`): a
    yard with no 18 ft quotes 20 ft, what Loft bought before it listed
    18 ft. A common length stands alone, so a 12 ft line the book does not
    price stays blank (its blank asks for the price) rather than buy 16 ft.
    Then, for a member that may splice and is longer than the
    :data:`~loft_wire.lumber.COMMON_MAX_STOCK_FT` every yard stocks, every
    splice tier (:func:`stock_splice_tiers`), so a 24 ft plate is 16 + 8 at
    a yard with no 24 ft. A one-piece member is never spliced."""
    tiers: list[tuple[tuple[int, ...], ...]] = []
    for feet in lengths:
        if _covers(line.length_mm, feet):
            tiers.append(((feet,),))
            if feet in COMMON_STOCK_LENGTHS_FT:
                break
    if not line.one_piece and not _covers(line.length_mm, COMMON_MAX_STOCK_FT):
        tiers.extend(_splice_tiers(line.length_mm, tuple(lengths)))
    return tuple(tiers)


def price_lines(
    lines: Sequence[CutListLine], book: PriceBookResponse
) -> list[CutListLine]:
    """*lines* priced from *book*, on the stock pieces bought: each line's
    unit price is an 'each' entry for its stock length (for a spliced line,
    for every piece of a splice, :func:`_price_stock`), from the first tier
    of :func:`_stock_tiers` (its own stock, past 18, 22 or 24 ft a longer
    single length, then for a member that may splice, the fewest pieces,
    then least waste) the book
    prices, its offcut recomputed, else a per-foot entry
    on the feet bought, else a per-board-foot entry (for its material and
    profile), and its extended price is that times its stock quantity (one
    per piece, a splice set counting once), so the offcut is paid for. A
    sheet line is priced by the 'each' entry for its product and sheet,
    times its sheets, and a unit line by the 'each' entry for its unit key
    and material, times its units. A foundation line (SLAB) is priced by its
    item's entry: concrete per cubic yard times the yards ordered, a rebar
    line Each per 20 ft stick times its sticks, anchor bolts Each. A line
    with no stock or no entry stays unpriced (null)."""
    entries = {entry.key: entry for entry in book.entries}
    priced: list[CutListLine] = []
    for line in lines:
        lumber = lumber_for(line.profile)
        good = sheet_good_for(line.profile)
        stock = line.stock_pieces_ft
        quantity = line.stock_quantity
        unit_price: int | None = None
        unit: PriceUnit | None = None
        update: dict[str, object] = {}
        item = foundation_item_for(line.profile) if line.item is not None else None
        if item is not None:
            if line.material is not None:
                key = (line.material, item.key, item.price_unit)
                entry = entries.get((*key, item.stock_length_ft, None))
                if entry is not None:
                    unit_price, unit = entry.price_cents, entry.unit
        elif line.unit is not None:
            if line.unit_key is not None and line.material is not None:
                entry = entries.get((line.material, line.unit_key, "each", None, None))
                if entry is not None:
                    unit_price, unit = entry.price_cents, "each"
        elif (
            good is not None
            and line.sheet is not None
            and line.material is not None
            and quantity is not None
        ):
            entry = entries.get((line.material, good.key, "each", None, line.sheet))
            if entry is not None:
                unit_price, unit = entry.price_cents, "each"
        elif (
            lumber is not None
            and line.material is not None
            and stock
            and quantity is not None
        ):
            tiers = _stock_tiers(line, stock_lengths_ft(lumber))
            if not tiers or tuple(stock) not in tiers[0]:
                tiers = ((tuple(stock),),)
            found = None
            for options in tiers:
                found = _price_stock(entries, line.material, lumber, options)
                if found is not None:
                    break
            if found is not None:
                unit_price, unit, bought = found
                update["stock_pieces_ft"] = list(bought)
                # The stock shown is the stock bought: an 18 ft line priced
                # at 20 ft reads 20 ft, a 24 ft line spliced 16 + 8 none.
                update["stock_length_ft"] = bought[0] if len(bought) == 1 else None
                update["waste_mm"] = max(
                    0.0, round(sum(bought) * MM_PER_FOOT - line.length_mm, 6)
                )
        priced.append(
            line.model_copy(
                update={
                    **update,
                    "unit_price_cents": unit_price,
                    "price_unit": unit,
                    "extended_price_cents": _extended(line, unit_price, quantity),
                }
            )
        )
    return priced


def _extended(
    line: CutListLine, unit_price: int | None, quantity: int | None
) -> int | None:
    """Unit price x stock quantity; for concrete, x the cubic yards ORDERED
    (a multiple of 1/4, so exact), rounded once, half up."""
    if unit_price is None:
        return None
    if line.item == "concrete":
        if line.order_yd3 is None:
            return None
        return _round_half_up(Fraction(line.order_yd3) * unit_price)
    return None if quantity is None else unit_price * quantity


def cut_list_response(
    *,
    document_id: uuid.UUID,
    document_kind: RefDocumentKind,
    name: str,
    length_unit: LengthUnit,
    pieces: Sequence[CutListPiece],
    missing: Sequence[CutListMissing] = (),
    price_book: PriceBookResponse = EMPTY_PRICE_BOOK,
) -> CutListResponse:
    """The grouped response for *pieces* (and an assembly's deleted parts),
    priced from *price_book* (an assembly's list is one grouped list across
    its parts, so its total is the sum of its lines)."""
    lines = price_lines(group_pieces(pieces), price_book)
    extended = [
        line.extended_price_cents
        for line in lines
        if line.extended_price_cents is not None
    ]
    return CutListResponse(
        document_id=document_id,
        document_kind=document_kind,
        name=name,
        length_unit=length_unit,
        lines=lines,
        total_quantity=sum(line.quantity for line in lines),
        unclassified=sum(
            line.quantity for line in lines if line.classification == "unclassified"
        ),
        missing=list(missing),
        currency=price_book.currency,
        total_price_cents=sum(extended) if extended else None,
        unpriced_lines=len(lines) - len(extended),
    )
