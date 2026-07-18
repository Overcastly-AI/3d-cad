---
name: geometry-gates
description: Run and extend Loft's geometric-correctness gates — golden models, STEP round-trips, determinism, performance budgets. Mandatory for any kernel-adjacent change; new modeling capability requires a new golden model in the same commit.
---

# Geometry gates

The CAD-specific quality bar (RESEARCH §9). "Unit tests pass" does not clear
it — these gates check that the geometry is *right*.

## Running

```bash
just geometry-gates            # full suite: goldens + round-trips + determinism
pytest services/geometry/tests/goldens -k <model>   # one golden
```

## Golden models (`services/geometry/goldens/`)

Each golden is: a feature-tree JSON + a committed expectations file
(volume, surface area, centroid, face/edge/shell counts, tolerance, and the
justification for that tolerance).

Adding one (required with every new feature type):

1. Build the reference part via the feature-tree API.
2. Compute expectations with the harness (`just golden-record <name>`), then
   **verify the numbers independently** — hand-calculate or cross-check in a
   second tool. A golden recorded from buggy output enshrines the bug.
3. Commit tree + expectations + a docstring stating what capability it locks.

## Rules

- **Never loosen a tolerance to go green.** Tolerance changes are reviewed
  decisions with kernel-level justification, recorded in the expectations
  file and `docs/GEOMETRY-QA.md`.
- Topology counts are exact-match — a changed face count is a real change,
  explain it or fix it.
- Round-trip failures (STEP export → import → mismatch) are defects, not
  noise. Root-cause to export, import, or kernel before filing.
- Determinism: same tree N times → identical metadata. Any flake here is a
  P0, not a retry.
- Budgets: rebuild/tessellation wall-clock ceilings live with the goldens; a
  regression >10% gets filed even inside budget.
