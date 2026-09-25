"""A twisted part in an assembly meshes at bounded cost (TWIST-ASSEMBLY-MESH-COST-1).

The single-part path (``4c49218``, design twisted-extrude.md §6.1) meshes a
twisted body's helicoidal flanks with the bounded mesher. The assembly mesh
exports (STL / GLB / 3MF) place each instance with a deep copy that carries no
triangulation, so before this they re-meshed a twisted part at FULL cost: a
20 mm square twisted 720 deg over 30 mm took 10.4 s (STL, GLB) and 15.0 s
(3MF) inside a two-part assembly, against 0.2 s for the same part alone.

Pinned here:

* a twisted part's assembly STL/GLB export is bounded, timed against a stated
  ceiling and counted in triangles;
* a 3MF too dense for lib3mf's full-cost re-mesh is refused, as for one part;
* an assembly WITHOUT a twisted part exports byte-for-byte what the composition
  it replaced produces (``Compound`` of placed bodies through the single-body
  writers).
"""

import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Compound
from fastapi.testclient import TestClient
from geometry.assembly.evaluate import solve_assembly
from geometry.assembly.export import export_assembly
from geometry.assembly.transform import Pose
from geometry.kernel import MeshExportTooDenseError
from geometry.kernel.export import (
    export_glb_bytes,
    export_stl_bytes,
    place_body,
)
from geometry.kernel.types import BodyShape
from geometry.main import app
from loft_wire.assemblies import EvaluateAssemblyRequest, ExportAssemblyRequest

client = TestClient(app)

ASSEMBLY_GOLDENS = Path(__file__).resolve().parent.parent / "goldens-assembly"
PLAIN_ASSEMBLY = ASSEMBLY_GOLDENS / "assembly-two-plates-bolted" / "model.json"

#: Wall-clock ceiling (s) for the five-turn twisted assembly STL/GLB export on
#: this box. Measured with the bounded mesher: 1.66 s (STL) and 1.83 s (GLB),
#: the same as the single-part tree export (1.70 s). Unbounded, the part alone
#: took 59-97 s (geometry QA F4), and the 720 deg case above already 10.4 s.
#: 20 s is 11x the measured cost and a third of the smallest unbounded one.
FIVE_TURN_EXPORT_CEILING_S = 20.0

#: Triangle ceiling for the same export: bounded, the twisted part is 6 180
#: triangles and the plate a few hundred; the production mesher gives the
#: twisted part alone about a million (design §6.1).
FIVE_TURN_TRIANGLE_CEILING = 20_000


def _square(side: float) -> list[dict[str, Any]]:
    h = side / 2
    c = [(-h, -h), (h, -h), (h, h), (-h, h)]
    return [
        {
            "id": f"e{i}",
            "kind": "line",
            "start": {"x": c[i][0], "y": c[i][1]},
            "end": {"x": c[(i + 1) % 4][0], "y": c[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]


def _twisted_part(twist: float) -> list[dict[str, Any]]:
    sketch_id, extrude_id = str(uuid.UUID(int=0xA1)), str(uuid.UUID(int=0xA2))
    return [
        {
            "id": sketch_id,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": _square(20.0),
                    "constraints": [],
                },
            },
        },
        {
            "id": extrude_id,
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch_id},
                    "distance_mm": 30.0,
                    "operation": "add",
                    "twist_angle_deg": twist,
                },
            },
        },
    ]


def _assembly(twist: float, fmt: str) -> ExportAssemblyRequest:
    plain = EvaluateAssemblyRequest.model_validate_json(PLAIN_ASSEMBLY.read_text())
    plate = [f.model_dump(mode="json") for f in plain.instances[0].features]
    return ExportAssemblyRequest.model_validate(
        {
            "assembly_id": str(uuid.UUID(int=0xA0)),
            "version": 1,
            "instances": [
                {
                    "instance_id": str(uuid.UUID(int=1)),
                    "part_key": "plate@1",
                    "name": "plate",
                    "features": plate,
                    "placement": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}},
                    "grounded": True,
                },
                {
                    "instance_id": str(uuid.UUID(int=2)),
                    "part_key": "twist@1",
                    "name": "twist",
                    "features": _twisted_part(twist),
                    "placement": {"position": {"x": 100.0, "y": 0.0, "z": 0.0}},
                    "grounded": True,
                },
            ],
            "mates": [],
            "linear_deflection": 0.1,
            "format": fmt,
        }
    )


@pytest.mark.parametrize("fmt", ["stl", "glb"])
def test_a_five_turn_part_in_an_assembly_exports_at_the_bounded_cost(
    fmt: str,
) -> None:
    request = _assembly(1800.0, fmt)
    start = time.perf_counter()
    data = export_assembly(request)
    elapsed = time.perf_counter() - start
    assert elapsed < FIVE_TURN_EXPORT_CEILING_S, f"{fmt}: {elapsed:.1f} s"
    if fmt == "stl":
        triangles = int.from_bytes(data[80:84], "little")
        assert len(data) == 84 + 50 * triangles
        assert triangles < FIVE_TURN_TRIANGLE_CEILING


def test_a_dense_twisted_part_refuses_an_assembly_3mf() -> None:
    with pytest.raises(MeshExportTooDenseError):
        export_assembly(_assembly(720.0, "3mf"))
    response = client.post(
        "/api/v1/assembly/export",
        json=_assembly(720.0, "3mf").model_dump(mode="json"),
    )
    assert response.status_code == 422, response.text
    assert "export_mesh_too_dense" in response.text


def _plain_request(fmt: str) -> ExportAssemblyRequest:
    plain = EvaluateAssemblyRequest.model_validate_json(PLAIN_ASSEMBLY.read_text())
    return ExportAssemblyRequest.model_validate(
        {**plain.model_dump(mode="json"), "format": fmt}
    )


def _composed(request: ExportAssemblyRequest) -> Compound:
    """The composition the untwisted path has always used: every instance's body
    deep-copied to its solved placement, in instance order."""
    solved = solve_assembly(request)
    bodies: list[BodyShape] = []
    for placed in solved.placed:
        pose = Pose.from_placement(placed.placement)
        bodies.append(
            place_body(
                placed.body,
                (float(pose.t[0]), float(pose.t[1]), float(pose.t[2])),
                (
                    float(pose.q[0]),
                    float(pose.q[1]),
                    float(pose.q[2]),
                    float(pose.q[3]),
                ),
            )
        )
    return Compound(bodies)


def test_an_untwisted_assembly_meshes_byte_identically() -> None:
    """No twisted part: the STL and GLB exports are byte-for-byte what the
    single-body writers produce for the plain placed composition."""
    stl_request = _plain_request("stl")
    expected_stl = export_stl_bytes(
        _composed(stl_request),
        stl_request.linear_deflection,
        stl_request.angular_deflection,
    )
    assert export_assembly(stl_request) == expected_stl
    glb_request = _plain_request("glb")
    expected_glb = export_glb_bytes(
        _composed(glb_request), glb_request.linear_deflection
    )
    assert export_assembly(glb_request) == expected_glb
