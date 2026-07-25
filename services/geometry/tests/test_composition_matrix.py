"""COMPOSITION MATRIX — the standing gate for "feature N reasons wrongly about
the body feature N-1 produced" (docs/GEOMETRY-QA.md 2026-07-25).

WHY THIS FILE EXISTS. Every golden under ``services/geometry/goldens/``
exercises verbs in (near-)ISOLATION, and every one of the five
silent-wrong-geometry defects found in the 2026-07-24/25 audit was a
COMPOSITION of two features that each passed its own golden:

  1. ``pattern`` x ``hole``      — patterned the whole body instead of arraying
     the cut (51773.8 / 59497.3 vs 31547.6 / 34492.04). FINDINGS #1, `feb4318`.
  2. ``mirror`` x ``hole``       — the whole-body union FILLED the hole and
     returned a featureless brick (32000.0 vs 29989.38). FINDINGS #2, `feb4318`.
  3. ``mirror`` x ``extrude-cut`` about a CLEARING plane — the reflected tool
     landed outside the body, so the mirror was a SILENT NO-OP (30000 vs
     60000). code-review regression B, `fa30220`.
  4. ``mirror`` where an EARLIER cut precedes the mirrored one — the tempting
     "union then re-cut" fix WELDS the earlier pocket shut (29600 correct vs
     30400 for that fix). Non-regression lock, `fa30220`.
  5. ``hole`` edit -> sibling ``hole`` on the SAME face — the sibling reference
     was orphaned (``subshape_unresolved``), and the first fix then silently
     TRANSLATED the resolved plane origin by 0.1156 mm in x AND y. FINDINGS #3
     `2b6b72e` + code-review regression A.

Isolated goldens are STRUCTURALLY BLIND to that class. This module composes
feature PAIRS (plus triples) systematically and asserts correctness by
properties that need no hand-authored golden per combination:

* **Analytic** closed-form volume/area/centroid where the composed shape is
  derivable by hand (the strongest assertion — :func:`_analytic` cases).
* **Shape-independent invariants** (:func:`test_pair_matrix`): a cut-kind
  feature may never INCREASE volume; a mirror about a plane the body does not
  cross must EXACTLY double it; a pattern of a disjoint cut must remove exactly
  ``(count-1) x`` the seed removal; a feature that removes nothing must ERROR,
  never silently return the input; ``suppress`` then ``unsuppress`` must return
  the byte-identical shape; edit-a-parameter-then-revert must return the
  byte-identical shape; a same-face reference must resolve to the SAME plane
  origin after an unrelated sibling edit.
* **Cross-checks** of the two evaluation orders where order must not matter
  (:func:`test_order_independent_pairs`) — plus a NON-commuting control pair, so
  the check is proven to have teeth rather than being vacuously true.

TOLERANCES (never ad-hoc — the two reviewed golden tiers, reused verbatim):

* :data:`PLANAR_TOL` ``1e-9`` — all-planar compositions. The same bound the
  planar goldens carry (``mirror-triangle-prism-2x``,
  ``mirror-cut-clearing-plane-block-40x40x20``). Worst residual measured over
  this module's planar cases: ~3.6e-12 (the bare 40x40x10 plate's own GProp),
  so ~275x headroom.
* :data:`CURVED_TOL` ``1e-8`` — any composition carrying a cylindrical/conical
  face (bore, fillet, revolve) or a ROTATED placement (circular pattern). The
  same bound the curved/rotating goldens carry
  (``pattern-cut-6hole-boltcircle-60x60x10``, ``mirror-hole-feature-plate-40x40x20``,
  whose documented worst residual is 1.46e-11). Worst measured here ~2.4e-11.

Loosening either bound is a reviewed decision requiring a kernel-level
justification recorded here AND in docs/GEOMETRY-QA.md — never a fix for a red
run (CLAUDE.md conventions / geometry-gates skill).

RUNTIME. The whole module is a per-commit gate: ~26 s wall clock on the CI-class
container (measured 2026-07-25), dominated by the 104-cell pair matrix (~6 s)
and the STEP round-trip leg (~6 s). No case needed a slow-tier marker — every
fixture is deliberately sized to the smallest body that still exercises the
seam, so the whole matrix fits the every-commit budget instead of a nightly one.

LIVE DEFECTS. Cases proving a defect found BY this matrix and not yet fixed are
marked ``xfail(strict=True)`` with the measured expected-vs-obtained numbers in
the docstring: the assertion is REAL and unweakened, the suite stays honest
today, and the strict marker turns the suite RED the moment the kernel fix
lands, forcing the marker's removal. See the ``## 2026-07-25`` entry in
docs/GEOMETRY-QA.md for the filed findings (CM-1 .. CM-4).
"""

import copy
import math
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest

# Upstream signatures carry Shape[Unknown]/PathLike[Unknown] type params (the
# same gap tessellate.py documents for export_gltf) — scoped ignores only.
from build123d import (
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.features import evaluate_tree
from geometry.features.evaluate import TreeEvaluation
from geometry.kernel import measure_shape
from geometry.schemas import ShapeProperties
from py_kit.schemas.features import EvaluateTreeRequest

# --- Documented tolerances (see the module docstring) -----------------------------

#: All-planar compositions. The reviewed planar golden tier.
PLANAR_TOL = 1e-9
#: Compositions with a curved face or a rotated placement. The reviewed
#: curved/rotating golden tier.
CURVED_TOL = 1e-8
#: STEP round-trip bound: the CLAUDE.md kernel linear tolerance, the same
#: ``ROUNDTRIP_TOL`` the golden round-trip gate uses (conftest).
ROUNDTRIP_TOL = 1e-7

PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000c0de")
XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}

# --- Tree-authoring DSL ---------------------------------------------------------
#
# pytest runs with ``--import-mode=importlib`` (root pyproject), so test modules
# cannot import each other; this module owns its own builders, exactly as
# test_mirror.py / test_hole.py / test_pattern.py each own theirs. They emit the
# same JSON shape the goldens' ``model.json`` files carry, so a failing case can
# be pasted straight into a golden directory.


def _fid(n: int) -> uuid.UUID:
    """A stable, readable feature id (deterministic — no uuid4 anywhere)."""
    return uuid.UUID(f"00000000-0000-0000-0000-{n:012d}")


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def rect_sketch(
    feature_id: uuid.UUID,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    plane: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A closed rectangle ``[x0,x1] x [y0,y1]``, unconstrained.

    No constraints means the solver returns the authored positions bitwise (zero
    residual), the same posture every rectangle golden uses — so a numeric
    deviation in a composed case is the KERNEL's, never the solver's.
    """
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(plane or XY_PLANE),
                "entities": [
                    _line(f"e{i + 1}", corners[i], corners[(i + 1) % 4])
                    for i in range(4)
                ],
                "constraints": [],
            },
        },
    }


def revolve_profile_sketch(
    feature_id: uuid.UUID,
    plane: dict[str, Any],
    points: list[tuple[float, float]],
    axis: tuple[tuple[float, float], tuple[float, float]],
) -> dict[str, Any]:
    """A closed polygon profile plus a CONSTRUCTION centerline (``"ax"``)."""
    entities = [
        _line(f"e{i + 1}", points[i], points[(i + 1) % len(points)])
        for i in range(len(points))
    ]
    entities.append({**_line("ax", axis[0], axis[1]), "construction": True})
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(plane),
                "entities": entities,
                "constraints": [],
            },
        },
    }


def extrude(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    distance_mm: float,
    operation: Literal["add", "cut"] = "add",
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": operation,
                "direction": "normal",
            },
        },
    }


def revolve(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    operation: Literal["add", "cut"] = "add",
    angle_deg: float = 360.0,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "revolve",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "axis": {"kind": "sketch_line", "entity": "ax"},
                "angle_deg": angle_deg,
                "operation": operation,
            },
        },
    }


def face_ref(
    anchor_id: uuid.UUID,
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    area_mm2: float,
) -> dict[str, Any]:
    """A stage-1 planar-face ``SubshapeRef`` — the one grammar hole / shell /
    draft / on_face-datum all resolve (topological-naming.md §4)."""
    return {
        "kind": "subshape",
        "feature_id": str(anchor_id),
        "subshape_type": "face",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "face",
                "surface": "plane",
                "normal": {"x": normal[0], "y": normal[1], "z": normal[2]},
                "centroid": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
                "area_mm2": area_mm2,
            },
        },
    }


def hole(
    feature_id: uuid.UUID,
    face: dict[str, Any],
    position: tuple[float, float, float],
    diameter_mm: float,
    depth: dict[str, Any] | None = None,
    hole_type: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "face": face,
        "position": {"x": position[0], "y": position[1], "z": position[2]},
        "diameter_mm": diameter_mm,
        "depth": depth or {"kind": "through_all"},
    }
    if hole_type is not None:
        params["type"] = hole_type
    return {
        "id": str(feature_id),
        "feature": {"type": "hole", "version": 1, "params": params},
    }


def counterbore(diameter_mm: float, depth_mm: float) -> dict[str, Any]:
    return {
        "kind": "counterbore",
        "cbore_diameter_mm": diameter_mm,
        "cbore_depth_mm": depth_mm,
    }


def countersink(diameter_mm: float, angle_deg: float) -> dict[str, Any]:
    return {
        "kind": "countersink",
        "csink_diameter_mm": diameter_mm,
        "csink_angle_deg": angle_deg,
    }


def linear_pattern(
    feature_id: uuid.UUID,
    direction: tuple[float, float, float],
    spacing_mm: float,
    count: int,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "linear",
                    "direction": {
                        "x": direction[0],
                        "y": direction[1],
                        "z": direction[2],
                    },
                    "spacing_mm": spacing_mm,
                    "count": count,
                }
            },
        },
    }


def circular_pattern(
    feature_id: uuid.UUID,
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
    count: int,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "circular",
                    "axis_point": {
                        "x": axis_point[0],
                        "y": axis_point[1],
                        "z": axis_point[2],
                    },
                    "axis_direction": {
                        "x": axis_direction[0],
                        "y": axis_direction[1],
                        "z": axis_direction[2],
                    },
                    "angle_deg": angle_deg,
                    "count": count,
                }
            },
        },
    }


def mirror(feature_id: uuid.UUID, plane: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {"type": "mirror", "version": 1, "params": {"plane": plane}},
    }


def datum_offset(
    feature_id: uuid.UUID, base: Literal["XY", "XZ", "YZ"], offset_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": base, "offset_mm": offset_mm, "flip": False},
        },
    }


def datum_on_face(
    feature_id: uuid.UUID, face: dict[str, Any], offset_mm: float = 0.0
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"kind": "on_face", "face": face, "offset_mm": offset_mm},
        },
    }


def fillet(
    feature_id: uuid.UUID, radius_mm: float, axis: Literal["X", "Y", "Z"] = "Z"
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {"kind": "axis_parallel", "axis": axis},
                "radius_mm": radius_mm,
            },
        },
    }


def chamfer(
    feature_id: uuid.UUID, distance_mm: float, axis: Literal["X", "Y", "Z"] = "Z"
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "chamfer",
            "version": 1,
            "params": {
                "edges": {"kind": "axis_parallel", "axis": axis},
                "distance_mm": distance_mm,
            },
        },
    }


def shell(
    feature_id: uuid.UUID, thickness_mm: float, open_faces: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "shell",
            "version": 1,
            "params": {
                "thickness_mm": thickness_mm,
                "faces": {"kind": "faces", "refs": open_faces},
            },
        },
    }


def draft(
    feature_id: uuid.UUID,
    angle_deg: float,
    faces: list[dict[str, Any]],
    base: Literal["XY", "XZ", "YZ"] = "XY",
    offset_mm: float = 0.0,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "draft",
            "version": 1,
            "params": {
                "faces": {"kind": "faces", "refs": faces},
                "angle_deg": angle_deg,
                "neutral_plane": {
                    "kind": "datum",
                    "base": base,
                    "offset_mm": offset_mm,
                    "flip": False,
                },
            },
        },
    }


def suppress(features: list[dict[str, Any]], target: uuid.UUID) -> list[dict[str, Any]]:
    """A deep copy of *features* with *target*'s envelope ``suppressed`` (§4.3a)."""
    out = copy.deepcopy(features)
    for entry in out:
        if entry["id"] == str(target):
            entry["feature"]["suppressed"] = True
    return out


def without(features: list[dict[str, Any]], target: uuid.UUID) -> list[dict[str, Any]]:
    """*features* with *target* DELETED — the oracle a suppress must match."""
    return [copy.deepcopy(e) for e in features if e["id"] != str(target)]


# --- Evaluation helpers ---------------------------------------------------------


def evaluate(features: list[dict[str, Any]]) -> TreeEvaluation:
    """Evaluate a feature list through the SAME path the REST route and the
    worker share (``evaluate_tree``), at the goldens' 0.1 mm deflection."""
    request = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(PART_ID),
            "tree_version": 1,
            "features": features,
            "linear_deflection": 0.1,
        }
    )
    return evaluate_tree(request)


def statuses(evaluation: TreeEvaluation) -> list[str]:
    return [r.status for r in evaluation.result.features]


def error_codes(evaluation: TreeEvaluation) -> list[str]:
    return [r.error.code for r in evaluation.result.features if r.error is not None]


