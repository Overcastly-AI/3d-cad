"""The `boolean` feature — union/subtract/intersect between independently-built
bodies (docs/design/multi-body.md §Decisions-3 / §MB-1 / §MB-2).

The goldens ``boolean-{union,subtract,intersect}-two-cubes-overlap`` lock the
analytic numbers (12000 / 4000 / 4000 mm^3, shells=1) + byte-identical GLB/STEP
determinism; this module gates the BEHAVIOURS a single golden number cannot
express:

1. **The three operation paths** — two overlapping bodies fuse (union), the tool
   is cut out of the target (subtract), or their common volume is kept
   (intersect), each to ONE connected solid.
2. **The single-connected-solid-per-body invariant** — a union of DISJOINT
   bodies, or a subtract that SEVERS the target into ≥2 pieces, is a
   deterministic ``boolean_disjoint`` error (the reason ``bodies`` values stay a
   ``Solid``, never a ``Compound``, in v1).
3. **The empty result** — a subtract that removes the whole target, or an
   intersect with no overlap, is an honest ``boolean_empty`` error (MB-2), never
   a crash or a null body.
4. **Operand replacement** — the result takes over the target's identity slot
   and the tool body is removed, so the part ends with one body AND a downstream
   ref to the target keeps resolving; a later boolean naming the CONSUMED tool is
   an honest eval-time ``reference_unresolved`` (documents cannot catch it
   statically).
"""

import math
from typing import Any

import pytest
from build123d import Solid
from geometry.features import evaluate_tree
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


def _boolean(
    fid: str,
    operation: str,
    target: str,
    tool: str,
    *,
    allow_disjoint: bool | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "operation": operation,
        "target": {"kind": "feature", "feature_id": target},
        "tool": {"kind": "feature", "feature_id": tool},
    }
    if allow_disjoint is not None:
        params["allow_disjoint"] = allow_disjoint
    return {
        "id": fid,
        "feature": {"type": "boolean", "version": 1, "params": params},
    }


def _fillet_edge(
    fid: str,
    anchor: str,
    end_a: tuple[float, float, float],
    end_b: tuple[float, float, float],
    radius_mm: float,
) -> dict[str, Any]:
    """A fillet naming ONE picked edge by its stage-1 EdgeSignature (a straight
    line between *end_a* and *end_b*), anchored to feature *anchor*."""
    ax, ay, az = end_a
    bx, by, bz = end_b
    signature = {
        "subshape_type": "edge",
        "curve": "line",
        "end_a": {"x": ax, "y": ay, "z": az},
        "end_b": {"x": bx, "y": by, "z": bz},
        "midpoint": {"x": (ax + bx) / 2, "y": (ay + by) / 2, "z": (az + bz) / 2},
        "length_mm": ((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2) ** 0.5,
    }
    return {
        "id": fid,
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": anchor,
                            "subshape_type": "edge",
                            "selector": {"selector_version": 1, "signature": signature},
                        }
                    ],
                },
                "radius_mm": radius_mm,
            },
        },
    }


