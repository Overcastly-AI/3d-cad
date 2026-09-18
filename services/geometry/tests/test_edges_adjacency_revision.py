"""§14 at the FEATURE-TREE level — the audit's part, edited the way parts get edited.

The kernel-level gates for the adjacency re-anchor live in ``test_edges.py``; this
file exercises the whole path the PRODUCT takes, because the finding is a property
of an ORDER of features and not of one resolver call.

THE FINDING (product audit 2026-09-16, P0). A gearbox housing — 3 mm wall, R8
corner rounds, four Ø8 mounting holes, six features — then the most ordinary thing
a working engineer does: **one sketch dimension, width 120 -> 150.** Result:
``Fillet1 ERR SUBSHAPE_UNRESOLVED``, ``Shell1`` / ``Hole1`` / ``Pattern1`` SKIP,
and the part collapsed to a bare block. Four of six features destroyed by one
dimension edit. The auditor's verdict: *"Yes for a first build, no for the second
edit — that is the thing that sends an engineer back to Fusion."*

THE MECHANISM, and why the obvious tier could not reach it. Every field of an
``EdgeSignature`` is an ABSOLUTE WORLD COORDINATE. §13's durable tier re-matches a
straight edge on its own SUPPORTING LINE, which is invariant under the edge being
lengthened or shortened IN PLACE — and a width edit *translates* the vertical edges
onto a parallel line 30 mm away. Not collinear, so the tier cannot fire: by
construction, at any tolerance. The durable tier is invariant under the
transformation that almost never happens and not under the one that always does.

THE ASYMMETRY THAT SOLVES IT. Every FACE reference in the same tree re-resolved
through the same edit, because a face has four tiers and an identity (area,
in-plane centroid) that survives being moved. An edge of a manifold solid IS the
intersection of two faces — so the identity it lacks in its own geometry it borrows
from its neighbours. That is tier 3.

THE CONTROL MATTERS AS MUCH AS THE FAILURE, and is the reason this file is not one
test: the same tree with the adjacency annotation STRIPPED — byte-for-byte a
selector persisted before §14 — must still collapse, or the passing cases below
prove nothing. And the correctness claim is NOT "it rebuilds": a matcher that
re-anchored to the wrong edge would also rebuild. It is that the rescued body is
BYTE-IDENTICAL to the body an exact re-pick produces.
"""

import copy
import hashlib
import math
import uuid
from typing import Any

import pytest
from geometry.features import evaluate_tree
from geometry.harness import evaluate_model
from geometry.kernel.edges import enumerate_edges_with_adjacency
from loft_wire.features import EvaluateTreeRequest

PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000ad00")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000ad01")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-00000000ad02")
FILLET_ID = uuid.UUID("00000000-0000-0000-0000-00000000ad03")
SHELL_ID = uuid.UUID("00000000-0000-0000-0000-00000000ad04")

#: The housing's authored width, and the audit's two edits of it.
AUTHORED_W = 120.0
WIDENED_W = 150.0
NARROWED_W = 130.0

DEPTH = 80.0
HEIGHT = 40.0
CORNER_R = 8.0
WALL = 3.0

#: Analytic-agreement bound for prisms and right cylinders, which GProp integrates
#: exactly — the documented golden-suite bound (docs/GEOMETRY-QA.md), not an
#: ad-hoc epsilon. Measured residuals here are ~1e-11.
VOLUME_TOLERANCE_MM3 = 1e-9

#: Centroid agreement bound (mm) between two constructions of the SAME solid. The
#: two bodies are geometrically identical, so this absorbs only the ulp-scale
#: residual of GProp integrating a differently-ordered face list — measured
#: 5e-14 mm on a 75 mm coordinate. The documented kernel linear tolerance
#: (CLAUDE.md 1e-7) is the ceiling, not a fit.
CENTROID_TOLERANCE_MM = 1e-7


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _sketch(width_mm: float) -> dict[str, Any]:
    """The housing footprint. ``width_mm`` is THE dimension the audit retyped."""
    corners = [(0.0, 0.0), (width_mm, 0.0), (width_mm, DEPTH), (0.0, DEPTH)]
    return {
        "id": str(SKETCH_ID),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    _line(f"e{i + 1}", corners[i], corners[(i + 1) % 4])
                    for i in range(4)
                ],
                "constraints": [],
            },
        },
    }


