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
the single-solid check is sufficient, never a silently wrong solid. That sweep
was not exhaustive: OCCT DOES return an invalid draft (the blade-root cap of a
blade-hub body drafted with the pull along Y, 2026-10-02), which reached the
evaluator's validity gate as ``invalid_body``. So the result is checked here:
valid (``BRepCheck``) and no looser than the input's loosest tolerance or the
fillet's 1e-2 mm floor, else a :class:`DraftError`.

INPUT UNTOUCHED (DRAFT-IN-PLACE, measured 2026-10-02): ``BRepOffsetAPI_DraftAngle``
writes to the body it drafts. On the blade-hub bodies every successful draft
(123 of 128) cleared the ``Checked`` flag of one or two input ``TShape`` objects;
no failure (178) touched the input, and geometry, tolerances, pcurves and
locations never changed. Cosmetic, and a later cut matched a cut on a fresh
build; but the input is the caller's and the rebuild cache's body, so the draft
runs on a working copy (:mod:`geometry.kernel.working_faces`), as the fillet does.

CRASH ISOLATION (DRAFT-SEGFAULT, 2026-10-02): OCCT can also SEGFAULT in
``BRepOffsetAPI_DraftAngle::Build``: a 30 deg draft of a hub's cylinder or cone
face beside a lofted blade, with the hub's seam at 180 deg (at 0 deg it raises).
So a draft outside the analytic cases runs in a forked child of the blend server
(:func:`draft_needs_isolation`, the fillet's rule applied to the edges of the
picked faces; :mod:`geometry.kernel.fillet_isolation`), and a crash is a typed
:class:`DraftError`. No analytic draft crashed in a sweep of plane, cylinder and
cone faces on hubs with box blades, bosses, bores and sphere caps (seams 0-180
deg, angles 3-60 deg), and isolating those too would add ~30 ms to every draft.

Determinism (RESEARCH §9): the OCCT draft is a pure function of
``(body, faces, neutral_plane, angle)``.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

from collections.abc import Sequence
from math import radians

from build123d import Compound, DraftAngleError, Face, GeomType, Plane, Solid
from OCP.BRep import BRep_Tool
from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle
from OCP.gp import gp_Dir, gp_Pln
from OCP.StdFail import StdFail_NotDone
from OCP.TopoDS import TopoDS

from geometry.kernel.fillet_guard import TOLERANCE_FLOOR_MM, max_tolerance
from geometry.kernel.fillet_isolation import (
    BlendCrashed,
    BlendFailed,
    BlendTimedOut,
    needs_isolation,
    run_isolated_draft,
)
from geometry.kernel.healing import clean_shape, new_geometry_is_valid
from geometry.kernel.lumps import assemble_lumps, group_faces_by_lump
from geometry.kernel.naming import OpHistory
from geometry.kernel.types import BodyShape
from geometry.kernel.working_faces import working_copy_faces


class DraftError(RuntimeError):
    """The OCCT draft failed or produced an unsupported result.

    The kernel could not complete the taper (a ``Standard_ConstructionError`` /
    ``StdFail_NotDone`` from ``BRepOffsetAPI_DraftAngle`` — e.g. an angle too
    large for the geometry so the tapered faces collapse / self-intersect, or a
    face OCCT cannot draft), or the result was not exactly one solid. The feature
    layer maps this onto ``draft_failed`` — a legible "the draft could not be
    applied", never a silently wrong solid."""


class DraftTimeoutError(DraftError):
    """The draft ran past its CPU or wall-clock bound in the blend server
    (:mod:`geometry.kernel.fillet_isolation`) and was killed."""


