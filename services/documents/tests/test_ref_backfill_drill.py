"""The backup drill for DESIGN-INTENT-BACKFILL, natively on real PostgreSQL 16.

``scripts/backup-restore-drill.sh`` proves backups on a Docker stack; this
sandbox has no Docker daemon, and the backfill is the first upgrade that
REWRITES stored params rather than only adding columns, so its own drill runs
here, with the same tools ``scripts/backup.sh`` uses (``pg_dump -Fc
--no-owner --no-privileges``, ``pg_restore``):

1. a part at schema 0015 with a pick stored WITHOUT a name (the population);
2. back up;
3. upgrade to 0016, open (the backfill writes the name), see the journal;
4. revert: the part's params are byte-for-byte what was backed up;
5. restore the backup into a fresh database: it dumps byte-for-byte equal to
   the backup, and the restored part is the pre-upgrade part.
"""

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.ref_names import (
    RefNameOutcome,
    RefNamesApplyRequest,
    RefNamesReport,
    signature_digest,
)

OWNER = "6f3f6b64-0000-4000-8000-0000000d0001"
PART = "6f3f6b64-0000-4000-8000-0000000d0002"
SKETCH = "6f3f6b64-0000-4000-8000-0000000d0003"
EXTRUDE = "6f3f6b64-0000-4000-8000-0000000d0004"
FILLET = "6f3f6b64-0000-4000-8000-0000000d0005"

_SIGNATURE = (
    '{"subshape_type": "edge", "curve": "line", '
    '"end_a": {"x": 20.0, "y": -12.5, "z": 10.0}, '
    '"end_b": {"x": 20.0, "y": 12.5, "z": 10.0}, '
    '"midpoint": {"x": 20.0, "y": 0.0, "z": 10.0}, "length_mm": 25.0}'
)
_FEATURES = [
    (
        SKETCH,
        0,
        "sketch",
        '{"plane": {"kind": "datum_plane", "plane": "XY"}, "entities": [], '
        '"constraints": []}',
    ),
    (
        EXTRUDE,
        1,
        "extrude",
        f'{{"profile": {{"kind": "feature", "feature_id": "{SKETCH}"}}, '
        '"distance_mm": 10.0, "operation": "add", "direction": "normal"}',
    ),
    (
        FILLET,
        2,
        "fillet",
        '{"edges": {"kind": "edges", "refs": [{"kind": "subshape", '
        f'"feature_id": "{EXTRUDE}", "subshape_type": "edge", "selector": '
        f'{{"selector_version": 1, "signature": {_SIGNATURE}}}}}]}}, '
        '"radius_mm": 2.0}',
    ),
]


def _run(*args: str) -> subprocess.CompletedProcess[bytes]:
    done = subprocess.run(args, capture_output=True, check=False)
    assert done.returncode == 0, done.stderr.decode()[-2000:]
    return done


def _socket(url: str) -> tuple[str, str]:
    """(socket dir, database) of a scratch-server URL."""
    database = url.split("@/")[1].split("?")[0]
    return url.split("host=")[1], database


def _psql(bin_dir: Path, url: str, sql: str) -> str:
    host, database = _socket(url)
    out = _run(
        str(bin_dir / "psql"), "-h", host, "-U", "loft", "-d", database,
        "-v", "ON_ERROR_STOP=1", "-At", "-c", sql,
    )  # fmt: skip
    return out.stdout.decode().strip()


def _dump(bin_dir: Path, url: str, *, custom: Path | None = None) -> bytes:
    host, database = _socket(url)
    args = [str(bin_dir / "pg_dump"), "-h", host, "-U", "loft", "-d", database]
    args += ["--no-owner", "--no-privileges"]
    if custom is not None:
        _run(*args, "-Fc", "-f", str(custom))
        return custom.read_bytes()
    # pg_dump 16.10+ brackets a plain dump in restrict / unrestrict lines
    # with a random key (CVE-2025-8714); everything else is the data.
    lines = _run(*args).stdout.splitlines(keepends=True)
    return b"".join(
        line for line in lines if not line.startswith((b"\\restrict", b"\\unrestrict"))
    )


