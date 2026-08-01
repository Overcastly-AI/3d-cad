"""Shared HTTP + modeling helpers for the self-host proof scripts.

Stdlib only (urllib + json + struct), so anything built on it runs on a bare
Docker host with no Python toolchain beyond ``python3``.

Two scripts import this, and they must stay in agreement about what a "real
modeling round-trip" is — that is the whole reason it is one module and not
two copies (CLAUDE.md DRY rule):

* :mod:`compose-roundtrip <scripts.compose-roundtrip>` — the deploy-path proof
  (build → boot → migrate → model → export), and
* :mod:`backup-verify <scripts.backup-verify>` — the backup/restore drill, which
  seeds a part with the SAME feature tree, records its evaluated volume and
  content-addressed mesh id, and re-asserts both after the volumes have been
  destroyed and the dumps restored.

The shared 40 x 25 x 10 mm block matters to both: its volume is an exact
analytic number, so "the restored tree still builds the same solid" is a
comparison against 10 000 mm^3, not against a fixture nobody can check.
"""

from __future__ import annotations

import json
import struct
import urllib.error
import urllib.request
from typing import Any, cast

#: The §6 worked example: a 40 x 25 mm rectangle extruded 10 mm.
WIDTH_MM = 40.0
HEIGHT_MM = 25.0
DEPTH_MM = 10.0
EXPECTED_VOLUME_MM3 = WIDTH_MM * HEIGHT_MM * DEPTH_MM

#: Relative tolerance on the evaluated volume. The exact value is a golden
#: (services/geometry/tests asserts abs=1e-6 on the same model); these scripts
#: guard the deploy path, so they only need to prove the body that came back
#: is the body that was modeled.
VOLUME_RTOL = 1e-9

#: Evaluate crosses gateway → documents → geometry (OCCT); the gateway's own
#: upstream budget is 30 s, so anything slower is already a 504 upstream.
REQUEST_TIMEOUT_S = 60.0

#: GLB container constants (glTF 2.0 binary, spec §4.4.3).
GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = 0x4E4F534A


class CheckFailed(Exception):
    """A round-trip assertion did not hold."""


class Response:
    """Minimal HTTP response holder (status + raw body)."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def json(self) -> dict[str, Any]:
        try:
            parsed: Any = json.loads(self.body)
        except ValueError as exc:  # pragma: no cover - diagnostic path
            raise CheckFailed(
                f"response body is not JSON: {exc}: {self.text()}"
            ) from exc
        if not isinstance(parsed, dict):
            raise CheckFailed(f"expected a JSON object, got {type(parsed).__name__}")
        return cast("dict[str, Any]", parsed)

    def text(self, limit: int = 400) -> str:
        return self.body[:limit].decode("utf-8", "replace")


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Response:
    """One HTTP call; HTTP errors come back as a Response, not an exception."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base_url}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
            return Response(response.status, response.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read())
    except urllib.error.URLError as exc:
        raise CheckFailed(f"{method} {path} did not connect: {exc.reason}") from exc


def expect(response: Response, status: int, what: str) -> dict[str, Any]:
    """Assert the status code and return the decoded JSON body."""
    if response.status != status:
        raise CheckFailed(
            f"{what}: expected HTTP {status}, got {response.status} — {response.text()}"
        )
    return response.json()


def sketch_params() -> dict[str, Any]:
    """A fully-constrained 40 x 25 rectangle on XY (DOF 0).

    Entities are drawn deliberately sloppily: the constraint solver, not the
    input coordinates, has to land the analytic corners — so a stack whose
    solver never ran cannot accidentally pass the volume assertion.
    """

    def line(
        eid: str, start: tuple[float, float], end: tuple[float, float]
    ) -> dict[str, Any]:
        return {
            "id": eid,
            "kind": "line",
            "start": {"x": start[0], "y": start[1]},
            "end": {"x": end[0], "y": end[1]},
        }

    def coincident(a: tuple[str, str], b: tuple[str, str]) -> dict[str, Any]:
        return {
            "kind": "coincident",
            "a": {"entity": a[0], "point": a[1]},
            "b": {"entity": b[0], "point": b[1]},
        }

    return {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            line("e1", (0.0, 0.0), (38.0, 1.0)),
            line("e2", (39.0, 0.5), (41.0, 24.0)),
            line("e3", (40.5, 26.0), (-1.0, 25.5)),
            line("e4", (0.5, 24.5), (-0.5, 1.0)),
        ],
        "constraints": [
            coincident(("e1", "end"), ("e2", "start")),
            coincident(("e2", "end"), ("e3", "start")),
            coincident(("e3", "end"), ("e4", "start")),
            coincident(("e4", "end"), ("e1", "start")),
            {"kind": "horizontal", "entity": "e1"},
            {"kind": "vertical", "entity": "e2"},
            {"kind": "horizontal", "entity": "e3"},
            {"kind": "vertical", "entity": "e4"},
            {"kind": "distance", "entity": "e1", "value_mm": WIDTH_MM},
            {"kind": "distance", "entity": "e2", "value_mm": HEIGHT_MM},
            {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
        ],
    }


def parse_glb(blob: bytes) -> dict[str, Any]:
    """Validate the GLB container and return its parsed JSON chunk."""
    if len(blob) < 20:
        raise CheckFailed(f"mesh is too short to be a GLB ({len(blob)} bytes)")
    magic, version, declared = struct.unpack_from("<4sII", blob, 0)
    if magic != GLB_MAGIC:
        raise CheckFailed(f"mesh does not start with the glTF magic: {magic!r}")
    if version != 2:
        raise CheckFailed(f"unexpected GLB version {version}")
    if declared != len(blob):
        raise CheckFailed(
            f"GLB declares {declared} bytes, body is {len(blob)} — truncated"
        )
    chunk_length, chunk_type = struct.unpack_from("<II", blob, 12)
    if chunk_type != GLB_JSON_CHUNK:
        raise CheckFailed(f"first GLB chunk is not JSON (type {chunk_type:#x})")
    document: Any = json.loads(blob[20 : 20 + chunk_length])
    if not isinstance(document, dict):
        raise CheckFailed("GLB JSON chunk is not an object")
    return cast("dict[str, Any]", document)


def assert_glb_has_geometry(blob: bytes) -> dict[str, Any]:
    """Parse a GLB and assert it carries real geometry, not an empty scene."""
    document = parse_glb(blob)
    meshes: list[Any] = list(document.get("meshes") or [])
    accessors: list[Any] = list(document.get("accessors") or [])
    if not meshes or not accessors:
        raise CheckFailed(
            "GLB carries no geometry "
            f"(meshes={len(meshes)}, accessors={len(accessors)})"
        )
    return document
