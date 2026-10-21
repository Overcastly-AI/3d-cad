"""Objects To Cut: which bodies a sketch-based cut removes material from
(CUT-OBJECTS-TO-CUT, docs/RESEARCH.md §28).

Fusion 360's *Objects To Cut* and SolidWorks' *Feature Scope* both default a
new extrude, revolve, sweep or loft cut to EVERY body the tool meets, with a
body list to narrow it. ``cut_bodies`` carries that choice on the extrude,
revolve, sweep, loft and pipe params:

* ``"all"``: every body the tool meets, found on each rebuild (SolidWorks'
  *All bodies*). What a new cut stores, so a notch drawn across a top plate
  and three studs cuts all four, and a stud added under it later is cut too.
* a list of bodies, each named by its base (body-creating) feature, the
  boolean operand rule: exactly these. A listed body the tool misses is the
  typed rebuild error ``cut_removed_nothing`` pinned to that body, never a
  silent no-op.
* absent: the ACTIVE body only. Every cut stored before Objects To Cut has no
  field and rebuilds exactly as it did (versioned by absence, as ``merge`` and
  the twist were), so no saved part changes.

A pure wire module (no kernel types). Absent dumps as absent, so a stored cut
serializes byte-for-byte as before.
"""

from typing import Annotated, Literal, Protocol

from pydantic import Field

from loft_wire.refs import FeatureRef
from loft_wire.twist import is_none

#: Ceiling on a cut's body list (a work bound: one boolean per body). A body
#: is at least one feature, so a tree cannot hold more.
MAX_CUT_BODIES = 1000

#: ``"all"`` or a non-empty list of bodies by base feature (module docstring).
CutBodies = (
    Literal["all"]
    | Annotated[list[FeatureRef], Field(min_length=1, max_length=MAX_CUT_BODIES)]
)

CUT_BODIES_FIELD = Field(
    default=None,
    exclude_if=is_none,
    description=(
        "CUT only: the bodies the cut removes material from (Fusion 360's "
        'Objects To Cut, SolidWorks\' Feature Scope). "all" cuts every body '
        "the tool meets, found on each rebuild (what a new cut stores); a list "
        "of bodies, each by its base feature, cuts exactly those, and one the "
        "tool misses is `cut_removed_nothing` pinned to it. Absent (every cut "
        "saved before Objects To Cut) cuts the ACTIVE body only, as it always "
        "did. Must be absent on an add."
    ),
)


class _CutScoped(Protocol):
    @property
    def operation(self) -> Literal["add", "cut"]: ...

    @property
    def cut_bodies(self) -> CutBodies | None: ...


def check_cut_bodies[M: _CutScoped](model: M) -> M:
    """``model_validator(mode="after")`` body: Objects To Cut belongs to a cut
    and names each body at most once."""
    scope = model.cut_bodies
    if scope is None:
        return model
    if model.operation != "cut":
        raise ValueError("cut_bodies applies to a cut only; omit it on an add")
    if scope != "all":
        ids = [ref.feature_id for ref in scope]
        if len(set(ids)) != len(ids):
            raise ValueError("cut_bodies names the same body more than once")
    return model
