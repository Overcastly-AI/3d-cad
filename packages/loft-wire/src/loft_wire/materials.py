"""Material + density vocabulary — the single home of "what a body is made of".

docs/design/materials.md is the decision record. Two rules carry this module:

1. **Mass is DERIVED, never stored.** ``mass = volume x density`` is computed
   exactly where the other mass properties are computed
   (``geometry.kernel.properties``), from the same measured volume, so the two
   can never drift. Nothing persists a mass.
2. **A body with no material has NO mass — absent, not zero.** Every mass field
   on the wire is ``float | None`` and ``None`` means "unknown, because nothing
   has said what this is made of". ``0.0`` would be a claim about a real body
   (a massless one), which is a lie; a default steel would be a different lie.
   Consumers must render absence as absence.

Canonical units mirror the length convention (docs/design/units.md): storage and
the kernel speak canonical **millimetres**, so the canonical mass unit is the
one that falls out of ``mm^3 x kg/m^3`` — **grams**. Display units (g / kg / lb)
are a presentation concern owned by ``packages/design``, exactly like the
mm-per-unit length factors; py-kit never converts for display.
"""

import uuid
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loft_wire.casework import CaseworkItem
from loft_wire.foundation import FoundationItem
from loft_wire.lumber import LumberProfile
from loft_wire.opening_units import OpeningUnitSize
from loft_wire.roofing import RoofingItem
from loft_wire.sheet_goods import SheetGood, SheetSize
from loft_wire.siding import SidingProduct

#: The built-in material library keys (v1). A closed literal, so an unknown
#: material is a parse error at the boundary rather than a silent "no mass"
#: three services later. User-defined materials are a follow-up (design §5) and
#: will arrive as a separate, additive branch of this type — never by loosening
#: it to ``str``.
MaterialKey = Literal[
    "steel_1018",
    "stainless_304",
    "aluminium_6061",
    "brass_c360",
    "abs",
    "pla",
    "nylon_6",
    "spf_lumber",
    "dfl_lumber",
    "southern_pine_pt",
    "white_oak",
    "lvl",
    "glulam_dfl",
    "osb",
    "plywood",
    "steel_a992",
    "concrete",
    "pvc",
    "glass",
    "steel_a615",
    "steel_f1554",
    "gypsum",
    "melamine",
    "xps_foam",
    "fibre_cement",
    "western_red_cedar",
    "asphalt_shingle",
    "polypropylene",
    "aluminium_3105",
]


class Material(BaseModel):
    """One library material: its key, display name, and density.

    Density is the ONLY physical property v1 models, because mass is the only
    thing we claim to report. Thermal/elastic properties would be an unbacked
    promise until something computes with them (design §1).
    """

    key: MaterialKey
    name: str = Field(description="Display name, e.g. 'Aluminium 6061'")
    density_kg_m3: float = Field(
        gt=0,
        description="Density (kg/m^3). Handbook NOMINAL value — a production "
        "part uses its supplier's certificate, not this table.",
    )
    source: str = Field(
        description="Where the density comes from (standard, table, and the "
        "moisture content for wood), so a user can check it."
    )


