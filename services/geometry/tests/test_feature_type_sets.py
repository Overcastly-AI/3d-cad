"""The feature-type SETS agree with each other and with the registry.

Engineering audit J6 (2026-07-30): geometry re-declares the body-affecting
feature types as a hand-written frozenset
(:data:`geometry.features.evaluate._BODY_AFFECTING_TYPES`) while py-kit already
owns :data:`py_kit.schemas.features.BODY_AFFECTING_FEATURE_TYPES`. Both listed
the same 17 members and nothing checked that they still did.

Why a GATE and not a merge. The two constants answer different questions:

* py-kit's is "may a :class:`SubshapeRef` name a face on this feature's result?"
  (topo-naming §4).
* geometry's is "does an ok evaluation of this feature mutate the body set?"
  (§MB-0), which the main loop uses to set ``prev_body_feature_id`` so a pattern
  can infer its combine mode.

Those coincide today and the coincidence is not a tautology — a future verb could
plausibly be nameable without mutating the body chain, or vice versa. Collapsing
them into one name would assert an equivalence nobody has established, so instead
this locks the equality WITH a place to record a deliberate divergence: if one of
these sets ever legitimately needs a member the other lacks, change the assertion
to name that member and say why. What must never happen again is the two drifting
by accident, which is invisible until a pattern picks the wrong combine mode or a
face reference is rejected as unnameable.

Modelled on the house pattern (`apps/web/src/features/thread.test.ts`, which
parses the kernel's ISO table rather than re-typing it) and on the composition
matrix's coverage audit, which derives its rows from ``FEATURE_REGISTRY.models()``
after a hand-listed axis silently stopped covering (CM-5).
"""

from geometry.features.evaluate import _BODY_AFFECTING_TYPES
from py_kit.schemas.features import (
    BASE_BODY_AFFECTING_FEATURE_TYPES,
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
)

#: Members that are NOT body-affecting, asserted explicitly so the sets cannot
#: pass by being empty or by swallowing the whole vocabulary. `sketch` produces
#: input geometry and `datum` produces a plane; neither ever yields a body.
NON_BODY_AFFECTING = frozenset({"sketch", "datum"})


def test_geometry_and_py_kit_agree_on_body_affecting_types() -> None:
    """The duplicate declarations have identical membership.

    A `frozenset ==` on both sides, so a member added to ONE side fails here —
    which is the property audit J6 found missing.
    """
    assert _BODY_AFFECTING_TYPES == BODY_AFFECTING_FEATURE_TYPES, (
        "geometry's _BODY_AFFECTING_TYPES has drifted from py-kit's "
        "BODY_AFFECTING_FEATURE_TYPES. Only geometry.features.evaluate:"
        f"{sorted(_BODY_AFFECTING_TYPES - BODY_AFFECTING_FEATURE_TYPES)}; "
        "only py_kit.schemas.features: "
        f"{sorted(BODY_AFFECTING_FEATURE_TYPES - _BODY_AFFECTING_TYPES)}. If the "
        "divergence is deliberate, name the member here and say why."
    )


def test_the_agreement_is_not_vacuous() -> None:
    """Both sets are populated and neither has swallowed the vocabulary.

    Without this, emptying both sides — a bad merge, a typo in a shared
    constructor — would satisfy the equality above and read as green.
    """
    assert len(BODY_AFFECTING_FEATURE_TYPES) >= 10
    assert "extrude" in _BODY_AFFECTING_TYPES
    assert not (NON_BODY_AFFECTING & BODY_AFFECTING_FEATURE_TYPES), (
        "sketch/datum produce input geometry and a plane, never a body"
    )


def test_every_body_affecting_type_is_a_registered_feature() -> None:
    """No set member is a string the product no longer has a verb for.

    This is the assertion that catches a RENAME. A hand-written string survives
    a verb rename silently: the set keeps a dead entry, the renamed verb is
    absent, and the only symptom is a feature quietly failing to count as
    body-affecting. Deriving the check from the registry — the same source the
    matrix's coverage audit uses — makes that a red test instead of a mystery.
    """
    registered = frozenset(FEATURE_REGISTRY.models())
    unknown = BODY_AFFECTING_FEATURE_TYPES - registered
    assert not unknown, (
        f"BODY_AFFECTING_FEATURE_TYPES names unregistered feature types: "
        f"{sorted(unknown)} — a verb was renamed or removed and the set kept a "
        "dead string."
    )


def test_base_body_affecting_is_a_subset() -> None:
    """The base-body set is a genuine subset, not a parallel list.

    BASE_BODY_AFFECTING_FEATURE_TYPES is the verbs that can START a body (six of
    them). A member outside the wider set would mean something creates a body
    without being body-affecting, which is incoherent.
    """
    assert BASE_BODY_AFFECTING_FEATURE_TYPES <= BODY_AFFECTING_FEATURE_TYPES
    assert BASE_BODY_AFFECTING_FEATURE_TYPES  # non-vacuous
    assert BASE_BODY_AFFECTING_FEATURE_TYPES < BODY_AFFECTING_FEATURE_TYPES, (
        "a PROPER subset: modifiers like fillet/shell/hole affect a body "
        "without being able to start one"
    )
