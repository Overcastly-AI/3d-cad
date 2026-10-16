"""An assembly, exported from a script (ASM-FAILED-PART-API).

    asm = session.assembly(assembly_id)
    asm.export("bike.step")

The export is the browser's: the gateway route the web's Export button calls,
fed the assembly's evaluation-ready graph exactly as documents serves it. A part
that fails to build has no body, so the file leaves its occurrences out (at any
depth, pattern copies included). The web says so with its Partial gate; a
script would otherwise get a short file with no signal at all, so the export
raises :class:`OmittedOccurrencesWarning` naming the parts, from the
``X-Loft-Omitted-Occurrences`` header geometry writes. A warning rather than an
error because the file is still the right file for what built, which is what
Fusion and SolidWorks write too: they export what has geometry and report the
rest.
"""

from __future__ import annotations

import os
import uuid
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from loft_wire.assemblies import (
    EvaluateAssemblyRequest,
    ExportAssemblyRequest,
)
from loft_wire.geometry import ExportFormat
from loft_wire.omitted_occurrences import (
    OMITTED_OCCURRENCES_HEADER,
    OmittedOccurrences,
    decode_omitted_header,
)

from loft import _operations as ops
from loft.part import EXPORT_SUFFIXES

if TYPE_CHECKING:
    from loft.session import Session

__all__ = ["Assembly", "OmittedOccurrencesWarning"]


class OmittedOccurrencesWarning(UserWarning):
    """An assembly export left out occurrences whose part produced no body.

    ``omitted`` is the decoded header: the total ``count`` and, per part, its
    name, typed code and how many occurrences the file lacks.
    """

    def __init__(self, message: str, omitted: OmittedOccurrences) -> None:
        super().__init__(message)
        self.omitted = omitted


def omitted_message(target: str, omitted: OmittedOccurrences) -> str:
    """The warning's sentence, e.g. "bike.step leaves out 2 occurrences whose
    part failed to build: Crank arm x2 (no_body)"."""
    named = [
        part.name
        + (f" x{part.occurrences}" if part.occurrences > 1 else "")
        + f" ({part.code})"
        for part in omitted.parts
    ]
    if not omitted.complete:
        named.append("more not listed")
    noun = "occurrence" if omitted.count == 1 else "occurrences"
    return (
        f"{target} leaves out {omitted.count} {noun} whose part failed to "
        f"build: {', '.join(named)}"
    )


class Assembly:
    """A handle to an existing assembly: (session, id), nothing fetched yet."""

    def __init__(self, session: Session, assembly_id: uuid.UUID) -> None:
        self.session = session
        self.id = assembly_id

    def __repr__(self) -> str:
        return f"Assembly(id={self.id})"

    def evaluation_request(self) -> EvaluateAssemblyRequest:
        """The assembly's graph, evaluation-ready, as geometry will solve it."""
        return self.session.transport.call(
            ops.GET_ASSEMBLIES_ASSEMBLY_ID_EVALUATION_REQUEST,
            EvaluateAssemblyRequest,
            path_params={"assembly_id": self.id},
        )

    def export_bytes(self, format: ExportFormat) -> bytes:
        """The exported file as bytes, as the browser downloads it.

        Warns (:class:`OmittedOccurrencesWarning`) when the file leaves out
        occurrences whose part failed to build.
        """
        return self._export(format, f"The {format} export")

    def _export(self, format: ExportFormat, target: str) -> bytes:
        graph = self.evaluation_request()
        exported = self.session.transport.call_file(
            ops.POST_GEOMETRY_ASSEMBLY_EXPORT,
            body=ExportAssemblyRequest(**graph.model_dump(), format=format),
        )
        header = exported.headers.get(OMITTED_OCCURRENCES_HEADER)
        if header is not None:
            omitted = decode_omitted_header(header)
            warnings.warn(
                OmittedOccurrencesWarning(omitted_message(target, omitted), omitted),
                # The script's own line: its export call, past this and the
                # public method.
                stacklevel=3,
            )
        return exported.content

    def export(
        self,
        path: str | os.PathLike[str],
        *,
        format: ExportFormat | None = None,
    ) -> Path:
        """Export to a file, inferring the format from the suffix (as a part)."""
        target = Path(path)
        resolved = format or EXPORT_SUFFIXES.get(target.suffix.lower())
        if resolved is None:
            raise ValueError(
                f"cannot infer an export format from {target.suffix!r}; pass "
                f"format= explicitly (one of {sorted(set(EXPORT_SUFFIXES.values()))})"
            )
        target.write_bytes(self._export(resolved, target.name))
        return target
