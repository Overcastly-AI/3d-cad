"""MB-0 multi-body plumbing — the two correctness rules the plumbing must hold
(docs/design/multi-body.md §MB-0, Decisions 1-2 + §Risks).

The golden ``multibody-two-disjoint-boxes`` locks the analytic roll-up +
Compound tessellation/export + determinism; this module gates the two BEHAVIOURS
that are not a single analytic number and that §Risks flags as the ways
multi-body silently goes wrong:

1. **Body-scoped resolution (Decision 1, the load-bearing correctness rule).**
   A modifying feature's topological naming resolves against the ACTIVE body
   ONLY, never a union of all bodies. Two bodies with a CONGRUENT (coincident)
   edge would tie a false ``subshape_ambiguous`` if resolution ran over the union
   — so a picked-edge fillet on the active body must resolve to exactly one edge
   and succeed.

2. **The assembly-mate ripple (§Risks — "miss it and mate resolution breaks
   silently").** ``TreeEvaluation.body`` widened ``Solid`` → ``BodyShape``
   (``Solid | Compound``), which flows into the assembly mate resolvers. They
   must still resolve a face/edge on a single-body part after the type change,
   and must enumerate across every subshape solid of a Compound.
"""

import uuid
from typing import Any

import pytest
from build123d import Compound, Solid
from geometry.features import evaluate_tree
from geometry.kernel.edges import enumerate_edges, resolve_edge
from geometry.kernel.faces import planar_faces, resolve_face_plane
from py_kit.schemas.features import EvaluateTreeRequest


def _iid(tag: str) -> str:
    return f"00000000-0000-0000-0000-{tag:>012}"


