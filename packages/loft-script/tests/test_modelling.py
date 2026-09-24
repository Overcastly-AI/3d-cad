"""Model a real part from a script, against a real stack, and check the GEOMETRY.

The part is the one ``apps/web/e2e/full-flow.spec.ts`` builds through the
browser — a 40 x 25 mm rectangle on XY, extruded 10 mm — and the numbers
asserted here are the numbers that spec asserts on screen: 10 000 mm^3 and
40 x 25 x 10 mm extents. That is what makes this a two-path comparison rather
than a self-consistent restatement: if the scripting path reached anything the
browser path does not, one of the two would stop producing those numbers.

Nothing here asserts on a status code. A 2xx proves a request parsed; params
models are pydantic-default ``extra="ignore"``, so a misspelled field validates
and silently means the old thing (CLAUDE.md). Every assertion below is on a
result — a volume, a face count, a byte, an error code.
"""

from __future__ import annotations

import itertools
import math
import uuid
from typing import Any

import loft
import pytest
from loft._operation import Operation
from loft.sketch import SOLVED_STATUSES
from loft.transport import Transport
from loft_wire.features import ExtrudeFeature, SketchFeature
from loft_wire.sketch import SketchArc, SketchCircle, SketchLine
from pydantic import BaseModel

from .conftest import Stack

PASSWORD = "loft-script-passphrase"

#: The full-flow part. Named as constants because three tests assert on them
#: and a drifting literal is how two tests come to disagree about one part.
WIDTH_MM = 40.0
HEIGHT_MM = 25.0
DEPTH_MM = 10.0
EXPECTED_VOLUME_MM3 = WIDTH_MM * HEIGHT_MM * DEPTH_MM  # 10 000

#: OCCT's exact B-rep volume of a box is analytic; the tolerance is for float
#: formatting on the wire, not for modelling slop.
VOLUME_TOLERANCE_MM3 = 1e-6

_emails = (f"script-{n}@example.com" for n in itertools.count())


def _session(stack: Stack) -> loft.Session:
    return loft.register(stack.gateway_url, email=next(_emails), password=PASSWORD)


def _bracket(session: loft.Session, *, name: str = "Bracket") -> loft.Part:
    """The README's example, verbatim — the part a script is meant to write."""
    part = session.new_part(name)
    sketch = part.sketch(on="XY")
    sketch.rect(WIDTH_MM, HEIGHT_MM)
    sketch.solve()
    part.extrude(sketch, DEPTH_MM)
    return part


# --- the geometry -----------------------------------------------------------


def test_a_scripted_part_has_the_geometry_the_browser_builds(stack: Stack) -> None:
    """10 000 mm^3, 6 faces, 40 x 25 x 10 — the full-flow spec's own numbers."""
    with _session(stack) as session:
        part = _bracket(session)
        properties = part.mass_properties()

    assert properties.volume == pytest.approx(
        EXPECTED_VOLUME_MM3, abs=VOLUME_TOLERANCE_MM3
    )
    # A box has six planar faces and twelve edges. Asserting the TOPOLOGY as
    # well as the volume is what distinguishes "a solid of the right size" from
    # "the solid that was modelled": a 40 x 25 x 10 shape with 7 faces is a
    # different part that happens to displace the same amount.
    assert properties.topology.faces == 6
    assert properties.topology.edges == 12
    assert properties.topology.shells == 1

    box = properties.bounding_box
    assert (box.max.x - box.min.x) == pytest.approx(WIDTH_MM, abs=1e-9)
    assert (box.max.y - box.min.y) == pytest.approx(HEIGHT_MM, abs=1e-9)
    assert (box.max.z - box.min.z) == pytest.approx(DEPTH_MM, abs=1e-9)
    assert properties.surface_area == pytest.approx(
        2 * (WIDTH_MM * HEIGHT_MM + WIDTH_MM * DEPTH_MM + HEIGHT_MM * DEPTH_MM),
        abs=1e-6,
    )
    # No material assigned, so mass is honestly unknown — never zero.
    assert properties.mass_g is None
    assert properties.center_of_mass is None


