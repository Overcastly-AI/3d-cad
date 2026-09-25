"""Stage-1 edge signatures + picked-edge resolution (kernel level).

Covers geometry.kernel.edges: the edge fingerprint (curve / endpoints / midpoint
/ length), the exactly-one-or-error resolver, and the picked-edge selector — the
SECOND SubshapeRef consumer (docs/design/topological-naming.md §2b/§4/§10),
mirroring test_faces.py. The HEADLINE gate is the same-enumeration guarantee:
the signature the selection overlay hands a client (the pick side) is
byte-for-byte the one the resolver matches against (the resolve side), so a
picked edge resolves back to itself — the measurement/faces order-equality
lesson applied to edges.

Unlike faces, edge ``subshape_ambiguous`` IS reachable on real bodies (a
symmetric part's congruent edges), so it is tested against a genuine solid, not
a monkeypatched enumeration.

Tolerances are the documented kernel bound, never ad-hoc epsilons: a box is
line-exact in OCCT, so deviation from analytic is round-off only.
"""
# The OCP wheel ships no type stubs, so raw build123d shape calls (``.is_same``,
# ``.cut``) are opaque to pyright; the directive scopes that relaxation to this
# file, exactly as the kernel modules and the other builder-using suites do.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false

import math
from typing import Any

import pytest
from build123d import GeomType, Location, Solid
from geometry.kernel import (
    EdgeRecord,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    edge_signature_dto,
    enumerate_edges,
    enumerate_edges_with_adjacency,
    resolve_edge,
    resolve_edge_durable,
    select_edges,
    selection_overlay,
)
from geometry.kernel.edges import (
    edge_signatures_match,
)
from geometry.kernel.faces import match_face_records, planar_faces
from geometry.kernel.types import BodyShape
from loft_wire.features import (
    AllEdgesSelector,
    EdgeSelectorV1,
    EdgeSignature,
    EdgeSubshapeRef,
    PickedEdgesSelector,
)
from loft_wire.geometry import Vec3

#: Kernel linear tolerance (CLAUDE.md 1e-7) — a ceiling, not a fit.
TOL = 1e-7

FEATURE_ID = "00000000-0000-0000-0000-0000000ed002"


def _box() -> Solid:
    """A 40x25x10 box at the origin (base of the selective-fillet golden)."""
    return Solid.make_box(40.0, 25.0, 10.0)


def _front_top_edge_signature() -> EdgeSignature:
    """The analytic signature of the box's front-top edge (y=0, z=10, length 40)."""
    return EdgeSignature(
        curve="line",
        end_a=Vec3(x=0.0, y=0.0, z=10.0),
        end_b=Vec3(x=40.0, y=0.0, z=10.0),
        midpoint=Vec3(x=20.0, y=0.0, z=10.0),
        length_mm=40.0,
    )


def _mid(edge: Any) -> tuple[float, float, float]:
    """The (x, y, z) midpoint of an edge as a plain tuple (for approx compares)."""
    point = edge @ 0.5
    return (point.X, point.Y, point.Z)


def _picked(signature: EdgeSignature) -> PickedEdgesSelector:
    return PickedEdgesSelector(
        kind="edges",
        refs=[
            EdgeSubshapeRef(
                kind="subshape",
                feature_id=FEATURE_ID,  # pyright: ignore[reportArgumentType]
                subshape_type="edge",
                selector=EdgeSelectorV1(signature=signature),
            )
        ],
    )


# --- signatures ------------------------------------------------------------------


def test_box_has_twelve_line_edge_signatures() -> None:
    records = enumerate_edges(_box())
    assert len(records) == 12  # a box has twelve edges
    assert all(r.signature.curve == "line" for r in records)
    # every straight edge is signed by length 40 (x-edges), 25 (y) or 10 (z)
    assert {round(r.signature.length_mm, 6) for r in records} == {40.0, 25.0, 10.0}


def test_endpoints_are_canonically_ordered() -> None:
    """end_a <= end_b lexicographically, so the signature is independent of the
    topological orientation OCCT assigned the edge (RESEARCH §9 determinism)."""
    for record in enumerate_edges(_box()):
        sig = record.signature
        a = (sig.end_a.x, sig.end_a.y, sig.end_a.z)
        b = (sig.end_b.x, sig.end_b.y, sig.end_b.z)
        assert a <= b


