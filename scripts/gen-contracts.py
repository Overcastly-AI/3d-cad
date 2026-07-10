#!/usr/bin/env python3
"""Export OpenAPI schemas from the service app factories (``just gen`` step 1).

Pydantic models are the single source of truth (CLAUDE.md DRY rule): each
service's ``build_app()`` is imported, its OpenAPI document dumped to
``packages/contracts/<service>.openapi.json``. Output is deterministic —
sorted keys, 2-space indent, trailing newline, no timestamps — so the drift
check (``just gen-check``) never flaps.

Run from the repo root: ``uv run scripts/gen-contracts.py [--out DIR]``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# gateway.main fail-fasts at import on the JWT secret posture (fail-closed:
# unset LOFT_ENV + unset JWT_SECRET refuses to boot). Schema export needs no
# real secret, so opt into the dev fallback explicitly — BEFORE the imports.
os.environ.setdefault("LOFT_ENV", "dev")

from documents.main import build_app as build_documents
from fastapi import FastAPI
from gateway.main import build_app as build_gateway
from geometry.main import build_app as build_geometry

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "packages" / "contracts"

#: One entry per service — extend here when a new service lands.
APP_FACTORIES: dict[str, Callable[[], FastAPI]] = {
    "gateway": build_gateway,
    "documents": build_documents,
    "geometry": build_geometry,
}


def dump_schema(service: str, factory: Callable[[], FastAPI], out_dir: Path) -> Path:
    """Build the app, render its OpenAPI document deterministically."""
    schema: dict[str, Any] = factory().openapi()
    target = out_dir / f"{service}.openapi.json"
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output directory (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for service, factory in sorted(APP_FACTORIES.items()):
        target = dump_schema(service, factory, out_dir)
        print(f"gen-contracts: wrote {os.path.relpath(target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
