"""Evaluation state shared by every feature handler (feature-tree design §4).

:class:`EvaluationState` is the mutable record one ordered dispatch pass threads
through the handlers, and :meth:`EvaluationState._admit` is the ONE funnel every
body enters ``bodies`` through (the CM-6 invalid-body gate). Also here: the
per-feature tool records a ``features``-scope mirror or pattern replays, the
:data:`FeatureHandler` signature, and the two body ops the sketch-based solids
and sheet metal share: the merge-aware additive :func:`_add_body` and the
active-body cut :func:`_cut_active`.
"""

import dataclasses
import functools
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from build123d import Plane, Solid
from loft_wire.features import (
    EvaluatedFeatureInput,
    FeatureError,
)

from geometry.kernel import (
    BooleanError,
    CutRemovedNothingError,
    combine_body_measured,
)
from geometry.kernel.clean_history import MergedFaces
from geometry.kernel.fork import fork_shapes
from geometry.kernel.healing import new_geometry_is_valid, shape_volume
from geometry.kernel.naming import BodyNames, NameHook, carry_names, tool_face_names
from geometry.kernel.provenance import FaceProvenanceRecorder
from geometry.kernel.resolution import ResolutionTally
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import (
    BendProvenance,
    CornerRelief,
    SheetMetalDefaults,
)
from geometry.sketch import (
    SolvedSketch,
)


class InvalidBodyError(RuntimeError):
    """A feature produced a shape ``BRepCheck`` rejects as a solid (CM-6).

    Raised by :meth:`EvaluationState._admit` — the ONE funnel every body passes
    through on its way into ``state.bodies`` — and turned into the typed
    per-feature ``invalid_body`` error by :func:`_dispatch`. It is deliberately an
    EXCEPTION rather than a returned :class:`FeatureError`: the gate sits inside a
    state mutator that every one of the twenty-odd body-affecting handlers calls,
    and threading a return value back out of each of them is exactly the
    per-op-site plumbing that lets a guard be forgotten (the CM-5 lesson).
    """


#: A recorded tool group's boolean: the operation the owning feature applied to the
#: active body, and therefore the operation a ``features``-scope mirror re-applies
#: to the reflected tools (docs/design/mirror-semantics.md §4.1/§4.2).
ToolOp = Literal["fuse", "cut"]


@dataclass(frozen=True)
class RecordedToolGroup:
    """One (operation, tool solids) pair a feature applied to the active body.

    A plain verb records exactly ONE group — an additive extrude its prism
    (``fuse``), a hole its bore + recess (``cut``). A ``features``-scope MIRROR
    records the concatenation of the groups it itself applied, in application
    order, so a nested (4-fold quadrant) mirror reflects them per group —
    mirror-semantics §4.6, the "op = per tool" row of §4.7.
    """

    op: ToolOp
    tools: list[BodyShape]
    #: Each tool's face names (aligned with ``tool.faces()``, or ``None`` for a
    #: tool with none), so a pattern or mirror repeating the tools can name the
    #: copies (DESIGN-INTENT-REFS). Empty means no names were recorded.
    names: list[list[str | None] | None] = field(
        default_factory=list[list[str | None] | None]
    )

    def names_of(self, index: int) -> list[str | None] | None:
        """The face names of tool *index*, or ``None``."""
        return self.names[index] if index < len(self.names) else None


@dataclass(frozen=True)
class RecordedFeatureTools:
    """The reflectable contribution of ONE ok feature (mirror-semantics §2b).

    Captured at the feature's OWN evaluation, from the body it was applied to —
    never re-derived later against a mutated body (the FINDINGS #1/#3 lesson that
    :meth:`EvaluationState.record_cut_tools` already encodes, generalised to every
    mirrorable verb). ``body_id`` is the body the groups were applied to, so a
    mirror can refuse to reflect body A's material into body B
    (``mirror_feature_other_body``, §MB-0 / §4.4).
    """

    body_id: uuid.UUID | None
    groups: list[RecordedToolGroup]

    @property
    def tool_count(self) -> int:
        """Total tool solids across every group (0 == "contributed nothing")."""
        return sum(len(group.tools) for group in self.groups)


