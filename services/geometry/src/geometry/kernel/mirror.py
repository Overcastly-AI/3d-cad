"""Mirror — reflect the current body about a plane and union the reflection in.

The kernel half of the mirror feature (feature-tree design §4.3; a daily verb in
every incumbent, the reflective sibling of :mod:`geometry.kernel.pattern`).

v1 DESIGN DECISION (recorded in docs/GEOMETRY-QA.md): a mirror REFLECTS the
CURRENT evaluated body about a plane and BOOLEAN-UNIONS the reflection into the
body chain (design §7.6) — option (B), exactly the "replicate the current body +
union" semantics of the ADD pattern. The mirror plane is a world-space plane the
feature layer resolves from an origin datum (XY/XZ/YZ) or an earlier ``datum``
feature (the SAME plane reference a sketch / offset datum uses — no picked
sub-geometry, so like a pattern's world vectors it is independent of topological
naming, #1). A mirror is an EXACT rigid reflection + fuse, with no solid-delta
extraction.

The reflected copy is a true REFLECTION (a handedness-reversing isometry), NOT a
translation: build123d's ``Shape.mirror`` maps every point ``p`` to its image
across the plane, so a chiral body's mirror lands where no translation can put
it (proven by the ``mirror-triangle-prism-2x`` golden — its centroid sits ON the
mirror plane, which a translation of the same chiral profile cannot reproduce).

Two READINGS of "mirror", chosen by geometry rather than guessed (see
:func:`mirror_cut`): when the preceding feature is a cut whose REFLECTED tool
still reaches the body, the mirror reflects that REMOVAL (a hole on both sides);
when the reflected removal cannot reach the body — the "complete the symmetric
half" / "duplicate across a clearing plane" workflows — it reflects and unions
the BODY, which already carries its own pockets. Neither reading is ever a
silent no-op.

TWO honest outcomes, both valid (unlike a pattern, a mirror does NOT force a
single connected lump — the reflection of a body that clears the plane is a
legitimately DISJOINT second lump, and multi-body parts are supported, §MB-0):

* the body CLEARS the plane → the reflection is a disjoint copy → the union is a
  TWO-lump body of volume ``2V`` (the analytic disjoint case, the golden);
* the body STRADDLES / TOUCHES the plane → the reflection OVERLAPS the body →
  the union merges into ONE connected solid of the hand-computed union volume;
* the body is SYMMETRIC about the plane → the reflection COINCIDES with the body
  → the union is the body itself (volume ``V``, unchanged), the on-plane case
  handled sanely by ``clean()`` collapsing the coincident geometry.

Determinism (RESEARCH §9): the reflection is a pure OCCT isometry of the plane,
the fuse/clean are pure algorithms on identical inputs, and the resulting lumps
are ordered by :func:`geometry.kernel.lumps.assemble_lumps` (centroid, then
volume) — never OCCT's traversal order — so the same body + plane tessellate to
byte-identical bytes across interpreter restarts.
"""
# pyright: reportUnknownMemberType=false

from collections.abc import Sequence

from build123d import Plane, Solid

from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.types import BodyShape


class MirrorError(RuntimeError):
    """The OCCT reflection or union failed, or produced no solid — a mirror
    never silently returns an empty/invalid body."""


def mirror_union(body: BodyShape, plane: Plane) -> BodyShape:
    """Reflect *body* about *plane* and boolean-union the reflection into it.

    The reflection is placed by ``Shape.mirror`` (an exact handedness-reversing
    isometry of *plane*), fused onto *body*, and ``clean()``-ed so redundant
    seams from an overlapping/coincident reflection collapse and topology counts
    stay meaningful (and golden-assertable). The result is whatever lumps remain,
    assembled in the deterministic :func:`assemble_lumps` order:

    * a disjoint reflection (the body clears the plane) → a TWO-lump body (``2V``);
    * an overlapping reflection → ONE merged solid (the hand-computed union);
    * a symmetric body → the body itself, unchanged (``V``).

    Raises:
        MirrorError: the OCCT reflection/union failed, or the union produced no
            solid (never expected — a reflection of a solid is a solid).
    """
    try:
        reflected = body.mirror(plane)
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise MirrorError(
            f"Mirror reflection failed in the kernel ({type(exc).__name__}); the "
            "mirror plane may be degenerate."
        ) from exc

    try:
        fused = body.fuse(reflected)
        solids = list(fused.clean().solids())
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise MirrorError(
            f"Mirror union failed in the kernel ({type(exc).__name__}); the "
            "reflection may graze or self-intersect the body."
        ) from exc

    if not solids:
        raise MirrorError(
            "Mirror produced no solid — the reflected union is empty. This is "
            "unexpected for a valid body; check the mirror plane."
        )
    return assemble_lumps(solids)