def _two_bodies(
    xa: tuple[float, float], xb: tuple[float, float], ids: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Two 20x20x20 cubes: A at x=`xa`, B at x=`xb` (merge=False -> a 2nd body)."""
    s1, e1, s2, e2 = ids
    return [
        _sketch(s1, _square(xa[0], 0, xa[1], 20)),
        _extrude(e1, s1),  # body A (first body)
        _sketch(s2, _square(xb[0], 0, xb[1], 20)),
        _extrude(e2, s2, merge=False),  # body B (second, distinct body)
    ]


def _scene(bodies: list[dict[str, Any]], *tail: dict[str, Any]) -> EvaluateTreeRequest:
    """A tree = a body-building prefix followed by *tail features (booleans)."""
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": _iid("00000000ff"),
            "tree_version": 1,
            "features": [*bodies, *tail],
            "linear_deflection": 0.1,
        }
    )


def _codes(evaluation: Any) -> list[tuple[str, str | None]]:
    return [
        (r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
    ]


# --- The union path (the golden's behavioural half) -----------------------------


def test_union_of_two_overlapping_bodies_is_one_connected_solid() -> None:
    """A[0,20] + B[10,30] (overlap x[10,20]) union -> ONE 30x20x20 box: volume
    12000 mm^3, shells=1, and the last-good body is a single Solid (the tool body
    was consumed, not left as a second lump)."""
    s1, e1, s2, e2, b = _iid("11"), _iid("12"), _iid("13"), _iid("14"), _iid("15")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, e2),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 5
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(12000.0, abs=1e-9)
    assert props.topology.shells == 1
    assert isinstance(evaluation.body, Solid)


def test_union_result_takes_over_target_identity_slot() -> None:
    """Operand replacement: after the union, the surviving body is keyed by the
    TARGET's base id, so a SECOND union naming (target, <fresh third body>)
    resolves the target and fuses again; the tool of the first union is gone."""
    s1, e1, s2, e2 = _iid("21"), _iid("22"), _iid("23"), _iid("24")
    s3, e3, b1, b2 = _iid("25"), _iid("26"), _iid("27"), _iid("28")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b1, "union", e1, e2),  # A+B -> keeps A's id (e1)
            _sketch(s3, _square(25, 0, 45, 20)),  # C overlaps the union at x[25,30]
            _extrude(e3, s3, merge=False),  # body C (third body)
            _boolean(b2, "union", e1, e3),  # (A+B) + C, target still e1
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 8
    props = evaluation.result.properties
    assert props is not None
    # A[0,20] u B[10,30] u C[25,45] tile x[0,45] with full y,z -> a 45x20x20 box.
    assert props.volume == pytest.approx(45 * 20 * 20, abs=1e-9)
    assert props.topology.shells == 1
    assert isinstance(evaluation.body, Solid)


# --- The single-connected-solid-per-body invariant (boolean_disjoint) -----------


def test_union_of_disjoint_bodies_is_boolean_disjoint() -> None:
    """A[0,20] + B[30,50] (10 mm gap) union -> the two lumps do not touch, so the
    union is >1 solid: a `boolean_disjoint` error, and the last-good body is the
    two-body Compound from BEFORE the failed boolean (strict-prefix, last-good)."""
    s1, e1, s2, e2, b = _iid("31"), _iid("32"), _iid("33"), _iid("34"), _iid("35")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (30, 50), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, e2),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 4 + [("error", "boolean_disjoint")]
    # last-good body = the two disjoint cubes (16000 mm^3, shells=2), untouched.
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(16000.0, abs=1e-9)
    assert props.topology.shells == 2


# --- MB-4: opt-in disjoint union -> ONE multi-lump body -------------------------


def test_allow_disjoint_union_is_one_multilump_body() -> None:
    """MB-4 opt-in: A[0,20] + B[30,50] (10 mm gap) union with
    ``allow_disjoint=True`` keeps the two non-touching lumps as ONE multi-lump
    body (a Compound), NOT a `boolean_disjoint` error: volume 16000 mm^3,
    shells=2, and the last-good body is a Compound (one bodies-entry)."""
    s1, e1, s2, e2, b = _iid("f01"), _iid("f02"), _iid("f03"), _iid("f04"), _iid("f05")
    from build123d import Compound  # local: kept out of the single-body import head

    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (30, 50), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, e2, allow_disjoint=True),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 5
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(16000.0, abs=1e-9)
    assert props.topology.shells == 2  # two lumps kept in one body
    assert props.topology.faces == 12
    assert isinstance(evaluation.body, Compound)


def test_allow_disjoint_false_still_errors() -> None:
    """The flag is genuinely opt-in: the SAME disjoint union with
    ``allow_disjoint=False`` (explicit) is still a `boolean_disjoint` error —
    the default safety is unchanged."""
    s1, e1, s2, e2, b = _iid("f11"), _iid("f12"), _iid("f13"), _iid("f14"), _iid("f15")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (30, 50), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, e2, allow_disjoint=False),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 4 + [("error", "boolean_disjoint")]


def test_allow_disjoint_empty_intersect_is_still_boolean_empty() -> None:
    """``allow_disjoint`` only relaxes the >1-solid branch: an EMPTY result (a
    non-overlapping intersect) is still `boolean_empty`, never a null body."""
    s1, e1, s2, e2, b = _iid("f21"), _iid("f22"), _iid("f23"), _iid("f24"), _iid("f25")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (30, 50), (s1, e1, s2, e2)),
            _boolean(b, "intersect", e1, e2, allow_disjoint=True),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 4 + [("error", "boolean_empty")]


def test_allow_disjoint_union_is_deterministic() -> None:
    """The multi-lump body is byte-identical across rebuilds — the lump order is
    the explicit centroid sort, not OCCT traversal order (RESEARCH §9)."""
    s1, e1, s2, e2, b = _iid("f31"), _iid("f32"), _iid("f33"), _iid("f34"), _iid("f35")
    scene = _scene(
        _two_bodies((0, 20), (30, 50), (s1, e1, s2, e2)),
        _boolean(b, "union", e1, e2, allow_disjoint=True),
    )
    first = evaluate_tree(scene)
    second = evaluate_tree(scene)
    assert first.glb == second.glb
    assert first.result.properties == second.result.properties


def test_boolean_disjoint_is_deterministic() -> None:
    """The disjoint error is a pure function of the inputs — same code + message
    on every evaluation (RESEARCH §9), never a coin flip."""
    s1, e1, s2, e2, b = _iid("41"), _iid("42"), _iid("43"), _iid("44"), _iid("45")
    scene = _scene(
        _two_bodies((0, 20), (40, 60), (s1, e1, s2, e2)), _boolean(b, "union", e1, e2)
    )
    first = evaluate_tree(scene).result.features[-1].error
    second = evaluate_tree(scene).result.features[-1].error
    assert first is not None and second is not None
    assert first.code == second.code == "boolean_disjoint"
    assert first.message == second.message


# --- Reference resolution (incl. the eval-time consumed-body case) ---------------


def test_boolean_naming_a_consumed_tool_is_reference_unresolved() -> None:
    """A body consumed as the TOOL of an earlier boolean is removed from the set,
    so a later boolean naming it is an honest eval-time `reference_unresolved`
    (documents cannot catch a body's consumption statically)."""
    s1, e1, s2, e2 = _iid("51"), _iid("52"), _iid("53"), _iid("54")
    s3, e3, b1, b2 = _iid("55"), _iid("56"), _iid("57"), _iid("58")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b1, "union", e1, e2),  # consumes e2 (the tool)
            _sketch(s3, _square(25, 0, 45, 20)),
            _extrude(e3, s3, merge=False),
            _boolean(b2, "union", e3, e2),  # tool e2 was already consumed
        )
    )
    last = evaluation.result.features[-1]
    assert last.status == "error"
    assert last.error is not None
    assert last.error.code == "reference_unresolved"
    assert last.error.upstream_feature_id is not None
    assert str(last.error.upstream_feature_id) == e2


