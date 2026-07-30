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
:func:`mirror_cut`): when the body carries a recorded cut whose REFLECTED tool
still reaches the body, the mirror reflects that REMOVAL (a hole on both sides) —
and the feature layer keeps that cut on record past intervening non-cut features,
because a mirror that forgets it ERASES the void (CM-1, 2026-07-25);
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
from geometry.kernel.removal import removal_reaches_body
from geometry.kernel.types import BodyShape


class MirrorError(RuntimeError):
    """The OCCT reflection or union failed, or produced no solid — a mirror
    never silently returns an empty/invalid body."""


class MirrorUnreachableError(MirrorError):
    """A reflected CUT tool cannot reach the body, so subtracting it would be a
    no-op.

    Two callers read this outcome differently, and the difference is the whole
    v1-vs-v2 story (docs/design/mirror-semantics.md §4.2):

    * :func:`mirror_cut` (the ``body`` scope) CATCHES it and falls back to
      :func:`mirror_union` — v1 had to guess which of two workflows the user meant,
      and "complete the symmetric half" is the right reading there;
    * :func:`mirror_tools_cut` (the ``features`` scope) lets it propagate, because
      an explicit selection has nothing to guess: a reflected cut that removes
      nothing means the wrong feature or the wrong plane was named, so the feature
      layer surfaces the typed ``mirror_feature_unreachable``. Explicit intent buys
      an honest error where implicit intent could only buy a fallback.
    """


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


def mirror_cut(body: BodyShape, tools: Sequence[Solid], plane: Plane) -> BodyShape:
    """Reflect the cut *tools* about *plane* and subtract them from *body*.

    The CUT-AWARE mirror (the reflective sibling of
    :func:`geometry.kernel.pattern.circular_pattern_cut`): when the body carries a
    recorded cut (an extrude-cut or a Hole, however many non-cut features sit
    between it and the mirror — CM-1), the mirror
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
    (:func:`geometry.kernel.removal.removal_reaches_body` — the SHARED predicate
    the patterned cut and the in-chain cut ask too) the feature falls back to
    :func:`mirror_union` — which is exactly right there, because the reflection of
    an ALREADY-CUT body carries its own pockets/holes: the result is the completed
    80 mm part with a pocket in each half (60000 mm^3), or two pocketed lumps for a
    clearing plane the body does not touch.

    The fallback is deliberately NOT the more "general" ``mirror_union`` +
    re-subtract of both tool sets: the union step FILLS every removal the
    reflection covers, while only the MOST RECENT cut's tools are known
    (:func:`geometry.features.evaluate._mirror_cut_tools`), so an EARLIER pocket on
    the same plate would be silently welded shut — trading one silent-wrong-body
    for a worse one (measured: 30400.0 for the union-then-recut "fix" where 29600.0
    is correct). Choosing the reading by reachability keeps every established
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
    reflected = reflect_tools(tools, plane)
    try:
        return cut_reflected_tools(body, reflected)
    except MirrorUnreachableError:
        # The mirrored removal cannot touch the body — cutting would be a no-op.
        # The user is completing/duplicating the body, not mirroring the cut.
        return mirror_union(body, plane)


def reflect_tools(tools: Sequence[BodyShape], plane: Plane) -> list[BodyShape]:
    """Reflect every tool about *plane* — the ONE reflection site both scopes use.

    ``Shape.mirror`` is the same exact handedness-reversing isometry
    :func:`mirror_union` applies to a whole body. Split out from the cut/fuse
    application so a ``features``-scope mirror can KEEP the reflected solids it
    applied: a nested (4-fold quadrant) mirror must reflect its inner mirror's tools
    AS PLACED, not the inner mirror's own sources — reflecting the sources again
    would re-fill the second quadrant and leave the fourth empty
    (docs/design/mirror-semantics.md §4.6).

    Raises:
        MirrorError: the OCCT reflection failed (a degenerate plane).
    """
    try:
        return [tool.mirror(plane) for tool in tools]
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise MirrorError(
            f"Mirror reflection of the tool failed in the kernel "
            f"({type(exc).__name__}); the mirror plane may be degenerate."
        ) from exc


def cut_reflected_tools(body: BodyShape, reflected: Sequence[BodyShape]) -> BodyShape:
    """Subtract already-:func:`reflect_tools`-ed solids from *body*, no fallback.

    The shared cut half of both mirror scopes, and the ONE difference between them
    is what happens when the reflected removal misses the body: this raises
    :class:`MirrorUnreachableError`, which :func:`mirror_cut` (``body`` scope)
    catches into :func:`mirror_union` and the ``features`` scope surfaces as the
    typed ``mirror_feature_unreachable`` (docs/design/mirror-semantics.md §4.2).
    Extracting it keeps ONE OCCT call sequence — the same reflection, the same
    reachability predicate, the same variadic ``body.cut``, the same ``clean()`` and
    the same guards — so the ``body`` path stays byte-identical to v1 (§6.1) rather
    than being re-expressed.

    The result must keep *body*'s LUMP COUNT (``k`` — 1 for the common single-body
    plate): a reflected hole cut interior to the body never severs or empties it.

    Raises:
        MirrorUnreachableError: no reflected tool can reach the body (the cut would
            remove nothing).
        MirrorError: the OCCT cut failed, removed the entire body, or changed the
            body's lump count.
    """
    lump_count = len(body.solids())
    if not removal_reaches_body(body, reflected):
        raise MirrorUnreachableError(
            "The mirrored removal lands entirely outside the body, so cutting it "
            "would remove nothing."
        )

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


def fuse_reflected_tools(body: BodyShape, reflected: Sequence[BodyShape]) -> BodyShape:
    """Fuse already-:func:`reflect_tools`-ed ADDITIVE solids into *body*.

    The additive half of the ``features`` scope (docs/design/mirror-semantics.md
    §4.1): the recorded tool of an additive verb — an extrude's prism, a revolve's
    solid, a swept/lofted solid, an imported body, a pattern's placements — is
    reflected and fused. UNLIKE :func:`cut_reflected_tools` there is NO lump-count
    invariant: a reflected additive tool that lands clear of the body legitimately
    makes a new disjoint lump (the §MB-0 case the ``2V`` goldens already assert), so
    the result is whatever lumps remain, in the deterministic
    :func:`assemble_lumps` order.

    Raises:
        MirrorError: the OCCT fuse failed, or produced no solid (never expected — a
            reflection of a solid is a solid).
    """
    try:
        fused = body.fuse(*reflected)
        solids = list(fused.clean().solids())
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise MirrorError(
            f"Mirror fuse of the reflected tool failed in the kernel "
            f"({type(exc).__name__}); the reflected tool may graze or "
            "self-intersect the body."
        ) from exc

    if not solids:
        raise MirrorError(
            "The mirrored add produced no solid — this is unexpected for a valid "
            "body and tool; check the mirror plane."
        )
    return assemble_lumps(solids)
