"""Library thumbnails (LIBRARY-THUMBNAILS): the renderer, the cache and the routes.

What is pinned:

- a part renders to a 256x256 RGBA PNG with a transparent background and an
  opaque model in the middle, byte-identically on a re-render;
- the picture is a function of the tree: an edit changes it, the cache serves a
  repeat without re-rendering (``X-Loft-Artifact-Cache: hit``);
- a part with an errored feature is a 422 ``thumbnail_failed`` even though its
  evaluate still has a last-good body (never a picture of an older build), and a
  sketch-only part is ``thumbnail_empty``; neither is cached;
- an assembly and a drawing sheet render too.
"""

import uuid
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from geometry.api import compose_sheet
from geometry.main import app
from geometry.thumbnail import THUMBNAIL_PX, render_sheet
from geometry.thumbnail_store import configure_thumbnail_store, thumbnail_key
from loft_wire.drawings import ComposeDrawingRequest, ComposedSheet
from loft_wire.features import EvaluatedFeatureInput, EvaluateTreeRequest
from loft_wire.thumbnails import THUMBNAIL_EMPTY, THUMBNAIL_FAILED
from numpy.typing import NDArray
from PIL import Image

client = TestClient(app)
_JSON = {"content-type": "application/json"}

_TESTS = Path(__file__).resolve().parent
_ASSEMBLY = (
    _TESTS.parent / "goldens-assembly" / "assembly-two-plates-bolted" / "model.json"
)
_COMPOSE = _TESTS / "compose_goldens" / "request.json"
_CACHE = "X-Loft-Artifact-Cache"

_PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000a001")
_SKETCH = uuid.UUID("00000000-0000-0000-0000-00000000a002")
_EXTRUDE = uuid.UUID("00000000-0000-0000-0000-00000000a003")


@pytest.fixture(autouse=True)
def _cold_cache() -> Iterator[None]:
    configure_thumbnail_store(None, "loft-test")
    yield
    configure_thumbnail_store(None, "loft-test")


def _polygon(points: list[tuple[float, float]]) -> dict[str, Any]:
    count = len(points)
    return {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": f"l{index}",
                "kind": "line",
                "start": {"x": points[index][0], "y": points[index][1]},
                "end": {
                    "x": points[(index + 1) % count][0],
                    "y": points[(index + 1) % count][1],
                },
            }
            for index in range(count)
        ],
        "constraints": [],
    }


#: An L-shaped plate: 40 x 30 with a 30 x 20 notch.
_L = [(0.0, 0.0), (40.0, 0.0), (40.0, 10.0), (10.0, 10.0), (10.0, 30.0), (0.0, 30.0)]


def _tree(
    *,
    depth: float = 10.0,
    version: int = 1,
    profile: uuid.UUID = _SKETCH,
    with_extrude: bool = True,
) -> EvaluateTreeRequest:
    features = [
        EvaluatedFeatureInput.model_validate(
            {
                "id": _SKETCH,
                "feature": {"type": "sketch", "version": 1, "params": _polygon(_L)},
            }
        )
    ]
    if with_extrude:
        features.append(
            EvaluatedFeatureInput.model_validate(
                {
                    "id": _EXTRUDE,
                    "feature": {
                        "type": "extrude",
                        "version": 1,
                        "params": {
                            "profile": {"kind": "feature", "feature_id": str(profile)},
                            "distance_mm": depth,
                            "operation": "add",
                            "direction": "normal",
                            "merge": True,
                        },
                    },
                }
            )
        )
    return EvaluateTreeRequest(
        part_id=_PART_ID, tree_version=version, features=features
    )


def _png(body: bytes) -> NDArray[np.uint8]:
    image = Image.open(BytesIO(body))
    assert image.format == "PNG"
    assert image.size == (THUMBNAIL_PX, THUMBNAIL_PX)
    assert image.mode == "RGBA"
    return np.asarray(image)


def _post_part(request: EvaluateTreeRequest) -> Any:
    return client.post(
        "/api/v1/thumbnail/part", content=request.model_dump_json(), headers=_JSON
    )


def test_a_part_renders_an_isometric_png_on_a_transparent_tile() -> None:
    response = _post_part(_tree())
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    pixels = _png(response.content)
    alpha = pixels[..., 3]
    # Corners are background; the model fills the middle of the tile.
    assert alpha[0, 0] == alpha[0, -1] == alpha[-1, 0] == alpha[-1, -1] == 0
    assert (alpha > 200).mean() > 0.2
    # Three visible face orientations shade differently, and edges are drawn dark.
    opaque = pixels[alpha == 255][:, :3]
    assert len(np.unique(opaque.sum(axis=1) // 24)) >= 3
    assert opaque.min() < 80


def test_a_repeat_is_a_cache_hit_with_identical_bytes() -> None:
    first = _post_part(_tree())
    second = _post_part(_tree())
    assert first.headers[_CACHE] == "miss"
    assert second.headers[_CACHE] == "hit"
    assert first.content == second.content


def test_rendering_is_deterministic() -> None:
    first = _post_part(_tree()).content
    configure_thumbnail_store(None, "loft-test")
    assert _post_part(_tree()).content == first


def test_an_edit_changes_the_picture() -> None:
    thin = _post_part(_tree(depth=4.0, version=1))
    thick = _post_part(_tree(depth=40.0, version=2))
    assert thin.status_code == thick.status_code == 200
    assert thick.headers[_CACHE] == "miss"
    assert thin.content != thick.content


def test_the_key_folds_in_the_kind_and_the_whole_request() -> None:
    assert thumbnail_key("part", _tree()) == thumbnail_key("part", _tree())
    assert thumbnail_key("part", _tree()) != thumbnail_key("part", _tree(version=2))
    assert thumbnail_key("part", _tree()) != thumbnail_key("assembly", _tree())


def test_a_failed_part_has_no_picture_even_with_a_last_good_body() -> None:
    """An extrude of a sketch that does not exist errors; the request is a failure,
    not a picture of the last-good state, and nothing is cached."""
    broken = _tree(profile=uuid.UUID("00000000-0000-0000-0000-00000000dead"))
    response = _post_part(broken)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == THUMBNAIL_FAILED
    assert _post_part(broken).status_code == 422


def test_a_sketch_only_part_is_empty() -> None:
    response = _post_part(_tree(with_extrude=False))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == THUMBNAIL_EMPTY


def test_an_assembly_renders() -> None:
    response = client.post(
        "/api/v1/thumbnail/assembly",
        content=_ASSEMBLY.read_text(encoding="utf-8"),
        headers=_JSON,
    )
    assert response.status_code == 200, response.text
    assert (_png(response.content)[..., 3] > 200).mean() > 0.05


def test_a_drawing_sheet_renders_paper_and_ink() -> None:
    response = client.post(
        "/api/v1/thumbnail/drawing",
        content=_COMPOSE.read_text(encoding="utf-8"),
        headers=_JSON,
    )
    assert response.status_code == 200, response.text
    pixels = _png(response.content)
    opaque = pixels[pixels[..., 3] == 255][:, :3]
    assert (opaque.min(axis=1) > 240).mean() > 0.5  # mostly paper
    assert opaque.max(axis=1).min() < 80  # with dark view edges on it


def test_an_empty_sheet_is_still_paper() -> None:
    """The renderer itself draws a view-less sheet; the ROUTE refuses it as empty."""
    request = ComposeDrawingRequest.model_validate_json(_COMPOSE.read_text("utf-8"))
    sheet = compose_sheet(request)
    blank = ComposedSheet.model_validate({**sheet.model_dump(), "views": []})
    assert _png(render_sheet(blank))[..., 3].max() == 255