def draft_body(
    body: BodyShape,
    faces: list[Face],
    neutral_plane: Plane,
    angle_deg: float,
    *,
    history: OpHistory | None = None,
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

    *history*, when given, receives each picked face paired with the tilted face
    it became (``BRepOffsetAPI_DraftAngle::Modified``), for face naming
    (:mod:`geometry.kernel.naming`), and in ``worked_on`` the copy of *body*
    the result was built on (its untouched faces are that copy's).

    *body* is never modified: the draft runs on a working copy (module
    docstring), and its result must be valid and no looser than the input's
    loosest tolerance or 1e-2 mm.

    Raises:
        DraftError: the OCCT draft failed to complete (an angle too large for the
            geometry, an undraftable face, …), left other than exactly one
            solid per drafted lump (single body chain per lump, design §7.6), or
            built an invalid or loose solid.
    """
    # OCCT drafts IN PLACE (it rewrites flags of the input's TShapes on every
    # successful draft, kernel/working_faces.py): work on a copy, so *body*,
    # the caller's and the rebuild cache's, is never touched.
    ceiling = max(max_tolerance(body), TOLERANCE_FLOOR_MM)
    work, work_faces = working_copy_faces(body, faces)
    direction, plane = neutral_plane.z_dir.to_dir(), neutral_plane.wrapped
    try:
        _check_kinds(work_faces)
        if draft_needs_isolation(work, work_faces):
            work, work_faces, drafted = run_isolated_draft(
                work, work_faces, direction, plane, angle_deg, history
            )
        else:
            drafted = draft_lumps(
                work, work_faces, direction, plane, angle_deg, history
            )
        lumps = work.solids() if isinstance(work, Compound) else [work]
        finished = [
            lump if solids is None else _finish(lump, solids, ceiling)
            for lump, solids in zip(lumps, drafted, strict=True)
        ]
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        if history is not None:
            history.generated.clear()
        raise _draft_error(exc, angle_deg) from exc
    result: BodyShape = (
        assemble_lumps(finished) if isinstance(work, Compound) else finished[0]
    )
    if history is not None:
        # Report against the CALLER's faces (the names were taken on those),
        # and say which copy the result was built on (names re-anchor on it).
        back = {id(copy): face for copy, face in zip(work_faces, faces, strict=True)}
        history.generated = [
            (back.get(id(source), source), tilted)
            for source, tilted in history.generated
        ]
        history.worked_on = work
    return result


def draft_needs_isolation(body: BodyShape, faces: Sequence[Face]) -> bool:
    """Whether drafting *faces* of *body* leaves OCCT's analytic cases, so it
    runs in the blend server (:mod:`geometry.kernel.fillet_isolation`): the
    blend rule (:func:`~geometry.kernel.fillet_isolation.needs_isolation`)
    applied to every edge of every picked face. A draft rebuilds each picked
    face and re-intersects it with every face beside it, so it is analytic
    exactly when those edges are lines, circles or ellipses between planes,
    cylinders, cones and spheres. A degenerate edge (a cone's apex) has no
    curve and is skipped. DRAFT-SEGFAULT (a 30 deg draft of a hub face beside
    a lofted blade) is outside that class: its root edges are B-splines."""
    edges = [
        edge
        for face in faces
        for edge in face.edges()
        if not BRep_Tool.Degenerated_s(TopoDS.Edge_s(edge.wrapped))
    ]
    return needs_isolation(body, edges)


def draft_lumps(
    body: BodyShape,
    faces: Sequence[Face],
    direction: gp_Dir,
    plane: gp_Pln,
    angle_deg: float,
    history: OpHistory | None,
) -> list[list[Solid] | None]:
    """The raw OCCT draft, per lump of *body*: the solids of each lump that owns
    a picked face, ``None`` for a lump that owns none. Raises what OCCT raises.

    Run in-process, or in a child of the blend server for a draft outside the
    analytic cases (``_fillet_worker``): the same calls either way. The checks
    and the clean are the caller's (:func:`_finish`), in this process.
    """
    if isinstance(body, Compound):
        solids = body.solids()
        groups = group_faces_by_lump(solids, list(faces))
        return [
            _draft_solid(solid, lump_faces, direction, plane, angle_deg, history)
            if (lump_faces := groups.get(index))
            else None
            for index, solid in enumerate(solids)
        ]
    return [_draft_solid(body, faces, direction, plane, angle_deg, history)]


def _check_kinds(faces: Sequence[Face]) -> None:
    for face in faces:
        if face.geom_type not in {GeomType.PLANE, GeomType.CYLINDER, GeomType.CONE}:
            raise ValueError(
                f"Face {face} has unsupported geometry type {face.geom_type.name}."
            )


def _draft_solid(
    body: Solid,
    faces: Sequence[Face],
    direction: gp_Dir,
    plane: gp_Pln,
    angle_deg: float,
    history: OpHistory | None,
) -> list[Solid]:
    """``Solid.draft`` (build123d 0.11), call for call, keeping the builder so
    its ``Modified`` history can be read. Raises what it raises."""
    _check_kinds(faces)
    builder = BRepOffsetAPI_DraftAngle(body.wrapped)
    for face in faces:
        builder.Add(face.wrapped, direction, radians(angle_deg), plane, Flag=True)
        if not builder.AddDone():
            raise DraftAngleError("Draft could not be added to a face.")
    try:
        builder.Build()
        result = Solid(TopoDS.Solid_s(builder.Shape()))
    except StdFail_NotDone as err:
        raise DraftAngleError("Draft build failed on the given solid.") from err
    if history is not None:
        # ``ModifiedShape``, not ``Modified``: DraftAngle answers the
        # per-subshape query and returns an EMPTY ``Modified`` list (measured,
        # OCCT 7.9).
        for face in faces:
            produced = builder.ModifiedShape(face.wrapped)
            if not produced.IsNull():
                history.generated.append((face, Face(TopoDS.Face_s(produced))))
    return list(result.solids())


def _finish(lump: Solid, solids: Sequence[Solid], ceiling_mm: float) -> Solid:
    """The drafted *lump* (of the working copy) as a cleaned solid, after the
    checks: exactly one solid (design §7.6), valid (``BRepCheck`` of the faces
    the draft made, :func:`~geometry.kernel.healing.new_geometry_is_valid`) and
    no looser than *ceiling_mm*; else :class:`_Refused`."""
    if len(solids) != 1:
        raise _Refused(
            f"Draft produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
        )
    loosest = max_tolerance(solids[0])
    if loosest > ceiling_mm:
        raise _Refused(
            f"The draft built a body Loft refuses: a vertex or edge tolerance of "
            f"{loosest:.3g} mm, above the {ceiling_mm:.3g} mm a draft may leave. "
            "The body is left as it was."
        )
    if not new_geometry_is_valid(solids[0], [lump]):
        raise _Refused(
            "The draft built a body Loft refuses: OCCT reports it as an invalid "
            "solid. The body is left as it was."
        )
    # clean() removes redundant seam faces/edges the operation can leave behind,
    # keeping topology counts meaningful (and golden-assertable).
    return clean_shape(solids[0])


class _Refused(RuntimeError):
    """The draft built, but not a body Loft accepts (:func:`_finish`)."""


def _draft_error(exc: Exception, angle_deg: float) -> DraftError:
    """The typed, sanitized error for a failed draft."""
    if isinstance(exc, _Refused):
        return DraftError(str(exc))
    if isinstance(exc, BlendTimedOut):
        return DraftTimeoutError(
            f"Draft stopped: the kernel ran past its time limit on this angle "
            f"({angle_deg} deg) and face set."
        )
    if isinstance(exc, BlendCrashed):
        return DraftError(
            "Draft failed: the kernel crashed on this face configuration (it ran "
            "isolated, so nothing else was affected). Try another angle "
            f"({angle_deg} deg) or face set."
        )
    cause = exc.args[0] if isinstance(exc, BlendFailed) else type(exc).__name__
    return DraftError(
        f"Draft failed in the kernel ({cause}); the angle ({angle_deg} deg) may "
        "be too large for these faces, or a face may be undraftable."
    )
