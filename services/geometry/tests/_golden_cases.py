"""The golden-model gates' expectations schema and per-golden checks
(gates 1 and 3 of the geometry QA strategy, docs/RESEARCH.md §9), shared by
test_goldens.py (the inventory) and test_goldens_{a,b}.py (the per-golden
gates, over interleaved halves of the goldens: a pytest shard packs whole
files, and the gates over every golden had outgrown one).

A plain module rather than conftest fixtures because the schema is also what
test_goldens.py validates the whole inventory against at collection. Test
modules import it with the tests directory on ``sys.path`` (the workspace runs
``--import-mode=importlib``), as test_siding_b7.py imports _siding_builder.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from geometry.harness import ModelRequest, evaluate_model, load_model_request
from geometry.schemas import (
    BoundingBox,
    TessellationMetadata,
    TopologyCounts,
    Vec3,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"


class ExpectedMassProperties(BaseModel):
    """Mass-property expectations, asserted within the golden's tolerance.

    ``mass_g`` / ``center_of_mass`` are OPTIONAL and their absence is itself an
    assertion (docs/design/materials.md §6): a golden whose model assigns no
    material must report **no mass at all**, and the runner checks that the
    kernel answers ``null`` rather than ``0.0`` or a defaulted density. A golden
    that does assign one states both, hand-derived as density x the volume this
    same file already locks.
    """

    model_config = ConfigDict(extra="forbid")

    volume: float = Field(gt=0, description="Volume (mm^3)")
    surface_area: float = Field(gt=0, description="Total surface area (mm^2)")
    centroid: Vec3
    mass_g: float | None = Field(
        default=None,
        gt=0,
        description="Expected mass (g); omit when the model assigns no material, "
        "which asserts the kernel reports mass as ABSENT.",
    )
    center_of_mass: Vec3 | None = Field(
        default=None,
        description="Expected MASS-weighted centre of mass (mm); omit exactly "
        "when mass_g is omitted.",
    )
    bounding_box: BoundingBox

    @model_validator(mode="after")
    def _mass_fields_agree(self) -> "ExpectedMassProperties":
        """Mass and centre of mass are known together or not at all.

        The kernel nulls both the moment any body lacks a material, so a golden
        that stated one without the other would be asserting a state the
        contract cannot produce.
        """
        if (self.mass_g is None) != (self.center_of_mass is None):
            raise ValueError("state mass_g and center_of_mass together, or neither")
        return self


class ExpectedMesh(BaseModel):
    """Tessellation-artifact expectations, asserted exactly.

    GLB byte size is intentionally absent: it is covered by the byte-level
    determinism gate within a kernel version, and pinning the absolute size
    would break on glTF-writer upgrades without geometric meaning.
    """

    model_config = ConfigDict(extra="forbid")

    vertices: int = Field(ge=3)
    triangles: int = Field(ge=1)


class ExpectedRefusal(BaseModel):
    """A feature a REFUSAL golden locks as a typed rebuild error."""

    model_config = ConfigDict(extra="forbid")

    feature_id: str
    code: str = Field(min_length=1)
    why: str = Field(min_length=1, description="What the refusal protects")


class GoldenExpectation(BaseModel):
    """Committed expectations for one golden model (``expected.json``).

    ``tolerance`` is the reviewed per-model bound for mass-property
    assertions. Loosening it is never a fix for a red run: it is a reviewed
    decision requiring kernel-level justification recorded in
    ``tolerance_rationale`` AND ``docs/GEOMETRY-QA.md``. Topology and mesh
    counts take no tolerance — they match exactly or the golden fails.
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str] = Field(
        description="Hand derivation of the expected values, line by line"
    )
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    roundtrip_tolerance: float | None = Field(
        default=None,
        gt=0,
        description="Reviewed STEP round-trip bound replacing ROUNDTRIP_TOL for "
        "this golden only (conftest.roundtrip_tolerance_for); needs a rationale.",
    )
    roundtrip_tolerance_rationale: str | None = None
    refusals: list[ExpectedRefusal] = Field(
        default_factory=list[ExpectedRefusal],
        description="Features that must fail with exactly this code (a refusal "
        "golden); every other feature must be ok. The asserted body is the last "
        "good one.",
    )
    properties: ExpectedMassProperties
    topology: TopologyCounts
    mesh: ExpectedMesh


@dataclass(frozen=True)
class GoldenCase:
    """A discovered golden: its name, build request, and expectations."""

    name: str
    request: ModelRequest
    expected: GoldenExpectation

    @property
    def refusals(self) -> dict[str, str]:
        """feature id -> the error code it must fail with."""
        return {r.feature_id: r.code for r in self.expected.refusals}

    def build(self) -> tuple[bytes, TessellationMetadata]:
        """Rebuild through the shared harness, holding it to the refusals."""
        return evaluate_model(self.request, self.refusals)