def test_circle_edge_signature_is_curve_circle() -> None:
    """A cylinder's circular cap edges are curve='circle' (a rendering + match
    discriminator); length is the circumference."""
    cylinder = Solid.make_cylinder(10.0, 25.0)
    records = enumerate_edges(cylinder)
    circles = [r for r in records if r.signature.curve == "circle"]
    assert circles  # the two caps are full circles
    circumference = 2 * 3.141592653589793 * 10.0
    for record in circles:
        assert record.signature.length_mm == pytest.approx(circumference, abs=1e-6)
    # cross-check curve kind vs the raw geom_type
    for edge, record in zip(cylinder.edges(), records, strict=True):
        is_circle = edge.geom_type == GeomType.CIRCLE
        expected = "circle" if is_circle else record.signature.curve
        assert record.signature.curve == expected


# --- resolution ------------------------------------------------------------------


def test_resolve_front_top_edge_is_unique() -> None:
    edge = resolve_edge(_box(), _front_top_edge_signature())
    # the resolved edge is a straight edge of length 40 at y=0, z=10
    assert edge.length == pytest.approx(40.0, abs=TOL)
    assert _mid(edge) == pytest.approx((20.0, 0.0, 10.0), abs=TOL)


def test_resolve_is_deterministic_across_rebuilds() -> None:
    """The same signature against a freshly rebuilt body resolves to the same
    edge midpoint — the edge reference survives a rebuild (topo-naming §7.5)."""
    target = _front_top_edge_signature()
    a = resolve_edge(_box(), target) @ 0.5
    b = resolve_edge(_box(), target) @ 0.5
    assert (a.X, a.Y, a.Z) == (b.X, b.Y, b.Z)