def test_the_sketch_solves_to_the_analytic_rectangle(stack: Stack) -> None:
    """dof 0 and the exact corners: the anchor + dimensions really constrain it.

    Without this, ``rect()`` could be emitting a rigid-but-floating system and
    the extrude would still produce 10 000 mm^3 somewhere else in space.
    """
    with _session(stack) as session:
        part = session.new_part("Solved")
        sketch = part.sketch(on="XY")
        sketch.rect(WIDTH_MM, HEIGHT_MM)
        solved = sketch.solve()

    assert solved.status == "converged"
    assert solved.dof == 0
    assert solved.conflicting_constraints == []
    corners = [(0.0, 0.0), (WIDTH_MM, 0.0), (WIDTH_MM, HEIGHT_MM), (0.0, HEIGHT_MM)]
    for index, entity in enumerate(solved.entities):
        assert isinstance(entity, SketchLine)
        assert (entity.start.x, entity.start.y) == pytest.approx(
            corners[index], abs=1e-9
        )
        assert (entity.end.x, entity.end.y) == pytest.approx(
            corners[(index + 1) % 4], abs=1e-9
        )


def test_re_parametrizing_the_extrude_rebuilds_the_body(stack: Stack) -> None:
    """The live parametric loop, from a script: 10 mm -> 20 mm doubles the volume.

    The browser does this by retyping a number in the extrude editor; the API
    must reach the same place, or the scripting surface is write-once.
    """
    with _session(stack) as session:
        part = _bracket(session, name="Reparam")
        extrude = part.extrude
        assert extrude is not None  # keeps the name meaningful to a reader
        feature = next(
            record
            for record in part.features()
            if isinstance(record.feature, ExtrudeFeature)
        )
        part.set_extrude_distance(feature.id, 2 * DEPTH_MM)
        properties = part.mass_properties()

    assert properties.volume == pytest.approx(
        2 * EXPECTED_VOLUME_MM3, abs=VOLUME_TOLERANCE_MM3
    )


#: A twisted prism's flanks are B-spline fits of screw surfaces (fit tolerance
#: 1e-7 mm, docs/design/twisted-extrude.md), so its volume is not float-exact
#: like the box's. Measured first, then set: residual +2.5e-7 mm^3 on this part
#: (2026-09-24, 2.5e-11 relative); 5e-6 is 20x clear of it.
TWIST_VOLUME_TOLERANCE_MM3 = 5e-6
#: Centroids of the same part, measured the same way: residual <= 3.8e-10 mm;
#: 1e-8 is 26x clear. A mirrored twist moves centroid.y by 10.2 mm.
TWIST_CENTROID_TOLERANCE_MM = 1e-8


def test_a_twisted_extrude_reaches_the_kernel_and_can_be_straightened(
    stack: Stack,
) -> None:
    """``twist_angle_deg`` through the script path, asserted on the GEOMETRY.

    A misspelled or dropped field would validate and silently extrude straight
    (params models ignore extras), so the assertion is the centroid: the
    40 x 25 rectangle turns 30 deg about the sketch origin over 10 mm, so its
    centre (20, 12.5) sweeps an arc and the solid's centroid is that centre
    turned by the MEAN angle — counter-clockwise, because a positive twist is
    right-handed about +Z. Every slice is congruent, so the volume stays
    10 000 mm^3 (Cavalieri). Straightening it restores the box exactly.
    """
    theta = math.radians(30.0)
    cos_mean = math.sin(theta) / theta
    sin_mean = (1.0 - math.cos(theta)) / theta
    with _session(stack) as session:
        part = session.new_part("Twisted")
        sketch = part.sketch(on="XY")
        sketch.rect(WIDTH_MM, HEIGHT_MM)
        sketch.solve()
        feature = part.extrude(sketch, DEPTH_MM, twist_angle_deg=30.0)
        twisted = part.mass_properties()
        part.set_extrude_twist(feature.id, None)
        straight = part.mass_properties()

    cx, cy = WIDTH_MM / 2, HEIGHT_MM / 2
    assert twisted.volume == pytest.approx(
        EXPECTED_VOLUME_MM3, abs=TWIST_VOLUME_TOLERANCE_MM3
    )
    assert twisted.centroid.x == pytest.approx(
        cx * cos_mean - cy * sin_mean, abs=TWIST_CENTROID_TOLERANCE_MM
    )
    assert twisted.centroid.y == pytest.approx(
        cx * sin_mean + cy * cos_mean, abs=TWIST_CENTROID_TOLERANCE_MM
    )
    assert straight.volume == pytest.approx(
        EXPECTED_VOLUME_MM3, abs=VOLUME_TOLERANCE_MM3
    )
    assert straight.centroid.x == pytest.approx(cx, abs=VOLUME_TOLERANCE_MM3)
    assert straight.centroid.y == pytest.approx(cy, abs=VOLUME_TOLERANCE_MM3)


