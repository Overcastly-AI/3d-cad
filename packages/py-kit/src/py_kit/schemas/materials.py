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


# Densities are handbook nominal values at room temperature, rounded to the
# 3 significant figures every MCAD system ships as its default (ASM Metals
# Reference Book / MatWeb typical values for the metals; resin/filament
# datasheet typicals for the polymers). They are DEFAULTS, not measurements:
# a real 6061 extrusion is 2.70 +/- a hair, and a printed part is lighter than
# solid PLA because it is not solid. Written kg/m^3 so the numbers are the ones
# an engineer recognises (2700 = 2.70 g/cm^3).
_LIBRARY: tuple[Material, ...] = (
    Material(key="steel_1018", name="Steel (AISI 1018)", density_kg_m3=7870.0),
    Material(
        key="stainless_304", name="Stainless steel (AISI 304)", density_kg_m3=8000.0
    ),
    Material(key="aluminium_6061", name="Aluminium 6061", density_kg_m3=2700.0),
    Material(key="brass_c360", name="Brass (C360)", density_kg_m3=8500.0),
    Material(key="abs", name="ABS", density_kg_m3=1040.0),
    Material(key="pla", name="PLA", density_kg_m3=1240.0),
    Material(key="nylon_6", name="Nylon (PA6)", density_kg_m3=1140.0),
)

#: The library in display order (metals, then polymers) — the order a picker
#: shows. A tuple, so no caller can mutate the shared table.
MATERIALS: tuple[Material, ...] = _LIBRARY

#: Key -> material, for O(1) density lookup. Immutable view of the same objects.
MATERIALS_BY_KEY: Mapping[MaterialKey, Material] = {m.key: m for m in _LIBRARY}


class MaterialLibraryResponse(BaseModel):
    """The built-in material library, served so no client hardcodes a density.

    The picker needs names + densities, and a second copy of the table in TS
    would be a DRY violation that silently drifts (CLAUDE.md). One table, in
    py-kit, served over the API.
    """

    materials: list[Material]


class BodyMaterialAssignment(BaseModel):
    """A per-BODY material override, keyed by the body's §MB-0 identity.

    ``base_feature_id`` is the id of the feature that CREATED the body — the
    same key ``EvaluationState.bodies`` and
    :class:`~py_kit.schemas.features.BodyLumpInfo` use — so an override survives
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
