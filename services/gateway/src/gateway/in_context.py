"""In-context links: carry geometry's resolved values to documents
(ASM-A3-IN-CONTEXT, RESEARCH §24).

Geometry resolves each in-context link inside its context assembly's
evaluation and says which values changed; documents stores the last resolved
value so the edited part rebuilds the same way out of context. Neither talks
to the other (CLAUDE.md), so the gateway joins them after
``/geometry/assembly/evaluate``: one documents write per edited part, as the
caller (documents checks ownership). A failed write is logged and the
evaluation still answers: the value is a cache of what geometry just computed,
and the next evaluation writes it again.
"""

import uuid
from collections import defaultdict

from fastapi import Request
from loft_wire.assemblies import EvaluateAssemblyResult
from loft_wire.in_context import InContextResolvedItem, InContextResolvedWrite
from py_kit import get_logger

from gateway.db import User
from gateway.parts import forward_documents

_logger = get_logger("gateway.in_context")


def resolved_writes(
    result: EvaluateAssemblyResult,
) -> dict[uuid.UUID, InContextResolvedWrite]:
    """The changed resolved values of *result*, grouped by edited part."""
    items: dict[uuid.UUID, list[InContextResolvedItem]] = defaultdict(list)
    for status in result.in_context:
        if status.state != "ok" or not status.changed or status.resolved is None:
            continue
        items[status.part_id].append(
            InContextResolvedItem(
                feature_id=status.feature_id,
                entity_id=status.entity_id,
                assembly_id=result.assembly_id,
                occurrence_id=status.occurrence_id,
                resolved=status.resolved,
            )
        )
    return {
        part_id: InContextResolvedWrite(items=part_items)
        for part_id, part_items in items.items()
    }


async def write_back(
    http_request: Request, user: User, result: EvaluateAssemblyResult
) -> None:
    """Store every changed resolved value of *result* in documents."""
    for part_id, body in resolved_writes(result).items():
        try:
            upstream = await forward_documents(
                http_request,
                user,
                "POST",
                f"/api/v1/parts/{part_id}/in-context/resolved",
                json_content=body.model_dump_json(),
            )
        except Exception as exc:
            _logger.warning(
                "in_context_write_failed", part_id=str(part_id), error=str(exc)
            )
            continue
        if upstream.status_code != 200:
            _logger.warning(
                "in_context_write_refused",
                part_id=str(part_id),
                status=upstream.status_code,
            )
