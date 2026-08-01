"""Geometry REST API (``/api/v1``) — thin, typed shell over the kernel layer.

Kernel code stays in :mod:`geometry.kernel`; this module only translates
between HTTP and DTOs. Endpoints are sync ``def`` on purpose: kernel work is
CPU-bound and runs on the threadpool, keeping the event loop free. The arq
queue path (``geometry.worker``) calls the same core function.

ADMISSION CONTROL (``dependencies=[ADMISSION_CONTROL]``, docs/PERF.md CONC-2).
"Keeping the event loop free" was never the constraint: OCP does not release
the GIL, so the threadpool gave concurrency in NAME only — a worker held at
1.05-1.15 cores with 1, 2, 4 and 8 requests in flight, and sixteen simultaneous
evaluates all finished within 0.4 s of each other at ~40 s. Every OCCT route
below therefore queues behind :class:`py_kit.admission.AdmissionGate`: at most
``ADMISSION_CONCURRENCY`` (default 1, the worker's real core count) inside at a
time, the rest FIFO, and an honest 503 + ``Retry-After`` past the bound instead
of admitting work that cannot finish.

THREE ROUTES ARE DELIBERATELY NOT GATED, and the exemptions are the interesting
part of the design:

* ``/meshes/{id}`` — an object-store read, not kernel work. Queueing a 3 ms
  artifact fetch behind a 40 s rebuild would make the *cheapest* thing in the
  product the slowest, and it consumes none of the resource the gate protects.
* ``/warm`` and ``/warm/cancel`` — they only enqueue onto the warm scheduler
  and return; the speculation itself runs on that scheduler's own bounded
  thread. Gating them would queue the *scheduling*, i.e. make a prefetch wait
  for the very rebuild it exists to get ahead of. (The warm's CPU still
  competes with admitted work — that is CONC-6, and it is the warm scheduler's
  bound to fix, not this one's.)
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Response
from py_kit.admission import ADMISSION_CONTROL
from py_kit.errors import NotFoundError, ValidationApiError

# Media types, filename rule, and the shared OpenAPI responses blocks live in
# py-kit (single source of truth, shared with the gateway proxy).
from py_kit.schemas.assemblies import (
    MAX_INTERFERENCE_INSTANCES,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    ExportAssemblyRequest,
    InterferenceResult,
    assembly_export_filename,
)
from py_kit.schemas.drawings import (
    ARTIFACT_MEDIA_TYPES,
    ComposeDrawingRequest,
    ComposedSheet,
    EvaluateAssemblyDrawingViewsRequest,
    EvaluateAssemblyDrawingViewsResult,
    EvaluateDrawingViewsRequest,
    EvaluateDrawingViewsResult,
    artifact_filename,
)
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    ExportTreeRequest,
    WarmCancelRequest,
    WarmTreeRequest,
    WarmTreeResult,
    export_tree_filename,
)
from py_kit.schemas.geometry import (
    EXPORT_MEDIA_TYPES,
    GLB_MEDIA_TYPE,
    PROPERTIES_HEADER,
    export_filename,
    export_responses,
    tessellate_responses,
)
from py_kit.schemas.measure import MeasureRequest, MeasureResult
from py_kit.schemas.overlay import OverlayRequest, OverlayResult
from py_kit.schemas.sketch import (
    Point2D,
    SketchChamferRequest,
    SketchCornerResult,
    SketchEditRequest,
    SketchEditResult,
    SketchEntity,
    SketchFilletRequest,
    SketchMirrorRequest,
    SketchMirrorResult,
    SketchOffsetRequest,
    SketchOffsetResult,
)
from py_kit.schemas.step_import import (
    StepAssemblyImportRequest,
    StepAssemblyImportResult,
)

from geometry.assembly import (
    AssemblyExportError,
    check_interference,
    evaluate_assembly,
    export_assembly,
    import_step_assembly,
)
from geometry.drawing_store import (
    drawing_artifact_key,
    fetch_drawing_artifact,
    store_drawing_artifact,
)
from geometry.drawings import (
    compose_drawing_evaluation,
    evaluate_assembly_drawing_views,
    evaluate_drawing_views,
    place_sheet,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
    thread_schedule_rows,
)
from geometry.faults import unexpected_query_failure
from geometry.features import evaluate_tree, tree_no_body_error
from geometry.kernel import (
    ImportNoSolidError,
    ImportParseError,
    ImportParseTimeoutError,
    ImportResponseTooLargeError,
    ImportTooManyProductsError,
    evaluate_export,
    evaluate_tessellation,
    export_solid,
)
from geometry.measure import evaluate_measure
from geometry.mesh_store import fetch_mesh_glb
from geometry.overlay import evaluate_overlay
from geometry.schemas import ExportRequest, TessellateRequest, TessellationMetadata
from geometry.sketch import (
    SketchEditError,
    chamfer_sketch,
    extend_sketch,
    fillet_sketch,
    mirror_sketch,
    offset_sketch,
    trim_sketch,
)
from geometry.warm import warm_scheduler, warm_work

router = APIRouter(prefix="/api/v1", tags=["geometry"])

_TESSELLATE_RESPONSES = tessellate_responses(
    "Binary glTF (GLB) mesh of the requested shape. The "
    f"`{PROPERTIES_HEADER}` header carries `TessellationMetadata` "
    "as compact JSON (see `POST /api/v1/tessellate/meta` for the "
    "same payload as a typed JSON body)."
)

_EXPORT_RESPONSES = export_responses(
    "The exported CAD file: STEP AP214 part 21 (`model/step`, exact B-rep) "
    "or binary STL (`model/stl`, faceted mesh). `Content-Disposition` "
    "carries the suggested download filename. Byte-deterministic: identical "
    "requests produce identical files."
)

_ASSEMBLY_EXPORT_RESPONSES = export_responses(
    "The exported assembly file: STEP AP214 part 21 (`model/step`, exact "
    "B-rep) with product structure — each instance a named PRODUCT at its "
    "solved world placement — or binary STL (`model/stl`, faceted mesh with "
    "placements baked into one compound). `Content-Disposition` carries the "
    "suggested download filename. Byte-deterministic: identical requests "
    "produce identical files."
)


@router.post(
    "/tessellate",
    response_class=Response,
    responses=_TESSELLATE_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def tessellate(request: TessellateRequest) -> Response:
    """Build a parametric shape, tessellate it, return the GLB mesh."""
    glb, metadata = evaluate_tessellation(request)
    return Response(
        content=glb,
        media_type=GLB_MEDIA_TYPE,
        headers={PROPERTIES_HEADER: metadata.model_dump_json()},
    )


@router.post(
    "/tessellate/meta",
    dependencies=[ADMISSION_CONTROL],
)
def tessellate_meta(request: TessellateRequest) -> TessellationMetadata:
    """JSON twin of ``/tessellate``: mass properties + mesh stats, no mesh."""
    _glb, metadata = evaluate_tessellation(request)
    return metadata


@router.post(
    "/evaluate",
    dependencies=[ADMISSION_CONTROL],
)
def evaluate(request: EvaluateTreeRequest) -> EvaluateTreeResult:
    """Evaluate an ordered feature-tree prefix (feature-tree design §4).

    Stateless: documents sends the full ordered, validated, current-version
    feature list (rollback bar already applied); the response is per-feature
    statuses plus object-storage artifact references, under the strict-prefix
    rule (§4.3 — first failure ``error``, the rest ``skipped``). A feature
    failure is a **200 with per-feature errors**; the py-kit error envelope
    stays reserved for transport/validation failures of this call itself.
    """
    return evaluate_tree(request).result


@router.post("/warm")
def warm(request: WarmTreeRequest) -> WarmTreeResult:
    """Speculatively cache a feature-tree prefix. **Publishes nothing.**

    The prefetch route (docs/PERF.md PERF-1b). It returns as soon as the work is
    QUEUED — the warm itself runs on the worker's single speculation thread — and
    its reply carries no geometry at all (:class:`WarmTreeResult`), because the
    one thing a speculative rebuild must never become is an answer. All it can do
    is leave an evaluator checkpoint under the ordinary content-addressed key, so
    a later *real* request that hashes to the identical prefix resumes there.

    Why it is safe to spend CPU on a guess:

    * **one warm per worker, ever** — :class:`~geometry.rebuild_cache.WarmScheduler`
      holds a single slot, so speculation costs at most one core no matter how
      many clients ask (the reason this is not "an evaluate nobody awaits", which
      would scale the DoS with the client count);
    * **a newer ticket supersedes an older one**, and ``POST /warm/cancel``
      retires one outright — both observed between features, so a warm stops
      within one OCCT call of the editor closing or the travel stop moving;
    * **a spent budget just means a shorter prefix**, which is still a legitimate
      resume point.

    Always a 200 with ``accepted``; a warm has no failure mode a caller could act
    on, since a miss is only ever slower.
    """
    accepted = warm_scheduler().submit(request.ticket, warm_work(request))
    return WarmTreeResult(ticket=request.ticket, accepted=accepted)


@router.post("/warm/cancel")
def warm_cancel(request: WarmCancelRequest) -> WarmTreeResult:
    """Retire a warm ticket (the editor closed, the drag ended, the tab left).

    Prefetch hides latency; it does not reduce work — so the intent going away
    must stop the speculation it funded rather than let it finish out of
    politeness. ``accepted=false`` simply means it had already finished or was
    never running.
    """
    return WarmTreeResult(
        ticket=request.ticket, accepted=warm_scheduler().cancel(request.ticket)
    )


@router.post(
    "/assembly/evaluate",
    dependencies=[ADMISSION_CONTROL],
)
def evaluate_assembly_route(
    request: EvaluateAssemblyRequest,
) -> EvaluateAssemblyResult:
    """Evaluate an assembly to solved placements + shared meshes (design §4).

    Stateless (CLAUDE.md): documents sends the assembly graph — each instance's
    part feature list + authored placement + the ordered mates — and geometry is
    the sole evaluator. Each UNIQUE part is evaluated + tessellated ONCE
    (content-addressed; two instances of a part share one mesh), the mate solver
    produces a solved world :class:`Placement` per instance, and the response
    carries per-instance ``{shared mesh id, solved placement}`` + an analytic
    combined mass-property roll-up. The SOLVED transform is applied at RENDER
    time (per-instance transform over the shared mesh), never baked into the GLB.

    A bad part / mate / solve is a **200 with a typed per-entry error or a
    non-``well_constrained`` status** (mirroring ``/evaluate``'s strict-prefix
    posture, §4.3); the py-kit envelope stays reserved for transport/validation
    failures of this call itself.
    """
    return evaluate_assembly(request)


@router.post(
    "/assembly/interference",
    dependencies=[ADMISSION_CONTROL],
)
def assembly_interference_route(
    request: EvaluateAssemblyRequest,
) -> InterferenceResult:
    """Detect interfering instance pairs in a solved assembly (design §4).

    Stateless (CLAUDE.md): documents sends the SAME assembly graph the evaluate
    route takes; geometry solves it through the identical pipeline
    (``solve_assembly`` — each unique part evaluated once, the mate graph solved
    to per-instance world placements), then runs a pairwise ``BRepAlgoAPI_Common``
    over the solved world-placed instance bodies. The response is the clash list
    ``[{instance_a, instance_b, overlap_volume_mm3}]`` (each unordered pair once,
    a merely-touching pair reported as NO clash) plus the solve's own status /
    diagnosis / per-mate errors. A non-overlapping assembly is ``clashes: []``.
    O(N²) over bodied instances (accepted v1 bound; broad-phase AABB pre-filter is
    the v2 follow-up).

    **Per-request work bound (audit G2):** because the scan is quadratic, this
    route enforces a TIGHTER instance ceiling than the parse-time
    ``MAX_ASSEMBLY_INSTANCES`` — ``MAX_INTERFERENCE_INSTANCES`` (~19,900
    pairwise exact booleans at the cap; the constant's rationale comment in
    :mod:`py_kit.schemas.assemblies` documents the N² math). Over the cap is a
    typed 422 ``interference_too_many_instances``, never an unbounded scan.
    Cross-field (route-specific, not a property of the shared request model),
    so it is a handler check rather than a Field constraint.

    A bad part / mate / solve is a **200 with a typed status / diagnosis and a
    (possibly empty) clash list** (mirroring ``/assembly/evaluate``'s never-500
    posture, §4.3); the py-kit envelope stays reserved for transport/validation
    failures of this call itself.
    """
    if len(request.instances) > MAX_INTERFERENCE_INSTANCES:
        raise ValidationApiError(
            f"Interference checking is limited to {MAX_INTERFERENCE_INSTANCES} "
            f"instances per request (the pairwise clash scan is quadratic in "
            f"instance count), got {len(request.instances)}.",
            code="interference_too_many_instances",
        )
    return check_interference(request)


@router.post(
    "/assembly/export",
    response_class=Response,
    responses=_ASSEMBLY_EXPORT_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def export_assembly_route(request: ExportAssemblyRequest) -> Response:
    """Evaluate an assembly and export it as ONE multi-instance STEP/STL download.

    Stateless (CLAUDE.md): documents sends the assembly graph (the SAME
    ``EvaluateAssemblyRequest`` fields the evaluate route takes, plus the export
    ``format``), geometry solves it through the identical pipeline
    (``solve_assembly`` — each unique part evaluated once, the mate graph solved
    to per-instance world placements), and composes every instance that produced
    a body into a single file. STEP writes **AP214 product structure**: each
    instance is a named PRODUCT at its solved placement, so a re-import recovers
    each part traceable to its instance; STL bakes the placements into one
    faceted compound. Deterministic (RESEARCH §9): the STEP timestamp is pinned
    and the per-occurrence ids canonicalised, so identical requests produce
    byte-identical files.

    An assembly where NO instance produced a body is a clean 422
    ``assembly_export_no_body`` envelope (never a zero-solid file or a 500,
    mirroring ``/export/tree``'s no-body posture, §4.3); a bad part/mate/solve is
    absorbed by the solve into a best-fit placement, not a failure. The py-kit
    error envelope stays reserved for transport/validation failures of this call.
    """
    try:
        data = export_assembly(request)
    except AssemblyExportError as exc:
        raise ValidationApiError(str(exc), code=exc.code) from exc
    return Response(
        content=data,
        media_type=EXPORT_MEDIA_TYPES[request.format],
        headers={
            "Content-Disposition": (
                f'attachment; filename="{assembly_export_filename(request)}"'
            )
        },
    )


@router.post(
    "/assembly/import",
    dependencies=[ADMISSION_CONTROL],
)
def import_assembly_route(
    request: StepAssemblyImportRequest,
) -> StepAssemblyImportResult:
    """Read an assembly STEP into its structured product list (BACKLOG P1, §4).

    Stateless (CLAUDE.md): the inverse of ``/assembly/export`` — geometry walks
    the file's AP214 XDE product tree (``STEPCAFControl_Reader`` →
    ``XCAFDoc_ShapeTool``) into N positioned, NAMED products, each surfaced by
    reference: a content-addressed shared presentation mesh + its own mass
    properties (no B-rep / kernel type crosses the boundary). ``has_assembly_
    structure`` is true when the file carried ``NEXT_ASSEMBLY_USAGE_OCCURRENCE``
    product structure; a flat / single-body STEP returns false with one product
    at identity, the backward-compatible signal to fall back to the single-body
    MB-4b import (slice 2 wires that + the documents assembly-document creation).
    Deterministic (RESEARCH §9): units pinned to mm, per-product meshes
    content-addressed.

    A malformed / bodyless / adversarial file is a clean 422
    (``import_parse_failed`` / ``import_no_solid`` / ``import_parse_timeout`` — the
    untrusted XCAF read runs under the SAME killable CPU/wall DoS bound as the
    single-body import, design §6), never a 500 — the same typed taxonomy the
    single-body import uses (design §5). The parse's OUTPUT is bounded too, against
    response amplification (slice-2b security review): ``import_too_many_products``
    (leaf-occurrence count over ``MAX_IMPORT_ASSEMBLY_PRODUCTS``, rejected inside
    the CPU-bounded child) and ``import_response_too_large`` (total emitted
    ``body_step`` bytes over ``MAX_IMPORT_RESPONSE_BYTES``, the absolute bound that
    also catches one large body instanced many times) — both clean 422s. The
    py-kit error envelope stays reserved for transport/validation failures of this
    call itself.
    """
    try:
        return import_step_assembly(request)
    except ImportTooManyProductsError as exc:
        raise ValidationApiError(str(exc), code="import_too_many_products") from exc
    except ImportResponseTooLargeError as exc:
        raise ValidationApiError(str(exc), code="import_response_too_large") from exc
    except ImportParseTimeoutError as exc:
        raise ValidationApiError(str(exc), code="import_parse_timeout") from exc
    except ImportNoSolidError as exc:
        raise ValidationApiError(str(exc), code="import_no_solid") from exc
    except ImportParseError as exc:
        raise ValidationApiError(str(exc), code="import_parse_failed") from exc


@router.post(
    "/drawing/evaluate",
    dependencies=[ADMISSION_CONTROL],
)
def evaluate_drawing_route(
    request: EvaluateDrawingViewsRequest,
) -> EvaluateDrawingViewsResult:
    """Project a part into its requested standard drawing views (design §1.2/§4).

    Stateless (CLAUDE.md): documents sends INTENT — the referenced part's ordered
    feature prefix + the requested standard views (front/top/right/iso) + scale —
    and geometry is the sole evaluator. The part body is evaluated ONCE (reusing
    ``evaluate_tree``), then exact HLR (``HLRBRep_Algo``) runs per requested view,
    yielding per-view canonically-ordered neutral 2D edges (visible = solid, hidden
    = dashed; a hole projects to a real circle a Ø dimension reads off, §1.1). No
    kernel/OCCT type crosses the boundary — the response is pure pydantic.

    A body-less part is a **200 with a whole-request ``part_error``** (empty
    ``views``); a per-view HLR failure is a **200 with that view's typed
    ``view_projection_failed`` error** (the other views still project) — mirroring
    ``/evaluate`` and ``/assembly/evaluate``'s never-500 posture (§1.5/§4.3). The
    py-kit error envelope stays reserved for transport/validation failures of this
    call itself. Identity-free: the gateway owns auth (same posture as
    ``/assembly/evaluate``). Sheet auto-layout, dimension measurement, and SVG
    export are later slices (design §7).
    """
    return evaluate_drawing_views(request)


@router.post(
    "/drawing/assembly/evaluate",
    dependencies=[ADMISSION_CONTROL],
)
def evaluate_assembly_drawing_route(
    request: EvaluateAssemblyDrawingViewsRequest,
) -> EvaluateAssemblyDrawingViewsResult:
    """Project a solved ASSEMBLY into its requested standard drawing views (§7).

    Stateless (CLAUDE.md): documents sends INTENT — the assembly graph (the SAME
    ``EvaluateAssemblyRequest`` the ``/assembly/evaluate`` route takes, reused
    VERBATIM) plus the standard views (front/top/right/iso) + scale — and geometry is
    the sole evaluator. The assembly is solved ONCE (``solve_assembly`` — each unique
    part evaluated once, the mate graph solved to per-instance world placements),
    every bodied instance is placed at its solved pose and composed into one compound,
    then exact HLR (``HLRBRep_Algo``) runs per requested view. The projected edges are
    the SAME neutral :class:`ProjectedViewEdge` shape a part view emits — hidden lines
    dashed exactly where one instance occludes another. No kernel/OCCT type crosses
    the boundary.

    A body-less assembly (no instance produced a body) is a **200 with a whole-request
    ``assembly_error``** (empty ``views``); a bodyless instance is a typed per-instance
    error (dropped, the rest still project); a per-view HLR failure that view's typed
    ``view_projection_failed``; a flat_pattern / section view kind a typed
    ``assembly_view_unsupported_projection`` — mirroring ``/drawing/evaluate`` and
    ``/assembly/evaluate``'s never-500 posture (§1.5/§4/§7). Identity-free: the gateway
    owns auth. BOM / balloons + the gateway/documents/web wiring are follow-up slices.
    """
    return evaluate_assembly_drawing_views(request)


#: Response header reporting whether the compose route served a stored artifact
#: (``hit``) or composed it fresh (``miss``) — the DE-4 cache signal. An internal
#: observability header (not part of the pydantic contract, not forwarded by the
#: gateway pass-through), so adding it is not a schema change.
ARTIFACT_CACHE_HEADER = "X-Loft-Artifact-Cache"

_COMPOSE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "The composed drawing artifact bytes (`image/svg+xml`, "
            "`application/pdf`, or `image/vnd.dxf` per `format`). "
            "`Content-Disposition` carries the suggested download filename. "
            "Byte-deterministic: identical requests produce identical bytes. "
            "`X-Loft-Artifact-Cache` reports `hit` (served from the "
            "content-addressed store) or `miss` (composed fresh)."
        ),
        "content": {
            media: {"schema": {"type": "string", "format": "binary"}}
            for media in ARTIFACT_MEDIA_TYPES.values()
        },
    }
}


def _compose_sheet(request: ComposeDrawingRequest) -> ComposedSheet:
    """The shared ``/drawing/compose`` + ``/drawing/compose/sheet`` pipeline.

    ``compose_drawing_evaluation`` picks the projected-geometry source (design §7,
    D4 slice a): a PART compose (``assembly is None``) delegates to
    ``evaluate_drawing_views`` VERBATIM (byte-identical to the pre-assembly
    contract); an ASSEMBLY compose projects the solved compound
    (``evaluate_assembly_drawing_views``) and folds its per-view results into the
    same envelope. Either way ``place_sheet`` consumes ONE result shape — an
    assembly view is placed exactly as a part view. Assembly-view dimensioning is
    out of v1, so an assembly compose places NO dimensions (the evaluation carries
    none; passing the request's authored inputs would desynchronise the strict
    input/measured pairing and 500 — never-500 posture instead: they are ignored).
    """
    evaluation = compose_drawing_evaluation(request)
    dimensions = request.dimensions if request.assembly is None else []
    # Tapped-hole callouts are DERIVED from the part's feature params on every
    # compose (BACKLOG #50) — never stored, so a re-tapped hole cannot leave a stale
    # thread on the next print. An ASSEMBLY compose has no single feature tree (its
    # inherited `features` is empty by contract), so it schedules nothing rather than
    # calling out a thread it cannot attribute to a part.
    threads = thread_schedule_rows(request.features) if request.assembly is None else []
    return place_sheet(
        evaluation,
        dimensions,
        request.layout,
        request.annotations,
        threads=threads,
    )


@router.post(
    "/drawing/compose",
    response_class=Response,
    responses=_COMPOSE_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def compose_drawing_route(request: ComposeDrawingRequest) -> Response:
    """Compose a drawing into a placed sheet + serialized artifact (design §4.2).

    Approach C's server-composed export: geometry OWNS drafting placement. Reuses
    ``evaluate_drawing_views`` VERBATIM for the projected geometry + measured values
    (no re-projection; an ASSEMBLY compose — ``request.assembly`` set — projects the
    solved compound via ``evaluate_assembly_drawing_views`` instead, design §7),
    places the sheet (``place_sheet`` — bounds-aware view
    anchoring, dimension lines/arrowheads/angular arcs, sibling-collision flip),
    then serializes to the requested ``format``: ``svg`` (dependency-free),
    ``pdf`` (reportlab base-14) or ``dxf`` (ezdxf, real model-space entities) — all
    deterministic. Identity-free — the gateway owns auth (same posture as
    ``/export``). Deterministic (RESEARCH §9): same request ⇒ identical bytes.

    **Content-addressed cache (DE-4, drawing-export.md §8.3).** The composed bytes
    are stored keyed on a content address of the WHOLE request
    (:func:`~geometry.drawing_store.drawing_artifact_key`), so a repeat export of an
    unchanged drawing is served byte-identically from storage WITHOUT re-composing
    (``X-Loft-Artifact-Cache: hit``). Any edit — views/dimensions/title-block/sheet
    or the ``format`` — changes the key, misses (``miss``), and recomposes; a stale
    artifact is never served. The store is a cache, not state: a miss just composes.
    """
    key = drawing_artifact_key(request)
    cached = fetch_drawing_artifact(key)
    if cached is not None:
        body = cached
        cache_status = "hit"
    else:
        composed = _compose_sheet(request)
        if request.format == "pdf":
            body = serialize_pdf(composed)
        elif request.format == "dxf":
            body = serialize_dxf(composed)
        else:
            body = serialize_svg(composed).encode("utf-8")
        store_drawing_artifact(key, body)
        cache_status = "miss"
    filename = artifact_filename(request.layout.title, request.format)
    return Response(
        content=body,
        media_type=ARTIFACT_MEDIA_TYPES[request.format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            ARTIFACT_CACHE_HEADER: cache_status,
        },
    )


@router.post(
    "/drawing/compose/sheet",
    dependencies=[ADMISSION_CONTROL],
)
def compose_sheet_route(request: ComposeDrawingRequest) -> ComposedSheet:
    """Compose a drawing into the placed ``ComposedSheet`` MODEL (design §4.2, DE-1b).

    The JSON-model sibling of ``/drawing/compose``: it runs the SAME pipeline
    (``evaluate_drawing_views`` VERBATIM → ``place_sheet``) but returns the placed
    :class:`ComposedSheet` as typed JSON instead of serializing it to
    ``svg``/``pdf``/``dxf`` bytes. This is the one placement source the DE-1c client
    cutover renders from, deleting the frontend's duplicate placement engine
    (``apps/web/src/drawing/{dimensions,layout}.ts``). A DEDICATED route (rather than
    a ``format=json`` branch on ``/compose``) keeps the bytes formats and the JSON
    model as separate OpenAPI operations with distinct response TYPES — codegen emits
    ``ComposedSheet`` + its nested unions cleanly instead of a bytes/JSON union. The
    request's ``format`` field is inert here (no serialization). Identity-free — the
    gateway owns auth. Deterministic (RESEARCH §9): same request ⇒ identical sheet.
    """
    return _compose_sheet(request)


_MESH_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {GLB_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        "description": (
            "Binary glTF (GLB) mesh addressed by an `EvaluateTreeResult."
            "mesh_glb_id` content hash (`sha256:<hex>`). 404 = evicted or "
            "unknown: re-evaluate the tree (results are pure functions of "
            "the request; feature-tree design §4.4/§7.8)."
        ),
    }
}


@router.get("/meshes/{mesh_glb_id}", response_class=Response, responses=_MESH_RESPONSES)
def fetch_mesh(mesh_glb_id: str) -> Response:
    """Fetch the GLB artifact a tree evaluation returned by content address.

    The interim §7.8 mesh-delivery path: `mesh_glb_id` is a pure content
    address, so this route keeps the same contract when the in-process store
    is replaced by object storage (docs/design/feature-tree.md §7.8).
    """
    glb = fetch_mesh_glb(mesh_glb_id)
    if glb is None:
        raise NotFoundError(
            "Mesh artifact unknown or evicted; re-evaluate the tree to regenerate it.",
            code="mesh_not_found",
        )
    return Response(content=glb, media_type=GLB_MEDIA_TYPE)


@router.post(
    "/export",
    response_class=Response,
    responses=_EXPORT_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def export(request: ExportRequest) -> Response:
    """Build a parametric shape and export it as a STEP or STL download."""
    data = evaluate_export(request)
    return Response(
        content=data,
        media_type=EXPORT_MEDIA_TYPES[request.format],
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(request)}"'
        },
    )


@router.post(
    "/measure",
    tags=["geometry"],
    dependencies=[ADMISSION_CONTROL],
)
def measure(request: MeasureRequest) -> MeasureResult:
    """Exact nearest distance between two transient measurement targets.

    **Stateless** (CLAUDE.md): a one-shot query, nothing persisted. Each
    target is either a POINT (explicit world coordinates — a picked
    vertex/snap point, exact on its own) or an EDGE (a transient 0-based index
    into the deterministic edge list of a body geometry recomputes from the
    supplied ``tree``). Distances come from the exact B-rep via OCCT, so every
    supported case — point-point, point-edge, edge-edge, straight OR curved —
    is EXACT; nothing is read from the tessellation. The response carries the
    minimum distance, its (dx, dy, dz) components, the two witness points, and
    (for two straight edges) the acute angle between them. See
    :mod:`py_kit.schemas.measure` for the full contract + fidelity rationale.

    A tree that recomputes to no body is a clean 422 ``tree_measure_failed``
    envelope; an out-of-range edge index is a 422 ``edge_index_out_of_range``.
    """
    return evaluate_measure(request)


@router.post(
    "/overlay",
    tags=["geometry"],
    dependencies=[ADMISSION_CONTROL],
)
def overlay(request: OverlayRequest) -> OverlayResult:
    """Pickable selection geometry of an evaluated feature tree's body (#6b).

    **Stateless** (CLAUDE.md): recomputes ``request.tree`` (the SAME ordered
    dispatch + strict-prefix rule as ``/evaluate`` and ``/measure``, reusing
    ``evaluate_tree``) and returns the last-good body's EXACT pickable geometry:
    ``vertices`` (world-mm snap points in ``body.vertices()`` order — echo one
    back as a measure ``PointTarget`` for an exact point measurement) and
    ``edges`` in ``body.edges()`` order — the SAME enumeration ``/measure``
    resolves ``EdgeTarget.index`` against, so ``edges[i]`` IS the edge
    ``EdgeTarget(index=i)`` measures. Each edge carries a kind tag, its two
    endpoint coordinates, and a polyline sampled at the tree's
    ``linear_deflection`` (the SAME tolerance the mesh uses — no new epsilon).

    Both index spaces are TRANSIENT — valid for this request/tree only, NOT
    stable across edits (stable named references are topological naming, Phase
    2). A tree that recomputes to no body is a clean 422 ``tree_overlay_failed``
    envelope. See :mod:`py_kit.schemas.overlay` for the full contract.
    """
    return evaluate_overlay(request)


_SketchEdit = Callable[[list[SketchEntity], str, Point2D], list[SketchEntity]]


def _run_sketch_edit(
    op: _SketchEdit, request: SketchEditRequest, *, action: str
) -> SketchEditResult:
    """Run a stateless trim/extend edit, mapping failures to 422 (never 500).

    A diagnosed edit failure (:class:`SketchEditError`) rides its legible code
    into the envelope; a raw analytic raise is sanitized to the belt-and-braces
    ``sketch_{action}_failed`` (same posture as measure/overlay,
    :mod:`geometry.faults`). Pure function of the request — deterministic.
    """
    try:
        entities = op(request.entities, request.target, request.pick)
    except SketchEditError as exc:
        raise ValidationApiError(str(exc), code=exc.code) from exc
    except Exception as exc:  # belt and braces — an edit is never a 500
        raise unexpected_query_failure(
            exc, code=f"sketch_{action}_failed", action=f"sketch {action}"
        ) from exc
    return SketchEditResult(entities=entities)


@router.post(
    "/sketch/trim",
    dependencies=[ADMISSION_CONTROL],
)
def sketch_trim(request: SketchEditRequest) -> SketchEditResult:
    """Trim a sketch curve at the pick, returning the rewritten entity list.

    **Stateless** (CLAUDE.md): a one-shot geometry edit, nothing persisted and
    no kernel type crosses the boundary. The target curve is cut at its nearest
    intersection with the other entities on each side of ``pick`` and the picked
    segment removed (Onshape/Fusion "cut at intersection"); an unbounded side
    runs to the curve end, and a curve with no intersection at all is deleted
    whole. Splits may add a second entity with a fresh deterministic id (see
    :class:`py_kit.schemas.sketch.SketchEditResult`). Deterministic (RESEARCH
    §9): identical input yields coordinate-identical output.

    Errors are 422s with legible codes, never 500s: ``sketch_target_not_found``
    (target id absent), ``sketch_unsupported_entity`` (a free-point target),
    ``sketch_pick_not_on_target`` (pick projects off the curve's extent).
    """
    return _run_sketch_edit(trim_sketch, request, action="trim")


@router.post(
    "/sketch/extend",
    dependencies=[ADMISSION_CONTROL],
)
def sketch_extend(request: SketchEditRequest) -> SketchEditResult:
    """Extend a sketch curve's picked end to the nearest neighbor it meets.

    **Stateless** (CLAUDE.md): the picked end (the endpoint nearer ``pick``)
    grows along the target's own supporting line/circle to the closest entity
    in that direction. Line and arc targets are supported; a circle or point
    has no free end (``sketch_unsupported_entity``). Deterministic (RESEARCH
    §9). Errors are 422s: ``sketch_target_not_found``,
    ``sketch_unsupported_entity``, ``sketch_extend_no_target`` (nothing to meet
    in the extension direction), ``sketch_degenerate_result``.
    """
    return _run_sketch_edit(extend_sketch, request, action="extend")


@router.post(
    "/sketch/offset",
    dependencies=[ADMISSION_CONTROL],
)
def sketch_offset(request: SketchOffsetRequest) -> SketchOffsetResult:
    """Offset a sketch curve — a parallel copy at a signed distance (rib/web).

    **Stateless** (CLAUDE.md): a one-shot geometry op, nothing persisted and no
    kernel type crosses the boundary. Unlike trim (which rewrites the target),
    offset **ADDS** geometry: the source is unchanged and the response carries
    only the NEW offset entity, with a fresh deterministic id ``f"{target}.{n}"``
    inheriting the source's construction flag. Sign convention: the copy is
    displaced along the curve's **left-hand normal** (forward direction rotated
    +90° CCW), so ``+distance`` = left of the directed curve; a CCW arc/circle's
    left normal points inward, so ``+distance`` shrinks its radius. Line / arc /
    circle are supported (single-entity v1; chain offset is deferred).
    Exact closed-form and deterministic (RESEARCH §9).

    Errors are 422s with legible codes, never 500s: ``sketch_target_not_found``,
    ``sketch_unsupported_entity`` (a free-point target),
    ``sketch_offset_zero_distance`` (zero/NaN/inf distance),
    ``sketch_degenerate_result`` (inward offset drives an arc/circle radius ≤ 0).
    """
    try:
        entities = offset_sketch(request.entities, request.target, request.distance)
    except SketchEditError as exc:
        raise ValidationApiError(str(exc), code=exc.code) from exc
    except Exception as exc:  # belt and braces — an edit is never a 500
        raise unexpected_query_failure(
            exc, code="sketch_offset_failed", action="sketch offset"
        ) from exc
    return SketchOffsetResult(entities=entities)


@router.post(
    "/sketch/mirror",
    dependencies=[ADMISSION_CONTROL],
)
def sketch_mirror(request: SketchMirrorRequest) -> SketchMirrorResult:
    """Mirror sketch curves — reflected copies about an axis line (symmetry).

    **Stateless** (CLAUDE.md): a one-shot geometry op, nothing persisted and no
    kernel type crosses the boundary. Like offset (and unlike trim), mirror
    **ADDS** geometry: the sources are unchanged and the response carries only
    the NEW reflected copies — one per ``target``, in order — each with a fresh
    deterministic id ``f"{source}.{n}"`` inheriting the source's construction
    flag. Every entity kind is reflectable; a mirrored **arc** is start/end-
    swapped to stay CCW (reflection reverses orientation). The axis is a line
    entity id or two points (see ``MirrorAxis``).

    Distinct from the ``symmetric`` CONSTRAINT: this CREATES geometry, it does
    not enforce symmetry, and v1 does NOT auto-add symmetric constraints between
    a source and its copy (geometry-only). Exact closed-form (rational foot-of-
    perpendicular) and deterministic (RESEARCH §9).

    Every entity kind (point, line, circle, arc) is reflectable, so there is no
    unsupported-target path. Errors are 422s with legible codes, never 500s:
    ``sketch_target_not_found`` (a target id — or a ``MirrorAxisEntity`` axis id
    — absent), ``sketch_mirror_axis_not_line`` (axis entity is not a line),
    ``sketch_mirror_degenerate_axis`` (zero-length axis).
    """
    try:
        entities = mirror_sketch(request.entities, request.targets, request.axis)
    except SketchEditError as exc:
        raise ValidationApiError(str(exc), code=exc.code) from exc
    except Exception as exc:  # belt and braces — an edit is never a 500
        raise unexpected_query_failure(
            exc, code="sketch_mirror_failed", action="sketch mirror"
        ) from exc
    return SketchMirrorResult(entities=entities)


@router.post(
    "/sketch/fillet",
    dependencies=[ADMISSION_CONTROL],
)
def sketch_fillet(request: SketchFilletRequest) -> SketchCornerResult:
    """Round a sketch corner between two lines with a tangent arc (BACKLOG #5).

    **Stateless** (CLAUDE.md): a one-shot geometry edit, nothing persisted and no
    kernel type crosses the boundary. The corner between lines ``a`` and ``b`` is
    replaced by a tangent arc of ``radius``: both lines are trimmed to their
    tangent points (ids preserved) and the arc is appended with a fresh
    deterministic id ``f"{a}.{n}"`` (see
    :class:`py_kit.schemas.sketch.SketchCornerResult`). Exact closed-form and
    deterministic (RESEARCH §9). **v1 is line-line only.**

    Errors are 422s with legible codes, never 500s: ``sketch_target_not_found``
    (a target id absent), ``sketch_unsupported_entity`` (a non-line target — a
    line-arc/arc-arc corner is deferred), ``sketch_corner_not_found`` (the lines
    are parallel/collinear or the same entity — no isolated corner),
    ``sketch_corner_too_large`` (radius exceeds a leg's available length),
    ``sketch_degenerate_result`` (a zero-length result).
    """
    try:
        entities = fillet_sketch(request.entities, request.a, request.b, request.radius)
    except SketchEditError as exc:
        raise ValidationApiError(str(exc), code=exc.code) from exc
    except Exception as exc:  # belt and braces — an edit is never a 500
        raise unexpected_query_failure(
            exc, code="sketch_fillet_failed", action="sketch fillet"
        ) from exc
    return SketchCornerResult(entities=entities)


@router.post(
    "/sketch/chamfer",
    dependencies=[ADMISSION_CONTROL],
)
def sketch_chamfer(request: SketchChamferRequest) -> SketchCornerResult:
    """Bevel a sketch corner between two lines with a straight line (BACKLOG #5).

    **Stateless** (CLAUDE.md): the corner between lines ``a`` and ``b`` is
    replaced by a straight chamfer line across two equal-setback points at
    ``distance`` along each leg: both lines are trimmed to those points (ids
    preserved) and the chamfer line is appended with a fresh deterministic id
    ``f"{a}.{n}"``. Same corner contract, result shape, and determinism as
    ``/sketch/fillet``. **v1 is line-line only.**

    Errors are the same 422 codes as fillet: ``sketch_target_not_found``,
    ``sketch_unsupported_entity``, ``sketch_corner_not_found``,
    ``sketch_corner_too_large`` (distance exceeds a leg's available length),
    ``sketch_degenerate_result``.
    """
    try:
        entities = chamfer_sketch(
            request.entities, request.a, request.b, request.distance
        )
    except SketchEditError as exc:
        raise ValidationApiError(str(exc), code=exc.code) from exc
    except Exception as exc:  # belt and braces — an edit is never a 500
        raise unexpected_query_failure(
            exc, code="sketch_chamfer_failed", action="sketch chamfer"
        ) from exc
    return SketchCornerResult(entities=entities)


@router.post(
    "/export/tree",
    response_class=Response,
    responses=_EXPORT_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def export_tree(request: ExportTreeRequest) -> Response:
    """Evaluate a feature tree and export its LAST-GOOD body as STEP/STL.

    Reuses the evaluate-tree machinery verbatim (``evaluate_tree`` — the same
    ordered dispatch + strict-prefix rule as ``POST /api/v1/evaluate``, no
    duplicated logic), then exports the resulting kernel body through the
    SAME format dispatch parametric shapes use (``export_solid``). A tree that
    produces no body — a strict-prefix failure or a body-less tree — is a
    clean 422 ``tree_export_failed`` envelope (never a 500, never a partial
    file); the failing ``FeatureError`` rides in the envelope details.
    Deterministic: the STEP timestamp is pinned exactly as on the shape path.
    """
    evaluation = evaluate_tree(request)
    if evaluation.body is None:
        raise tree_no_body_error(
            evaluation.result, code="tree_export_failed", action="export"
        )
    data = export_solid(
        evaluation.body,
        request.format,
        request.linear_deflection,
        request.angular_deflection,
        name=request.name,
    )
    return Response(
        content=data,
        media_type=EXPORT_MEDIA_TYPES[request.format],
        headers={
            "Content-Disposition": (
                f'attachment; filename="{export_tree_filename(request)}"'
            )
        },
    )