def properties(evaluation: TreeEvaluation, label: str) -> ShapeProperties:
    """Mass properties of an evaluation that must be fully ``ok``.

    A per-feature error here is a gate failure with the offending codes in the
    message — a composed case exists to lock working capability.
    """
    bad = [
        (str(r.feature_id), r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
        if r.status != "ok"
    ]
    assert not bad, f"{label}: tree did not evaluate clean: {bad}"
    props = evaluation.result.properties
    assert props is not None, f"{label}: evaluated ok but produced no body"
    return props


def fingerprint(evaluation: TreeEvaluation) -> tuple[str, str]:
    """A byte-strength identity of an evaluation: the content-addressed mesh id
    plus the exact repr of every mass property.

    ``mesh_glb_id`` is the sha256 of the GLB, so equality is byte identity of
    the tessellated artifact; the property repr adds the B-rep measurements the
    mesh cannot distinguish. Used by the determinism / suppress-round-trip /
    edit-and-revert legs, where "identical" must mean identical, not "close".
    """
    assert evaluation.result.mesh_glb_id is not None
    return (evaluation.result.mesh_glb_id, geometry_print(evaluation))


def geometry_print(evaluation: TreeEvaluation) -> str:
    """The GEOMETRIC half of :func:`fingerprint`: the exact repr of every mass
    property plus the exact topology counts, with NO mesh-artifact bytes."""
    props = evaluation.result.properties
    assert props is not None
    return repr(
        (
            props.volume,
            props.surface_area,
            (props.centroid.x, props.centroid.y, props.centroid.z),
            (
                props.bounding_box.min.x,
                props.bounding_box.min.y,
                props.bounding_box.min.z,
                props.bounding_box.max.x,
                props.bounding_box.max.y,
                props.bounding_box.max.z,
            ),
            props.topology.model_dump(),
        )
    )


def assert_same_solid(
    got: TreeEvaluation, want: TreeEvaluation, tol: float, label: str
) -> None:
    """Assert TWO DIFFERENT TREES produced the SAME SOLID.

    Topology counts EXACTLY; every mass property within the composition's
    documented tolerance. This — not byte identity — is the correct bar when the
    trees differ, for two measured reasons:

    * a mirror-and-fuse (or pattern-and-fuse) rebuild legitimately hands OCCT
      the same solid with a different internal FACE ORDER, and the tessellator
      walks faces in that order, so the GLB bytes differ while the solid does
      not;
    * re-integrating GProp over a rebuilt B-rep moves the last bits. Measured
      over every identity case in this module (2026-07-25, build123d 0.11.1 /
      OCCT 7.9): volume EXACTLY 0.0 in all cases, topology equal in all cases,
      worst deviation 3.638e-12 (surface area, mirror-about-x=0 applied twice),
      then 2.842e-14 (centroid.y, shell then midplane mirror). The documented
      1e-9 / 1e-8 tiers therefore carry >= 275x headroom and are NOT fitted to
      these numbers.

    Byte identity remains the bar for rebuilding the SAME tree (gate 3), which
    :func:`fingerprint` keeps.
    """
    a = properties(got, label)
    b = properties(want, label)
    assert a.topology == b.topology, (
        f"{label}: topology differs — {a.topology.model_dump()} vs "
        f"{b.topology.model_dump()}"
    )
    for field, x, y in (
        ("volume", a.volume, b.volume),
        ("surface_area", a.surface_area, b.surface_area),
        ("centroid.x", a.centroid.x, b.centroid.x),
        ("centroid.y", a.centroid.y, b.centroid.y),
        ("centroid.z", a.centroid.z, b.centroid.z),
        ("bbox.min.x", a.bounding_box.min.x, b.bounding_box.min.x),
        ("bbox.min.y", a.bounding_box.min.y, b.bounding_box.min.y),
        ("bbox.min.z", a.bounding_box.min.z, b.bounding_box.min.z),
        ("bbox.max.x", a.bounding_box.max.x, b.bounding_box.max.x),
        ("bbox.max.y", a.bounding_box.max.y, b.bounding_box.max.y),
        ("bbox.max.z", a.bounding_box.max.z, b.bounding_box.max.z),
    ):
        assert x == pytest.approx(y, abs=tol), (
            f"{label}: {field} differs — {x!r} vs {y!r} (tol {tol!r})"
        )


# --- The shared 80x80x10 base plate + the disjoint verb placements ---------------
#
# One base body and ONE placement layout for every matrix cell, chosen so that
# the verbs are MUTUALLY DISJOINT in plan and each is strictly interior. That is
# what makes the additivity invariant meaningful: when two features touch
# disjoint material, the composed volume MUST be the sum of the two deltas, and
# any deviation is the composition seam misbehaving rather than an intended
# geometric interaction. Disjointness is argued per placement below and is
# re-proved numerically by ``test_disjoint_pair_volumes_are_additive``.

S_BASE, F_BASE = _fid(1), _fid(2)
S_BOSS, F_BOSS, D_BOSS = _fid(11), _fid(12), _fid(13)
S_POCKET, F_POCKET = _fid(21), _fid(22)
F_HOLE, F_CBORE, F_CSINK = _fid(31), _fid(32), _fid(33)
F_PATTERN_L, F_PATTERN_C = _fid(41), _fid(42)
D_CLEAR, D_MID, F_MIRROR = _fid(51), _fid(52), _fid(53)
F_FILLET, F_CHAMFER, F_SHELL, F_DRAFT = _fid(61), _fid(62), _fid(63), _fid(64)

#: The base plate: [0,80] x [0,80] x [0,10] mm. V = 80*80*10 = 64000 mm^3.
#: 80 mm (not 40) is deliberate: every placement below needs room for its
#: PATTERNED and MIRRORED copies to stay strictly interior, which is what makes
#: the "N x the seed removal" and "exactly 2V" invariants well-posed.
PLATE_SIDE = 80.0
PLATE_THICKNESS = 10.0
PLATE: list[dict[str, Any]] = [
    rect_sketch(S_BASE, 0.0, 0.0, PLATE_SIDE, PLATE_SIDE),
    extrude(F_BASE, S_BASE, PLATE_THICKNESS),
]
PLATE_VOLUME = PLATE_SIDE * PLATE_SIDE * PLATE_THICKNESS

#: The plate's +Z face: outward normal +Z, area centroid (40,40,10), area 6400.
TOP_FACE = face_ref(F_BASE, (0.0, 0.0, 1.0), (40.0, 40.0, 10.0), 6400.0)
#: The plate's +X face: outward normal +X, centroid (80,40,5), area 80*10 = 800.
PLUS_X_FACE = face_ref(F_BASE, (1.0, 0.0, 0.0), (80.0, 40.0, 5.0), 800.0)

BOSS_SIDE = 12.0
BOSS_HEIGHT = 5.0
POCKET_SIDE = 12.0
BORE_R = 4.0
RECESS_R = 8.0
RECESS_DEPTH = 3.0
FILLET_R = 4.0
CHAMFER_D = 4.0
SHELL_T = 2.0
DRAFT_DEG = 5.0
#: Linear pattern step, along +Y (see ``_verbs()`` for why +Y and not +X).
PATTERN_STEP = 20.0

#: Per-verb analytic volume DELTA against the bare plate (all derived by hand;
#: each is re-checked against the kernel by ``test_single_verb_deltas``).
BOSS_DV = BOSS_SIDE * BOSS_SIDE * BOSS_HEIGHT  # +720: a 12x12x5 prism on top
POCKET_DV = -(POCKET_SIDE * POCKET_SIDE * PLATE_THICKNESS)  # -1440: through-slot
HOLE_DV = -(math.pi * BORE_R**2 * PLATE_THICKNESS)  # -160pi: r4 through-bore
CBORE_DV = HOLE_DV - math.pi * (RECESS_R**2 - BORE_R**2) * RECESS_DEPTH  # bore + ring
# A 90-deg INCLUDED countersink tapers r8 -> r4 over (8-4)/tan(45) = 4 mm.
# Frustum (pi*h/3)(R^2+Rr+r^2) = (4pi/3)(64+32+16) = 448pi/3; the bore already
# removed pi*r^2*h = 64pi of that, so the recess ADDS 448pi/3 - 64pi = 256pi/3.
CSINK_DV = HOLE_DV - (448.0 * math.pi / 3.0 - math.pi * BORE_R**2 * 4.0)
# Four vertical corners rounded at r: each loses (r^2 - pi r^2/4) per unit height.
FILLET_DV = -PLATE_THICKNESS * 4.0 * (FILLET_R**2 - math.pi * FILLET_R**2 / 4.0)
# Four vertical corners bevelled at d: each loses a d/2-leg right triangle.
CHAMFER_DV = -PLATE_THICKNESS * 4.0 * (CHAMFER_D**2 / 2.0)
# Uniform inward wall t, top face left open: the cavity is (80-2t)^2 x (10-t).
SHELL_DV = -((PLATE_SIDE - 2 * SHELL_T) ** 2 * (PLATE_THICKNESS - SHELL_T))
# Tapering the +X wall inward by `a` about XY@0 removes an 80-wide wedge of
# height 10 and setback 10*tan(a).
DRAFT_DV = -(PLATE_SIDE * 0.5 * PLATE_THICKNESS**2 * math.tan(math.radians(DRAFT_DEG)))

#: Verb kinds, used to pick the shape-independent invariant in the pair matrix.
VerbKind = Literal["add", "cut", "replicate", "modify"]


@dataclass(frozen=True)
class Verb:
    """One composable modelling verb: the features it appends + its class.

    ``delta`` is the hand-derived volume change the verb makes ON THE BARE PLATE
    (``None`` for a replicate, whose meaning is contextual by design — a pattern
    or mirror reads the immediately-preceding body-affecting feature).
    """

    name: str
    features: list[dict[str, Any]]
    kind: VerbKind
    delta: float | None = None
    #: True when the verb's result is symmetric about the plate's x-midplane
    #: x=40 (so a mirror about that plane is the identity).
    x_symmetric: bool = False
    #: True when the verb introduces a curved face or a rotated placement, so
    #: the composition is asserted at CURVED_TOL rather than PLANAR_TOL.
    curved: bool = False


def _verbs() -> dict[str, Verb]:
    """The verb catalogue on the 80x80x10 plate. Placements, argued disjoint:

    * BOSS    [34,46] x [34,46], z 10..15 (plate centre, on a datum at z=10)
    * POCKET  [16,28] x [16,28], through   (SW)
    * HOLE    r4 at (60,20) -> x 56..64, y 16..24 (SE)
    * CBORE   r8 at (60,44) -> x 52..68, y 36..52 (E)
    * CSINK   r8 at (20,44) -> x 12..28, y 36..52 (W)
    * FILLET / CHAMFER  the four vertical corners (within 4 mm of a corner)
    * SHELL   the whole body (deliberately global, not disjoint)
    * DRAFT   the +X wall's top 0.875 mm (x > 79.125)

    Pairwise clearances (centre-to-centre or centre-to-nearest-point vs the sum
    of extents): HOLE(60,20)-CBORE(60,44) = 24 > 4+8; HOLE-CSINK = 45 > 12;
    CBORE-CSINK = 40 > 16; POCKET-HOLE nearest = 32 > 4; POCKET-CBORE nearest
    = 35 > 8; POCKET-CSINK = 16 > 8; BOSS is >= 6 mm clear of every disc's
    bounding band and >= 6 mm from the pocket; every placement's max x (68) is
    clear of the drafted wall (79.125), and every placement is >= 12 mm from
    any corner, so the corner fillet/chamfer never touches one.

    Replicated-copy interiority (what makes the pattern/mirror invariants
    well-posed):

    * ``pattern_linear`` steps +Y by 20 (NOT +X): every cut placement sits in
      y <= 52, so its copy lands in y <= 72 — strictly interior and disjoint
      from the seed. (+X would push CSINK's copy off the plate, which is
      finding CM-2's shape and must not be smuggled into a routine cell.)
    * ``pattern_circular`` is 3 instances at 120 deg about the plate centre.
      count=3 rather than 4 is deliberate: a 90-deg rotation maps the SQUARE
      plate onto itself, so a 4-up whole-body ring is legitimately an identity
      and could not carry the "a pattern must change the body" invariant.
    * ``mirror_clearing`` is the YZ origin plane x=0. No first-axis verb ever
      leaves x >= 0 (the linear pattern now moves in +Y), so x=0 touches every
      body without being crossed by it -> the reflection must EXACTLY double
      the volume, which is the assertion that catches defects #2 and #3.
    * ``mirror_midplane`` is x=40, the plate's own x-midplane.
    """
    boss_plane: dict[str, Any] = {"kind": "feature", "feature_id": str(D_BOSS)}
    return {
        "extrude_add": Verb(
            "extrude_add",
            [
                datum_offset(D_BOSS, "XY", PLATE_THICKNESS),
                rect_sketch(S_BOSS, 34.0, 34.0, 46.0, 46.0, boss_plane),
                extrude(F_BOSS, S_BOSS, BOSS_HEIGHT),
            ],
            "add",
            BOSS_DV,
            x_symmetric=True,  # [34,46] is centred on x=40
        ),
        "extrude_cut": Verb(
            "extrude_cut",
            [
                rect_sketch(S_POCKET, 16.0, 16.0, 28.0, 28.0),
                extrude(F_POCKET, S_POCKET, PLATE_THICKNESS, operation="cut"),
            ],
            "cut",
            POCKET_DV,
        ),
        "hole_simple": Verb(
            "hole_simple",
            [hole(F_HOLE, TOP_FACE, (60.0, 20.0, PLATE_THICKNESS), 2 * BORE_R)],
            "cut",
            HOLE_DV,
            curved=True,
        ),
        "hole_counterbore": Verb(
            "hole_counterbore",
            [
                hole(
                    F_CBORE,
                    TOP_FACE,
                    (60.0, 44.0, PLATE_THICKNESS),
                    2 * BORE_R,
                    hole_type=counterbore(2 * RECESS_R, RECESS_DEPTH),
                )
            ],
            "cut",
            CBORE_DV,
            curved=True,
        ),
        "hole_countersink": Verb(
            "hole_countersink",
            [
                hole(
                    F_CSINK,
                    TOP_FACE,
                    (20.0, 44.0, PLATE_THICKNESS),
                    2 * BORE_R,
                    hole_type=countersink(2 * RECESS_R, 90.0),
                )
            ],
            "cut",
            CSINK_DV,
            curved=True,
        ),
        "pattern_linear": Verb(
            "pattern_linear",
            [linear_pattern(F_PATTERN_L, (0.0, 1.0, 0.0), PATTERN_STEP, 2)],
            "replicate",
            x_symmetric=True,  # a +Y translation preserves x-symmetry
        ),
        "pattern_circular": Verb(
            "pattern_circular",
            [
                circular_pattern(
                    F_PATTERN_C, (40.0, 40.0, 0.0), (0.0, 0.0, 1.0), 360.0, 3
                )
            ],
            "replicate",
            curved=True,
        ),
        "mirror_clearing": Verb(
            "mirror_clearing",
            [
                datum_offset(D_CLEAR, "YZ", 0.0),
                mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_CLEAR)}),
            ],
            "replicate",
        ),
        "mirror_midplane": Verb(
            "mirror_midplane",
            [
                datum_offset(D_MID, "YZ", 40.0),
                mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_MID)}),
            ],
            "replicate",
            x_symmetric=True,
        ),
        "fillet": Verb(
            "fillet",
            [fillet(F_FILLET, FILLET_R)],
            "modify",
            FILLET_DV,
            x_symmetric=True,
            curved=True,
        ),
        "chamfer": Verb(
            "chamfer",
            [chamfer(F_CHAMFER, CHAMFER_D)],
            "modify",
            CHAMFER_DV,
            x_symmetric=True,
        ),
        "shell": Verb(
            "shell",
            [shell(F_SHELL, SHELL_T, [TOP_FACE])],
            "modify",
            SHELL_DV,
            x_symmetric=True,
        ),
        "draft": Verb(
            "draft", [draft(F_DRAFT, DRAFT_DEG, [PLUS_X_FACE])], "modify", DRAFT_DV
        ),
    }


