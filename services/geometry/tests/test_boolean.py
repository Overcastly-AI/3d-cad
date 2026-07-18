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


def _boolean(fid: str, operation: str, target: str, tool: str) -> dict[str, Any]:
    return {
        "id": fid,
        "feature": {
            "type": "boolean",
            "version": 1,
            "params": {
                "operation": operation,
                "target": {"kind": "feature", "feature_id": target},
                "tool": {"kind": "feature", "feature_id": tool},
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
