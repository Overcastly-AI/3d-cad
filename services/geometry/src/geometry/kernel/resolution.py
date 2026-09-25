"""Per-feature record of WHICH tier resolved each picked subshape reference.

EDGE-RESOLVE-WARN-1 (docs/design/topological-naming.md §7.3). The stage-1
resolvers are tiered: a picked edge is re-found strict (``exact``), then on its
rebuild invariant (``durable``), then as the edge its two stored neighbouring
faces share (``adjacent``, §14); a picked face strict, then on one of three
resilient invariants (all ``durable`` on the wire). Only the strict tier is
certain. The others are best-effort and can, rarely, re-find the WRONG subshape
without erroring (§7.3, measured in §14), so a feature that rebuilt on one of
them must be able to SAY so instead of reporting the same bare ``ok`` as an
exact rebuild.

:class:`ResolutionTally` is how the resolvers say it. The evaluator hands each
feature a fresh tally, every resolver that successfully re-finds a picked
reference calls :meth:`ResolutionTally.note` with the tier that fired, and the
evaluator turns the tally into the wire
:class:`~loft_wire.features.SubshapeResolutionSummary` on the feature's result.

It is an EXPLICIT keyword argument (``tally=``) on each resolver rather than an
ambient context: the resolvers are also called by drawings, mates and the
selection overlay, which report nothing, and a reader of a feature handler can
see which references it reports. That a handler cannot silently forget to pass
it is gated by a census over every feature type the wire schema lets name
a subshape (``tests/test_subshape_resolution.py``).

Recording is observation only: it never changes which subshape is returned, the
order anything is enumerated in, or the rebuild-cache key (the summary rides on
the cached ``FeatureResult``, so a resumed rebuild reports exactly what the cold
one did).
"""

from loft_wire.features import (
    SUBSHAPE_RESOLUTION_TIERS,
    SubshapeResolutionSummary,
    SubshapeResolutionTier,
)


class ResolutionTally:
    """Counts, per tier, the picked references ONE feature resolved.

    One count per reference, in the tier that resolved it - two refs that land
    on the same subshape still count twice, because the user picked twice.
    """

    __slots__ = ("_counts",)

    def __init__(self) -> None:
        self._counts: dict[SubshapeResolutionTier, int] = dict.fromkeys(
            SUBSHAPE_RESOLUTION_TIERS, 0
        )

    def note(self, tier: SubshapeResolutionTier) -> None:
        """Record that one reference resolved at *tier*."""
        self._counts[tier] += 1

    def summary(self) -> SubshapeResolutionSummary | None:
        """The wire summary, or ``None`` when nothing was resolved.

        ``None`` (not an all-zero summary) for a feature with no picked
        reference, so the field is absent exactly where there is nothing to say.
        """
        noted: list[SubshapeResolutionTier] = [
            tier for tier in SUBSHAPE_RESOLUTION_TIERS if self._counts[tier]
        ]
        if not noted:
            return None
        return SubshapeResolutionSummary(
            worst_tier=noted[-1],
            exact=self._counts["exact"],
            durable=self._counts["durable"],
            adjacent=self._counts["adjacent"],
        )


def face_tier(resilient: bool) -> SubshapeResolutionTier:
    """The wire tier of a planar-face match from
    :func:`geometry.kernel.faces.match_face_records`.

    Its three resilient tiers (coplanar, translated, enclosing) all mean "the
    face moved or changed and was re-found on an invariant" - the drawings
    vocabulary's ``durable``. ``adjacent`` is edge-only.
    """
    return "durable" if resilient else "exact"