def reid(features: list[dict[str, Any]], offset: int) -> list[dict[str, Any]]:
    """A deep copy of *features* with every feature id shifted by *offset*.

    Needed for SELF-composition (a verb applied twice): feature ids must be
    unique within a tree (documents enforces it), so a naive ``a + a`` would be
    an invalid tree rather than a real composition. This rewrites the top-level
    ids AND every id-valued reference inside the params — profile / sketch-plane
    ``FeatureRef``s and ``SubshapeRef.feature_id`` alike — by substituting on the
    id STRINGS, so no per-feature-type knowledge is needed.
    """
    original = [entry["id"] for entry in features]
    mapping = {
        old: str(_fid(int(uuid.UUID(old).hex[-12:], 16) + offset)) for old in original
    }

    def rewrite(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: rewrite(v) for k, v in node.items()}  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        if isinstance(node, list):
            return [rewrite(v) for v in node]  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        if isinstance(node, str) and node in mapping:
            return mapping[node]
        return node

    return [rewrite(copy.deepcopy(entry)) for entry in features]


VERBS = _verbs()

#: The FIRST axis (the "context" a composed feature must reason about): one
#: representative of every body-affecting family that can precede another.
FIRST_AXIS = [
    "extrude_add",
    "extrude_cut",
    "hole_simple",
    "pattern_linear",
    "mirror_midplane",
    "fillet",
    "shell",
    "draft",
]
#: The SECOND axis (the "composer"): every shipped verb, so each one is proved
#: to reason correctly about a body produced by eight different predecessors.
SECOND_AXIS = list(VERBS)


def tol_for(*verbs: Verb) -> float:
    """The documented tolerance tier for a composition: CURVED if any
    participating verb introduces a curved face or a rotated placement."""
    return CURVED_TOL if any(v.curved for v in verbs) else PLANAR_TOL


# --- Expected outcomes for the pair matrix ---------------------------------------
#
# Every (first, second) cell is EXPLICIT. A cell that is not meaningful is
# listed with its reason rather than silently omitted (the brief's rule), and a
# cell that must degrade honestly names the exact per-feature code. Everything
# not listed here must evaluate fully `ok` and satisfy its kind's invariant.


@dataclass(frozen=True)
class ExpectedError:
    """This composition must degrade to ONE typed per-feature error."""

    code: str
    reason: str


PAIR_EXPECTATIONS: dict[tuple[str, str], ExpectedError] = {
    ("extrude_add", "shell"): ExpectedError(
        "shell_failed",
        "A 12x12x5 boss on a 10 mm plate leaves a 5 mm step; a uniform 2 mm "
        "inward offset of that stepped solid self-intersects at the step, which "
        "OCCT refuses. Honest typed error, not a silently thin wall.",
    ),
    ("shell", "extrude_add"): ExpectedError(
        "boolean_failed",
        "The boss sits entirely over the shelled cavity, so the union lands "
        "DISJOINT and would take the body from 1 lump to 2. An in-chain add "
        "must preserve the lump count (design §7.6/§MB-4) — start a second body "
        "with merge=False instead.",
    ),
    ("shell", "hole_counterbore"): ExpectedError(
        "hole_too_deep",
        "A 3 mm counterbore recess cannot fit the 2 mm shelled wall.",
    ),
    ("shell", "hole_countersink"): ExpectedError(
        "hole_too_deep",
        "A 90-deg countersink from r8 to r4 needs 4 mm; the shelled wall is 2.",
    ),
    ("fillet", "chamfer"): ExpectedError(
        "chamfer_failed",
        "The r4 corner fillets consumed the vertical corner EDGES, so the "
        "axis-parallel-Z predicate now selects the fillet cylinders' SEAM edges, "
        "which cannot be bevelled. Honest typed error, not a mangled corner.",
    ),
}

#: Cells deliberately NOT asserted in the matrix, each with its reason (never
#: silently omitted — the brief's rule). Only the DIAGONAL is skipped, and it is
#: covered instead by ``test_self_composition`` / ``test_self_composition_errors``,
#: which give the second instance DISTINCT feature ids via :func:`reid`.
DIAGONAL_SKIP_REASON = (
    "Self-composition (the same verb twice at the SAME placement) would need two "
    "features with identical ids, which is not a valid tree (documents enforces "
    "unique feature ids). Covered explicitly, with re-issued ids, by "
    "test_self_composition* — including the 'a second identical hole removes "
    "nothing and must error' case."
)
PAIR_SKIPS: dict[tuple[str, str], str] = {
    (name, name): DIAGONAL_SKIP_REASON for name in FIRST_AXIS
}


def pair_ids() -> Iterator[tuple[str, str]]:
    for first in FIRST_AXIS:
        for second in SECOND_AXIS:
            if (first, second) not in PAIR_SKIPS:
                yield (first, second)


# =================================================================================
# SECTION A — the five audited defects, as seeded composition cases
# =================================================================================
#
# Each asserts the analytic value AND states what the pre-fix kernel returned, so
# a future reader can see the assertion is real (it FAILS on the old behaviour).


def test_seed1_pattern_of_a_hole_arrays_the_cut_not_the_body() -> None:
    """SEEDED DEFECT #1 (FINDINGS #1, fixed `feb4318`) — pattern x hole.

    Chain: sketch -> extrude add 10 -> HOLE Ø8 through at (10,20) -> LINEAR
    PATTERN +X, spacing 10, count 3.

    Analytic: a 40x40x10 plate is 16000 mm^3; three DISJOINT r4 through-bores
    (centres x = 10, 20, 30 at y = 20; adjacent gap 10 - 8 = 2 mm, each strictly
    interior since 30 + 4 = 34 < 40) remove exactly 3 x pi*4^2*10 = 480pi, so
    V = 16000 - 480pi = 14492.0355 mm^3.

    PRE-FIX the cut-array inference recognised ONLY extrude-cut, so a Hole
    source fell through to the WHOLE-BODY UNION path: the audit measured
    51773.8 mm^3 on its fixture (FINDINGS #1) and 59497.3 on the fix's fixture
    — i.e. the pattern INCREASED the volume of a cut. This assertion fails on
    that behaviour by ~37000 mm^3.
    """
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 10.0)]
    top = face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 10.0), 1600.0)
    props = properties(
        evaluate(
            [
                *plate,
                hole(F_HOLE, top, (10.0, 20.0, 10.0), 8.0),
                linear_pattern(F_PATTERN_L, (1.0, 0.0, 0.0), 10.0, 3),
            ]
        ),
        "seed1",
    )

    expected = 16000.0 - 3 * math.pi * 4.0**2 * 10.0
    assert props.volume == pytest.approx(expected, abs=CURVED_TOL)
    # A pattern of a CUT must never grow the body.
    assert props.volume < 16000.0
    # 9 faces = 2 caps + 4 walls + 3 bore cylinders; 21 edges = 2*(4 + 3) loop
    # edges + 4 vertical box corners + 3 cylinder seams. A whole-body union
    # would report a wholly different count.
    assert props.topology.model_dump() == {"faces": 9, "edges": 21, "shells": 1}


def test_seed2_mirror_of_a_hole_keeps_the_hole() -> None:
    """SEEDED DEFECT #2 (FINDINGS #2, fixed `feb4318`) — mirror x hole.

    Chain (the shipped golden `mirror-hole-feature-plate-40x40x20`'s fixture,
    re-derived here from scratch): 40x40 plate extruded 20 -> HOLE Ø8 through at
    (10,20) -> datum YZ@20 (the x-midplane) -> MIRROR.

    Analytic: 40*40*20 = 32000; the seed bore at x=10 reflects to x=30, giving
    TWO disjoint interior r4 through-bores, so V = 32000 - 2*pi*4^2*20 =
    32000 - 640pi = 29989.3807 mm^3.

    PRE-FIX the mirror reflected the whole FILLED body and unioned it, so the
    reflection's material filled the original bore and the result was the
    featureless brick 32000.0 with 6 faces. This assertion fails on that by
    2010.6 mm^3 and on topology by 2 faces.
    """
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 20.0)]
    top = face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 20.0), 1600.0)
    props = properties(
        evaluate(
            [
                *plate,
                hole(F_HOLE, top, (10.0, 20.0, 20.0), 8.0),
                datum_offset(D_MID, "YZ", 20.0),
                mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_MID)}),
            ]
        ),
        "seed2",
    )

    assert props.volume == pytest.approx(32000.0 - 640 * math.pi, abs=CURVED_TOL)
    assert props.volume < 32000.0, "the mirror filled the hole (FINDINGS #2)"
    # 8 faces = 6 box + 2 bore cylinders; 18 edges = 12 box + 2*2 bore circles
    # + 2 seams.
    assert props.topology.model_dump() == {"faces": 8, "edges": 18, "shells": 1}


def test_seed3_mirror_of_a_cut_about_a_clearing_plane_doubles_the_body() -> None:
    """SEEDED DEFECT #3 (code-review regression B, fixed `fa30220`) —
    mirror x extrude-cut about a CLEARING plane.

    Chain: 40x40 plate extruded 20 -> POCKET [10,20]x[10,30] cut 10 -> datum
    YZ@40 (the block's OWN +X face) -> MIRROR.

    Analytic: the pocketed block is 32000 - 10*20*10 = 30000 mm^3 over
    x in [0,40]. The plane x=40 touches the body but is not crossed by it, so
    the reflection is a second pocketed block over x in [40,80] that fuses on the
    shared face: V = 2 x 30000 = 60000 mm^3, one shell, bbox x in [0,80].

    PRE-FIX `mirror_cut` fired whenever the preceding feature was a cut and never
    checked that a removal happened, so the reflected tool at x in [60,70] cut
    nothing and the mirror was a SILENT NO-OP: 30000 mm^3 at x in [0,40], every
    feature `ok`. This assertion fails on that by 30000 mm^3 and on the bbox.
    """
    evaluation = evaluate(
        [
            rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0),
            extrude(F_BASE, S_BASE, 20.0),
            rect_sketch(S_POCKET, 10.0, 10.0, 20.0, 30.0),
            extrude(F_POCKET, S_POCKET, 10.0, operation="cut"),
            datum_offset(D_CLEAR, "YZ", 40.0),
            mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_CLEAR)}),
        ]
    )
    props = properties(evaluation, "seed3")

    assert props.volume == pytest.approx(60000.0, abs=PLANAR_TOL)
    assert props.bounding_box.max.x == pytest.approx(80.0, abs=PLANAR_TOL)
    # 16 faces = 6 outer + 5 pocket faces per half x 2; 1 shell (fused halves).
    assert props.topology.model_dump() == {"faces": 16, "edges": 36, "shells": 1}


