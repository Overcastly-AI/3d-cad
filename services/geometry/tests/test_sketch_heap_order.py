"""SKETCH-SOLVE-HEAP-ORDER: a sketch solves bit-identically however the heap looks.

planegcs 0.8.0 made three choices by memory ADDRESS (RESEARCH §2): the column
order of a subsystem (``std::set<double*>``), the column order of the two-level
solve (``std::sort`` of pointers), and, after an equality reduction, which of
the merged parameters seeded the solve (a walk of ``std::map<double*, ...>``).
The binding keeps parameters in a ``std::deque`` of 64-double chunks whose
relative addresses depend on the heap, so past 64 parameters one long-running
worker could rebuild a stored part differently: the 24-line polygon below came
back 27.4 um apart, and three rounded rectangles held to their virtual sharps
7e-15 apart. A fresh process looked deterministic, which is why the old
two-solve tests passed.

Loft builds planegcs from ``vendor/planegcs`` with
``vendor/planegcs-loft.patch``, which orders all three by declaration index.
These tests solve each sketch 20 times in ONE process with the C heap
deliberately churned between solves, then in fresh processes, and demand the
same bytes every time. No tolerance: determinism takes none.
"""

import hashlib
import importlib.metadata
import json
import math
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from geometry.sketch import PlanegcsSketchSolver, SketchDefinition

SOLVES = 20
#: Bytes per C-heap block. A bytearray over 512 bytes is malloc'd, not
#: pymalloc'd, and 513-520 lands in the same malloc bin as the binding's
#: 512-byte deque chunks: the churn that reorders them.
CHUNK_SIZED = (513, 516, 520)


