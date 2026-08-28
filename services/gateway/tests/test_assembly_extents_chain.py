"""``GET /api/v1/assemblies/{id}/extents`` over the REAL 3-service chain.

The route exists so a caller holding only an assembly id can ask how big the
assembly IS — a drawing sheet fitting its scale, most immediately: before it,
``DrawingPage`` fit-scaled a PART from ``evaluatePart``'s bbox and left an
assembly sheet at the picked scale, which is why the assembly sheet in
``docs/screenshots/drawing-assembly-parts-list.png`` overflows its title block.

**The property under test is that the extents are of the SOLVED compound.**
That is the whole reason the route cannot be a documents read: documents holds
the authored SEED placements, and on any assembly that has been mated the seeds
are not where the parts are. So the gate is built around a fixture where the two
answers DIFFER by a distance no tolerance argument can absorb, and asserts the
NUMBERS — never the status code, and never the solve's own ``status``, which
:func:`test_status_cannot_tell_the_two_apart` shows is identical in both worlds.
(A 2xx proves the request parsed; on a params model with pydantic's default
``extra="ignore"`` it does not prove it meant anything — CLAUDE.md's
seven-tests-against-a-silently-ignored-field recipe.)

**The fixture is MATE-1's**, reused verbatim from
``services/geometry/tests/test_assembly_mate_seats.py`` so its geometry is
already documented and independently gated at the kernel layer: a grounded
60 x 40 x 6 plate at the origin and a free 24 x 16 x 4 bracket seeded at
(18, 12, 3) — half-SUNK through the plate — with one flush coincident mate
joining the bracket's underside to the plate's top face. Here it is authored
through the REAL public API (register → two parts with sketch+extrude → an
assembly → two instances → a mate), so the graph the route resolves is one a
user could have made.

Hand-derived extents, both of them:

* SEEDED - plate ``z 0..6`` with bracket ``z 3..7`` -> ``max.z = 7``;
* SOLVED - the mate puts the bracket's underside ON the plate's top, so bracket
  ``z 6..10`` -> ``max.z = 10``.

3 mm apart, and 7 is exactly what folding the graph's seeds client-side would
have produced. ``min.z`` is 0 and the x/y extents are the plate's own 60 x 40 in
BOTH: one coincident mate leaves the bracket two in-plane translations and the
spin about the normal, but its footprint's half-diagonal is
``sqrt(12^2 + 8^2) = 14.42 mm`` about the plate's own centre (30, 20), so no
rotation in that null space can reach outside the plate. The free directions are
therefore stated rather than snapshotted — the geometry-gates rule against
enshrining recorded output.

Boots the same way as :mod:`tests.test_assembly_import_chain` (all three apps
in-process behind ``httpx.ASGITransport``, scratch SQLite via
``metadata.create_all``, geometry's in-process LRU mesh store, fail-open rate
limiter): real HTTP semantics, no uvicorn, no ports, no docker. Marked
``integration`` because it runs the real OCCT solve; NOT excluded from the
default run.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, NamedTuple

import httpx2 as httpx
import pytest
from documents.db import Base as DocumentsBase
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.main import GeometrySettings
from geometry.main import build_app as build_geometry_app
from py_kit.db import async_dsn
from py_kit.schemas.assemblies import (
    AssemblyExtentsResponse,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

pytestmark = pytest.mark.integration

TEST_JWT_SECRET = "extents-chain-jwt-secret-0123456789abcdef"

#: Solver-convergence bound for the extent assertions. The SAME documented bound
#: ``test_assembly_mate_seats.SOLVER_TOL`` states for this exact fixture (worst
#: observed deviation from the hand-derived values there: 4.8e-9 mm on the
#: assembly bbox max z), and the same one the two assembly goldens and
#: ``test_assembly_resolve``'s ``RESOLVE_TOL`` carry for a numeric mate solve —
#: not a new epsilon invented here. Re-declared rather than imported because
#: pytest's importlib mode blocks cross-member test imports. Loosening it is a
#: reviewed decision recorded in docs/GEOMETRY-QA.md, never a way to make a red
#: run green.
SOLVER_TOL = 1e-6

# --- the fixture's hand-derived geometry (see the module docstring) --------------

PLATE_W, PLATE_D, PLATE_H = 60.0, 40.0, 6.0
BRACKET_W, BRACKET_D, BRACKET_H = 24.0, 16.0, 4.0

#: The bracket's authored seed — half-sunk through the plate's 6 mm top.
SEED_X, SEED_Y, SEED_Z = 18.0, 12.0, 3.0

#: What a SEED-fold would answer: the bracket's top at its authored height.
SEEDED_MAX_Z = SEED_Z + BRACKET_H

#: What the SOLVE answers: the mate seats the bracket's underside on the
#: plate's top face (z = 6), so the assembly reaches 6 + 4.
SOLVED_MAX_Z = PLATE_H + BRACKET_H


def _block_feature_payloads(
    width: float, depth: float, height: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A ``width`` x ``depth`` rectangle on XY, extruded ``height``.

    Two feature-create bodies (the extrude's profile reference is filled in by
    the caller, which only learns the sketch's id once documents has assigned
    it — exactly what a client does).
    """
    corners = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    entities = [
        {
            "id": f"e{index + 1}",
            "kind": "line",
            "start": {"x": corner[0], "y": corner[1]},
            "end": {
                "x": corners[(index + 1) % len(corners)][0],
                "y": corners[(index + 1) % len(corners)][1],
            },
        }
        for index, corner in enumerate(corners)
    ]
    sketch = {
        "name": "Profile",
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": entities,
                "constraints": [],
            },
        },
    }
    extrude = {
        "name": "Body",
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": None},
                "distance_mm": height,
                "operation": "add",
                "direction": "normal",
            },
        },
    }
    return sketch, extrude