def test_seed4_mirror_does_not_weld_an_earlier_cut_shut() -> None:
    """SEEDED DEFECT #4 (the guard on #3's FIX, `fa30220`) — an EARLIER cut must
    survive the mirror.

    Chain: 40x40 plate extruded 20 -> POCKET A [4,8]x[10,30] cut 10 -> POCKET B
    [14,18]x[10,30] cut 10 -> datum YZ@20 -> MIRROR.

    Analytic: only the IMMEDIATELY-preceding cut's tools are recoverable, so the
    mirror reflects B (to x in [22,26]) and leaves A alone:
    V = 32000 - 800 (A) - 800 (B) - 800 (B') = 29600 mm^3, three notches.

    The tempting "general" fix — mirror_union then re-subtract both tool sets —
    returns 30400 mm^3 because the union FILLS pocket A (only B's tools are
    known to re-cut). That is strictly worse than the bug it fixes, so this
    case pins 29600 as a NON-regression: it fails at 30400 by 800 mm^3 and on
    the face count (16 instead of 21).
    """
    props = properties(
        evaluate(
            [
                rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0),
                extrude(F_BASE, S_BASE, 20.0),
                rect_sketch(S_POCKET, 4.0, 10.0, 8.0, 30.0),
                extrude(F_POCKET, S_POCKET, 10.0, operation="cut"),
                rect_sketch(_fid(23), 14.0, 10.0, 18.0, 30.0),
                extrude(_fid(24), _fid(23), 10.0, operation="cut"),
                datum_offset(D_MID, "YZ", 20.0),
                mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_MID)}),
            ]
        ),
        "seed4",
    )

    assert props.volume == pytest.approx(29600.0, abs=PLANAR_TOL)
    # 6 outer + 5 per notch x 3 notches = 21. A welded-shut pocket A reads 16.
    assert props.topology.faces == 21
    assert props.topology.shells == 1


# --- SEEDED DEFECT #5 — the same-face reference chain ----------------------------
#
# The FINDINGS #3 / regression-A fixture, authored as the real user story so BOTH
# halves of the defect are observable through `evaluate_tree`:
#
#   1. plate 40x40x10                  (top face: area 1600, centroid (20,20,10))
#   2. HOLE A at (8,8), diameter EDITED (its face ref = the pristine signature)
#   3. HOLE B at (30,20) Ø6            (its face ref = the post-A signature)
#   4. on_face DATUM on the top face   (its face ref = the post-A+B signature)
#   5. sketch [-5,5]^2 on that datum -> extrude 4 -> a 10x10x4 boss
#
# Editing A's diameter Ø6 -> Ø8 moves the shared top face's AREA and CENTROID but
# not its supporting plane, so:
#   * PRE-FINDINGS-#3 the strict signature match orphaned B and the datum
#     (`subshape_unresolved`), i.e. features 3-5 went red on an unrelated edit;
#   * POST-#3 / PRE-regression-A the resilient tier resolved them but returned the
#     matched face's CURRENT area centroid, silently TRANSLATING the datum (hence
#     the boss) by 0.1156 mm in x AND y on the audit's fixture.

A_POS, B_POS = (8.0, 8.0), (30.0, 20.0)
HOLE_B_D = 6.0
SIB_S, SIB_E = _fid(71), _fid(72)
SIB_A, SIB_B, SIB_DATUM = _fid(73), _fid(74), _fid(75)


def _top_face_signature(
    bores: list[tuple[float, float, float]],
) -> tuple[float, tuple[float, float, float]]:
    """Analytic (area, centroid) of the 40x40 top face after the given bores.

    Pure first-moment arithmetic over the 1600 mm^2 square minus each bore disc
    — the same quantity the kernel computes from the B-rep, derived by hand so
    the stored signatures in the fixture are authored, never recorded.
    """
    area = 1600.0
    mx = my = 1600.0 * 20.0
    for x, y, diameter in bores:
        disc = math.pi * (diameter / 2.0) ** 2
        area -= disc
        mx -= disc * x
        my -= disc * y
    return area, (mx / area, my / area, 10.0)


def _sibling_chain(diameter_a: float) -> list[dict[str, Any]]:
    area_a, centroid_a = _top_face_signature([(*A_POS, HOLE_B_D)])
    area_ab, centroid_ab = _top_face_signature([(*A_POS, HOLE_B_D), (*B_POS, HOLE_B_D)])
    pristine = face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 10.0), 1600.0)
    after_a = face_ref(F_BASE, (0.0, 0.0, 1.0), centroid_a, area_a)
    after_ab = face_ref(F_BASE, (0.0, 0.0, 1.0), centroid_ab, area_ab)
    datum_plane_ref: dict[str, Any] = {
        "kind": "feature",
        "feature_id": str(SIB_DATUM),
    }
    return [
        rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0),
        extrude(F_BASE, S_BASE, 10.0),
        hole(SIB_A, pristine, (*A_POS, 10.0), diameter_a),
        hole(SIB_B, after_a, (*B_POS, 10.0), HOLE_B_D),
        datum_on_face(SIB_DATUM, after_ab),
        rect_sketch(SIB_S, -5.0, -5.0, 5.0, 5.0, datum_plane_ref),
        extrude(SIB_E, SIB_S, 4.0),
    ]


@pytest.mark.parametrize("diameter_a", [6.0, 8.0])
def test_seed5_sibling_face_reference_is_stable_under_a_neighbours_edit(
    diameter_a: float,
) -> None:
    """SEEDED DEFECT #5 (FINDINGS #3 `2b6b72e` + code-review regression A).

    Both halves, asserted through the tree:

    * every feature evaluates ``ok`` at BOTH diameters (pre-#3: hole B and the
      on-face datum went ``subshape_unresolved`` at Ø8, taking the boss with
      them under the strict-prefix rule);
    * the resolved datum plane origin is EXACTLY the STORED signature centroid
      and does NOT move with the edit (pre-regression-A it returned the matched
      face's CURRENT centroid, translating the datum — and every sketch/mate
      seated on it — by 0.1734 mm in x and 0.1766 mm in y on this fixture);
    * the composed volume and centroid match the closed form, with the boss
      centred on the STORED origin (so a translated datum is visible in the
      centroid too, ~4.5e-3 mm — 4.5e6 x the tolerance).
    """
    evaluation = evaluate(_sibling_chain(diameter_a))
    assert statuses(evaluation) == ["ok"] * 7, error_codes(evaluation)
    props = properties(evaluation, f"seed5 Ø{diameter_a}")

    _area_ab, stored = _top_face_signature([(*A_POS, HOLE_B_D), (*B_POS, HOLE_B_D)])
    plane = evaluation.datum_planes[SIB_DATUM]
    assert tuple(plane.origin) == pytest.approx(stored, abs=PLANAR_TOL), (
        "the same-face reference resolved to a TRANSLATED origin — every sketch "
        "and datum seated on that face silently moved (regression A)"
    )
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=PLANAR_TOL)

    bore_a = math.pi * (diameter_a / 2.0) ** 2 * 10.0
    bore_b = math.pi * (HOLE_B_D / 2.0) ** 2 * 10.0
    boss = 10.0 * 10.0 * 4.0
    volume = 16000.0 - bore_a - bore_b + boss
    assert props.volume == pytest.approx(volume, abs=CURVED_TOL)

    # First moments: plate + boss (centred on the STORED datum origin) minus the
    # two bores. z: plate 5, bores 5, boss 12.
    def moment(plate_c: float, a_c: float, b_c: float, boss_c: float) -> float:
        return (
            16000.0 * plate_c - bore_a * a_c - bore_b * b_c + boss * boss_c
        ) / volume

    assert props.centroid.x == pytest.approx(
        moment(20.0, A_POS[0], B_POS[0], stored[0]), abs=CURVED_TOL
    )
    assert props.centroid.y == pytest.approx(
        moment(20.0, A_POS[1], B_POS[1], stored[1]), abs=CURVED_TOL
    )
    assert props.centroid.z == pytest.approx(
        moment(5.0, 5.0, 5.0, 12.0), abs=CURVED_TOL
    )


def test_seed5_edit_then_revert_restores_the_identical_shape() -> None:
    """The round-trip half of defect #5: Ø6 -> Ø8 -> Ø6 must return the
    BYTE-identical body, and the intermediate must genuinely differ.

    Byte identity (the content-addressed mesh id, not just matching mass
    properties) proves the rebuild is a pure function of the tree — a resolver
    that accumulated drift across edits, or a cached body, would show here.
    """
    first, edited, reverted = (
        fingerprint(evaluate(_sibling_chain(d))) for d in (6.0, 8.0, 6.0)
    )
    assert first != edited, "the diameter edit changed nothing"
    assert reverted == first, "edit-then-revert did not restore the identical shape"


# =================================================================================
# SECTION B — hand-derived analytic compositions
# =================================================================================


def test_single_verb_deltas() -> None:
    """Every verb's HAND-DERIVED delta against the bare plate.

    The matrix's baseline: if a single verb's own analytic value were wrong,
    every additivity/invariant assertion built on it would be meaningless. Also
    pins the base plate itself (36000 mm^3, 6/12/1).
    """
    base = properties(evaluate(PLATE), "plate")
    assert base.volume == pytest.approx(PLATE_VOLUME, abs=PLANAR_TOL)
    assert base.topology.model_dump() == {"faces": 6, "edges": 12, "shells": 1}

    for name, verb in VERBS.items():
        if verb.delta is None:
            continue  # replicate verbs are contextual by design (see Verb.delta)
        props = properties(evaluate(PLATE + verb.features), f"plate+{name}")
        assert props.volume == pytest.approx(
            PLATE_VOLUME + verb.delta, abs=tol_for(verb)
        ), f"{name}: analytic delta {verb.delta} not reproduced"


#: Pairs whose material changes are DISJOINT, so the composed volume must be the
#: exact sum of the two hand-derived deltas. Each is argued in ``_verbs()``.
#:
#: NOT included, deliberately: any pair of ``extrude_add``/``extrude_cut`` with
#: ``fillet``/``chamfer``. Those verbs select edges by the GLOBAL
#: ``axis_parallel: Z`` predicate, so a boss or a pocket CONTRIBUTES vertical
#: edges of its own and the composed delta is not the sum of the two isolated
#: deltas. That is correct behaviour, not additivity — and it is asserted
#: analytically in its own right by
#: ``test_edge_predicate_reaches_a_boss_added_after_the_base`` and
#: ``test_edge_predicate_reaches_a_pockets_internal_corners``.
ADDITIVE_PAIRS = [
    ("extrude_add", "extrude_cut"),
    ("extrude_add", "hole_simple"),
    ("extrude_add", "hole_counterbore"),
    ("extrude_add", "hole_countersink"),
    ("extrude_cut", "hole_simple"),
    ("extrude_cut", "hole_counterbore"),
    ("extrude_cut", "hole_countersink"),
    ("hole_simple", "hole_counterbore"),
    ("hole_simple", "hole_countersink"),
    ("hole_simple", "fillet"),
    ("hole_simple", "chamfer"),
    ("hole_simple", "draft"),
    ("extrude_cut", "draft"),
    ("hole_counterbore", "draft"),
    ("hole_countersink", "draft"),
    ("hole_counterbore", "fillet"),
    ("hole_countersink", "chamfer"),
]


@pytest.mark.parametrize(("first", "second"), ADDITIVE_PAIRS, ids=lambda p: str(p))
def test_disjoint_pair_volumes_are_additive(first: str, second: str) -> None:
    """DISJOINT composition is EXACTLY additive, in BOTH orders.

    The sharpest general statement of "feature N must reason correctly about the
    body feature N-1 produced": when the two features touch disjoint material,
    V(A then B) = V(plate) + dA + dB, independent of order. A composed feature
    that re-derived its tool from the wrong body, double-counted the seed, or
    filled a neighbouring void shows up here as a volume that is not the sum.
    """
    a, b = VERBS[first], VERBS[second]
    assert a.delta is not None and b.delta is not None
    expected = PLATE_VOLUME + a.delta + b.delta
    tol = tol_for(a, b)

    forward = properties(evaluate(PLATE + a.features + b.features), f"{first}+{second}")
    backward = properties(
        evaluate(PLATE + b.features + a.features), f"{second}+{first}"
    )
    assert forward.volume == pytest.approx(expected, abs=tol)
    assert backward.volume == pytest.approx(expected, abs=tol)
    assert forward.topology == backward.topology


def test_pattern_of_a_disjoint_cut_removes_exactly_n_times_the_seed() -> None:
    """A pattern of N instances of a CUT removes exactly N x the single removal
    when the placements are disjoint — for extrude-cut, simple, counterbore and
    countersink hole sources alike.

    The generalisation of seed #1 across every cut source the inference
    recognises. Uses the shared layout, whose +Y/20 mm copies are argued
    strictly interior and disjoint from their seed in ``_verbs()``.
    """
    pattern = VERBS["pattern_linear"]
    for name in ("extrude_cut", "hole_simple", "hole_counterbore", "hole_countersink"):
        verb = VERBS[name]
        assert verb.delta is not None
        props = properties(
            evaluate(PLATE + verb.features + pattern.features), f"{name}+pattern"
        )
        # count = 2 -> the seed plus one copy, each removing |delta|.
        assert props.volume == pytest.approx(
            PLATE_VOLUME + 2 * verb.delta, abs=tol_for(verb, pattern)
        ), f"{name}: a 2-up pattern of the cut did not remove 2x the seed"