# Densities are handbook nominal values at room temperature, rounded to the
# 3 significant figures every MCAD system ships as its default (ASM Metals
# Reference Book / MatWeb typical values for the metals; resin/filament
# datasheet typicals for the polymers). They are DEFAULTS, not measurements:
# a real 6061 extrusion is 2.70 +/- a hair, and a printed part is lighter than
# solid PLA because it is not solid. Written kg/m^3 so the numbers are the ones
# an engineer recognises (2700 = 2.70 g/cm^3).
#
# Building materials (LUMBER-MATERIALS, RESEARCH §23). Sawn lumber is the
# species group's specific gravity G from the AWC NDS (2018) Table 12.3.3A
# (oven-dry weight and volume), taken to density at 12 % moisture content with
# the Wood Handbook (FPL-GTR-190, 2010) ch. 4 relations:
#   G_b = G_0 / (1 + 0.265 G_0)                      basic (green volume)
#   G_M = G_b / (1 - 0.265 a G_b),  a = (30 - M)/30  at M % moisture
#   rho = 1000 G_M (1 + M/100)  kg/m^3
# SPF G_0 0.42 -> 450.35, DF-L 0.50 -> 531.81, southern pine 0.55 -> 582.07,
# white oak 0.73 -> 758.88 (timber-frame pegs, TIMBER-FRAME).
# packages/loft-wire/tests/test_lumber.py re-derives each one. The engineered
# and structural entries are the design unit weights their industries publish
# (lb/ft^3 x 16.0185 = kg/m^3).
_PCF = "lb/ft^3"
_LIBRARY: tuple[Material, ...] = (
    Material(
        key="steel_1018",
        name="Steel (AISI 1018)",
        density_kg_m3=7870.0,
        source="ASM Metals Reference Book, typical",
    ),
    Material(
        key="stainless_304",
        name="Stainless steel (AISI 304)",
        density_kg_m3=8000.0,
        source="ASM Metals Reference Book, typical",
    ),
    Material(
        key="aluminium_6061",
        name="Aluminium 6061",
        density_kg_m3=2700.0,
        source="ASM Metals Reference Book, typical",
    ),
    Material(
        key="brass_c360",
        name="Brass (C360)",
        density_kg_m3=8500.0,
        source="ASM Metals Reference Book, typical",
    ),
    Material(
        key="abs", name="ABS", density_kg_m3=1040.0, source="Resin datasheet, typical"
    ),
    Material(
        key="pla", name="PLA", density_kg_m3=1240.0, source="Resin datasheet, typical"
    ),
    Material(
        key="nylon_6",
        name="Nylon (PA6)",
        density_kg_m3=1140.0,
        source="Resin datasheet, typical",
    ),
    Material(
        key="spf_lumber",
        name="Spruce-pine-fir (SPF) lumber",
        density_kg_m3=450.0,
        source="AWC NDS 2018 Table 12.3.3A G = 0.42; Wood Handbook ch. 4, "
        "at 12% moisture content",
    ),
    Material(
        key="dfl_lumber",
        name="Douglas fir-larch lumber",
        density_kg_m3=532.0,
        source="AWC NDS 2018 Table 12.3.3A G = 0.50; Wood Handbook ch. 4, "
        "at 12% moisture content",
    ),
    Material(
        key="southern_pine_pt",
        name="Southern pine, pressure-treated",
        density_kg_m3=582.0,
        source="AWC NDS 2018 Table 12.3.3A G = 0.55; Wood Handbook ch. 4, "
        "at 12% moisture content (kiln-dried after treatment; preservative "
        "retention, under 1%, not included)",
    ),
    Material(
        key="white_oak",
        name="White oak",
        density_kg_m3=759.0,
        source="AWC NDS 2018 Table 12.3.3A G = 0.73; Wood Handbook ch. 4, "
        "at 12% moisture content",
    ),
    Material(
        key="lvl",
        name="LVL (laminated veneer lumber)",
        density_kg_m3=673.0,
        source=f"Manufacturer design weight, 42 {_PCF} (1.9E-2.0E LVL)",
    ),
    Material(
        key="glulam_dfl",
        name="Glulam (Douglas fir)",
        density_kg_m3=561.0,
        source=f"APA/AWC glulam design weight, 35 {_PCF}",
    ),
    # Sheet goods (SHEATHING): the panel weights APA publishes, typical for
    # the species and resin of US structural panels.
    Material(
        key="osb",
        name="OSB (oriented strand board)",
        density_kg_m3=641.0,
        source=f"APA typical panel weight, 40 {_PCF}",
    ),
    Material(
        key="plywood",
        name="Plywood (softwood, structural)",
        density_kg_m3=577.0,
        source=f"APA typical panel weight, 36 {_PCF}",
    ),
    Material(
        key="steel_a992",
        name="Structural steel (ASTM A992)",
        density_kg_m3=7850.0,
        source=f"AISC Steel Construction Manual, 490 {_PCF}",
    ),
    Material(
        key="concrete",
        name="Concrete (normal-weight, reinforced)",
        density_kg_m3=2400.0,
        source=f"ASCE 7-16 Table C3.1-2, reinforced stone concrete, 150 {_PCF}",
    ),
    # Window and door units (OPENING-UNITS, RESEARCH §23): a vinyl window's
    # frame and its glazing. The frame body is the frame's envelope, so it
    # weighs as solid PVC (an upper bound on a hollow extrusion).
    Material(
        key="pvc",
        name="Rigid PVC (vinyl)",
        density_kg_m3=1400.0,
        source="Rigid (unplasticised) PVC datasheet, typical (ISO 1183)",
    ),
    Material(
        key="glass",
        name="Glass (soda-lime)",
        density_kg_m3=2500.0,
        source="ASTM C1036 float glass, typical 2500 kg/m^3",
    ),
    # Foundation items (SLAB): listed, not drawn (loft_wire.foundation), so
    # they carry no mass; the key is what a rebar stick or bolt is priced as.
    Material(
        key="steel_a615",
        name="Reinforcing steel (ASTM A615)",
        density_kg_m3=7850.0,
        source=f"CRSI Manual of Standard Practice, 490 {_PCF}",
    ),
    Material(
        key="steel_f1554",
        name="Anchor-bolt steel (ASTM F1554)",
        density_kg_m3=7850.0,
        source=f"AISC Steel Construction Manual, 490 {_PCF}",
    ),
    # Gypsum board (INTERIOR-WALLS, RESEARCH §23): the dead load ASCE 7 tabulates,
    # 0.55 psf per 1/8 in of thickness, so 4.4 psf per inch: 52.8 lb/ft^3.
    Material(
        key="gypsum",
        name="Gypsum board",
        density_kg_m3=846.0,
        source=f"ASCE 7-16 Table C3.1-1a, gypsum board 0.55 psf per 1/8 in, "
        f"52.8 {_PCF}",
    ),
    # Casework (CASEWORK, RESEARCH §23): melamine-faced particleboard, the
    # carcass panel a frameless shop cuts beside cabinet plywood.
    Material(
        key="melamine",
        name="Melamine (faced particleboard)",
        density_kg_m3=721.0,
        source=f"ANSI A208.1 grade M-2 particleboard, typical 45 {_PCF}",
    ),
    # Rigid foam (OPENING-UPDATE, RESEARCH §23): the foam of an insulated
    # header ("Two plies, foam between"), extruded polystyrene at ASTM C578
    # Type IV's minimum density, the 25 psi board framers buy for it.
    Material(
        key="xps_foam",
        name="Rigid foam (XPS)",
        density_kg_m3=23.2,
        source=f"ASTM C578 Type IV extruded polystyrene, minimum 1.45 {_PCF}",
    ),
    # Siding and trim (SIDING-TRIM, RESEARCH §23). Fibre cement: James
    # Hardie's HardiePlank 8.25 x 5/16 weighs 2.3 lb per ft² of wall at its
    # 7 in exposure, so a board's own face weighs 2.3 x 7 / 8.25 lb/ft² at
    # 5/16 in: 75 lb/ft^3. Western red cedar (siding, trim) is the Western
    # Cedars group by the wood relations above, G_0 0.36 -> 388.37.
    Material(
        key="fibre_cement",
        name="Fibre cement",
        density_kg_m3=1200.0,
        source=f"James Hardie HardiePlank 8.25 x 5/16, 2.3 lb/ft² of wall at "
        f"7 in exposure: 75 {_PCF}",
    ),
    Material(
        key="western_red_cedar",
        name="Western red cedar",
        density_kg_m3=388.0,
        source="AWC NDS 2018 Table 12.3.3A Western Cedars G = 0.36; Wood "
        "Handbook ch. 4, at 12% moisture content",
    ),
    # Roofing (ROOFING, RESEARCH §23): listed, not drawn (loft_wire.roofing),
    # so they carry no mass; the key is what a bundle, roll or stick is
    # priced as. Asphalt shingles by their binder, the asphaltum ASCE 7
    # tabulates; synthetic underlayment is woven polypropylene; drip edge
    # is roll-formed 3105 aluminium coil.
    Material(
        key="asphalt_shingle",
        name="Asphalt shingle",
        density_kg_m3=1300.0,
        source=f"ASCE 7-16 Table C3.1-2, asphaltum, 81 {_PCF}",
    ),
    Material(
        key="polypropylene",
        name="Polypropylene",
        density_kg_m3=905.0,
        source="Polypropylene homopolymer datasheet, typical (ISO 1183)",
    ),
    Material(
        key="aluminium_3105",
        name="Aluminium 3105",
        density_kg_m3=2720.0,
        source="Aluminum Association, Aluminum Standards and Data: 3105, 2.72 g/cm^3",
    ),
)

