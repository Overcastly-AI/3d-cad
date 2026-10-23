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
lumber lengths :data:`STOCK_LENGTHS_FT`; the shortest that covers the member
is suggested, with the offcut it leaves. A member longer than the longest
stock is SPLICED from stock pieces, as a framer buys a long plate
(:func:`stock_splices`, RESEARCH §27): the pieces covering it in the fewest
pieces (joints), then with the least waste; when pricing, the first such
splice whose every piece the book prices, as a yard quotes it. A member no
:data:`MAX_SPLICE_PIECES`-piece splice covers, or one that is not lumber,
has no stock suggestion.

**Sheet goods** (SHEATHING): a member whose ``profile`` names a sheet product
(:mod:`loft_wire.sheet_goods`, "7/16 OSB") is a PANEL. Its thickness is its
smallest measured extent and its net area its volume over that thickness
(openings cut out), and it is cut from the shortest sheet covering its other
two extents. Panels group by product, material and sheet (not by member or
size), and a line buys the sheets its panels are CUT from, as a yard sells
whole sheets (:func:`sheets_to_cut`, SHEET-COUNT-PIECES): each panel takes a
sheet unless an earlier offcut of the line covers it whole, largest panels
first, a saw kerf (:data:`SHEET_KERF_MM`) lost at every cut (SHEET-KERF). A
floor panel keeps the sheet's strength axis across the joists, so it is never
turned to fit an offcut (SUBFLOOR-GRAIN); a wall panel may be. Openings are
not credited (framers sheathe over them and cut them out), so a line's
offcut area is its sheets' area less its net area.

**Order** (CUT-LIST-PANEL): lines are grouped by SYSTEM, as Chief
Architect's Materials List groups by category: Floor, Walls (with their doors
and windows), Roof, Sheathing (every sheet good), then Deck, Frame and Other.
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

Prices (PRICE-BOOK, RESEARCH §27) come from the user's
:mod:`loft_wire.price_book`: each line is priced on the stock pieces bought
(:func:`price_lines`), in integer cents, and a line the book does not price
stays null (blank, never $0); the response totals the priced lines and counts
the rest.

