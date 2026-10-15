"""Component pattern rows: validation, expressions and cascades (ASM-A3).

The write rules for :class:`documents.db.AssemblyPattern`, shared by the
pattern routes (:mod:`documents.assembly_patterns`), the instance delete
cascade and the graph read in :mod:`documents.assemblies`:

- every SEED is an instance of the assembly (a part or a rigid sub-assembly);
- every REFERENCE (a direction or axis edge, a driving hole, a further driving
  instance) is a PART of the assembly: a direct part instance or a part inside
  one of its sub-assemblies, by occurrence id, as joints name them;
- further driving instances of a hole-driven pattern instance the same part as
  the seed hole's (checked where both are direct instances; geometry reports a
  nested mismatch as ``pattern_driver_mismatch``);
- each typed expression is evaluated here and its number stored, so geometry
  and every client read numbers (the expression text is kept beside it).

Deleting an instance removes it from every pattern's seeds; a pattern left
without seeds, or whose reference lived on that instance, is deleted with it,
as a joint is.
"""

import uuid
from collections.abc import Sequence

from loft_wire.component_patterns import (
    MAX_ASSEMBLY_PATTERNS,
    CircularComponentPattern,
    ComponentPattern,
    ComponentPatternParams,
    HoleComponentPattern,
    LinearComponentPattern,
    PatternResponse,
    pattern_reference_ids,
)
from loft_wire.expr import ExpressionError, Kind, coerce, coerce_int, evaluate
from py_kit import ValidationApiError
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assembly_history import ordered_instances, ordered_patterns
from documents.occurrences import mate_members

#: Reconstruct a stored pattern row's params into the discriminated union.
PATTERN_ADAPTER: TypeAdapter[ComponentPatternParams] = TypeAdapter(ComponentPattern)


def pattern_response(row: db.AssemblyPattern) -> PatternResponse:
    """Row -> DTO: the params JSONB reassembled into the union."""
    return PatternResponse(
        id=row.id,
        assembly_id=row.assembly_id,
        order_index=row.order_index,
        pattern=PATTERN_ADAPTER.validate_python(row.params),
    )


def _value(text: str, kind: Kind | None, field: str) -> float:
    """*text* evaluated for a field of *kind* (None: a whole number)."""
    try:
        quantity = evaluate(text)
        if kind is None:
            return float(coerce_int(quantity, field))
        return coerce(quantity, kind, field)
    except ExpressionError as exc:
        raise ValidationApiError(
            f"{field}: {exc}", code=exc.code, details={"field": field}
        ) from None


def resolve_expressions(pattern: ComponentPatternParams) -> ComponentPatternParams:
    """*pattern* with every typed expression evaluated into its number.

    The number a client sent is overwritten: the server's evaluation is the
    stored truth, as for feature formulas. A value outside its field's range
    is the same 422 a typed number gets (``pattern_value_invalid``).
    """
    update_fields: dict[str, float | int] = {}
    if (
        isinstance(pattern, LinearComponentPattern | CircularComponentPattern)
        and pattern.count_expr is not None
    ):
        update_fields["count"] = int(_value(pattern.count_expr, None, "count"))
    if isinstance(pattern, LinearComponentPattern) and pattern.spacing_expr:
        update_fields["spacing_mm"] = _value(pattern.spacing_expr, "length", "spacing")
    if isinstance(pattern, CircularComponentPattern) and pattern.angle_expr:
        update_fields["angle_deg"] = _value(pattern.angle_expr, "angle", "angle")
    if not update_fields:
        return pattern
    try:
        return type(pattern).model_validate(
            {**pattern.model_dump(mode="json"), **update_fields}
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ValidationApiError(
            f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}",
            code="pattern_value_invalid",
            details={"field": str(first["loc"][0]) if first["loc"] else None},
        ) from None


