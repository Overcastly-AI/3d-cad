"""End-to-end sketch flow over REAL HTTP — the BACKLOG #3 acceptance gate.

Boots the actual three-service stack (documents + geometry + gateway, real
uvicorn servers on loopback ports, SQLite stores) and drives the full loop a
client sees: register → create part → create a sketch feature → evaluate →
solved geometry back in ``FeatureResult.data``. No mock transports anywhere —
the gateway's upstream clients cross real sockets to the other two services.

The sketch is the design doc's §6 worked example (40 x 25 mm rectangle on
XY), benchmark-constrained as in RESEARCH §2 (all corners coincident,
horizontal/vertical on all sides, two driving dimensions, one anchor →
DOF 0). Corner assertions use the documented solver benchmark tolerance
(1e-9 mm, tests/test_sketch_solver.py in services/geometry) — not an ad-hoc
epsilon.
"""

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import httpx2 as httpx
import pytest
import uvicorn
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.main import build_app as build_geometry_app
from py_kit.db import async_dsn
from py_kit.schemas.features import EvaluateTreeResult
from py_kit.schemas.sketch import SketchLine
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "e2e-test-jwt-secret-0123456789abcdef"

#: Documented solver benchmark tolerance (mm) — see module docstring.
RECTANGLE_TOLERANCE_MM = 1e-9

#: Server boot budget; loopback uvicorn starts in well under a second.
BOOT_TIMEOUT_S = 30.0


def _sketch_params() -> dict[str, Any]:
    """§6 rectangle, benchmark-constrained; entities drawn deliberately
    sloppily — the solver, not the input, must land the analytic corners."""

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
            {"kind": "distance", "entity": "e1", "value_mm": 40.0},
            {"kind": "distance", "entity": "e2", "value_mm": 25.0},
            {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
        ],
    }


#: Analytic corners of the solved rectangle (see test_sketch_solver.py).
EXPECTED_CORNERS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "e1": ((0.0, 0.0), (40.0, 0.0)),
    "e2": ((40.0, 0.0), (40.0, 25.0)),
    "e3": ((40.0, 25.0), (0.0, 25.0)),
    "e4": ((0.0, 25.0), (0.0, 0.0)),
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


class _Server:
    """One uvicorn server on a loopback port, run in a daemon thread."""

    def __init__(self, app: FastAPI, port: int) -> None:
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("uvicorn server failed to boot")
            time.sleep(0.01)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=BOOT_TIMEOUT_S)


async def _create_gateway_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(GatewayBase.metadata.create_all)
    await engine.dispose()


async def _create_documents_schema(url: str) -> None:
    # Local import: keep the module-level namespace free of a second Base.
    from documents.db import Base as DocumentsBase

    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(DocumentsBase.metadata.create_all)
    await engine.dispose()


class Stack(NamedTuple):
    """Base URLs of the booted stack (geometry exposed for byte-identity
    checks against the gateway's mesh proxy — never for product traffic)."""

    gateway_url: str
    geometry_url: str


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    """The booted three-service stack (real uvicorn servers on loopback)."""
    tmp_path: Path = tmp_path_factory.mktemp("evaluate-e2e")
    documents_db = f"sqlite:///{tmp_path}/documents.db"
    gateway_db = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_documents_schema(documents_db))
    asyncio.run(_create_gateway_schema(gateway_db))

    documents_port, geometry_port, gateway_port = (
        _free_port(),
        _free_port(),
        _free_port(),
    )
    servers = [
        _Server(
            build_documents_app(DocumentsSettings(postgres_url=documents_db)),
            documents_port,
        ),
        _Server(build_geometry_app(), geometry_port),
        _Server(
            build_gateway_app(
                GatewaySettings(
                    geometry_url=f"http://127.0.0.1:{geometry_port}",
                    documents_url=f"http://127.0.0.1:{documents_port}",
                    postgres_url=gateway_db,
                    loft_env="dev",
                    jwt_secret=TEST_JWT_SECRET,
                )
            ),
            gateway_port,
        ),
    ]
    try:
        for server in servers:
            server.start()
        yield Stack(
            gateway_url=f"http://127.0.0.1:{gateway_port}",
            geometry_url=f"http://127.0.0.1:{geometry_port}",
        )
    finally:
        for server in reversed(servers):
            server.stop()


