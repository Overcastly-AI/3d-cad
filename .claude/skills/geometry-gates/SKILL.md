---
name: geometry-gates
description: Run and extend Loft's geometric-correctness gates — golden models, STEP round-trips, determinism, performance tripwires. Use for any kernel-adjacent change; a new modelling capability needs a new golden in the same commit.
---

# Geometry gates

These gates check that the geometry is right, not just that the code runs
(RESEARCH §9).

## Running

```bash
uv run pytest services/geometry/tests                      # everything, incl. goldens
uv run pytest services/geometry/tests/test_goldens.py -k <name>
scripts/e2e.sh --geometry-only                             # the e2e geometry leg
just bench                                                 # detailed timings (not a gate)
```

## Adding a golden

Create `services/geometry/goldens/<name>/` (or `goldens-assembly/` or
`goldens-sheet-metal/`) with:

- `model.json`: a serialized `TessellateRequest` or `EvaluateTreeRequest`;
- `expected.json`: volume, area, centroid, bounds, topology and mesh counts,
  the tolerance, and a description of what it locks and how the numbers were
  derived.

The runner discovers it without changes. **Derive the expected numbers
independently** (by hand, analytically, or with a second tool). A golden
recorded from the code's own output only locks in its bugs.

## Rules

- Never loosen a tolerance to go green. A tolerance change needs a
  kernel-level reason, written into `expected.json`.
- Topology counts must match exactly. A changed face count is a real change:
  explain it or fix it.
- A round-trip mismatch is a defect. Trace it to the export, the import or
  the kernel.
- A determinism failure is blocking, never something to retry.