@dataclass
class EvaluationState:
    """Mutable state threaded through one ordered dispatch pass.

    ``solved_sketches``/``sketch_planes`` are keyed by feature id and
    insertion-ordered by evaluation order (deterministic); the extrude
    handler reads its profile from them. ``sketch_planes`` holds the RESOLVED
    :class:`~build123d.Plane` each ok sketch sits on (origin datum or offset
    ``datum`` feature — docs/design/datum-planes.md §3a), so every downstream
    builder takes a concrete plane. ``datum_planes`` holds the resolved
    :class:`~build123d.Plane` of each ok ``datum`` feature, keyed by its id, so
    a later sketch's plane FeatureRef resolves against it. All hold kernel
    types strictly service-internal (never serialized), exactly like ``bodies``.

    ``bodies`` is the part's set of solid bodies (docs/design/multi-body.md
    §MB-0): keyed by the BASE feature id that created each body and insertion-
    ordered by the tree order those base features were evaluated (deterministic,
    RESEARCH §9). A part is *implicitly one body* until an additive feature with
    ``merge=False`` (or an ``import`` after a body already exists) starts a
    second. ``active_body_id`` names the body every MODIFYING feature (fillet/
    chamfer/shell/draft/pattern, add-merge/cut) targets AND that topological
    naming resolves against — NEVER a union of all bodies (the MB-0 correctness
    rule, Decision 1): a congruent face on two coexisting bodies must not tie a
    false ``subshape_ambiguous``. ``bodies`` is mutated only by body-affecting
    handlers **on success**, so after a failure it is exactly the last-good body
    set the strict-prefix rule tessellates (§4.3).
    """

    linear_deflection: float
    solved_sketches: dict[uuid.UUID, SolvedSketch] = field(
        default_factory=dict[uuid.UUID, SolvedSketch]
    )
    sketch_planes: dict[uuid.UUID, Plane] = field(
        default_factory=dict[uuid.UUID, Plane]
    )
    datum_planes: dict[uuid.UUID, Plane] = field(default_factory=dict[uuid.UUID, Plane])
    bodies: dict[uuid.UUID, BodyShape] = field(
        default_factory=dict[uuid.UUID, BodyShape]
    )
    #: FINGERPRINTS of the WHOLE body set after each ok BODY-AFFECTING feature, in
    #: evaluation order (earliest first). Per-face feature provenance (FINDINGS #9,
    #: :func:`geometry.kernel.attribute_faces`) walks these earliest-first to
    #: attribute each final face to the feature that created or last modified it, so
    #: the frontend can highlight one feature's faces instead of clay-swapping the
    #: whole body. Each snapshot is fingerprinted off exactly the shape the final
    #: tessellation is built from (:func:`_snapshot_shape` — bare solid or flattened
    #: Compound), so a face matches across snapshots by geometry.
    #:
    #: It holds fingerprints and NOT the snapshot B-reps (PERF-5b): retaining bodies
    #: made the interactive attribution pass ``O(features x faces)`` — 11-16 % of
    #: every ``/overlay`` request, quadratic in tree length — and kept an
    #: intermediate body alive per feature. Recorded on EVERY evaluation since
    #: PERF-REAL-3 (see :func:`evaluate_tree`, "ONE LINEAGE"), bounded by
    #: :data:`~loft_wire.overlay.MAX_PROVENANCE_FACES`.
    provenance: FaceProvenanceRecorder = field(default_factory=FaceProvenanceRecorder)
    #: The part's sheet-metal defaults (gauge/K/bend-radius) keyed by the
    #: base-flange feature id that created the sheet body (docs/design/
    #: sheet-metal.md §4.1/§5). Recorded only on an ok base flange; the
    #: edge-flange / unfold slices read it to compute a bend allowance. Held as a
    #: service-internal record (never serialized), exactly like ``bodies``.
    sheet_metal_defaults: dict[uuid.UUID, SheetMetalDefaults] = field(
        default_factory=dict[uuid.UUID, SheetMetalDefaults]
    )
    #: The bend provenance (§5: cylindrical-face + base-face signatures + K-factor)
    #: recorded by each ok edge-flange feature, keyed by that feature id and
    #: insertion-ordered by evaluation order (deterministic). The unfold reads it to
    #: find each bend by provenance, never blind detection. Service-internal.
    bend_provenance: dict[uuid.UUID, BendProvenance] = field(
        default_factory=dict[uuid.UUID, BendProvenance]
    )
    #: The explicit corner reliefs (§4.4) authored by each ok corner-relief feature,
    #: keyed by that feature id and insertion-ordered by evaluation order
    #: (deterministic). The flat-pattern unfold reads them to develop the relieved
    #: blank; the 3D notch is already cut into the active body. Service-internal.
    corner_reliefs: dict[uuid.UUID, CornerRelief] = field(
        default_factory=dict[uuid.UUID, CornerRelief]
    )
    #: The CLEAN sheet body the flat-pattern unfold AND every corner relief resolve
    #: their bend signatures against (§4.4.4): every bend applied, NO relief notches,
    #: maintained by each fold (:func:`_fold_flange_off_edge`) and NEVER mutated by a
    #: relief cut. A relief notch shortens a bend cylindrical face, shifting its
    #: centroid past the signature match tolerance, so resolving against the live
    #: (notched) body would miss a shared/earlier bend — resolving against this
    #: un-notched body sidesteps that regardless of feature order (a relief that
    #: shares a flange with an earlier relief, or a flange authored AFTER a relief,
    #: both resolve). ``None`` until the first fold sets it; for an unrelieved part it
    #: equals the live body (same bends, no notches). Service-internal, like ``bodies``.
    sheet_metal_unfold_body: BodyShape | None = None
    active_body_id: uuid.UUID | None = None
    #: The id of the immediately-preceding ok BODY-AFFECTING feature (tree order),
    #: advanced by :func:`evaluate_tree` after each one. Read ONLY through
    #: :func:`_pattern_cut_tools`, to answer "was the last body feature the cut
    #: that produced :attr:`last_cut_tools`?" — the pattern's locked
    #: source-inference rule (BACKLOG #3).
    prev_body_feature_id: uuid.UUID | None = None
    #: The removal TOOL solid(s) of the most recent ok CUT feature — an
    #: extrude-CUT's region prisms, or a Hole's bore + any counterbore/countersink
    #: recess — CAPTURED at cut-eval time from the SAME pre-cut body, so they
    #: reproduce the removed geometry exactly instead of being re-derived later
    #: against the post-cut body (FINDINGS #1/#3). Recorded through
    #: :meth:`record_cut_tools`; ``None`` until the first cut. Two readers with two
    #: DIFFERENT, documented rules: :func:`_pattern_cut_tools` (immediate
    #: predecessor only — locked) and :func:`_mirror_cut_tools` (the most recent
    #: cut, however far back — CM-1). Service-internal, like ``bodies``.
    last_cut_tools: list[Solid] | None = None
    #: The feature id that produced :attr:`last_cut_tools`, and the body those
    #: tools were cut FROM. The pattern compares the id against
    #: :attr:`prev_body_feature_id`; BOTH readers require the recorded body to still
    #: be active, so a cut on body A can never be replicated into body B (§MB-0).
    last_cut_feature_id: uuid.UUID | None = None
    last_cut_body_id: uuid.UUID | None = None
    #: The ids named by any ``features``-scope mirror OR PATTERN in this request —
    #: the OPT-IN capture set (:func:`_tool_scope_ids`, mirror-semantics §9,
    #: pattern-scope §5). Only these features retain their tools in
    #: :attr:`feature_tools`, so a tree with no such verb pays nothing. Named
    #: ``tool_scope_ids`` rather than ``mirror_scope_ids`` since the pattern joined:
    #: a slot holding pattern ids under a mirror's name is the kind of small lie the
    #: next reader pays for. Set once by :func:`evaluate_tree`; never mutated after.
    tool_scope_ids: frozenset[uuid.UUID] = frozenset()
    #: The reflectable contribution of each CAPTURED ok feature, keyed by feature id
    #: and INSERTION-ORDERED BY EVALUATION ORDER — which is what makes a
    #: ``features``-scope mirror apply its reflected tools in TREE order rather than
    #: the UI-incidental array order (mirror-semantics §8.1, a determinism rule a
    #: caller can observe). Service-internal, like ``bodies``.
    feature_tools: dict[uuid.UUID, RecordedFeatureTools] = field(
        default_factory=dict[uuid.UUID, RecordedFeatureTools]
    )
    #: The feature TYPE of each CAPTURED feature that evaluated ok, in evaluation
    #: order. A mirror needs it to tell the three refusals apart: an id absent here
    #: is not in this prefix (``reference_unresolved``); present with no
    #: :attr:`feature_tools` entry is a kind with no reflectable contribution
    #: (``mirror_feature_unsupported`` — every modifier, a ``body``-scope mirror, a
    #: ``sketch``/``datum``); present WITH tools is reflectable. Only captured ids
    #: are tracked, so this costs one dict entry per selected feature.
    scoped_feature_types: dict[uuid.UUID, str] = field(
        default_factory=dict[uuid.UUID, str]
    )
    #: Which tier resolved each picked subshape reference of the feature BEING
    #: evaluated (EDGE-RESOLVE-WARN-1, :mod:`geometry.kernel.resolution`). PER-
    #: FEATURE SCRATCH, not tree state: :func:`_dispatch_one` installs a fresh
    #: tally before every dispatch and reads it into that feature's
    #: ``FeatureResult.subshape_resolution`` straight after, so no count can leak
    #: from one feature into the next, and a fork (which shares it) never reaches a
    #: later feature holding the old one. Handlers pass it as ``tally=`` to every
    #: resolver of a picked reference.
    subshape_tally: ResolutionTally = field(default_factory=ResolutionTally)
    #: The history-based face names of each body (DESIGN-INTENT-REFS,
    #: :mod:`geometry.kernel.naming`), keyed like :attr:`bodies`. Kept in step by
    #: the three body funnels below, which carry every body change through
    #: :func:`~geometry.kernel.naming.carry_names`, so no handler can leave a
    #: body with stale names; a face the map does not hold has no name.
    topo_names: dict[uuid.UUID, BodyNames] = field(
        default_factory=dict[uuid.UUID, BodyNames]
    )
    #: The volume of each body's CURRENT shape, where one is known, keyed like
    #: :attr:`bodies`: the operand volumes the boolean integrity guard bounds a
    #: result by (:mod:`geometry.kernel.boolean_guard`). A guarded boolean
    #: returns its result's volume, and the body funnel that installs the result
    #: records it, so a chain of booleans integrates each body once. Every funnel
    #: that installs a shape WITHOUT a volume drops the entry, so a value here
    #: always describes the shape in :attr:`bodies` (the funnels are the only
    #: writers of :attr:`bodies`). Read through :meth:`body_volume`.
    body_volumes: dict[uuid.UUID, float] = field(default_factory=dict[uuid.UUID, float])

    def body_volume(self, body_id: uuid.UUID) -> float:
        """The volume of body *body_id*'s current shape, integrated at most once."""
        known = self.body_volumes.get(body_id)
        if known is None:
            known = shape_volume(self.bodies[body_id])
            self.body_volumes[body_id] = known
        return known

    def _note_volume(self, body_id: uuid.UUID, volume: float | None) -> None:
        """Record (or, for ``None``, forget) the volume of a body just installed."""
        if volume is None:
            self.body_volumes.pop(body_id, None)
        else:
            self.body_volumes[body_id] = volume

    def face_names(self) -> list[str | None]:
        """The ACTIVE body's face names, aligned with ``active_body.faces()``
        (empty with no active body)."""
        active = self.active_body
        if active is None or self.active_body_id is None:
            return []
        names = self.topo_names.get(self.active_body_id)
        return (
            [None] * len(active.faces()) if names is None else names.face_names(active)
        )

    def record_cut_tools(self, feature_id: uuid.UUID, tools: list[Solid]) -> None:
        """Record the removal tool(s) an ok CUT feature just subtracted.

        The ONE write path for :attr:`last_cut_tools` (extrude-CUT and Hole today):
        a mirror or pattern that must replicate a removal replicates THESE solids —
        the exact tools that were cut, from the body they were cut from — rather
        than re-deriving them later. Called only after the cut succeeded, so the
        slot always describes material actually removed from the active body.

        DELIBERATELY UNCHANGED by the v2 mirror (mirror-semantics §6.2 — the single
        highest-risk hunk of that work). The v1 readers
        (:func:`_mirror_cut_tools` / :func:`_pattern_cut_tools`) share this ONE slot
        with two different documented rules, so widening it — e.g. letting the
        revolve/sweep/loft cuts that record nothing today write here — would
        silently change what a ``body``-scope mirror or a pattern reflects on trees
        that have shipped goldens and locks. v2's per-feature store
        (:meth:`record_feature_tools`) is therefore SEPARATE and additive: this slot
        keeps exactly today's write sites and exactly today's meaning, which makes
        the "v1 readers return an identical tool list" guarantee structural rather
        than measured. (Extending the cut slot to the other subtractive verbs is a
        real, separate improvement — filed in BACKLOG, not smuggled in here.)
        """
        self.last_cut_tools = tools
        self.last_cut_feature_id = feature_id
        self.last_cut_body_id = self.active_body_id

    def record_feature_tools(
        self,
        feature_id: uuid.UUID,
        op: ToolOp,
        tools: list[BodyShape],
        generated: NameHook = (),
    ) -> None:
        """Record ONE feature's reflectable contribution (mirror-semantics §2b).

        A no-op unless *feature_id* is in the opt-in capture set
        (:attr:`tool_scope_ids`), so an ordinary rebuild retains nothing extra.
        Called by every mirrorable verb AFTER its body op succeeded, so the record
        always describes material actually applied to :attr:`active_body_id`.
        *generated* is the feature's naming hook; each tool's face names are
        taken from it, so a repeat of the tool can name its copies.
        """
        if feature_id not in self.tool_scope_ids:
            return
        names = [tool_face_names(tool, generated) for tool in tools]
        self.record_feature_tool_groups(
            feature_id, [RecordedToolGroup(op, tools, list(names))]
        )

    def record_feature_tool_groups(
        self, feature_id: uuid.UUID, groups: list[RecordedToolGroup]
    ) -> None:
        """:meth:`record_feature_tools` for a feature with SEVERAL ops.

        Only a ``features``-scope mirror needs this: its contribution is the ordered
        sequence of (op, reflected tools) it applied, which a nested mirror replays
        per group (§4.6).
        """
        if feature_id not in self.tool_scope_ids:
            return
        self.feature_tools[feature_id] = RecordedFeatureTools(
            body_id=self.active_body_id, groups=groups
        )

    @property
    def active_body(self) -> BodyShape | None:
        """The current shape of the ACTIVE body, or ``None`` if no body yet.

        The single read every modifying handler and the topo-naming resolvers
        use in place of the former single ``body`` slot (§MB-0). A body is a
        single :class:`~build123d.Solid` OR a multi-lump
        :class:`~build123d.Compound` (§MB-4).
        """
        if self.active_body_id is None:
            return None
        return self.bodies[self.active_body_id]

    def _admit(self, shape: BodyShape, *consumed: BodyShape) -> BodyShape:
        """The INVALID-BODY GATE (CM-6) — every body enters ``bodies`` through here.

        A body OCCT itself calls invalid used to be tessellated into the viewport,
        measured for mass properties and written to STEP with every feature
        reporting ``ok`` (docs/QA-REVIEW.md QA-1: 31865.9587 mm^3 against an
        analytic 30793.6284, ``Shape.is_valid`` false). Nothing asked. This asks,
        once, at the ONE place a shape becomes part of the part — see
        :func:`geometry.kernel.healing.body_is_valid` for why the gate lives at this
        funnel and not in each of the twenty-odd kernel ops or at the export
        boundary.

        *consumed* names the operand body(-ies) this op transformed, and is what
        makes the gate PROPORTIONAL rather than O(features x faces): the check runs
        over the faces the op actually produced plus their neighbours
        (:func:`~geometry.kernel.healing.new_geometry_is_valid`, docs/PERF.md fix
        #2 — 22 % of an N=200 rebuild). Passing nothing keeps the whole-body check,
        which is what a body being STARTED (first extrude / ``merge=False`` /
        import) gets. The publish-time whole-body re-check in
        :func:`evaluate_tree` is unchanged and is what still makes "no invalid body
        reaches the viewport, mass properties or STEP" absolute.

        Raises:
            InvalidBodyError: ``BRepCheck`` rejects *shape*. :func:`_dispatch`
                turns it into a typed per-feature ``invalid_body`` error, so the
                tree stops at the offending feature and the last-good body — which
                this method has NOT overwritten — is what the viewport shows.
        """
        if not new_geometry_is_valid(shape, consumed):
            raise InvalidBodyError(
                "This feature produced a body OCCT rejects as an invalid solid "
                "(BRepCheck), so its volume, mesh and STEP export cannot be "
                "trusted. The part is left at the last valid feature."
            )
        return shape

    def set_active_body(
        self,
        shape: BodyShape,
        generated: NameHook = (),
        merged: Sequence[MergedFaces] = (),
        *,
        worked_on: BodyShape | None = None,
        volume: float | None = None,
    ) -> None:
        """Replace the ACTIVE body's current shape (a modifying feature result).

        Keeps the body's identity slot (its base feature id) so downstream refs
        keep resolving; asserts an active body exists (callers gate on it). The
        shape may be a single solid or a lump-count-preserving multi-lump
        Compound (§MB-4). Gated by :meth:`_admit` (CM-6). *generated* is the
        op's naming hook: the faces it created or modified, with their names;
        *merged* the faces its ``clean`` merged (:attr:`OpHistory.merged`).
        *worked_on* is the copy of the active body the op ran on, when it did
        not run on the body itself (a fillet, chamfer, draft or shell): the
        body's names and the provenance memo are re-anchored on that copy, face
        for face, so its untouched faces keep them. *volume* is *shape*'s volume
        when the op measured it (a guarded boolean), for :attr:`body_volumes`.
        """
        body_id = self.active_body_id
        assert body_id is not None, "no active body to modify"
        before = self.bodies[body_id]
        consumed = before if worked_on is None else worked_on
        self.bodies[body_id] = self._admit(shape, consumed)
        self._note_volume(body_id, volume)
        if worked_on is not None:
            # The result's untouched faces are the copy's: re-anchor what is
            # keyed on face identity (names, the provenance memo) on it.
            self.provenance.reanchor(before, worked_on)
            if body_id in self.topo_names:
                self.topo_names[body_id] = self.topo_names[body_id].fork(
                    before, worked_on
                )
        self._rename(body_id, shape, [body_id], generated, merged)

    def _rename(
        self,
        body_id: uuid.UUID,
        shape: BodyShape,
        sources: list[uuid.UUID],
        generated: NameHook,
        merged: Sequence[MergedFaces] = (),
    ) -> None:
        """Carry the names of the *sources* bodies onto *shape* (the new body)."""
        self.topo_names[body_id] = carry_names(
            shape,
            [self.topo_names[s] for s in sources if s in self.topo_names],
            generated,
            merged,
        )

    def start_body(
        self,
        base_id: uuid.UUID,
        shape: BodyShape,
        generated: NameHook = (),
        *,
        volume: float | None = None,
    ) -> None:
        """Insert a NEW body keyed by its base feature id and make it active.

        The second-body path (``merge=False`` / ``import`` / the first body): a
        body's identity IS its base feature id (§MB-0 Decision 1), so the key is
        the creating feature's id and it becomes the resolution target. Gated by
        :meth:`_admit` (CM-6) — including an IMPORTED body, which is the one shape
        the kernel did not build itself and so the one it should trust least.
        """
        self.bodies[base_id] = self._admit(shape)
        self._note_volume(base_id, volume)
        self.active_body_id = base_id
        self._rename(base_id, shape, [], generated)

    def combine_bodies(
        self,
        target_id: uuid.UUID,
        tool_id: uuid.UUID,
        shape: BodyShape,
        *,
        volume: float | None = None,
    ) -> None:
        """Replace two operand bodies with a boolean result (multi-body §MB-1).

        The operand-replacement mechanism of the ``boolean`` feature: the result
        TAKES OVER the target's identity slot — reusing ``bodies[target_id]``
        keeps target's base-feature id AND its tree-ordered insertion position, so
        every downstream ref to the surviving body keeps resolving — and the TOOL
        body is REMOVED from the set (consumed). The combined body becomes active.
        Callers verify both ids name distinct current bodies first. *shape* may be
        a single solid or a multi-lump Compound (a disjoint boolean, §MB-4). Gated
        by :meth:`_admit` (CM-6).
        """
        self.bodies[target_id] = self._admit(
            shape, self.bodies[target_id], self.bodies[tool_id]
        )
        del self.bodies[tool_id]
        self._note_volume(target_id, volume)
        self.body_volumes.pop(tool_id, None)
        self.active_body_id = target_id
        self._rename(target_id, shape, [target_id, tool_id], ())
        self.topo_names.pop(tool_id, None)

    def shape_slots(self) -> list[tuple[BodyShape, Callable[[BodyShape], None]]]:
        """EVERY kernel shape this state holds, each with a setter for its slot.

        THE one list of shape-bearing fields (PERF-REAL-2 review, DRY): both
        :meth:`fork` (which copies these and writes the copies back through the
        setters) and :meth:`_Checkpoint.detach` (which drops their triangulation)
        walk it, so a shape added here is forked AND detached, and a shape
        missing here is neither — which ``tests/test_rebuild_cache.py`` catches by
        walking the state generically and comparing. The order is fixed (bodies,
        last cut tools, captured feature tools, unfold body) so the combined copy
        in :func:`~geometry.kernel.fork.fork_shapes` is deterministic.

        The setters write INTO this state's containers, so only call them on a
        state whose containers are its own (see :meth:`fork`).
        """
        slots: list[tuple[BodyShape, Callable[[BodyShape], None]]] = []
        bodies = self.bodies
        for body_id, body in bodies.items():
            slots.append((body, functools.partial(bodies.__setitem__, body_id)))
        cut_tools = self.last_cut_tools
        if cut_tools is not None:
            for index, tool in enumerate(cut_tools):

                def set_cut(shape: BodyShape, index: int = index) -> None:
                    cut_tools[index] = cast(Solid, shape)

                slots.append((tool, set_cut))
        for recorded in self.feature_tools.values():
            for group in recorded.groups:
                for index, tool in enumerate(group.tools):
                    slots.append(
                        (tool, functools.partial(group.tools.__setitem__, index))
                    )
        if self.sheet_metal_unfold_body is not None:

            def set_unfold(shape: BodyShape) -> None:
                self.sheet_metal_unfold_body = shape

            slots.append((self.sheet_metal_unfold_body, set_unfold))
        return slots

    def fork(self, *, weigh: bool = False) -> tuple["EvaluationState", int]:
        """An independent copy of this state, and (if *weigh*) its heap bytes.

        The ladder primitive (PERF-REAL-2, :mod:`geometry.rebuild_cache`): every
        KERNEL shape the state holds (:meth:`shape_slots`) is copied in ONE
        :func:`~geometry.kernel.fork.fork_shapes` call, so shapes that share
        subshapes here (a body and the tool that cut it; the unfold body that IS
        the live body on an unrelieved part) still share them in the fork. Every
        container a later feature appends to is copied; the values inside the
        non-shape containers (solved sketches, planes, frozen sheet-metal records)
        are never mutated after insertion and are shared.
        """
        twin = dataclasses.replace(
            self,
            solved_sketches=dict(self.solved_sketches),
            sketch_planes=dict(self.sketch_planes),
            datum_planes=dict(self.datum_planes),
            bodies=dict(self.bodies),
            sheet_metal_defaults=dict(self.sheet_metal_defaults),
            bend_provenance=dict(self.bend_provenance),
            corner_reliefs=dict(self.corner_reliefs),
            last_cut_tools=(
                None if self.last_cut_tools is None else list(self.last_cut_tools)
            ),
            feature_tools={
                feature_id: RecordedFeatureTools(
                    body_id=recorded.body_id,
                    groups=[
                        RecordedToolGroup(group.op, list(group.tools), group.names)
                        for group in recorded.groups
                    ],
                )
                for feature_id, recorded in self.feature_tools.items()
            },
            scoped_feature_types=dict(self.scoped_feature_types),
            body_volumes=dict(self.body_volumes),
        )
        # The twin's containers are its own now, so its slots can be rewritten
        # with the copies without touching this state.
        slots = twin.shape_slots()
        forked = fork_shapes([shape for shape, _ in slots], weigh=weigh)
        for (_, put), copy in zip(slots, forked.shapes, strict=True):
            put(copy)
        # The provenance recorder is re-anchored on the copied bodies, so a face
        # still live keeps its (possibly not yet computed) fingerprint instead of
        # being fingerprinted again as a stranger (PERF-REAL-3 follow-up).
        twin.provenance = self.provenance.fork(
            [(body, twin.bodies[body_id]) for body_id, body in self.bodies.items()]
        )
        # Names are keyed by face identity, so they too are re-anchored on the
        # copies; a name the copy cannot map is dropped, never guessed.
        twin.topo_names = {
            body_id: names.fork(self.bodies[body_id], twin.bodies[body_id])
            for body_id, names in self.topo_names.items()
            if body_id in self.bodies
        }
        return twin, forked.nbytes

    def adopt(self, other: "EvaluationState") -> None:
        """Become *other*, field for field, keeping this object's identity.

        The dispatch loop's callers hold a reference to the state they passed in;
        swapping in a forked state at a ladder rung has to be visible through it.
        """
        for item in dataclasses.fields(self):
            setattr(self, item.name, getattr(other, item.name))


