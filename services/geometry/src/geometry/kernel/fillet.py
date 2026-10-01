"""Constant-radius edge fillet — round selected edges of the body chain.

The kernel half of the fillet feature (feature-tree design §4.3): the feature
layer hands in the current body (a service-internal :class:`Solid`) plus the
resolved edge set (from :func:`geometry.kernel.edges.select_edges` — the shared
geometric edge-selection plumbing, design §2.4, NOT topological naming) and the
validated radius. This module owns only the OCCT/build123d fillet call. Failure
raises the typed exception below with a **sanitized message** (no kernel
internals), which the feature layer maps 1:1 onto the ``fillet_failed``
``FeatureError`` code so geometry outcomes stay values at the boundary.

Determinism (RESEARCH §9): the OCCT fillet is a pure function of
``(body, edges, radius)``.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

from build123d import Edge, Face, Solid
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.Standard import Standard_Failure
from OCP.StdFail import StdFail_NotDone
from OCP.TopoDS import TopoDS

from geometry.kernel.fillet_guard import (
    fillet_problem,
    max_tolerance,
)
from geometry.kernel.fillet_isolation import (
    BlendCrashed,
    BlendFailed,
    BlendTimedOut,
    needs_isolation,
    run_isolated,
    working_copy,
)
from geometry.kernel.healing import clean_shape
from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.naming import OpHistory
from geometry.kernel.reseam import reseam_near
from geometry.kernel.types import BodyShape


class FilletError(RuntimeError):
    """The OCCT fillet failed or produced an unsupported result (e.g. a radius
    too large for the local geometry, self-intersecting the body)."""


class FilletTimeoutError(FilletError):
    """The OCCT fillet ran past its CPU or wall-clock bound (an isolated blend,
    :mod:`geometry.kernel.fillet_isolation`) and was killed."""


def fillet_body(
    body: BodyShape,
    edges: list[Edge],
    radius_mm: float,
    *,
    history: OpHistory | None = None,
) -> BodyShape:
    """Round *edges* of *body* with a constant *radius_mm*; LUMP-COUNT-PRESERVING.

    *body* is a single :class:`~build123d.Solid` (the common case — byte-identical
    to before) OR a multi-lump :class:`~build123d.Compound` (§MB-4). OCCT's
    ``BRepFilletAPI`` fillets the named edges of whichever lumps own them and
    leaves the rest untouched, so a fillet on one lump of a k-lump body keeps all
    k lumps. A result whose lump count differs from the input is a merge/sever
    (unsupported) → :class:`FilletError`.

    *history*, when given, receives each edge paired with the fillet face(s) it
    generated (``BRepFilletAPI_MakeFillet::Generated``), for face naming
    (:mod:`geometry.kernel.naming`), and in ``worked_on`` the copy of *body*
    the result was built on (its untouched faces are that copy's).

    *body* is never modified: OCCT fillets in place, so each attempt runs on a
    copy, and a result is only accepted when it passes
    :func:`~geometry.kernel.fillet_guard.fillet_problem` (closed, no looser
    than it may be, faces beyond the fillet's reach intact).

    A blend outside OCCT's analytic cases runs in a forked child
    (:mod:`geometry.kernel.fillet_isolation`): OCCT can segfault there, and a
    crash must cost this fillet, not the service.

    Raises:
        FilletError: the OCCT fillet failed or crashed, or changed the body's
            lump count (a radius too large for an adjacent face — design §7.6 /
            §MB-4).
        FilletTimeoutError: the isolated blend ran past its time bound.
    """
    if radius_mm <= 0:
        raise ValueError(f"radius_mm must be > 0, got {radius_mm}")
    lump_count = len(body.solids())
    input_tolerance = max_tolerance(body)
    # OCCT fillets IN PLACE: a failed attempt can leave the input's vertices at
    # any tolerance (74 mm measured), so every attempt works on its own copy and
    # *body*, the caller's and the rebuild cache's, is never touched.
    isolate = needs_isolation(body, edges)
    try:
        work, work_edges, solids = _attempt(
            *working_copy(body, edges), radius_mm, history, isolate=isolate
        )
        problem = fillet_problem(work, work_edges, radius_mm, solids, input_tolerance)
        if problem is not None:
            raise _Rejected(problem)
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        if history is not None:
            history.generated.clear()
        if isinstance(exc, BlendTimedOut):
            raise _timed_out(radius_mm) from exc
        # A closed face's seam ending on or beside a filleted edge defeats the
        # OCCT blend (a parameterisation artefact, not geometry): retry ONCE on
        # a fresh copy of the untouched input with those seams moved clear
        # (geometry.kernel.reseam), under the same checks.
        moved = reseam_near(body, edges) if isinstance(body, Solid) else None
        try:
            if moved is None:
                raise exc
            work, work_edges, solids = _attempt(
                *moved, radius_mm, history, isolate=isolate
            )
            problem = fillet_problem(
                work, work_edges, radius_mm, solids, input_tolerance
            )
            if problem is not None:
                raise _Rejected(problem) from exc
        except Exception as retry_exc:  # OCCT failure modes are not a stable taxonomy
            if history is not None:
                history.generated.clear()
            if isinstance(retry_exc, BlendTimedOut):
                raise _timed_out(radius_mm) from retry_exc
            if isinstance(exc, BlendCrashed):
                raise FilletError(
                    "Fillet failed: the kernel crashed on this edge and face "
                    "configuration (it ran isolated, so nothing else was "
                    f"affected). Try another radius ({radius_mm} mm) or edge set."
                ) from exc
            if isinstance(exc, _Rejected):
                raise FilletError(
                    f"The fillet built a body Loft refuses: {exc}. The body is "
                    "left as it was."
                ) from exc
            cause = exc.args[0] if isinstance(exc, BlendFailed) else type(exc).__name__
            raise FilletError(
                f"Fillet failed in the kernel ({cause}); the radius "
                f"({radius_mm} mm) may be too large for an adjacent face."
            ) from exc
    if history is not None:
        # Report against the CALLER's edges (the names were taken on those),
        # and say which copy the result was built on (names re-anchor on it).
        back = {id(copy): edge for copy, edge in zip(work_edges, edges, strict=True)}
        history.generated = [
            (back.get(id(source), source), face) for source, face in history.generated
        ]
        history.worked_on = work

    if len(solids) != lump_count:
        raise FilletError(
            f"Fillet produced {len(solids)} lumps from a {lump_count}-lump body "
            "(it merged or severed a lump); the radius may be too large for an "
            "adjacent face (design §7.6 / §MB-4)."
        )
    # clean() removes redundant seam faces/edges the operation can leave behind,
    # keeping topology counts meaningful (and golden-assertable). k==1 returns a
    # bare cleaned Solid (byte-identical); a multi-lump body reassembles in the
    # explicit lump order (RESEARCH §9).
    if lump_count == 1:
        return clean_shape(solids[0])
    return assemble_lumps([clean_shape(solid) for solid in solids])


class _Rejected(RuntimeError):
    """The fillet built, but :func:`fillet_problem` found something wrong."""


def _timed_out(radius_mm: float) -> FilletTimeoutError:
    return FilletTimeoutError(
        f"Fillet stopped: the kernel ran past its time limit on this radius "
        f"({radius_mm} mm) and edge set."
    )


def _attempt(
    work: BodyShape,
    work_edges: list[Edge],
    radius_mm: float,
    history: OpHistory | None,
    *,
    isolate: bool,
) -> tuple[BodyShape, list[Edge], list[Solid]]:
    """One fillet of a working copy, in-process or isolated; returns the copy
    the result was built on, its edges and the result's solids."""
    if not isolate:
        return work, work_edges, _fillet(work, work_edges, radius_mm, history)
    return run_isolated("fillet", work, work_edges, radius_mm, history)


def _fillet(
    body: BodyShape, edges: list[Edge], radius_mm: float, history: OpHistory | None
) -> list[Solid]:
    """The OCCT fillet, as solids. Raises what it raises."""
    # fillet() carries Shape[Unknown] type params upstream (same gap
    # tessellate.py documents for export_gltf) — scoped ignore only.
    result = (
        body.fillet(radius_mm, edges)
        if history is None
        else _fillet_with_history(body, edges, radius_mm, history)
    )
    return list(result.solids())


def _fillet_with_history(
    body: BodyShape, edges: list[Edge], radius_mm: float, history: OpHistory
) -> BodyShape:
    """``Mixin3D.fillet`` (build123d 0.11), call for call, keeping the builder
    so its ``Generated`` history can be read. Raises what it raises."""
    builder = BRepFilletAPI_MakeFillet(body.wrapped)
    for edge in edges:
        builder.Add(radius_mm, edge.wrapped)
    try:
        result = Solid._make_3d_result(builder.Shape())  # pyright: ignore[reportPrivateUsage]
        if not result.is_valid:
            raise Standard_Failure
    except (StdFail_NotDone, Standard_Failure) as err:
        raise ValueError(
            f"Failed creating a fillet with radius of {radius_mm}"
        ) from err
    for edge in edges:
        for produced in builder.Generated(edge.wrapped):
            history.generated.append((edge, Face(TopoDS.Face_s(produced))))
    return result
