"""Assembly drawing projection — project a solved assembly to HLR 2D edges (§7).

The assembly analogue of :mod:`geometry.drawings.evaluate` (which projects a single
PART body). Where a part view runs exact HLR on one body, an assembly view projects
the UNION of every instance's body at its SOLVED world placement:

1. **Solve the assembly ONCE** via :func:`geometry.assembly.evaluate.solve_assembly`
   (reused VERBATIM — the SAME solve the ``/assembly/evaluate`` / interference /
   export paths call): each unique part evaluated once, the mate graph solved to a
   per-instance world :class:`~py_kit.schemas.assemblies.Placement`, each bodied
   instance paired with its resolved kernel body (``solved.placed``).
2. **Place every bodied instance** at its solved world pose through the shared
   :func:`geometry.kernel.export.place_body` transform (NOT reinvented — the SAME
   quaternion→``gp_Trsf`` the export/interference paths use) and **compose them into
   ONE compound** (:func:`compose_assembly_body`). A single-instance assembly stays
   the bare placed body, so it projects byte-identically to that part alone.
3. **Run the SAME exact HLR** (:func:`geometry.drawings.project.project_view`) per
   requested view on the compound → the assembly's canonically-ordered visible/hidden
   2D edges, where a hidden edge is correctly dashed exactly where one instance
   occludes another (HLR hides behind the nearest solid across the whole compound).

Error posture (design §4/§7, mirroring the part path + ``evaluate_assembly``): the
whole function is TOTAL — never raises for an evaluation outcome. A bodyless instance
is a typed :class:`~py_kit.schemas.assemblies.InstanceEvaluationError` (dropped from
the projection, the rest still project); an unresolvable mate a typed
``MateEvaluationError`` (from the reused solve); an HLR failure on one view that view's
typed ``view_projection_failed`` (the others still project); a flat_pattern / section
view kind (part-body only) a typed ``assembly_view_unsupported_projection``; and an
assembly where NO instance produced a body a whole-request ``assembly_error`` (empty
``views``). No kernel/OCCT type crosses the boundary — the response is pure pydantic.

Determinism (RESEARCH §9): the BLAS-pinned solve + fixed request-instance order + the
canonical HLR edge order (:func:`geometry.drawings.project.canonical_edges_repr`) yield
byte-identical projected edges for the same request, in-process and across a restart.
"""

from __future__ import annotations

from typing import cast

from build123d import Compound
from py_kit.schemas.assemblies import InstanceEvaluationError
from py_kit.schemas.drawings import (
    DrawingViewResult,
    EvaluateAssemblyDrawingViewsRequest,
    EvaluateAssemblyDrawingViewsResult,
)
from py_kit.schemas.features import FeatureError

from geometry.assembly.evaluate import PlacedInstance, solve_assembly
from geometry.assembly.transform import Pose
from geometry.drawings.evaluate import projected_edge_dto
from geometry.drawings.project import ViewDirection, ViewProjectionError, project_view
from geometry.kernel import place_body
from geometry.kernel.types import BodyShape

#: The standard orthographic + isometric view directions an assembly view supports
#: (the same quartet the part HLR path projects). ``flat_pattern`` / ``section`` are
#: single-part view kinds (an unfold / a planar cut of ONE body), so they are a typed
#: per-view error for an assembly view (§7) rather than a crash.
_STANDARD_VIEWS: frozenset[str] = frozenset({"front", "top", "right", "iso"})


def _world_body(placed: PlacedInstance) -> BodyShape:
    """A solved instance's part body copied to its SOLVED world placement.

    Decomposes the placement into a translation + unit quaternion via the same
    :class:`Pose` the solver / export / interference paths use, then positions the
    body through the shared kernel transform (:func:`geometry.kernel.place_body`), so
    no representation drift happens between solve, export, clash, and this drawing
    projection — the drawing is of exactly what the user would export / see.
    """
    pose = Pose.from_placement(placed.placement)
    return place_body(
        placed.body,
        (float(pose.t[0]), float(pose.t[1]), float(pose.t[2])),
        (float(pose.q[0]), float(pose.q[1]), float(pose.q[2]), float(pose.q[3])),
    )


