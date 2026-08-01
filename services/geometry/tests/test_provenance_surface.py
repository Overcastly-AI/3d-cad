"""QA3-3 — a feature owns the faces whose SURFACE it created, not the ones it
merely re-bounded.

The defect (docs/QA-REVIEW.md 2026-08-01): `attribute_faces` credited a face to the
earliest feature after which it existed in its FINAL form, so any cut that re-cut a
large face took ownership of it. On the dogfooding remix the 5th Ø3 mount hole owned
3 of the plate's 18 faces — its own 75.4 mm² bore wall PLUS the vendor plate's entire
1 323.8 mm² top and 1 682.7 mm² back — and "highlight only this feature's faces" lit
most of the part, which is the very thing FINDINGS #9 exists to prevent. Fusion and
SolidWorks light the bore wall and its edges.

The rule is GEOMETRIC, and these gates are written to say why that matters rather
than to pin one part's numbers. An AREA CUTOFF would have fitted this plate and
failed the first time somebody drilled through a small face, so
`test_a_bore_through_a_face_smaller_than_its_own_wall` builds exactly that part: the
face the bore re-cuts is SMALLER than the wall the bore creates, so no ordering by
size can separate them and only "was this surface here before?" gets it right.

Tolerances: the surface descriptors are compared by EXACT equality (a boolean re-uses
the `Geom_Surface` of a face it only re-bounds), and the extent guard uses the
documented kernel linear tolerance. No new epsilon — see `provenance.SurfaceKey`.
"""

# The OCP wheel ships no type stubs, so raw build123d booleans are opaque to
# pyright (the house pattern for kernel-adjacent tests); `_surface_key` is
# module-private because it never crosses a boundary, and testing it directly is
# the point of the surface-family gate.
# pyright: reportPrivateUsage=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false

import uuid
from pathlib import Path

import pytest
from build123d import Face, GeomType, Location, Solid
from geometry.features import evaluate_tree
from geometry.kernel import FaceProvenance, attribute_faces
from geometry.kernel.faces import face_signature_dto
from geometry.kernel.provenance import SurfaceKey, _surface_key
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import EvaluateTreeRequest

A = uuid.UUID("00000000-0000-0000-0000-0000000e0001")
B = uuid.UUID("00000000-0000-0000-0000-0000000e0002")

#: The vendor STEP the defect was measured on. Owned by the e2e suite
#: (`apps/web/e2e/import-remix.spec.ts` imports the same bytes); read here, never
#: written, because duplicating 52 KB of fixture to prove the kernel half would be
#: the WET defect and the two halves must agree about the same part.
NEMA_STEP = (
    Path(__file__).resolve().parents[3]
    / "apps"
    / "web"
    / "e2e"
    / "fixtures"
    / "nema17-front-plate.step"
)


def _owners(history: list[tuple[uuid.UUID, BodyShape]]) -> list[uuid.UUID | None]:
    """Attribution of the LAST snapshot's faces, given the whole history."""
    return attribute_faces(history[-1][1], FaceProvenance.of_bodies(history))


def _areas(
    body: BodyShape, owners: list[uuid.UUID | None], who: uuid.UUID
) -> list[float]:
    return sorted(
        round(face.area, 4)
        for face, owner in zip(body.faces(), owners, strict=True)
        if owner == who
    )


# --- the headline: the vendor plate the defect was measured on --------------------


def _nema_remix() -> EvaluateTreeRequest:
    """The dogfooding remix, kernel-side: import the vendor plate, then drill a 5th
    Ø3 mount hole on the back face picked by its stage-1 signature — the same two
    features `import-remix.spec.ts` authors through the gateway."""
    step = NEMA_STEP.read_text()
    imported = {
        "id": str(A),
        "feature": {
            "type": "import",
            "version": 1,
            "params": {"kind": "inline", "format": "step", "data": step},
        },
    }
    plate = evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": "00000000-0000-0000-0000-0000000000fd",
                "tree_version": 1,
                "features": [imported],
            }
        )
    )
    assert plate.body is not None
    back = next(
        signature
        for signature in (face_signature_dto(face) for face in plate.body.faces())
        if signature is not None and abs(signature.area_mm2 - 1689.7785) < 0.01
    )
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": "00000000-0000-0000-0000-0000000000fd",
            "tree_version": 1,
            "features": [
                imported,
                {
                    "id": str(B),
                    "feature": {
                        "type": "hole",
                        "version": 1,
                        "params": {
                            "face": {
                                "kind": "subshape",
                                "feature_id": str(A),
                                "subshape_type": "face",
                                "selector": {
                                    "selector_version": 1,
                                    "signature": back.model_dump(mode="json"),
                                },
                            },
                            "position": {"x": 15.5, "y": 0, "z": 0},
                            "diameter_mm": 3.0,
                            "depth": {"kind": "through_all"},
                        },
                    },
                },
            ],
        }
    )


