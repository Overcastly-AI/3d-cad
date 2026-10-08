"""Orchestrate the history-name backfill (DESIGN-INTENT-BACKFILL).

The gateway is the only service that talks to both documents and geometry, so
it runs the backfill's three hops (docs/OPERATIONS.md §5, RESEARCH §14
"Backfill"):

1. documents ``GET /parts/{id}/ref-names-request``: is the part pending, and
   if so its WHOLE tree (rollback ignored, params upcast);
2. geometry ``POST /ref-names``: a cold rebuild that reports, per stored pick
   without a name, the name a fresh pick would store, but only where the
   strict tier pins one subshape and the round trip holds;
3. documents ``POST /parts/{id}/ref-names``: the locked, guarded write.

Two triggers share :func:`run_backfill`:

- **on open**: after a non-preview evaluate whose tree holds an unnamed pick,
  as a Starlette background task (after the response, like the last-evaluate
  bookkeeping). Best effort: every failure is logged and swallowed. A geometry
  error writes nothing and leaves the part pending, so the next open retries;
  a stale write (the user edited while geometry ran) is dropped by documents
  and also retried.
- **the operator sweep**: ``python -m gateway.ref_backfill`` (``--dry-run``,
  ``--part``, ``--limit``, ``--revert PART``), for parts nobody opens.

``loft_ref_backfill_runs_total{trigger,result}`` counts every run.
"""

import argparse
import asyncio
import os
import sys
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import httpx2 as httpx
from fastapi import Request, status
from loft_wire.features import EvaluateTreeRequest
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.ref_names import (
    RefBackfillPartList,
    RefNamesApplyRequest,
    RefNamesApplyResult,
    RefNamesReport,
    RefNamesRequestResponse,
    RefNamesRevertResult,
    tree_needs_ref_names,
)
from py_kit import get_logger
from py_kit.metrics import record_ref_backfill_run

from gateway.affinity import forward_geometry, parse_worker_urls
from gateway.db import User
from gateway.parts import forward_documents

_logger = get_logger("gateway.ref_backfill")

Trigger = Literal["open", "sweep"]
RunResult = Literal["written", "unchanged", "stale", "dry_run", "not_needed", "failed"]

#: ``(method, path, json body, query) -> response`` against documents, with the
#: part owner's principal already attached.
DocumentsCall = Callable[
    [str, str, str | None, dict[str, str] | None], Awaitable[httpx.Response]
]
#: ``(path, json body) -> response`` against geometry (POST).
GeometryCall = Callable[[str, str], Awaitable[httpx.Response]]


@dataclass
class RunSummary:
    """What one run did, for the CLI's report and the tests."""

    result: RunResult
    outcomes: Counter[str] = field(default_factory=Counter[str])
    refs_written: int = 0
    detail: str = ""


async def run_backfill(
    documents: DocumentsCall,
    geometry: GeometryCall,
    part_id: uuid.UUID,
    *,
    trigger: Trigger,
    dry_run: bool = False,
    force: bool = False,
) -> RunSummary:
    """One backfill of one part. Never raises: a failure is a ``failed``
    summary (and writes nothing)."""
    try:
        summary = await _run(
            documents, geometry, part_id, dry_run=dry_run, force=force, trigger=trigger
        )
    # Deliberately broad: the on-open caller is a background task that must
    # never fail, and the sweep reports a failed part and moves on.
    except Exception as exc:
        summary = RunSummary(result="failed", detail=type(exc).__name__)
    record_ref_backfill_run(trigger, summary.result)
    log = _logger.warning if summary.result == "failed" else _logger.info
    log(
        "ref_backfill_run",
        part_id=str(part_id),
        trigger=trigger,
        result=summary.result,
        refs_written=summary.refs_written,
        outcomes=dict(summary.outcomes),
        detail=summary.detail,
    )
    return summary


