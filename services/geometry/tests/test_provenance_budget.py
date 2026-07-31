"""The per-face provenance BUDGET — where feature highlighting goes dark (PERF-5).

``geometry.kernel.attribute_faces`` skips attribution entirely (returns
all-``None``) once the fingerprint budget ``len(final faces) + sum(len(snapshot
faces))`` exceeds :data:`~py_kit.schemas.overlay.MAX_PROVENANCE_FACES`. Past that
point, clicking a feature in the tree silently stops highlighting that feature's
faces and falls back to whole-body selection.

The budget sums over **every** snapshot, so it is spent by ``features x faces`` —
quadratic in part size — and the crossing point is therefore a FEATURE COUNT, not
a face count. Measured on the docs/PERF.md tray (2026-07-31 / 2026-07-31b):

======== ====== =========== =======================
features  faces  budget      vs. ceiling
======== ====== =========== =======================
100         219    7 242     91 % of the old 8 000
105         237    8 180     **crossed** 8 000
200         442   28 552     95 % of the new 30 000
205         449   29 452     98 %
210         467   31 310     **crosses** 30 000
======== ====== =========== =======================

So the old ceiling went dark at **N ~= 103 features** while its docstring said an
authored part was "nowhere near the bound"; the re-derived one crosses at
**N ~= 207**, past every size that rebuilds at all today (N=200 takes 27 s).

These gates are UNMARKED (they run in the default suite) and cheap: the budget
arithmetic is identical whether the snapshots come from a 110-feature tray rebuild
(~9 s) or from a synthetic growing part (~1 s), and it is the arithmetic that is
under test.
"""

from __future__ import annotations

import uuid
from typing import cast

from build123d import Compound, Solid
from geometry.kernel import attribute_faces
from geometry.kernel.types import BodyShape
from py_kit.schemas.overlay import MAX_PROVENANCE_FACES

#: Lattice pitch/side for the synthetic part below — 2 mm apart so no two cubes
#: touch (no boolean, no shared faces) and every face is geometrically distinct,
#: which is what makes the attribution assertion meaningful.
_PITCH = 2.0
_SIDE = 32


def _growing_history(
    steps: int, boxes_per_step: int
) -> tuple[BodyShape, list[tuple[uuid.UUID, BodyShape]]]:
    """A synthetic *growing* part: snapshot *k* is a compound of ``(k + 1) *
    boxes_per_step`` unit cubes, so each snapshot adds DISTINCT faces and every
    final face first appears in exactly one snapshot — the same shape a real
    feature history has, at a fraction of the rebuild cost.
    """
    cubes = [
        Solid.make_box(1.0, 1.0, 1.0).translate(
            (
                i % _SIDE * _PITCH,
                i // _SIDE % _SIDE * _PITCH,
                i // (_SIDE * _SIDE) * _PITCH,
            )
        )
        for i in range(steps * boxes_per_step)
    ]
    history = [
        (
            uuid.UUID(int=step + 1),
            cast(BodyShape, Compound(cubes[: (step + 1) * boxes_per_step])),
        )
        for step in range(steps)
    ]
    return history[-1][1], history


def test_a_part_past_the_old_provenance_crossing_still_attributes() -> None:
    """PERF-5: past the OLD 8 000 budget, feature-localized highlighting used to go
    silently dark. It must not.

    The history built here lands BETWEEN the old 8 000 ceiling and the current
    one, so it fails if the ceiling is ever walked back without redoing the
    docs/PERF.md evidence — and it fails LOUDLY rather than as a null field in an
    overlay response that nothing asserts on.
    """
    body, history = _growing_history(steps=15, boxes_per_step=10)
    budget = len(body.faces()) + sum(len(shape.faces()) for _fid, shape in history)
    assert 8_000 < budget < MAX_PROVENANCE_FACES, (
        f"budget {budget} no longer straddles the old 8 000 crossing and the "
        f"current {MAX_PROVENANCE_FACES} ceiling — this gate stopped testing what "
        "it claims to."
    )

    owners = attribute_faces(body, history)
    assert len(owners) == len(body.faces())
    assert all(owner is not None for owner in owners), (
        "a part past the OLD provenance crossing attributed nothing — clicking a "
        "feature in the tree silently stops highlighting its faces (PERF-5)."
    )
    # Attribution is still CORRECT, not merely non-null: each cube's faces are
    # owned by the EARLIEST snapshot that contains that cube, so every snapshot
    # owns exactly the faces it introduced.
    assert len(set(owners)) == len(history), (
        f"expected all {len(history)} snapshots to own the faces they introduced; "
        f"got {len(set(owners))} distinct owners"
    )


def test_the_provenance_ceiling_is_the_re_derived_one() -> None:
    """Pin the ceiling VALUE, with its derivation, where a reader will look.

    Re-derived 2026-07-31 (PERF-5) from the measured per-fingerprint cost
    (134-237 us, an exact-B-rep GProp area + centroid), so the worst admitted pass
    is ~4.0-7.1 s. That is deliberately larger than the ~1.5 s the old 8 000 was
    sized for: at N=125 — the first size 8 000 refused — the SAME overlay request
    already pays ~11 s of rebuild underneath it, so the bound was spending the
    point of the request to save a sixth of it. It still degrades the pathological
    case audit H4 named: a 20 000-face imported body is one snapshot, budget 40 000.
    """
    assert MAX_PROVENANCE_FACES == 30_000