#: The library in display order (metals, polymers, wood, then structural steel
#: and concrete) — the order a picker
#: shows. A tuple, so no caller can mutate the shared table.
MATERIALS: tuple[Material, ...] = _LIBRARY

#: Key -> material, for O(1) density lookup. Immutable view of the same objects.
MATERIALS_BY_KEY: Mapping[MaterialKey, Material] = {m.key: m for m in _LIBRARY}


class MaterialLibraryResponse(BaseModel):
    """The built-in material library, served so no client hardcodes a density.

    The picker needs names + densities, and a second copy of the table in TS
    would be a DRY violation that silently drifts (CLAUDE.md). One table, in
    py-kit, served over the API.

    ``profiles`` is the section library members are cut from (US lumber,
    ``loft_wire.lumber``), served beside the materials as SolidWorks serves
    weldment profiles beside its material database.
    """

    materials: list[Material]
    profiles: list[LumberProfile] = Field(
        description="Lumber sections: nominal name and actual dressed size."
    )
    sheet_goods: list[SheetGood] = Field(
        description="Sheet products (SHEATHING): a material at a thickness, "
        "e.g. '7/16 OSB'."
    )
    sheet_sizes: list[SheetSize] = Field(
        description="The sheets they are sold in, shortest first: 4x8, 4x9, "
        "4x10, 4x12 (each product in its own: gypsum board in 4x8 and 4x12)."
    )
    opening_units: list[OpeningUnitSize] = Field(
        default_factory=list[OpeningUnitSize],
        description="Window and door units by call size (OPENING-UNITS): "
        "what a unit price is keyed by ('window_3040') and its frame material.",
    )
    foundation_items: list[FoundationItem] = Field(
        default_factory=list[FoundationItem],
        description="Foundation items (SLAB): ready-mix concrete per cubic "
        "yard, #4 rebar per 20 ft stick and 1/2 in anchor bolts Each, keyed "
        "as a price-book profile ('rebar_4').",
    )
    casework_items: list[CaseworkItem] = Field(
        default_factory=list[CaseworkItem],
        description="Edge banding and cabinet hardware (CASEWORK): what a "
        "casework price is keyed by ('hinge', 'slide_22'), its unit and the "
        "materials it is sold in.",
    )
    siding_products: list[SidingProduct] = Field(
        default_factory=list[SidingProduct],
        description="Siding products (SIDING-TRIM): what a siding price is "
        "keyed by ('vinyl_d4'), its material, how it is sold (a 12 ft board "
        "Each, or vinyl per square) and what one covers.",
    )
    roofing_items: list[RoofingItem] = Field(
        default_factory=list[RoofingItem],
        description="Roofing items (ROOFING): shingles by the bundle, "
        "underlayment by the roll, drip edge by the 10 ft stick, starter and "
        "ridge cap by the foot, keyed as a price-book profile ('drip_edge').",
    )


