"""The mate-pick seam: the face set a client is OFFERED is the face set the mate
resolver ACCEPTS (MATE-1's kernel half).

MATE-1 reports that a mate-target face can be structurally unreachable, and its
first question is a layering question: is the *candidate set the geometry service
offers* wrong or incomplete, or is the face reachable at the boundary and lost
downstream?  Nothing gated that before this module.  The mate resolver's own
tests (:mod:`tests.test_assembly_resolve`) reach into
:func:`geometry.kernel.faces.planar_faces` to pick ONE face by its normal and
hand its signature straight back to :func:`resolve_mate_geometry` — the resolve
side talking to itself.  The overlay tests (:mod:`tests.test_overlay`) check the
pick side against sketch/datum consumers.  Neither crosses from
:func:`geometry.kernel.overlay.selection_overlay` — the payload the mate-authoring
UI is actually handed (``InstanceMateOverlay``: it offers exactly those faces with
``planar and signature != null``) — into the mate path.  So the two enumerations
(``body.faces()`` on the pick side, ``planar_faces`` on the resolve side) were
free to disagree for mates with no gate objecting.

The three properties locked here are the kernel-side preconditions of every
MATE-1 fix, whichever layer it lands in:

* **completeness** — the offered candidates are EXACTLY the body's planar faces;
  a face missing from the offer is unpickable no matter how good the hit-test is;
* **fidelity** — every offered signature resolves back through the mate resolver
  to THAT face, exactly (no tolerance: both sides derive the plane from the same
  face by the same code, so the doubles are identical — a nonzero difference
  means the sides diverged, which is the defect, not round-off);
* **discrimination** — the two faces of a thin sheet, the pair the S-15
  reproduction could not tell apart, are offered as DISTINCT candidates carrying
  everything needed to separate them, and resolving one never yields the other.

That last one is MATE-1's own reproduction expressed in the kernel.  S-15's two
colliding pick markers are ``Planar face 2, centred at 1, 0, 0`` and
``Planar face 8, centred at 1, 0, 2`` — same x/y, 2 mm apart, i.e. the two faces
of ONE 2 mm sheet, not (as the ticket summarises it) two parts overlapping.  The
"2 mm error" the auditor was offered as an out is exactly the thickness.  If the
kernel handed those two faces over as one indistinguishable blob, or resolved a
ref for the bottom one onto the top one, MATE-1 would be a kernel defect.  It
does not, and these tests are the proof — and the regression gate that keeps the
proof true while the reachability fix is built on top of it.

The bracket is the repo's canonical folded sheet bracket
(``tests/_l_bracket_builder.py``, loaded by file path because the workspace runs
``--import-mode=importlib`` and test modules cannot import each other by name);
its base flange contributes precisely the S-15 face pair.  Assertions on the pair
are DERIVED from the builder's own parameters (thickness, leg lengths), never
hard-coded coordinates, so they state the property rather than a snapshot.

The OCP wheel ships no type stubs, so the raw build123d solid construction is
opaque to pyright; the directive scopes that relaxation to this test only.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from build123d import Location, Solid
from geometry.assembly.protocol import ResolvedFace
from geometry.assembly.resolve import resolve_mate_geometry
from geometry.kernel.faces import planar_faces
from geometry.kernel.overlay import selection_overlay
from geometry.kernel.types import BodyShape
from py_kit.schemas.assemblies import MateFaceRef
from py_kit.schemas.overlay import OverlayFace

_HERE = Path(__file__).resolve().parent
_BUILDER_PATH = _HERE / "_l_bracket_builder.py"

#: Overlay curved-edge sampling, irrelevant to faces but required by the pick-side
#: signature. The tree default; no new tolerance is introduced by this module.
LINEAR_DEFLECTION = 0.1

#: The S-15 bracket, in the builder's own units: a 2 mm sheet, so its base flange's
#: two planar faces sit exactly THICKNESS apart with anti-parallel normals — the
#: pair whose 8 px pick markers the audit could not separate.
BRACKET_LEG_1 = 60.0
BRACKET_LEG_2 = 30.0
BRACKET_THICKNESS = 2.0
BRACKET_BEND_RADIUS = 2.0
BRACKET_WIDTH = 40.0

#: The mounting plate the bracket mates to: 70 x 40 x 6 with two M5 clearance holes.
_PLATE = (70.0, 40.0, 6.0)
_PLATE_HOLE_R = 2.5
_PLATE_HOLES = ((15.0, 20.0), (55.0, 20.0))

BuildFn = Callable[[float, float, float, float, float], BodyShape]


def _load_builder() -> ModuleType:
    """Load the test-local body builder by file path (importlib import-mode: test
    modules cannot import each other by name — root pyproject.toml)."""
    spec = importlib.util.spec_from_file_location("_l_bracket_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_l_bracket = cast(BuildFn, _load_builder().build_l_bracket)


def mounting_plate() -> BodyShape:
    """The plate half of the S-15 fixture: a 70 x 40 x 6 plate with two holes."""
    body = Solid.make_box(*_PLATE)
    for cx, cy in _PLATE_HOLES:
        drill = Solid.make_cylinder(_PLATE_HOLE_R, _PLATE[2] + 2.0).located(
            Location((cx, cy, -1.0))
        )
        body = body.cut(drill)
    assert isinstance(body, Solid)
    return body


def sheet_bracket() -> BodyShape:
    """The bracket half of the S-15 fixture: a folded 2 mm sheet L-bracket."""
    return build_l_bracket(
        BRACKET_LEG_1,
        BRACKET_LEG_2,
        BRACKET_THICKNESS,
        BRACKET_BEND_RADIUS,
        BRACKET_WIDTH,
    )


FIXTURES: dict[str, Callable[[], BodyShape]] = {
    "mounting-plate": mounting_plate,
    "sheet-bracket": sheet_bracket,
}


def offered_faces(body: BodyShape) -> list[OverlayFace]:
    """The faces the mate-authoring overlay OFFERS as coincident-mate candidates.

    Mirrors the client predicate verbatim (``apps/web/src/features/face.ts``'s
    ``isPickableFace``, used by ``InstanceMateOverlay``): a face is on offer iff it
    is planar AND carries a signature. One definition of "on offer", tested here
    against the payload the service actually emits.
    """
    return [
        face
        for face in selection_overlay(body, LINEAR_DEFLECTION).faces
        if face.planar and face.signature is not None
    ]


def _mate_ref(face: OverlayFace) -> MateFaceRef:
    """The MateFaceRef a client builds by echoing an offered face's signature."""
    assert face.signature is not None
    return MateFaceRef(instance_id=uuid.UUID(int=1), signature=face.signature)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_offered_candidates_are_exactly_the_bodys_planar_faces(name: str) -> None:
    """COMPLETENESS — the offer omits nothing but the non-planar faces.

    A mate can only name a planar face (``MateFaceRef`` carries a
    ``PlanarFaceSignature`` by construction), so the complete candidate set IS
    ``planar_faces``. If the pick side ever dropped one — a face whose signature
    failed to build, a truncated enumeration — that face would be unreachable for
    a mate at every camera angle, which is MATE-1's symptom arising kernel-side.
    """
    body = FIXTURES[name]()

    offered = offered_faces(body)
    resolvable = planar_faces(body)

    assert [face.index for face in offered] == [rec.index for rec in resolvable]
    # ...and the rest of the body is non-planar, never a silently dropped plane.
    every = selection_overlay(body, LINEAR_DEFLECTION).faces
    dropped = [face for face in every if face not in offered]
    assert all(not face.planar and face.signature is None for face in dropped)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_offered_candidate_resolves_back_to_itself(name: str) -> None:
    """FIDELITY — each offered signature resolves to THAT face, exactly.

    Pick side == resolve side for mates: both derive the plane from the same
    ``Face`` through the same ``geometry.kernel.faces`` code, so the resolved
    point/normal are the signature's own doubles. Compared with ``==`` rather than
    an epsilon deliberately: any difference at all means the two sides diverged,
    and that is the defect this gate exists to catch (CLAUDE.md — no ad-hoc
    epsilons; there is no measurement error to absorb here).
    """
    body = FIXTURES[name]()

    for face in offered_faces(body):
        assert face.signature is not None
        resolved = resolve_mate_geometry(body, _mate_ref(face))
        assert isinstance(resolved, ResolvedFace)
        assert resolved.point == face.signature.centroid, f"face {face.index} point"
        assert resolved.normal == face.signature.normal, f"face {face.index} normal"