def load_golden_case(model_path: Path) -> GoldenCase:
    """One golden directory's request and validated expectations."""
    golden_dir = model_path.parent
    return GoldenCase(
        name=golden_dir.name,
        request=load_model_request(model_path.read_text(encoding="utf-8")),
        expected=GoldenExpectation.model_validate_json(
            (golden_dir / "expected.json").read_text(encoding="utf-8")
        ),
    )


def load_goldens() -> list[GoldenCase]:
    """Discover and validate every golden directory. Malformed goldens fail
    collection loudly (pydantic ``extra="forbid"`` catches typo'd keys)."""
    return [
        load_golden_case(model_path)
        for model_path in sorted(GOLDENS_DIR.glob("*/model.json"))
    ]


def check_mass_properties_within_documented_tolerance(case: GoldenCase) -> None:
    _, metadata = case.build()
    actual = metadata.properties
    expected = case.expected.properties
    tolerance = case.expected.tolerance

    if expected.mass_g is None:
        # The honesty gate (docs/design/materials.md §6): no material in, no mass
        # out. "0 g" or a defaulted steel would both be claims about a part
        # nobody has said the material of.
        assert actual.mass_g is None, (
            f"{case.name}: the model assigns no material, so mass must be ABSENT "
            f"(null) — got {actual.mass_g!r}. Zero is not the same answer."
        )
        assert actual.center_of_mass is None, (
            f"{case.name}: no material, so there is no centre of MASS — got "
            f"{actual.center_of_mass!r}"
        )
    else:
        assert actual.mass_g is not None and actual.center_of_mass is not None, (
            f"{case.name}: the model assigns a material, so mass must be reported"
        )

    checks: list[tuple[str, float, float]] = [
        ("volume", actual.volume, expected.volume),
        ("surface_area", actual.surface_area, expected.surface_area),
        ("centroid.x", actual.centroid.x, expected.centroid.x),
        ("centroid.y", actual.centroid.y, expected.centroid.y),
        ("centroid.z", actual.centroid.z, expected.centroid.z),
        ("bbox.min.x", actual.bounding_box.min.x, expected.bounding_box.min.x),
        ("bbox.min.y", actual.bounding_box.min.y, expected.bounding_box.min.y),
        ("bbox.min.z", actual.bounding_box.min.z, expected.bounding_box.min.z),
        ("bbox.max.x", actual.bounding_box.max.x, expected.bounding_box.max.x),
        ("bbox.max.y", actual.bounding_box.max.y, expected.bounding_box.max.y),
        ("bbox.max.z", actual.bounding_box.max.z, expected.bounding_box.max.z),
    ]
    if (
        expected.mass_g is not None
        and expected.center_of_mass is not None
        and actual.mass_g is not None
        and actual.center_of_mass is not None
    ):
        # Mass rides the model's documented tolerance rather than a bound of its
        # own: mass = volume x density and every library density is < 1 in
        # g/mm^3 (steel, the densest, is 7.87e-3), so the propagated mass error
        # is strictly SMALLER than the volume error the same bound already
        # covers. The centre of mass is a length, in mm, like the centroid.
        checks += [
            ("mass_g", actual.mass_g, expected.mass_g),
            ("center_of_mass.x", actual.center_of_mass.x, expected.center_of_mass.x),
            ("center_of_mass.y", actual.center_of_mass.y, expected.center_of_mass.y),
            ("center_of_mass.z", actual.center_of_mass.z, expected.center_of_mass.z),
        ]
    for label, got, want in checks:
        assert got == pytest.approx(want, abs=tolerance), (
            f"{case.name}: {label} expected {want!r}, got {got!r} "
            f"(documented tolerance {tolerance!r} — never loosen to go green; "
            f"see expected.json tolerance_rationale)"
        )


def check_topology_and_mesh_counts_exact(case: GoldenCase) -> None:
    """Exact-match gate: a changed count is a real geometric change —
    explain it or fix it (geometry-gates skill), never widen it."""
    glb, metadata = case.build()

    assert metadata.properties.topology == case.expected.topology, (
        f"{case.name}: topology expected "
        f"{case.expected.topology.model_dump()}, "
        f"got {metadata.properties.topology.model_dump()}"
    )
    assert metadata.mesh.vertices == case.expected.mesh.vertices, case.name
    assert metadata.mesh.triangles == case.expected.mesh.triangles, case.name
    assert metadata.mesh.glb_bytes == len(glb), case.name


def check_rebuild_is_deterministic_in_process(case: GoldenCase) -> None:
    """Same request twice → identical metadata AND byte-identical GLB.

    Canonical home of the determinism gate (RESEARCH §9); any flake here is
    a P0, not a retry.
    """
    glb_a, meta_a = case.build()
    glb_b, meta_b = case.build()

    assert meta_a == meta_b, f"{case.name}: metadata differs between rebuilds"
    assert glb_a == glb_b, f"{case.name}: GLB bytes differ between rebuilds"