# --- export -----------------------------------------------------------------


def test_step_and_stl_export_real_files(stack: Stack, tmp_path: Any) -> None:
    """Assert on the BYTES, not on the 200: a zero-byte success is the worst
    failure shape there is, and every digest downstream would agree with it."""
    with _session(stack) as session:
        part = _bracket(session, name="Exported")
        step_path = part.export(tmp_path / "bracket.step")
        stl = part.export_bytes("stl")

    step = step_path.read_bytes()
    assert step.startswith(b"ISO-10303-21;")
    assert b"END-ISO-10303-21;" in step
    # The file is named after the PART, so what lands in a vendor's Downloads is
    # a product name rather than a uuid.
    assert b"Exported" in step
    assert len(step) > 1000

    # A binary STL is an 80-byte header, a uint32 triangle count, then 50 bytes
    # per triangle. A box tessellates to 12 triangles; deriving the length from
    # the count is what proves the payload is a mesh rather than a header.
    assert len(stl) > 84
    triangles = int.from_bytes(stl[80:84], "little")
    assert triangles == 12
    assert len(stl) == 84 + 50 * triangles


def test_export_infers_the_format_from_the_suffix(stack: Stack, tmp_path: Any) -> None:
    with _session(stack) as session:
        part = _bracket(session, name="Suffixed")
        written = part.export(tmp_path / "bracket.stl")
        assert int.from_bytes(written.read_bytes()[80:84], "little") == 12
        with pytest.raises(ValueError, match="cannot infer an export format"):
            part.export(tmp_path / "bracket.dwg")


# --- refusals: the API must stop where the UI stops --------------------------


def test_an_unauthenticated_call_is_refused(stack: Stack) -> None:
    """No token, no parts — the same 401 a browser without a session gets."""
    anonymous = loft.Session(Transport(stack.gateway_url))
    with anonymous, pytest.raises(loft.AuthenticationError) as caught:
        anonymous.parts()
    assert caught.value.status == 401


def test_a_bad_token_is_refused(stack: Stack) -> None:
    session = loft.connect(stack.gateway_url, token="not-a-jwt")
    with session, pytest.raises(loft.AuthenticationError):
        session.parts()


def test_another_users_part_is_not_found(stack: Stack) -> None:
    """Ownership is the gateway's, and a script does not get around it.

    404 rather than 403 deliberately: telling a caller that a part exists but is
    not theirs is an enumeration oracle.
    """
    with _session(stack) as owner:
        part = owner.new_part("Private")
        part_id = part.id
    with _session(stack) as stranger, pytest.raises(loft.NotFound):
        stranger.part(part_id).refresh()


def test_a_non_positive_extrude_distance_is_refused(stack: Stack) -> None:
    """``ExtrudeParamsV1.distance_mm`` is ``gt=0`` — the browser's validator.

    Raised client-side by the shared DTO, which is the DRY payoff: the script
    gets the same refusal without a round trip, and cannot construct a payload
    the server would have rejected.
    """
    with _session(stack) as session:
        part = _bracket(session, name="BadThickness")
        sketch = part.sketches()[0]
        with pytest.raises(ValueError):
            part.extrude(sketch, 0)
        with pytest.raises(ValueError):
            part.extrude(sketch, -5)


