#!/usr/bin/env python3
"""Structural invariants on the compose stack (engineering audit G1/G3).

The CHEAP half of the compose gate: renders the config (no daemon, no image
pulls — runnable in a container with the registry blocked) and asserts the
structural invariants. The expensive half — a real ``docker compose up`` and
a modeling round-trip on a live stack — is ``scripts/compose-smoke.sh`` (CI
workflow ``deploy-path``); this file keeps the regressions visible on every
push without paying for an image build. Invariants:

1. G1 — geometry carries S3 credentials whose VALUES equal the MinIO root
   credentials (anchor-sourced in docker-compose.yml, so they cannot drift),
   plus a non-empty ``S3_URL``. Without them every mesh put/get 403s.
2. G3 — documents (:8001, trusts ``X-Loft-User``) and geometry (:8002) are
   NOT host-published in the base file; the gateway (:8000) is. The dev
   overlay may publish them, but only loopback-bound (127.0.0.1).
3. minio-init bootstraps the bucket with the same anchor-sourced credentials.
4. Gateway and documents point at DIFFERENT databases, each created by
   deploy/docker/postgres-init — both alembic trees start at revision "0001"
   in the default ``alembic_version`` table, so one shared database makes the
   second service's first migration silently a no-op (found by the first real
   run of the stack, 2026-07-25).

Stdlib only (subprocess + json): runnable locally and in the CI ``compose``
job with no Python deps. Run from the repo root:

    python3 scripts/check-compose.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE = ["-f", "docker-compose.yml"]
DEV = ["-f", "docker-compose.yml", "-f", "docker-compose.dev.yml"]


def render(files: list[str]) -> dict[str, Any]:
    """Render a compose file set to its canonical JSON config."""
    out = subprocess.run(
        ["docker", "compose", *files, "config", "--format", "json"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    config: dict[str, Any] = json.loads(out)
    return config


def env(service: dict[str, Any]) -> dict[str, str]:
    environment: dict[str, str] = service.get("environment") or {}
    return environment


def ports(service: dict[str, Any]) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = service.get("ports") or []
    return mappings


def database_of(dsn: str) -> str:
    """Database name from a postgres DSN ('' when absent/malformed)."""
    return urlsplit(dsn).path.lstrip("/")


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {message}")
        if not ok:
            failures.append(message)

    base = render(BASE)["services"]
    dev = render(DEV)["services"]

    print("base: G1 — geometry S3 credentials match MinIO root credentials")
    minio_user = env(base["minio"]).get("MINIO_ROOT_USER")
    minio_password = env(base["minio"]).get("MINIO_ROOT_PASSWORD")
    geometry_env = env(base["geometry"])
    check(bool(minio_user), "minio sets MINIO_ROOT_USER")
    check(bool(minio_password), "minio sets MINIO_ROOT_PASSWORD")
    check(bool(geometry_env.get("S3_URL")), "geometry sets S3_URL (S3 store active)")
    check(bool(geometry_env.get("S3_BUCKET")), "geometry sets S3_BUCKET")
    check(
        geometry_env.get("S3_ACCESS_KEY_ID") == minio_user,
        "geometry S3_ACCESS_KEY_ID == minio MINIO_ROOT_USER",
    )
    check(
        geometry_env.get("S3_SECRET_ACCESS_KEY") == minio_password,
        "geometry S3_SECRET_ACCESS_KEY == minio MINIO_ROOT_PASSWORD",
    )
    check(
        env(base["minio-init"]).get("MINIO_ROOT_USER") == minio_user
        and env(base["minio-init"]).get("MINIO_ROOT_PASSWORD") == minio_password,
        "minio-init bootstraps the bucket with the same credentials",
    )

    print("base: one database per schema-owning service")
    db_env = env(base["db"])
    gateway_db = database_of(env(base["gateway"]).get("POSTGRES_URL", ""))
    documents_db = database_of(env(base["documents"]).get("POSTGRES_URL", ""))
    check(
        bool(gateway_db) and bool(documents_db) and gateway_db != documents_db,
        f"gateway ({gateway_db}) and documents ({documents_db}) use DIFFERENT "
        "databases — both alembic trees start at revision 0001 in the default "
        "alembic_version table, so sharing one silently breaks the second",
    )
    check(
        gateway_db == db_env.get("GATEWAY_DB"),
        f"the db init script creates the gateway database ({gateway_db})",
    )
    check(
        documents_db == db_env.get("DOCUMENTS_DB"),
        f"the db init script creates the documents database ({documents_db})",
    )

    print("base: G3 — internal services unpublished, gateway published")
    check(not ports(base["documents"]), "documents has NO host port")
    check(not ports(base["geometry"]), "geometry has NO host port")
    check(bool(ports(base["gateway"])), "gateway is host-published")

    print("dev overlay: internal-service debug ports are loopback-only")
    for name in ("documents", "geometry"):
        mappings = ports(dev[name])
        check(
            bool(mappings) and all(m.get("host_ip") == "127.0.0.1" for m in mappings),
            f"dev overlay binds {name} to 127.0.0.1 only",
        )

    if failures:
        print(f"\ncheck-compose: FAILED ({len(failures)} invariant(s) violated)")
        return 1
    print("\ncheck-compose: all compose invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