def compose_assembly_body(placed: list[PlacedInstance]) -> BodyShape | None:
    """Compose every placed instance body into ONE body for HLR (design §7).

    Each bodied instance is copied to its solved world pose (:func:`_world_body`) and
    the results are gathered into a single :class:`~build123d.Compound` — the input
    exact HLR projects as a whole (occlusion resolved ACROSS instances). A single
    bodied instance is returned as the bare placed body (no wrapping compound), so a
    one-instance assembly projects byte-identically to that part alone (the consistency
    contract). ``None`` when no instance produced a body (nothing to project).
    """
    if not placed:
        return None
    bodies = [_world_body(p) for p in placed]
    if len(bodies) == 1:
        return bodies[0]
    return Compound(children=bodies)


def evaluate_assembly_drawing_views(
    request: EvaluateAssemblyDrawingViewsRequest,
) -> EvaluateAssemblyDrawingViewsResult:
    """Project a solved assembly into its requested standard drawing views (§7).

    Solves the assembly ONCE (``solve_assembly``), composes every bodied instance at
    its solved world placement into one compound, then runs exact HLR per requested
    view. Total — never raises for an evaluation outcome: a bodyless instance is a
    typed per-instance error (dropped, the rest still project); an unresolvable mate a
    typed per-mate error; a per-view HLR failure that view's typed
    ``view_projection_failed`` (the rest still project); a flat_pattern / section view
    a typed ``assembly_view_unsupported_projection``; and an assembly with NO bodied
    instance a whole-request ``assembly_error`` (empty ``views``). Deterministic
    (RESEARCH §9): byte-identical projected edges for the same request.
    """
    solved = solve_assembly(request.assembly)
    scale_value = request.scale.numerator / request.scale.denominator

    # Per-instance errors in deterministic request-instance order (solve_assembly's
    # instance_errors dict is insertion-ordered by request.instances, but iterate the
    # request explicitly so the order is provably request-order regardless of dict).
    instance_errors = [
        InstanceEvaluationError(instance_id=inst.instance_id, error=err)
        for inst in request.assembly.instances
        if (err := solved.instance_errors.get(inst.instance_id)) is not None
    ]

    body = compose_assembly_body(solved.placed)
    if body is None:
        # No instance produced a body — nothing to project (the assembly analogue of
        # the part `part_error`). Per-instance reasons ride `instance_errors`.
        return EvaluateAssemblyDrawingViewsResult(
            assembly_id=request.assembly.assembly_id,
            version=request.assembly.version,
            views=[],
            status=solved.status,
            diagnosis=solved.diagnosis,
            instance_errors=instance_errors,
            mate_errors=solved.mate_errors,
            assembly_error=FeatureError(
                code="no_body",
                message=(
                    "No instance in the assembly produced a body; there is nothing to "
                    "project. Check the instances' feature trees for errors."
                ),
            ),
        )

    views: list[DrawingViewResult] = []
    for view in request.views:
        if view not in _STANDARD_VIEWS:
            # flat_pattern / section are single-part view kinds (§7): an assembly view
            # supports the standard orthographic + iso quartet only. Typed per-view
            # error, never a crash (the never-500 contract).
            views.append(
                DrawingViewResult(
                    view=view,
                    scale=request.scale,
                    edges=[],
                    error=FeatureError(
                        code="assembly_view_unsupported_projection",
                        message=(
                            f"View kind '{view}' is a single-part projection "
                            "(flat_pattern / section) and is not supported for an "
                            "assembly view; use front / top / right / iso."
                        ),
                    ),
                )
            )
            continue
        try:
            projection = project_view(
                body, cast(ViewDirection, view), scale=scale_value
            )
        except ViewProjectionError as exc:
            views.append(
                DrawingViewResult(
                    view=view,
                    scale=request.scale,
                    edges=[],
                    error=FeatureError(code="view_projection_failed", message=str(exc)),
                )
            )
            continue
        views.append(
            DrawingViewResult(
                view=view,
                scale=request.scale,
                edges=[projected_edge_dto(e) for e in projection.edges],
                error=None,
            )
        )

    return EvaluateAssemblyDrawingViewsResult(
        assembly_id=request.assembly.assembly_id,
        version=request.assembly.version,
        views=views,
        status=solved.status,
        diagnosis=solved.diagnosis,
        instance_errors=instance_errors,
        mate_errors=solved.mate_errors,
        assembly_error=None,
    )
