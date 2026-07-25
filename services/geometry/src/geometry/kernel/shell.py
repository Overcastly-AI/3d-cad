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
where two offset faces land on the same plane (a rib whose two walls exactly
meet, so the cavity pinches to zero width) OCCT leaves the smaller face's
corners sitting mid-edge on the larger one instead of splitting that edge. The
geometry is right and ``BRepCheck`` says invalid, and a STEP round-trip does not
preserve it (the reader sews and gains edges). Every shelled lump therefore goes
through :func:`~geometry.kernel.healing.conform_solid`, which no-ops on the valid
bodies (all goldens) and heals that one — see that module for the measured
evidence.

Determinism (RESEARCH §9): the OCCT hollow is a pure function of
``(body, faces, thickness)``; so is the heal (measured byte-identical over three
fresh builds, and idempotent).
"""

from build123d import Compound, Face, Solid

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
    """The wall thickness collapses / self-intersects the inward cavity.

    Raised when the hollow COMPLETES but the material-removed invariant fails
    (the walls merged and no cavity remains — OCCT's silent too-thick path). The
    feature layer maps this onto ``shell_thickness_too_large`` — a legible "the
    wall is too thick for this body", never a silently wrong solid."""


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
            path).
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
    # keeping topology counts meaningful (and golden-assertable). conform_solid()
    # then returns a VALID result untouched and heals the non-conformal
    # pinched-cavity case (CM-4, module docstring) — never a silent reshape: it
    # raises if the heal would move material.
    try:
        shelled = conform_solid(solids[0].clean())
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