def _reflected_tools_reach_body(body: BodyShape, reflected: Sequence[Solid]) -> bool:
    """Does any *reflected* removal tool share VOLUME with *body*?

    The discriminator between the two honest mirror readings (below). Purely
    TOPOLOGICAL — a boolean common that yields at least one SOLID — so it
    introduces no epsilon (CLAUDE.md): tools that merely touch the body on a face
    (the exact clearing-plane case, where the reflection sits against the mirror
    plane) common to a face/shell, never a solid, and correctly read as "does not
    reach". A probe that raises is answered ``True`` — i.e. keep the established
    cut path, which guards its own outcome — so an OCCT anomaly can never turn a
    previously-working mirror into an error.
    """
    for tool in reflected:
        try:
            # build123d types the boolean common as ShapeList[Unknown] | None (the
            # OCP wheel ships no stubs); the ignore is scoped to this one call.
            common = body.intersect(tool)  # pyright: ignore[reportUnknownVariableType]
        except Exception:  # OCCT failure modes are not a stable taxonomy
            return True
        if common is not None and common.solids():
            return True
    return False


def mirror_cut(body: BodyShape, tools: Sequence[Solid], plane: Plane) -> BodyShape:
    """Reflect the cut *tools* about *plane* and subtract them from *body*.

    The CUT-AWARE mirror (the reflective sibling of
    :func:`geometry.kernel.pattern.circular_pattern_cut`): when the mirror's
    immediately-preceding feature is a cut (an extrude-cut or a Hole), the mirror
    must reflect that removal — a plate with a hole on one side of the plane
    mirrors to a plate with a hole on BOTH sides — NOT reflect the whole filled
    body and union it (which would fill the original hole, betraying the #1 mirror
    use case). Each tool is reflected by ``Shape.mirror`` (the same exact
    handedness-reversing isometry :func:`mirror_union` uses) and cut from *body* in
    one variadic ``cut``, then ``clean()``-ed so the removed geometry's redundant
    seams collapse and topology counts stay meaningful (and golden-assertable).

    VACUOUS-CUT FALLBACK (the fix for a silent no-op, code review 2026-07-25).
    "Mirror the cut" is only the user's meaning when the reflected removal can
    actually reach the body. In the OTHER canonical mirror workflow — "complete
    the symmetric half" / "duplicate across a clearing plane": extrude-add a
    block, pocket it, then mirror about the block's own +X FACE — the reflected
    tool lands entirely OUTSIDE the body, ``body.cut(...)`` returns the body
    unchanged, and the mirror was a SILENT NO-OP (measured: a 40x40x20 block with
    a 10x20x10 pocket mirrored about x=40 stayed 30000 mm^3 at x in [0,40], every
    feature reporting ``ok``). So when the reflected tools do not reach the body
    (:func:`_reflected_tools_reach_body`) the feature falls back to
    :func:`mirror_union` — which is exactly right there, because the reflection of
    an ALREADY-CUT body carries its own pockets/holes: the result is the completed
    80 mm part with a pocket in each half (60000 mm^3), or two pocketed lumps for a
    clearing plane the body does not touch.

    The fallback is deliberately NOT the more "general" ``mirror_union`` +
    re-subtract of both tool sets: the union step FILLS every removal the
    reflection covers, and only the IMMEDIATELY-preceding cut's tools are known
    (:func:`geometry.features.evaluate._prev_cut_tools`), so an EARLIER pocket on
    the same plate would be silently welded shut — trading one silent-wrong-body
    for a worse one. Choosing the reading by reachability keeps every established
    case byte-identical (the overlapping midplane mirror still takes the cut path)
    and is regression-tested both ways.

    When the cut path IS taken the result must keep *body*'s LUMP COUNT (``k`` — 1
    for the common single-body plate): a reflected hole cut interior to the body
    never severs or empties it. A cut that removes the whole body, or splits a
    lump, is a :class:`MirrorError` (never a silently wrong body).

    Raises:
        MirrorError: the OCCT reflection/cut failed, removed the entire body, or
            changed the body's lump count.
    """
    lump_count = len(body.solids())
    try:
        reflected = [tool.mirror(plane) for tool in tools]
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise MirrorError(
            f"Mirror reflection of the cut tool failed in the kernel "
            f"({type(exc).__name__}); the mirror plane may be degenerate."
        ) from exc

    if not _reflected_tools_reach_body(body, reflected):
        # The mirrored removal cannot touch the body — cutting would be a no-op.
        # The user is completing/duplicating the body, not mirroring the cut.
        return mirror_union(body, plane)

    try:
        cut = body.cut(*reflected)
        solids = list(cut.clean().solids())
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise MirrorError(
            f"Mirror cut failed in the kernel ({type(exc).__name__}); a reflected "
            "tool may graze or self-intersect the body."
        ) from exc

    if not solids:
        raise MirrorError(
            "The mirrored cut removed the entire body — nothing remains. Check the "
            "mirror plane and the cut it reflects."
        )
    if len(solids) != lump_count:
        raise MirrorError(
            f"The mirrored cut changed the body from {lump_count} to {len(solids)} "
            "disjoint lumps — a reflected tool sliced a lump apart (design §7.6 / "
            "§MB-4)."
        )
    if lump_count == 1:
        return solids[0]
    return assemble_lumps(solids)
