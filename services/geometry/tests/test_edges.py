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

import math
from typing import Any

import pytest
from build123d import GeomType, Solid
from geometry.kernel import (
    EdgeRecord,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    edge_signature_dto,
    enumerate_edges,
    resolve_edge,
    resolve_edge_durable,
    select_edges,
    selection_overlay,
)
from geometry.kernel.edges import (
    edge_signatures_match,
)
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import (
    AllEdgesSelector,
    EdgeSelectorV1,
    EdgeSignature,
    EdgeSubshapeRef,
    PickedEdgesSelector,
)
from py_kit.schemas.geometry import Vec3

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
    """The HEADLINE gate: the overlay's edge signatures are byte-for-byte the
    resolver's ``enumerate_edges`` enumeration, in the same order — a picked
    signature resolves to the SAME edge (the measurement/faces order-equality
    lesson, applied to edges)."""
    box = _box()
    overlay = selection_overlay(box, 0.1)
    records = enumerate_edges(box)

    assert [e.signature for e in overlay.edges] == [r.signature for r in records]
    assert len(overlay.edges) == 12


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