def test_circular_pattern_of_a_hole_removes_exactly_n_bores() -> None:
    """The ROTATED cut-array: 3 bores at 120 deg about the plate centre remove
    exactly 3 x pi r^2 h. Rotation (unlike translation) exercises the trig
    placement path, which is why this case sits at CURVED_TOL."""
    props = properties(
        evaluate(
            PLATE + VERBS["hole_simple"].features + VERBS["pattern_circular"].features
        ),
        "hole+circular",
    )
    assert props.volume == pytest.approx(PLATE_VOLUME + 3 * HOLE_DV, abs=CURVED_TOL)
    # 2 caps + 4 walls + 3 bore cylinders = 9 faces; 2*(4+3) + 4 + 3 = 21 edges.
    assert props.topology.model_dump() == {"faces": 9, "edges": 21, "shells": 1}


def test_shell_and_hole_compose_analytically_in_both_orders() -> None:
    """A case where ORDER LEGITIMATELY MATTERS, with both answers hand-derived —
    the control that proves the order-independence suite is not vacuous.

    * HOLE then SHELL: the bore exists when the body is hollowed, so the wall
      offset wraps it as a 2 mm tube through the cavity. The cavity becomes
      ((80-4)^2 - pi*(4+2)^2) * 8, so
      V = 64000 - 160pi - (76^2 - 36pi)*8 = 17792 + 128pi.
    * SHELL then HOLE: the cavity is already empty, so a through-bore only
      pierces the 2 mm floor: V = 17792 - pi*4^2*2.
    """
    hole_then_shell = properties(
        evaluate(PLATE + VERBS["hole_simple"].features + VERBS["shell"].features),
        "hole+shell",
    )
    shell_then_hole = properties(
        evaluate(PLATE + VERBS["shell"].features + VERBS["hole_simple"].features),
        "shell+hole",
    )

    shelled = PLATE_VOLUME + SHELL_DV  # 17792
    assert hole_then_shell.volume == pytest.approx(
        shelled + 128 * math.pi, abs=CURVED_TOL
    )
    assert shell_then_hole.volume == pytest.approx(
        shelled - math.pi * BORE_R**2 * SHELL_T, abs=CURVED_TOL
    )
    assert hole_then_shell.volume != shell_then_hole.volume


def test_edge_predicate_reaches_a_boss_added_after_the_base() -> None:
    """A fillet/chamfer's ``axis_parallel: Z`` predicate is GLOBAL over the body
    that exists at its point in the tree, so it also rounds/bevels the four
    vertical edges of a boss added earlier.

    Analytic, and a real composition statement: the modifier's delta is a
    function of the COMPOSED body, not of the base. The 12x12x5 boss contributes
    four 5 mm-tall vertical edges, so

      fillet:  d = -10*4*(r^2 - pi r^2/4)  -  5*4*(r^2 - pi r^2/4)
      chamfer: d = -10*4*(d^2/2)           -  5*4*(d^2/2)

    A predicate that silently missed the boss's edges (or double-counted the
    plate's) fails here; so would a fillet applied to the pre-boss body.
    """
    corner_fillet = FILLET_R**2 - math.pi * FILLET_R**2 / 4.0
    corner_chamfer = CHAMFER_D**2 / 2.0
    for name, per_corner in (("fillet", corner_fillet), ("chamfer", corner_chamfer)):
        props = properties(
            evaluate(PLATE + VERBS["extrude_add"].features + VERBS[name].features),
            f"boss+{name}",
        )
        expected = (
            PLATE_VOLUME
            + BOSS_DV
            - PLATE_THICKNESS * 4.0 * per_corner
            - BOSS_HEIGHT * 4.0 * per_corner
        )
        assert props.volume == pytest.approx(expected, abs=tol_for(VERBS[name])), (
            f"boss+{name}: the edge predicate did not see the boss's four "
            "vertical edges (or saw the wrong body)"
        )


def test_edge_predicate_reaches_a_pockets_internal_corners() -> None:
    """The same predicate over a CONCAVE composition: a through-pocket's four
    internal vertical corners.

    Rounding/bevelling a CONCAVE edge ADDS material (it fills the void's corner),
    and the pocket is a through-cut of the SAME 10 mm height as the plate with
    exactly four vertical corners of the same radius — so the added material
    EXACTLY cancels the plate's four convex corners and the composed volume is
    the bare pocketed volume, to the tolerance. The topology must still change
    (4 -> 8 rounded corners), which is what makes this a change, not a no-op.

    This is why the matrix's ``modify`` invariant is "the body changed" (byte
    fingerprint) rather than "the volume decreased": an exact cancellation is a
    correct result that a naive volume-only rule would call a silent no-op.
    """
    pocketed = properties(evaluate(PLATE + VERBS["extrude_cut"].features), "pocketed")
    for name in ("fillet", "chamfer"):
        props = properties(
            evaluate(PLATE + VERBS["extrude_cut"].features + VERBS[name].features),
            f"pocket+{name}",
        )
        assert props.volume == pytest.approx(
            pocketed.volume, abs=tol_for(VERBS[name])
        ), f"pocket+{name}: the convex/concave corner volumes did not cancel"
        assert props.topology.faces > pocketed.topology.faces
        assert props.topology.edges > pocketed.topology.edges


def test_draft_tilts_two_of_the_four_vertical_edges_out_of_the_predicate() -> None:
    """DRAFT then FILLET removes exactly HALF the fillet volume.

    Tapering the +X wall by 5 deg tilts the two vertical edges it shares with the
    +/-Y walls out of Z-parallel, so the ``axis_parallel: Z`` predicate then
    matches only the TWO edges at x=0: d = -10*2*(r^2 - pi r^2/4), half of the
    un-drafted fillet's delta.

    A composed feature whose selector was evaluated against the PRE-draft body
    would round all four and fail here by exactly the other half.
    """
    props = properties(
        evaluate(PLATE + VERBS["draft"].features + VERBS["fillet"].features),
        "draft+fillet",
    )
    assert props.volume == pytest.approx(
        PLATE_VOLUME + DRAFT_DV + FILLET_DV / 2.0, abs=CURVED_TOL
    )


def test_revolve_composes_with_hole_and_a_circular_pattern() -> None:
    """A NON-prismatic base composed with a cut and a rotated cut-array.

    Ring: the profile x in [10,20], z in [0,15] on XZ revolved 360 deg about the
    sketch centerline (the Z axis) -> an annulus r 10..20, h 15, so
    V = pi(20^2 - 10^2)*15 = 4500pi. Its +Z face is the annulus of area 300pi.
    Then a Ø6 through-bore at (15,0) on that face (-9pi*15 = -135pi) and a 6-up
    circular pattern of it about the axis (6 disjoint bores at r 15, adjacent
    centre gap 15 mm >> 6 mm): V = 4500pi - 6*135pi = 3690pi.
    """
    ring = [
        revolve_profile_sketch(
            S_BASE,
            {"kind": "datum_plane", "plane": "XZ"},
            [(10.0, 0.0), (20.0, 0.0), (20.0, 15.0), (10.0, 15.0)],
            ((0.0, 0.0), (0.0, 15.0)),
        ),
        revolve(F_BASE, S_BASE),
    ]
    ring_top = face_ref(F_BASE, (0.0, 0.0, 1.0), (0.0, 0.0, 15.0), 300 * math.pi)

    bare = properties(evaluate(ring), "ring")
    assert bare.volume == pytest.approx(4500 * math.pi, abs=CURVED_TOL)

    drilled = properties(
        evaluate([*ring, hole(F_HOLE, ring_top, (15.0, 0.0, 15.0), 6.0)]), "ring+hole"
    )
    assert drilled.volume == pytest.approx(
        4500 * math.pi - 135 * math.pi, abs=CURVED_TOL
    )

    arrayed = properties(
        evaluate(
            [
                *ring,
                hole(F_HOLE, ring_top, (15.0, 0.0, 15.0), 6.0),
                circular_pattern(
                    F_PATTERN_C, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 360.0, 6
                ),
            ]
        ),
        "ring+hole+circular",
    )
    assert arrayed.volume == pytest.approx(3690 * math.pi, abs=CURVED_TOL)


def test_triple_hole_pattern_then_clearing_mirror() -> None:
    """A TRIPLE: hole -> linear pattern -> mirror about a clearing plane.

    Chain: 40x40x10 plate -> Ø8 bore at (10,20) -> 3-up +X pattern (x = 10,20,30)
    -> datum YZ@0 -> mirror. The three-bore plate is 16000 - 480pi; the plane
    x=0 is its own -X face, so the reflection fuses on that face:
    V = 2(16000 - 480pi) = 28984.071 mm^3 over x in [-40,40].

    Composition depth matters: the pattern must array the hole's cut (defect #1)
    AND the mirror must then double the ALREADY-DRILLED body (defect #2/#3). A
    regression in either shows up as 2x16000, 16000-480pi, or 32000.
    """
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 10.0)]
    top = face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 10.0), 1600.0)
    props = properties(
        evaluate(
            [
                *plate,
                hole(F_HOLE, top, (10.0, 20.0, 10.0), 8.0),
                linear_pattern(F_PATTERN_L, (1.0, 0.0, 0.0), 10.0, 3),
                datum_offset(D_CLEAR, "YZ", 0.0),
                mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_CLEAR)}),
            ]
        ),
        "triple hole+pattern+mirror",
    )
    assert props.volume == pytest.approx(2 * (16000.0 - 480 * math.pi), abs=CURVED_TOL)
    assert props.bounding_box.min.x == pytest.approx(-40.0, abs=PLANAR_TOL)
    assert props.bounding_box.max.x == pytest.approx(40.0, abs=PLANAR_TOL)
    assert props.topology.shells == 1


def test_triple_pocket_fillet_shell_is_a_valid_single_lump() -> None:
    """A TRIPLE with no closed form: pocket -> fillet -> shell.

    No analytic volume exists for the filleted-then-shelled cavity, so this
    asserts the invariants that must hold anyway: strictly less material than
    the un-shelled body, one shell, and — the real point — that the three
    modifiers compose at all instead of degrading. Its numeric fidelity is
    covered by the STEP round-trip leg.
    """
    pocketed = properties(evaluate(PLATE + VERBS["extrude_cut"].features), "pocket")
    props = properties(
        evaluate(
            PLATE
            + VERBS["extrude_cut"].features
            + VERBS["fillet"].features
            + VERBS["shell"].features
        ),
        "pocket+fillet+shell",
    )
    assert 0.0 < props.volume < pocketed.volume
    assert props.topology.shells == 1
    assert props.topology.faces > pocketed.topology.faces


# =================================================================================
# SECTION C — the pair matrix: shape-independent invariants over every cell
# =================================================================================


def _assert_valid_solid(props: ShapeProperties, label: str) -> None:
    assert props.volume > 0.0, f"{label}: non-positive volume {props.volume}"
    assert props.surface_area > 0.0, f"{label}: non-positive area"
    assert props.topology.shells >= 1, f"{label}: no shell"
    assert props.topology.faces >= 4, f"{label}: fewer faces than a tetrahedron"