#: One feature handler: evaluate the item, record outputs on ``state``, and
#: return ``None`` on success or the per-feature error (§4.3). Geometry
#: outcomes are values, never exceptions. Handlers mutate ``state`` only on
#: the success path.
FeatureHandler = Callable[[EvaluatedFeatureInput, EvaluationState], FeatureError | None]


def _add_body(
    item: EvaluatedFeatureInput,
    state: EvaluationState,
    tool: Solid,
    *,
    merge: bool,
    generated: NameHook = (),
) -> FeatureError | None:
    """Apply an ADDITIVE body op under the multi-body merge rule (§MB-0 Dec. 2).

    ``merge=True`` with an active body fuses *tool* into it (today's single-body
    behaviour); ``merge=False``, or no active body yet, STARTS a new active body
    keyed by this feature's id (``item.id`` — the base-feature-keyed identity of
    §MB-0 Decision 1). ``state.bodies`` is mutated only on success (last-good
    semantics, §4.3). Shared by extrude/revolve/sweep/loft ADD (CLAUDE.md DRY).

    On success the tool is RECORDED as this feature's reflectable contribution
    (:meth:`EvaluationState.record_feature_tools`, opt-in) so a ``features``-scope
    mirror can reflect it and re-fuse — mirror-semantics §4.1. Recorded AFTER the
    body op so the record names the body the tool actually landed in (a base feature
    keys its own new body).
    """
    if merge and state.active_body_id is not None:
        active = state.active_body
        assert active is not None
        try:
            fused = combine_body_measured(
                active, tool, "add", body_volume=state.body_volume(state.active_body_id)
            )
        except BooleanError as exc:
            return FeatureError(code="boolean_failed", message=str(exc))
        state.set_active_body(fused.shape, generated, volume=fused.volume)
        state.record_feature_tools(item.id, "fuse", [tool], generated)
        return None
    state.start_body(item.id, tool, generated)
    state.record_feature_tools(item.id, "fuse", [tool], generated)
    return None