This module is pure (no I/O, no kernel): the gateway assembles the cut list
with it, and the B1 acceptance test calls it on geometry's measurements.
"""

import csv
import io
import math
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import combinations_with_replacement, permutations
from typing import Final, Literal

from pydantic import BaseModel, Field

from loft_wire.assemblies import RefDocumentKind
from loft_wire.features import EvaluateTreeRequest
from loft_wire.lumber import (
    LUMBER_PROFILES,
    MM_PER_INCH,
    STOCK_LENGTHS_FT,
    LumberProfile,
)
from loft_wire.materials import (
    MATERIALS_BY_KEY,
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
    SHEET_FIT_TOLERANCE_MM,
    SheetSize,
    SheetSizeKey,
    covering_sheet,
    sheet_good_for,
)
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

#: The most stock pieces one member is spliced from: 5 x 20 ft covers 100 ft.
#: A longer member (a modelling slip more often than a real plate) has no
#: stock, so it is listed and left unpriced, never guessed at.
MAX_SPLICE_PIECES: Final = 5

#: Sheet-good roles whose panels keep the sheet's strength axis (its length)
#: across their supports, so the count never turns one to fit an offcut
#: (SUBFLOOR-GRAIN: APA lays floor panels strength axis across the joists).
#: Wall sheathing may run either way, so its panels may turn.
GRAIN_LOCKED_ROLES: Final[frozenset[str]] = frozenset({"subfloor"})

#: The saw kerf lost at every cut of a sheet (mm): 1/8 in, a circular saw's
#: or panel saw's blade (SHEET-KERF). Two 24 in rips do not come from one
#: 48 in sheet, nor two 48 in halves from one 96 in sheet.
SHEET_KERF_MM: Final = 0.125 * MM_PER_INCH


#: How a piece was identified: from a plugin member's metadata, by matching
#: its section to a library profile, or not at all.
CutListClassification = Literal["member", "matched", "unclassified"]

#: The system a line belongs to (CUT-LIST-PANEL), in the order the list is
#: grouped: a materials list's categories.
CutListSystem = Literal["floor", "walls", "roof", "sheathing", "deck", "frame", "other"]

#: :data:`CutListSystem` in list order.
SYSTEM_ORDER: Final[tuple[CutListSystem, ...]] = (
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
    "loft.floor": "floor",
    "loft.wall": "walls",
    "loft.window": "walls",
    "loft.door": "walls",
    "loft.roof": "roof",
    "loft.deck": "deck",
    "loft.timber_frame": "frame",
}


def system_for_plugin(plugin_id: str | None) -> CutListSystem:
    """The system a plugin's members are listed under (:data:`PLUGIN_SYSTEMS`)."""
    return "other" if plugin_id is None else PLUGIN_SYSTEMS.get(plugin_id, "other")


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
        "Sheathing, ...): its members' plugin's system; every sheet good is "
        "'sheathing'; a body that is no plugin member is 'other'."
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
        description="A sheet line's sheet ('4x8', '4x9', '4x10'): the "
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
        "is longer than any splice covers."
    )
    stock_pieces_ft: list[int] | None = Field(
        default=None,
        max_length=MAX_SPLICE_PIECES,
        description="The stock pieces ONE piece of the line is cut from (ft), "
        "longest first: [16] for one stock length, [12, 12] for a member "
        "spliced from two 12 ft pieces (longer than the longest stock); null "
        "with no stock.",
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


def stock_length_ft(length_mm: float) -> int | None:
    """The shortest standard stock (ft) that covers *length_mm*, or ``None``."""
    for feet in STOCK_LENGTHS_FT:
        if _covers(length_mm, feet):
            return feet
    return None


def _evenness(splice: tuple[int, ...]) -> tuple[int, ...]:
    """Sort key among equally good splices: the most even first (the longest
    shortest piece, then the shortest longest), then the longer pieces first,
    so 24 ft is 12 + 12, then 14 + 10, then 16 + 8."""
    return (-min(splice), max(splice), *(-feet for feet in splice))


@lru_cache(maxsize=1024)
def stock_splice_tiers(length_mm: float) -> tuple[tuple[tuple[int, ...], ...], ...]:
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
    16 + 16 when it stocks no 14 ft. Empty for a member that one stock
    length covers, or that no splice covers."""
    if stock_length_ft(length_mm) is not None:
        return ()
    tiers: dict[tuple[int, int], list[tuple[int, ...]]] = {}
    for pieces in range(2, MAX_SPLICE_PIECES + 1):
        for splice in combinations_with_replacement(
            sorted(STOCK_LENGTHS_FT, reverse=True), pieces
        ):
            feet = sum(splice)
            if _covers(length_mm, feet):
                tiers.setdefault((pieces, feet), []).append(splice)
    return tuple(tuple(sorted(tiers[key], key=_evenness)) for key in sorted(tiers))


def stock_splices(length_mm: float) -> tuple[tuple[int, ...], ...]:
    """The equally good fewest-piece, least-waste splices for a member longer
    than the longest stock, best first: the first tier of
    :func:`stock_splice_tiers` (24 ft is 12 + 12, 14 + 10 or 16 + 8; 37 ft is
    2 x 20). Empty for a member that one stock
    length covers, or that no splice covers."""
    tiers = stock_splice_tiers(length_mm)
    return tiers[0] if tiers else ()


def stock_pieces_ft(length_mm: float) -> tuple[int, ...] | None:
    """The stock one member of *length_mm* is cut from: one stock length, the
    best splice, or ``None`` when no splice covers it."""
    single = stock_length_ft(length_mm)
    if single is not None:
        return (single,)
    splices = stock_splices(length_mm)
    return splices[0] if splices else None


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
    #: A panel that keeps the sheet's strength axis (:data:`GRAIN_LOCKED_ROLES`).
    keep_grain: bool = False

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


def classify_body(
    body: BodyExtent,
    member: CutListMember | None,
    materials: MaterialAssignment | None,
    count: int = 1,
) -> CutListPiece:
    """One body as a cut-list piece (module docstring)."""
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
    if member is not None:
        good = sheet_good_for(member.metadata.profile)
        if good is not None:
            # A panel: its thinnest extent through it, the other two its face.
            thickness = extents[2]
            return CutListPiece(
                member=member.title,
                profile=good.name,
                lumber=False,
                material=material,
                classification="member",
                length_mm=extents[0],
                section_mm=(thickness, extents[1]),
                count=count,
                sheet=covering_sheet(extents[0], extents[1]),
                area_mm2=body.volume_mm3 / thickness if thickness > 0 else 0.0,
                system="sheathing",
                keep_grain=member.role in GRAIN_LOCKED_ROLES,
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


def part_pieces(
    extents: BodyExtentsResult,
    members: Iterable[CutListMember],
    materials: MaterialAssignment | None,
    count: int = 1,
) -> list[CutListPiece]:
    """Every body of one part as pieces, in tree order (*count* of each)."""
    by_id = {member.feature_id: member for member in members}
    return [
        classify_body(body, by_id.get(body.base_feature_id), materials, count)
        for body in extents.bodies
    ]


Rect = tuple[float, float]


def _fits(panel: Rect, rect: Rect) -> bool:
    """Whether a ``(long, short)`` *panel* is cut whole from *rect*."""
    return (
        panel[0] <= rect[0] + SHEET_FIT_TOLERANCE_MM
        and panel[1] <= rect[1] + SHEET_FIT_TOLERANCE_MM
    )


def _leftovers(rect: Rect, panel: Rect, *, turn: bool) -> list[Rect]:
    """What is left of *rect* once *panel* is cut from its corner, long side
    along *rect*'s first side, a kerf (:data:`SHEET_KERF_MM`) lost at each
    cut: the RIP the full length beside it, then the END across the panel's
    width; slivers dropped. With *turn*, each is ``(long, short)``, so a
    later panel may lie either way in it; without, each keeps the sheet's
    frame, ``(along its length, along its width)``, so no panel turns."""
    out: list[Rect] = []
    rip = (rect[0], rect[1] - panel[1] - SHEET_KERF_MM)
    end = (rect[0] - panel[0] - SHEET_KERF_MM, panel[1])
    for a, b in (rip, end):
        if min(a, b) > SHEET_FIT_TOLERANCE_MM:
            out.append((max(a, b), min(a, b)) if turn else (a, b))
    return out


def sheets_to_cut(
    panels: Iterable[Rect], sheet: SheetSize, *, turn: bool = True
) -> int:
    """How many sheets of *sheet* the ``(length, width)`` *panels* are cut from
    (SHEET-COUNT-PIECES): the yard sells whole sheets, so count what the
    modelled panels are actually cut from, not their area.

    Deterministic: the panels go largest face first (then longest, then
    widest). Each is cut from the smallest offcut that covers it whole (the
    earliest of equal ones), else from a new sheet. A panel is cut from a
    corner, long side along the sheet's, leaving a rip the full length
    beside it and an end across it, both offcuts for later panels, less a
    1/8 in kerf at each cut (SHEET-KERF): two 24 in rips take two 48 in
    sheets. With *turn* false (a floor's panels, SUBFLOOR-GRAIN) a panel's
    long side stays along the sheet's length, its strength axis, so an
    offcut narrower along the sheet than the panel is long never takes it;
    with *turn* (wall sheathing) a panel may lie either way in an offcut.
    Openings are not credited: a panel is its whole face, as framers
    sheathe over an opening and cut it out."""
    rects = sorted(
        ((max(a, b), min(a, b)) for a, b in panels),
        key=lambda r: (
            -round(r[0] * r[1], LENGTH_DECIMALS),
            -round(r[0], LENGTH_DECIMALS),
            -round(r[1], LENGTH_DECIMALS),
        ),
    )
    if not rects:
        return 0
    smallest = (min(r[0] for r in rects), min(r[1] for r in rects))
    whole: Rect = (sheet.length_mm, sheet.width_mm)
    offcuts: list[Rect] = []
    sheets = 0
    for panel in rects:
        best: int | None = None
        for index, offcut in enumerate(offcuts):
            if _fits(panel, offcut) and (
                best is None
                or offcut[0] * offcut[1] < offcuts[best][0] * offcuts[best][1]
            ):
                best = index
        if best is None:
            sheets += 1
            source = whole
        else:
            source = offcuts.pop(best)
        # An offcut no panel could fit is dropped, keeping the scan short.
        offcuts.extend(
            r for r in _leftovers(source, panel, turn=turn) if _fits(smallest, r)
        )
    return sheets


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
    if sheet is None:
        length = round(max(p.length_mm for p in pieces), 6)
        width = round(max(p.section_mm[1] for p in pieces), 6)
        sheets = None
        offcut = None
    else:
        length, width = round(sheet.length_mm, 6), round(sheet.width_mm, 6)
        sheets = sheets_to_cut(
            ((p.length_mm, p.section_mm[1]) for p in pieces for _ in range(p.count)),
            sheet,
            turn=not any(p.keep_grain for p in pieces),
        )
        offcut = round(max(sheets * sheet.area_mm2 - area, 0.0), 6)
    return CutListLine(
        system="sheathing",
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
        length = 0.0 if line.area_mm2 is not None else line.length_mm
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
    for piece in pieces:
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
        )
        if piece.classification == "unclassified":
            key += tuple(round(v, LENGTH_DECIMALS) for v in piece.section_mm)
        first, count = groups.get(key, (piece, 0))
        groups[key] = (first, count + piece.count)
    lines: list[CutListLine] = []
    for group_key, (piece, quantity) in groups.items():
        if piece.panel:
            lines.append(_sheet_line(panels[group_key], quantity))
            continue
        if piece.unit is not None:
            lines.append(_unit_line(piece, piece.unit, quantity))
            continue
        length = round(piece.length_mm, 6)
        stock = stock_pieces_ft(length) if piece.lumber else None
        thickness, width = (round(v, 6) for v in piece.section_mm)
        waste = None if stock is None else round(sum(stock) * MM_PER_FOOT - length, 6)
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


#: Which unit wins when the book prices a line more than one way.
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


def price_lines(
    lines: Sequence[CutListLine], book: PriceBookResponse
) -> list[CutListLine]:
    """*lines* priced from *book*, on the stock pieces bought: each line's
    unit price is an 'each' entry for its stock length (for a spliced line,
    for every piece of a splice, :func:`_price_stock`, from the first (fewest
    pieces, then least waste) tier of :func:`stock_splice_tiers` the book
    prices whole, its offcut
    recomputed), else a per-foot entry
    on the feet bought, else a per-board-foot entry (for its material and
    profile), and its extended price is that times its stock quantity (one
    per piece, a splice set counting once), so the offcut is paid for. A
    sheet line is priced by the 'each' entry for its product and sheet,
    times its sheets, and a unit line by the 'each' entry for its unit key
    and material, times its units. A line with no stock or no entry
    stays unpriced (null)."""
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
        if line.unit is not None:
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
            tiers = stock_splice_tiers(line.length_mm) if len(stock) > 1 else ()
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
                update["waste_mm"] = round(
                    sum(bought) * MM_PER_FOOT - line.length_mm, 6
                )
        priced.append(
            line.model_copy(
                update={
                    **update,
                    "unit_price_cents": unit_price,
                    "price_unit": unit,
                    "extended_price_cents": (
                        None
                        if unit_price is None or quantity is None
                        else unit_price * quantity
                    ),
                }
            )
        )
    return priced


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


# --- CSV ----------------------------------------------------------------------------

#: Millimetres per display unit.
_MM_PER_UNIT: Final[Mapping[LengthUnit, float]] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": MM_PER_INCH,
    "ft": MM_PER_FOOT,
}

#: Decimals an area is written with, per unit (1 mm^2 or finer).
_AREA_DECIMALS: Final[Mapping[LengthUnit, int]] = {
    "mm": 0,
    "cm": 2,
    "m": 6,
    "in": 4,
    "ft": 6,
}

#: Decimals a length is written with, per unit (about 1 um in each).
_DECIMALS: Final[Mapping[LengthUnit, int]] = {
    "mm": 3,
    "cm": 4,
    "m": 6,
    "in": 4,
    "ft": 5,
}


def format_length(value_mm: float, unit: LengthUnit) -> str:
    """*value_mm* in *unit*, trailing zeros trimmed (``141``, ``10.5``)."""
    text = f"{value_mm / _MM_PER_UNIT[unit]:.{_DECIMALS[unit]}f}"
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "") else text


def format_area(value_mm2: float, unit: LengthUnit) -> str:
    """*value_mm2* in square *unit*, trailing zeros trimmed (``45893``)."""
    text = f"{value_mm2 / _MM_PER_UNIT[unit] ** 2:.{_AREA_DECIMALS[unit]}f}"
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "") else text


#: The CSV's columns (lengths in the document unit, money in the currency).
def csv_header(unit: LengthUnit, currency: Currency = "USD") -> list[str]:
    return [
        "Item",
        "System",
        "Member",
        "Profile",
        f"Section ({unit})",
        "Material",
        "Qty",
        f"Length ({unit})",
        f"Total length ({unit})",
        f"Area (sq {unit})",
        "Stock",
        f"Waste each ({unit})",
        "Stock qty",
        f"Unit price ({currency})",
        "Price unit",
        f"Extended ({currency})",
    ]


#: How the CSV names each price unit.
PRICE_UNIT_LABELS: Final[Mapping[PriceUnit, str]] = {
    "each": "Each",
    "linear_foot": "Per ft",
    "board_foot": "Per BF",
}


def format_cents(cents: int) -> str:
    """*cents* as a plain number of the major unit (``1736.08``), with no
    symbol or separator, so a spreadsheet reads it as a number."""
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}{whole}.{part:02d}"


def total_label(unpriced: int) -> str:
    """The Total row's label: ``Total``, or ``Total of priced lines, N
    unpriced`` when the total leaves lines out."""
    return "Total" if unpriced == 0 else f"Total of priced lines, {unpriced} unpriced"


#: A cell starting with one of these is a FORMULA to Excel, LibreOffice and
#: Google Sheets (``=HYPERLINK(...)``, ``+cmd|...``, ``@SUM``, a leading tab or
#: CR). Member text comes from a plugin's metadata, which a shared ``.loft``
#: carries for a plugin this server may not have, so it is untrusted.
FORMULA_TRIGGERS: Final = ("=", "+", "-", "@", "\t", "\r")


def csv_text(value: str) -> str:
    """*value* safe as a CSV text cell: a formula trigger at its start, or
    after leading whitespace (a spreadsheet may skip it, so ``" =1+1"`` can
    still be a formula), is escaped with a single quote (OWASP, CSV
    injection), so the cell reads as text."""
    if value.startswith(FORMULA_TRIGGERS) or value.lstrip().startswith(
        FORMULA_TRIGGERS
    ):
        return f"'{value}"
    return value


def _stock(line: CutListLine) -> str:
    if line.unit is not None:
        return "Unit"
    if line.sheet is not None:
        return f"{line.sheet} sheet"
    if line.stock_pieces_ft:
        return splice_label(line.stock_pieces_ft)
    return "" if line.stock_length_ft is None else f"{line.stock_length_ft} ft"


def _money(cents: int | None) -> str:
    return "" if cents is None else format_cents(cents)


def cut_list_csv(cut_list: CutListResponse) -> str:
    """The cut list as CSV (RFC 4180, CRLF), one row per line, then a Total
    row of the priced lines. Every text cell goes through :func:`csv_text`;
    numbers are written by this module, money as plain numbers, and an
    unpriced line's price cells are blank (never 0)."""
    unit = cut_list.length_unit
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    header = csv_header(unit, cut_list.currency)
    writer.writerow(header)
    for item, line in enumerate(cut_list.lines, start=1):
        sheet = line.area_mm2 is not None
        material = "" if line.material is None else MATERIALS_BY_KEY[line.material].name
        writer.writerow(
            [
                item,
                SYSTEM_LABELS[line.system],
                csv_text(line.member or ""),
                csv_text(line.profile or "Unclassified"),
                " x ".join(format_length(v, unit) for v in line.section_mm),
                csv_text(material),
                line.quantity,
                "" if sheet else format_length(line.length_mm, unit),
                "" if sheet else format_length(line.total_length_mm, unit),
                "" if line.area_mm2 is None else format_area(line.area_mm2, unit),
                _stock(line),
                "" if line.waste_mm is None else format_length(line.waste_mm, unit),
                "" if line.stock_quantity is None else line.stock_quantity,
                _money(line.unit_price_cents),
                "" if line.price_unit is None else PRICE_UNIT_LABELS[line.price_unit],
                _money(line.extended_price_cents),
            ]
        )
    blank: list[object] = [""] * len(header)
    member, profile, qty = (header.index(h) for h in ("Member", "Profile", "Qty"))
    for missing in cut_list.missing:
        row = list(blank)
        row[member], row[profile], row[qty] = (
            "Deleted part",
            "Not listed",
            missing.quantity,
        )
        writer.writerow(row)
    total = list(blank)
    # In the first text column (System), so a sort by Member keeps it apart.
    total[1] = total_label(cut_list.unpriced_lines)
    total[-1] = _money(cut_list.total_price_cents)
    writer.writerow(total)
    return out.getvalue()


def cut_list_filename(name: str) -> str:
    """``<name> cut list.csv``, with path and quote characters dropped."""
    safe = "".join(c for c in name if c not in '\\/:*?"<>|\r\n').strip() or "cut-list"
    return f"{safe} cut list.csv"
