"""``/api/v1/thumbnail/*`` — library thumbnails (LIBRARY-THUMBNAILS).

Three stateless routes, one per document kind, each taking the SAME request the
kind's evaluate already takes (documents composes it; the gateway relays it):

- ``/thumbnail/part`` — an :class:`EvaluateTreeRequest`: evaluate (a rebuild-cache
  hit when the modeler just had the part open), then render its body mesh;
- ``/thumbnail/assembly`` — an :class:`EvaluateAssemblyRequest`: solve and render
  the one-file GLB with every placement baked in (the ``glb`` assembly export);
- ``/thumbnail/drawing`` — a :class:`ComposeDrawingRequest` for the first sheet:
  compose it and draw the sheet.

**A failure is a 422, never a picture.** A part whose tree has an errored feature
renders nothing — even though evaluate still has a last-good body — because a
library tile is a claim about the CURRENT document, and an older body would claim
a success that is not true (``thumbnail_failed``). Likewise an assembly with a
component that produced no body, and a sheet with a failed view. A document with
nothing to draw is ``thumbnail_empty``. The web shows its placeholder for both.

Every route is behind the admission gate (kernel work on a miss) and cached by the
content address of its inputs (:mod:`geometry.thumbnail_store`); failures are not
cached. ``X-Loft-Artifact-Cache`` says hit or miss, as the compose route does.
"""

from collections.abc import Callable

from fastapi import APIRouter, Response
from loft_wire.assemblies import EvaluateAssemblyRequest, ExportAssemblyRequest
from loft_wire.drawings import ComposeDrawingRequest
from loft_wire.features import EvaluateTreeRequest
from loft_wire.thumbnails import (
    THUMBNAIL_EMPTY,
    THUMBNAIL_FAILED,
    THUMBNAIL_MEDIA_TYPE,
    thumbnail_responses,
)
from py_kit.admission import ADMISSION_CONTROL
from py_kit.errors import ValidationApiError
from pydantic import BaseModel

from geometry.api import ARTIFACT_CACHE_HEADER, compose_sheet
from geometry.assembly import AssemblyExportError, export_assembly_reporting
from geometry.features import evaluate_tree
from geometry.kernel import MeshExportNotManifoldError, MeshExportTooDenseError
from geometry.mesh_store import fetch_mesh_glb
from geometry.thumbnail import ThumbnailError, render_glb, render_sheet
from geometry.thumbnail_store import fetch_thumbnail, store_thumbnail, thumbnail_key

router = APIRouter(prefix="/api/v1/thumbnail", tags=["thumbnails"])

_RESPONSES = thumbnail_responses(
    "A 256x256 PNG thumbnail on a transparent background. A document that fails "
    "to build is a 422 `thumbnail_failed` envelope and one with nothing to draw a "
    "422 `thumbnail_empty`: never a picture of an older build. Deterministic, and "
    "cached by the content address of the request (`X-Loft-Artifact-Cache`)."
)


def _failed(message: str) -> ValidationApiError:
    return ValidationApiError(message, code=THUMBNAIL_FAILED)


def _empty(message: str) -> ValidationApiError:
    return ValidationApiError(message, code=THUMBNAIL_EMPTY)


def _cached(kind: str, request: BaseModel, render: Callable[[], bytes]) -> Response:
    key = thumbnail_key(kind, request)
    png = fetch_thumbnail(key)
    status = "hit"
    if png is None:
        try:
            png = render()
        except ThumbnailError as exc:
            raise _empty(f"Nothing to draw: {exc}.") from exc
        store_thumbnail(key, png)
        status = "miss"
    return Response(
        content=png,
        media_type=THUMBNAIL_MEDIA_TYPE,
        headers={ARTIFACT_CACHE_HEADER: status},
    )


@router.post(
    "/part",
    response_class=Response,
    responses=_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def part_thumbnail(request: EvaluateTreeRequest) -> Response:
    """The isometric thumbnail of a part's current body."""

    def render() -> bytes:
        result = evaluate_tree(request).result
        if any(feature.status == "error" for feature in result.features):
            raise _failed("The part does not rebuild, so it has no thumbnail.")
        if result.mesh_glb_id is None:
            raise _empty("The part has no body yet.")
        glb = fetch_mesh_glb(result.mesh_glb_id)
        if glb is None:  # evicted between publish and read: a fault, not a picture
            raise _failed("The part's mesh was not available.")
        return render_glb(glb)

    return _cached("part", request, render)


@router.post(
    "/assembly",
    response_class=Response,
    responses=_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def assembly_thumbnail(request: EvaluateAssemblyRequest) -> Response:
    """The isometric thumbnail of an assembly at its solved placements."""

    def render() -> bytes:
        if not request.instances:
            raise _empty("The assembly has no components yet.")
        export = ExportAssemblyRequest.model_validate(
            {**request.model_dump(), "format": "glb"}
        )
        try:
            glb, omitted = export_assembly_reporting(export)
        except AssemblyExportError as exc:
            raise _failed(f"The assembly does not build: {exc}") from exc
        except (MeshExportNotManifoldError, MeshExportTooDenseError) as exc:
            raise _empty(f"The assembly is too large to draw: {exc}") from exc
        if omitted is not None:
            raise _failed("A component of the assembly does not rebuild.")
        return render_glb(glb)

    return _cached("assembly", request, render)


@router.post(
    "/drawing",
    response_class=Response,
    responses=_RESPONSES,
    dependencies=[ADMISSION_CONTROL],
)
def drawing_thumbnail(request: ComposeDrawingRequest) -> Response:
    """The thumbnail of a drawing sheet: paper, frame and the visible view edges."""

    def render() -> bytes:
        sheet = compose_sheet(request)
        if not sheet.views:
            raise _empty("The sheet has no views yet.")
        if any(view.failed for view in sheet.views):
            raise _failed("A view on the sheet could not be projected.")
        return render_sheet(sheet)

    return _cached("drawing", request, render)
