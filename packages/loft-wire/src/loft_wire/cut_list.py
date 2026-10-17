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
stock, or one that is not lumber, has no stock suggestion.

This module is pure (no I/O, no kernel): the gateway assembles the cut list
with it, and the B1 acceptance test calls it on geometry's measurements.
"""

import csv
import io
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import permutations
from typing import Final, Literal

from pydantic import BaseModel, Field

from loft_wire.assemblies import RefDocumentKind
from loft_wire.features import EvaluateTreeRequest
from loft_wire.lumber import (
    LUMBER_PROFILES,
    MM_PER_INCH,
    LumberProfile,
)
from loft_wire.materials import (
    MATERIALS_BY_KEY,
    MaterialAssignment,
    MaterialKey,
)
from loft_wire.plugins import MemberMetadata
from loft_wire.units import LengthUnit

#: Standard US lumber stock lengths (ft), shortest first.
STOCK_LENGTHS_FT: Final[tuple[int, ...]] = (8, 10, 12, 14, 16, 20)

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

#: How a piece was identified: from a plugin member's metadata, by matching
#: its section to a library profile, or not at all.
CutListClassification = Literal["member", "matched", "unclassified"]


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
    """One line: pieces with the same member, profile, material and length."""

    member: str | None = Field(
        description="Member role title (e.g. 'Joist'); null when the body is "
        "not a plugin member."
    )
    profile: str | None = Field(
        description="Section as sold (e.g. '2x10'); null when unclassified."
    )
    material: MaterialKey | None = Field(description="Library material, or null.")
    classification: CutListClassification
    quantity: int = Field(ge=1)
    length_mm: float = Field(ge=0, description="Measured length of each piece.")
    total_length_mm: float = Field(ge=0, description="quantity x length.")
    section_mm: list[float] = Field(
        min_length=2,
        max_length=2,
        description="Measured section (mm): [thickness, width], smaller first.",
    )
    stock_length_ft: int | None = Field(
        description="Shortest standard stock that covers the piece (ft); null "
        "for a piece that is not lumber or is longer than the longest stock."
    )
    waste_mm: float | None = Field(
        description="Offcut of each piece from its stock (mm); null with no stock."
    )


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


def stock_length_ft(length_mm: float) -> int | None:
    """The shortest standard stock (ft) that covers *length_mm*, or ``None``."""
    for feet in STOCK_LENGTHS_FT:
        if length_mm <= feet * MM_PER_FOOT + 1e-6:
            return feet
    return None


@dataclass(frozen=True)
class CutListPiece:
    """One measured piece, before grouping (``count`` copies of it)."""

    member: str | None
    profile: str | None
    lumber: bool
    material: MaterialKey | None
    classification: CutListClassification
    length_mm: float
    section_mm: tuple[float, float]
    count: int = 1


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
    if member is not None:
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


def group_pieces(pieces: Iterable[CutListPiece]) -> list[CutListLine]:
    """Pieces grouped by member, profile, material and length, in the order
    each group first appears (the tree order, as SolidWorks lists it)."""
    groups: dict[tuple[object, ...], tuple[CutListPiece, int]] = {}
    for piece in pieces:
        key: tuple[object, ...] = (
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
    for piece, quantity in groups.values():
        length = round(piece.length_mm, 6)
        stock = stock_length_ft(length) if piece.lumber else None
        thickness, width = (round(v, 6) for v in piece.section_mm)
        waste = None if stock is None else round(stock * MM_PER_FOOT - length, 6)
        lines.append(
            CutListLine(
                member=piece.member,
                profile=piece.profile,
                material=piece.material,
                classification=piece.classification,
                quantity=quantity,
                length_mm=length,
                total_length_mm=round(length * quantity, 6),
                section_mm=[thickness, width],
                stock_length_ft=stock,
                waste_mm=waste,
            )
        )
    return lines


def cut_list_response(
    *,
    document_id: uuid.UUID,
    document_kind: RefDocumentKind,
    name: str,
    length_unit: LengthUnit,
    pieces: Sequence[CutListPiece],
) -> CutListResponse:
    """The grouped response for *pieces*."""
    lines = group_pieces(pieces)
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


#: The CSV's columns (lengths in the document unit).
def csv_header(unit: LengthUnit) -> list[str]:
    return [
        "Item",
        "Member",
        "Profile",
        f"Section ({unit})",
        "Material",
        "Qty",
        f"Length ({unit})",
        f"Total length ({unit})",
        "Stock",
        f"Waste each ({unit})",
    ]


def cut_list_csv(cut_list: CutListResponse) -> str:
    """The cut list as CSV (RFC 4180, CRLF), one row per line."""
    unit = cut_list.length_unit
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(csv_header(unit))
    for item, line in enumerate(cut_list.lines, start=1):
        material = "" if line.material is None else MATERIALS_BY_KEY[line.material].name
        writer.writerow(
            [
                item,
                line.member or "",
                line.profile or "Unclassified",
                " x ".join(format_length(v, unit) for v in line.section_mm),
                material,
                line.quantity,
                format_length(line.length_mm, unit),
                format_length(line.total_length_mm, unit),
                "" if line.stock_length_ft is None else f"{line.stock_length_ft} ft",
                "" if line.waste_mm is None else format_length(line.waste_mm, unit),
            ]
        )
    return out.getvalue()


def cut_list_filename(name: str) -> str:
    """``<name> cut list.csv``, with path and quote characters dropped."""
    safe = "".join(c for c in name if c not in '\\/:*?"<>|\r\n').strip() or "cut-list"
    return f"{safe} cut list.csv"