async def validate_pattern(
    session: AsyncSession,
    owner_id: uuid.UUID,
    assembly_id: uuid.UUID,
    pattern: ComponentPatternParams,
) -> None:
    """422 unless *pattern*'s seeds and references belong to the assembly."""
    instances = {row.id: row for row in await ordered_instances(session, assembly_id)}
    for seed in pattern.seed_instance_ids:
        if seed not in instances:
            raise ValidationApiError(
                f"Pattern seed {seed} is not an instance of this assembly.",
                code="pattern_seed_unknown",
                details={"instance_id": str(seed)},
            )
    references = pattern_reference_ids(pattern)
    members = await mate_members(session, owner_id, assembly_id, set(references))
    for reference in references:
        member = members.get(reference)
        if member is None:
            raise ValidationApiError(
                f"The pattern reads geometry from {reference}, which is not a part "
                "of this assembly.",
                code="pattern_reference_unknown",
                details={"instance_id": str(reference)},
            )
        if member.is_sub_assembly:
            raise ValidationApiError(
                "A pattern direction, axis or hole is picked on a part: pick an "
                "edge of a part inside the sub-assembly.",
                code="pattern_needs_part",
                details={"instance_id": str(reference)},
            )
    if isinstance(pattern, HoleComponentPattern):
        driver = instances.get(pattern.seed_hole.instance_id)
        for other_id in pattern.also_on:
            other = instances.get(other_id)
            if (
                driver is not None
                and other is not None
                and other.ref_document_id != driver.ref_document_id
            ):
                raise ValidationApiError(
                    f"{other.name} is not an instance of the driving part, so it "
                    "has none of its holes.",
                    code="pattern_driver_mismatch",
                    details={"instance_id": str(other_id)},
                )


async def require_pattern_room(session: AsyncSession, assembly_id: uuid.UUID) -> int:
    """The append position for a new pattern, or 422 at the per-assembly cap."""
    position = len(await ordered_patterns(session, assembly_id))
    if position >= MAX_ASSEMBLY_PATTERNS:
        raise ValidationApiError(
            f"An assembly holds at most {MAX_ASSEMBLY_PATTERNS} component patterns.",
            code="pattern_limit_exceeded",
            details={"max_patterns": MAX_ASSEMBLY_PATTERNS},
        )
    return position


async def renumber_patterns(session: AsyncSession, assembly_id: uuid.UUID) -> None:
    """Close gaps in the pattern order, ascending (legal under IMMEDIATE checks)."""
    await session.flush()
    for index, row in enumerate(await ordered_patterns(session, assembly_id)):
        if row.order_index != index:
            await session.execute(
                update(db.AssemblyPattern)
                .where(db.AssemblyPattern.id == row.id)
                .values(order_index=index)
            )


async def cascade_instance_delete(
    session: AsyncSession,
    owner_id: uuid.UUID,
    assembly_id: uuid.UUID,
    instance_id: uuid.UUID,
) -> None:
    """Take *instance_id* out of every pattern of *assembly_id* (see module).

    Runs before the instance row is deleted, so a nested reference can still
    be traced to the sub-assembly instance it lives in.
    """
    rows = await ordered_patterns(session, assembly_id)
    if not rows:
        return
    parsed = {row.id: PATTERN_ADAPTER.validate_python(row.params) for row in rows}
    references: set[uuid.UUID] = {
        ref for pattern in parsed.values() for ref in pattern_reference_ids(pattern)
    }
    members = await mate_members(session, owner_id, assembly_id, references)
    changed = False
    for row in rows:
        pattern = parsed[row.id]
        lost_reference = any(
            (member := members.get(ref)) is not None and member.group_id == instance_id
            for ref in pattern_reference_ids(pattern)
        )
        seeds: Sequence[uuid.UUID] = [
            s for s in pattern.seed_instance_ids if s != instance_id
        ]
        if lost_reference or not seeds:
            await session.delete(row)
            changed = True
        elif len(seeds) != len(pattern.seed_instance_ids):
            row.params = pattern.model_copy(
                update={"seed_instance_ids": list(seeds)}
            ).model_dump(mode="json")
            changed = True
    if changed:
        await renumber_patterns(session, assembly_id)
