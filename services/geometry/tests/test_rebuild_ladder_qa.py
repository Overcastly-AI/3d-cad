"""Independent geometry-QA gates for the rebuild-cache LADDER (PERF-REAL-2).

Written by geometry QA, not by the ladder's builder, against the claims in
``09416c6``: a rebuild that resumes from a ladder rung must be byte-identical to
a cold rebuild — the GLB, its content-addressed ``mesh_glb_id``, the mass
properties and topology counts, AND the STEP export — and an edit at feature *k*
must never resume from a rung that has seen feature *k*.

``tests/test_rebuild_cache.py`` already gates the edits on both sides of each rung
of the housing tray. This file widens the net in the three directions that suite
does not reach:

* **The STEP export.** The builder's gate compares the mesh; a rung is a
  ``BRepBuilderAPI_Copy``, and a copy that meshed identically but carried a
  different tolerance, pcurve or orientation would still move the exact B-rep a
  user exports. ``export_step_bytes`` is compared byte-for-byte.
* **A boolean tree whose operands SHARE faces.** Every boolean in the housing
  tray is a cut or boss well inside a face. :func:`shared_face_tree` is built from
  the cases that stress a copy instead: bodies whose faces coincide (a block
  unioned to a block it touches, a slab subtracted from the same outline, a
  pocket refilled by an extrude of its own profile, a pattern whose tools share
  one ``TShape`` at three locations). ``fork_shapes`` exists to keep that sharing
  across a copy; this is the tree that would notice if it did not.
* **Edit positions the builder's gate does not pick:** the FIRST feature, the
  LAST feature, a rung boundary exactly, and a feature BETWEEN rungs, plus an
  exhaustive walk of every position of the shared-face tree for the resume-length
  invariant alone.
* **The double fork.** The builder recorded that "fork once and continue on the
  original" passed their whole suite. It does NOT pass this one: a single
  ``BRepBuilderAPI_Copy`` moves the GLB (a glTF accessor bound by one ULP,
  ``0.020000000000000004`` -> ``0.02``, or a few denormal-level float words) on
  13 of 89 trees measured 2026-09-23, including this file's shared-face tree and
  the housing tray from 27 features up, while a copy of a copy is byte-identical
  to the copy. So under that mutant the byte gate goes red on the shared-face
  edits at 16, 23 and 25 and the housing edit at 27, and
  :func:`test_every_rung_climb_carries_on_with_a_copy_of_the_rung` checks the
  same guarantee structurally (docs/GEOMETRY-QA.md, 2026-09-23 entry).
"""

# reportPrivateUsage: the double-fork gate spies on the evaluator's private
# rung seam (`_climb_rung`, `_REBUILD_CACHE`, the ladder's `_rungs`) — the
# guarantee it checks lives there and has no public surface.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import importlib.util
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from geometry.features import evaluate as evaluate_module
from geometry.features.evaluate import (
    EvaluationState,
    _Checkpoint,
    evaluate_tree,
    rebuild_cache_stats,
    reset_rebuild_cache,
)
from geometry.kernel.export import export_step_bytes
from geometry.kernel.types import BodyShape
from geometry.rebuild_cache import RUNG_SPACING
from geometry.schemas import ShapeProperties
from loft_wire.features import EvaluateTreeRequest

_BUILDERS_PATH = Path(__file__).resolve().parent / "_big_part_builders.py"


def _load_builders() -> ModuleType:
    """Load the tree builders by file path (importlib import-mode: test modules
    cannot import each other by name — root pyproject.toml)."""
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILDERS = _load_builders()

_XY = {"kind": "datum_plane", "plane": "XY"}


def _uid(n: int) -> str:
    return str(uuid.UUID(int=0xA11E_0000 + n))