def test_boolean_naming_a_missing_body_is_reference_unresolved() -> None:
    """An operand ref to a feature that never produced a body resolves to a clean
    `reference_unresolved` (geometry re-checks; it must not trust its callers)."""
    s1, e1, s2, e2, b = _iid("61"), _iid("62"), _iid("63"), _iid("64"), _iid("65")
    missing = _iid("6f")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, missing),
        )
    )
    last = evaluation.result.features[-1]
    assert last.status == "error"
    assert last.error is not None
    assert last.error.code == "reference_unresolved"


def test_boolean_target_equals_tool_is_boolean_same_body() -> None:
    """Target and tool naming the SAME body is a degenerate self-fuse: a clean
    `boolean_same_body` error, never a silent body-deleting no-op."""
    s1, e1, s2, e2, b = _iid("71"), _iid("72"), _iid("73"), _iid("74"), _iid("75")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, e1),
        )
    )
    last = evaluation.result.features[-1]
    assert last.status == "error"
    assert last.error is not None
    assert last.error.code == "boolean_same_body"


# --- MB-2: subtract + intersect (the two new operation paths) --------------------


def test_subtract_removes_the_tool_from_the_target() -> None:
    """A[0,20] - B[10,30] (overlap x[10,20], same y,z) -> the slab x[0,10]: a
    clean 4000 mm^3 box, ONE connected solid (the golden's behavioural half)."""
    s1, e1, s2, e2, b = _iid("81"), _iid("82"), _iid("83"), _iid("84"), _iid("85")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "subtract", e1, e2),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 5
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(4000.0, abs=1e-9)
    assert props.topology.shells == 1
    assert isinstance(evaluation.body, Solid)


def test_intersect_keeps_only_the_common_volume() -> None:
    """A[0,20] ∩ B[10,30] -> the overlap slab x[10,20]: a clean 4000 mm^3 box,
    ONE connected solid (the intersect golden's behavioural half)."""
    s1, e1, s2, e2, b = _iid("91"), _iid("92"), _iid("93"), _iid("94"), _iid("95")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "intersect", e1, e2),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 5
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(4000.0, abs=1e-9)
    assert props.topology.shells == 1
    assert isinstance(evaluation.body, Solid)


def test_subtract_order_matters_target_is_the_minuend() -> None:
    """subtract is NOT commutative: target-tool vs tool-target differ. B[10,30] -
    A[0,20] keeps the slab x[20,30] (also 4000 mm^3 but a DIFFERENT body), proving
    the operand roles (target=minuend, tool=subtrahend) are honoured."""
    s1, e1, s2, e2, b = _iid("a1"), _iid("a2"), _iid("a3"), _iid("a4"), _iid("a5")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "subtract", e2, e1),  # B - A (roles swapped vs above)
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 5
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(4000.0, abs=1e-9)
    # B - A = the slab x[20,30]; its centroid sits at x=25, distinguishing it from
    # A - B (x=5). The surviving body is keyed by the TARGET (e2 = B's base).
    assert props.centroid.x == pytest.approx(25.0, abs=1e-9)
    assert props.topology.shells == 1


