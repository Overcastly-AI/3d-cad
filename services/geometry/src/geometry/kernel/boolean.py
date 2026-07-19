"""Boolean between two independently-built bodies (multi-body §Decisions-3).

The kernel half of the ``boolean`` feature (docs/design/multi-body.md §MB-1/§MB-2):
where :func:`geometry.kernel.extrude.combine_body` booleans a freshly-built tool
prism INTO the running body chain, this module booleans two whole BODIES the part
already holds — each built independently under MB-0's ``merge=False`` seam.

All three OCCT booleans are license-clean (OCCT is the kernel) and share the
build123d method surface ``combine_body`` already uses:

* ``union``     — ``Solid.fuse``      (``BRepAlgoAPI_Fuse``);
* ``subtract``  — ``Solid.cut``       (``BRepAlgoAPI_Cut``);
* ``intersect`` — ``Solid.intersect`` (``BRepAlgoAPI_Common``).

THE SINGLE-CONNECTED-SOLID DEFAULT (§Decisions-3, relaxed by §MB-4): by default
the result MUST be exactly one connected solid. ``result.solids()`` counts the
lumps OCCT produced:

* ``> 1`` solids → :class:`BooleanDisjointError` (→ ``boolean_disjoint``) UNLESS
  the caller opts in with ``allow_disjoint`` (§MB-4), in which case the >1 lumps
  are kept as ONE multi-lump body (a lump-sorted ``Compound``). The default error
  covers the common case where a union of non-touching bodies — or a
  subtract/intersect that leaves ≥2 disconnected pieces (a severing cut, a
  two-region intersect) — is a positioning bug, not an intent. When it IS the
  intent, ``allow_disjoint`` combines the lumps into one body: an
  ``EvaluationState.bodies`` value is then a ``Compound`` (§MB-4 widened the map
  from ``dict[UUID, Solid]`` to ``dict[UUID, BodyShape]``).
* ``0`` solids (or a ``None`` result — build123d returns ``None`` for an empty
  ``intersect``) → the material vanished. For ``subtract``/``intersect`` this is a
  MEANINGFUL empty result — the tool consumes the whole target, or the operands
  do not overlap — reported as :class:`BooleanEmptyError` (→ ``boolean_empty``),
  never a crash or a null body. For ``union`` (which never removes material) an
  empty result is instead a kernel failure (:class:`BooleanError`).

Determinism (RESEARCH §9): fuse/cut/common + ``clean`` are pure OCCT algorithms
on identical inputs and no iteration over an unordered container participates, so
the same two bodies boolean to a byte-identical result across interpreter
restarts.
"""

from typing import Literal

from build123d import ShapeList, Solid

from geometry.kernel.extrude import BooleanError
from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.types import BodyShape


class BooleanDisjointError(BooleanError):
    """A boolean whose result is >1 disconnected solid (§MB-1/§MB-2).

    A union of non-touching bodies, or a subtract/intersect that leaves ≥2
    disconnected pieces (a severing cut, a two-region intersect). Distinct from
    the generic :class:`BooleanError` so the feature layer maps it to the
    ``boolean_disjoint`` code — a real authoring limit in v1 (the result is
    genuinely multiple lumps; multi-lump compound bodies are MB-4), not the
    catch-all ``boolean_failed``.
    """


class BooleanEmptyError(BooleanError):
    """A subtract/intersect that produced no solid (§MB-2).

    The tool consumes the WHOLE target (an empty subtract), or the operands do
    not overlap (an empty intersect). A meaningful, honest empty result — mapped
    to the ``boolean_empty`` code — never a crash or a silently null body.
    Distinct from :class:`BooleanError` (a genuine kernel failure) and
    :class:`BooleanDisjointError` (a >1-solid result).
    """