def _planar_face(
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    area_mm2: float,
) -> dict[str, Any]:
    """A ``PlanarFaceSignature`` for a BOX face, in the part's LOCAL frame.

    Hand-derived rather than read back from the kernel: on an axis-aligned box
    the outward normal, the area centroid and the area are exact closed forms,
    so writing them out is a statement of what the fixture IS. (The
    ``outer_*`` invariants are optional and omitted — the resolver dual-reads,
    and a box face carries nothing cut into it for them to disambiguate.)
    """
    return {
        "subshape_type": "face",
        "surface": "plane",
        "normal": {"x": normal[0], "y": normal[1], "z": normal[2]},
        "centroid": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
        "area_mm2": area_mm2,
    }


#: The plate's TOP face (+Z at z = 6) and the bracket's UNDERSIDE (-Z at z = 0)
#: — the two faces the mate joins, each in its own part's local frame.
PLATE_TOP = _planar_face((0.0, 0.0, 1.0), (PLATE_W / 2, PLATE_D / 2, PLATE_H), 2400.0)
BRACKET_UNDERSIDE = _planar_face(
    (0.0, 0.0, -1.0), (BRACKET_W / 2, BRACKET_D / 2, 0.0), 384.0
)


class Chain(NamedTuple):
    """A booted 3-service chain: a gateway client + the two upstream apps.

    The upstream apps are exposed so the DOF cross-check can read the graph
    documents actually hands over and solve it directly — an internal probe of
    the fixture's discriminating power, never a product path.
    """

    client: httpx.AsyncClient
    documents_app: FastAPI
    geometry_app: FastAPI


async def _create_schema(url: str, base: type[DeclarativeBase]) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    await engine.dispose()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run an app's startup/shutdown (ASGITransport does not drive lifespan)."""
    async with app.router.lifespan_context(app):
        yield