@pytest.mark.parametrize(("first", "second"), list(pair_ids()), ids=lambda p: str(p))
def test_pair_matrix(first: str, second: str) -> None:
    """THE MATRIX. For every (first, second) cell: either the declared typed
    error, or a valid solid satisfying the SECOND verb's kind invariant.

    Invariants, none of which needs a per-combination golden:

    * ``add``       — volume STRICTLY increases; the bbox never shrinks.
    * ``cut``       — volume STRICTLY decreases (a cut may never grow the body,
                      the FINDINGS #1 symptom) and the bbox never grows.
    * ``modify``    — the body CHANGES (no silent no-op) and the bbox never grows
                      (fillet/chamfer/shell/draft are all inward).
    * ``replicate`` — volume is in (0, 2V] for a mirror (a reflect-and-union can
                      never exceed 2V, a reflected cut can only remove), and a
                      CLEARING mirror is EXACTLY 2V (this is the assertion that
                      catches defects #2 and #3, in all eight contexts). A
                      pattern must CHANGE the body — never a silent no-op.

    An ERROR cell additionally asserts the strict-prefix contract: the reported
    last-good body is EXACTLY the first verb's body, so a failed composition
    never leaves a half-applied one behind.
    """
    a, b = VERBS[first], VERBS[second]
    tol = tol_for(a, b)
    base = evaluate(PLATE + a.features)
    before = properties(base, f"plate+{first}")
    evaluation = evaluate(PLATE + a.features + b.features)
    label = f"{first} x {second}"

    expected_error = PAIR_EXPECTATIONS.get((first, second))
    if expected_error is not None:
        assert error_codes(evaluation) == [expected_error.code], (
            f"{label}: expected the typed {expected_error.code} "
            f"({expected_error.reason}) — got {error_codes(evaluation)}"
        )
        assert fingerprint(evaluation) == fingerprint(base), (
            f"{label}: the last-good body is not the first verb's body — a "
            "failed feature must leave the body untouched (strict prefix §4.3)"
        )
        return

    props = properties(evaluation, label)
    _assert_valid_solid(props, label)

    # Mirroring an x-symmetric body about its own midplane is the ONE legitimate
    # identity in the matrix: the reflection coincides with the body. Assert the
    # SOLID is unchanged (topology exactly, properties within tolerance — a
    # mirror that perturbed a symmetric body shows here) and stop; the "must
    # change the body" rule below does not apply.
    if second == "mirror_midplane" and a.x_symmetric:
        assert_same_solid(
            evaluation,
            base,
            tol,
            f"{label} (mirroring an x-symmetric body about its own midplane must "
            "be the identity)",
        )
        return

    # UNIVERSAL "no silent no-op": a feature that reports ok must have CHANGED
    # the body in some observable way. Volume alone is not enough — a fillet can
    # remove convex material and add exactly as much back at a concave edge (see
    # test_edge_predicate_reaches_a_pockets_internal_corners) — so this compares
    # the byte-strength fingerprint (mesh sha256 + every mass property + exact
    # topology counts).
    assert fingerprint(evaluation) != fingerprint(base), (
        f"{label}: the second feature reported ok but produced a BYTE-IDENTICAL "
        "body — a silent no-op (compare findings CM-2 / CM-3)"
    )

    if b.kind == "add":
        assert props.volume > before.volume + tol, f"{label}: an add lost material"
        assert props.bounding_box.max.z >= before.bounding_box.max.z - tol
    elif b.kind == "cut":
        assert props.volume < before.volume - tol, (
            f"{label}: a CUT did not remove material "
            f"({before.volume!r} -> {props.volume!r})"
        )
        assert props.bounding_box.max.x <= before.bounding_box.max.x + tol
        assert props.bounding_box.max.y <= before.bounding_box.max.y + tol
    elif b.kind == "modify":
        # An inward modifier may not GROW the envelope. Its volume may be
        # unchanged (the convex/concave fillet cancellation above), which the
        # universal fingerprint check already covers.
        assert props.bounding_box.max.x <= before.bounding_box.max.x + tol
        assert props.bounding_box.max.y <= before.bounding_box.max.y + tol
        assert props.bounding_box.max.z <= before.bounding_box.max.z + tol
    else:
        assert b.kind == "replicate"
        if second == "mirror_clearing":
            assert props.volume == pytest.approx(2.0 * before.volume, abs=tol), (
                f"{label}: a mirror about a plane the body does NOT cross must "
                f"EXACTLY double the volume ({before.volume!r} -> "
                f"{props.volume!r}, expected {2.0 * before.volume!r}). A silent "
                "no-op reads 1x (defect #3); a whole-body union that fills the "
                "body's own voids reads more than 2x minus the voids (defect #2)."
            )
        elif second == "mirror_midplane":
            # Asymmetric first (the symmetric case returned above as an
            # identity): a reflect-and-union can never exceed 2V, and a
            # reflected CUT can only remove.
            assert props.volume <= 2.0 * before.volume + tol, (
                f"{label}: a mirror produced MORE than twice the body"
            )
        else:
            assert props.volume != pytest.approx(before.volume, abs=tol), (
                f"{label}: the pattern was a SILENT NO-OP — the body is "
                f"unchanged at {props.volume!r} and every feature reported ok"
            )


def test_pair_matrix_covers_every_shipped_verb() -> None:
    """Coverage audit (gate 1): every verb in the catalogue must appear on the
    SECOND axis (proved to compose after eight different predecessors), and
    every body-affecting family must appear on the FIRST axis.

    A new feature type that ships without a matrix row/column fails HERE, so the
    gap is a red gate rather than a quiet omission.
    """
    assert set(SECOND_AXIS) == set(VERBS)
    families = {
        "extrude_add",
        "extrude_cut",
        "hole_simple",
        "pattern_linear",
        "mirror_midplane",
        "fillet",
        "shell",
        "draft",
    }
    assert families <= set(FIRST_AXIS)
    # 8 x 13 cells, minus the explicitly-skipped ones.
    assert len(list(pair_ids())) == len(FIRST_AXIS) * len(SECOND_AXIS) - len(PAIR_SKIPS)


# =================================================================================
# SECTION D — order-independence cross-checks
# =================================================================================

#: Pairs whose two evaluation orders MUST agree exactly (disjoint material, so
#: no interaction can depend on which came first).
#: NOT included (order LEGITIMATELY matters, and is asserted elsewhere):
#: shell x hole (``test_shell_and_hole_compose_analytically_in_both_orders``),
#: pocket/boss x fillet/chamfer (the global edge predicate sees the pocket's or
#: boss's own vertical edges only if they already exist —
#: ``test_edge_predicate_reaches_*``), draft x fillet
#: (``test_draft_tilts_two_of_the_four_vertical_edges_out_of_the_predicate``).
COMMUTING_PAIRS = [
    ("extrude_cut", "hole_simple"),
    ("hole_simple", "hole_counterbore"),
    ("hole_simple", "hole_countersink"),
    ("hole_simple", "fillet"),
    ("hole_simple", "chamfer"),
    ("hole_simple", "draft"),
    ("extrude_add", "extrude_cut"),
    ("extrude_cut", "hole_counterbore"),
    ("hole_counterbore", "hole_simple"),
]


@pytest.mark.parametrize(("first", "second"), COMMUTING_PAIRS, ids=lambda p: str(p))
def test_order_independent_pairs(first: str, second: str) -> None:
    """Two features on disjoint material commute: identical mass properties and
    identical topology counts in either order.

    Order-dependence here would mean a feature is reading state it should not
    (a stale tool, a resolved face from the wrong body).
    """
    a, b = VERBS[first], VERBS[second]
    tol = tol_for(a, b)
    forward = properties(evaluate(PLATE + a.features + b.features), f"{first}+{second}")
    backward = properties(
        evaluate(PLATE + b.features + a.features), f"{second}+{first}"
    )

    assert forward.volume == pytest.approx(backward.volume, abs=tol)
    assert forward.surface_area == pytest.approx(backward.surface_area, abs=tol)
    assert forward.centroid.x == pytest.approx(backward.centroid.x, abs=tol)
    assert forward.centroid.y == pytest.approx(backward.centroid.y, abs=tol)
    assert forward.centroid.z == pytest.approx(backward.centroid.z, abs=tol)
    assert forward.topology == backward.topology


# --- SELF-composition: the matrix diagonal, with re-issued ids -------------------
#
# The diagonal is skipped in the matrix because two features cannot share an id
# (see ``DIAGONAL_SKIP_REASON``); these cases apply each verb TWICE at the same
# placement with the second instance's ids shifted by :func:`reid`, which is what
# an "I did that again" user action really looks like.

#: verb -> the typed error the second application must produce.
SELF_COMPOSITION_ERRORS = {
    # The DIAGONAL that used to be finding CM-3's shape: a duplicated cut
    # reported `ok` and returned the input body (14400.0 both times). Since the
    # 2026-07-25 fix it degrades exactly as the Hole always has.
    "extrude_cut": "cut_removed_nothing",
    "hole_simple": "hole_off_body",
    "hole_counterbore": "hole_off_body",
    "hole_countersink": "hole_off_body",
    "fillet": "fillet_failed",
    "chamfer": "chamfer_failed",
    "shell": "shell_failed",
    "draft": "subshape_unresolved",
}

#: verb -> reason the second application is a legitimate IDENTITY.
SELF_COMPOSITION_IDENTITIES = {
    "extrude_add": "Unioning the identical boss again adds no material.",
    "mirror_clearing": (
        "After mirroring about x=0 the body is symmetric about x=0, so the second "
        "reflection coincides with it."
    ),
    "mirror_midplane": (
        "The plate is already symmetric about x=40, so both mirrors are the identity."
    ),
    "pattern_circular": (
        "A 3-up 120-degree ring about the plate centre leaves a body with exact "
        "3-fold rotational symmetry about that axis, so a SECOND identical ring "
        "maps it onto itself. (Measured 81148.74831559186 mm^3 both times, 26 "
        "faces / 72 edges / 1 shell -- correct, and the reason the matrix's "
        "'a pattern must change the body' rule is applied off the DIAGONAL only.)"
    ),
}

#: verb -> reason the second application legitimately CHANGES the body further.
SELF_COMPOSITION_PROGRESSES = {
    "pattern_linear": "A second +Y row extends the body again.",
}


@pytest.mark.parametrize("name", sorted(SELF_COMPOSITION_ERRORS), ids=str)
def test_self_composition_errors_honestly(name: str) -> None:
    """Applying a verb TWICE at the same placement degrades to ONE typed error
    (never a raise, never a silently unchanged body reported as ok).

    ``hole_*`` is the flagship: the second drill finds no material and answers
    ``hole_off_body`` — the "a feature that removes nothing must raise" rule,
    which ``extrude_cut`` now satisfies too (``cut_removed_nothing``, CM-3 fixed
    2026-07-25; it used to report every feature ``ok`` and return the input body).
    """
    verb = VERBS[name]
    first = evaluate(PLATE + verb.features)
    again = evaluate(PLATE + verb.features + reid(verb.features, 500))
    assert error_codes(again) == [SELF_COMPOSITION_ERRORS[name]], error_codes(again)
    assert fingerprint(again) == fingerprint(first), (
        f"{name} x {name}: the failed second application did not leave the "
        "first's body untouched (strict prefix, feature-tree design 4.3)"
    )


@pytest.mark.parametrize("name", sorted(SELF_COMPOSITION_IDENTITIES), ids=str)
def test_self_composition_identities_are_exact(name: str) -> None:
    """The self-compositions that are legitimately the IDENTITY reproduce the
    first application's SOLID: topology counts exactly, every mass property
    within the documented tolerance (see :func:`assert_same_solid`)."""
    verb = VERBS[name]
    first = evaluate([*PLATE, *verb.features])
    again = evaluate([*PLATE, *verb.features, *reid(verb.features, 500)])
    assert statuses(again)[-1] == "ok", error_codes(again)
    assert_same_solid(
        again,
        first,
        tol_for(verb),
        f"{name} x {name} should be the identity: {SELF_COMPOSITION_IDENTITIES[name]}",
    )


@pytest.mark.parametrize("name", sorted(SELF_COMPOSITION_PROGRESSES), ids=str)
def test_self_composition_progresses(name: str) -> None:
    """The self-compositions that must go FURTHER (a second pattern really adds
    instances) change the body and grow it."""
    verb = VERBS[name]
    before = properties(evaluate(PLATE + verb.features), name)
    props = properties(
        evaluate(PLATE + verb.features + reid(verb.features, 500)), f"{name} x {name}"
    )
    assert props.volume > before.volume + tol_for(verb), (
        f"{name} x {name} should progress: {SELF_COMPOSITION_PROGRESSES[name]}"
    )


def test_self_composition_taxonomy_is_exhaustive() -> None:
    """EVERY verb is classified as error / identity / progress under
    self-composition — no unclassified diagonal left.

    ``extrude_cut`` was the one exemption while finding CM-3 was live (a
    duplicated cut removed nothing yet reported ok); with the fix it joins the
    error class, so the exemption is gone and a new verb cannot be quietly left
    unclassified.
    """
    classified = (
        set(SELF_COMPOSITION_ERRORS)
        | set(SELF_COMPOSITION_IDENTITIES)
        | set(SELF_COMPOSITION_PROGRESSES)
    )
    assert set(VERBS) - classified == set()


# =================================================================================
# SECTION E — determinism, suppress round-trip, edit-and-revert over compositions
# =================================================================================

#: Representative composed chains, each exercising a different seam, used by the
#: determinism / suppress / edit-revert legs. The (features, last-feature-id,
#: edit-path, edited-value) tuple lets one parametrization drive all three.
CompositionChain = tuple[str, list[dict[str, Any]], uuid.UUID]


def _chains() -> list[CompositionChain]:
    return [
        (
            "hole+pattern",
            PLATE + VERBS["hole_simple"].features + VERBS["pattern_linear"].features,
            F_PATTERN_L,
        ),
        (
            "hole+mirror_mid",
            PLATE + VERBS["hole_simple"].features + VERBS["mirror_midplane"].features,
            F_MIRROR,
        ),
        (
            "pocket+mirror_clear",
            PLATE + VERBS["extrude_cut"].features + VERBS["mirror_clearing"].features,
            F_MIRROR,
        ),
        (
            "cbore+fillet",
            PLATE + VERBS["hole_counterbore"].features + VERBS["fillet"].features,
            F_FILLET,
        ),
        (
            "csink+chamfer",
            PLATE + VERBS["hole_countersink"].features + VERBS["chamfer"].features,
            F_CHAMFER,
        ),
        (
            "pocket+shell",
            PLATE + VERBS["extrude_cut"].features + VERBS["shell"].features,
            F_SHELL,
        ),
        (
            "boss+draft",
            PLATE + VERBS["extrude_add"].features + VERBS["draft"].features,
            F_DRAFT,
        ),
        (
            "hole+circular",
            PLATE + VERBS["hole_simple"].features + VERBS["pattern_circular"].features,
            F_PATTERN_C,
        ),
    ]