def boolean_bodies(
    target: BodyShape,
    tool: BodyShape,
    operation: Literal["union", "subtract", "intersect"],
    *,
    allow_disjoint: bool = False,
) -> BodyShape:
    """Boolean two whole part bodies; return the new body (one or more lumps).

    *target* is the surviving body, *tool* the consumed body (multi-body
    §Decisions-3). ``union`` fuses, ``subtract`` cuts *tool* out of *target*, and
    ``intersect`` keeps their common volume — each an OCCT boolean via the
    build123d method surface, followed by a ``clean()`` per lump that removes the
    redundant seam faces/edges the boolean leaves at the former body boundary (so
    topology counts stay meaningful and golden-assertable — exactly as
    :func:`combine_body` does in-chain).

    By default the result MUST be exactly one connected solid; a >1-solid result
    is a :class:`BooleanDisjointError`. When *allow_disjoint* is set (the opt-in
    multi-lump path, §MB-4) a >1-solid result is instead accepted as ONE
    multi-lump body — a lump-sorted :class:`~build123d.Compound` (deterministic
    order, RESEARCH §9) — rather than raised. An EMPTY result is
    :class:`BooleanEmptyError` / :class:`BooleanError` regardless of the flag.

    Raises:
        BooleanDisjointError: the result is >1 disconnected solid and
            *allow_disjoint* is False — a union of non-touching bodies, or a
            subtract/intersect that leaves ≥2 pieces (the single-connected-solid
            invariant, §Decisions-3).
        BooleanEmptyError: a ``subtract``/``intersect`` produced no solid — the
            tool consumed the whole target, or the operands do not overlap.
        BooleanError: the kernel boolean raised, or a ``union`` produced no solid.
    """
    try:
        # fuse/cut/intersect carry Shape[Unknown] type params upstream (the same
        # gap combine_body / tessellate.py document); intersect returns a
        # ShapeList (or None for an empty common) rather than a Shape. Extract the
        # solid list per branch so the mixed return type never leaks — scoped
        # ignores only, exactly like combine_body.
        solids: list[Solid]
        if operation == "union":
            solids = list(target.fuse(tool).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        elif operation == "subtract":
            solids = list(target.cut(tool).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        else:  # intersect — the closed Literal's only remaining member
            # An empty intersect returns None (build123d); a non-empty one a
            # ShapeList whose .solids() is the lump list. Annotate so the mixed
            # partially-unknown return does not leak past this line.
            common: ShapeList[Solid] | None = target.intersect(tool)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            solids = list(common.solids()) if common is not None else []  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise BooleanError(
            f"Boolean {operation} failed in the kernel ({type(exc).__name__}); "
            "the bodies may share only a degenerate contact."
        ) from exc

    if len(solids) == 0:
        if operation == "union":
            # A union never removes material, so an empty result is a kernel
            # failure, not a meaningful empty.
            raise BooleanError("Boolean union produced no solid.")
        if operation == "subtract":
            raise BooleanEmptyError(
                "Boolean subtract removed the entire target body — nothing "
                "remains. The tool fully contains the target; nothing to keep."
            )
        raise BooleanEmptyError(
            "Boolean intersect produced no solid — the two bodies do not "
            "overlap, so their common volume is empty."
        )
    if len(solids) > 1:
        if allow_disjoint:
            # Opt-in multi-lump body (§MB-4): keep the >1 lumps as ONE body — a
            # lump-sorted Compound of the cleaned lumps (each lump's boolean seams
            # cleaned, then the explicit total order imposed for determinism).
            return assemble_lumps([solid.clean() for solid in solids])
        if operation == "subtract":
            detail = (
                f"severed the target into {len(solids)} disconnected pieces — the "
                "tool splits the target in two"
            )
        elif operation == "intersect":
            detail = (
                f"produced {len(solids)} disconnected pieces — the bodies meet in "
                "two separate regions"
            )
        else:
            detail = (
                f"produced {len(solids)} disjoint solids — the two bodies do not "
                "touch, so their union is not one connected solid"
            )
        raise BooleanDisjointError(
            f"Boolean {operation} {detail}. Set 'allow_disjoint' to keep the "
            "result as one multi-lump body (design §MB-4)."
        )
    return solids[0].clean()