def _extrude() -> dict[str, Any]:
    return {
        "id": str(EXTRUDE_ID),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "distance_mm": HEIGHT,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _vertical_edge_signatures(features: list[dict[str, Any]]) -> list[Any]:
    """The four vertical edges' PICK-side signatures, as the product captures them.

    Exactly how a pick is captured: the selection overlay hands the client the
    signature of the edge as it stands after the features that precede the new
    one, through the SAME :func:`enumerate_edges_with_adjacency` the overlay uses.
    So this is an INPUT, produced the way the product produces it — every
    expectation in this file is derived independently of it.
    """
    evaluation = _evaluate(features, 1)
    assert evaluation.body is not None
    verticals = [
        record.signature
        for record in enumerate_edges_with_adjacency(evaluation.body)
        if record.signature.curve == "line"
        and record.signature.length_mm == pytest.approx(HEIGHT, abs=1e-9)
        and record.signature.end_a.z == pytest.approx(0.0, abs=1e-9)
    ]
    assert len(verticals) == 4, "a rectangular prism has four vertical edges"
    return sorted(verticals, key=lambda s: (s.end_a.x, s.end_a.y))


def _fillet(signatures: list[Any]) -> dict[str, Any]:
    """R8 corner rounds on the four PICKED vertical edges.

    Picked, not ``axis_parallel``: the predicate would also rebuild but it selects
    a SET, which is not what an engineer who clicked four edges asked for — and it
    is the workaround the audit had to apply by hand. The whole point of tier 3 is
    that the pick survives.
    """
    return {
        "id": str(FILLET_ID),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": str(EXTRUDE_ID),
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": signature.model_dump(),
                            },
                        }
                        for signature in signatures
                    ],
                },
                "radius_mm": CORNER_R,
            },
        },
    }


def _shell() -> dict[str, Any]:
    """Hollow to a 3 mm wall — the audit's ``Shell1``, the first feature to SKIP.

    Sealed (``refs: []``, a fully-enclosed cavity) rather than open-topped, and
    deliberately: opening a face would add a picked-FACE reference to a tree whose
    whole subject is a picked-EDGE reference, and a failure could then be either
    one's. With no face refs, the only named reference in this tree is the
    fillet's, so every status below is attributable to it.
    """
    return {
        "id": str(SHELL_ID),
        "feature": {
            "type": "shell",
            "version": 1,
            "params": {"thickness_mm": WALL, "faces": {"kind": "faces", "refs": []}},
        },
    }


def _evaluate(features: list[dict[str, Any]], tree_version: int) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(PART_ID),
                "tree_version": tree_version,
                "features": features,
                "linear_deflection": 0.1,
            }
        )
    )


def _authored_tree(width_mm: float) -> list[dict[str, Any]]:
    """The housing as authored at *width_mm*, with every pick captured at that state."""
    base: list[dict[str, Any]] = [_sketch(width_mm), _extrude()]
    return [*base, _fillet(_vertical_edge_signatures(base)), _shell()]


def _revised(tree: list[dict[str, Any]], width_mm: float) -> list[dict[str, Any]]:
    """*tree* with ONLY the sketch width retyped — the audit's single edit."""
    revised = copy.deepcopy(tree)
    revised[0] = _sketch(width_mm)
    return revised