def _assert_solved_rectangle(result: EvaluateTreeResult, width_mm: float) -> None:
    (feature,) = result.features
    assert feature.status == "ok", feature
    solved = feature.data
    assert solved is not None
    assert solved.kind == "solved_sketch"
    assert solved.status == "converged"
    assert solved.dof == 0
    assert [entity.id for entity in solved.entities] == ["e1", "e2", "e3", "e4"]
    scale = width_mm / 40.0
    for entity in solved.entities:
        assert isinstance(entity, SketchLine)
        (ex1, ey1), (ex2, ey2) = EXPECTED_CORNERS[entity.id]
        assert entity.start.x == pytest.approx(ex1 * scale, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.start.y == pytest.approx(ey1, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.end.x == pytest.approx(ex2 * scale, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.end.y == pytest.approx(ey2, abs=RECTANGLE_TOLERANCE_MM)


def test_sketch_create_update_solve_end_to_end(stack: Stack) -> None:
    """create part → add sketch feature → evaluate → solved §6 corners in
    ``response.data``; then update the sketch and re-evaluate — the solved
    geometry follows the edit. Every hop is a real HTTP request."""
    with httpx.Client(base_url=stack.gateway_url, timeout=30.0) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": "eng@example.com", "password": "hunter2-passphrase"},
        )
        assert register.status_code == 201, register.text
        bearer = {"Authorization": f"Bearer {register.json()['access_token']}"}

        part = client.post("/api/v1/parts", json={"name": "demo-block"}, headers=bearer)
        assert part.status_code == 201, part.text
        part_id = part.json()["id"]

        created = client.post(
            f"/api/v1/parts/{part_id}/features",
            json={
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": _sketch_params()},
                "expected_tree_version": 0,
            },
            headers=bearer,
        )
        assert created.status_code == 201, created.text
        feature_id = created.json()["feature"]["id"]
        tree_version = created.json()["tree_version"]

        evaluated = client.post(f"/api/v1/parts/{part_id}/evaluate", headers=bearer)
        assert evaluated.status_code == 200, evaluated.text
        result = EvaluateTreeResult.model_validate(evaluated.json())
        assert result.tree_version == tree_version
        assert result.last_good_feature_id is not None
        assert str(result.last_good_feature_id) == feature_id
        assert result.mesh_glb_id is None  # sketches are not body-affecting
        _assert_solved_rectangle(result, width_mm=40.0)

        # Update the driving dimension (40 → 60 mm) and solve again: the
        # sketch API round-trips edits into new solved geometry.
        params = _sketch_params()
        params["constraints"][8] = {
            "kind": "distance",
            "entity": "e1",
            "value_mm": 60.0,
        }
        updated = client.patch(
            f"/api/v1/parts/{part_id}/features/{feature_id}",
            json={
                "expected_tree_version": tree_version,
                "feature": {"type": "sketch", "version": 1, "params": params},
            },
            headers=bearer,
        )
        assert updated.status_code == 200, updated.text

        re_evaluated = client.post(f"/api/v1/parts/{part_id}/evaluate", headers=bearer)
        assert re_evaluated.status_code == 200, re_evaluated.text
        _assert_solved_rectangle(
            EvaluateTreeResult.model_validate(re_evaluated.json()), width_mm=60.0
        )


def test_conflicting_sketch_surfaces_solver_status_not_a_crash(
    stack: Stack,
) -> None:
    """Acceptance: a conflicting sketch comes back as a per-feature
    ``FeatureError`` (HTTP 200) through the whole real stack."""
    with httpx.Client(base_url=stack.gateway_url, timeout=30.0) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": "eng2@example.com", "password": "hunter2-passphrase"},
        )
        assert register.status_code == 201, register.text
        bearer = {"Authorization": f"Bearer {register.json()['access_token']}"}

        part = client.post(
            "/api/v1/parts", json={"name": "broken-block"}, headers=bearer
        )
        assert part.status_code == 201, part.text
        part_id = part.json()["id"]

        conflicting: dict[str, Any] = {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                {
                    "id": "e1",
                    "kind": "line",
                    "start": {"x": 0.0, "y": 0.0},
                    "end": {"x": 10.0, "y": 0.0},
                }
            ],
            "constraints": [
                {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
                {"kind": "fixed", "point": {"entity": "e1", "point": "end"}},
                {"kind": "distance", "entity": "e1", "value_mm": 25.0},
            ],
        }
        created = client.post(
            f"/api/v1/parts/{part_id}/features",
            json={
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": conflicting},
                "expected_tree_version": 0,
            },
            headers=bearer,
        )
        assert created.status_code == 201, created.text

        evaluated = client.post(f"/api/v1/parts/{part_id}/evaluate", headers=bearer)
        assert evaluated.status_code == 200, evaluated.text
        result = EvaluateTreeResult.model_validate(evaluated.json())
        (feature,) = result.features
        assert feature.status == "error"
        assert feature.error is not None
        assert feature.error.code == "sketch_conflicting"
        assert feature.data is None
        assert result.last_good_feature_id is None


def test_extruded_body_mesh_reaches_browser_through_gateway(stack: Stack) -> None:
    """The extrude closes the loop to the viewport: sketch → extrude →
    evaluate yields a ``mesh_glb_id``, and the gateway mesh proxy serves the
    exact bytes the geometry service holds (§7.8 content-addressed GLB). This
    is the path that was computed-but-invisible before the proxy landed."""
    with httpx.Client(base_url=stack.gateway_url, timeout=30.0) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": "eng3@example.com", "password": "hunter2-passphrase"},
        )
        assert register.status_code == 201, register.text
        bearer = {"Authorization": f"Bearer {register.json()['access_token']}"}

        part = client.post("/api/v1/parts", json={"name": "solid"}, headers=bearer)
        assert part.status_code == 201, part.text
        part_id = part.json()["id"]

        sketch = client.post(
            f"/api/v1/parts/{part_id}/features",
            json={
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": _sketch_params()},
                "expected_tree_version": 0,
            },
            headers=bearer,
        )
        assert sketch.status_code == 201, sketch.text
        sketch_id = sketch.json()["feature"]["id"]
        tree_version = sketch.json()["tree_version"]

        extruded = client.post(
            f"/api/v1/parts/{part_id}/features",
            json={
                "name": "Extrude1",
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": sketch_id},
                        "distance_mm": 10.0,
                        "operation": "add",
                        "direction": "normal",
                    },
                },
                "expected_tree_version": tree_version,
            },
            headers=bearer,
        )
        assert extruded.status_code == 201, extruded.text

        evaluated = client.post(f"/api/v1/parts/{part_id}/evaluate", headers=bearer)
        assert evaluated.status_code == 200, evaluated.text
        result = EvaluateTreeResult.model_validate(evaluated.json())
        assert result.mesh_glb_id is not None  # a body was produced
        assert result.mesh_glb_id.startswith("sha256:")
        assert result.properties is not None
        # §6 worked example: 40x25 profile extruded 10 mm.
        assert result.properties.volume == pytest.approx(10_000.0, abs=1e-6)

        # The gateway proxy serves the browser a valid GLB...
        via_gateway = client.get(
            f"/api/v1/geometry/meshes/{result.mesh_glb_id}", headers=bearer
        )
        assert via_gateway.status_code == 200, via_gateway.text
        assert via_gateway.content[:4] == b"glTF"

    # ...and it is byte-identical to what the geometry service itself holds
    # (the proxy adds auth + routing, never re-encodes the artifact).
    with httpx.Client(base_url=stack.geometry_url, timeout=30.0) as geometry:
        direct = geometry.get(f"/api/v1/meshes/{result.mesh_glb_id}")
        assert direct.status_code == 200, direct.text
    assert via_gateway.content == direct.content