def test_unmatched_signature_is_subshape_unresolved() -> None:
    """A signature no edge matches (wrong midpoint) is an honest error, not a
    wrong edge — the 'no longer exists after the rebuild' path (§5)."""
    stale = EdgeSignature(
        curve="line",
        end_a=Vec3(x=0.0, y=0.0, z=99.0),
        end_b=Vec3(x=40.0, y=0.0, z=99.0),
        midpoint=Vec3(x=20.0, y=0.0, z=99.0),  # no edge at z=99
        length_mm=40.0,
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge(_box(), stale)


def test_curve_kind_discriminates_a_line_from_an_arc() -> None:
    """A 'circle' signature never matches a straight box edge even when the point
    fields are near — curve family is a match field, not a hint here."""
    line_sig = _front_top_edge_signature()
    arc_sig = line_sig.model_copy(update={"curve": "circle"})
    assert not edge_signatures_match(line_sig.model_copy(), arc_sig)


def test_congruent_edges_are_subshape_ambiguous(monkeypatch: Any) -> None:
    """The exactly-one rule refuses to guess between two edges that share a
    signature (§7.2), rather than mis-resolving to one. The tie is forced via the
    enumeration (two records with the same signature), standing in for two edges
    that truly COINCIDE in space — a boolean seam or a non-manifold duplicate.
    Note the tie is NOT produced by a symmetric part's mirror-congruent edges:
    the signature encodes absolute position, so those four vertical edges have
    DISTINCT signatures and each resolves uniquely — that is exactly why the
    same-position selective fillet is unambiguous."""
    box = _box()
    target = _front_top_edge_signature()
    twin = EdgeRecord(index=0, signature=target, edge=box.edges()[0])

    def _two_matching(_body: Solid) -> list[EdgeRecord]:
        return [twin, twin]

    monkeypatch.setattr("geometry.kernel.edges.enumerate_edges", _two_matching)
    with pytest.raises(SubshapeAmbiguousError):
        resolve_edge(box, target)


# --- selector plumbing -----------------------------------------------------------


def test_select_edges_picked_returns_exactly_the_named_edge() -> None:
    box = _box()
    edges = select_edges(box, _picked(_front_top_edge_signature()))
    assert len(edges) == 1
    assert _mid(edges[0]) == pytest.approx((20.0, 0.0, 10.0), abs=TOL)


def test_select_edges_picked_unresolved_raises() -> None:
    """A reference to an edge that is genuinely GONE still fails honestly.

    The mutation is a whole-edge TRANSLATION off its own supporting line, which is
    what "this edge no longer exists" looks like on a real body. It used to move
    only the ``midpoint`` to z=99 while leaving both endpoints on the real edge —
    an internally inconsistent signature no pick side can emit (for a straight
    edge the midpoint is a function of the endpoints), which the durable tier
    (NAME-2) now resolves on those endpoints. That is correct, and it made the
    old fixture a gate that could no longer fail for the reason it existed.
    """
    box = _box()
    gone = EdgeSignature(
        curve="line",
        end_a=Vec3(x=0.0, y=0.0, z=99.0),
        end_b=Vec3(x=40.0, y=0.0, z=99.0),
        midpoint=Vec3(x=20.0, y=0.0, z=99.0),
        length_mm=40.0,
    )
    with pytest.raises(SubshapeUnresolvedError):
        select_edges(box, _picked(gone))


def test_select_edges_predicate_all_edges_still_works() -> None:
    """Backward-compat: the predicate members resolve exactly as before."""
    edges = select_edges(_box(), AllEdgesSelector(kind="all_edges"))
    assert len(edges) == 12


# --- same-enumeration guarantee (pick side == resolve side) ----------------------


def test_overlay_edges_match_the_resolver_enumeration() -> None:
    """The HEADLINE gate: a signature the overlay hands a client resolves back to
    the SAME edge, at the SAME index, through the STRICT tier (the
    measurement/faces order-equality lesson, applied to edges).

    STRENGTHENED when §14 adjacency landed, and the strengthening is the point.
    This gate used to assert the two enumerations were byte-equal, as a PROXY for
    the property its own docstring names. The pick side now carries strictly more
    than the resolve side — the ``adjacent_faces`` annotation, which the resolve
    side deliberately does not compute (it is not read from a CANDIDATE) and tier
    1 deliberately does not compare — so byte-equality became false while the
    property stayed true, and "make the fixture agree" would have deleted the
    gate. It asserts the property directly instead, plus the byte-equality of
    everything the two sides DO share so the fields cannot drift apart:

    1. overlay signature MINUS adjacency == ``enumerate_edges`` signature, in order;
    2. every overlay signature resolves to its own index at tier ``exact`` — the
       claim the proxy was standing in for, and the one that would catch an
       adjacency annotation that perturbed strict matching.
    """
    box = _box()
    overlay = selection_overlay(box, 0.1)
    records = enumerate_edges(box)

    assert len(overlay.edges) == 12
    assert [
        e.signature.model_copy(update={"adjacent_faces": None}) for e in overlay.edges
    ] == [r.signature for r in records]

    for index, overlay_edge in enumerate(overlay.edges):
        resolved = resolve_edge_durable(box, overlay_edge.signature)
        assert resolved.tier == "exact"
        assert resolved.edge.is_same(records[index].edge)


def test_a_picked_overlay_signature_resolves_back_to_its_edge() -> None:
    """Round-trip: pick an edge's overlay signature, echo it into a picked
    selector, resolve it, and land on that same edge — what the pick UI will do
    end to end."""
    box = _box()
    overlay = selection_overlay(box, 0.1)
    # the front-top edge: a straight edge with midpoint (20, 0, 10)
    picked_sig = next(
        e.signature
        for e in overlay.edges
        if e.signature.curve == "line"
        and e.signature.midpoint == Vec3(x=20.0, y=0.0, z=10.0)
    )
    edges = select_edges(box, _picked(picked_sig))
    assert len(edges) == 1
    assert _mid(edges[0]) == pytest.approx((20.0, 0.0, 10.0), abs=TOL)


def test_edge_signature_dto_shares_construction_with_enumerate_edges() -> None:
    """DRY: edge_signature_dto (pick side) and enumerate_edges (resolve side)
    build the identical DTO for the same edge."""
    box = _box()
    records = enumerate_edges(box)
    for edge, record in zip(box.edges(), records, strict=True):
        assert edge_signature_dto(edge) == record.signature


# --- TIER 2: the durable re-match (NAME-2, audit S-24/S-24b) ---------------------
#
# The defect these gate: the strict matcher pins BOTH endpoints, the midpoint AND
# the length, so any dimension edit that moved a picked edge orphaned its
# fillet / chamfer / edge flange / hem on the FIRST edit. ORDER is the safety
# property — tier 2 runs only on an EMPTY tier-1 result, so nothing that resolved
# before can be retargeted now, which is what the "exact" assertions below hold.


def _grown_box() -> Solid:
    """The box after its 40 mm dimension is retyped to 55 — the audit's S-24 edit
    ("the same boundary edge of the same face, just longer")."""
    return Solid.make_box(55.0, 25.0, 10.0)


def test_a_clean_rebuild_still_reports_the_exact_tier() -> None:
    """Nothing about an unchanged body changes: the strict tier fires, and the
    returned signature IS the stored one."""
    resolved = resolve_edge_durable(_box(), _front_top_edge_signature())
    assert resolved.tier == "exact"
    assert resolved.signature == _front_top_edge_signature()
    assert _mid(resolved.edge) == pytest.approx((20.0, 0.0, 10.0), abs=TOL)


def test_an_edge_that_grew_along_itself_re_anchors_durably() -> None:
    """THE NAME-2 GATE at kernel level. The front-top edge is 40 mm long when the
    reference is authored and 55 mm long after the edit — a different ``end_b``, a
    different midpoint and a different length, i.e. every field the strict matcher
    compares. It is still the same edge of the same face."""
    resolved = resolve_edge_durable(_grown_box(), _front_top_edge_signature())
    assert resolved.tier == "durable"
    assert _mid(resolved.edge) == pytest.approx((27.5, 0.0, 10.0), abs=TOL)
    assert resolved.edge.length == pytest.approx(55.0, abs=TOL)


def test_the_durable_tier_returns_the_CURRENT_signature_to_re_stamp() -> None:
    """The re-stamp channel (NAME-2's "write the new signature back"): a durable
    match hands back the signature of the edge it landed ON, not the stale stored
    one, so a client that persists it puts the reference back on the strict tier.
    Asserted by feeding it straight back in and requiring an ``exact`` match."""
    grown = _grown_box()
    resolved = resolve_edge_durable(grown, _front_top_edge_signature())
    assert resolved.signature != _front_top_edge_signature()
    assert resolve_edge_durable(grown, resolved.signature).tier == "exact"


def test_consecutive_edits_do_not_accumulate_drift() -> None:
    """The audit's S-24b shape, and the reason an INVARIANT tier needs no
    re-stamping to be correct: the stored signature is authored ONCE, at 40, and
    each subsequent edit resolves for the same reason the first one did — the
    supporting line never moves. A drift-budget matcher fails at some N."""
    stored = _front_top_edge_signature()
    for length in (41.0, 42.0, 43.0, 80.0, 400.0):
        resolved = resolve_edge_durable(Solid.make_box(length, 25.0, 10.0), stored)
        assert resolved.tier == "durable"
        assert resolved.edge.length == pytest.approx(length, abs=TOL)


def test_an_edge_that_shrank_below_the_stored_span_still_re_anchors() -> None:
    """Shrinking is the same invariant read the other way: the spans still
    overlap, so the reference survives being made smaller as well as larger."""
    resolved = resolve_edge_durable(
        Solid.make_box(9.0, 25.0, 10.0), _front_top_edge_signature()
    )
    assert resolved.tier == "durable"
    assert resolved.edge.length == pytest.approx(9.0, abs=TOL)


def test_an_edge_that_left_its_supporting_line_still_fails_honestly() -> None:
    """The residual §7.3 refusal, deliberately kept. An edge translated
    PERPENDICULAR to itself (the plate got thicker, so the top-front edge moved in
    z) is a DIFFERENT line, and every parallel edge of the same length is an
    equally good candidate — re-anchoring there could only be a guess. Honest
    ``subshape_unresolved``, exactly as before this tier existed."""
    moved = _front_top_edge_signature().model_copy(
        update={
            "end_a": Vec3(x=0.0, y=0.0, z=16.0),
            "end_b": Vec3(x=40.0, y=0.0, z=16.0),
            "midpoint": Vec3(x=20.0, y=0.0, z=16.0),
        }
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge_durable(_box(), moved)


def test_a_collinear_edge_end_to_end_with_the_stored_one_is_not_accepted() -> None:
    """The overlap clause, which is what keeps the tier honest rather than merely
    permissive: an edge on the SAME line but beyond the stored span (a corner
    round splitting one edge in two) is a different edge and must not resolve."""
    beyond = _front_top_edge_signature().model_copy(
        update={
            "end_a": Vec3(x=60.0, y=0.0, z=10.0),
            "end_b": Vec3(x=100.0, y=0.0, z=10.0),
            "midpoint": Vec3(x=80.0, y=0.0, z=10.0),
        }
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge_durable(_box(), beyond)


def _bored_plate(radius_mm: float) -> BodyShape:
    """A 40x40x10 plate with a central through bore of *radius_mm*."""
    plate = Solid.make_box(40.0, 40.0, 10.0)
    bore = Solid.make_cylinder(radius_mm, 10.0).translate((20.0, 20.0, 0.0))
    return plate.cut(bore)  # pyright: ignore[reportUnknownMemberType]


def test_a_bore_rim_re_anchors_across_a_diameter_change() -> None:
    """The circular half of the tier: a hole resized keeps its centre, its plane
    and its angular station, so a chamfer/fillet picked on its rim survives the
    edit that resizes it. Every strict field moves (a circle scaled about its
    centre moves both stored points and its length)."""
    rim = next(
        record.signature
        for record in enumerate_edges(_bored_plate(4.0))
        if record.signature.curve == "circle"
        and record.signature.midpoint.z == pytest.approx(10.0, abs=TOL)
    )
    resolved = resolve_edge_durable(_bored_plate(6.0), rim)
    assert resolved.tier == "durable"
    assert resolved.edge.length == pytest.approx(2.0 * math.pi * 6.0, abs=1e-6)


def test_a_bore_rim_does_not_re_anchor_onto_the_opposite_rim() -> None:
    """The angular-station + centre clauses doing the load-bearing work: the two
    rims of one through bore are congruent circles on one axis, and the tier must
    not slide the top rim onto the bottom one. Enlarging the bore leaves BOTH rims
    present, so a sloppy predicate would tie or pick wrong; the centres differ in
    z, so only the top rim is a candidate."""
    rim = next(
        record.signature
        for record in enumerate_edges(_bored_plate(4.0))
        if record.signature.curve == "circle"
        and record.signature.midpoint.z == pytest.approx(10.0, abs=TOL)
    )
    resolved = resolve_edge_durable(_bored_plate(6.0), rim)
    assert _mid(resolved.edge)[2] == pytest.approx(10.0, abs=TOL)


def test_an_other_curve_has_no_invariant_and_stays_unresolved() -> None:
    """A spline/ellipse (``curve == "other"``) has no rebuild invariant we can
    state honestly, so the tier refuses rather than guessing."""
    other = _front_top_edge_signature().model_copy(
        update={"curve": "other", "length_mm": 41.0}
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge_durable(_grown_box(), other)


def test_two_equally_valid_re_anchors_are_an_honest_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """>1 candidate at the durable tier refuses to guess, with a message that
    names the tier that produced the tie rather than the strict one's wording."""
    grown = _grown_box()
    record = next(
        r
        for r in enumerate_edges(grown)
        if r.signature.midpoint == Vec3(x=27.5, y=0.0, z=10.0)
    )

    def _two(_body: Solid) -> list[EdgeRecord]:
        return [record, record]

    monkeypatch.setattr("geometry.kernel.edges.enumerate_edges", _two)
    with pytest.raises(SubshapeAmbiguousError, match="re-anchors"):
        resolve_edge_durable(grown, _front_top_edge_signature())


def test_select_edges_picks_up_the_durable_tier_for_fillet_and_chamfer() -> None:
    """The selector plumbing every picked-edge feature shares goes through the
    SAME two-tier match, so a fillet on a grown edge survives the edit."""
    edges = select_edges(_grown_box(), _picked(_front_top_edge_signature()))
    assert len(edges) == 1
    assert _mid(edges[0]) == pytest.approx((27.5, 0.0, 10.0), abs=TOL)


def test_resolve_edge_stays_STRICT_for_drawings_and_mates() -> None:
    """The contract split that keeps the drawings RE-ANCHORED chip honest:
    :func:`resolve_edge` must NOT have grown a second tier, because
    ``geometry.drawings.anchor.resolve_anchor_edge`` runs it as its tier 1 and
    reports ``exact`` when it succeeds. If this ever resolves, a re-anchored
    dimension silently reports itself as exact."""
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge(_grown_box(), _front_top_edge_signature())


# --- TIER 3: the ADJACENCY re-anchor (§14, product audit 2026-09-16) -------------
#
# THE DEFECT these gates exist for, reproduced at the feature-tree level in
# test_edges_adjacency_revision.py and at the kernel level here: every field of an
# EdgeSignature is an ABSOLUTE WORLD COORDINATE, so an edit that RESIZES the part
# translates the picked edge off all of them — and tier 2 cannot help, because it
# re-matches a straight edge on its own SUPPORTING LINE and a translation leaves
# that line behind. Not a tolerance question: ``collinear_overlapping_match``
# returns False for every candidate, at any epsilon.


def _upright_box(width_mm: float) -> Solid:
    """The audit's part in miniature: a ``width x 80 x 40`` block whose WIDTH is
    the dimension the engineer retypes. Its four vertical edges are the fillet
    targets and are congruent in every respect except position."""
    return Solid.make_box(width_mm, 80.0, 40.0)


def _picked_vertical_edge(body: Solid, at_x: float, at_y: float) -> EdgeSignature:
    """The PICK-side signature of the vertical edge at (*at_x*, *at_y*) — built
    through :func:`enumerate_edges_with_adjacency`, which is what the selection
    overlay hands a client, so these gates test the signature the PRODUCT stores
    rather than one the test invented."""
    return next(
        record.signature
        for record in enumerate_edges_with_adjacency(body)
        if record.signature.curve == "line"
        and record.signature.end_a == Vec3(x=at_x, y=at_y, z=0.0)
        and record.signature.length_mm == pytest.approx(40.0, abs=TOL)
    )


def test_the_pick_side_stamps_adjacency_and_the_resolve_side_does_not() -> None:
    """The asymmetry is deliberate and is the reason the resolve path stays cheap:
    tier 3 re-resolves the TARGET's stored faces against the body, so it never
    reads a CANDIDATE's adjacency. Making ``enumerate_edges`` compute it would buy
    nothing and cost an outer-wire region per face on every rebuild."""
    box = _upright_box(120.0)
    assert all(r.signature.adjacent_faces is None for r in enumerate_edges(box))
    stamped = enumerate_edges_with_adjacency(box)
    assert all(r.signature.adjacent_faces is not None for r in stamped)
    assert all(len(r.signature.adjacent_faces or []) == 2 for r in stamped)


def test_adjacency_is_deterministic_and_canonically_ordered() -> None:
    """RESEARCH §9. The pair is persisted and hashed, so its ORDER is part of the
    stored identity: sorting by (normal, centroid) makes it a pure function of the
    geometry rather than of OCCT's ancestor-list order."""
    first = _picked_vertical_edge(_upright_box(120.0), 120.0, 0.0)
    second = _picked_vertical_edge(_upright_box(120.0), 120.0, 0.0)
    assert first.adjacent_faces == second.adjacent_faces
    pair = first.adjacent_faces or []
    assert [(f.normal.x, f.normal.y, f.normal.z) for f in pair] == sorted(
        (f.normal.x, f.normal.y, f.normal.z) for f in pair
    )


def test_THE_DEFECT_the_edge_leaves_its_supporting_line_and_tiers_1_and_2_MISS() -> (
    None
):
    """THE REPRODUCTION, stated as the mechanism rather than as a symptom. With
    the adjacency annotation STRIPPED — i.e. exactly a selector persisted before
    §14, and exactly the state of every picked edge before this commit — widening
    the block 120 -> 150 is ``subshape_unresolved``. This is the NEGATIVE CONTROL
    for every gate below it: they are only meaningful because this one fails."""
    stored = _picked_vertical_edge(_upright_box(120.0), 120.0, 0.0)
    legacy = stored.model_copy(update={"adjacent_faces": None})
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge_durable(_upright_box(150.0), legacy)


def test_adjacency_carries_the_picked_edge_through_a_WIDTH_edit() -> None:
    """THE FIX. The same signature, with its two planar neighbours attached,
    resolves 120 -> 150 — and resolves to the RIGHT edge, which is the claim that
    matters: (150, 0) is the picked corner carried to its new place, not one of
    the three other vertical edges, all of which are congruent to it."""
    stored = _picked_vertical_edge(_upright_box(120.0), 120.0, 0.0)
    resolved = resolve_edge_durable(_upright_box(150.0), stored)
    assert resolved.tier == "adjacent"
    assert _mid(resolved.edge) == pytest.approx((150.0, 0.0, 20.0), abs=TOL)


def test_it_lands_on_the_picked_corner_and_not_on_its_three_congruent_twins() -> None:
    """The discrimination claim, asserted over ALL FOUR corners rather than the
    one that happens to work. A width edit leaves two of the four vertical edges
    exactly where they were, so tiers 1/2 answer for those; adjacency must answer
    for the two that moved, and must answer DIFFERENTLY for each."""
    original, widened = _upright_box(120.0), _upright_box(150.0)
    for at_x, at_y, expected_x in (
        (0.0, 0.0, 0.0),
        (0.0, 80.0, 0.0),
        (120.0, 0.0, 150.0),
        (120.0, 80.0, 150.0),
    ):
        stored = _picked_vertical_edge(original, at_x, at_y)
        resolved = resolve_edge_durable(widened, stored)
        expected = (expected_x, at_y, 20.0)
        assert _mid(resolved.edge) == pytest.approx(expected, abs=TOL), (
            f"edge picked at ({at_x}, {at_y}) landed wrong"
        )


def test_the_edit_is_reversible_and_repeatable_from_ONE_stored_signature() -> None:
    """The S-24b shape for tier 3: the signature is authored ONCE, at 120, and
    every subsequent edit resolves for the same reason the first did — the faces
    are re-resolved from scratch each time, so nothing accumulates. 150 -> 130 was
    the audit's own second edit."""
    stored = _picked_vertical_edge(_upright_box(120.0), 120.0, 0.0)
    for width in (150.0, 130.0, 95.0, 400.0, 120.0):
        resolved = resolve_edge_durable(_upright_box(width), stored)
        assert _mid(resolved.edge) == pytest.approx((width, 0.0, 20.0), abs=TOL)


def test_tier_ORDER_is_the_safety_property_an_exact_match_still_wins() -> None:
    """Tier 3 runs ONLY on an empty tier-2 result and ``edge_signatures_match``
    deliberately ignores ``adjacent_faces``, so adding the field cannot re-target
    a reference that already resolves. Asserted on the body it was picked from:
    the tier must still read ``exact``, not ``adjacent``."""
    box = _upright_box(120.0)
    resolved = resolve_edge_durable(box, _picked_vertical_edge(box, 120.0, 0.0))
    assert resolved.tier == "exact"


def test_tier_2_still_wins_over_tier_3_when_the_edge_merely_GREW() -> None:
    """The other half of the ordering: an edge that stayed on its own supporting
    line is still answered by the cheaper, tighter tier — adjacency does not
    shoulder in ahead of it."""
    grown_signature = next(
        r.signature
        for r in enumerate_edges_with_adjacency(_box())
        if r.signature.midpoint == Vec3(x=20.0, y=0.0, z=10.0)
    )
    assert resolve_edge_durable(_grown_box(), grown_signature).tier == "durable"


# --- tier 3 REFUSES TO GUESS (§7.2) ---------------------------------------------


def _notched_slab(front_y: float) -> BodyShape:
    """A 40 x 10 slab whose FRONT face sits at *front_y*, with a relief notch
    bitten out of the MIDDLE of its bottom-front edge.

    The point of the shape: the bottom face (z=0) and the front face then meet
    along TWO collinear runs instead of one, so a reference to either run names a
    pair of faces that cannot distinguish them. Retyping *front_y* MOVES their
    line of intersection, which is what puts tiers 1 and 2 out of the picture and
    hands the question to tier 3. The notch travels with the front face, as a
    parametric relief actually would.
    """
    slab = Solid.make_box(40.0, 25.0 - front_y, 10.0).locate(
        Location((0.0, front_y, 0.0))
    )
    notch = Solid.make_box(12.0, 6.0, 4.0).locate(Location((14.0, front_y - 1.0, -1.0)))
    return slab.cut(notch)


def _bottom_front_run(body: BodyShape) -> EdgeSignature:
    """The LEFT of the two collinear runs of the slab's bottom-front line."""
    runs = sorted(
        (
            r.signature
            for r in enumerate_edges_with_adjacency(body)
            if r.signature.curve == "line"
            and r.signature.midpoint.z == pytest.approx(0.0, abs=TOL)
            and r.signature.midpoint.y == pytest.approx(0.0, abs=TOL)
        ),
        key=lambda s: s.end_a.x,
    )
    assert len(runs) == 2, "the fixture must present exactly two collinear runs"
    return runs[0]


def test_two_edges_shared_by_the_SAME_face_pair_are_an_honest_ambiguity() -> None:
    """THE GATE THAT KEEPS THE FIX FROM BEING A REGRESSION IN A FIX'S CLOTHES. A
    durability tier that merely became greedier would resolve this; there are two
    genuinely equally valid re-anchors, and §7.2 says refuse. Both stored faces
    resolve UNIQUELY here — measured, so the refusal is the tie itself and not a
    knock-on of a face that failed — and the message names tier 3's own reason
    rather than borrowing the strict tier's wording."""
    stored = _bottom_front_run(_notched_slab(0.0))
    assert stored.adjacent_faces is not None
    moved = _notched_slab(-7.0)
    records = planar_faces(moved)
    for face in stored.adjacent_faces:
        assert len(match_face_records(records, face)[0]) == 1

    with pytest.raises(SubshapeAmbiguousError, match="shared by BOTH faces"):
        resolve_edge_durable(moved, stored)


def test_a_neighbour_that_no_longer_resolves_leaves_the_edge_unresolved() -> None:
    """A pair we cannot pin cannot pin an edge. A stored neighbour that names
    nothing on the rebuilt body must fail honestly, never fall back to "the other
    face's edges" and guess among them."""
    stored = _picked_vertical_edge(_upright_box(120.0), 120.0, 0.0)
    pair = list(stored.adjacent_faces or [])
    pair[0] = pair[0].model_copy(
        update={
            "normal": Vec3(x=0.0, y=0.0, z=1.0),
            "centroid": Vec3(x=5.0, y=5.0, z=999.0),
            "area_mm2": 7.0,
            "outer_area_mm2": 7.0,
            "outer_centroid": Vec3(x=5.0, y=5.0, z=999.0),
            "outer_perimeter_mm": 11.0,
        }
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge_durable(
            _upright_box(150.0), stored.model_copy(update={"adjacent_faces": pair})
        )


def test_an_edge_bounded_by_a_CURVED_face_carries_no_adjacency() -> None:
    """The stated honest limit of §14, gated rather than assumed.
    ``PlanarFaceSignature`` describes planes, so a bore's rim — bounded by the top
    plane and a CYLINDER — gets no adjacency at all rather than a partial one, and
    tier 3 simply does not fire for it. Minting a curved sibling signature is a
    second schema, not this commit."""
    rims = [
        r
        for r in enumerate_edges_with_adjacency(_bored_plate(6.0))
        if r.signature.curve == "circle"
    ]
    assert rims, "the fixture must present circular rims"
    assert all(r.signature.adjacent_faces is None for r in rims)


def test_a_seam_edge_with_ONE_face_on_both_sides_carries_no_adjacency() -> None:
    """The other absence: a cylinder's seam names the SAME face twice, so there is
    no pair to intersect. Absent, never half-filled."""
    records = enumerate_edges_with_adjacency(Solid.make_cylinder(5.0, 20.0))
    seams = [
        r
        for r in records
        if r.signature.curve == "line"
        and r.signature.length_mm == pytest.approx(20.0, abs=TOL)
    ]
    assert seams, "the fixture must present a seam edge"
    assert all(r.signature.adjacent_faces is None for r in seams)


def test_select_edges_picks_up_tier_3_for_fillet_and_chamfer() -> None:
    """The selector plumbing every picked-edge feature shares reaches tier 3, so
    the fix lands in the product path and not only in the resolver."""
    stored = _picked_vertical_edge(_upright_box(120.0), 120.0, 0.0)
    edges = select_edges(_upright_box(150.0), _picked(stored))
    assert len(edges) == 1
    assert _mid(edges[0]) == pytest.approx((150.0, 0.0, 20.0), abs=TOL)