class BodyMaterialAssignment(BaseModel):
    """A per-BODY material override, keyed by the body's §MB-0 identity.

    ``base_feature_id`` is the id of the feature that CREATED the body — the
    same key ``EvaluationState.bodies`` and
    :class:`~loft_wire.features.BodyLumpInfo` use — so an override survives
    edits to other features the way any body reference does. An override naming
    a body the tree no longer produces is inert (it matches nothing); it is not
    an error, because a rolled-back tree legitimately hides the body for a while.
    """

    base_feature_id: uuid.UUID = Field(
        description="Id of the feature that created the body (its MB-0 identity)"
    )
    material: MaterialKey = Field(description="Material for THIS body only")


class MaterialAssignment(BaseModel):
    """What a document is made of: one default + per-body overrides (design §2).

    A multi-body part legitimately mixes materials (a steel pin in an aluminium
    housing), so a single document-level material would be wrong for exactly the
    parts mass matters most on. The resolution rule is one line — an override
    wins over the default (:func:`resolve_body_material`) — and lives here so
    every consumer resolves identically.

    ``default_material: None`` with no overrides is the HONEST empty state a new
    document starts in: no material anywhere, therefore no mass anywhere.
    """

    model_config = ConfigDict(frozen=True)

    default_material: MaterialKey | None = Field(
        default=None,
        description="Material for every body without an override; null means "
        "the document has no material, so its mass is UNKNOWN (not zero).",
    )
    bodies: list[BodyMaterialAssignment] = Field(
        default_factory=list["BodyMaterialAssignment"],
        description="Per-body overrides; at most one entry per base_feature_id.",
    )

    @model_validator(mode="after")
    def _reject_duplicate_bodies(self) -> "MaterialAssignment":
        """One override per body — a duplicate is a malformed assignment.

        Silently letting "last wins" through would make the resolved mass depend
        on array order, which is exactly the class of nondeterminism RESEARCH §9
        forbids; rejecting it at the boundary keeps resolution order-free.
        """
        seen: set[uuid.UUID] = set()
        for entry in self.bodies:
            if entry.base_feature_id in seen:
                raise ValueError(
                    f"duplicate material override for body {entry.base_feature_id}"
                )
            seen.add(entry.base_feature_id)
        return self


