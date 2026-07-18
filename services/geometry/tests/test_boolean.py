"""MB-1a: the `boolean` feature — `union` between independently-built bodies
(docs/design/multi-body.md §Decisions-3 / §MB-1).

The golden ``boolean-union-two-cubes-overlap`` locks the analytic numbers
(12000 mm^3, shells=1) + byte-identical GLB/STEP determinism; this module gates
the BEHAVIOURS a single golden number cannot express:

1. **The union path** — two overlapping bodies fuse to ONE connected solid.
2. **The single-connected-solid-per-body invariant** — a union of DISJOINT
   bodies is a deterministic ``boolean_disjoint`` error (the reason ``bodies``
   values stay a ``Solid``, never a ``Compound``, in v1).
3. **Operand replacement** — the result takes over the target's identity slot
   and the tool body is removed, so the part ends with one body AND a downstream
   ref to the target keeps resolving; a later boolean naming the CONSUMED tool is
   an honest eval-time ``reference_unresolved`` (documents cannot catch it
   statically).
4. **The MB-1a operation gate** — ``subtract``/``intersect`` are defined in the
   schema but return ``boolean_not_implemented`` until MB-2.
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


# --- The MB-1a operation gate (subtract/intersect are MB-2) ----------------------


@pytest.mark.parametrize("operation", ["subtract", "intersect"])
def test_subtract_and_intersect_are_not_implemented_in_mb1a(operation: str) -> None:
    """`subtract`/`intersect` are defined in the schema (stable wire/client type)
    but return an honest `boolean_not_implemented` until MB-2 — never a silent
    wrong body."""
    s1, e1, s2, e2, b = _iid("81"), _iid("82"), _iid("83"), _iid("84"), _iid("85")
    evaluation = evaluate_tree(
        _scene(
            _two_bodies((0, 20), (10, 30), (s1, e1, s2, e2)),
            _boolean(b, operation, e1, e2),
        )
    )
    last = evaluation.result.features[-1]
    assert last.status == "error"
    assert last.error is not None
    assert last.error.code == "boolean_not_implemented"