async def _run(
    documents: DocumentsCall,
    geometry: GeometryCall,
    part_id: uuid.UUID,
    *,
    dry_run: bool,
    force: bool,
    trigger: Trigger,
) -> RunSummary:
    base = f"/api/v1/parts/{part_id}"
    upstream = await documents(
        "GET", f"{base}/ref-names-request", None, {"force": "true"} if force else None
    )
    if upstream.status_code != status.HTTP_200_OK:
        return RunSummary(result="failed", detail=f"documents {upstream.status_code}")
    need = RefNamesRequestResponse.model_validate_json(upstream.content)
    if not need.needed or need.request is None:
        if need.ref_names_checked_version is None and not dry_run:
            # Nothing unnamed: mark it checked so the sweep moves past it.
            empty = RefNamesReport(
                tree_version=need.tree_version, kernel="", outcomes=[]
            )
            await _apply(documents, base, need.tree_version, empty, dry_run, trigger)
        return RunSummary(result="not_needed")
    evaluated = await geometry("/api/v1/ref-names", need.request.model_dump_json())
    if evaluated.status_code != status.HTTP_200_OK:
        # Nothing is written, and the part stays pending: the next run retries.
        return RunSummary(result="failed", detail=f"geometry {evaluated.status_code}")
    report = RefNamesReport.model_validate_json(evaluated.content)
    outcomes = Counter(outcome.outcome for outcome in report.outcomes)
    applied = await _apply(documents, base, need.tree_version, report, dry_run, trigger)
    if applied is None:
        return RunSummary(result="failed", outcomes=outcomes, detail="documents write")
    return RunSummary(
        result=applied.result, outcomes=outcomes, refs_written=applied.refs_written
    )


async def _apply(
    documents: DocumentsCall,
    base: str,
    tree_version: int,
    report: RefNamesReport,
    dry_run: bool,
    trigger: Trigger,
) -> RefNamesApplyResult | None:
    body = RefNamesApplyRequest(
        tree_version=tree_version, report=report, dry_run=dry_run, trigger=trigger
    )
    response = await documents(
        "POST", f"{base}/ref-names", body.model_dump_json(), None
    )
    if response.status_code != status.HTTP_200_OK:
        return None
    return RefNamesApplyResult.model_validate_json(response.content)


# --- trigger 1: on open -------------------------------------------------------------


def needs_backfill(request: EvaluateTreeRequest) -> bool:
    """Whether an evaluated tree holds a pick without a name: the cheap,
    local pre-check that keeps a fully named part (every part made since
    DESIGN-INTENT-REFS) from paying even one extra round trip per open."""
    return tree_needs_ref_names(request.features)


async def backfill_on_open(
    http_request: Request, user: User, part_id: uuid.UUID
) -> None:
    """The evaluate route's background task. Best effort, never raises."""

    async def documents(
        method: str, path: str, body: str | None, params: dict[str, str] | None
    ) -> httpx.Response:
        return await forward_documents(http_request, user, method, path, body, params)

    async def geometry(path: str, body: str) -> httpx.Response:
        return await forward_geometry(
            http_request,
            str(user.id),
            "POST",
            path,
            service="Geometry",
            json_content=body,
        )

    await run_backfill(documents, geometry, part_id, trigger="open")


# --- trigger 2: the operator CLI ----------------------------------------------------


@dataclass
class Upstreams:
    """The two clients the CLI talks through (injectable for tests)."""

    documents: httpx.AsyncClient
    geometry: httpx.AsyncClient

    def documents_as(self, owner: uuid.UUID) -> DocumentsCall:
        async def call(
            method: str, path: str, body: str | None, params: dict[str, str] | None
        ) -> httpx.Response:
            headers = {PRINCIPAL_HEADER: str(owner)}
            if body is not None:
                headers["content-type"] = "application/json"
            return await self.documents.request(
                method, path, content=body, params=params, headers=headers
            )

        return call

    async def geometry_call(self, path: str, body: str) -> httpx.Response:
        return await self.geometry.post(
            path, content=body, headers={"content-type": "application/json"}
        )


