"""Golden-model harness — gates 1 and 3 of the geometry QA strategy
(docs/RESEARCH.md §9, .claude/skills/geometry-gates/SKILL.md).

Discovers every golden under ``services/geometry/goldens/`` and, for each:

* rebuilds it through :func:`geometry.harness.evaluate_model`, which
  dispatches to the same evaluation paths the REST routes and the worker
  task share (``evaluate_tessellation`` for shape goldens, ``evaluate_tree``
  for feature-tree goldens);
* asserts mass properties (volume, surface area, centroid, exact AABB — plus
  mass and the mass-weighted centre of mass when the model assigns a material)
  within the golden's **documented per-model tolerance** from
  ``expected.json`` (never an ad-hoc epsilon — CLAUDE.md conventions);
* asserts that a model with NO material reports **no mass at all** — null, not
  ``0`` and not a defaulted steel (docs/design/materials.md §6). Every golden
  that does not name a material is an instance of that honesty gate;
* asserts topology counts (faces/edges/shells) and mesh counts
  (vertices/triangles) **exactly**;
* rebuilds twice in-process and requires byte-identical GLB plus identical
  metadata (determinism gate); the fresh-interpreter leg of the same gate runs
  in ``test_goldens_restart_{a,b}.py`` over interleaved halves of the goldens
  (it is ~80% of this gate's time, and a shard packs whole files). This is the
  canonical determinism home; it strictly subsumes the former
  ``test_kernel.py::test_tessellation_is_deterministic`` (same request, same
  byte-strength assertion, plus the cross-process leg), which was removed.

A REFUSAL golden (``refusals`` in expected.json, listed in
:data:`REFUSAL_GOLDENS`) locks a typed refusal instead: exactly the listed
features must fail, each with exactly its code, and the gates above run on the
last good body.

Adding a golden requires ZERO runner changes: drop
``goldens/<name>/model.json`` (a serialized ``TessellateRequest`` for a
single shape, or a serialized ``EvaluateTreeRequest`` for a feature tree —
:mod:`geometry.harness` owns the dispatch) and ``goldens/<name>/expected.json``
next to it. Expectations must be hand-derived or independently cross-checked
— a golden recorded from buggy harness output enshrines the bug
(geometry-gates skill rule).
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


def _load_goldens() -> list[GoldenCase]:
    """Discover and validate every golden directory. Malformed goldens fail
    collection loudly (pydantic ``extra="forbid"`` catches typo'd keys)."""
    cases: list[GoldenCase] = []
    for model_path in sorted(GOLDENS_DIR.glob("*/model.json")):
        golden_dir = model_path.parent
        cases.append(
            GoldenCase(
                name=golden_dir.name,
                request=load_model_request(model_path.read_text(encoding="utf-8")),
                expected=GoldenExpectation.model_validate_json(
                    (golden_dir / "expected.json").read_text(encoding="utf-8")
                ),
            )
        )
    return cases


GOLDEN_CASES = _load_goldens()
each_golden = pytest.mark.parametrize(
    "case", GOLDEN_CASES, ids=[case.name for case in GOLDEN_CASES]
)


def test_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert GOLDEN_CASES, f"no goldens discovered under {GOLDENS_DIR}"


#: Goldens whose STEP round trip is held to a reviewed bound of their own
#: (``roundtrip_tolerance`` in expected.json) instead of ROUNDTRIP_TOL. Listed
#: here, not discovered, so an override cannot appear unreviewed. Empty from
#: GEOMETRY-QA 2026-09-25 F1 (shell-spline-prism-30x10-t1's 1e-6 retired) until
#: 2026-10-07, when the 704,000 mm^3 moto frame arrived: its STEP drift (1.3e-5
#: mm^3, 0.18 mm^2) is OCCT's, shared by a pure-build123d twin. The bike frame
#: of four Pipes (2026-10-16) drifts the same way, as does its twin.
ROUNDTRIP_TOLERANCE_OVERRIDES: frozenset[str] = frozenset(
    {
        "frame-moto-cradle-tube-od25.4-t1.6",
        "frame-bike-4-pipes-one-skeleton-head73",
        # The same four Pipes on a 3D sketch skeleton (SKETCH-3D): same solid.
        "frame-bike-3d-sketch-skeleton-4-pipes",
        # A 1.06e9 mm^3 sum of 46 solids: re-import order moves it by 2e-15.
        "b1-deck-framing-16ft",
        # The same deck from the loft.deck plugin, and its 20 ft edit (DECK).
        "plugin-deck-v1-b1-12x16ft",
        "plugin-deck-v1-b1-20ft",
        # B2's four walls from loft.wall, and the 24 in o.c. edit (STUD-WALL).
        "b2-walls-no-openings-16oc",
        "b2-walls-no-openings-24oc",
        # One wall turned 30 deg: OCCT's STEP drift on turned planes (twin: 5.7e-4).
        "plugin-wall-v1-144-30deg",
        # B2 with its hosted door and window, and the three edits (WINDOW-DOOR).
        "b2-walls-door-window",
        "b2-walls-door-moved-24",
        "b2-walls-window-30",
        "b2-walls-door-deleted",
        # Those walls and B1's deck at 1.1.0 with a hole in one member, before
        # and after the edit that renumbered 1.0.0 (WALL-MEMBER-RENUMBER).
        "b2-walls-v1.1-hole-stud-128",
        "b2-walls-v1.1-hole-door-moved-24",
        "plugin-deck-v1.1-b1-16ft-hole-end-joist",
        "plugin-deck-v1.1-b1-20ft-hole-end-joist",
        # B1 at 1.2.0 on its pier footings, and the 20 ft edit (DECK-FOOTINGS):
        # the same summation drift over 49 and 54 solids (3.6e-6 at worst).
        "plugin-deck-v1.2-b1-footings-16ft",
        "plugin-deck-v1.2-b1-footings-20ft",
        # The loft.roof B2 gable at 6/12 and 8/12 (ROOF): OCCT's STEP rounds
        # the sloped rafters' coordinates; a build123d twin drifts the same.
        "b2-roof-6-12",
        "b2-roof-8-12",
        # B3's hip roof at 6/12 and 8/12 (ROOF-HIP): the same STEP rounding
        # (2.3e-4 at worst); a build123d twin drifts too, its ridge not.
        "b3-hip-6-12",
        "b3-hip-8-12",
        # B4's L hip roof and its 48 in wing (ROOF-VALLEY): the same STEP
        # rounding over more sloped members (1.3e-3 at worst); twin drifts too.
        "b4-l-hip-valley",
        "b4-wing-48",
        # B5's floor (loft.floor), its 12 in o.c. edit, and B2's walls on it
        # (FLOOR-FRAME): the same summation drift as the B2 walls.
        "b5-floor-2x8-16oc",
        "b5-floor-2x8-12oc",
        "b5-shed-walls-on-floor",
        # B6's timber frame and its 14 ft edit (TIMBER-FRAME): 16 bodies of
        # ~9.2e8 mm^3, the posts' bores re-integrated (1.5e-6 at worst).
        "b6-frame-12x16",
        "b6-frame-14x16",
        # B3 at 1.3.0 with a hole in one rafter, before and after the edits
        # that renumbered 1.2.0 (ROOF-MEMBER-RENUMBER): b3-hip's STEP rounding.
        "b3-hip-v1.3-hole-common",
        "b3-hip-v1.3-168-hole-common",
        "b3-hip-v1.3-hole-jack",
        "b3-hip-v1.3-8-12-hole-jack",
        # An L at 1.2.0 framing one common where it framed two
        # (ROOF-L-DOUBLED-COMMON): b4's STEP rounding (8.5e-4 measured).
        "l-hip-16oc-v1.2-one-common",
        # B5 sheathed: the floor's subfloor and B2's OSB walls on it
        # (SHEATHING): the same summation drift over 98 bodies.
        "b5-shed-sheathed",
        # B2's walls with a notch across five members, and with a hole and a
        # fillet on its first stud (CUT-OBJECTS-TO-CUT): B2's summation drift,
        # 1.5e-7 and 7e-7 mm^3 on the volume.
        "cut-objects-to-cut-b2-front-notch-studs-16-32-48",
        "framing-hole-d1-fillet-r0.25-first-stud-b2",
        # B7 from one outline sketch (BUILDING-OUTLINE): b2-roof's STEP
        # rounding over 26 sloped rafters and the notched OSB (3.6e-4 at worst,
        # the build123d twin's).
        "b7-outline",
        # B7 grown to 336, the left window moved to 84, its openings measured
        # from the X 0 end (OPENING-FROM-END): b7-outline's class, 4.2e-4 at
        # worst (the twin's).
        "b7-front-wall-from-end",
        # B3's hip on B2's sheathed outline, its tails and hips notched out of
        # the OSB (ROOF-HIP-SHEATHING-NOTCH): b3-hip's STEP rounding, 2.5e-4.
        "b3-outline-hip-sheathed",
        # B7 with its window and door units (OPENING-UNITS): b7-outline's
        # class, 3.8e-4 at worst (the twin's).
        "b7-units",
        # B2 in 2x6 with three-ply headers (HEADER-PLIES): the B2 walls'
        # summation drift over 66 boxes (2.4e-6 mm^3).
        "b2-2x6-walls-header-plies",
        # B7's floor both ways (FLOOR-JOIST-SPAN): the B5 floor goldens'
        # summation drift, 9.5e-7 mm^3 at worst.
        "b7-floor-left-right",
        "b7-floor-long-walls",
        # B8: B7's walls, openings and roof on its slab (SLAB): b7-outline's
        # class, 2.9e-4 at worst; the slab itself round-trips exactly.
        "b8-slab-house",
        # B9: B7 as built on its crawl space (CRAWL-SPACE): b7-outline's
        # class, 3.4e-4 at worst; the foundation alone drifts 1.1e-5.
        "b9-crawl-space",
        # B10, B7 with two partitions (INTERIOR-WALLS): b7-outline's class,
        # 3.3e-4 at worst; the partitions and gypsum are boxes.
        "b10-partitions",
        # B7 after Update all (OPENING-UPDATE): b7-outline's class, 3.2e-4
        # measured; the 18 header plies and spacers are boxes.
        "b7-opening-update",
        # B7's gable tied by 11 ceiling joists (CEILING-JOISTS): b7-outline's
        # class, 3.8e-4 at worst (the twin's); the joists' snips add nothing.
        "b7-ceiling-joists",
        # B7 saved at batch48's releases after one Update all
        # (PLUGIN-UPDATE-ALL), its roof at 1.7.0 (GABLE-END-STUDS): b7-outline's
        # class, 2.7e-4 at worst (the twin's).
        "b7-update-all",
        # B7's gables framed and sheathed (GABLE-END-STUDS): b7-outline's
        # class, 3.3e-4 at worst (the twin's); 2.7e-4 the plugin's.
        "b7-gable-ends",
        # Casework (CASEWORK): C1 at 27 in and in face frame, C3 in face frame
        # and C2's 91 panels, the summation drift (1.0e-7 to 3.6e-7 mm^3);
        # C1 turned 30 deg, OCCT's STEP drift on turned planes (1.05e-4).
        "c1-b27-frameless-casework",
        "c1-b24-face-frame-casework",
        "c1-b24-turned-30-casework",
        "c2-kitchen-b7-left-wall",
        "c3-v3021-melamine-face-frame",
        # Casework on B10's finished faces (CASEWORK-B10): C2's 91 panels and
        # C4's 35 and its V3621 edit, the summation drift (2.1e-7 to 6.0e-7
        # mm^3); B10 with its walls' inside gypsum, b7-outline's class, 3.2e-4.
        "c2-kitchen-b10-left-wall",
        "c4-vanity-b10-p1",
        "c4-v3621-b10-p1",
        "b10-inside-gypsum",
        # B1 with its stair, closed risers and the 36 in deck, and the free
        # 14-riser stair (STAIRS): OCCT's STEP rounds the notched stringers'
        # and the handrail's slope, 2.7e-5 mm^3 on B1 (twin 6.5e-5) and
        # 5.1e-4 free (twin 1.2e-4).
        "b1-stair-30",
        "b1-stair-30-closed",
        "b1-stair-36",
        "free-stair-107",
        # B1's guard opened at its stair (DECK-GUARD-OPENING): b1-stair-30's
        # class, 3.8e-6 mm^3 measured (the twin 3.1e-5); the guard is boxes.
        "b1-stair-30-guard-opening",
    }
)


def test_roundtrip_overrides_are_the_reviewed_ones() -> None:
    declared = {
        case.name
        for case in GOLDEN_CASES
        if case.expected.roundtrip_tolerance is not None
    }
    assert declared == ROUNDTRIP_TOLERANCE_OVERRIDES
    for case in GOLDEN_CASES:
        if case.name in declared:
            assert case.expected.roundtrip_tolerance_rationale, case.name


#: The refusal goldens, listed so one cannot appear (or vanish) unreviewed: a
#: golden that EXPECTS a feature error must be one somebody meant.
REFUSAL_GOLDENS: frozenset[str] = frozenset(
    {"sweep-twist-arc-path-refused-square10-r40-90deg"}
)


def test_refusal_goldens_are_the_reviewed_ones() -> None:
    declared = {case.name for case in GOLDEN_CASES if case.expected.refusals}
    assert declared == REFUSAL_GOLDENS


def test_every_golden_dir_is_complete() -> None:
    """Every directory under goldens/ carries both halves of a golden."""
    for golden_dir in sorted(p for p in GOLDENS_DIR.iterdir() if p.is_dir()):
        assert (golden_dir / "model.json").is_file(), f"{golden_dir}: model.json"
        assert (golden_dir / "expected.json").is_file(), f"{golden_dir}: expected.json"


@each_golden
def test_mass_properties_within_documented_tolerance(case: GoldenCase) -> None:
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


@each_golden
def test_topology_and_mesh_counts_exact(case: GoldenCase) -> None:
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


@each_golden
def test_rebuild_is_deterministic_in_process(case: GoldenCase) -> None:
    """Same request twice → identical metadata AND byte-identical GLB.

    Canonical home of the determinism gate (RESEARCH §9); any flake here is
    a P0, not a retry.
    """
    glb_a, meta_a = case.build()
    glb_b, meta_b = case.build()

    assert meta_a == meta_b, f"{case.name}: metadata differs between rebuilds"
    assert glb_a == glb_b, f"{case.name}: GLB bytes differ between rebuilds"