def _seed_extruded_part(
    client: httpx.Client, email: str, name: str = "exportable"
) -> tuple[dict[str, str], str]:
    """Register, create a part, and add sketch + extrude — returns (auth, id)."""
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert register.status_code == 201, register.text
    bearer = {"Authorization": f"Bearer {register.json()['access_token']}"}
    return bearer, _seed_extruded_part_for(client, bearer, name)


def _seed_extruded_part_for(
    client: httpx.Client, bearer: dict[str, str], name: str
) -> str:
    """The same sketch + extrude seed for an ALREADY-registered caller, so a
    test can own two parts (the export-collision case) without two accounts."""
    part = client.post("/api/v1/parts", json={"name": name}, headers=bearer)
    assert part.status_code == 201, part.text
    part_id = part.json()["id"]

    sketch = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Sketch1",
            "feature": {"type": "sketch", "version": 1, "params": _sketch_params()},
            "expected_tree_version": 0,
        },
        headers=bearer,
    )
    assert sketch.status_code == 201, sketch.text
    sketch_id = sketch.json()["feature"]["id"]
    tree_version = sketch.json()["tree_version"]

    extruded = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Extrude1",
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch_id},
                    "distance_mm": 10.0,
                    "operation": "add",
                    "direction": "normal",
                },
            },
            "expected_tree_version": tree_version,
        },
        headers=bearer,
    )
    assert extruded.status_code == 201, extruded.text
    return part_id