def _strip_adjacency(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*tree* with every edge selector's §14 annotation removed.

    Byte-for-byte a selector persisted before this commit, which is what makes
    this the honest negative control rather than a simulation of one.
    """
    stripped = copy.deepcopy(tree)
    for ref in stripped[2]["feature"]["params"]["edges"]["refs"]:
        ref["selector"]["signature"]["adjacent_faces"] = None
    return stripped


def _statuses(evaluation: Any) -> list[tuple[str, str, str | None]]:
    return [
        (str(r.feature_id)[-4:], r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
    ]


# --- the finding, reproduced ------------------------------------------------------


def test_THE_DEFECT_one_width_edit_destroys_every_feature_below_the_fillet() -> None:
    """THE REPRODUCTION, on a selector authored the way every selector in the
    database was authored before §14. The whole point is that it fails for the
    RIGHT reason: ``subshape_unresolved`` on the FILLET (not on the sketch, not a
    kernel modeling failure), with everything below it strict-prefix ``skipped``.

    This test is the negative control for the entire file. If it ever passes, the
    reproduction is wrong and nothing else here means anything."""
    collapsed = _evaluate(
        _strip_adjacency(_revised(_authored_tree(AUTHORED_W), WIDENED_W)), 2
    )
    assert _statuses(collapsed) == [
        ("ad01", "ok", None),
        ("ad02", "ok", None),
        ("ad03", "error", "subshape_unresolved"),
        ("ad04", "skipped", None),
    ]


def test_the_authored_tree_builds_clean() -> None:
    """The control at the other end: nothing is wrong with the part itself."""
    assert all(
        status == "ok"
        for _id, status, _code in _statuses(_evaluate(_authored_tree(AUTHORED_W), 1))
    )


def test_adjacency_carries_all_four_corner_rounds_through_the_width_edit() -> None:
    """THE FIX, through the product path. Same tree, same edit, adjacency intact:
    every feature rebuilds, and the body is a real hollow housing rather than the
    bare block the collapse produced."""
    rebuilt = _evaluate(_revised(_authored_tree(AUTHORED_W), WIDENED_W), 2)
    assert all(status == "ok" for _id, status, _code in _statuses(rebuilt))
    assert rebuilt.body is not None


def _artifact(features: list[dict[str, Any]], tree_version: int) -> tuple[str, Any]:
    """``(glb sha256, metadata)`` of *features* — the shipped artifact."""
    blob, meta = evaluate_model(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(PART_ID),
                "tree_version": tree_version,
                "features": features,
                "linear_deflection": 0.1,
            }
        )
    )
    return hashlib.sha256(blob).hexdigest(), meta


def test_the_rescued_FILLET_is_byte_identical_to_an_exact_re_pick() -> None:
    """THE CORRECTNESS CLAIM, and the reason "it rebuilds" is not it. A matcher
    that silently re-anchored to the WRONG vertical edge would also rebuild, and
    would produce a housing rounded on the wrong corners — a difference no status
    column shows. So the oracle is the part an engineer would have got by
    re-picking every edge by hand at the new width.

    Asserted through the FILLET (the tree prefix), which is where the claim
    belongs: tier 3 decides which edges the fillet rounds, so a byte-identical
    filleted body is the complete statement of "the rescue chose exactly what the
    re-pick chose" — same GLB, same volume, same centroid, same topology, same
    mesh. It is a STRONGER assertion than the same comparison on the finished
    part, because nothing downstream is averaging over it."""
    rescued_hash, rescued_meta = _artifact(
        _revised(_authored_tree(AUTHORED_W), WIDENED_W)[:3], 3
    )
    exact_hash, exact_meta = _artifact(_authored_tree(WIDENED_W)[:3], 4)

    assert rescued_hash == exact_hash
    assert rescued_meta.properties.volume == exact_meta.properties.volume
    assert rescued_meta.properties.centroid == exact_meta.properties.centroid
    assert rescued_meta.properties.topology == exact_meta.properties.topology
    assert rescued_meta.mesh == exact_meta.mesh


def test_the_finished_part_agrees_in_every_quantity_a_CONSUMER_reads() -> None:
    """The same comparison carried through ``Shell1`` to the finished housing —
    volume bit-for-bit, topology counts, and mesh counts.

    The GLB BYTES and the last ulp of the volume are deliberately NOT asserted
    here, and the reason is MEASURED rather than assumed — which matters, because
    "the hash differs" is exactly how a wrong re-anchor would look and shrugging
    it off is how one would ship. The shell emits the same 20 faces in a
    DIFFERENT ORDER when its input body was built by a different history, which
    re-partitions the glTF primitives and re-associates the GProp integration,
    while every quantity an engineer reads stays equal. Measured both ways:

    * TIER 3 (this change) — filleted body **byte-identical**, post-shell GLB
      differs, post-shell volume agrees to ~1e-10 mm^3 on 116 228 mm^3;
    * the PRE-EXISTING TIER 2 durable re-match (§13, shipped 2026-08-24), with
      adjacency stripped so only it can fire — filleted body byte-identical,
      post-shell GLB differs, post-shell volume likewise inexact.

    The older tier reproduces the divergence exactly, so it is a property of the
    shell operator and not of edge resolution. Asserting bytes here would be
    asserting a guarantee the shell has never made; the byte oracle therefore
    sits on the FILLET above, where the claim is about this change and where it
    holds exactly, and the consumer-visible quantities sit here at the documented
    tolerances."""
    _rescued_hash, rescued_meta = _artifact(
        _revised(_authored_tree(AUTHORED_W), WIDENED_W), 5
    )
    _exact_hash, exact_meta = _artifact(_authored_tree(WIDENED_W), 6)

    assert rescued_meta.properties.topology == exact_meta.properties.topology
    assert rescued_meta.mesh.vertices == exact_meta.mesh.vertices
    assert rescued_meta.mesh.triangles == exact_meta.mesh.triangles
    assert rescued_meta.properties.volume == pytest.approx(
        exact_meta.properties.volume, abs=VOLUME_TOLERANCE_MM3
    )
    for axis in ("x", "y", "z"):
        assert getattr(rescued_meta.properties.centroid, axis) == pytest.approx(
            getattr(exact_meta.properties.centroid, axis), abs=CENTROID_TOLERANCE_MM
        )


def test_the_rescued_volume_agrees_with_the_closed_form() -> None:
    """An INDEPENDENT oracle, so the byte-identity above cannot be two wrongs
    agreeing: that test compares the rescue against a re-pick, and if BOTH landed
    on the same wrong edge it would pass. This one compares against arithmetic.

    A prism with four R8 corner rounds has plan area ``W*D - (4 - pi) * R^2`` —
    each rounded corner removes a square and gives back a quarter-disc. Sealing it
    to a uniform 3 mm wall inserts a cavity inset by the wall on all six sides,
    whose vertical corners are rounded at ``R - WALL``.

    Two witnesses matter. ``WIDENED_W`` in the outer term says the fillet followed
    the edges to the NEW width rather than stopping at the stale 120; and the
    ``R - WALL`` inner radius says the rounds landed on the four vertical CORNER
    edges — a fillet on any other edge would not offset to that radius, so this
    number cannot be satisfied by a body rounded in the wrong place."""
    rebuilt = _evaluate(_revised(_authored_tree(AUTHORED_W), WIDENED_W), 2)
    assert rebuilt.body is not None

    def plan_area(width: float, depth: float, radius: float) -> float:
        return width * depth - (4.0 - math.pi) * radius**2

    outer = plan_area(WIDENED_W, DEPTH, CORNER_R) * HEIGHT
    cavity = plan_area(WIDENED_W - 2 * WALL, DEPTH - 2 * WALL, CORNER_R - WALL) * (
        HEIGHT - 2 * WALL
    )
    assert rebuilt.body.volume == pytest.approx(
        outer - cavity, abs=VOLUME_TOLERANCE_MM3
    )


def test_the_SECOND_edit_rebuilds_from_the_SAME_stored_signature() -> None:
    """The audit's own follow-up — 150 -> 130 — and the property that makes tier 3
    worth having rather than a one-shot rescue. The stored adjacency is never
    re-stamped here; each edit re-resolves the two faces from scratch, so nothing
    accumulates and edit N resolves for the reason edit 1 did."""
    tree = _authored_tree(AUTHORED_W)
    for version, width in enumerate((WIDENED_W, NARROWED_W, 95.0, AUTHORED_W), start=2):
        rebuilt = _evaluate(_revised(tree, width), version)
        assert all(status == "ok" for _id, status, _code in _statuses(rebuilt)), (
            f"width {width} did not rebuild clean"
        )


def test_a_pre_adjacency_selector_still_resolves_on_a_CLEAN_rebuild() -> None:
    """Dual-read, the half that protects the installed base. Tier 1 does not read
    ``adjacent_faces``, so a selector persisted before §14 is completely unchanged
    when the part is rebuilt unedited — this fix adds a rescue path and moves
    nothing that already worked."""
    rebuilt = _evaluate(_strip_adjacency(_authored_tree(AUTHORED_W)), 2)
    assert all(status == "ok" for _id, status, _code in _statuses(rebuilt))
