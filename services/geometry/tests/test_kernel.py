"""Kernel golden model: the 10 x 20 x 30 mm box (first light).

Mass properties are asserted against analytic values within GOLDEN_TOL;
topology counts exactly; tessellation determinism at full byte strength
(RESEARCH §9 geometry gates).
"""

import struct
import time

import pytest
from geometry.kernel import build_box, evaluate_tessellation, glb_stats, measure_shape
from geometry.kernel.tessellate import tessellate_glb
from geometry.schemas import BoxParams, TessellateRequest

#: Documented golden-model tolerance for the box (CLAUDE.md kernel linear
#: tolerance, 1e-7). The box is planar-exact in OCCT — GProp integrates its
#: mass properties without approximation error — so this bound is generous.
GOLDEN_TOL = 1e-7

#: Golden box: 10 x 20 x 30 mm, min corner at the origin.
X, Y, Z = 10.0, 20.0, 30.0
ANALYTIC_VOLUME = X * Y * Z  # 6000 mm^3
ANALYTIC_AREA = 2 * (X * Y + Y * Z + X * Z)  # 2200 mm^2
ANALYTIC_CENTROID = (X / 2, Y / 2, Z / 2)  # (5, 10, 15) mm

GOLDEN_REQUEST = TessellateRequest(
    shape="box", params=BoxParams(x=X, y=Y, z=Z), linear_deflection=0.1
)


def test_box_mass_properties_match_analytic() -> None:
    properties = measure_shape(build_box(X, Y, Z))

    assert properties.volume == pytest.approx(ANALYTIC_VOLUME, abs=GOLDEN_TOL)
    assert properties.surface_area == pytest.approx(ANALYTIC_AREA, abs=GOLDEN_TOL)
    assert properties.centroid.x == pytest.approx(ANALYTIC_CENTROID[0], abs=GOLDEN_TOL)
    assert properties.centroid.y == pytest.approx(ANALYTIC_CENTROID[1], abs=GOLDEN_TOL)
    assert properties.centroid.z == pytest.approx(ANALYTIC_CENTROID[2], abs=GOLDEN_TOL)


def test_box_bounding_box_exact() -> None:
    bbox = measure_shape(build_box(X, Y, Z)).bounding_box

    for actual, expected in (
        (bbox.min.x, 0.0),
        (bbox.min.y, 0.0),
        (bbox.min.z, 0.0),
        (bbox.max.x, X),
        (bbox.max.y, Y),
        (bbox.max.z, Z),
    ):
        assert actual == pytest.approx(expected, abs=GOLDEN_TOL)


def test_box_topology_counts_exact() -> None:
    topology = measure_shape(build_box(X, Y, Z)).topology

    assert topology.faces == 6
    assert topology.edges == 12
    assert topology.shells == 1


def test_box_rejects_non_positive_dimensions() -> None:
    for dims in ((0.0, Y, Z), (X, -1.0, Z), (X, Y, 0.0)):
        with pytest.raises(ValueError, match="strictly positive"):
            build_box(*dims)


def test_tessellate_rejects_non_positive_deflection() -> None:
    box = build_box(X, Y, Z)
    with pytest.raises(ValueError, match="linear_deflection"):
        tessellate_glb(box, 0.0)


def test_glb_payload_is_valid_binary_gltf() -> None:
    glb, metadata = evaluate_tessellation(GOLDEN_REQUEST)

    magic, version, length = struct.unpack_from("<4sII", glb, 0)
    assert magic == b"glTF"
    assert version == 2
    assert length == len(glb)

    # glb_stats re-parses the payload; a box tessellates to 2 triangles per
    # face and 4 vertices per face (faceted normals — no vertex sharing
    # across faces).
    stats = glb_stats(glb)
    assert stats == metadata.mesh
    assert stats.triangles == 12
    assert stats.vertices == 24
    assert stats.glb_bytes == len(glb)


def test_tessellation_is_deterministic() -> None:
    """Same request twice → identical metadata AND byte-identical GLB."""
    glb_a, meta_a = evaluate_tessellation(GOLDEN_REQUEST)
    glb_b, meta_b = evaluate_tessellation(GOLDEN_REQUEST)

    assert meta_a == meta_b
    assert glb_a == glb_b


def test_build_and_tessellate_performance_budget() -> None:
    """Pathological-regression tripwire (RESEARCH §9 performance budgets).

    Measured on the dev container, warm: 4 to 8 ms for build + measure +
    tessellate + GLB parse. The 2 s ceiling is deliberately generous —
    it exists to fail loudly on order-of-magnitude regressions, not to
    flake on CI noise.
    """
    evaluate_tessellation(GOLDEN_REQUEST)  # warm-up (lazy kernel init)

    start = time.perf_counter()
    evaluate_tessellation(GOLDEN_REQUEST)
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, f"build+tessellate took {elapsed:.3f}s (budget 2s)"
