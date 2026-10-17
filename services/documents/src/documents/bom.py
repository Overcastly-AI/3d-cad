"""An assembly's bill of materials, in SolidWorks' three views (ASM-A3).

- **Top level** — one line per document the assembly instances directly; a
  sub-assembly is one line.
- **Indented** — the top-level lines with each sub-assembly's own lines listed
  beneath it, to any depth; quantities are per parent, with the all-levels count
  alongside.
- **Parts only** — every part at every level, counted once per placed
  occurrence: what a shop builds.

A pure read model over the instance tables (no writes, no migration). Names are
the referenced documents' CURRENT names; a document deleted while still
instanced keeps its line with ``missing`` set, and a missing sub-assembly is not
opened. The walk is depth-bounded and memoised per assembly.

A component pattern's copies count as instances of their seed's document
(ASM-A3), at whatever level the pattern is. A hole-driven pattern's count is
the driving part's hole count, which geometry resolves: the gateway passes it
in (:func:`parse_pattern_counts`), and a pattern it could not resolve counts
its seeds only and is listed in ``unresolved_patterns``.

A component mirror's twin counts on its seed's line when it is a mirrored copy,
and on a line of its own, "<part> (opposite hand)" with ``opposite_hand`` set,
when it is an opposite-hand version: a different part to make, as SolidWorks
bills a "Create opposite hand version" part (ASM-MIRROR-COMPONENT).
"""

import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import cast

from loft_wire.assemblies import (
    MAX_ASSEMBLY_DEPTH,
    AssemblyBomResponse,
    BomLine,
    IndentedBomLine,
    RefDocumentKind,
)
from py_kit import ValidationApiError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assembly_history import ordered_mirrors, ordered_patterns
from documents.occurrences import OccurrenceWalk, copies_per_seed

RefKey = tuple[uuid.UUID, RefDocumentKind]

#: A BOM line's identity: the referenced document, and whether the line is
#: that part's opposite hand.
LineKey = tuple[uuid.UUID, RefDocumentKind, bool]

#: How an opposite-hand line is named after its part.
OPPOSITE_HAND_SUFFIX = " (opposite hand)"


def line_name(names: Mapping[RefKey, str], key: LineKey) -> str | None:
    """The name a line of *key* shows: the document's, marked for an
    opposite hand; None when the document is missing."""
    ref_id, kind, opposite = key
    name = names.get((ref_id, kind))
    if name is None or not opposite:
        return name
    return f"{name}{OPPOSITE_HAND_SUFFIX}"


def parse_pattern_counts(values: Iterable[str]) -> dict[uuid.UUID, int]:
    """``['<pattern id>:<count>', ...]`` (the BOM query) as a map, or 422."""
    counts: dict[uuid.UUID, int] = {}
    for value in values:
        pattern_id, _, count = value.partition(":")
        try:
            counts[uuid.UUID(pattern_id)] = int(count)
        except ValueError:
            raise ValidationApiError(
                f"pattern_count {value!r} is not '<pattern id>:<count>'.",
                code="invalid_pattern_count",
            ) from None
    return counts


async def direct_quantities(
    session: AsyncSession,
    assembly_id: uuid.UUID,
    counts: Mapping[uuid.UUID, int],
    unresolved: set[uuid.UUID],
) -> dict[LineKey, int]:
    """How many of each referenced document *assembly_id* places directly,
    in first-appearance (instance) order: one per instance, plus each
    pattern's copies of its seeds, plus each mirror's twin of its seeds (an
    opposite-hand twin on its own line, after the instances). Hole-driven
    patterns missing from *counts* add nothing and are added to
    *unresolved*."""
    result = await session.execute(
        select(
            db.Instance.id, db.Instance.ref_document_id, db.Instance.ref_document_kind
        )
        .where(db.Instance.assembly_id == assembly_id)
        .order_by(db.Instance.order_index)
    )
    ref_of: dict[uuid.UUID, LineKey] = {}
    quantities: dict[LineKey, int] = {}
    for instance_id, ref_id, kind in result.all():
        key: LineKey = (ref_id, cast(RefDocumentKind, kind), False)
        ref_of[instance_id] = key
        quantities[key] = quantities.get(key, 0) + 1
    if not ref_of:
        return quantities
    for row in await ordered_patterns(session, assembly_id):
        copies = copies_per_seed(row, counts)
        if copies is None:
            unresolved.add(row.id)
            continue
        for seed in row.params.get("seed_instance_ids", []):
            seed_ref = ref_of.get(uuid.UUID(seed))
            if seed_ref is not None:
                quantities[seed_ref] += copies
    for mirror in await ordered_mirrors(session, assembly_id):
        opposite = set(mirror.params.get("opposite_hand_instance_ids", []))
        for seed in mirror.params.get("seed_instance_ids", []):
            seed_ref = ref_of.get(uuid.UUID(seed))
            if seed_ref is None:
                continue
            ref_id, kind, _ = seed_ref
            twin: LineKey = (ref_id, kind, kind == "part" and seed in opposite)
            quantities[twin] = quantities.get(twin, 0) + 1
    return quantities


