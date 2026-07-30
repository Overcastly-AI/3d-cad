"""Uniform-thickness shell — hollow the body, opening picked faces.

The kernel half of the shell feature (feature-tree design §4.3): the feature
layer hands in the current body (a service-internal :class:`Solid`), the
resolved set of faces to REMOVE (from :func:`geometry.kernel.faces.resolve_faces`
— the picked-FACE sibling of the edge selector, reusing the SAME stage-1
planar-face signature the ``on_face`` datum resolves, NOT a parallel taxonomy),
and the validated wall thickness. This module owns only the OCCT/build123d
hollow call. Failures raise the typed exceptions below with **sanitized
messages** (no kernel internals), which the feature layer maps 1:1 onto the
``shell_thickness_too_large`` / ``shell_failed`` ``FeatureError`` codes so
geometry outcomes stay values at the boundary.

The hollow is a UNIFORM INWARD offset (build123d ``Solid.hollow`` /
``BRepOffsetAPI_MakeThickSolid`` with a NEGATIVE thickness): the wall grows into
the solid, so the outer envelope is unchanged and the named faces are left open.
An empty ``faces_to_remove`` list produces a sealed (fully-enclosed) hollow.

HONEST OCCT-SHELL SUBTLETY (measured 2026-07-13, build123d 0.11.1 / OCCT 7.9 —
docs/GEOMETRY-QA.md): a thickness too large for the local wall geometry (the
inward cavity self-intersects / collapses) surfaces TWO ways, and this module
catches BOTH rather than shipping a wrong body:

* OCCT sometimes RAISES (``StdFail_NotDone``) — caught here as
  :class:`ShellError` → ``shell_failed`` (the belt-and-braces "kernel could not
  complete the offset" bucket, the fillet/chamfer precedent);
* OCCT sometimes SILENTLY returns the un-hollowed body (the walls merged, no
  material removed) — caught here by the MATERIAL-REMOVED invariant: a valid
  inward shell strictly reduces the volume, so a result whose volume is not
  below the original is a collapsed cavity → :class:`ShellThicknessError` →
  ``shell_thickness_too_large``. This invariant is the load-bearing guard: it
  is the ONLY thing standing between a too-thick shell and a silently wrong
  solid on the OCCT-returns-quietly path.

A THIRD mode (finding CM-4, docs/GEOMETRY-QA.md 2026-07-25): the hollow
completes, removes the right material, and returns a **non-conformal** solid —
OCCT leaves a face's corners sitting mid-edge on a neighbour instead of splitting
that edge. The geometry is right and ``BRepCheck`` says invalid, and a STEP
round-trip does not preserve it (the reader sews and gains edges). Every shelled
lump therefore goes through :func:`~geometry.kernel.healing.conform_solid`, which
no-ops on the valid bodies (all goldens) and heals that one — see that module for
the measured evidence.

A FOURTH mode, the one CM-4's heal made survivable rather than sound (finding
SH-1, docs/GEOMETRY-QA.md 2026-07-30): where an internal wall of the body is
**exactly 2 x the thickness**, the two inward offsets land on the SAME plane, the
cavity pinches to zero width, and the result carries a **zero-width slit** — two
coincident faces with no material between them. That is refused here, before the
heal, via the shared :func:`~geometry.kernel.degenerate.find_zero_width_slits`
predicate (see :class:`ShellThicknessError` for why it is an error and not a
success-with-warning).

Determinism (RESEARCH §9): the OCCT hollow is a pure function of
``(body, faces, thickness)``; so are the slit probe and the heal (measured
byte-identical over three fresh builds, and idempotent).
"""

from build123d import Compound, Face, Solid

from geometry.kernel.degenerate import find_zero_width_slits
from geometry.kernel.healing import HealingError, conform_solid
from geometry.kernel.lumps import assemble_lumps, group_faces_by_lump
from geometry.kernel.types import BodyShape

#: A valid inward shell strictly REMOVES material (the cavity), so the shelled
#: volume is below the original. The margin absorbs GProp float noise while
#: staying orders of magnitude below the material any non-degenerate wall
#: removes: the thinnest useful shell of an authored part removes a cavity of
#: whole mm^3, so a result within this margin of the original is a COLLAPSED
#: cavity (walls merged), never a genuine thin shell (mm-scale linear tolerance,
#: matching the kernel's 1e-7 m posture).
_MATERIAL_REMOVED_MARGIN_MM3 = 1e-6