CHAINS = _chains()
each_chain = pytest.mark.parametrize(
    ("features", "last_id"),
    [(features, last_id) for _name, features, last_id in CHAINS],
    ids=[name for name, _f, _l in CHAINS],
)


@each_chain
def test_composed_rebuild_is_deterministic(
    features: list[dict[str, Any]], last_id: uuid.UUID
) -> None:
    """Gate 3 over COMPOSITIONS: rebuilding the same composed tree three times
    yields the byte-identical GLB and identical mass-property reprs.

    The goldens cover determinism for single verbs; a composed tree adds the
    boolean/tool-reconstruction paths, whose OCCT traversal order is exactly
    where non-determinism would hide.
    """
    del last_id
    prints = {fingerprint(evaluate(features)) for _ in range(3)}
    assert len(prints) == 1, f"composed rebuild is not deterministic: {prints}"


@each_chain
def test_suppress_then_unsuppress_returns_the_identical_shape(
    features: list[dict[str, Any]], last_id: uuid.UUID
) -> None:
    """``suppress(F)`` then ``unsuppress(F)`` is the identity, and ``suppress(F)``
    equals DELETING F — byte-identically, for every composed chain.

    The composition angle: suppressing the final feature must leave the
    preceding body exactly as it was, and un-suppressing must re-derive the
    composed body from scratch rather than from a stale cache.
    """
    plain = fingerprint(evaluate(features))
    suppressed = evaluate(suppress(features, last_id))
    deleted = evaluate(without(features, last_id))

    assert [r.status for r in suppressed.result.features if r.status == "suppressed"], (
        "the target feature was not reported suppressed"
    )
    assert fingerprint(suppressed) == fingerprint(deleted), (
        "a suppressed feature is not equivalent to a deleted one"
    )
    assert fingerprint(suppressed) != plain, (
        "suppressing the last feature changed nothing"
    )
    assert fingerprint(evaluate(features)) == plain, "un-suppressing did not restore"


#: (chain name, the JSON path to a numeric param, the perturbed value). Every
#: edit is a real user edit of the COMPOSED feature or its predecessor.
EDIT_CASES: list[tuple[str, list[dict[str, Any]], list[str | int], float]] = [
    (
        "pattern spacing",
        PLATE + VERBS["hole_simple"].features + VERBS["pattern_linear"].features,
        ["params", "pattern", "spacing_mm"],
        18.0,
    ),
    (
        "hole diameter under a pattern",
        PLATE + VERBS["hole_simple"].features + VERBS["pattern_linear"].features,
        ["params", "diameter_mm"],
        6.0,
    ),
    (
        "counterbore depth under a fillet",
        PLATE + VERBS["hole_counterbore"].features + VERBS["fillet"].features,
        ["params", "type", "cbore_depth_mm"],
        2.0,
    ),
    (
        "fillet radius over a counterbore",
        PLATE + VERBS["hole_counterbore"].features + VERBS["fillet"].features,
        ["params", "radius_mm"],
        3.0,
    ),
    (
        "shell thickness over a pocket",
        PLATE + VERBS["extrude_cut"].features + VERBS["shell"].features,
        ["params", "thickness_mm"],
        1.5,
    ),
    (
        "draft angle over a boss",
        PLATE + VERBS["extrude_add"].features + VERBS["draft"].features,
        ["params", "angle_deg"],
        8.0,
    ),
    (
        "circular pattern count over a hole",
        PLATE + VERBS["hole_simple"].features + VERBS["pattern_circular"].features,
        ["params", "pattern", "count"],
        4,
    ),
]


def _edited(
    features: list[dict[str, Any]], path: list[str | int], value: float
) -> list[dict[str, Any]]:
    """A deep copy of *features* with the LAST feature holding *path* re-valued.

    Walks the envelope's params by the given key path; the target is the last
    feature that actually carries it, so an edit is unambiguous even when two
    features share a key name.
    """
    out = copy.deepcopy(features)
    for entry in reversed(out):
        node: Any = entry["feature"]
        try:
            for key in path[:-1]:
                node = node[key]
            if path[-1] in node:
                node[path[-1]] = value
                return out
        except (KeyError, TypeError):
            continue
    raise AssertionError(f"no feature carries the param path {path}")


@pytest.mark.parametrize(
    ("features", "path", "value"),
    [(f, p, v) for _n, f, p, v in EDIT_CASES],
    ids=[name for name, _f, _p, _v in EDIT_CASES],
)
def test_parameter_edit_and_revert_round_trips(
    features: list[dict[str, Any]], path: list[str | int], value: float
) -> None:
    """The parameter-edit-and-rebuild pass over each composed chain: edit a
    numeric param, then revert it, and the body must be BYTE-identical to the
    original — while the edited intermediate must genuinely differ.

    Both halves matter. "Differs" proves the edit actually reached the composed
    feature (a param the composition ignored would silently pass); "identical"
    proves the rebuild is a pure function of the tree, with no drift accumulated
    through the tool reconstruction / face re-resolution the composition needs.
    """
    original = fingerprint(evaluate(features))
    edited = fingerprint(evaluate(_edited(features, path, value)))
    assert edited != original, f"editing {path} changed nothing in the composed body"
    assert fingerprint(evaluate(features)) == original, (
        f"reverting {path} did not restore"
    )


# =================================================================================
# SECTION F — STEP round-trip fidelity of COMPOSED bodies (gate 2)
# =================================================================================

#: Composed bodies whose B-rep must survive STEP unchanged. The golden
#: round-trip gate covers single-verb models; these are the boolean-heavy
#: compositions, which is where an export/import defect would actually land.
ROUNDTRIP_CHAINS = [
    (
        "hole+pattern",
        PLATE + VERBS["hole_simple"].features + VERBS["pattern_linear"].features,
    ),
    (
        "hole+mirror_clearing",
        PLATE + VERBS["hole_simple"].features + VERBS["mirror_clearing"].features,
    ),
    (
        "cbore+csink",
        PLATE + VERBS["hole_counterbore"].features + VERBS["hole_countersink"].features,
    ),
    ("pocket+fillet", PLATE + VERBS["extrude_cut"].features + VERBS["fillet"].features),
    ("pocket+shell", PLATE + VERBS["extrude_cut"].features + VERBS["shell"].features),
    ("hole+shell", PLATE + VERBS["hole_simple"].features + VERBS["shell"].features),
    ("boss+chamfer", PLATE + VERBS["extrude_add"].features + VERBS["chamfer"].features),
    (
        "hole+circular_pattern",
        PLATE + VERBS["hole_simple"].features + VERBS["pattern_circular"].features,
    ),
]


def _roundtrip(
    features: list[dict[str, Any]], name: str
) -> tuple[ShapeProperties, ShapeProperties]:
    """Build, export to STEP, re-import, re-measure. Returns (original, reimported)."""
    evaluation = evaluate(features)
    properties(evaluation, name)
    shape = evaluation.body
    assert shape is not None
    original = measure_shape(shape)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.step"
        assert export_step(shape, path), f"{name}: STEP export failed"
        reimported_shape = import_step(path)
        solids = list(reimported_shape.solids())
        assert solids, f"{name}: re-imported STEP carries no solid"
        reimported = measure_shape(solids[0] if len(solids) == 1 else reimported_shape)
    return original, reimported


@pytest.mark.parametrize(
    ("name", "features"), ROUNDTRIP_CHAINS, ids=[n for n, _f in ROUNDTRIP_CHAINS]
)
def test_composed_body_survives_a_step_roundtrip(
    name: str, features: list[dict[str, Any]]
) -> None:
    """Gate 2 over compositions: mass properties within ``ROUNDTRIP_TOL`` and
    topology counts EXACTLY, model -> STEP -> re-import.

    A deviation is a defect to root-cause to export, import, or the kernel —
    never tolerance noise (geometry-gates rules).
    """
    original, reimported = _roundtrip(features, name)
    for field, got, want in (
        ("volume", reimported.volume, original.volume),
        ("surface_area", reimported.surface_area, original.surface_area),
        ("centroid.x", reimported.centroid.x, original.centroid.x),
        ("centroid.y", reimported.centroid.y, original.centroid.y),
        ("centroid.z", reimported.centroid.z, original.centroid.z),
        ("bbox.min.x", reimported.bounding_box.min.x, original.bounding_box.min.x),
        ("bbox.max.x", reimported.bounding_box.max.x, original.bounding_box.max.x),
        ("bbox.max.z", reimported.bounding_box.max.z, original.bounding_box.max.z),
    ):
        assert got == pytest.approx(want, abs=ROUNDTRIP_TOL), (
            f"{name}: round-trip {field} drifted — exported {want!r}, "
            f"re-imported {got!r} (tol {ROUNDTRIP_TOL!r})"
        )
    assert reimported.topology == original.topology, (
        f"{name}: topology changed across the STEP round-trip — exported "
        f"{original.topology.model_dump()}, re-imported "
        f"{reimported.topology.model_dump()}"
    )


# =================================================================================
# SECTION G — LIVE DEFECTS this matrix found (assertions REAL, xfail(strict))
# =================================================================================
#
# Each case below is a composition the matrix caught on HEAD 446a872. The
# assertions are the correct ones, unweakened; `xfail(strict=True)` records that
# the kernel does not satisfy them YET, so the suite is honest today and turns
# RED the moment the fix lands (forcing the marker's removal). Filed in
# docs/GEOMETRY-QA.md 2026-07-25 as CM-1 .. CM-4.


@pytest.mark.xfail(
    strict=True,
    reason="CM-1 (P0, LIVE on 446a872): a mirror re-ERASES a cut whenever any "
    "non-cut feature sits between the cut and the mirror. `_prev_cut_tools` "
    "reads only `state.prev_body_feature`, so an intervening chamfer/fillet/"
    "boss makes it return None and `_evaluate_mirror` takes `mirror_union`, "
    "whose reflection FILLS the seed void — the FINDINGS #2 featureless-brick "
    "symptom, reachable again. Measured: 31640.0 obtained vs 29629.3807 "
    "expected (chamfer); 31845.4867 vs 29834.8674 (fillet); 32640.0 vs "
    "30629.3807 (boss). Fix = walk back past non-cut features (or track cut "
    "tools per feature) instead of only the immediate predecessor.",
)
@pytest.mark.parametrize(
    ("label", "between", "between_delta"),
    [
        # A CHAMFER of the four vertical corners: 4 * (d^2/2) per unit height.
        ("chamfer", [chamfer(F_CHAMFER, 3.0)], -(4.0 * 20.0 * (3.0**2 / 2.0))),
        # A FILLET of the same four corners: 4 * (r^2 - pi r^2 / 4) per height.
        (
            "fillet",
            [fillet(F_FILLET, 3.0)],
            -(20.0 * 4.0 * (3.0**2 - math.pi * 3.0**2 / 4.0)),
        ),
        # An ADD (a boss) — not a modifier at all, proving the shadowing is about
        # "the predecessor is not a cut", not about modifiers specifically. The
        # boss is 8x8x5 = 320 on a datum at z=20; it sits at x in [30,38], so the
        # mirror about x=20 also reflects it to x in [2,10] -> +2 * 320.
        (
            "boss",
            [
                datum_offset(D_BOSS, "XY", 20.0),
                rect_sketch(
                    S_BOSS,
                    30.0,
                    30.0,
                    38.0,
                    38.0,
                    {"kind": "feature", "feature_id": str(D_BOSS)},
                ),
                extrude(F_BOSS, S_BOSS, 5.0),
            ],
            2.0 * (8.0 * 8.0 * 5.0),
        ),
    ],
)
def test_cm1_mirror_keeps_the_hole_across_an_intervening_feature(
    label: str, between: list[dict[str, Any]], between_delta: float
) -> None:
    """CM-1 — the FINDINGS #2 fixture with ONE unrelated feature inserted.

    Chain: 40x40 plate extruded 20 -> HOLE Ø8 at (10,20) -> <feature> ->
    datum YZ@20 -> MIRROR. The inserted feature is 20+ mm from the bore, so the
    correct answer is the seed-2 answer plus that feature's own (mirror-aware)
    delta: the bore at x=10 must STILL reflect to x=30.

    Obtained on HEAD: the bore is COMPLETELY FILLED — the volume equals the
    modified plate with no hole at all, and the topology carries NO cylindrical
    face — i.e. exactly the P0 symptom `feb4318` fixed for the
    cut-immediately-before-mirror case.
    """
    del label
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 20.0)]
    top = face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 20.0), 1600.0)
    props = properties(
        evaluate(
            [
                *plate,
                hole(F_HOLE, top, (10.0, 20.0, 20.0), 8.0),
                *between,
                datum_offset(D_MID, "YZ", 20.0),
                mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_MID)}),
            ]
        ),
        "cm1",
    )
    expected = 32000.0 + between_delta - 2 * math.pi * 4.0**2 * 20.0
    assert props.volume == pytest.approx(expected, abs=CURVED_TOL)