def test_the_two_faces_of_the_sheet_are_distinct_mate_candidates() -> None:
    """DISCRIMINATION — S-15's own pair, kernel-side.

    The bracket's base flange has two planar faces one THICKNESS apart with
    anti-parallel normals (the audit's ``centred at 1, 0, 0`` / ``centred at
    1, 0, 2``). Both are offered, they are separable by normal AND by centroid,
    and a ref for one never resolves onto the other — so the "accept a 2 mm error"
    out the auditor was left with is not something the kernel forced.
    """
    body = sheet_bracket()
    offered = offered_faces(body)

    pairs = [
        (a, b)
        for a in offered
        for b in offered
        if a.index < b.index
        and a.signature is not None
        and b.signature is not None
        # anti-parallel normals: the two skins of one sheet
        and a.signature.normal.x == pytest.approx(-b.signature.normal.x, abs=1e-9)
        and a.signature.normal.y == pytest.approx(-b.signature.normal.y, abs=1e-9)
        and a.signature.normal.z == pytest.approx(-b.signature.normal.z, abs=1e-9)
        # congruent: the flange's two faces have equal area
        and a.signature.area_mm2 == pytest.approx(b.signature.area_mm2, rel=1e-9)
    ]
    assert pairs, "the sheet's two skins must both be on offer"

    separated = 0
    for a, b in pairs:
        assert a.signature is not None and b.signature is not None
        gap = (
            (a.signature.centroid.x - b.signature.centroid.x) ** 2
            + (a.signature.centroid.y - b.signature.centroid.y) ** 2
            + (a.signature.centroid.z - b.signature.centroid.z) ** 2
        ) ** 0.5
        if gap != pytest.approx(BRACKET_THICKNESS, abs=1e-9):
            continue
        separated += 1
        # Each resolves onto its OWN plane — never its neighbour a thickness away.
        for mine, theirs in ((a, b), (b, a)):
            assert mine.signature is not None and theirs.signature is not None
            resolved = resolve_mate_geometry(body, _mate_ref(mine))
            assert isinstance(resolved, ResolvedFace)
            assert resolved.point == mine.signature.centroid
            assert resolved.point != theirs.signature.centroid
            assert resolved.normal == mine.signature.normal

    assert separated >= 1, (
        "the base flange's two skins, exactly one thickness apart, must be a "
        "separable pair — that is S-15's reproduction"
    )


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_the_offer_is_deterministic(name: str) -> None:
    """The candidate set is a pure function of the body (RESEARCH §9).

    A pick set whose ORDER or content wandered between requests would make a
    "select other" cycle — MATE-1's proposed affordance — non-reproducible, and
    would break the transient index the client keys its selection on.
    """
    first = FIXTURES[name]()
    second = FIXTURES[name]()

    assert [face.model_dump_json() for face in offered_faces(first)] == [
        face.model_dump_json() for face in offered_faces(second)
    ]
