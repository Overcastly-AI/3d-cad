"""What an assembly export or drawing leaves out (ASM-FAILED-PART-API).

A part that fails to build has no body, so every assembly export writes only
the other occurrences, and no drawing view can draw them. Geometry folds those
occurrences by part (:class:`OmittedOccurrences`), returns the fold on the
assembly evaluate result, and names them on the export in the
``X-Loft-Omitted-Occurrences`` header. Pure pydantic.
"""

import json
from typing import Any

from pydantic import BaseModel, Field

from loft_wire.geometry import export_responses

#: Response header on ``POST /geometry/assembly/export`` naming the
#: occurrences the file LEAVES OUT because their part produced no body
#: (ASM-FAILED-PART-API). Absent when every occurrence is in the file. Its value
#: is :class:`OmittedOccurrences` as ASCII-only compact JSON
#: (:func:`encode_omitted_header`): every non-ASCII character of a part name is a
#: ``\uXXXX`` escape and every control character is escaped, so no part name
#: can break the header or smuggle a second one.
OMITTED_OCCURRENCES_HEADER = "X-Loft-Omitted-Occurrences"

#: Byte bound on the header's value. Proxies and HTTP clients cap a response's
#: header block (h11 at 16 KiB in all), so the per-part list is cut from the end
#: to fit and ``complete`` says so; ``count`` stays the true total.
MAX_OMITTED_HEADER_BYTES = 4096


class OmittedPart(BaseModel):
    """One PART that produced no body, folded over everywhere it occurs.

    The same fold the web's assembly Partial gate makes (``partFailures.ts``):
    one entry per part document, named as the user knows the part ("Crank arm",
    the instance's ``<n>`` stripped), counting its occurrences at any depth:
    directly, inside sub-assemblies, and as component-pattern copies.
    """

    name: str = Field(description='The part\'s name as the user knows it ("Crank arm")')
    part_document_id: str | None = Field(
        default=None,
        description="The part document (the `part_key` before `@`); null if unknown",
    )
    code: str = Field(description="The kernel's typed code (`no_body`, …)")
    message: str = Field(
        default="",
        description="The kernel's sentence. Empty in the export header, which "
        "carries only names, codes and counts.",
    )
    occurrences: int = Field(ge=1, description="Occurrences the file leaves out")


class OmittedOccurrences(BaseModel):
    """The occurrences an assembly's export or drawing leaves out, by part."""

    count: int = Field(ge=1, description="Total occurrences left out")
    parts: list[OmittedPart] = Field(
        description="One entry per part, in the order the solve first meets them"
    )
    complete: bool = Field(
        default=True,
        description="False when `parts` was cut to fit the header bound; "
        "`count` is still the total",
    )


def encode_omitted_header(omitted: OmittedOccurrences) -> str:
    """*omitted* as the ``X-Loft-Omitted-Occurrences`` value: ASCII JSON, bounded.

    ``ensure_ascii`` is what makes it header-safe: a header value is Latin-1 on
    the wire, so a raw "Kurbelarm ü" or "曲柄" would not encode at all, and JSON
    escapes CR/LF. Messages are dropped (a kernel sentence can be long);
    parts are cut from the end, flagging ``complete: false``, until it fits.
    """
    parts = [part.model_copy(update={"message": ""}) for part in omitted.parts]
    complete = True
    while True:
        value = json.dumps(
            OmittedOccurrences(
                count=omitted.count, parts=parts, complete=complete
            ).model_dump(mode="json", exclude={"parts": {"__all__": {"message"}}}),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        if len(value) <= MAX_OMITTED_HEADER_BYTES or not parts:
            return value
        parts = parts[:-1]
        complete = False


def decode_omitted_header(value: str) -> OmittedOccurrences:
    """The inverse of :func:`encode_omitted_header`."""
    return OmittedOccurrences.model_validate_json(value)


def assembly_export_responses(description: str) -> dict[int | str, dict[str, Any]]:
    """:func:`~loft_wire.geometry.export_responses` plus the omitted header.

    One block for the geometry route and the gateway proxy, so the contract
    declares ``X-Loft-Omitted-Occurrences`` on both (ASM-FAILED-PART-API).
    """
    responses = export_responses(description)
    responses[200]["headers"][OMITTED_OCCURRENCES_HEADER] = {
        "description": "Present only when the file leaves occurrences out "
        "because their part produced no body: `OmittedOccurrences` as "
        "ASCII-only compact JSON (non-ASCII as \\uXXXX escapes), at most "
        f"{MAX_OMITTED_HEADER_BYTES} bytes.",
        "schema": {"type": "string"},
    }
    return responses
