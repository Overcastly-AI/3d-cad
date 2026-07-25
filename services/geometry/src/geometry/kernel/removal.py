"""The ONE shared "does this removal actually remove anything?" predicate.

Every subtractive verb in this kernel asks the same question before (or instead
of) trusting a boolean cut: *can this tool reach the body at all?* Asked in three
places, answered by ONE function here (CLAUDE.md DRY rule — this was the same
predicate written once and missing twice, which is exactly how the
composition-matrix gate found three defects on 2026-07-25):

* :func:`geometry.kernel.mirror.mirror_cut` — a reflected removal that cannot
  reach the body means the user is COMPLETING a symmetric part, not mirroring a
  cut, so the mirror falls back to reflect-and-union (a documented, geometrically
  meaningful reading — GEOMETRY-QA 2026-07-25 / `fa30220`);
* :func:`geometry.kernel.pattern.linear_pattern_cut` /
  :func:`~geometry.kernel.pattern.circular_pattern_cut` — the same reading for the
  translated/rotated twin of that workflow (CM-2);
* :func:`geometry.kernel.extrude.combine_body` — an in-chain ``cut`` whose tool
  misses the body is the USER'S MISTAKE (a pocket sketched beside the part, a
  duplicated cut feature), so it is a typed error, never a silent ``ok`` (CM-3),
  exactly as the Hole feature has always reported ``hole_off_body``.

TOPOLOGICAL, NOT metric — no epsilon (CLAUDE.md forbids ad-hoc epsilons): the
question is answered by a boolean COMMON that yields at least one SOLID. A tool
that merely touches the body on a face (the exact clearing-plane case: a
reflected/translated copy sitting against the body's own boundary face) commons
to a face/shell, never a solid, and correctly reads as "does not reach". A tool
that shares any volume — however small — reads as "reaches", so a legitimate
grazing cut is never turned into an error by a tolerance choice.

Determinism (RESEARCH §9): a pure boolean probe on the given shapes in the given
order, with no state and no unordered iteration. It short-circuits on the first
tool that reaches, so the ordinary case (the seed copy of a patterned cut, the
one tool of a plain cut) costs a single probe.
"""
# pyright: reportUnknownMemberType=false

from collections.abc import Sequence

from geometry.kernel.types import BodyShape


def removal_reaches_body(body: BodyShape, tools: Sequence[BodyShape]) -> bool:
    """Does ANY *tools* member share VOLUME with *body* (i.e. remove material)?

    ``True`` as soon as one tool commons to a solid; ``False`` only when EVERY
    tool misses (or merely touches) the body, i.e. cutting them all would be a
    no-op. An empty *tools* sequence is ``False`` — nothing to remove.

    A probe that RAISES is answered ``True``: the callers all treat ``True`` as
    "keep the established path, which guards its own outcome", so an OCCT anomaly
    can never turn a previously-working feature into an error (the posture
    :func:`geometry.kernel.mirror.mirror_cut` shipped with in `fa30220`).
    """
    for tool in tools:
        try:
            # build123d types the boolean common as ShapeList[Unknown] | None (the
            # OCP wheel ships no stubs); the ignore is scoped to this one call.
            common = body.intersect(tool)  # pyright: ignore[reportUnknownVariableType]
        except Exception:  # OCCT failure modes are not a stable taxonomy
            return True
        if common is not None and common.solids():
            return True
    return False
