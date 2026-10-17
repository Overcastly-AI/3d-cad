"""Library thumbnails — the wire constants the geometry service, gateway and web share.

A thumbnail is a 256x256 PNG of a document (LIBRARY-THUMBNAILS): an isometric
render of a part or assembly, or the first sheet of a drawing. It is served as
bytes (``image/png``), so there is no response model; what crosses the wire as
a contract is the media type and the two refusal codes that mean "show the
placeholder instead", both 422 envelopes:

- :data:`THUMBNAIL_FAILED` — the document does not build (a feature errored, a
  component failed, a drawing view could not be projected). Never a picture of
  an older, successful build: a failed part has no thumbnail.
- :data:`THUMBNAIL_EMPTY` — the document builds to nothing to draw (a part with
  only a sketch, an assembly with no components, a sheet with no views).
"""

from typing import Any

THUMBNAIL_MEDIA_TYPE = "image/png"

#: The edge length of every thumbnail, pixels (square).
THUMBNAIL_SIZE_PX = 256

THUMBNAIL_FAILED = "thumbnail_failed"
THUMBNAIL_EMPTY = "thumbnail_empty"


def thumbnail_responses(
    description: str, *, revalidates: bool = False
) -> dict[int | str, dict[str, Any]]:
    """The OpenAPI ``responses`` block of a route that serves a thumbnail PNG.

    *revalidates* adds the ``304`` a conditional (``If-None-Match``) GET earns.
    """
    responses: dict[int | str, dict[str, Any]] = {
        200: {
            "content": {
                THUMBNAIL_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}
            },
            "description": description,
        },
    }
    if revalidates:
        responses[304] = {
            "description": "The thumbnail the caller holds (its `ETag`) is current."
        }
    return responses