def test_the_fifth_hole_owns_its_bore_wall_and_nothing_else() -> None:
    """HEADLINE GATE (QA3-3 acceptance), on the real vendor part.

    Before: the hole owned 3 of 18 — its 75.3982 mm² wall, the plate's 1 323.81 mm²
    top and its 1 682.71 mm² back. After: 1 of 18, the wall, and the import keeps 17
    including both large faces it actually brought. These are the numbers
    `import-remix.spec.ts` asserts through the browser; they are pinned here too so a
    kernel change that moves them fails in the fast suite, not only in Playwright.

    Note the bore wall's area is 75.3982 mm² and so is every one of the four VENDOR
    Ø3 bores — the part itself says that area cannot identify a feature's work."""
    evaluation = evaluate_tree(_nema_remix(), record_history=True)
    assert evaluation.body is not None
    owners = attribute_faces(evaluation.body, evaluation.face_provenance)

    assert len(owners) == 18
    assert owners.count(B) == 1
    assert owners.count(A) == 17
    # The hole's ONE face is the Ø3 x 8 mm bore wall (pi * 3 * 8 = 75.3982 mm^2).
    assert _areas(evaluation.body, owners, B) == [75.3982]
    # ... and the two big faces the bore re-cut stayed with the import that made them.
    import_areas = _areas(evaluation.body, owners, A)
    assert any(area == pytest.approx(1323.81, abs=0.01) for area in import_areas)
    assert any(area == pytest.approx(1682.71, abs=0.01) for area in import_areas)


# --- why an area threshold would have been a guess --------------------------------


def test_a_bore_through_a_face_smaller_than_its_own_wall() -> None:
    """The anti-heuristic gate: SIZE cannot decide this, only the surface can.

    A 3x3x20 mm post drilled Ø2 through the top. The face the bore re-cuts is the
    post's 5.86 mm² top; the face the bore CREATES is its 125.66 mm² wall — twenty-one
    times bigger. Any rule of the shape "a small cut does not own a large face"
    inverts here and hands the top to the hole again, while the surface rule is
    scale-free: the top is still the plane the extrude made."""
    post = Solid.make_box(3.0, 3.0, 20.0)
    bit = Solid.make_cylinder(1.0, 30.0).locate(Location((1.5, 1.5, -5.0)))
    drilled = post.cut(bit)
    owners = _owners([(A, post), (B, drilled)])

    wall = _areas(drilled, owners, B)
    assert wall == [pytest.approx(125.6637, abs=1e-3)]  # 2 * pi * 1 * 20
    top = max(face.area for face in drilled.faces() if face.geom_type == GeomType.PLANE)
    assert top == pytest.approx(60.0, abs=1e-6)  # a 3 x 20 side, untouched
    drilled_top = min(
        face.area for face in drilled.faces() if face.geom_type == GeomType.PLANE
    )
    assert drilled_top == pytest.approx(9.0 - 3.14159265, abs=1e-3)
    assert drilled_top < wall[0]  # the re-cut face is SMALLER than the new one
    assert owners.count(B) == 1  # ... and the hole still owns only the wall


# --- the extent guard: "same plane" is not "same face" ----------------------------


def test_two_disjoint_coplanar_bodies_keep_their_own_faces() -> None:
    """A plane is UNBOUNDED, so surface identity alone links patches that merely
    happen to be coplanar. Two 10 mm cubes 40 mm apart share their Z=0, Z=10, Y=0 and
    Y=10 planes; without the extent guard the first extrude took four of the second
    cube's six faces (measured: 6/6 became 10/2 on the `multibody-two-disjoint-boxes`
    and `boolean-union-two-disjoint-cubes` goldens). The final patch has to lie inside
    the extent the surface had back then, and cube B's does not."""
    first = Solid.make_box(10.0, 10.0, 10.0)
    second = Solid.make_box(10.0, 10.0, 10.0).locate(Location((40.0, 0.0, 0.0)))
    both = first.fuse(second)
    owners = _owners([(A, first), (B, both)])

    assert owners.count(A) == 6
    assert owners.count(B) == 6