@pytest.mark.parametrize(
    ("label", "cut", "cut_delta"),
    [
        (
            "pocket",
            [
                rect_sketch(S_POCKET, 4.0, 10.0, 12.0, 30.0),
                extrude(F_POCKET, S_POCKET, 10.0, operation="cut"),
            ],
            -(8.0 * 20.0 * 10.0),
        ),
        (
            "hole",
            [
                hole(
                    F_HOLE,
                    face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 10.0), 1600.0),
                    (20.0, 20.0, 10.0),
                    8.0,
                )
            ],
            -(math.pi * 4.0**2 * 10.0),
        ),
    ],
)
def test_cm2_pattern_of_a_clearing_translation_is_not_a_silent_no_op(
    label: str, cut: list[dict[str, Any]], cut_delta: float
) -> None:
    """CM-2 — the seed-3 (clearing-plane) shape, expressed as a PATTERN.

    Chain: 40x40x10 plate -> <cut> -> LINEAR PATTERN +X, spacing 40, count 2.
    The plate is 40 wide, so the replicated cut tool lands entirely beyond the
    body's +X face and can remove nothing. `mirror` answers this by falling back
    to a whole-body replicate (giving the completed 80 mm part, a copy of the cut
    in each half); `pattern` silently returned the input body.

    FIXED 2026-07-25 (kernel): `linear_pattern_cut` / `circular_pattern_cut` now
    ask the SHARED `removal_reaches_body` predicate `mirror_cut` already used, and
    take the whole-body ADD path when NO replicated tool can reach the body.
    Pre-fix: pocket source 14400.0 (unchanged, every feature `ok`) vs 28800.0
    expected; hole source 15497.34517542563 vs 30994.690350851266.
    """
    del label
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 10.0)]
    single = 16000.0 + cut_delta
    props = properties(
        evaluate(plate + cut + [linear_pattern(F_PATTERN_L, (1.0, 0.0, 0.0), 40.0, 2)]),
        "cm2",
    )
    assert props.volume == pytest.approx(2.0 * single, abs=CURVED_TOL)


@pytest.mark.parametrize(
    ("label", "features"),
    [
        (
            "beside the body",
            [
                rect_sketch(S_POCKET, 100.0, 100.0, 110.0, 110.0),
                extrude(F_POCKET, S_POCKET, 10.0, operation="cut"),
            ],
        ),
        (
            "above the body",
            [
                datum_offset(D_BOSS, "XY", 20.0),
                rect_sketch(
                    S_POCKET,
                    10.0,
                    10.0,
                    20.0,
                    20.0,
                    {"kind": "feature", "feature_id": str(D_BOSS)},
                ),
                extrude(F_POCKET, S_POCKET, 5.0, operation="cut"),
            ],
        ),
        (
            "the same pocket cut twice",
            [
                rect_sketch(S_POCKET, 4.0, 10.0, 12.0, 30.0),
                extrude(F_POCKET, S_POCKET, 10.0, operation="cut"),
                rect_sketch(_fid(91), 4.0, 10.0, 12.0, 30.0),
                extrude(_fid(92), _fid(91), 10.0, operation="cut"),
            ],
        ),
        (
            "a revolve-cut clear of the body",
            [
                revolve_profile_sketch(
                    _fid(93),
                    {"kind": "datum_plane", "plane": "XZ"},
                    [(100.0, 0.0), (110.0, 0.0), (110.0, 5.0), (100.0, 5.0)],
                    ((0.0, 0.0), (0.0, 5.0)),
                ),
                revolve(_fid(94), _fid(93), operation="cut"),
            ],
        ),
    ],
)
def test_cm3_a_cut_that_removes_nothing_must_error(
    label: str, features: list[dict[str, Any]]
) -> None:
    """CM-3 — "a feature that removes nothing must raise, never silently return
    the input", applied to extrude-cut and revolve-cut.

    This is also the matrix's ``extrude_cut`` DIAGONAL (see
    ``test_self_composition_taxonomy_is_exhaustive``): "cut it again" used to be
    the one self-composition that was neither an honest error nor a declared
    identity, because the kernel reported it as a successful no-op.

    FIXED 2026-07-25 (kernel): ``combine_body`` asks the SHARED
    ``removal_reaches_body`` predicate BEFORE the boolean — "removed nothing" is
    invisible afterwards — and raises ``CutRemovedNothingError``, which the feature
    layer surfaces as the typed ``cut_removed_nothing`` (the Hole's
    ``hole_off_body`` for every other subtractive verb). Pre-fix all four chains
    returned the input body (16000.0 / 14400.0) with every feature ``ok``.
    """
    del label
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 10.0)]
    evaluation = evaluate([*plate, *features])
    assert error_codes(evaluation), (
        "a cut that removed nothing reported every feature ok and returned the "
        f"input body ({evaluation.result.properties})"
    )


@pytest.mark.xfail(
    strict=True,
    reason="CM-4 (P2, LIVE on 446a872): the pocket+fillet+shell TRIPLE gains 2 "
    "straight edges across a STEP round-trip (faces 36 = 36, edges 96 -> 98, "
    "LINE edges 64 -> 66; volume delta 8.3e-11, so the GEOMETRY is preserved). "
    "Isolated to the triple: every pair (fillet+shell, pocket+fillet, "
    "pocket+shell, hole+shell, chamfer+shell) round-trips with EXACT topology. "
    "Diagnosis: two straight edges are re-read as collinear pairs on import "
    "(an extra vertex), i.e. an export/import seam, not a kernel modelling bug. "
    "It matters because edge SIGNATURES (picked fillet/chamfer edges) and the "
    "drawings edge pipeline key off edge identity after an import round-trip.",
)
def test_cm4_pocket_fillet_shell_survives_a_step_roundtrip() -> None:
    """CM-4 — gate 2 on the one composition that fails it.

    Its own fixture, deliberately NOT the shared 80 mm plate: the drift is
    geometry-specific (a 40x40x10 plate, a [4,12]x[10,30] through-pocket, an r3
    corner fillet and a 2 mm open-top shell). On the 80 mm layout the same triple
    round-trips with exact topology, which is why the finding is filed as a
    fixture-specific export/import seam rather than "shell round-trips wrongly".
    """
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 10.0)]
    top = face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 10.0), 1600.0)
    original, reimported = _roundtrip(
        [
            *plate,
            rect_sketch(S_POCKET, 4.0, 10.0, 12.0, 30.0),
            extrude(F_POCKET, S_POCKET, 10.0, operation="cut"),
            fillet(F_FILLET, 3.0),
            shell(F_SHELL, 2.0, [top]),
        ],
        "pocket_fillet_shell",
    )
    assert reimported.volume == pytest.approx(original.volume, abs=ROUNDTRIP_TOL)
    assert reimported.topology == original.topology


# --- Documented v1 limits, LOCKED with their measured values ---------------------
#
# Not defects: deliberate v1 semantics whose numbers must not drift silently.
# Recording them here means a future change to the rule is a visible, reviewed
# test change rather than a quiet behavioural shift.


def test_documented_limit_mirror_reflects_only_the_last_cut() -> None:
    """v1 LIMIT (documented, `fa30220` / GEOMETRY-QA 2026-07-13): a mirror
    reflects only the IMMEDIATELY-preceding cut's tools, so with TWO holes the
    result has THREE bores, not four.

    Chain: 40x40x20 plate -> HOLE A Ø8 at (10,10) -> HOLE B Ø8 at (10,30) ->
    datum YZ@20 -> MIRROR. A stays put, B reflects to (30,30):
    V = 32000 - 3*pi*4^2*20 = 28984.071 mm^3 (four bores would be 27978.761).
    The alternative — union-then-recut — would WELD A shut (seed #4), so this is
    the deliberate lesser evil, not an oversight.
    """
    plate = [rect_sketch(S_BASE, 0.0, 0.0, 40.0, 40.0), extrude(F_BASE, S_BASE, 20.0)]
    pristine = face_ref(F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 20.0), 1600.0)
    after_a = face_ref(
        F_BASE, (0.0, 0.0, 1.0), (20.0, 20.0, 20.0), 1600.0 - math.pi * 16.0
    )
    props = properties(
        evaluate(
            [
                *plate,
                hole(_fid(81), pristine, (10.0, 10.0, 20.0), 8.0),
                hole(_fid(82), after_a, (10.0, 30.0, 20.0), 8.0),
                datum_offset(D_MID, "YZ", 20.0),
                mirror(F_MIRROR, {"kind": "feature", "feature_id": str(D_MID)}),
            ]
        ),
        "documented: mirror reflects the last cut only",
    )
    assert props.volume == pytest.approx(
        32000.0 - 3 * math.pi * 4.0**2 * 20.0, abs=CURVED_TOL
    )


def test_documented_limit_intervening_feature_shadows_a_pattern_cut_source() -> None:
    """v1 LIMIT (documented, GEOMETRY-QA 2026-07-13): "a cut shadowed by an
    intervening body-affecting feature falls back to the whole-body union path".

    Chain: 80x80x10 plate -> POCKET -> CHAMFER -> LINEAR PATTERN +Y/20/2. The
    chamfer shadows the pocket, so the pattern replicates the WHOLE body: the
    copy at y in [20,100] overlaps the seed, the union spans y in [0,100], and
    the volume EXCEEDS the pocketed body instead of removing a second pocket.
    Locked so that generalising the inference (the documented forward scope item)
    becomes a visible, reviewed test change.

    NB: for `mirror` the same shadowing is NOT benign — it FILLS the cut. That
    asymmetry is finding CM-1 above.
    """
    pocketed = properties(evaluate(PLATE + VERBS["extrude_cut"].features), "pocketed")
    props = properties(
        evaluate(
            PLATE
            + VERBS["extrude_cut"].features
            + VERBS["chamfer"].features
            + VERBS["pattern_linear"].features
        ),
        "documented: intervening chamfer shadows the pattern's cut source",
    )
    assert props.volume > pocketed.volume
    assert props.bounding_box.min.y == pytest.approx(0.0, abs=PLANAR_TOL)
    assert props.bounding_box.max.y == pytest.approx(
        PLATE_SIDE + PATTERN_STEP, abs=PLANAR_TOL
    )


def test_observed_limit_a_crossing_mirror_erases_an_asymmetric_modifier() -> None:
    """OBSERVATION (CM-1's unfixable half — design limit, NOT a filed defect).

    A mirror about a plane the body CROSSES reflects-and-unions, so it fills in
    ANY asymmetric material removal — including one made by a MODIFIER, which
    leaves no reflectable "tool" behind at all.

    Chain: 80x80x10 plate -> DRAFT 5 deg on the +X wall -> datum YZ@40 ->
    MIRROR. The drafted wedge sits only on the +X side, so the reflection fills
    it and the result is the FULL 64000 mm^3 box with 6 faces: the draft is
    silently erased. Unlike CM-1 (a cut, whose tools exist and could be
    reflected) there is nothing for a cut-aware mirror to reflect here, so this
    is inherent to the v1 reflect-and-union design.

    Locked with its measured value so that a future mirror redesign has to
    change this test deliberately, and so the asymmetry with CM-1 stays visible.
    """
    drafted = properties(evaluate([*PLATE, *VERBS["draft"].features]), "drafted")
    props = properties(
        evaluate(
            [*PLATE, *VERBS["draft"].features, *VERBS["mirror_midplane"].features]
        ),
        "draft then crossing mirror",
    )
    assert drafted.volume == pytest.approx(PLATE_VOLUME + DRAFT_DV, abs=PLANAR_TOL)
    assert props.volume == pytest.approx(PLATE_VOLUME, abs=PLANAR_TOL)
    assert props.topology.model_dump() == {"faces": 6, "edges": 12, "shells": 1}


def test_observed_limit_draft_propagates_along_a_tangent_chain() -> None:
    """OBSERVATION (P3 doc/UX, NOT a geometry defect) — a draft applied to ONE
    picked face tapers EVERY face in its tangent-continuous chain.

    Chain: 80x80x10 plate -> FILLET r4 on the four vertical corners -> DRAFT
    5 deg naming ONLY the +X face. The r4 fillets make all four side walls
    tangent-continuous, and OCCT's ``BRepOffsetAPI_DraftAngle`` propagates along
    that chain, so all FOUR walls come back tapered (each planar side face's
    normal gains a +Z component of sin 5 deg = 0.0872) and the four fillet
    cylinders become cones.

    Measured removal 1361.7627 mm^3 against 314.9581 mm^3 for the named face
    alone (80 -> 72 mm wall after the fillet: 72 * 0.5 * 10^2 * tan5). It is
    OCCT-correct and usually what a molded part wants, but a picked-face UI does
    not say so — hence the doc/UX finding. On the UN-filleted plate (no tangent
    chain) only the named face tapers, which
    ``test_single_verb_deltas`` pins analytically.
    """
    filleted = properties(evaluate([*PLATE, *VERBS["fillet"].features]), "filleted")
    props = properties(
        evaluate([*PLATE, *VERBS["fillet"].features, *VERBS["draft"].features]),
        "fillet then draft",
    )
    wall = PLATE_SIDE - 2 * FILLET_R
    named_face_only = (
        wall * 0.5 * PLATE_THICKNESS**2 * math.tan(math.radians(DRAFT_DEG))
    )
    removed = filleted.volume - props.volume
    assert removed > 4.0 * named_face_only, (
        "the draft no longer propagates along the tangent chain — removed "
        f"{removed!r} mm^3 where the named face alone accounts for "
        f"{named_face_only!r}"
    )
    # Every planar side face now carries the pull-direction component.
    assert props.topology.faces == filleted.topology.faces
    assert props.bounding_box.max.z == pytest.approx(PLATE_THICKNESS, abs=CURVED_TOL)