@contextlib.asynccontextmanager
async def _chain(tmp_path: Path) -> AsyncGenerator[Chain]:
    """Boot geometry + documents + gateway in-process and yield a gateway client."""
    documents_url = f"sqlite:///{tmp_path}/documents.db"
    gateway_url = f"sqlite:///{tmp_path}/gateway.db"
    await _create_schema(documents_url, DocumentsBase)
    await _create_schema(gateway_url, GatewayBase)

    # Explicit s3_url=None: the in-process LRU mesh store, never a stray ambient
    # S3_URL from the developer's shell (hermetic).
    geometry_app = build_geometry_app(GeometrySettings(s3_url=None))
    documents_app = build_documents_app(
        DocumentsSettings(postgres_url=documents_url, s3_url=None)
    )
    gateway_app = build_gateway_app(
        GatewaySettings(
            geometry_url="http://geometry.internal:8002",
            documents_url="http://documents.internal:8001",
            postgres_url=gateway_url,
            redis_url=None,  # fail-open no-op rate limiter
            loft_env="dev",
            jwt_secret=TEST_JWT_SECRET,
        ),
        geometry_transport=httpx.ASGITransport(geometry_app),
        documents_transport=httpx.ASGITransport(documents_app),
    )
    async with (
        _lifespan(geometry_app),
        _lifespan(documents_app),
        _lifespan(gateway_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(gateway_app),
            base_url="http://gateway.test",
            timeout=120.0,
        ) as client,
    ):
        yield Chain(client, documents_app, geometry_app)