def test_an_unsolvable_sketch_is_refused_with_the_conflicting_constraints(
    stack: Stack,
) -> None:
    """Two contradictory dimensions on one edge: 40 mm AND 60 mm.

    The workspace leaves extrude disabled here. The library raises, carrying the
    indices of the constraints that conflict, so a caller (or an agent) can name
    the offending line instead of re-deriving it.
    """
    with _session(stack) as session:
        part = session.new_part("Conflicting")
        sketch = part.sketch(on="XY")
        rect = sketch.rect(WIDTH_MM, HEIGHT_MM)
        sketch.distance(rect.bottom, 60.0)  # contradicts the 40 mm already there
        with pytest.raises(loft.SketchNotSolved) as caught:
            sketch.solve()

    error = caught.value
    # The GEOMETRY SERVICE's own code, not this library's generic one. A
    # contradictory sketch arrives as a feature ERROR carrying a typed
    # `sketch_diagnosis` — the solved-payload route only ever reports the
    # redundant-but-solvable kind, because an unsolvable system has no geometry
    # to return — and passing that code straight through is what lets an MCP
    # caller branch on the same string the workspace branches on.
    assert error.code == "sketch_conflicting"
    assert error.solve_status == "conflicting"
    # The indices index the constraint list AS AUTHORED, so a caller can name
    # the offending line. Constraint 9 is the rect's 40 mm width dimension
    # (0-3 coincident, 4-7 H/V, 8 the anchor) and 11 is the 60 mm added above.
    assert 11 in error.conflicting_constraints, error.conflicting_constraints
    assert error.details is not None and error.details["removable"] is False
    payload = error.as_dict()
    assert payload["code"] == "sketch_conflicting"
    assert payload["solve_status"] == "conflicting"
    assert payload["conflicting_constraints"] == list(error.conflicting_constraints)


def test_an_open_profile_cannot_be_extruded(stack: Stack) -> None:
    """Three sides of a rectangle: the solver is happy, the kernel is not.

    A feature failure arrives on a **200** with per-feature statuses, so this is
    the library turning a red row in the tree into a refusal a script cannot
    walk past — and the code is the geometry service's own.
    """
    with _session(stack) as session:
        part = session.new_part("OpenProfile")
        sketch = part.sketch(on="XY")
        a = sketch.line((0, 0), (40, 0))
        b = sketch.line((40, 0), (40, 25))
        c = sketch.line((40, 25), (0, 25))
        sketch.coincident((a, "end"), (b, "start"))
        sketch.coincident((b, "end"), (c, "start"))
        sketch.fixed((a, "start"))
        sketch.solve()
        part.extrude(sketch, DEPTH_MM)

        with pytest.raises(loft.FeatureFailed) as caught:
            part.mass_properties()

    assert caught.value.code
    assert caught.value.feature_id
    assert caught.value.as_dict()["feature_id"] == caught.value.feature_id


def test_a_sketch_only_part_has_no_body_to_export_or_measure(stack: Stack) -> None:
    """The UI shows "No body" and disables export; the library raises NoBody.

    Returning ``None`` would let a script write a zero-byte STEP and call it a
    part.
    """
    with _session(stack) as session:
        part = session.new_part("SketchOnly")
        sketch = part.sketch(on="XY")
        sketch.rect(WIDTH_MM, HEIGHT_MM)
        sketch.solve()

        with pytest.raises(loft.NoBody):
            part.mass_properties()
        with pytest.raises(loft.NoBody):
            part.export_bytes("step")

        # ...and the evaluate it rests on is NOT an error: a sketch-only tree
        # evaluates cleanly with no body, which is the honest protocol state.
        evaluation = part.evaluate()
        assert evaluation.ok
        assert evaluation.properties is None


# --- reconstruction: what the MCP server will need ---------------------------


def test_every_handle_can_be_rebuilt_from_an_id_alone(stack: Stack) -> None:
    """An agent's next tool call gets an id and nothing else. Prove that is enough.

    Rebuilds the part, the sketch and the tree from ids across a FRESH session,
    then edits the rebuilt sketch and reads the geometry back — the cheap
    version of "no hidden session state" would have been asserting the objects
    exist, which proves nothing about whether they still work.
    """
    with _session(stack) as first:
        part = _bracket(first, name="Rebuildable")
        part_id = part.id
        sketch_id = part.sketches()[0].id
        token = first.token

    with loft.connect(stack.gateway_url, token=token) as resumed:
        rebuilt = resumed.part(part_id)
        assert rebuilt.name == "Rebuildable"
        sketch = rebuilt.sketch_by_id(sketch_id)
        assert len(sketch.entities) == 4
        assert len(sketch.constraints) == 11

        # Retype the width: 40 -> 60. The re-saved sketch re-solves and the
        # body follows, from a handle that carried no memory of its authoring.
        for constraint in sketch.constraints:
            if getattr(constraint, "kind", None) == "distance" and (
                getattr(constraint, "value_mm", None) == WIDTH_MM
            ):
                object.__setattr__(constraint, "value_mm", 60.0)
        sketch.save()
        properties = rebuilt.mass_properties()

    assert properties.volume == pytest.approx(
        60.0 * HEIGHT_MM * DEPTH_MM, abs=VOLUME_TOLERANCE_MM3
    )


