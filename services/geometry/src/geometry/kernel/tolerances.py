"""The kernel's ONE linear tolerance, in the units this service models in (mm).

CLAUDE.md fixes the kernel-side linear tolerance at **1e-7 m**; the geometry
service models in millimetres, so every "are these two pieces of geometry the
same place?" comparison in :mod:`geometry.kernel` is a comparison against
**1e-4 mm**. That number was written out THREE times before this module existed
(``interference._KERNEL_LINEAR_TOL_MM``, ``extrude.PROFILE_WIRE_TOLERANCE``, and
— nearly — the zero-width-slit probe), which is the re-declared-epsilon defect
CLAUDE.md names outright. It lives here once instead.

Two DELIBERATE non-members, so the split is a decision and not an oversight:

* :data:`geometry.kernel.extrude.PROFILE_WIRE_TOLERANCE` happens to hold the same
  1e-4 mm but is not a comparison bound — it is the sewing tolerance HANDED TO
  OCCT when a profile wire is built, so it stays where its callers reason about
  it (a future OCCT-side retune must not silently move a comparison epsilon);
* the golden-suite tolerances (`docs/GEOMETRY-QA.md` tiers) are per-model
  ASSERTION bounds reviewed with their models, never kernel behaviour.

Derived floors belong with the predicate that uses them (e.g.
:data:`geometry.kernel.interference.CLASH_VOLUME_FLOOR_MM3` = one tolerance
CUBE, :data:`geometry.kernel.degenerate.SLIT_AREA_FLOOR_MM2` = one tolerance
SQUARE), because the exponent is part of that predicate's meaning.
"""

#: Kernel linear tolerance expressed in mm (``1e-7 m``; CLAUDE.md conventions /
#: RESEARCH §9). Two points, planes or faces closer than this are the SAME place
#: as far as this kernel is concerned — the single source for every kernel
#: coincidence comparison (module docstring).
KERNEL_LINEAR_TOL_MM = 1e-4
