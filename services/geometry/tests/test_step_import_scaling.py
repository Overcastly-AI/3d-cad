"""STEP import at real part size — the reader's cost curve and its DoS ceiling.

Companion to ``test_scaling_benchmarks.py`` (which measures REBUILD at size) for
the other half of docs/PERF.md: **reading a big STEP back in.** The first
real-part benchmark (2026-07-31) found the import of Loft's OWN export of a
2 006-face part burning **18.44 s of the 20 s CPU ceiling** — 92 % — so a part
only ~4 % larger would have come back ``import_parse_timeout``: not a slow
import, a **wrong refusal** on a legitimate file.

Root cause (profiled, docs/PERF.md 2026-07-31b): OCCT's STEP transfer runs a
``ShapeFix_Shape`` pass after building the topology, and one operation in it —
``ShapeFix_Wire::FixSelfIntersection`` — is super-quadratic in **edges per wire**.
The benchmark heat sink's two comb faces each carry ONE wire of ``4 * fins + 4``
edges, so its worst wire grew with the part and the import curve looked like
``faces^2.4``. It never was a face-count law: a 442-face tray (worst wire: 8
edges) and a 406-face perforated plate (worst wire: 4) import in ~1.4 s, while the
2 006-face sink took 18.6 s. :data:`~geometry.kernel._step_parse_worker.
SHAPE_FIX_PARAMETERS` disables that one operation; the transferred shape is
byte-identical and the curve is linear.

TIER POLICY, same as ``test_scaling_benchmarks.py``:

* the **sweep** is ``benchmark``-marked AND gated on ``LOFT_SCALING_BENCH=1``, so
  it never runs in CI and asserts nothing about time — it prints the table
  docs/PERF.md is written from;
* the **correctness gates** are unmarked and always on, because "does a comb-wire
  part still round-trip exactly through the bounded worker" is a fidelity
  question, not a timing one. They run at the SMALL end (128 fins / 518 faces).

Reproduce the sweep::

    LOFT_SCALING_BENCH=1 uv run pytest \\
      services/geometry/tests/test_step_import_scaling.py -m benchmark -s
"""

# The OCP wheel ships no type stubs, so the raw OCCT reader calls in the
# shape-fix-parameter gate below are opaque to pyright; the directives scope that
# relaxation to this file only (the same posture as geometry.kernel.imports).
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import importlib.util
import os
import resource
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from build123d import Solid
from geometry.features import evaluate_tree
from geometry.kernel import measure_shape
from geometry.kernel._step_parse_worker import (
    SHAPE_FIX_PARAMETERS,
    apply_shape_fix_parameters,
)
from geometry.kernel.export import export_step_bytes
from geometry.kernel.imports import import_step_solid
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import EvaluateTreeRequest

_HERE = Path(__file__).resolve().parent

#: Always-on fidelity size: 518 faces, one 516-edge comb wire — big enough that
#: the disabled repair operation is genuinely exercised, small enough (~3 s end to
#: end) to sit in the default suite.
GATE_FINS = 128

#: Sweep points for the opt-in table.
FIN_SWEEP: tuple[int, ...] = (64, 128, 256, 500)
FEATURE_SWEEP: tuple[int, ...] = (100, 200)
HOLE_SWEEP: tuple[int, ...] = (200, 400)