async def resolve_document_names(
    session: AsyncSession,
    owner_id: uuid.UUID,
    refs: set[RefKey],
) -> dict[RefKey, str]:
    """Current names of the referenced parts / assemblies, keyed by (id, kind).

    Owner-scoped (defense-in-depth — references are same-owner enforced at write
    time): a referenced document DELETED since it was instanced is simply absent
    from the map, and the BOM reports that line ``missing`` rather than 500-ing.
    One query per kind over only the ids actually referenced.

    Shared with :mod:`documents.drawings` (a drawing sheet's BOM resolves the SAME
    names for its item lines — CLAUDE.md DRY), hence public.
    """
    part_ids = {ref_id for ref_id, kind in refs if kind == "part"}
    assembly_ids = {ref_id for ref_id, kind in refs if kind == "assembly"}
    names: dict[RefKey, str] = {}
    if part_ids:
        result = await session.execute(
            select(db.Part.id, db.Part.name).where(
                db.Part.id.in_(part_ids), db.Part.owner_id == owner_id
            )
        )
        for ref_id, name in result.all():
            names[(ref_id, "part")] = name
    if assembly_ids:
        result = await session.execute(
            select(db.Assembly.id, db.Assembly.name).where(
                db.Assembly.id.in_(assembly_ids), db.Assembly.owner_id == owner_id
            )
        )
        for ref_id, name in result.all():
            names[(ref_id, "assembly")] = name
    return names


def _sorted(lines: list[BomLine]) -> list[BomLine]:
    """Stable order: resolved name, then id; deleted-ref (null name) lines last."""
    return sorted(
        lines,
        key=lambda line: (
            line.name is None,
            line.name or "",
            str(line.ref_document_id),
            line.opposite_hand,
        ),
    )


class _BomWalk:
    """One read's walk over the assembly tree, memoising each level's lines."""

    def __init__(
        self,
        session: AsyncSession,
        owner_id: uuid.UUID,
        counts: Mapping[uuid.UUID, int] | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.counts: Mapping[uuid.UUID, int] = counts or {}
        self.unresolved: set[uuid.UUID] = set()
        self._lines: dict[uuid.UUID, list[BomLine]] = {}

    async def top_level(self, assembly_id: uuid.UUID) -> list[BomLine]:
        """One line per document *assembly_id* instances directly, sorted."""
        cached = self._lines.get(assembly_id)
        if cached is not None:
            return cached
        quantities = await direct_quantities(
            self.session, assembly_id, self.counts, self.unresolved
        )
        names = await resolve_document_names(
            self.session,
            self.owner_id,
            {(ref_id, kind) for ref_id, kind, _ in quantities},
        )
        lines = _sorted(
            [
                BomLine(
                    ref_document_id=key[0],
                    ref_document_kind=key[1],
                    name=line_name(names, key),
                    missing=(key[0], key[1]) not in names,
                    quantity=count,
                    opposite_hand=key[2],
                )
                for key, count in quantities.items()
            ]
        )
        self._lines[assembly_id] = lines
        return lines

    async def indented(
        self,
        assembly_id: uuid.UUID,
        *,
        prefix: str = "",
        level: int = 0,
        multiplier: int = 1,
        parts: Counter[tuple[uuid.UUID, bool]],
        part_lines: dict[tuple[uuid.UUID, bool], BomLine],
    ) -> list[IndentedBomLine]:
        """The indented rows under *assembly_id*, tallying parts as it goes."""
        rows: list[IndentedBomLine] = []
        for index, line in enumerate(await self.top_level(assembly_id), start=1):
            item = f"{prefix}{index}"
            total = line.quantity * multiplier
            rows.append(
                IndentedBomLine(
                    **line.model_dump(), item=item, level=level, total_quantity=total
                )
            )
            if line.ref_document_kind == "part":
                part = (line.ref_document_id, line.opposite_hand)
                parts[part] += total
                part_lines.setdefault(part, line)
            elif not line.missing and level + 1 < MAX_ASSEMBLY_DEPTH:
                rows.extend(
                    await self.indented(
                        line.ref_document_id,
                        prefix=f"{item}.",
                        level=level + 1,
                        multiplier=total,
                        parts=parts,
                        part_lines=part_lines,
                    )
                )
        return rows


async def assembly_bom(
    session: AsyncSession,
    assembly: db.Assembly,
    counts: Mapping[uuid.UUID, int] | None = None,
) -> AssemblyBomResponse:
    """The assembly's bill of materials: top level, indented and parts only."""
    # Bounded first: the indented rows and part tallies are no more than the
    # components the tree places, which the write-time bound keeps small.
    await OccurrenceWalk(session, assembly.owner_id).require_within_bounds(assembly.id)
    walk = _BomWalk(session, assembly.owner_id, counts)
    lines = await walk.top_level(assembly.id)
    parts: Counter[tuple[uuid.UUID, bool]] = Counter()
    part_lines: dict[tuple[uuid.UUID, bool], BomLine] = {}
    indented = await walk.indented(assembly.id, parts=parts, part_lines=part_lines)
    parts_only = _sorted(
        [
            part_lines[part].model_copy(update={"quantity": count})
            for part, count in parts.items()
        ]
    )
    return AssemblyBomResponse(
        assembly_id=assembly.id,
        lines=lines,
        total_instances=sum(line.quantity for line in lines),
        indented=indented,
        parts_only=parts_only,
        total_parts=sum(line.quantity for line in parts_only),
        unresolved_patterns=sorted(walk.unresolved, key=str),
    )