def _square(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
    """A closed, shape-pinned axis-aligned rectangle sketch (corners CCW)."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    entities = [
        {
            "id": f"l{k + 1}",
            "kind": "line",
            "start": {"x": corners[k][0], "y": corners[k][1]},
            "end": {"x": corners[(k + 1) % 4][0], "y": corners[(k + 1) % 4][1]},
        }
        for k in range(4)
    ]
    constraints: list[dict[str, Any]] = [
        {
            "kind": "coincident",
            "a": {"entity": f"l{k}", "point": "end"},
            "b": {"entity": f"l{k % 4 + 1}", "point": "start"},
        }
        for k in range(1, 5)
    ]
    constraints += [
        {"kind": "horizontal", "entity": "l1"},
        {"kind": "horizontal", "entity": "l3"},
        {"kind": "vertical", "entity": "l2"},
        {"kind": "vertical", "entity": "l4"},
    ]
    return {"entities": entities, "constraints": constraints}


def _sketch(fid: str, sq: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fid,
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {"plane": {"kind": "datum_plane", "plane": "XY"}, **sq},
        },
    }


def _extrude(fid: str, profile: str, *, merge: bool | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "profile": {"kind": "feature", "feature_id": profile},
        "distance_mm": 20.0,
        "operation": "add",
        "direction": "normal",
    }
    if merge is not None:
        params["merge"] = merge
    return {"id": fid, "feature": {"type": "extrude", "version": 1, "params": params}}


def _tree(features: list[dict[str, Any]]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": _iid("00000000dd"),
            "tree_version": 1,
            "features": features,
            "linear_deflection": 0.1,
        }
    )


def _one_box() -> Solid:
    """A single 20 mm cube at the origin (its own single-body evaluation)."""
    s, e = _iid("a1"), _iid("a2")
    body = evaluate_tree(
        _tree([_sketch(s, _square(0, 0, 20, 20)), _extrude(e, s)])
    ).body
    assert isinstance(body, Solid)
    return body


# --- Decision 2: merge=False starts a second body ------------------------------


def test_merge_false_starts_a_second_body() -> None:
    """An additive ``merge=False`` starts a NEW body: the part ends with two
    disjoint solids (shells=2), volume summed over the body set, and the last-good
    body is a Compound (§MB-0)."""
    s1, e1, s2, e2 = _iid("b1"), _iid("b2"), _iid("b3"), _iid("b4")
    evaluation = evaluate_tree(
        _tree(
            [
                _sketch(s1, _square(0, 0, 20, 20)),
                _extrude(e1, s1),  # body A (merge absent -> True, first body)
                _sketch(s2, _square(30, 0, 50, 20)),  # 10 mm gap -> disjoint
                _extrude(e2, s2, merge=False),  # body B (new active body)
            ]
        )
    )
    assert [r.status for r in evaluation.result.features] == ["ok"] * 4
    props = evaluation.result.properties
    assert props is not None
    assert props.topology.shells == 2
    assert props.volume == pytest.approx(16000.0, rel=1e-9)
    assert isinstance(evaluation.body, Compound)


def test_merge_true_default_fuses_into_one_body() -> None:
    """The default ``merge=True`` keeps the historical single-body behaviour:
    two overlapping additive extrudes fuse to ONE body (shells=1), byte-identical
    to the pre-multi-body path (a single-entry ``bodies`` measured as the solid)."""
    s1, e1, s2, e2 = _iid("c1"), _iid("c2"), _iid("c3"), _iid("c4")
    evaluation = evaluate_tree(
        _tree(
            [
                _sketch(s1, _square(0, 0, 20, 20)),
                _extrude(e1, s1),
                _sketch(s2, _square(10, 0, 30, 20)),  # overlaps A in x[10,20]
                _extrude(e2, s2),  # merge default True -> fuse into A
            ]
        )
    )
    assert [r.status for r in evaluation.result.features] == ["ok"] * 4
    props = evaluation.result.properties
    assert props is not None
    assert props.topology.shells == 1
    assert isinstance(evaluation.body, Solid)


# --- Decision 1: body-scoped resolution (no false cross-body ambiguity) ---------


def test_body_scoped_fillet_resolves_on_active_body_only() -> None:
    """Two fully-COINCIDENT boxes (body B via ``merge=False`` on top of body A):
    every edge of B is congruent (same absolute signature) with an edge of A. A
    picked-edge fillet on the ACTIVE body (B) must resolve to EXACTLY ONE edge and
    succeed — if resolution ran over a union of both bodies the congruent twin
    would tie a false ``subshape_ambiguous`` (§MB-0 Decision 1, the load-bearing
    rule). The fillet is body-scoped, so it resolves cleanly."""
    # A vertical edge signature of a 20 mm cube at the origin — congruent on BOTH
    # coincident bodies, so a union resolve would be ambiguous.
    vertical = next(
        r
        for r in enumerate_edges(_one_box())
        if r.signature.curve == "line"
        and abs(r.signature.end_a.x - r.signature.end_b.x) < 1e-9
        and abs(r.signature.end_a.y - r.signature.end_b.y) < 1e-9
    )
    s1, e1, s2, e2, fil = (
        _iid("d1"),
        _iid("d2"),
        _iid("d3"),
        _iid("d4"),
        _iid("d5"),
    )
    picked_ref = {
        "kind": "subshape",
        "feature_id": e2,  # the active body's base feature
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": vertical.signature.model_dump(),
        },
    }
    fillet = {
        "id": fil,
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {"kind": "edges", "refs": [picked_ref]},
                "radius_mm": 2.0,
            },
        },
    }
    evaluation = evaluate_tree(
        _tree(
            [
                _sketch(s1, _square(0, 0, 20, 20)),
                _extrude(e1, s1),  # body A
                _sketch(s2, _square(0, 0, 20, 20)),  # SAME square -> coincident
                _extrude(e2, s2, merge=False),  # body B (active), coincident with A
                fillet,  # picked-edge fillet on B
            ]
        )
    )
    statuses = [
        (r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
    ]
    # The fillet resolves body-scoped to B's single matching edge — no
    # subshape_ambiguous despite A's congruent twin edge.
    assert statuses == [("ok", None)] * 5, statuses
    props = evaluation.result.properties
    assert props is not None
    assert props.topology.shells == 2  # still two bodies (A untouched, B filleted)


# --- §Risks: the assembly-mate resolvers survive the Solid->BodyShape widening --


def test_widened_resolvers_accept_solid_and_compound() -> None:
    """``TreeEvaluation.body`` widened ``Solid`` -> ``BodyShape`` flows into the
    assembly mate resolvers (``resolve_face_plane`` / ``resolve_edge`` — §Risks,
    the sneaky ripple). They must resolve a face/edge on a SINGLE-body ``Solid``
    (the common assembly case) AND enumerate across every subshape solid of a
    multi-body ``Compound``."""
    solid = _one_box()
    # Single-body Solid: the mate-resolver entry points still resolve.
    top = next(r for r in planar_faces(solid) if r.signature.normal.z > 0.99)
    plane = resolve_face_plane(solid, top.signature, 0.0)
    assert plane.origin.Z == 20.0  # the top face of the origin cube
    a_vertical = next(
        r
        for r in enumerate_edges(solid)
        if r.signature.curve == "line"
        and abs(r.signature.end_a.x - r.signature.end_b.x) < 1e-9
        and abs(r.signature.end_a.y - r.signature.end_b.y) < 1e-9
    )
    assert resolve_edge(solid, a_vertical.signature) is not None

    # Compound of two DISJOINT boxes: planar_faces / enumerate_edges iterate across
    # every subshape solid (12 planar faces, 24 edges over the two cubes), and a
    # signature unique to one body resolves to exactly one subshape.
    far = Solid.make_box(20, 20, 20).translate((100, 0, 0))
    compound = Compound([solid, far])
    assert len(planar_faces(compound)) == 12
    assert len(enumerate_edges(compound)) == 24
    # The origin cube's top face signature is unique in the compound -> resolves.
    resolve_face_plane(compound, top.signature, 0.0)


def test_mate_resolves_a_face_on_a_multilump_body() -> None:
    """The historically-silent MB-0 ripple, now on a MULTI-LUMP body (§MB-4): a
    part instance whose body is a Compound of several lumps must still resolve a
    mate FACE ref that names a face of ONE lump. ``resolve_mate_geometry``
    delegates to ``resolve_face_plane``, which enumerates faces across every
    subshape solid, so a face unique to the far lump resolves to exactly one face
    (centroid + outward normal) — never a silent break or a cross-lump tie."""
    from geometry.assembly.protocol import ResolvedFace
    from geometry.assembly.resolve import resolve_mate_geometry
    from py_kit.schemas.assemblies import MateFaceRef

    near = _one_box()  # origin cube, x[0,20]
    far = Solid.make_box(20, 20, 20).translate((100, 0, 0))  # far lump, x[100,120]
    compound = Compound([near, far])

    # The +X face of the FAR lump (centroid x=120) is unique to that lump.
    far_plus_x = next(
        r
        for r in planar_faces(compound)
        if r.signature.normal.x > 0.99 and r.signature.centroid.x > 100
    )
    ref = MateFaceRef(
        # any uuid — resolution is body-scoped, not id-scoped
        instance_id=uuid.UUID(_iid("e01a")),
        signature=far_plus_x.signature,
    )
    resolved = resolve_mate_geometry(compound, ref)
    # Resolves to the far lump's +X face: a point ON it (x=120) with outward +X.
    assert isinstance(resolved, ResolvedFace)
    assert resolved.point.x == pytest.approx(120.0, abs=1e-9)
    assert resolved.normal.x == pytest.approx(1.0, abs=1e-9)