def _p(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def polygon_24() -> dict[str, Any]:
    """24 lines joined end to start, every other one 13 mm, one corner fixed.

    96 free parameters and DOF 34, so the result depends on where the solve
    starts; the ends are drawn 0.3 / -0.2 off the next start, so each
    coincidence merges two DIFFERENT values (the seed the patch makes stable).
    """
    n = 24
    rng = random.Random(3)
    pts = [
        (
            50 * math.cos(2 * math.pi * i / n) + rng.uniform(-1, 1),
            50 * math.sin(2 * math.pi * i / n) + rng.uniform(-1, 1),
        )
        for i in range(n)
    ]
    entities = [
        {
            "id": f"l{i}",
            "kind": "line",
            "start": _p(*pts[i]),
            "end": _p(pts[(i + 1) % n][0] + 0.3, pts[(i + 1) % n][1] - 0.2),
        }
        for i in range(n)
    ]
    constraints: list[dict[str, Any]] = [
        {
            "kind": "coincident",
            "a": {"entity": f"l{i}", "point": "end"},
            "b": {"entity": f"l{(i + 1) % n}", "point": "start"},
        }
        for i in range(n)
    ]
    constraints += [
        {"kind": "distance", "entity": f"l{i}", "value_mm": 13} for i in range(0, n, 2)
    ]
    constraints.append({"kind": "fixed", "point": {"entity": "l0", "point": "start"}})
    return {"entities": entities, "constraints": constraints}


def _rounded_rect(k: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """An 80 x 50 rectangle, corners filleted, W and H held to the virtual sharps."""
    pre, ox, w, h, r = f"r{k}", 100.0 * k, 80.0, 50.0, 5.0
    rng = random.Random(pre)

    def jit(x: float, y: float) -> dict[str, float]:
        return _p(x + rng.uniform(-0.7, 0.7), y + rng.uniform(-0.7, 0.7))

    def line(i: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
        return {"id": pre + i, "kind": "line", "start": jit(*a), "end": jit(*b)}

    def arc(
        i: str, c: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
    ) -> dict[str, Any]:
        return {
            "id": pre + i,
            "kind": "arc",
            "center": jit(*c),
            "start": jit(*a),
            "end": jit(*b),
        }

    entities = [
        line("1", (ox + r, 0), (ox + w - r, 0)),
        line("2", (ox + w, r), (ox + w, h - r)),
        line("3", (ox + w - r, h), (ox + r, h)),
        line("4", (ox, h - r), (ox, r)),
        arc("a", (ox + w - r, h - r), (ox + w, h - r), (ox + w - r, h)),
        arc("b", (ox + w - r, r), (ox + w - r, 0), (ox + w, r)),
        arc("c", (ox + r, h - r), (ox + r, h), (ox, h - r)),
        arc("d", (ox + r, r), (ox, r), (ox + r, 0)),
    ]

    def tangent(a: str, ap: str, b: str, bp: str) -> dict[str, Any]:
        return {
            "kind": "tangent",
            "a": pre + a,
            "b": pre + b,
            "a_point": ap,
            "b_point": bp,
        }

    constraints: list[dict[str, Any]] = [
        {"kind": "horizontal", "entity": pre + "1"},
        {"kind": "vertical", "entity": pre + "2"},
        {"kind": "horizontal", "entity": pre + "3"},
        {"kind": "vertical", "entity": pre + "4"},
        tangent("2", "end", "a", "start"),
        tangent("3", "start", "a", "end"),
        tangent("1", "end", "b", "start"),
        tangent("2", "start", "b", "end"),
        tangent("3", "end", "c", "start"),
        tangent("4", "start", "c", "end"),
        tangent("4", "end", "d", "start"),
        tangent("1", "start", "d", "end"),
        {"kind": "radius", "entity": pre + "a", "value_mm": 15},
        *({"kind": "radius", "entity": pre + x, "value_mm": 5} for x in "bcd"),
        {"kind": "fixed", "point": {"entity": pre + "d", "point": "center"}},
        {
            "kind": "distance",
            "entity": pre + "1",
            "value_mm": 80,
            "start_sharp": pre + "4",
            "end_sharp": pre + "2",
        },
        {
            "kind": "distance",
            "entity": pre + "2",
            "value_mm": 50,
            "start_sharp": pre + "1",
            "end_sharp": pre + "3",
        },
    ]
    return entities, constraints


def rounded_rects_with_sharps() -> dict[str, Any]:
    """Three of them in one sketch: well past 64 parameters, fully constrained."""
    entities: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for k in range(3):
        e, c = _rounded_rect(k)
        entities += e
        constraints += c
    return {"entities": entities, "constraints": constraints}


FIXTURES = {
    "polygon-24-underconstrained": (polygon_24, "underconstrained"),
    "rounded-rects-virtual-sharps": (rounded_rects_with_sharps, "converged"),
}


def _solve_digest(raw: dict[str, Any]) -> tuple[str, str]:
    """(status, sha256 of the solved sketch's JSON). JSON floats round-trip exactly."""
    solved = PlanegcsSketchSolver().solve(SketchDefinition.model_validate(raw))
    return solved.status, hashlib.sha256(solved.model_dump_json().encode()).hexdigest()


def _churn(rng: random.Random, held: list[bytearray]) -> None:
    """Fragment the C heap the way a busy worker does between two solves."""
    for _ in range(rng.randint(5, 40)):
        size = rng.choice(CHUNK_SIZED) if rng.random() < 0.7 else rng.randint(600, 6000)
        held.append(bytearray(size))
    rng.shuffle(held)
    del held[: len(held) // 2]
    # The solver's own allocations too: an unrelated small sketch.
    PlanegcsSketchSolver().solve(
        SketchDefinition.model_validate(
            {
                "entities": [
                    {
                        "id": "x",
                        "kind": "line",
                        "start": _p(0, 0),
                        "end": _p(rng.uniform(5, 50), 1),
                    }
                ],
                "constraints": [{"kind": "horizontal", "entity": "x"}],
            }
        )
    )


def test_the_vendored_planegcs_is_installed() -> None:
    """The PyPI wheel has the bug; only the patched build may be under test."""
    assert "+loft." in importlib.metadata.version("planegcs")


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_same_sketch_solves_bit_identically_under_heap_churn(name: str) -> None:
    build, status = FIXTURES[name]
    raw = build()
    rng = random.Random(name)
    held: list[bytearray] = []
    digests: list[str] = []
    for _ in range(SOLVES):
        _churn(rng, held)
        got_status, digest = _solve_digest(raw)
        assert got_status == status
        digests.append(digest)
    assert len(set(digests)) == 1, (
        f"{len(set(digests))} distinct results in {SOLVES} solves"
    )


_CHILD = """
import json, random, sys
sys.path.insert(0, sys.argv[1])
import test_sketch_heap_order as t
held = []
rng = random.Random(int(sys.argv[2]))
for _ in range(rng.randint(0, 3)):
    t._churn(rng, held)
digests = {n: t._solve_digest(b())[1] for n, (b, _) in sorted(t.FIXTURES.items())}
print(json.dumps(digests))
"""


def test_same_sketch_solves_bit_identically_across_processes() -> None:
    """Fresh processes, each starting from a different heap, agree with this one."""
    here = {n: _solve_digest(b())[1] for n, (b, _) in sorted(FIXTURES.items())}
    tests_dir = str(Path(__file__).resolve().parent)
    for seed in (1, 2):
        out = subprocess.run(
            [sys.executable, "-c", _CHILD, tests_dir, str(seed)],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        assert json.loads(out.stdout) == here
