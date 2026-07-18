"""The ``SketchSolver`` contract (RESEARCH §2).

The 2D constraint solver hides behind this protocol so the backend is
swappable (planegcs today; anything else tomorrow) and so the GPL guardrail
is structural: callers never import a solver package, only this interface.

Contract requirements for any implementation:

- **Deterministic** (RESEARCH §9): the same ``SketchDefinition`` yields a
  bitwise-identical ``SolvedSketch``, across calls and across processes.
  Entities and constraints are processed in input list order; no
  nondeterministic iteration participates.
- **Diagnosing, not raising:** solve *outcomes* — underconstrained,
  overconstrained, conflicting, diverged — are reported in
  ``SolvedSketch.status``, never as exceptions. Exceptions
  (:class:`SketchDefinitionError`) are reserved for malformed *input*:
  references to unknown entities, wrong point names, constraints applied to
  the wrong entity kind, degenerate geometry.
- **No foreign types:** input and output are the pydantic DTOs from
  :mod:`geometry.sketch.schemas`; solver-native handles never escape.
"""

from typing import Protocol

from geometry.sketch.schemas import SketchDefinition, SolvedSketch


class SketchDefinitionError(ValueError):
    """A ``SketchDefinition`` is malformed (bad reference, wrong entity kind,
    degenerate geometry) — a caller bug, not a solve outcome."""


class SketchSolver(Protocol):
    """A 2D geometric constraint solver."""

    def solve(self, sketch: SketchDefinition) -> SolvedSketch:
        """Solve the sketch and return solved positions plus diagnosis.

        Raises:
            SketchDefinitionError: if the definition is malformed (see the
                module docstring for the exception-vs-status contract).
        """
        ...
