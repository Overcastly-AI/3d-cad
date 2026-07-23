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

from build123d import Plane

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
