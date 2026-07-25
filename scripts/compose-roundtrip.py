#!/usr/bin/env python3
"""Real end-to-end round-trip against a RUNNING stack, over the gateway only.

This is the runtime half of the self-host proof (the config half is
``scripts/check-compose.py``). It drives exactly what a self-hoster's browser
drives — register → part → sketch → extrude → evaluate → fetch the mesh →
export STEP — through the published gateway port and nothing else, then
asserts the internal services are NOT reachable from the host.

Why it exists: a rendered-config check cannot catch a wrong *runtime*. The
audit-G1 bug (geometry given ``S3_URL`` but no credentials → every mesh
put/get 403s → blank viewport) produces a perfectly valid compose config; it
only shows up when a real request walks the whole path. So the mesh fetch
below is the load-bearing assertion: real GLB bytes, parsed, with geometry in
them — not a 403, not an empty body, not a JSON error envelope.

Stdlib only (urllib + json + socket): runnable on any Docker host without a
Python toolchain beyond python3. Usually invoked by
``scripts/compose-smoke.sh``; standalone::

    python3 scripts/compose-roundtrip.py --base-url http://127.0.0.1:8000

Exit code 0 = every assertion held; 1 = a numbered check failed (the failure
line names the check, the URL, and what came back).
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any, cast

#: Canonical internal ports the base compose file deliberately does NOT
#: publish (audit G3: documents trusts the gateway-verified X-Loft-User
#: header, so host-publishing it is forged-header cross-tenant access).
INTERNAL_PORTS = {"documents": 8001, "geometry": 8002}

#: The §6 worked example: a 40 x 25 mm rectangle extruded 10 mm.
WIDTH_MM = 40.0
HEIGHT_MM = 25.0
DEPTH_MM = 10.0
EXPECTED_VOLUME_MM3 = WIDTH_MM * HEIGHT_MM * DEPTH_MM

#: Relative tolerance on the evaluated volume. The exact value is a golden
#: (services/geometry/tests asserts abs=1e-6 on the same model); this script
#: guards the deploy path, so it only needs to prove the body that came back
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


def assert_internal_ports_closed(host: str) -> None:
    """The G3 posture, at RUNTIME: only the gateway is reachable from the host."""
    for name, port in sorted(INTERNAL_PORTS.items()):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(2.0)
            if probe.connect_ex((host, port)) == 0:
                raise CheckFailed(
                    f"{name} answers on {host}:{port} — the base compose stack must "
                    "publish the gateway ONLY (audit G3). Are you running the dev "
                    "overlay, or is a stray local service holding the port?"
                )


def run(base_url: str, host: str) -> None:
    """Drive the full round-trip; raises CheckFailed on the first bad step."""
    steps: list[str] = []

    def ok(message: str) -> None:
        steps.append(message)
        print(f"  ok  {message}", flush=True)

    # 1. Register — proves the gateway's identity schema really migrated.
    email = f"selfhost-{uuid.uuid4().hex[:12]}@example.com"
    registered = expect(
        request(
            base_url,
            "POST",
            "/api/v1/auth/register",
            payload={"email": email, "password": "hunter2-passphrase"},
        ),
        201,
        "register",
    )
    token = str(registered["access_token"])
    ok(f"registered {email} (gateway schema live)")

    # 2. Create a part — proves the documents schema migrated and the
    #    gateway→documents hop carries the verified principal.
    part = expect(
        request(
            base_url,
            "POST",
            "/api/v1/parts",
            token=token,
            payload={"name": "self-host-proof"},
        ),
        201,
        "create part",
    )
    part_id = str(part["id"])
    ok(f"created part {part_id} (documents schema live)")

    # 3. Sketch + 4. extrude — the feature tree a real user authors.
    sketch = expect(
        request(
            base_url,
            "POST",
            f"/api/v1/parts/{part_id}/features",
            token=token,
            payload={
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": sketch_params()},
                "expected_tree_version": 0,
            },
        ),
        201,
        "create sketch feature",
    )
    sketch_id = str(sketch["feature"]["id"])
    tree_version = int(sketch["tree_version"])
    ok("authored Sketch1")

    expect(
        request(
            base_url,
            "POST",
            f"/api/v1/parts/{part_id}/features",
            token=token,
            payload={
                "name": "Extrude1",
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": sketch_id},
                        "distance_mm": DEPTH_MM,
                        "operation": "add",
                        "direction": "normal",
                    },
                },
                "expected_tree_version": tree_version,
            },
        ),
        201,
        "create extrude feature",
    )
    ok("authored Extrude1")

    # 5. Evaluate — gateway → documents → geometry (OCCT) → S3/MinIO put.
    result = expect(
        request(base_url, "POST", f"/api/v1/parts/{part_id}/evaluate", token=token),
        200,
        "evaluate",
    )
    features: list[Any] = list(result["features"])
    for entry in features:
        if not isinstance(entry, dict):  # pragma: no cover - defensive
            raise CheckFailed(f"unexpected feature entry: {entry!r}")
        feature = cast("dict[str, Any]", entry)
        if feature.get("status") != "ok":
            raise CheckFailed(
                f"feature {feature.get('name')} did not evaluate: {feature}"
            )
    mesh_id = result.get("mesh_glb_id")
    if not isinstance(mesh_id, str) or not mesh_id.startswith("sha256:"):
        raise CheckFailed(
            f"evaluate returned no content-addressed mesh id: {mesh_id!r}"
        )

    raw_properties: Any = result.get("properties")
    if not isinstance(raw_properties, dict):
        raise CheckFailed(f"evaluate returned no mass properties: {raw_properties!r}")
    properties = cast("dict[str, Any]", raw_properties)
    volume = float(properties["volume"])
    if abs(volume - EXPECTED_VOLUME_MM3) > VOLUME_RTOL * EXPECTED_VOLUME_MM3:
        raise CheckFailed(
            f"evaluated volume {volume} mm^3, expected {EXPECTED_VOLUME_MM3} mm^3"
        )
    ok(f"evaluated: volume {volume:g} mm^3, mesh {mesh_id[:19]}...")

    # 6. Fetch the mesh — THE credential-path assertion (audit G1). The mesh
    #    was written to MinIO by geometry and is read back out of it here; a
    #    stack whose S3 credentials are missing/mismatched 403s and never
    #    reaches this line with real bytes.
    mesh = request(base_url, "GET", f"/api/v1/geometry/meshes/{mesh_id}", token=token)
    if mesh.status != 200:
        raise CheckFailed(
            f"mesh fetch: expected HTTP 200, got {mesh.status} — {mesh.text()}"
        )
    document = parse_glb(mesh.body)
    meshes: list[Any] = list(document.get("meshes") or [])
    accessors: list[Any] = list(document.get("accessors") or [])
    if not meshes or not accessors:
        raise CheckFailed(
            "GLB carries no geometry "
            f"(meshes={len(meshes)}, accessors={len(accessors)})"
        )
    ok(
        f"fetched mesh from object storage: {len(mesh.body)} bytes, "
        f"valid GLB, {len(meshes)} mesh(es)"
    )

    # ...and the same artifact is NOT served to an anonymous caller.
    anonymous = request(base_url, "GET", f"/api/v1/geometry/meshes/{mesh_id}")
    if anonymous.status != 401:
        raise CheckFailed(
            f"unauthenticated mesh fetch returned {anonymous.status}, expected 401"
        )
    ok("unauthenticated mesh fetch is 401")

    # 7. Export STEP — the file the engineer takes to a machine shop.
    step = request(
        base_url, "POST", f"/api/v1/parts/{part_id}/export?format=step", token=token
    )
    if step.status != 200:
        raise CheckFailed(
            f"STEP export: expected HTTP 200, got {step.status} — {step.text()}"
        )
    if not step.body.startswith(b"ISO-10303-21"):
        raise CheckFailed(f"STEP export is not a part-21 file: {step.text(80)!r}")
    if b"ADVANCED_FACE" not in step.body or not step.body.rstrip().endswith(
        b"END-ISO-10303-21;"
    ):
        raise CheckFailed("STEP export has no B-rep faces or is truncated")
    ok(f"exported STEP: {len(step.body)} bytes, part-21 with B-rep faces")

    # 8. Security posture at runtime, not just in the rendered config.
    assert_internal_ports_closed(host)
    ok("internal services (documents, geometry) are unreachable from the host")

    print(f"\nround-trip: {len(steps)} checks passed against {base_url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="published gateway origin (default: %(default)s)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host the stack publishes on, for the port check (default: %(default)s)",
    )
    args = parser.parse_args()
    base_url = str(args.base_url).rstrip("/")
    print(f"round-trip: driving {base_url} (gateway only, as a browser would)")
    try:
        run(base_url, str(args.host))
    except CheckFailed as exc:
        print(f"\nround-trip: FAILED — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
