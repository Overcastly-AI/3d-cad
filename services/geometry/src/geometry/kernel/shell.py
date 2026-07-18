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

Determinism (RESEARCH §9): the OCCT hollow is a pure function of
``(body, faces, thickness)``.
"""

from build123d import Face, Solid

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


def shell_body(body: Solid, faces_to_remove: list[Face], thickness_mm: float) -> Solid:
    """Hollow *body* to a uniform inward *thickness_mm*, opening *faces_to_remove*.

    An empty *faces_to_remove* produces a sealed (fully-enclosed) hollow; a
    non-empty list leaves those faces open. Returns a new single solid.

    Raises:
        ShellThicknessError: the thickness collapses the cavity (the hollow
            completed but removed no material — OCCT's silent too-thick path).
        ShellError: the OCCT hollow failed to complete, or left other than
            exactly one solid (single body chain per part in v1, design §7.6).
    """
    if thickness_mm <= 0:
        raise ValueError(f"thickness_mm must be > 0, got {thickness_mm}")

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
    shelled = solids[0].clean()

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
