"""Boolean between two independently-built bodies (multi-body §Decisions-3).

The kernel half of the ``boolean`` feature (docs/design/multi-body.md §MB-1):
where :func:`geometry.kernel.extrude.combine_body` fuses a freshly-built tool
prism INTO the running body chain, this module fuses two whole BODIES the part
already holds — each built independently under MB-0's ``merge=False`` seam.

MB-1a wires ``union`` (OCCT ``BRepAlgoAPI_Fuse`` via build123d ``Solid.fuse``,
the same license-clean algorithm ``combine_body`` uses); ``subtract`` (``cut`` /
``BRepAlgoAPI_Cut``) and ``intersect`` (``BRepAlgoAPI_Common``) land in MB-2 —
the feature layer gates them to an honest ``boolean_not_implemented`` before
they reach here, so this module only implements union in this slice.

THE v1 SINGLE-CONNECTED-SOLID-PER-BODY INVARIANT (§Decisions-3, resolves the
code-review 🟢): the union result MUST be exactly one connected solid. OCCT
``fuse`` of two DISJOINT (non-touching) solids returns a compound of both
lumps — ``.solids()`` then has length 2 — which we reject as
:class:`BooleanDisjointError` (→ ``boolean_disjoint``). This guard is WHY a
part's ``EvaluationState.bodies`` values stay a single ``Solid`` (never a
``Compound``): a body is always one connected lump in v1. Multi-lump compound
bodies are deferred to MB-4.

Determinism (RESEARCH §9): ``fuse`` + ``clean`` are pure OCCT algorithms on
identical inputs and no iteration over an unordered container participates, so
the same two bodies fuse to a byte-identical result across interpreter restarts.
"""

from typing import Literal

from build123d import Solid

from geometry.kernel.extrude import BooleanError


class BooleanDisjointError(BooleanError):
    """A union whose operands do not touch → not one connected solid (§MB-1).

    Distinct from the generic :class:`BooleanError` so the feature layer maps it
    to the ``boolean_disjoint`` code (a real authoring limit in v1 — the bodies
    are genuinely two lumps; multi-lump compound bodies are MB-4), not the
    catch-all ``boolean_failed``.
    """


def boolean_bodies(
    target: Solid, tool: Solid, operation: Literal["union", "subtract", "intersect"]
) -> Solid:
    """Boolean two whole part bodies; return the new single connected solid.

    *target* is the surviving body, *tool* the consumed body (multi-body
    §Decisions-3). MB-1a implements ``union`` (fuse); ``subtract``/``intersect``
    are wired in MB-2 and are gated to ``boolean_not_implemented`` at the feature
    layer, so a non-union op cannot reach here in this slice — the guard below is
    defensive only.

    Raises:
        BooleanDisjointError: the union produced more than one solid — the
            operands do not touch (the single-connected-solid-per-body invariant,
            §Decisions-3).
        BooleanError: the kernel boolean raised, or produced no solid.
    """
    if operation != "union":
        # The feature layer returns ``boolean_not_implemented`` before calling
        # this, so this never fires in MB-1a; kept explicit so MB-2 fills the
        # subtract/intersect branches in one obvious place.
        raise NotImplementedError(
            f"boolean operation {operation!r} is wired in MB-2, not MB-1a"
        )

    try:
        # fuse carries Shape[Unknown] type params upstream (same gap combine_body
        # / tessellate.py document) — scoped ignore only.
        result = target.fuse(tool)  # pyright: ignore[reportUnknownMemberType]
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise BooleanError(
            f"Boolean union failed in the kernel ({type(exc).__name__}); "
            "the bodies may share only a degenerate contact."
        ) from exc

    if len(solids) == 0:
        # A union never removes material, so an empty result means OCCT produced
        # no valid solid — a kernel failure, not a disjoint pair.
        raise BooleanError("Boolean union produced no solid.")
    if len(solids) > 1:
        raise BooleanDisjointError(
            f"Boolean union produced {len(solids)} disjoint solids — the two "
            "bodies do not touch, so their union is not one connected solid. "
            "Position the bodies to overlap or abut (disjoint multi-lump bodies "
            "are not supported in v1)."
        )
    # clean() removes redundant seam faces/edges the fuse leaves at the former
    # body boundary, so topology counts stay meaningful (and golden-assertable) —
    # exactly as combine_body does for the in-chain boolean.
    return solids[0].clean()
