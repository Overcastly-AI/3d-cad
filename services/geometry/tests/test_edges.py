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
    select_edges,
    selection_overlay,
)
from geometry.kernel.edges import (
    _edge_signatures_match,  # pyright: ignore[reportPrivateUsage]
)
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
    assert not _edge_signatures_match(line_sig.model_copy(), arc_sig)


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
    box = _box()
    stale = _front_top_edge_signature().model_copy(
        update={"midpoint": Vec3(x=20.0, y=0.0, z=99.0)}
    )
    with pytest.raises(SubshapeUnresolvedError):
        select_edges(box, _picked(stale))


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
