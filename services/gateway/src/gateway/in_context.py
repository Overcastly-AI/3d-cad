"""In-context links: carry geometry's resolved values to documents
(ASM-A3-IN-CONTEXT, RESEARCH §24).

Geometry resolves each in-context link inside its context assembly's
evaluation and says which values changed; documents stores the last resolved
value so the edited part rebuilds the same way out of context. Neither talks
to the other (CLAUDE.md), so the gateway joins them after
``/geometry/assembly/evaluate``.

Only a COMMITTED evaluation may write. The caller opts in (``write_back``;
the workspace's own evaluation does, a live preview of a draft joint or move
never does), and the gateway then checks that the request is the assembly as
stored at its version: the same instances at the same poses, the same mates
and patterns. Anything else is a draft, and nothing is written. One documents
write per edited part, as the caller (documents checks ownership and that each
item's link is still exactly the one resolved). A failed write is logged and
the evaluation still answers: the next committed evaluation writes it again.
"""

import uuid
from collections import defaultdict
from typing import Any

from fastapi import Request
from loft_wire.assemblies import EvaluateAssemblyRequest, EvaluateAssemblyResult
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
                host_occurrence_id=status.host_occurrence_id,
                occurrence_id=status.occurrence_id,
                part_id=status.referenced_part_id,
                edge=status.edge,
                resolved=status.resolved,
            )
        )
    return {
        part_id: InContextResolvedWrite(items=part_items)
        for part_id, part_items in items.items()
    }


def _structure(request: EvaluateAssemblyRequest) -> Any:
    """What makes a request the stored assembly (and not a draft): its
    version, and every instance's pose, grounding, part and sub-assembly
    structure, every mate, every pattern and every mirror, at every level. Part features
    are left out: a part edit is not an assembly draft."""

    def level(req: EvaluateAssemblyRequest) -> Any:
        return {
            "instances": sorted(
                (
                    str(inst.instance_id),
                    inst.part_key,
                    inst.placement.model_dump_json(),
                    inst.grounded,
                    None if inst.sub_assembly is None else level(inst.sub_assembly),
                )
                for inst in req.instances
            ),
            "mates": sorted(
                (str(m.mate_id), m.order_index, m.mate.model_dump_json())
                for m in req.mates
            ),
            "patterns": sorted(p.model_dump_json() for p in req.patterns),
            "mirrors": sorted(m.model_dump_json() for m in req.mirrors),
        }

    return (str(request.assembly_id), request.version, level(request))


async def _is_committed(
    http_request: Request, user: User, request: EvaluateAssemblyRequest
) -> bool:
    """Whether *request* is the assembly as documents stores it now."""
    upstream = await forward_documents(
        http_request,
        user,
        "GET",
        f"/api/v1/assemblies/{request.assembly_id}/evaluation-request",
    )
    if upstream.status_code != 200:
        return False
    stored = EvaluateAssemblyRequest.model_validate_json(upstream.content)
    return _structure(stored) == _structure(request)


async def write_back(
    http_request: Request,
    user: User,
    request: EvaluateAssemblyRequest,
    result: EvaluateAssemblyResult,
) -> None:
    """Store every changed resolved value of *result* in documents, when
    *request* is the committed assembly (module docstring)."""
    writes = resolved_writes(result)
    if not writes:
        return
    try:
        committed = await _is_committed(http_request, user, request)
    except Exception as exc:
        _logger.warning("in_context_check_failed", error=str(exc))
        return
    if not committed:
        _logger.info(
            "in_context_write_skipped_draft", assembly_id=str(request.assembly_id)
        )
        return
    for part_id, body in writes.items():
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