def _load_builders() -> ModuleType:
    """Load the shared big-part builders by path (importlib import-mode: test
    modules cannot import each other by name — root pyproject.toml)."""
    spec = importlib.util.spec_from_file_location(
        "_big_part_builders", _HERE / "_big_part_builders.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILDERS = _load_builders()
housing_tree = cast(Callable[[int], dict[str, Any]], _BUILDERS.housing_tree)
heat_sink_tree = cast(Callable[[int], dict[str, Any]], _BUILDERS.heat_sink_tree)


def perforated_plate_tree(holes: int) -> dict[str, Any]:
    """A plate with *holes* through-holes in a row (one pattern-cut feature).

    The topological OPPOSITE of the heat sink at comparable face count: many faces
    and many WIRES, every wire 4 edges or fewer. It is the corpus point that shows
    import cost tracks edges-per-wire and input bytes, never face count.
    """
    uid: Callable[[int], str] = cast(Callable[[int], str], _BUILDERS._uid)
    sketch: Callable[..., dict[str, Any]] = cast(
        Callable[..., dict[str, Any]], _BUILDERS._sketch
    )
    rect: Callable[..., list[dict[str, Any]]] = cast(
        Callable[..., list[dict[str, Any]]], _BUILDERS._rect_entities
    )
    xy = cast(dict[str, Any], _BUILDERS._XY)

    pitch, diameter, thickness = 10.0, 6.0, 4.0
    length = pitch * holes + 20.0
    ids = [uid(0x900 + i) for i in range(5)]
    hole_profile = [
        {
            "id": "c0",
            "kind": "circle",
            "center": {"x": -length / 2 + 10.0, "y": 0.0},
            "radius": diameter / 2,
        }
    ]

    def extrude(profile_id: str, distance: float, operation: str) -> dict[str, Any]:
        return {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": profile_id},
                "distance_mm": distance,
                "operation": operation,
                "direction": "normal",
            },
        }

    return {
        "part_id": uid(0x9F1),
        "tree_version": 1,
        "features": [
            {"id": ids[0], "feature": sketch(xy, rect(0.0, 0.0, length, 40.0, "p"))},
            {"id": ids[1], "feature": extrude(ids[0], thickness, "add")},
            {"id": ids[2], "feature": sketch(xy, hole_profile)},
            {"id": ids[3], "feature": extrude(ids[2], thickness + 2.0, "cut")},
            {
                "id": ids[4],
                "feature": {
                    "type": "pattern",
                    "version": 1,
                    "params": {
                        "pattern": {
                            "kind": "linear",
                            "direction": {"x": 1.0, "y": 0.0, "z": 0.0},
                            "spacing_mm": pitch,
                            "count": holes,
                        }
                    },
                },
            },
        ],
        "linear_deflection": 0.1,
    }


def _build(payload: dict[str, Any]) -> BodyShape:
    request = EvaluateTreeRequest.model_validate(payload)
    evaluation = evaluate_tree(request)
    failed = [
        f"{index}:{request.features[index].feature.type}:{result.status}"
        for index, result in enumerate(evaluation.result.features)
        if result.status != "ok"
    ]
    assert not failed, f"benchmark tree did not evaluate clean: {failed}"
    body = evaluation.body
    assert body is not None
    return body


def _worst_wire_edges(body: BodyShape) -> int:
    """Edges in the body's LONGEST wire — the quantity import cost tracks."""
    return max(
        (len(wire.edges()) for face in body.faces() for wire in face.wires()), default=0
    )


def _child_cpu_s() -> float:
    """CPU seconds consumed by REAPED CHILDREN — exactly what ``RLIMIT_CPU``
    bounds in the parse worker, and (unlike wall-clock) invariant to machine load,
    which is the whole premise of the import bound's design."""
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


# --- Correctness / fidelity (UNMARKED — runs in the default suite) --------------


def test_comb_wire_part_round_trips_through_the_bounded_worker(
    assert_roundtrip_preserved: Callable[[str, Any, Any], None],
) -> None:
    """A part with a LONG wire survives export → the real bounded import exactly.

    This is the gate that pays for disabling OCCT's self-intersecting-wire repair
    (``SHAPE_FIX_PARAMETERS``): the operation was removed precisely because it
    changes nothing on well-formed input, and "changes nothing" has to be a gate,
    not a claim. Deliberately through :func:`import_step_solid` — the subprocess
    the evaluate handler actually uses, where the parameter is applied — and not
    ``build123d.import_step``, so a regression in the worker's wiring fails here.

    Same bound as every other round-trip gate: the shared ``ROUNDTRIP_TOL`` (1e-7)
    and topology counts exactly. No size-scaled epsilon.
    """
    body = _build(heat_sink_tree(GATE_FINS))
    worst = _worst_wire_edges(body)
    assert worst >= 4 * GATE_FINS, (
        f"the fidelity gate needs a LONG wire to be meaningful; worst wire is "
        f"{worst} edges — the builder changed and this gate stopped testing the "
        "operation it exists for."
    )

    original = measure_shape(body)
    reimported = import_step_solid(export_step_bytes(body).decode("utf-8"))
    assert_roundtrip_preserved(
        f"heat-sink({GATE_FINS} fins)", measure_shape(reimported), original
    )


