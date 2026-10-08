"""Reading a ``.loft`` file with no server at all (docs/FILE-FORMAT.md).

``loft.open("bracket.loft")`` answers "what is in this file?" offline: the
manifest, the feature tree (with any imported STEP text inline again) and what
the reader noticed. It runs the SAME verified reader the gateway runs on an
upload (:func:`loft_wire.loft_file.read_loft`), so a file it accepts is a file
an import accepts, as far as the container goes. To turn the file into a part,
import it: ``session.open(path)``.
"""

from __future__ import annotations

import builtins
import os
from pathlib import Path

from loft_wire.loft_file import (
    MAX_LOFT_UPLOAD_BYTES,
    LoftArchive,
    LoftFileError,
    read_loft,
)

__all__ = ["LoftArchive", "LoftFileError", "open"]


def open(path: str | os.PathLike[str]) -> LoftArchive:
    """Read and verify a ``.loft`` file locally, or raise :class:`LoftFileError`.

    Nothing is sent anywhere and nothing is written. A file over the upload
    limit is refused before it is read into memory.
    """
    source = Path(path)
    if source.stat().st_size > MAX_LOFT_UPLOAD_BYTES:
        raise LoftFileError(
            f"The .loft is over the {MAX_LOFT_UPLOAD_BYTES}-byte upload limit.",
            code="loft_too_large",
            details={"max_bytes": MAX_LOFT_UPLOAD_BYTES},
        )
    with builtins.open(source, "rb") as handle:
        return read_loft(handle.read(MAX_LOFT_UPLOAD_BYTES + 1))