async def _register(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_block_part(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    name: str,
    width: float,
    depth: float,
    height: float,
) -> str:
    """Author a box part through the real API — sketch, then extrude."""
    part = await client.post("/api/v1/parts", json={"name": name}, headers=headers)
    assert part.status_code == 201, part.text
    part_id: str = part.json()["id"]

    sketch_body, extrude_body = _block_feature_payloads(width, depth, height)
    sketch = await client.post(
        f"/api/v1/parts/{part_id}/features",
        json={**sketch_body, "expected_tree_version": 0},
        headers=headers,
    )
    assert sketch.status_code == 201, sketch.text
    extrude_body["feature"]["params"]["profile"]["feature_id"] = sketch.json()[
        "feature"
    ]["id"]
    extrude = await client.post(
        f"/api/v1/parts/{part_id}/features",
        json={**extrude_body, "expected_tree_version": sketch.json()["tree_version"]},
        headers=headers,
    )
    assert extrude.status_code == 201, extrude.text
    return part_id


class Seeded(NamedTuple):
    """One authored assembly + the ids a later mate or probe needs."""

    assembly_id: str
    owner_id: str
    plate_instance: str
    bracket_instance: str
    doc_version: int


async def _seed_assembly(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    name: str,
    plate_part: str,
    bracket_part: str,
) -> Seeded:
    """The MATE-1 fixture as an assembly: grounded plate + half-sunk bracket."""
    assembly = await client.post(
        "/api/v1/assemblies", json={"name": name}, headers=headers
    )
    assert assembly.status_code == 201, assembly.text
    assembly_id: str = assembly.json()["id"]
    owner_id: str = assembly.json()["owner_id"]
    version: int = assembly.json()["doc_version"]

    async def add_instance(
        part_id: str,
        instance_name: str,
        position: tuple[float, float, float],
        *,
        grounded: bool,
    ) -> str:
        nonlocal version
        created = await client.post(
            f"/api/v1/assemblies/{assembly_id}/instances",
            json={
                "expected_version": version,
                "ref_document_id": part_id,
                "ref_document_kind": "part",
                "name": instance_name,
                "placement": {
                    "position": {
                        "x": position[0],
                        "y": position[1],
                        "z": position[2],
                    },
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
                "grounded": grounded,
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        version = created.json()["doc_version"]
        instance_id: str = created.json()["instance"]["id"]
        return instance_id

    plate = await add_instance(plate_part, "Plate <1>", (0.0, 0.0, 0.0), grounded=True)
    bracket = await add_instance(
        bracket_part, "Bracket <1>", (SEED_X, SEED_Y, SEED_Z), grounded=False
    )
    return Seeded(assembly_id, owner_id, plate, bracket, version)


async def _add_coincident_mate(
    client: httpx.AsyncClient, headers: dict[str, str], seeded: Seeded
) -> None:
    """The one flush coincident mate: bracket underside onto the plate's top."""
    created = await client.post(
        f"/api/v1/assemblies/{seeded.assembly_id}/mates",
        json={
            "expected_version": seeded.doc_version,
            "mate": {
                "type": "coincident",
                "a": {
                    "kind": "face",
                    "instance_id": seeded.bracket_instance,
                    "signature": BRACKET_UNDERSIDE,
                },
                "b": {
                    "kind": "face",
                    "instance_id": seeded.plate_instance,
                    "signature": PLATE_TOP,
                },
                "flush": True,
            },
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text


async def _extents(
    client: httpx.AsyncClient, headers: dict[str, str], assembly_id: str
) -> AssemblyExtentsResponse:
    """The route under test, parsed through the shared contract model."""
    response = await client.get(
        f"/api/v1/assemblies/{assembly_id}/extents", headers=headers
    )
    assert response.status_code == 200, response.text
    return AssemblyExtentsResponse.model_validate(response.json())


class Fixture(NamedTuple):
    """Both assemblies — identical instances, one mated and one not."""

    headers: dict[str, str]
    mated: Seeded
    unmated: Seeded


async def _build(client: httpx.AsyncClient, email: str) -> Fixture:
    headers = await _register(client, email)
    plate = await _create_block_part(
        client, headers, "Plate", PLATE_W, PLATE_D, PLATE_H
    )
    bracket = await _create_block_part(
        client, headers, "Bracket", BRACKET_W, BRACKET_D, BRACKET_H
    )
    mated = await _seed_assembly(client, headers, "Mated Stack", plate, bracket)
    await _add_coincident_mate(client, headers, mated)
    unmated = await _seed_assembly(client, headers, "Unmated Stack", plate, bracket)
    return Fixture(headers, mated, unmated)


# --- the gate -------------------------------------------------------------------


def test_extents_are_the_solved_compound_not_the_authored_seeds(
    tmp_path: Path,
) -> None:
    """The route answers 10 mm tall, which is only true AFTER the mate solves.

    Every assertion is on the geometry that came back. The unmated control is
    the same two instances at the same seeds with nothing constraining them, and
    it answers 7 — the number a client folding the graph's own placements would
    have produced for BOTH, i.e. the wrong answer this route exists to replace.
    """

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            fixture = await _build(chain.client, "extents@example.com")

            solved = await _extents(
                chain.client, fixture.headers, fixture.mated.assembly_id
            )
            box = solved.bounding_box
            assert box is not None, "both instances have bodies; extents must exist"

            # 1. THE SOLVED HEIGHT. The bracket sits ON the plate, not through it.
            assert abs(box.max.z - SOLVED_MAX_Z) < SOLVER_TOL, (
                f"assembly spans z up to {box.max.z}; seated on the plate it "
                f"must reach {SOLVED_MAX_Z}"
            )
            assert abs(box.min.z) < SOLVER_TOL, box.min.z

            # 2. NOT THE SEED. Coarse on purpose: 3 mm is not a tolerance
            #    argument, so this cannot be explained away by convergence.
            assert box.max.z - SEEDED_MAX_Z > 1.0, (
                f"z reaches {box.max.z}, the bracket's AUTHORED top "
                f"({SEEDED_MAX_Z}) — the extents are the seeds, not the solve"
            )

            # 3. THE FOOTPRINT is the grounded plate's own, in both directions:
            #    the bracket's null space cannot carry it outside (docstring).
            assert abs(box.min.x) < SOLVER_TOL, box.min.x
            assert abs(box.min.y) < SOLVER_TOL, box.min.y
            assert abs(box.max.x - PLATE_W) < SOLVER_TOL, box.max.x
            assert abs(box.max.y - PLATE_D) < SOLVER_TOL, box.max.y

            # 4. THE CONTROL. Identical instances, no mate: the seeds, exactly.
            unmated = await _extents(
                chain.client, fixture.headers, fixture.unmated.assembly_id
            )
            control = unmated.bounding_box
            assert control is not None
            assert abs(control.max.z - SEEDED_MAX_Z) < SOLVER_TOL, (
                f"the unmated control reaches {control.max.z}, not the seeded "
                f"{SEEDED_MAX_Z} — the fixture has drifted and proves nothing"
            )
            assert box.max.z - control.max.z == pytest.approx(
                SOLVED_MAX_Z - SEEDED_MAX_Z, abs=SOLVER_TOL
            )

    asyncio.run(scenario())


def test_status_cannot_tell_the_two_apart(tmp_path: Path) -> None:
    """Why the assertions above are on the numbers: the STATUS is identical.

    The solve that seats the bracket and the solve with no mate at all BOTH come
    back ``under_constrained`` (the bracket keeps free DOF either way), so a gate
    keyed on ``status`` — or on the 200 — passes in a world where the route
    reports seed placements. The extents differ by the full 3 mm the mate is
    worth.
    """

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            fixture = await _build(chain.client, "extents-status@example.com")
            mated = await _extents(
                chain.client, fixture.headers, fixture.mated.assembly_id
            )
            unmated = await _extents(
                chain.client, fixture.headers, fixture.unmated.assembly_id
            )

            assert mated.status == unmated.status == "under_constrained"
            assert str(mated.assembly_id) == fixture.mated.assembly_id
            assert mated.version == fixture.mated.doc_version + 1  # the mate

            mated_box, unmated_box = mated.bounding_box, unmated.bounding_box
            assert mated_box is not None and unmated_box is not None
            assert mated_box.max.z - unmated_box.max.z > 1.0, (
                f"mated {mated_box.max.z} vs unmated {unmated_box.max.z}: the "
                "two are indistinguishable by extents, which makes this gate blind"
            )

    asyncio.run(scenario())


def test_the_mate_is_in_the_solve_it_removes_three_degrees_of_freedom(
    tmp_path: Path,
) -> None:
    """The fixture discriminates BECAUSE the mate reaches the solver — measured.

    A mate that were silently dropped between documents and geometry would leave
    the bracket with all six rigid-body DOF and the extents at their seeds, which
    is precisely the failure the test above would then be measuring the shadow
    of. Read off the graph documents ACTUALLY hands over, solved directly: three
    remaining DOF (the coincident mate pins the along-normal translation and two
    rotations, leaving two in-plane translations and the spin), no dropped mate.
    """

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            fixture = await _build(chain.client, "extents-dof@example.com")
            principal = {PRINCIPAL_HEADER: fixture.mated.owner_id}
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(chain.documents_app),
                    base_url="http://documents.internal:8001",
                    timeout=120.0,
                ) as documents,
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(chain.geometry_app),
                    base_url="http://geometry.internal:8002",
                    timeout=120.0,
                ) as geometry,
            ):
                handover = await documents.get(
                    f"/api/v1/assemblies/{fixture.mated.assembly_id}"
                    "/evaluation-request",
                    headers=principal,
                )
                assert handover.status_code == 200, handover.text
                request = EvaluateAssemblyRequest.model_validate_json(handover.content)
                assert len(request.mates) == 1, request.mates

                solved = await geometry.post(
                    "/api/v1/assembly/evaluate",
                    content=request.model_dump_json(),
                    headers={"content-type": "application/json"},
                )
                assert solved.status_code == 200, solved.text
                result = EvaluateAssemblyResult.model_validate_json(solved.content)

            assert result.mate_errors == [], (
                f"the mate was dropped before the solve: {result.mate_errors}"
            )
            assert result.diagnosis is not None
            assert result.diagnosis.remaining_dof == 3, (
                "one coincident mate must remove exactly three degrees of "
                f"freedom; got {result.diagnosis.remaining_dof} (6 means the "
                "constraint never entered the system)"
            )

    asyncio.run(scenario())


def test_a_foreign_caller_gets_a_404_and_no_geometry_is_solved(
    tmp_path: Path,
) -> None:
    """Ownership rides on the documents hop — the uniform 404, before any solve.

    The extents of somebody else's assembly are a fact about their design (how
    big is it?), so the route must be exactly as unreachable as the graph read
    is. It is, and for free: the ``/evaluation-request`` hop is principal-scoped,
    so an unowned id fails there and geometry is never asked.
    """

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            fixture = await _build(chain.client, "extents-owner@example.com")
            intruder = await _register(chain.client, "extents-thief@example.com")

            stolen = await chain.client.get(
                f"/api/v1/assemblies/{fixture.mated.assembly_id}/extents",
                headers=intruder,
            )
            assert stolen.status_code == 404, stolen.text
            assert "bounding_box" not in stolen.text

            anonymous = await chain.client.get(
                f"/api/v1/assemblies/{fixture.mated.assembly_id}/extents"
            )
            assert anonymous.status_code == 401, anonymous.text

    asyncio.run(scenario())
