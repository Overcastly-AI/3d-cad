"""Thread schedule — a part's tapped holes, derived for the print (BACKLOG #50).

The output half of cosmetic threads. `19c9dc2` gave a hole a typed ISO designation
and bored the tap drill; the designation then reached the editor and the feature
tree and nothing a shop ever sees. A tapped hole's SOLID is byte-identical to its
bore (``geometry.kernel.threads`` — that is the whole cosmetic-thread trade-off),
so the drawing is the only place the thread can exist. Until it is stamped there,
an M6x1 tapped hole and a plain 5 mm drilled hole are the same part, and the shop
manufactures the wrong one.

DERIVED, NEVER STORED (the assembly-BOM posture): the rows are recomputed from the
feature params on every compose, so re-tapping a hole cannot leave a stale callout
on the next print. The kernel's
:func:`~geometry.kernel.threads.resolve_iso_metric_thread` is the sole source of
the designation string and the tap drill — this module counts and orders, it
never re-derives a formula (CLAUDE.md DRY).

Order is TREE order of first appearance, not request-array order (RESEARCH §9
feature-set determinism): the same part composes to byte-identical rows however the
UI happened to hand the features over.

An UNRESOLVABLE designation is SKIPPED, not guessed. It cannot normally occur — the
evaluator raises ``hole_thread_unsupported`` before any geometry, so a tree that
composed at all has resolvable threads — but a compose request is a separate call
that can carry any feature list, and inventing a callout for a thread the kernel
refuses to cut is the one failure mode worse than omitting the row.
"""

from __future__ import annotations

from collections.abc import Iterable

from py_kit.schemas.drawings import ThreadCalloutRow
from py_kit.schemas.features import EvaluatedFeatureInput, HoleParamsV1

from geometry.kernel.threads import ThreadUnsupportedError, resolve_iso_metric_thread


def thread_schedule_rows(
    features: Iterable[EvaluatedFeatureInput],
) -> list[ThreadCalloutRow]:
    """Roll *features*' tapped holes up into one row per distinct designation.

    Every ``hole`` feature carrying a ``thread`` contributes one to its
    designation's quantity; the row order is first appearance in the given
    (tree-ordered) feature list. A feature list with no tapped hole returns ``[]``,
    which composes to no block at all — additive, byte-identical to before.

    Note this counts FEATURES, not holes-in-the-solid: a tapped hole inside a 6x
    pattern is one feature and reads as quantity 1 here. Pattern instance counting
    needs the evaluated topology rather than the params, and a schedule that
    silently under-counts a patterned hole would be worse than one that plainly
    counts what the tree says — so the row is honest about being per-feature, and
    resolving the pattern multiplier is a tracked follow-up.
    """
    counts: dict[str, int] = {}
    drills: dict[str, float] = {}
    for entry in features:
        params = entry.feature.params
        if not isinstance(params, HoleParamsV1) or params.thread is None:
            continue
        try:
            thread = resolve_iso_metric_thread(
                params.thread.nominal_diameter_mm, params.thread.pitch_mm
            )
        except ThreadUnsupportedError:
            continue
        counts[thread.designation] = counts.get(thread.designation, 0) + 1
        drills[thread.designation] = thread.tap_drill_diameter_mm
    return [
        ThreadCalloutRow(
            designation=designation,
            quantity=quantity,
            tap_drill_mm=drills[designation],
        )
        for designation, quantity in counts.items()
    ]