def test_part_export_carries_the_part_name_end_to_end(stack: Stack) -> None:
    """The exported file is named after the PART — filename AND STEP PRODUCT.

    Audit N4's last hop: geometry has honoured ``ExportTreeRequest.name`` since
    2026-07-31, but the gateway never SET it, so every download still fell back
    to ``part-<uuid>.step`` containing ``PRODUCT('SOLID')`` — a file a vendor
    cannot identify. Asserted against the EXPORTED BYTES and the real response
    header (this repo's standard: a claim about an export is checked against the
    export), over the same real three-service HTTP stack as the rest of this
    module."""
    with httpx.Client(base_url=stack.gateway_url, timeout=30.0) as client:
        bearer, part_id = _seed_extruded_part(
            client, "n4-name@example.com", "Motor Mount Bracket"
        )

        step = client.post(
            f"/api/v1/parts/{part_id}/export", params={"format": "step"}, headers=bearer
        )
        assert step.status_code == 200, step.text
        assert (
            step.headers["content-disposition"]
            == 'attachment; filename="motor-mount-bracket.step"'
        )
        # The bytes themselves, not just the header: OCCT's default is
        # PRODUCT('SOLID'), so this string can only come from the name we set.
        assert b"PRODUCT('Motor Mount Bracket'" in step.content
        assert b"PRODUCT('SOLID'" not in step.content

        # STL carries no product names, but it IS named after the part.
        stl = client.post(
            f"/api/v1/parts/{part_id}/export", params={"format": "stl"}, headers=bearer
        )
        assert stl.status_code == 200, stl.text
        assert (
            stl.headers["content-disposition"]
            == 'attachment; filename="motor-mount-bracket.stl"'
        )

        # Two of the SAME caller's parts exported in a row land as two files in
        # Downloads, not one overwriting the other.
        other_id = _seed_extruded_part_for(client, bearer, "Spindle Cap")
        other = client.post(
            f"/api/v1/parts/{other_id}/export",
            params={"format": "step"},
            headers=bearer,
        )
        assert other.status_code == 200, other.text
        assert (
            other.headers["content-disposition"]
            == 'attachment; filename="spindle-cap.step"'
        )
        assert b"PRODUCT('Spindle Cap'" in other.content

        # A foreign caller still cannot read the name through the export route:
        # the second documents fetch the name costs is auth-scoped like the
        # first, so an unowned part is a 404, never a leaked document name.
        intruder = client.post(
            "/api/v1/auth/register",
            json={"email": "n4-intruder@example.com", "password": "hunter2-passphrase"},
        )
        assert intruder.status_code == 201, intruder.text
        stolen = client.post(
            f"/api/v1/parts/{part_id}/export",
            params={"format": "step"},
            headers={"Authorization": f"Bearer {intruder.json()['access_token']}"},
        )
        assert stolen.status_code == 404, stolen.text
        assert b"Motor Mount Bracket" not in stolen.content