class ShellError(RuntimeError):
    """The OCCT hollow failed to complete (belt-and-braces ``shell_failed``).

    The kernel could not build the offset (an ``StdFail_NotDone`` from
    ``MakeThickSolid``, or a result that is not exactly one solid). For too-large
    thicknesses OCCT raises this on the paths where it does not instead return a
    quietly-collapsed body — see :class:`ShellThicknessError` for that path."""


class ShellThicknessError(ValueError):
    """The wall thickness collapses, self-intersects, or PINCHES the inward cavity.

    Two measured causes, one user action ("change the thickness"), so one code:

    * the hollow COMPLETES but the material-removed invariant fails (the walls
      merged and no cavity remains — OCCT's silent too-thick path);
    * the hollow completes, removes the right material, and leaves a **zero-width
      slit** because an internal wall is exactly ``2 x thickness`` wide (SH-1,
      docs/GEOMETRY-QA.md 2026-07-30).

    The feature layer maps both onto ``shell_thickness_too_large`` — a legible "the
    wall is too thick for this body", never a silently wrong solid.

    WHY THE SLIT IS AN ERROR AND NOT A SUCCESS-WITH-WARNING (the P3-labelled
    honesty question, decided on measured evidence — GEOMETRY-QA SH-1):

    1. **At exactly 2 x t the hollow is unreliable in KIND, not just in topology.**
       Two bodies one fillet apart: the CM-4 body (r3 on the Z edges) returns the
       analytically CORRECT 6171.186 mm^3 with a 112 mm^2 slit, while the same
       chain without the fillet returns **14172.183 mm^3 where 6308.531 is
       correct** — 2.25x the material, only 227.8 of 8091.5 mm^3 of cavity cut.
       That second body is caught today only by luck (``ShapeFix`` happens to fail
       on it); the material-removed invariant passes it, because material WAS
       removed. A success we cannot tell apart from a 2.25x-too-heavy body is not
       a success.
    2. **We cannot make the body sound.** ``ShapeFix_Shape``, a self-fuse and
       ``ShapeUpgrade_UnifySameDomain`` all leave the coincident pair in place
       (measured — :mod:`geometry.kernel.degenerate`), so "succeed and heal" is not
       on the table; the choice is refuse or ship a cracked body.
    3. **The user loses nothing.** The knife edge is a single value: on the same
       CM-4 layout t=1.9 mm gives a sound 0.2 mm cavity (5901.709 mm^3) and
       t=2.1 mm gives a sound merged rib (6411.437 mm^3) — the two things the user
       could have meant. The message names both moves.

    A `warning` channel would be the better UX for case 3 (`ok` + advice) but
    ``FeatureResult`` has no such field, and inventing half of one — a warning
    smuggled into a success message the frontend does not model — is worse than an
    honest refusal. Filed instead (BACKLOG P3): a typed ``warnings`` list on
    ``FeatureResult`` plus a distinct ``shell_pinched_wall`` code, both py-kit
    schema changes owned outside the kernel. Until then this rides
    ``shell_thickness_too_large``, whose documented remedy ("reduce below the
    smallest half-wall") is exactly the boundary being hit."""


def shell_body(
    body: BodyShape, faces_to_remove: list[Face], thickness_mm: float
) -> BodyShape:
    """Hollow *body* to a uniform inward *thickness_mm*, opening *faces_to_remove*.

    An empty *faces_to_remove* produces a sealed (fully-enclosed) hollow; a
    non-empty list leaves those faces open.

    Multi-body (§MB-4): a single :class:`~build123d.Solid` hollows exactly as
    before (byte-identical). A multi-lump :class:`~build123d.Compound` is shelled
    PER LUMP — OCCT's ``MakeThickSolid`` cannot run on a whole compound, so each
    lump is hollowed independently (opening the picked faces that belong to it;
    lumps with no picked face become sealed hollows) and the results reassemble in
    the explicit lump order. Every lump is hollowed, so the lump count is
    preserved and the material-removed invariant is checked per lump.

    Raises:
        ShellThicknessError: the thickness collapses the cavity on some lump (the
            hollow completed but removed no material — OCCT's silent too-thick
            path), or PINCHES it to zero width on some lump (an internal wall
            exactly ``2 * thickness_mm`` wide, leaving coincident faces with no
            material between them — SH-1; see that class for why this is an error).
        ShellError: the OCCT hollow failed to complete, or left other than
            exactly one solid per lump (single body chain per lump, design §7.6).
    """
    if thickness_mm <= 0:
        raise ValueError(f"thickness_mm must be > 0, got {thickness_mm}")

    if isinstance(body, Compound):
        solids = body.solids()
        groups = group_faces_by_lump(solids, faces_to_remove)
        return assemble_lumps(
            [
                _shell_one_lump(solid, groups.get(index, []), thickness_mm)
                for index, solid in enumerate(solids)
            ]
        )
    return _shell_one_lump(body, faces_to_remove, thickness_mm)


