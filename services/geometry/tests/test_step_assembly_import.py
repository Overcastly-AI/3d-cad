"""Assembly STEP import — the XCAF product-structure reader (BACKLOG P1, slice 1).

The inverse of the assembly export (``test_assembly_export``): MANUFACTURE a
multi-instance assembly STEP with the shipped
:func:`~geometry.kernel.export.export_step_assembly_bytes`, then read it BACK
through :func:`~geometry.assembly.import_step.import_step_assembly` and prove
fidelity — the killer round-trip a real "open an assembly STEP" flow performs.

Coverage:

* **Round-trip:** a >=2-instance assembly (incl. a REPEATED part and a
  non-identity off-axis rotation — the cases the identity-only goldens miss) →
  export → import → ``has_assembly_structure`` true, N products recovered, each
  product's placement reproduces the exported world pose (world centroid + volume
  within the documented kernel ``roundtrip_tol``, never an ad-hoc epsilon), and
  each PRODUCT name is recovered.
* **Flat fallback:** a single-body part STEP parses with
  ``has_assembly_structure=false`` and exactly ONE body (the MB-4b single-body
  path stays intact — slice 2 wires the fallback).
* **Never-500 taxonomy:** garbage bytes → ``ImportParseError``; a surfaces-only
  STEP → ``ImportNoSolidError``; the HTTP route maps both to a clean 422.
* **Determinism (RESEARCH §9):** the same bytes yield an identical structured
  read (product count, names, placements, properties).
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
from build123d import (
    Compound,
    Face,
    Location,
    Solid,
    export_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.assembly.import_step import import_step_assembly
from geometry.kernel import ImportNoSolidError, ImportParseError
from geometry.kernel.export import (
    AssemblyComponent,
    export_step_assembly_bytes,
    export_step_bytes,
)
from geometry.kernel.step_assembly import StepAssemblyRead, read_step_assembly
from geometry.main import app
from py_kit.schemas.assemblies import Placement
from py_kit.schemas.step_import import (
    StepAssemblyImportRequest,
    StepAssemblyImportResult,
)

client = TestClient(app)

#: A 10x20x30 box: local centroid (5, 10, 15), volume 6000.
_BOX = Solid.make_box(10, 20, 30)
_BOX_LOCAL_CENTROID = np.array([5.0, 10.0, 15.0])
_BOX_VOLUME = 6000.0


def _quat(
    axis: tuple[float, float, float], angle_deg: float
) -> tuple[float, float, float, float]:
    """The (x, y, z, w) unit quaternion for an axis-angle rotation."""
    a = np.array(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    th = math.radians(angle_deg)
    v = a * math.sin(th / 2)
    return (float(v[0]), float(v[1]), float(v[2]), float(math.cos(th / 2)))


def _rodrigues(axis: tuple[float, float, float], angle_deg: float) -> np.ndarray:
    """Independent rotation matrix (Rodrigues) — the world-pose oracle.

    Built WITHOUT a quaternion so a shared quaternion-convention bug in the
    export placement AND the import placement cannot hide behind a matching
    oracle (same discipline as ``test_assembly_export``'s rotated guard).
    """
    a = np.array(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    th = math.radians(angle_deg)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(th) * k + (1 - math.cos(th)) * (k @ k)


# --- the killer round-trip: export -> import -> placements + names ---------------


def test_export_import_roundtrip_recovers_products_placements_names(
    roundtrip_tol: float,
) -> None:
    """Export a 3-instance assembly (repeated part + off-axis rotation) → import →
    every product's world pose + PRODUCT name is recovered within the kernel tol.
    """
    specs = [
        ("inst-A", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.0),
        ("inst-B", (100.0, 5.0, -3.0), (0.0, 0.0, 1.0), 0.0),
        ("inst-C", (5.0, -2.0, 8.0), (1.0, 2.0, 3.0), 50.0),
    ]
    components: list[AssemblyComponent] = []
    expected: dict[str, tuple[float, np.ndarray]] = {}
    for name, pos, axis, ang in specs:
        components.append(
            AssemblyComponent(
                name=name,
                body=_BOX,
                translation=pos,
                quaternion=_quat(axis, ang),
            )
        )
        world_centroid = _rodrigues(axis, ang) @ _BOX_LOCAL_CENTROID + np.array(pos)
        expected[name] = (_BOX_VOLUME, world_centroid)

    data = export_step_assembly_bytes("round-trip-asm", components)
    result = import_step_assembly(StepAssemblyImportRequest(data=data.decode("utf-8")))

    assert result.has_assembly_structure is True
    assert len(result.products) == len(specs)

    by_name = {p.name: p for p in result.products}
    recovered_names = [p.name for p in result.products]
    assert set(by_name) == {name for name, *_ in specs}, (
        f"recovered product names {recovered_names} != exported names"
    )

    for name, (want_volume, want_world_centroid) in expected.items():
        product = by_name[name]
        assert product.properties is not None
        assert product.mesh_glb_id is not None
        # Volume is rigid-invariant: compared to the local body directly.
        assert product.properties.volume == pytest.approx(
            want_volume, abs=roundtrip_tol
        )
        # Apply the RECOVERED placement to the RECOVERED local centroid and check
        # it lands at the independently-derived world pose (transpose / quat-order
        # / frame-convention guard) within the documented kernel round-trip bound.
        pose = Placement.model_validate(product.placement.model_dump())
        q = pose.orientation
        rot = _quat_to_matrix((q.x, q.y, q.z, q.w))
        local = np.array(
            [
                product.properties.centroid.x,
                product.properties.centroid.y,
                product.properties.centroid.z,
            ]
        )
        world = rot @ local + np.array(
            [pose.position.x, pose.position.y, pose.position.z]
        )
        for axis_label, got, wanted in zip(
            "xyz", world, want_world_centroid, strict=True
        ):
            assert got == pytest.approx(wanted, abs=roundtrip_tol), (
                f"{name}: recovered placement world centroid.{axis_label} {got!r} "
                f"does not match the independent Rodrigues pose {wanted!r} "
                f"(tol {roundtrip_tol!r})"
            )


def _quat_to_matrix(q: tuple[float, float, float, float]) -> np.ndarray:
    """Rotation matrix of an (x, y, z, w) quaternion (test-local oracle)."""
    x, y, z, w = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def test_repeated_part_products_share_one_mesh() -> None:
    """Two occurrences of ONE part dedup to a single content-addressed mesh."""
    components = [
        AssemblyComponent(
            name="a", body=_BOX, translation=(0, 0, 0), quaternion=(0, 0, 0, 1)
        ),
        AssemblyComponent(
            name="b", body=_BOX, translation=(50, 0, 0), quaternion=(0, 0, 0, 1)
        ),
    ]
    data = export_step_assembly_bytes("dup-asm", components)
    result = import_step_assembly(StepAssemblyImportRequest(data=data.decode("utf-8")))
    ids = {p.mesh_glb_id for p in result.products}
    assert len(result.products) == 2
    assert len(ids) == 1, f"repeated part did not share one mesh id: {ids}"


# --- flat single-body fallback (MB-4b path intact) ------------------------------


def test_flat_single_body_step_falls_back_with_one_product() -> None:
    """A flat part STEP → has_assembly_structure=false and exactly ONE body."""
    data = export_step_bytes(Solid.make_box(3, 4, 5))
    result = import_step_assembly(StepAssemblyImportRequest(data=data.decode("utf-8")))
    assert result.has_assembly_structure is False
    assert len(result.products) == 1
    product = result.products[0]
    assert product.properties is not None
    assert product.properties.volume == pytest.approx(60.0, abs=1e-7)
    # Identity placement for a flat STEP.
    assert product.placement.position.x == pytest.approx(0.0, abs=1e-7)
    assert product.placement.orientation.w == pytest.approx(1.0, abs=1e-7)


def test_flat_multi_lump_step_is_one_product() -> None:
    """A flat STEP of two disjoint solids stays ONE (multi-lump) product, false
    flag — the MB-4b single-body taxonomy, not two products."""
    cube_a = Solid.make_box(20, 20, 20)
    cube_b = Solid.make_box(20, 20, 20).located(Location((30, 0, 0)))  # x-centroid 40
    buffer = io.BytesIO()
    assert export_step(Compound([cube_b, cube_a]), buffer)
    result = import_step_assembly(
        StepAssemblyImportRequest(data=buffer.getvalue().decode("utf-8"))
    )
    assert result.has_assembly_structure is False
    assert len(result.products) == 1
    assert result.products[0].properties is not None
    assert result.products[0].properties.volume == pytest.approx(16000.0, abs=1e-7)


# --- never-500 taxonomy ---------------------------------------------------------


def test_garbage_bytes_raise_parse_error() -> None:
    with pytest.raises(ImportParseError):
        read_step_assembly("this is not a STEP file at all")


def test_surfaces_only_step_raises_no_solid() -> None:
    buffer = io.BytesIO()
    assert export_step(Face.make_rect(10, 10), buffer)
    with pytest.raises(ImportNoSolidError):
        read_step_assembly(buffer.getvalue().decode("utf-8"))


def test_route_maps_parse_failure_to_422() -> None:
    response = client.post(
        "/api/v1/assembly/import", json={"data": "garbage not a step file"}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "import_parse_failed"


def test_route_roundtrips_over_http() -> None:
    components = [
        AssemblyComponent(
            name="p1", body=_BOX, translation=(0, 0, 0), quaternion=(0, 0, 0, 1)
        ),
        AssemblyComponent(
            name="p2", body=_BOX, translation=(80, 0, 0), quaternion=(0, 0, 0, 1)
        ),
    ]
    data = export_step_assembly_bytes("http-asm", components)
    response = client.post(
        "/api/v1/assembly/import", json={"data": data.decode("utf-8")}
    )
    assert response.status_code == 200, response.text
    result = StepAssemblyImportResult.model_validate(response.json())
    assert result.has_assembly_structure is True
    assert {p.name for p in result.products} == {"p1", "p2"}


def test_oversize_payload_is_422_at_validation() -> None:
    from py_kit.schemas.features import MAX_INLINE_STEP_CHARS

    response = client.post(
        "/api/v1/assembly/import", json={"data": "x" * (MAX_INLINE_STEP_CHARS + 1)}
    )
    assert response.status_code == 422, response.text


# --- determinism (RESEARCH §9) --------------------------------------------------


def test_structured_read_is_deterministic() -> None:
    """The same bytes yield an identical structured read (names, placements)."""
    components = [
        AssemblyComponent(
            name="d1", body=_BOX, translation=(0, 0, 0), quaternion=(0, 0, 0, 1)
        ),
        AssemblyComponent(
            name="d2",
            body=_BOX,
            translation=(10, 20, 30),
            quaternion=_quat((1, 1, 0), 33.0),
        ),
    ]
    text = export_step_assembly_bytes("det-asm", components).decode("utf-8")

    def digest(
        read: StepAssemblyRead,
    ) -> list[
        tuple[
            str | None,
            tuple[float, float, float],
            tuple[float, float, float, float],
        ]
    ]:
        return [(p.name, p.translation, p.quaternion) for p in read.products]

    assert digest(read_step_assembly(text)) == digest(read_step_assembly(text))