def test_part_export_downloads_evaluated_body_through_gateway(stack: Stack) -> None:
    """Export-from-tree end to end: sketch + extrude a part, then download it
    as STEP and STL through the gateway. The gateway aggregates documents
    (evaluation-ready tree) → geometry (tree export) and streams the file the
    engineer modeled — not a bare primitive. Every hop is real HTTP."""
    with httpx.Client(base_url=stack.gateway_url, timeout=30.0) as client:
        bearer, part_id = _seed_extruded_part(client, "export@example.com")

        step = client.post(
            f"/api/v1/parts/{part_id}/export", params={"format": "step"}, headers=bearer
        )
        assert step.status_code == 200, step.text
        assert step.headers["content-type"] == "model/step"
        assert "attachment; filename=" in step.headers["content-disposition"]
        # A valid STEP AP214 part 21 file (the exact B-rep of the modeled body).
        assert step.content.startswith(b"ISO-10303-21")

        stl = client.post(
            f"/api/v1/parts/{part_id}/export", params={"format": "stl"}, headers=bearer
        )
        assert stl.status_code == 200, stl.text
        assert stl.headers["content-type"] == "model/stl"
        # Binary STL: 84-byte header (80 + uint32 count) + 50 bytes per facet.
        assert len(stl.content) >= 84

    # Auth is enforced: no bearer → 401, never a leaked download.
    with httpx.Client(base_url=stack.gateway_url, timeout=30.0) as anon:
        unauth = anon.post(f"/api/v1/parts/{part_id}/export", params={"format": "step"})
        assert unauth.status_code == 401, unauth.text


def test_part_export_sketch_only_is_clean_error_through_gateway(stack: Stack) -> None:
    """A part with no body-affecting feature exports as a 422
    ``tree_export_failed`` envelope re-surfaced through the gateway — never a
    500 or a partial file."""
    with httpx.Client(base_url=stack.gateway_url, timeout=30.0) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": "export2@example.com", "password": "hunter2-passphrase"},
        )
        assert register.status_code == 201, register.text
        bearer = {"Authorization": f"Bearer {register.json()['access_token']}"}

        part = client.post("/api/v1/parts", json={"name": "sketchy"}, headers=bearer)
        assert part.status_code == 201, part.text
        part_id = part.json()["id"]

        sketch = client.post(
            f"/api/v1/parts/{part_id}/features",
            json={
                "name": "Sketch1",
                "feature": {
                    "type": "sketch",
                    "version": 1,
                    "params": _sketch_params(),
                },
                "expected_tree_version": 0,
            },
            headers=bearer,
        )
        assert sketch.status_code == 201, sketch.text

        exported = client.post(
            f"/api/v1/parts/{part_id}/export", params={"format": "step"}, headers=bearer
        )
        assert exported.status_code == 422, exported.text
        assert exported.json()["error"]["code"] == "tree_export_failed"
