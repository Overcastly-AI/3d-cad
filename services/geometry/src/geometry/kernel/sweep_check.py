"""Refuse a swept solid that passes through itself (open and closed sweeps).

A sweep path that crosses itself (a figure eight), or comes back within the
section's reach of itself, sweeps into a solid whose faces intersect one
another. ``BRepCheck_Analyzer`` passes such a solid: it checks each face and
edge on its own. Its volume counts the crossing twice (a G1 figure eight of
two R20 lobes swept with r3 reads exactly pi r^2 L), and it would become the
part body and go out in STEP. ``BRepAlgoAPI_Check`` with the self-interference
test runs the boolean engine's face-face intersection on the one shape and
catches it, so every sweep is checked before it is cleaned and combined.

It does NOT see a spindle torus (a bend tighter than the section, an analytic
torus face folding through its axis), which is why the closed sweep keeps its
one-sided bend check. Cost measured 2026-10-09 per sweep: 0.5-28 ms on the
sweep goldens, 0.30 s and 0.51 s for the moto frame's two rail halves (0.8 s
of a 5.7 s rebuild); docs/RESEARCH.md §19.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false

from build123d import Solid
from OCP.BRepAlgoAPI import BRepAlgoAPI_Check


class SweepSelfIntersectingError(RuntimeError):
    """The swept solid passes through itself (its faces intersect)."""


def check_not_self_intersecting(solid: Solid) -> None:
    """Raise :class:`SweepSelfIntersectingError` if *solid* intersects itself.

    ``BRepAlgoAPI_Check(shape, bTestSE=True, bTestSI=True)``: small edges and
    self-interference, the checks the boolean engine runs on its arguments.
    """
    if not BRepAlgoAPI_Check(solid.wrapped, True, True).IsValid():
        raise SweepSelfIntersectingError(
            "The swept solid passes through itself: the path crosses itself or "
            "comes back within the profile's reach of itself. Move that part of "
            "the path further away, or shrink the profile."
        )
