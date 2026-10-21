"""Objects To Cut: a sketch-based cut removes material from the bodies its
``cut_bodies`` names (CUT-OBJECTS-TO-CUT, docs/RESEARCH.md §28).

Fusion 360's *Objects To Cut* and SolidWorks' *Feature Scope* default a new
extrude, revolve, sweep, loft or pipe cut to every body the tool meets. Before
this a cut removed material from the ACTIVE (most recently built) body only, so
a notch drawn across a top plate and three studs cut the plate and left the
studs whole, and a cut through a stud alone was refused.

``cut_bodies`` (:mod:`loft_wire.cut_bodies`) is ``"all"`` (every body met), a
list of bodies by base feature, or absent. Absent is every cut stored before
the field: it takes :func:`~geometry.features.state._cut_active` exactly as
before, so no saved part changes. This module is the other two.
"""

# Underscore names are private to the geometry.features package rather than to
# one module, so importing them from a sibling module is intended.
# pyright: reportPrivateUsage=false

import uuid
from collections.abc import Sequence

from build123d import Solid
from loft_wire.cut_bodies import CutBodies
from loft_wire.features import FeatureError

from geometry.features.bodies import _resolve_operand_body
from geometry.features.state import EvaluationState, _cut_active
from geometry.kernel import (
    BooleanError,
    CutRemovedNothingError,
    bounds_apart,
    combine_body_measured,
)
from geometry.kernel.boolean_guard import MeasuredBody
from geometry.kernel.naming import NameHook
from geometry.kernel.types import BodyShape

_MISSED_ALL = (
    "This cut removed no material from any body: the profile lies off every "
    "body (beside it, or in free space), the cut direction points away from "
    "the material, or an identical cut has already been made here."
)
_REGION_MISSED = (
    "One region of this cut's profile removes no material from any body it "
    "may cut. Move or resize that region so it overlaps a body, or remove it."
)
_BODY_MISSED = (
    "This cut's Objects To Cut lists a body the cut does not reach, so the "
    "cut would remove nothing from it. Untick that body, or move the profile "
    "so it overlaps the body."
)


def _targets(
    state: EvaluationState, scope: CutBodies
) -> list[tuple[uuid.UUID, BodyShape]] | FeatureError:
    """The bodies the cut MAY cut, in tree order (the order of ``bodies``).

    ``"all"`` is every current body; a list resolves each entry by base feature
    (``reference_unresolved`` for one that is not a current body)."""
    if scope == "all":
        return list(state.bodies.items())
    listed: set[uuid.UUID] = set()
    for index, ref in enumerate(scope):
        body = _resolve_operand_body(ref, state, slot=f"cut_bodies[{index}]")
        if isinstance(body, FeatureError):
            return body
        listed.add(ref.feature_id)
    return [(body_id, b) for body_id, b in state.bodies.items() if body_id in listed]


def cut_one_tool(
    state: EvaluationState,
    tool: Solid,
    *,
    feature_id: uuid.UUID,
    scope: CutBodies | None,
    generated: NameHook = (),
) -> FeatureError | None:
    """The CUT of a revolve, sweep, loft or pipe: a stored cut with no
    ``cut_bodies`` cuts the active body exactly as before (:func:`_cut_active`),
    one with the field cuts its Objects To Cut (:func:`cut_scoped_bodies`)."""
    if scope is None:
        return _cut_active(state, tool, feature_id=feature_id, generated=generated)
    return cut_scoped_bodies(
        state, [tool], feature_id=feature_id, scope=scope, generated=generated
    )


def cut_scoped_bodies(
    state: EvaluationState,
    tools: Sequence[Solid],
    *,
    feature_id: uuid.UUID,
    scope: CutBodies,
    generated: NameHook = (),
) -> FeatureError | None:
    """Cut every *tools* member from each body of *scope* it meets.

    Each body is cut independently by the tools that reach it, in tree order,
    so the result does not depend on how the list was written. A body the
    boxes prove apart from a tool skips that boolean (:func:`bounds_apart`);
    every other pair asks the shared CM-3 predicate inside the cut. Errors
    are typed and leave every body untouched (the state is written only once
    every boolean has succeeded, §4.3):

    * ``cut_removed_nothing``: no body was cut at all; or one region of a
      multi-region profile met none of them (the extrude rule, region by
      region); or a LISTED body the cut does not reach, pinned to that body;
    * ``boolean_failed``: a kernel failure on any body;
    * ``reference_unresolved``: a listed body that is not a current body.

    On success the cut bodies are installed, the active body stays active if
    it was cut and otherwise becomes the first cut body (the body the feature
    touched, as a Hole's owner does), and the tools are recorded for a
    following pattern or mirror exactly as the active-body cut records them.
    """
    targets = _targets(state, scope)
    if isinstance(targets, FeatureError):
        return targets
    cuts: dict[uuid.UUID, MeasuredBody] = {}
    tool_met = [False] * len(tools)
    for body_id, body in targets:
        current: MeasuredBody | None = None
        for index, tool in enumerate(tools):
            if bounds_apart(body, tool):
                continue
            shape = body if current is None else current.shape
            volume = state.body_volume(body_id) if current is None else current.volume
            try:
                current = combine_body_measured(shape, tool, "cut", body_volume=volume)
            except CutRemovedNothingError:
                continue
            except BooleanError as exc:
                return FeatureError(
                    code="boolean_failed",
                    message=str(exc),
                    upstream_feature_id=body_id,
                )
            tool_met[index] = True
        if current is not None:
            cuts[body_id] = current
        elif scope != "all":
            return FeatureError(
                code="cut_removed_nothing",
                message=_BODY_MISSED,
                upstream_feature_id=body_id,
            )
    if not cuts:
        return FeatureError(code="cut_removed_nothing", message=_MISSED_ALL)
    if not all(tool_met):
        return FeatureError(code="cut_removed_nothing", message=_REGION_MISSED)
    for body_id, cut in cuts.items():
        state.set_body(body_id, cut.shape, generated, volume=cut.volume)
    if state.active_body_id not in cuts:
        state.active_body_id = next(iter(cuts))
    state.cut_bodies_met = list(cuts)
    state.record_cut_tools(feature_id, list(tools))
    state.record_feature_tools(feature_id, "cut", list(tools), generated)
    return None
