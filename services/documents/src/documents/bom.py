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
"""

import uuid
from collections import Counter

from loft_wire.assemblies import (
    MAX_ASSEMBLY_DEPTH,
    AssemblyBomResponse,
    BomLine,
    IndentedBomLine,
    RefDocumentKind,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db

RefKey = tuple[uuid.UUID, RefDocumentKind]


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
        ),
    )


class _BomWalk:
    """One read's walk over the assembly tree, memoising each level's lines."""

    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self._lines: dict[uuid.UUID, list[BomLine]] = {}

    async def top_level(self, assembly_id: uuid.UUID) -> list[BomLine]:
        """One line per document *assembly_id* instances directly, sorted."""
        cached = self._lines.get(assembly_id)
        if cached is not None:
            return cached
        result = await self.session.execute(
            select(
                db.Instance.ref_document_id,
                db.Instance.ref_document_kind,
                func.count(),
            )
            .where(db.Instance.assembly_id == assembly_id)
            .group_by(db.Instance.ref_document_id, db.Instance.ref_document_kind)
        )
        groups: list[tuple[uuid.UUID, RefDocumentKind, int]] = [
            (ref_id, kind, int(count)) for ref_id, kind, count in result.all()
        ]
        names = await resolve_document_names(
            self.session, self.owner_id, {(ref_id, kind) for ref_id, kind, _ in groups}
        )
        lines = _sorted(
            [
                BomLine(
                    ref_document_id=ref_id,
                    ref_document_kind=kind,
                    name=names.get((ref_id, kind)),
                    missing=(ref_id, kind) not in names,
                    quantity=count,
                )
                for ref_id, kind, count in groups
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
        parts: Counter[uuid.UUID],
        part_lines: dict[uuid.UUID, BomLine],
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
                parts[line.ref_document_id] += total
                part_lines.setdefault(line.ref_document_id, line)
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


async def top_level_lines(
    session: AsyncSession, owner_id: uuid.UUID, assembly_id: uuid.UUID
) -> list[BomLine]:
    """The assembly's TOP-LEVEL lines (the default BOM and a drawing's)."""
    return await _BomWalk(session, owner_id).top_level(assembly_id)


async def assembly_bom(
    session: AsyncSession, assembly: db.Assembly
) -> AssemblyBomResponse:
    """The assembly's bill of materials: top level, indented and parts only."""
    walk = _BomWalk(session, assembly.owner_id)
    lines = await walk.top_level(assembly.id)
    parts: Counter[uuid.UUID] = Counter()
    part_lines: dict[uuid.UUID, BomLine] = {}
    indented = await walk.indented(assembly.id, parts=parts, part_lines=part_lines)
    parts_only = _sorted(
        [
            part_lines[ref_id].model_copy(update={"quantity": count})
            for ref_id, count in parts.items()
        ]
    )
    return AssemblyBomResponse(
        assembly_id=assembly.id,
        lines=lines,
        total_instances=sum(line.quantity for line in lines),
        indented=indented,
        parts_only=parts_only,
        total_parts=sum(line.quantity for line in parts_only),
    )