async def sweep(
    upstreams: Upstreams,
    *,
    dry_run: bool = False,
    part: uuid.UUID | None = None,
    limit: int = 1000,
    out: Callable[[str], None] = print,
) -> int:
    """Backfill pending parts (or one named part, forced). Returns the process
    exit code: 1 when any part failed, else 0."""
    params = {"limit": str(limit)}
    if part is not None:
        params["part_id"] = str(part)
    listed = await upstreams.documents.get("/api/v1/ref-backfill/parts", params=params)
    listed.raise_for_status()
    parts = RefBackfillPartList.model_validate_json(listed.content).parts
    if part is not None and not parts:
        out(f"part {part}: not found")
        return 1
    totals: Counter[str] = Counter()
    failed = 0
    for row in parts:
        summary = await run_backfill(
            upstreams.documents_as(row.owner_id),
            upstreams.geometry_call,
            row.part_id,
            trigger="sweep",
            dry_run=dry_run,
            force=part is not None,
        )
        totals.update(summary.outcomes)
        failed += summary.result == "failed"
        outcomes = " ".join(f"{k}={v}" for k, v in sorted(summary.outcomes.items()))
        out(
            f"part {row.part_id}: {summary.result} refs_written={summary.refs_written}"
            + (f" {outcomes}" if outcomes else "")
            + (f" ({summary.detail})" if summary.detail else "")
        )
    out(
        f"{len(parts)} part(s), {failed} failed"
        + (
            ""
            if not totals
            else " | " + " ".join(f"{k}={v}" for k, v in sorted(totals.items()))
        )
        + (" | DRY RUN: nothing written" if dry_run else "")
    )
    return 1 if failed else 0


async def revert(
    upstreams: Upstreams, part: uuid.UUID, out: Callable[[str], None] = print
) -> int:
    """Undo the part's latest backfill write (documents keeps the journal)."""
    listed = await upstreams.documents.get(
        "/api/v1/ref-backfill/parts", params={"part_id": str(part)}
    )
    listed.raise_for_status()
    rows = RefBackfillPartList.model_validate_json(listed.content).parts
    if not rows:
        out(f"part {part}: not found")
        return 1
    response = await upstreams.documents_as(rows[0].owner_id)(
        "POST", f"/api/v1/parts/{part}/ref-names/revert", None, None
    )
    if response.status_code != status.HTTP_200_OK:
        out(f"part {part}: revert failed ({response.status_code})")
        return 1
    result = RefNamesRevertResult.model_validate_json(response.content)
    out(
        f"part {part}: {result.result} restored={result.features_restored} "
        f"skipped={result.features_skipped} tree_version={result.tree_version}"
    )
    return 0


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m gateway.ref_backfill",
        description="Name stored picks that predate history names "
        "(DESIGN-INTENT-BACKFILL). Back up first (docs/OPERATIONS.md §5).",
    )
    parser.add_argument("--dry-run", action="store_true", help="write nothing")
    parser.add_argument("--part", type=uuid.UUID, help="only this part (forced)")
    parser.add_argument("--limit", type=int, default=1000, help="parts per run")
    parser.add_argument(
        "--revert", type=uuid.UUID, metavar="PART", help="undo PART's last write"
    )
    return parser.parse_args(argv)


#: The gateway's own upstream variables (the same names and defaults as
#: ``GatewaySettings``, read directly: importing ``gateway.main`` builds the
#: whole app, JWT posture check included, which a CLI has no use for).
_DOCUMENTS_URL = ("DOCUMENTS_URL", "http://localhost:8001")
_GEOMETRY_URL = ("GEOMETRY_URL", "http://localhost:8002")

#: A cold rebuild of a big part is the slowest thing the backfill does; the
#: sweep is not interactive, so it waits longer than a modeller's request.
_SWEEP_GEOMETRY_TIMEOUT_S = 600.0


async def _main(args: argparse.Namespace) -> int:
    documents_url = os.environ.get(*_DOCUMENTS_URL)
    geometry_url = parse_worker_urls(os.environ.get(*_GEOMETRY_URL))[0]
    async with (
        httpx.AsyncClient(base_url=documents_url, timeout=60.0) as documents,
        httpx.AsyncClient(
            base_url=geometry_url, timeout=_SWEEP_GEOMETRY_TIMEOUT_S
        ) as geometry,
    ):
        upstreams = Upstreams(documents=documents, geometry=geometry)
        if args.revert is not None:
            return await revert(upstreams, args.revert)
        return await sweep(
            upstreams, dry_run=args.dry_run, part=args.part, limit=args.limit
        )


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(_parse(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    raise SystemExit(main())