def test_the_parse_worker_disables_self_intersection_repair(tmp_path: Path) -> None:
    """The mechanism, pinned: the reader's TRANSFER ACTOR carries the parameter.

    ``XSControl_Reader::SetShapeFixParameters`` forwards the map to the actor, and
    the actor does not exist until ``ReadFile`` has initialised the work session —
    so calling it too early is SILENTLY a no-op (measured: 2.07 s vs 0.53 s on the
    same file, with identical output either way, which is exactly the kind of
    regression that hides). Asserting on the actor's map, not the reader's, is the
    only way to tell the two apart, and the ``pytest.raises`` half pins the
    ordering constraint so a future refactor cannot quietly move the call.
    """
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TCollection import TCollection_AsciiString

    path = tmp_path / "box.step"
    path.write_bytes(export_step_bytes(Solid.make_box(10.0, 10.0, 10.0)))

    reader = STEPControl_Reader()
    # Before ReadFile there is no actor at all — the trap this ordering avoids.
    assert reader.WS().TransferReader().Actor() is None

    assert reader.ReadFile(str(path)) == IFSelect_ReturnStatus.IFSelect_RetDone
    apply_shape_fix_parameters(reader)

    actor_parameters = reader.WS().TransferReader().Actor().GetShapeFixParameters()
    assert SHAPE_FIX_PARAMETERS == {"FixShape.FixSelfIntersectionMode": "0"}
    for key, value in SHAPE_FIX_PARAMETERS.items():
        bound = actor_parameters.Find(TCollection_AsciiString(key))
        assert bound.ToCString() == value, (
            f"the transfer actor did not receive {key}={value} — OCCT's "
            "super-quadratic self-intersecting-wire repair is running again "
            "(docs/PERF.md PERF-3)."
        )


# --- The sweep (benchmark-marked AND env-gated; never a CI gate) ----------------


@pytest.mark.benchmark
@pytest.mark.skipif(
    os.environ.get("LOFT_SCALING_BENCH") != "1",
    reason="scaling sweep is opt-in: set LOFT_SCALING_BENCH=1 (see module docstring)",
)
def test_record_step_import_scaling(capsys: pytest.CaptureFixture[str]) -> None:
    """Import every corpus part through the BOUNDED worker; print the table.

    Reports the child's CPU seconds — the quantity ``RLIMIT_CPU`` actually bounds —
    next to the ceiling, so the headroom claim in
    :data:`~geometry.kernel.imports.DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S` is a
    measurement and not an estimate. Asserts nothing about time; the only
    assertions are correctness ones that would invalidate a measurement.
    """
    from geometry.kernel.imports import DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S

    parts: list[tuple[str, dict[str, Any]]] = [
        *[(f"tray N={n}", housing_tree(n)) for n in FEATURE_SWEEP],
        *[(f"plate {h} holes", perforated_plate_tree(h)) for h in HOLE_SWEEP],
        *[(f"sink {k} fins", heat_sink_tree(k)) for k in FIN_SWEEP],
    ]

    rows: list[tuple[str, int, int, float, float, float, float]] = []
    for label, payload in parts:
        body = _build(payload)
        step = export_step_bytes(body)
        mib = len(step) / 1048576
        before_cpu, before_wall = _child_cpu_s(), time.perf_counter()
        reimported = import_step_solid(
            step.decode("utf-8"), cpu_timeout_s=600.0, wall_timeout_s=900.0
        )
        wall_ms = (time.perf_counter() - before_wall) * 1000.0
        cpu_s = _child_cpu_s() - before_cpu
        assert len(reimported.faces()) == len(body.faces()), label
        rows.append(
            (
                label,
                len(body.faces()),
                _worst_wire_edges(body),
                mib,
                wall_ms,
                cpu_s,
                100.0 * cpu_s / DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S,
            )
        )

    with capsys.disabled():
        print(
            f"\n### STEP import through import_step_solid "
            f"(ceiling {DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S:g} CPU s)\n"
        )
        print(
            "| part | faces | worst wire (edges) | STEP MiB | import ms | "
            "child CPU s | CPU s/MiB | of ceiling |"
        )
        print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for label, faces, worst, mib, wall_ms, cpu_s, share in rows:
            print(
                f"| {label} | {faces} | {worst} | {mib:.2f} | {wall_ms:.0f} | "
                f"{cpu_s:.2f} | {cpu_s / mib:.2f} | {share:.0f}% |"
            )
