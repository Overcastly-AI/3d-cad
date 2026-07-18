"""Out-of-process STEP parse — the hard wall-clock KILL boundary (design §6).

Run as ``python -m geometry.kernel._step_parse_worker <in_path> <out_path>``. The
parent (:func:`geometry.kernel.imports.import_step_solid`) spawns this with a
``subprocess.run(..., timeout=...)`` bound so a degenerate/adversarial part-21
whose OCCT transfer is super-linear can be **SIGKILLed and reaped**, never
pinning a FastAPI threadpool worker (BACKLOG P1, docs/design/step-import.md §6).

This module imports **only OCP** — never build123d — on purpose: build123d's
import graph adds ~2.5 s of cold-start to every spawn, while the raw OCCT
reader/writer is ~0.85 s. The untrusted work done here is exactly the two
unbounded-time OCCT calls (``ReadFile`` → ``TransferRoots``); everything
legible — the null / single-solid taxonomy — stays in the parent where it is
tested and can use build123d.

The result crosses the process boundary as a BREP file (OCCT's native, lossless
serialization): the parent reads it back and runs the topology checks. Units are
pinned to millimetres HERE, in the fresh process, so the read is independent of
any ambient ``Interface_Static`` state — the determinism guarantee is actually
stronger than the in-process path it replaces (RESEARCH §9).

Exit codes are the protocol: ``0`` = a shape (possibly null / a compound) was
written; :data:`EXIT_PARSE_FAILED` = OCCT could not read or transfer the bytes.
A SIGKILL (timeout) or any other nonzero exit is treated by the parent as a
parse failure / timeout — a crash in untrusted parsing is never a 500.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import sys

#: Exit code when OCCT cannot read/transfer the payload (→ ``ImportParseError``).
#: Distinct from 0 (wrote a shape) and from a SIGKILL/other crash (the parent
#: maps any non-zero, non-timeout exit to a parse failure regardless).
EXIT_PARSE_FAILED = 2


def _parse(in_path: str, out_path: str) -> int:
    """Read the STEP at *in_path*, write the transferred shape to *out_path*."""
    from OCP.BRepTools import BRepTools
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Reader

    # Pin the target unit in THIS process (fresh every spawn → no ambient state).
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")

    reader = STEPControl_Reader()
    status = reader.ReadFile(in_path)
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        return EXIT_PARSE_FAILED
    try:
        reader.TransferRoots()
        shape = reader.OneShape()
    except Exception:  # OCCT transfer raises are not a stable taxonomy
        return EXIT_PARSE_FAILED

    # A null / compound shape serializes fine; the parent owns the null and
    # single-solid checks so the healing report stays in one tested place.
    BRepTools.Write_s(shape, out_path)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return EXIT_PARSE_FAILED
    return _parse(argv[1], argv[2])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