def _shell_one_lump(
    body: Solid, faces_to_remove: list[Face], thickness_mm: float
) -> Solid:
    """Hollow ONE lump (a single solid) — the byte-identical single-body path.

    Shared by the single-solid fast path and each lump of the multi-lump path
    (§MB-4). Returns a new single cleaned solid; raises on the two too-thick
    modes (OCCT raise / silent no-op) exactly as the pre-multi-lump code did.
    """
    original_volume = body.volume
    try:
        # Negative thickness shells INWARD (the wall grows into the solid); the
        # faces list is removed (left open). hollow() carries Shape[Unknown]
        # type params upstream (the same gap tessellate.py documents for
        # export_gltf) — scoped ignore only.
        result = body.hollow(faces_to_remove, -thickness_mm)  # pyright: ignore[reportUnknownMemberType]
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise ShellError(
            f"Shell failed in the kernel ({type(exc).__name__}); the wall "
            f"thickness ({thickness_mm} mm) may be too large for this body."
        ) from exc

    if len(solids) != 1:
        raise ShellError(
            f"Shell produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
        )
    # clean() removes redundant seam faces/edges the operation can leave behind,
    # keeping topology counts meaningful (and golden-assertable).
    cleaned = solids[0].clean()

    # Zero-width-slit guard (SH-1), BEFORE the heal for two reasons: the heal
    # cannot remove a slit (measured - kernel/degenerate.py), so healing first
    # would only spend a ShapeFix on a body we refuse; and the probe then reports
    # what OCCT actually produced. Sub-millisecond on a sound body (0.33 ms on the
    # 6-face box, 0.56 ms on the 11-face golden tray, 2.0 ms on the 36-face CM-4
    # layout vs 58-82 ms for shell+heal): the antiparallel/coincident-plane test is
    # float arithmetic, and on a sound body no pair ever reaches the boolean.
    slits = find_zero_width_slits(cleaned)
    if slits:
        worst = slits[0]
        raise ShellThicknessError(
            f"Wall thickness {thickness_mm} mm leaves a zero-width slit: an "
            f"internal wall of this body is exactly {2 * thickness_mm} mm thick "
            f"(2 x the wall thickness), so the two inward offsets land on the same "
            f"plane and the cavity pinches to nothing over "
            f"{worst.area_mm2:.6g} mm^2 around (x {worst.at[0]:.6g}, "
            f"y {worst.at[1]:.6g}, z {worst.at[2]:.6g}): two coincident faces "
            f"with no material between them. Change the thickness so it is not "
            f"exactly half that wall - a little thinner leaves a thin cavity "
            f"there, a little thicker merges the two walls into solid material."
        )

    # conform_solid() returns a VALID result untouched and heals the non-conformal
    # T-junction case (CM-4, module docstring) — never a silent reshape: it raises
    # if the heal would move material.
    try:
        shelled = conform_solid(cleaned)
    except HealingError as exc:
        raise ShellError(
            f"Shell produced a body the kernel could not validate ({exc}); the "
            f"wall thickness ({thickness_mm} mm) may be too large for this body."
        ) from exc

    # Material-removed invariant: a valid inward shell strictly reduces the
    # volume. OCCT can quietly return the un-hollowed body when the thickness
    # collapses the cavity — catch that here rather than ship a wrong solid.
    if shelled.volume >= original_volume - _MATERIAL_REMOVED_MARGIN_MM3:
        raise ShellThicknessError(
            f"Wall thickness {thickness_mm} mm is too large: the inward cavity "
            "collapses (no material was removed). Reduce the thickness below the "
            "smallest half-wall of the body."
        )
    return shelled