def _rect(x0: float, y0: float, x1: float, y1: float, tag: str) -> list[dict[str, Any]]:
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [
        {
            "id": f"{tag}{i}",
            "kind": "line",
            "start": {"x": pts[i][0], "y": pts[i][1]},
            "end": {"x": pts[(i + 1) % 4][0], "y": pts[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]


class _Tree:
    def __init__(self) -> None:
        self.features: list[dict[str, Any]] = []

    def add(self, feature: dict[str, Any]) -> str:
        feature_id = _uid(len(self.features) + 1)
        self.features.append({"id": feature_id, "feature": feature})
        return feature_id

    def sketch(self, plane: dict[str, Any], entities: list[dict[str, Any]]) -> str:
        return self.add(
            {
                "type": "sketch",
                "version": 1,
                "params": {"plane": plane, "entities": entities, "constraints": []},
            }
        )

    def extrude(
        self,
        profile: str,
        distance: float,
        operation: str = "add",
        *,
        direction: str = "normal",
        merge: bool = True,
    ) -> str:
        params: dict[str, Any] = {
            "profile": {"kind": "feature", "feature_id": profile},
            "distance_mm": distance,
            "operation": operation,
            "direction": direction,
        }
        if not merge:
            params["merge"] = False
        return self.add({"type": "extrude", "version": 1, "params": params})

    def boolean(self, operation: str, target: str, tool: str) -> str:
        return self.add(
            {
                "type": "boolean",
                "version": 1,
                "params": {
                    "operation": operation,
                    "target": {"kind": "feature", "feature_id": target},
                    "tool": {"kind": "feature", "feature_id": tool},
                },
            }
        )


def shared_face_tree() -> dict[str, Any]:
    """A 26-feature part made of booleans whose operands share faces.

    Rungs fall after 8, 16 and 24 features (``RUNG_SPACING`` = 8), so the tree
    has a feature on both sides of every rung, and the last two features (a
    notch flush with the part's y = 20 wall, cut from its own sketch) sit past
    the last rung. Every body-affecting feature is dimension-driven or refers to
    features by id — no picked-face signatures — so an edit anywhere, including
    feature 0, leaves every later feature resolvable.
    """
    t = _Tree()
    s0 = t.sketch(_XY, _rect(-30.0, -20.0, 30.0, 20.0, "a"))  # 0
    a = t.extrude(s0, 10.0)  # 1: body A, 60 x 40 x 10
    s1 = t.sketch(_XY, _rect(30.0, -10.0, 50.0, 10.0, "b"))  # 2
    b = t.extrude(s1, 10.0, merge=False)  # 3: body B, touches A on x = 30
    t.boolean("union", a, b)  # 4: coincident face x = 30 is internal
    s2 = t.sketch(_XY, _rect(-10.0, -8.0, 10.0, 8.0, "c"))  # 5
    c = t.extrude(s2, 10.0, merge=False)  # 6: body C, coplanar top AND bottom
    t.boolean("subtract", a, c)  # 7: through-window, walls from C's faces
    top = t.add(  # 8  <- rung 8 sits BEFORE this feature
        {
            "type": "datum",
            "version": 1,
            "params": {"kind": "offset", "base": "XY", "offset_mm": 10.0},
        }
    )
    top_plane = {"kind": "feature", "feature_id": top}
    s3 = t.sketch(top_plane, _rect(-26.0, -6.0, -16.0, 6.0, "d"))  # 9
    t.extrude(s3, 4.0, "cut", direction="reverse")  # 10: blind pocket
    t.extrude(s3, 6.0, "cut", direction="reverse")  # 11: same walls, deeper
    s4 = t.sketch(  # 12
        top_plane,
        [{"id": "h", "kind": "circle", "center": {"x": 42.0, "y": 0.0}, "radius": 2.5}],
    )
    t.extrude(s4, 10.0, "cut", direction="reverse")  # 13: hole through B
    t.add(  # 14: the hole's tool at three locations, one TShape
        {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "linear",
                    "direction": {"x": -1.0, "y": 0.0, "z": 0.0},
                    "spacing_mm": 7.0,
                    "count": 3,
                }
            },
        }
    )
    s5 = t.sketch(_XY, _rect(-30.0, -20.0, -20.0, 20.0, "e"))  # 15
    d = t.extrude(s5, 15.0, merge=False)  # 16 <- rung 16 sits BEFORE this
    t.boolean("union", a, d)  # 17: shares x = -30, y = +-20 and z = 0 planes
    s6 = t.sketch(_XY, _rect(-30.0, -20.0, 30.0, 20.0, "f"))  # 18: = sketch 0
    e = t.extrude(s6, 2.0, merge=False)  # 19: a slab on A's own outline
    t.boolean("subtract", a, e)  # 20: side walls coincide with A's
    s7 = t.sketch(top_plane, _rect(4.0, 10.0, 14.0, 16.0, "g"))  # 21
    t.extrude(s7, 3.0, "cut", direction="reverse")  # 22: pocket
    t.extrude(s7, 3.0, "add", direction="reverse")  # 23: refill it with its own tool
    s8 = t.sketch(_XY, _rect(-8.0, 12.0, 0.0, 20.0, "k"))  # 24 <- rung 24 before
    t.extrude(s8, 5.0, "cut", direction="normal")  # 25: notch flush with y = 20
    return {
        "part_id": str(uuid.UUID(int=0xA11E)),
        "tree_version": 1,
        "features": t.features,
    }


#: Positions of the shared-face tree the byte-identity gate edits: the first
#: feature, both sides of rung 8 (6 is the last DIMENSIONED feature inside it; 7
#: suppresses the subtract, which makes feature 10 fail — the failure path must
#: not be served rung 8 either), a rung boundary exactly (16), between rungs
#: (12), the last feature inside rung 24, and the last feature of the tree.
#: Every other edit leaves all 26 features ``ok``.
SHARED_FACE_EDITS = (0, 6, 7, 8, 9, 12, 16, 23, 25)

#: Housing tray long enough for three rungs, cut so its LAST feature is a pocket
#: extrude (a trailing sketch would make the last-feature edit a no-op).
#: Positions by role: the shell under everything, between rungs, a rung
#: boundary, a hole past rung 16, and the last feature.
HOUSING_N = 3 * RUNG_SPACING + 4
HOUSING_EDITS = (3, 12, 16, 20, HOUSING_N - 1)


def _housing() -> dict[str, Any]:
    return cast(dict[str, Any], _BUILDERS.housing_tree(HOUSING_N))


_TREES = {"shared-face": shared_face_tree, "housing": _housing}


def _edit(payload: dict[str, Any], index: int) -> dict[str, Any]:
    """*payload* with feature *index* changed so the answer changes.

    A sketch moves by 0.4 mm in x (every entity); a dimensioned feature shrinks
    3 %; a pattern's spacing shrinks 3 %; anything else is suppressed.
    """
    edited = copy.deepcopy(payload)
    feature = edited["features"][index]["feature"]
    params = feature.get("params", {})
    if feature["type"] == "sketch":
        for entity in params["entities"]:
            for key in ("start", "end", "center"):
                if key in entity:
                    entity[key]["x"] += 0.4
        return edited
    for name in (
        "distance_mm",
        "depth_mm",
        "diameter_mm",
        "radius_mm",
        "thickness_mm",
        "offset_mm",
        "angle_deg",
    ):
        value = params.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value:
            params[name] = value * 0.97
            return edited
    pattern = params.get("pattern")
    if isinstance(pattern, dict) and "spacing_mm" in pattern:
        pattern["spacing_mm"] *= 0.97
        return edited
    feature["suppressed"] = True
    return edited


@dataclass(frozen=True)
class Observed:
    """Everything a user can observe of one evaluation, for byte comparison."""

    statuses: tuple[str, ...]
    codes: tuple[str | None, ...]
    last_good: uuid.UUID | None
    mesh_glb_id: str | None
    glb: bytes | None
    properties: object
    step: bytes | None


def _observe(payload: dict[str, Any]) -> Observed:
    evaluation = evaluate_tree(EvaluateTreeRequest.model_validate(payload))
    result = evaluation.result
    return Observed(
        statuses=tuple(f.status for f in result.features),
        codes=tuple(f.error.code if f.error else None for f in result.features),
        last_good=result.last_good_feature_id,
        mesh_glb_id=result.mesh_glb_id,
        glb=evaluation.glb,
        properties=result.properties,
        step=None if evaluation.body is None else export_step_bytes(evaluation.body),
    )


def _cold(payload: dict[str, Any]) -> Observed:
    reset_rebuild_cache()
    observed = _observe(payload)
    reset_rebuild_cache()
    return observed


def _explain(warm: Observed, cold: Observed) -> str:
    fields = [
        name
        for name in Observed.__dataclass_fields__
        if getattr(warm, name) != getattr(cold, name)
    ]
    return f"resumed rebuild differs from a cold one in: {fields}"


def test_the_shared_face_tree_is_all_ok_and_one_body() -> None:
    """The fixture must be what its docstring says, or every gate below is vacuous:
    every feature ``ok`` (an error would stop the ladder at the failure), past
    three rungs, and every ``merge=False`` body consumed by its boolean — one
    shell at the end, so the union/subtract really ran on the shared faces."""
    observed = _cold(shared_face_tree())
    assert set(observed.statuses) == {"ok"}, observed.statuses
    assert observed.step is not None and observed.glb is not None
    assert len(observed.statuses) == 26
    assert len(observed.statuses) > 3 * RUNG_SPACING, "must pass three rungs"
    properties = cast(ShapeProperties, observed.properties)
    assert properties.topology.shells == 1


@pytest.mark.parametrize(
    ("tree", "index"),
    [("shared-face", i) for i in SHARED_FACE_EDITS]
    + [("housing", i) for i in HOUSING_EDITS],
)
def test_a_ladder_resume_is_byte_identical_to_cold_in_mesh_and_step(
    tree: str, index: int
) -> None:
    """Edit feature *index* of a tree whose ladder was built under the ORIGINAL
    keys; the resumed answer must equal a cold rebuild of the edited tree in
    every observable — GLB bytes, ``mesh_glb_id``, mass properties + topology,
    per-feature statuses, and the STEP export byte for byte — and it must have
    resumed from exactly the rung at or below *index*."""
    payload = _TREES[tree]()
    edited = _edit(payload, index)
    reference = _cold(edited)
    assert reference != _cold(payload), "the edit must change the answer"

    reset_rebuild_cache()
    _observe(payload)  # builds the ladder under the original keys
    before = rebuild_cache_stats()
    warm = _observe(edited)
    after = rebuild_cache_stats()

    assert warm == reference, _explain(warm, reference)
    expected = (index // RUNG_SPACING) * RUNG_SPACING
    assert after.resumed_features - before.resumed_features == expected
    assert after.rung_hits - before.rung_hits == (1 if expected else 0)


def test_no_edit_position_resumes_past_itself() -> None:
    """Exhaustive over the shared-face tree: an edit at EVERY index resumes from
    ``floor(k / 8) * 8`` — never from a rung that has seen feature *k*, and never
    from a shallower rung than it could (which would be a silent slowdown)."""
    payload = shared_face_tree()
    reset_rebuild_cache()
    _observe(payload)
    for index in range(len(payload["features"])):
        before = rebuild_cache_stats()
        evaluate_tree(EvaluateTreeRequest.model_validate(_edit(payload, index)))
        resumed = rebuild_cache_stats().resumed_features - before.resumed_features
        assert resumed == (index // RUNG_SPACING) * RUNG_SPACING, (index, resumed)
        assert resumed <= index


def _kernel_shapes(state: EvaluationState) -> list[BodyShape]:
    """Every kernel shape an evaluator state holds — the list ``fork`` copies."""
    shapes: list[BodyShape] = [*state.bodies.values(), *(state.last_cut_tools or ())]
    for recorded in state.feature_tools.values():
        for group in recorded.groups:
            shapes.extend(group.tools)
    if state.sheet_metal_unfold_body is not None:
        shapes.append(state.sheet_metal_unfold_body)
    return shapes


def _faces(shapes: list[BodyShape]) -> list[Any]:
    return [face.wrapped for shape in shapes for face in shape.faces()]


def _shares_a_face(a: list[BodyShape], b: list[BodyShape]) -> bool:
    """Whether any FACE of *a* has the same ``TShape`` as a face of *b*, at any
    location (``IsPartner``) — the sharing an in-place boolean rewrite travels
    through, which body-level identity alone would miss."""
    faces_b = _faces(b)
    return any(fa.IsPartner(fb) for fa in _faces(a) for fb in faces_b)


def test_every_rung_climb_carries_on_with_a_copy_of_the_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE DOUBLE-FORK GUARANTEE, structurally (PERF-REAL-2, ``_climb_rung``).

    After a rung the evaluation must carry on with a state that shares no face
    ``TShape`` with EITHER the state it arrived with (the ORIGINAL) or the STORED
    rung, and a resume must carry on with a fork of the rung, never the rung.

    * LIVE shares with ORIGINAL: "fork once and continue on the original". The
      cold path then carries un-copied shapes forward while a resume carries a
      copy — and a copy does NOT re-mesh like its original on this tree (the byte
      gate above goes red on edits 16, 23 and 25 under exactly that mutant).
    * LIVE shares with the RUNG: a later feature's in-place rewrite (CM-6b)
      edits the rung every future resume starts from.

    Deliberately NOT asserted: that the rung shares nothing with the original.
    Storing the original and carrying on with ONE fork of it is byte-equivalent
    (cold and resume both continue on a copy of the same state), so that would
    forbid a legitimate halving of the fork tax.

    Checked at the FACE level on every rung of the shared-face tree, cold and
    resumed: body-level ``IsSame`` would pass a state that re-wrapped a shared
    face in a new solid.
    """
    climbs: list[tuple[int, list[BodyShape], list[BodyShape], list[BodyShape]]] = []
    stored: list[_Checkpoint] = []
    resumes: list[tuple[list[BodyShape], list[BodyShape]]] = []
    cache = evaluate_module._REBUILD_CACHE
    real_climb = evaluate_module._climb_rung
    real_store = cache.store_rung
    real_take = cache.take

    def spy_store(*args: Any, **kwargs: Any) -> bool:
        stored.append(cast(_Checkpoint, args[2]))
        return real_store(*args, **kwargs)

    def spy_climb(position: int, state: EvaluationState, *args: Any) -> None:
        original = _kernel_shapes(state)
        count = len(stored)
        real_climb(position, state, *args)
        assert len(stored) == count + 1, "every climb must offer exactly one rung"
        climbs.append(
            (
                position,
                original,
                _kernel_shapes(stored[-1].state),
                _kernel_shapes(state),
            )
        )

    def spy_take(keys: Any) -> Any:
        resume = real_take(keys)
        if resume is not None and resume.rung:
            rung = cache._rungs[keys[resume.prefix_length]].checkpoint
            resumes.append(
                (_kernel_shapes(rung.state), _kernel_shapes(resume.checkpoint.state))
            )
        return resume

    monkeypatch.setattr(evaluate_module, "_climb_rung", spy_climb)
    monkeypatch.setattr(cache, "store_rung", spy_store)
    monkeypatch.setattr(cache, "take", spy_take)

    payload = shared_face_tree()
    reset_rebuild_cache()
    _observe(payload)
    _observe(_edit(payload, 19))  # resumes from rung 16, climbs rung 24 again

    assert [c[0] for c in climbs] == [8, 16, 24, 24], "the census of climbs"
    assert len(resumes) == 1, "the edit must have resumed from a rung"
    for position, original, rung, live in climbs:
        assert original and rung and live, f"rung {position}: an empty state"
        assert not _shares_a_face(original, live), (
            f"rung {position}: the evaluation carries on with the ORIGINAL "
            "(fork once, continue on the original)"
        )
        assert not _shares_a_face(rung, live), (
            f"rung {position}: the evaluation carries on with the stored rung itself"
        )
    for rung, handed_out in resumes:
        assert not _shares_a_face(rung, handed_out), "a resume was handed the rung"


def test_a_session_of_edits_stays_byte_identical_to_cold() -> None:
    """A modelling SESSION, not one edit: late edit, then an edit further up,
    then back to the original, then the late edit again. Each step resumes from
    whatever the previous steps left on the ladder or the frontier (including
    rungs stored by a resumed evaluation, not only by the cold one), and each
    must equal its own cold rebuild."""
    payload = shared_face_tree()
    steps = [
        payload,
        _edit(payload, 25),
        _edit(payload, 12),
        _edit(_edit(payload, 12), 20),
        payload,
        _edit(payload, 25),
        _edit(payload, 17),
    ]
    references = [_cold(step) for step in steps]
    reset_rebuild_cache()
    for number, (step, reference) in enumerate(zip(steps, references, strict=True)):
        warm = _observe(step)
        assert warm == reference, f"step {number}: {_explain(warm, reference)}"
    assert rebuild_cache_stats().rung_hits >= 4, "the session must exercise rungs"