def _seed(bin_dir: Path, url: str) -> None:
    _psql(
        bin_dir,
        url,
        "INSERT INTO parts (id, owner_id, name, tree_version, history_cursor) "
        f"VALUES ('{PART}', '{OWNER}', 'Old bracket', 3, NULL)",
    )
    for feature_id, index, kind, params in _FEATURES:
        _psql(
            bin_dir,
            url,
            "INSERT INTO features (id, part_id, order_index, name, type, "
            f"param_version, params) VALUES ('{feature_id}', '{PART}', {index}, "
            f"'F{index}', '{kind}', 1, '{params}')",
        )
    for source, target in ((EXTRUDE, SKETCH), (FILLET, EXTRUDE)):
        _psql(
            bin_dir,
            url,
            "INSERT INTO feature_dependencies (part_id, feature_id, "
            f"references_feature_id) VALUES ('{PART}', '{source}', '{target}')",
        )


def _report(signature: dict[str, Any]) -> RefNamesReport:
    return RefNamesReport(
        tree_version=3,
        kernel="drill",
        outcomes=[
            RefNameOutcome(
                feature_id=uuid.UUID(FILLET),
                path="/edges/refs/0",
                kind="edge",
                signature_sha256=signature_digest(signature),
                outcome="named",
                topo_name="drill:a|drill:b",
            )
        ],
    )


def test_backup_upgrade_open_journal_revert_restore(
    pg_server: Any,
    pg_url: str,
    alembic_runner: Any,
    tmp_path: Path,
) -> None:
    bin_dir: Path = pg_server.bin_dir
    if not (bin_dir / "pg_dump").exists():  # pragma: no cover - same package
        pytest.skip("pg_dump not installed beside initdb")
    alembic_runner(pg_url, "0015", downgrade=True)
    _seed(bin_dir, pg_url)
    fillet_before = _psql(
        bin_dir, pg_url, f"SELECT params::text FROM features WHERE id = '{FILLET}'"
    )
    backup = tmp_path / "documents.dump"
    _dump(bin_dir, pg_url, custom=backup)
    plain_backup = _dump(bin_dir, pg_url)

    # Upgrade, then open: documents serves the tree, the report is applied.
    alembic_runner(pg_url, "head")
    headers = {PRINCIPAL_HEADER: OWNER}
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        need = client.get(f"/api/v1/parts/{PART}/ref-names-request", headers=headers)
        assert need.status_code == 200, need.text
        assert need.json()["needed"] is True
        fillet = need.json()["request"]["features"][2]["feature"]
        signature = fillet["params"]["edges"]["refs"][0]["selector"]["signature"]
        applied = client.post(
            f"/api/v1/parts/{PART}/ref-names",
            content=RefNamesApplyRequest(
                tree_version=3, report=_report(signature)
            ).model_dump_json(),
            headers={**headers, "content-type": "application/json"},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["result"] == "written"
        assert _psql(
            bin_dir,
            pg_url,
            "SELECT kind || ':' || tree_version_before || '->' || tree_version_after "
            "FROM ref_name_backfills",
        ) == ("backfill:3->4")
        named = _psql(
            bin_dir,
            pg_url,
            "SELECT params #>> '{edges,refs,0,selector,signature,topo_name}' "
            f"FROM features WHERE id = '{FILLET}'",
        )
        assert named == "drill:a|drill:b"

        reverted = client.post(
            f"/api/v1/parts/{PART}/ref-names/revert", headers=headers
        )
        assert reverted.status_code == 200, reverted.text
        assert reverted.json()["features_restored"] == 1
    assert (
        _psql(
            bin_dir, pg_url, f"SELECT params::text FROM features WHERE id = '{FILLET}'"
        )
        == fillet_before
    )

    # Restore the backup into a fresh database: it IS the backup.
    _psql(bin_dir, pg_url, "CREATE DATABASE drill_restored")
    restored_url = pg_url.replace(_socket(pg_url)[1], "drill_restored")
    host, _db = _socket(restored_url)
    _run(
        str(bin_dir / "pg_restore"), "-h", host, "-U", "loft", "-d", "drill_restored",
        "--no-owner", "--no-privileges", str(backup),
    )  # fmt: skip
    assert _dump(bin_dir, restored_url) == plain_backup
    assert (
        _psql(
            bin_dir,
            restored_url,
            f"SELECT params::text FROM features WHERE id = '{FILLET}'",
        )
        == fillet_before
    )
    assert _psql(bin_dir, restored_url, "SELECT version_num FROM alembic_version") == (
        "0015"
    )