# --- MB-2: the empty result (boolean_empty) --------------------------------------


def test_intersect_with_no_overlap_is_boolean_empty() -> None:
    """A[0,20] ∩ B[30,50] (10 mm gap) -> the common volume is empty: an honest
    `boolean_empty` error (build123d returns None for an empty common), never a
    crash or a null body. Last-good = the two disjoint cubes, untouched."""
    s1, e1, s2, e2, b = _iid("b1"), _iid("b2"), _iid("b3"), _iid("b4"), _iid("b5")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (30, 50), (s1, e1, s2, e2)),
            _boolean(b, "intersect", e1, e2),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 4 + [("error", "boolean_empty")]
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(16000.0, abs=1e-9)  # both cubes intact
    assert props.topology.shells == 2


def test_subtract_that_removes_the_whole_target_is_boolean_empty() -> None:
    """A tool that fully CONTAINS the target removes everything -> `boolean_empty`
    (0 solids), never a silent null body. A[5,15]³ inside B[0,20]³: A - B = ∅."""
    s1, e1, s2, e2, b = _iid("c1"), _iid("c2"), _iid("c3"), _iid("c4"), _iid("c5")
    evaluation = evaluate_tree(
        _scene(
            [
                _sketch(s1, _square(5, 5, 15, 15)),
                _extrude(e1, s1),  # body A: 10x10 at [5,15], extrude 20 -> inside B
                _sketch(s2, _square(0, 0, 20, 20)),
                _extrude(e2, s2, merge=False),  # body B: 20x20x20, contains A
            ],
            _boolean(b, "subtract", e1, e2),  # A - B: B swallows A -> empty
        )
    )
    last = evaluation.result.features[-1]
    assert last.status == "error"
    assert last.error is not None
    assert last.error.code == "boolean_empty"


# --- MB-2: a severing subtract violates the single-connected-solid invariant -----


def test_subtract_that_severs_the_target_is_boolean_disjoint() -> None:
    """A subtract whose tool SPLITS the target into two disconnected pieces is a
    `boolean_disjoint` error (>1 solid — multi-lump bodies are MB-4). Bar A spans
    x[0,30], y[0,10], z[0,20]; tool B is the middle slab x[10,20] over the bar's
    full y,z -> A - B = x[0,10] and x[20,30], two lumps."""
    s1, e1, s2, e2, b = _iid("d1"), _iid("d2"), _iid("d3"), _iid("d4"), _iid("d5")
    evaluation = evaluate_tree(
        _scene(
            [
                _sketch(s1, _square(0, 0, 30, 10)),
                _extrude(e1, s1),  # bar A: x[0,30], y[0,10], z[0,20]
                _sketch(s2, _square(10, 0, 20, 10)),
                _extrude(e2, s2, merge=False),  # tool B: middle slab x[10,20]
            ],
            _boolean(b, "subtract", e1, e2),  # severs A into two pieces
        )
    )
    last = evaluation.result.features[-1]
    assert last.status == "error"
    assert last.error is not None
    assert last.error.code == "boolean_disjoint"


# --- MB-3: a downstream fillet on a boolean-CREATED edge --------------------------
#
# The golden ``boolean-union-then-fillet`` locks the analytic numbers (11920 +
# 20*pi mm^3, 7/15/1) + byte-identical determinism; these tests gate the
# topological-naming BEHAVIOURS a single golden number cannot express (design
# §MB-3 / §Decisions-4): the fillet resolves a boolean-created edge on a clean
# rebuild, and degrades to a TYPED error (never a wrong edge / crash) under a
# topology-changing upstream edit. The picked edge is the fused 30x20x20 box's
# vertical corner at x=0,y=0,z[0,20] — an edge of body A that survives the union
# as an OUTER corner of the fused result.

#: The x=0,y=0 vertical corner edge of the fused A[0,20]+B box (z runs [0,20]).
_CORNER = ((0.0, 0.0, 0.0), (0.0, 0.0, 20.0))


