"""Geometry worker placeholder — the arq worker is NOT implemented yet.

The real worker (arq ``WorkerSettings`` running OCCT feature evaluation,
tessellation to GLB, and STEP/STL export via ``py_kit.queue``) lands with
the "web shell + first light" item (docs/BACKLOG.md). Kernel imports
(OCP/build123d) arrive only then, and only inside this service — this
module intentionally contains no code today.
"""
