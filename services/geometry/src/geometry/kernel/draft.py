"""Constant-angle face draft — taper picked faces about a neutral plane.

The kernel half of the draft feature (feature-tree design §4.3): the feature
layer hands in the current body (a service-internal :class:`Solid`), the resolved
set of faces to TAPER (from :func:`geometry.kernel.faces.resolve_faces` — the
SAME picked-FACE resolver shell uses, reusing the SAME stage-1 planar-face
signature, NOT a parallel taxonomy), the NEUTRAL PLANE (built from a principal
datum via :func:`geometry.kernel.build_datum_plane` — the plane that stays fixed,
whose normal is the PULL direction), and the validated draft angle. This module
owns only the OCCT/build123d draft call (build123d ``Solid.draft`` /
``BRepOffsetAPI_DraftAngle`` underneath). Failures raise the typed exception
below with a **sanitized message** (no kernel internals), which the feature layer
maps 1:1 onto the ``draft_failed`` ``FeatureError`` code so geometry outcomes
stay values at the boundary.

Draft tilts each picked face by ``angle_deg`` about its intersection with the
neutral plane (build123d ``Solid.draft`` derives the pull direction from
``neutral_plane.z_dir``). SIGN (measured 2026-07-13, build123d 0.11.1 / OCCT 7.9
— docs/GEOMETRY-QA.md): a POSITIVE angle tapers INWARD toward the pull direction
(the far/pull-normal end NARROWS — standard mold release); a NEGATIVE angle
tapers outward.

HONEST OCCT-DRAFT FINDING (measured 2026-07-13 — docs/GEOMETRY-QA.md, contrast
shell): an angle too large for the local geometry (the tapered faces collapse to
zero width / self-intersect) makes OCCT **RAISE** — a ``Standard_ConstructionError``
from ``BRepOffsetAPI_DraftAngle`` (or a ``StdFail_NotDone`` build123d re-raises as
``DraftAngleError``). Across a full angle sweep (inward AND outward, up to the
collapse) OCCT NEVER silently returned a bad/invalid body (every built result was
a valid single solid; every over-angle raised). So — UNLIKE shell, whose
too-thick path could silently return the un-hollowed body — draft needs NO
material-validity invariant guard: catching the raise (→ :class:`DraftError`) plus
the single-solid check is sufficient, never a silently wrong solid.

Determinism (RESEARCH §9): the OCCT draft is a pure function of
``(body, faces, neutral_plane, angle)``.
"""

from build123d import Compound, Face, Plane, Solid

from geometry.kernel.lumps import assemble_lumps, group_faces_by_lump
from geometry.kernel.types import BodyShape


class DraftError(RuntimeError):
    """The OCCT draft failed or produced an unsupported result.

    The kernel could not complete the taper (a ``Standard_ConstructionError`` /
    ``StdFail_NotDone`` from ``BRepOffsetAPI_DraftAngle`` — e.g. an angle too
    large for the geometry so the tapered faces collapse / self-intersect, or a
    face OCCT cannot draft), or the result was not exactly one solid. The feature
    layer maps this onto ``draft_failed`` — a legible "the draft could not be
    applied", never a silently wrong solid."""


def draft_body(
    body: BodyShape, faces: list[Face], neutral_plane: Plane, angle_deg: float
) -> BodyShape:
    """Taper *faces* of *body* by *angle_deg* about *neutral_plane*; LUMP-PRESERVING.

    *faces* is the resolved picked-face list (a non-empty list of kernel Faces —
    the empty case is a ``no_draft_faces`` decision the feature layer makes before
    calling here). *neutral_plane*'s normal is the pull direction (build123d
    derives it).

    Multi-body (§MB-4): a single :class:`~build123d.Solid` drafts exactly as
    before (byte-identical). A multi-lump :class:`~build123d.Compound` is drafted
    PER LUMP — OCCT's ``DraftAngle`` cannot run on a whole compound, so each lump
    that OWNS a picked face is tapered independently and the lumps with none pass
    straight through (unchanged), reassembling in the explicit lump order. The
    lump count is preserved by construction.

    Raises:
        DraftError: the OCCT draft failed to complete (an angle too large for the
            geometry, an undraftable face, …) or left other than exactly one
            solid per drafted lump (single body chain per lump, design §7.6).
    """
    if isinstance(body, Compound):
        solids = body.solids()
        groups = group_faces_by_lump(solids, faces)
        return assemble_lumps(
            [
                _draft_one_lump(solid, lump_faces, neutral_plane, angle_deg)
                if (lump_faces := groups.get(index))
                else solid
                for index, solid in enumerate(solids)
            ]
        )
    return _draft_one_lump(body, faces, neutral_plane, angle_deg)


def _draft_one_lump(
    body: Solid, faces: list[Face], neutral_plane: Plane, angle_deg: float
) -> Solid:
    """Taper the picked *faces* of ONE lump — the byte-identical single-body path.

    Shared by the single-solid fast path and each face-owning lump of the
    multi-lump path (§MB-4). Returns a new single cleaned solid; a lump with no
    picked face is passed through by :func:`draft_body` and never reaches here.
    """
    try:
        # draft() carries Shape[Unknown] type params upstream (the same gap
        # tessellate.py documents for export_gltf) — scoped ignore only.
        result = body.draft(faces, neutral_plane, angle_deg)  # pyright: ignore[reportUnknownMemberType]
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise DraftError(
            f"Draft failed in the kernel ({type(exc).__name__}); the angle "
            f"({angle_deg} deg) may be too large for these faces, or a face may "
            "be undraftable."
        ) from exc

    if len(solids) != 1:
        raise DraftError(
            f"Draft produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
        )
    # clean() removes redundant seam faces/edges the operation can leave behind,
    # keeping topology counts meaningful (and golden-assertable).
    return solids[0].clean()