def test_fillet_resolves_a_boolean_created_edge() -> None:
    """THE MB-3 proof: a fillet on an edge of the fused result resolves via the
    stage-1 EdgeSignature to EXACTLY ONE edge on a clean rebuild, and rounds it —
    the fused body's edges get signatures like any primitive's. The result is one
    connected solid (shells=1) with the analytic filleted volume."""
    s1, e1, s2, e2 = _iid("e1"), _iid("e2"), _iid("e3"), _iid("e4")
    b, fil = _iid("e5"), _iid("e6")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, e2),  # -> fused 30x20x20 box, keyed by e1
            _fillet_edge(fil, b, _CORNER[0], _CORNER[1], radius_mm=2.0),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 6
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(11920 + 20 * math.pi, abs=1e-9)
    assert props.topology.shells == 1  # still one connected solid
    assert props.topology.faces == 7  # 6 box faces + 1 fillet face
    assert isinstance(evaluation.body, Solid)


def test_fillet_on_boolean_edge_is_body_scoped_no_consumed_operand_ghost() -> None:
    """Body-scoped confirm (design §MB-3 / §MB-0 Decision 1): after the union the
    tool body B is CONSUMED (removed from the set), so the fillet resolves against
    the SINGLE post-boolean active body — the picked corner resolves to exactly
    one edge with NO false `subshape_ambiguous` from a ghost of B. (Both A and B
    had an x=0,y=0-family corner before the union; only the fused body's single
    outer corner survives.)"""
    s1, e1, s2, e2 = _iid("f1"), _iid("f2"), _iid("f3"), _iid("f4")
    b, fil = _iid("f5"), _iid("f6")
    evaluation = evaluate_tree(
        _scene(
            # B coincident-in-x-range with A so both share the x=0-plane face
            # region; the union still yields ONE fused body with ONE x=0,y=0 edge.
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, "union", e1, e2),
            _fillet_edge(fil, b, _CORNER[0], _CORNER[1], radius_mm=2.0),
        )
    )
    # Resolves cleanly (exactly one edge) — no subshape_ambiguous, no ghost.
    assert _codes(evaluation) == [("ok", None)] * 6
    props = evaluation.result.properties
    assert props is not None
    # ONE body remains (the fused+filleted solid); B's ghost is gone.
    assert props.topology.shells == 1


def test_fillet_on_boolean_edge_degrades_to_typed_error_under_topology_edit() -> None:
    """The honest degrade-under-edit limit (design §MB-3): a topology-CHANGING
    upstream edit that removes the picked edge surfaces a CLEAN typed
    `subshape_unresolved` — never a wrong-edge fillet or a crash. Here cube B is
    moved to x[-5,15] so it SWALLOWS the x=0,y=0 corner of A (the corner becomes
    interior to the union, so the picked outer edge no longer exists). Observed
    2026-07-18: stage-1 absolute-coordinate signature -> `subshape_unresolved`."""
    s1, e1, s2, e2 = _iid("1a1"), _iid("1a2"), _iid("1a3"), _iid("1a4")
    b, fil = _iid("1a5"), _iid("1a6")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (-5, 15), (s1, e1, s2, e2)),  # B swallows the corner
            _boolean(b, "union", e1, e2),
            _fillet_edge(fil, b, _CORNER[0], _CORNER[1], radius_mm=2.0),
        )
    )
    codes = _codes(evaluation)
    # The boolean itself still succeeds (A and B overlap -> one fused body); the
    # FILLET is the honest failure: the picked corner edge is gone.
    assert codes[:-1] == [("ok", None)] * 5
    last = evaluation.result.features[-1]
    assert last.status == "error"
    assert last.error is not None
    assert last.error.code == "subshape_unresolved"


def test_fillet_on_boolean_edge_survives_a_non_topology_changing_edit() -> None:
    """The other half of the honest bound (design §MB-3): an upstream edit that
    does NOT touch the picked edge leaves it resolvable — the signature is not
    brittle to every change, only to ones that move/remove the edge. Moving B to
    x[5,25] (still overlapping A, the x=0,y=0 corner untouched) -> the fillet
    still resolves `ok`."""
    s1, e1, s2, e2 = _iid("1b1"), _iid("1b2"), _iid("1b3"), _iid("1b4")
    b, fil = _iid("1b5"), _iid("1b6")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (5, 25), (s1, e1, s2, e2)),  # union spans x[0,25]
            _boolean(b, "union", e1, e2),
            _fillet_edge(fil, b, _CORNER[0], _CORNER[1], radius_mm=2.0),
        )
    )
    assert _codes(evaluation) == [("ok", None)] * 6
    props = evaluation.result.properties
    assert props is not None
    # Fused body is a 25x20x20 box (volume 10000) minus the same corner round.
    assert props.volume == pytest.approx(25 * 20 * 20 - 20 * (4 - math.pi), abs=1e-9)
    assert props.topology.shells == 1