def test_a_feature_that_grows_a_face_takes_it() -> None:
    """The extent guard's other direction, and the reason it is a CONTAINMENT test
    and not an equality one. A boss whose side wall is coplanar with the plate's
    merges into ONE taller face: that face is not the one the extrude had (it spans
    beyond its extent), so the boss owns it — while the plate's untouched faces stay
    put. Cutting only shrinks a face; only adding material can grow one."""
    plate = Solid.make_box(40.0, 25.0, 10.0)
    boss = Solid.make_box(15.0, 25.0, 10.0).locate(Location((0.0, 0.0, 10.0)))
    grown = plate.fuse(boss)
    owners = _owners([(A, plate), (B, grown)])

    # The Y=0 / Y=25 walls now span 0..20 in Z — grown, so they are the boss's.
    grown_walls = [
        face
        for face, owner in zip(grown.faces(), owners, strict=True)
        if owner == B and face.area == pytest.approx(550.0, abs=1e-6)
    ]
    assert len(grown_walls) == 2
    # The plate's bottom is unchanged and still the plate's.
    assert 1000.0 in _areas(grown, owners, A)


# --- surface identity: every family, and the free-form fallback -------------------


def test_every_analytic_surface_family_has_a_canonical_key() -> None:
    """The five families `_surface_key` canonicalises, each read off a real body.
    A missing branch here is a face that silently falls back to the old rule."""
    families = {
        _surface_key(face).family  # pyright: ignore[reportOptionalMemberAccess]
        for solid in (
            Solid.make_box(10.0, 10.0, 10.0),  # planes
            Solid.make_cylinder(5.0, 10.0),  # cylinder (+ planar caps)
            Solid.make_cone(5.0, 1.0, 10.0),  # cone
            Solid.make_sphere(5.0),  # sphere
            Solid.make_torus(10.0, 2.0),  # torus
        )
        for face in solid.faces()
    }
    assert len(families) == 5


def test_a_cylindrical_face_survives_being_re_bounded() -> None:
    """The non-planar half of the rule: a cross-hole through a shaft re-bounds the
    shaft's cylindrical wall (its area and centroid both move) without touching the
    cylinder itself, so the wall stays with the feature that turned it."""
    shaft = Solid.make_cylinder(6.0, 40.0)
    bored = shaft.cut(
        Solid.make_cylinder(2.0, 30.0).locate(Location((-15.0, 0.0, 20.0), (0, 90, 0)))
    )
    owners = _owners([(A, shaft), (B, bored)])

    outer = [
        face
        for face, owner in zip(bored.faces(), owners, strict=True)
        if owner == A and face.geom_type == GeomType.CYLINDER
    ]
    assert len(outer) == 1
    assert outer[0].area < 2.0 * 3.14159265 * 6.0 * 40.0  # genuinely re-bounded
    # The cross-bore's own wall (split in two by the shaft's hollow) is the cut's.
    assert all(
        face.geom_type == GeomType.CYLINDER
        for face, owner in zip(bored.faces(), owners, strict=True)
        if owner == B
    )


def test_a_free_form_face_has_no_surface_key_and_falls_back_honestly() -> None:
    """A B-spline surface has no analytic descriptor to canonicalise, so it carries
    no key and keeps the OLDER final-form answer — documented degradation, not a
    crash and not a guess. Nothing else in the body is affected."""
    lofted = Solid.make_loft(
        [
            Face.make_rect(20.0, 20.0).outer_wire(),
            Face.make_rect(8.0, 14.0).outer_wire().moved(Location((0.0, 0.0, 25.0))),
        ]
    )
    free_form = [face for face in lofted.faces() if _surface_key(face) is None]
    assert free_form, "expected at least one non-analytic face on a loft"

    drilled = lofted.cut(
        Solid.make_cylinder(2.0, 60.0).locate(Location((0.0, 0.0, -10.0)))
    )
    owners = _owners([(A, lofted), (B, drilled)])
    assert all(owner is not None for owner in owners)
    assert owners.count(B) >= 1  # the bore wall at least


