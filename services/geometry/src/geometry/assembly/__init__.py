"""Assembly mate solver (design ``docs/design/assemblies.md`` §2).

The deterministic rigid-body 3D mate solver, behind the
:class:`~geometry.assembly.protocol.AssemblySolver` protocol (mirroring
``SketchSolver``). Numeric core only (numpy) — no OCCT, no GPL. Item #2 proves
the numerics against SYNTHETIC resolved geometry; item #3 wires the real
mate-geometry-ref resolution into :class:`SolverMate.geometry`.
"""

from geometry.assembly.evaluate import evaluate_assembly
from geometry.assembly.protocol import (
    AssemblyDefinitionError,
    AssemblyOverconstraintClass,
    AssemblySolveDiagnosis,
    AssemblySolveInput,
    AssemblySolveMethod,
    AssemblySolver,
    AssemblySolveResult,
    AssemblySolveStatus,
    ResolvedAxis,
    ResolvedFace,
    ResolvedMateGeometry,
    SolvedInstancePlacement,
    SolverInstance,
    SolverMate,
)
from geometry.assembly.resolve import (
    ResolvableInstance,
    ResolvableMate,
    build_assembly_solve_input,
    resolve_mate_geometry,
)
from geometry.assembly.solver import RigidBodyAssemblySolver

__all__ = [
    "AssemblyDefinitionError",
    "AssemblyOverconstraintClass",
    "AssemblySolveDiagnosis",
    "AssemblySolveInput",
    "AssemblySolveMethod",
    "AssemblySolveResult",
    "AssemblySolveStatus",
    "AssemblySolver",
    "ResolvableInstance",
    "ResolvableMate",
    "ResolvedAxis",
    "ResolvedFace",
    "ResolvedMateGeometry",
    "RigidBodyAssemblySolver",
    "SolvedInstancePlacement",
    "SolverInstance",
    "SolverMate",
    "build_assembly_solve_input",
    "evaluate_assembly",
    "resolve_mate_geometry",
]