def _cut_active(
    state: EvaluationState,
    tool: Solid,
    *,
    feature_id: uuid.UUID,
    generated: NameHook = (),
) -> FeatureError | None:
    """Subtract *tool* from the ACTIVE body (a modifying op — §MB-0).

    The caller has already verified an active body exists (``no_prior_body``
    otherwise). ``state.bodies`` is mutated only on success (§4.3). A tool that
    cannot reach the body is the typed ``cut_removed_nothing`` (CM-3) — the same
    honesty the Hole feature has always had (``hole_off_body``), so a revolve /
    sweep / loft cut into free space is never a successful no-op.

    On success the removal tool is recorded TWICE, into the two stores that answer
    two different questions (and this is the ONE funnel where all three
    non-extrude cuts do it, so no verb can be forgotten):

    * :meth:`EvaluationState.record_cut_tools` — the v1 cut slot a ``body``-scope
      mirror and a ``pattern`` read. **Widened to these three verbs 2026-07-30**
      (CM-5): while they recorded nothing, a ``body``-scope mirror after a
      revolve/sweep/loft cut had no cut on record, took ``mirror_union``, and the
      reflection FILLED the void — measured on the matrix plate as the literal
      featureless brick (63999.999999999985 mm^3, **6 faces / 12 edges**, i.e. the
      bare 80x80x10 plate) where 62994.6904 / 62720.0 / 61973.3333 are correct.
      That is the FINDINGS #2 silent-wrong-geometry class, so rarity of the chain
      does not soften it. The widening is safe for existing trees because it only
      ADDS records for verbs that had none: neither reader's RULE changes, and
      both were measured to return an identical tool list on every chain the suite
      exercises (docs/GEOMETRY-QA.md 2026-07-30).
    * :meth:`EvaluationState.record_feature_tools` — the opt-in per-feature v2
      store a ``features``-scope mirror reflects (mirror-semantics §4.2).
    """
    active = state.active_body
    assert active is not None, "cut without an active body is handled by the caller"
    body_id = state.active_body_id
    assert body_id is not None
    try:
        cut = combine_body_measured(
            active, tool, "cut", body_volume=state.body_volume(body_id)
        )
        state.set_active_body(cut.shape, generated, volume=cut.volume)
    except CutRemovedNothingError as exc:
        return FeatureError(code="cut_removed_nothing", message=str(exc))
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))
    state.record_cut_tools(feature_id, [tool])
    state.record_feature_tools(feature_id, "cut", [tool], generated)
    return None