# --- the invariants the rule and its cost rest on ---------------------------------


def test_the_surface_rule_never_answers_later_than_the_old_one() -> None:
    """MONOTONICITY, on a real mixed-vocabulary part (the docs/PERF.md tray at N=10:
    7 body-affecting features, 28 faces, booleans throughout).

    Both indices are consulted and the EARLIER wins, so this change can only ever
    move a face EARLIER in the tree. That is what makes it safe to land without
    re-blessing every consumer: nothing that used to be attributed becomes
    unattributed, and nothing moves toward the leaf."""
    import importlib.util

    path = Path(__file__).resolve().parent / "_big_part_builders.py"
    spec = importlib.util.spec_from_file_location("_big_part_builders", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(module.housing_tree(10)), record_history=True
    )
    assert evaluation.body is not None
    provenance = evaluation.face_provenance
    order = {feature_id: i for i, (feature_id, _fps) in enumerate(provenance.snapshots)}

    new = attribute_faces(evaluation.body, provenance)
    # The old rule, reproduced by starving the pass of the surface index.
    old = attribute_faces(
        evaluation.body, FaceProvenance(provenance.snapshots, provenance.face_count)
    )

    assert all(owner is not None for owner in new)
    assert any(a != b for a, b in zip(old, new, strict=True))  # it did something
    for before, after in zip(old, new, strict=True):
        assert before is not None and after is not None
        assert order[after] <= order[before]


def test_the_pass_consumes_the_prebuilt_surface_index() -> None:
    """PERF-5b's shape, defended. Building the surface index inside
    `attribute_faces` would put an O(sum snapshot faces) loop back into every
    interactive pick — measured at +44 % on the N=100 tray — so the RECORDER owns it
    and the pass only reads it. Asserted behaviourally: hand the pass a provenance
    with the index stripped and the answer must fall back to the old rule, which it
    could not do if it derived the index from the snapshots it still has."""
    from geometry.kernel import provenance as module

    block = Solid.make_box(40.0, 25.0, 10.0)
    drilled = block.cut(
        Solid.make_cylinder(5.0, 30.0).locate(Location((20.0, 12.5, -5.0)))
    )
    recorded = FaceProvenance.of_bodies([(A, block), (B, drilled)])
    assert recorded.surfaces, "the recorder is meant to build the index"

    assert attribute_faces(drilled, recorded).count(B) == 1
    stripped = module.FaceProvenance(recorded.snapshots, recorded.face_count)
    assert attribute_faces(drilled, stripped).count(B) == 3  # the old rule, exactly


def test_the_index_and_the_attribution_are_deterministic() -> None:
    """RESEARCH §9. The surface index is dict-ordered by first sighting and the
    extent lists are append-only, so two evaluations of one tree agree entry for
    entry — not merely on the owners they imply."""
    tree = _nema_remix()
    first = evaluate_tree(tree, record_history=True)
    second = evaluate_tree(tree, record_history=True)
    assert first.body is not None and second.body is not None
    assert first.face_provenance.surfaces == second.face_provenance.surfaces
    assert attribute_faces(first.body, first.face_provenance) == attribute_faces(
        second.body, second.face_provenance
    )


def test_a_canonical_key_is_indifferent_to_the_sense_occt_chose() -> None:
    """The canonicalisation, isolated. A box's two X-normal faces point in opposite
    directions and are NOT the same surface; the same plane read from two bodies IS,
    whichever sense OCCT hands back. Without the fixed sign convention the second
    would miss and the whole rule would silently degrade to the old one."""
    box = Solid.make_box(10.0, 10.0, 10.0)
    keys = [_surface_key(face) for face in box.faces()]
    assert all(key is not None for key in keys)
    assert len({key for key in keys if key is not None}) == 6

    tall = Solid.make_box(10.0, 10.0, 30.0)
    shared = {key for key in keys if key is not None} & {
        key for key in (_surface_key(face) for face in tall.faces()) if key is not None
    }
    # X=0, X=10, Y=0, Y=10 and Z=0 are common; only the top plane differs.
    assert len(shared) == 5
    assert all(isinstance(key, SurfaceKey) for key in shared)