def test_a_part_id_string_is_accepted_as_well_as_a_uuid(stack: Stack) -> None:
    """Agents pass strings; ids round-trip through JSON as strings."""
    with _session(stack) as session:
        part = session.new_part("Stringly")
        assert session.part(str(part.id)).name == "Stringly"
        assert isinstance(session.part(str(part.id)).id, uuid.UUID)


def test_the_tree_version_cache_is_an_optimisation_not_a_requirement(
    stack: Stack,
) -> None:
    """Two handles to one part, editing in turn; neither may lose a write.

    This is the concurrency shape an agent produces by accident — one tool call
    per handle, each holding a version it saw earlier. The stale one must
    refetch and retry, not fail.
    """
    with _session(stack) as session:
        part = _bracket(session, name="Concurrent")
        stale = session.part(part.id)
        stale.tree()  # prime the cache

        part.rename("Renamed once")  # moves the version under `stale`
        stale.rename("Renamed twice")  # must recover, not raise

        assert part.name == "Renamed twice"


# --- the structural claim: only declared routes, only declared payloads ------


class _Recorder(Transport):
    """A transport that records every (operation, body model) it is asked for."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[Operation, str | None]] = []

    def _send(self, operation: Operation, **kwargs: Any) -> Any:  # type: ignore[override]
        body: BaseModel | None = kwargs.get("body")
        self.calls.append((operation, type(body).__name__ if body else None))
        return super()._send(operation, **kwargs)


def test_every_call_the_library_makes_is_a_declared_operation(stack: Stack) -> None:
    """The "another client of the gateway, not a second product" claim, measured.

    Drives the whole modelling flow and then asserts, over the calls that
    ACTUALLY happened, that each names an operation in the generated table and
    carries the body model the contract declares for it. The count floor is not
    decoration: an empty recording would make both assertions vacuously true,
    which is the failure this repo keeps paying for.
    """
    from loft._operations import OPERATIONS

    recorder = _Recorder(stack.gateway_url)
    session = loft.register(stack.gateway_url, email=next(_emails), password=PASSWORD)
    recorder.token = session.token
    session.close()

    with loft.Session(recorder) as scripted:
        part = _bracket(scripted, name="Recorded")
        part.mass_properties()
        part.export_bytes("step")
        part.tree()
        part.rename("Recorded again")

    # Eight is what the flow above costs today: create part, create sketch,
    # evaluate (the solve), create extrude, evaluate (mass properties), export,
    # tree, rename. A floor rather than an equality so adding a verb does not
    # fail it — but a floor with a NUMBER in it, because an empty recording
    # would make the loop below vacuously true, which is the failure mode this
    # repo keeps paying for.
    assert len(recorder.calls) >= 8, (
        f"only {len(recorder.calls)} calls recorded; too few to mean anything"
    )
    reached: set[str] = set()
    for operation, body_model in recorder.calls:
        assert OPERATIONS.get(operation.operation_id) is operation, (
            f"{operation.method} {operation.path} is not in the generated table"
        )
        assert operation.request_model == body_model, (
            f"{operation.operation_id} declares {operation.request_model!r} but "
            f"the library sent {body_model!r}"
        )
        reached.add(operation.operation_id)

    # The flow must have touched every layer, or the parity check above only
    # covered the easy half.
    assert {
        "create_part_api_v1_parts_post",
        "create_feature_api_v1_parts__part_id__features_post",
        "evaluate_part_api_v1_parts__part_id__evaluate_post",
        "export_part_api_v1_parts__part_id__export_post",
    } <= reached


def test_the_scripted_tree_is_the_shape_the_browser_persists(stack: Stack) -> None:
    """Two features, in order, with the envelope types the workspace writes.

    The tree is what a browser opening this part would render, so a script that
    produced a tree the UI cannot read would have diverged even with identical
    geometry.
    """
    with _session(stack) as session:
        part = _bracket(session, name="Shaped")
        features = part.features()
        tree = part.tree()

    assert [record.order_index for record in features] == [0, 1]
    assert isinstance(features[0].feature, SketchFeature)
    assert isinstance(features[1].feature, ExtrudeFeature)
    assert features[0].feature.version == 1
    assert features[1].feature.params.operation == "add"
    assert features[1].feature.params.profile.feature_id == features[0].id
    assert features[1].feature.params.distance_mm == DEPTH_MM
    assert tree.rollback_feature_id is None
    assert not any(record.rolled_back for record in features)


# --- the public methods that had no test at all -----------------------------
#
# ``delete_feature`` 422'd on EVERY call, for every input, from the day it
# shipped: it omitted the ``expected_tree_version`` the route declares as a
# REQUIRED query parameter, and a DELETE has no body, so the contract check that
# guards every other write had nothing to look at. Nothing caught it because the
# method had no test — and the call-parity floor could not help, since a method
# nobody calls contributes no calls to count.
#
# It was one of seven public methods in that position. The others are covered
# here in the same pass, on the principle that the class of defect is "a public
# method nobody exercises", not "this one method".


def test_delete_feature_removes_it_and_the_body_follows(stack: Stack) -> None:
    """P0 REGRESSION. Asserts on the RESULT — the tree and the geometry — never
    on a status: a 2xx proves a request parsed, which is exactly what this bug
    did not do (it 422'd), and the inverse mistake would hide the next one."""
    with _session(stack) as session:
        part = _bracket(session, name="Deletable")
        assert part.mass_properties().volume == pytest.approx(
            EXPECTED_VOLUME_MM3, abs=VOLUME_TOLERANCE_MM3
        )

        extrude = next(f for f in part.features() if f.feature.type == "extrude")
        part.delete_feature(extrude.id)

        remaining = part.features()
        assert [f.feature.type for f in remaining] == ["sketch"]
        # The body is GONE, not merely unlisted: a sketch-only part has nothing
        # to measure, which is the same refusal the workspace shows.
        with pytest.raises(loft.NoBody):
            part.mass_properties()


def test_delete_feature_leaves_the_version_usable_for_the_next_write(
    stack: Stack,
) -> None:
    """The half a "does it 2xx?" test would miss.

    ``delete_feature`` carries the concurrency token in the QUERY, and the route
    returns the surviving tree, so the handle must come back holding the NEW
    version. If it kept the pre-delete one, the next write would 409 — a bug
    that only appears on the *second* call and would survive any single-call
    test.
    """
    with _session(stack) as session:
        part = _bracket(session, name="Sequential")
        extrude = next(f for f in part.features() if f.feature.type == "extrude")
        part.delete_feature(extrude.id)

        part.rename("Renamed after delete")
        assert part.name == "Renamed after delete"


def test_delete_feature_is_refused_when_a_later_feature_depends_on_it(
    stack: Stack,
) -> None:
    """The extrude consumes the sketch, so deleting the sketch must be refused —
    the library stops where the UI stops."""
    with _session(stack) as session:
        part = _bracket(session, name="Dependent")
        sketch = next(f for f in part.features() if f.feature.type == "sketch")
        # `Conflict`, not `LoftError`. Measured: the first draft of this test
        # caught the base class, and it therefore PASSED against the broken
        # method, whose 422 `InvalidRequest` is also a `LoftError` — a refusal
        # test that cannot tell "the server refused for the right reason" from
        # "my request was malformed" is the one shape this whole commit is
        # about.
        with pytest.raises(loft.Conflict) as raised:
            part.delete_feature(sketch.id)
        assert raised.value.code is not None
        # ...and nothing was removed.
        assert len(part.features()) == 2


def test_update_feature_replaces_the_envelope_wholesale(stack: Stack) -> None:
    """Named for the property that matters: params are REPLACED, not merged, so
    a caller who omits a field gets the model's default rather than the old
    value. Asserted on the geometry, which is the only place the difference
    shows."""
    with _session(stack) as session:
        part = _bracket(session, name="Updatable")
        record = next(f for f in part.features() if f.feature.type == "extrude")
        params = record.feature.params

        part.update_feature(
            record.id,
            feature=record.feature.model_copy(
                update={"params": params.model_copy(update={"distance_mm": 30.0})}
            ),
            name="Taller",
        )

        assert part.mass_properties().volume == pytest.approx(
            WIDTH_MM * HEIGHT_MM * 30.0, abs=VOLUME_TOLERANCE_MM3
        )
        assert [f.name for f in part.features() if f.feature.type == "extrude"] == [
            "Taller"
        ]


def test_set_units_changes_display_only_and_not_the_geometry(stack: Stack) -> None:
    """The claim in its docstring, measured. Storage is canonical mm, so the
    volume must be BYTE-identical across the change — a units bug that scaled
    the model would be invisible to a test that only read the unit back."""
    with _session(stack) as session:
        part = _bracket(session, name="Unitful")
        before = part.mass_properties().volume

        record = part.set_units("in")

        assert record.length_unit == "in"
        assert part.mass_properties().volume == before


def test_deleting_a_part_removes_it_from_the_register(stack: Stack) -> None:
    with _session(stack) as session:
        part = session.new_part("Doomed")
        part_id = part.id
        assert part_id in {p.id for p in session.parts()}

        part.delete()

        assert part_id not in {p.id for p in session.parts()}
        # `refresh()`, not `.name`: both fetch, but a bare property access is a
        # statement ruff reads as dead code (B018), and a reader would have to
        # know `.name` is a round trip to see why it is here.
        with pytest.raises(loft.NotFound):
            session.part(part_id).refresh()


def test_an_arc_dimensioned_by_radius_solves_to_that_radius(stack: Stack) -> None:
    """Covers ``Sketch.arc``, ``Sketch.radius`` and ``Sketch.constrain`` in one
    part — ``radius`` is sugar over ``constrain``, and an arc is the entity a
    radius dimension exists for.

    Asserts on the SOLVED geometry rather than on what was sent: a constraint
    the solver ignored and a constraint it satisfied are indistinguishable in
    the request.
    """
    with _session(stack) as session:
        part = session.new_part("Arcs")
        sketch = part.sketch(on="XY")
        arc = sketch.arc(center=(0.0, 0.0), start=(10.0, 0.0), end=(0.0, 10.0))
        index = sketch.radius(arc, 12.0)
        assert index == len(sketch.constraints) - 1

        solved = sketch.save().solved
        assert solved is not None
        # `underconstrained` here, and that is correct: the arc's centre is not
        # anchored, so the system has free DOF. It is in SOLVED_STATUSES — the
        # same set the workspace uses to enable extrude — and the dimension is
        # satisfied regardless, which is what the measurement below pins.
        assert solved.status in SOLVED_STATUSES

        entity = next(e for e in solved.entities if e.id == arc)
        assert isinstance(entity, SketchArc)
        # An arc carries no radius field — it is IMPLIED by |start - center|,
        # which is exactly why this reads the solved points rather than echoing
        # back the number that was sent.
        measured = math.hypot(
            entity.start.x - entity.center.x, entity.start.y - entity.center.y
        )
        assert measured == pytest.approx(12.0, abs=1e-6)


def test_a_circle_dimensioned_by_diameter_solves_to_half_that_radius(
    stack: Stack,
) -> None:
    """``Sketch.diameter`` — the one whose whole reason for existing is that a
    hole is specified by diameter everywhere except in the kernel. The bug it
    guards against is a factor of two, so the assertion is the radius.
    """
    with _session(stack) as session:
        part = session.new_part("Holes")
        sketch = part.sketch(on="XY")
        circle = sketch.circle(center=(0.0, 0.0), radius=3.0, dimension=False)
        sketch.diameter(circle, 20.0)

        solved = sketch.save().solved
        assert solved is not None
        assert solved.status in SOLVED_STATUSES

        entity = next(e for e in solved.entities if e.id == circle)
        assert isinstance(entity, SketchCircle)
        assert entity.radius == pytest.approx(10.0, abs=1e-6)