#: A document with nothing assigned — the honest default for every new part.
EMPTY_MATERIAL_ASSIGNMENT = MaterialAssignment()


def resolve_body_material(
    assignment: MaterialAssignment | None, base_feature_id: uuid.UUID
) -> MaterialKey | None:
    """THE resolution rule: a body's override, else the document default, else none.

    One implementation (CLAUDE.md DRY) — the kernel, the assembly roll-up and any
    future BOM all ask this, none of them re-derive it. ``None`` out means the
    body has no material, so it has no mass.
    """
    if assignment is None:
        return None
    for entry in assignment.bodies:
        if entry.base_feature_id == base_feature_id:
            return entry.material
    return assignment.default_material


def with_member_materials(
    assignment: MaterialAssignment | None,
    members: Mapping[uuid.UUID, MaterialKey | None],
) -> MaterialAssignment | None:
    """The assignment geometry evaluates with: *assignment* plus each plugin
    member's own material (RESEARCH §23, DECK).

    A generated member is cut from a material its plugin names (a joist of
    pressure-treated pine), as a SolidWorks weldment member carries its
    profile's material: so a member body takes that material over the
    document default, and the user's own per-body override still wins over
    both. *members* maps each member body's id (its creating feature) to its
    material, in tree order; ``None`` there leaves the body to the default.
    The stored assignment is never changed: this is derived per evaluation,
    so a regenerated member keeps following its plugin's input.
    """
    chosen = {
        entry.base_feature_id
        for entry in (assignment or EMPTY_MATERIAL_ASSIGNMENT).bodies
    }
    extra = [
        BodyMaterialAssignment(base_feature_id=body, material=material)
        for body, material in members.items()
        if material is not None and body not in chosen
    ]
    if not extra:
        return assignment
    base = assignment or EMPTY_MATERIAL_ASSIGNMENT
    return MaterialAssignment(
        default_material=base.default_material, bodies=[*base.bodies, *extra]
    )


def density_kg_m3(material: MaterialKey | None) -> float | None:
    """Density of a library material; ``None`` in → ``None`` out (no material)."""
    if material is None:
        return None
    return MATERIALS_BY_KEY[material].density_kg_m3


#: Grams per (mm^3 x kg/m^3): 1 kg/m^3 = 1e-6 g/mm^3. The ONE mass conversion
#: constant in the codebase — canonical mm^3 in, canonical grams out.
GRAMS_PER_MM3_KG_M3 = 1e-6


def mass_g(volume_mm3: float, density: float | None) -> float | None:
    """``volume x density`` → grams, or ``None`` when there is no density.

    The single mass computation (CLAUDE.md DRY): every mass on the wire comes
    through here, so a mass can never disagree with the volume it was derived
    from. Deterministic — two float multiplies, no accumulation order to vary.
    """
    if density is None:
        return None
    return volume_mm3 * density * GRAMS_PER_MM3_KG_M3
