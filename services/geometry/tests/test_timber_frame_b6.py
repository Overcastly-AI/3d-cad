"""TIMBER-FRAME acceptance: B6's frame and one joint from ``loft.timber_frame``.

``goldens/timber-mt-8x8`` (one pegged mortise and tenon), ``b6-frame-12x16``
and ``b6-frame-14x16`` (the width edit) are the plugin's expansion
(``model.json``, member materials applied as documents sends them) and each
member's metadata (``members.json``), pinned to the plugin by
``packages/loft-plugins/tests/test_timber_frame.py``. Geometry never learns
plugins exist, so this module reads JSON only. Checked against
``docs/reference-parts/buildings.md`` B6 and an INDEPENDENT build123d script
(:func:`script_frame`, :func:`script_joint`) that builds every member from
the spec another way: build123d boxes and cylinders, the mortise and the
peg holes cut with build123d booleans, the tenon fused on:

1. the cut list, measured from the bodies, is buildings.md B6's;
2. every body is the script's to 1e-4 mm^3 (volume and symmetric
   difference), the totals are 8 775, 56 025 and 58 725 in^3 to 1e-4, and
   the exported STEP's solids match too;
3. each peg and its three holes (two through the post's mortise cheeks, one
   through the tenon) are coaxial and of one radius, on the STEP;
4. the fit is line to line: no two bodies share volume, every tenon/mortise
   and peg/hole pair touches, and the bodies together fill exactly the
   members' shoulder boxes (no gap, no void);
5. the overlap sweep (inner bents with shortened tenons, narrow beams,
   girts low and high, large sections, eight bents) builds valid bodies that
   at most touch (``tests/fixtures/timber-frame-sweep.json.gz``);
6. the frame goldens' STEP drift (1.5e-6 mm^3) is OCCT's: the script's own
   solids drift the same through build123d's STEP.

Topology, counted per body (the goldens' expected.json): a post is its box
(6 faces, 12 edges) and per mortise 5 faces and 12 edges (mouth, four
corners, bottom) plus the bore's two cylinder walls (2 faces; 4 circles and
2 seams). A beam is its box and per tenon 5 faces and 12 edges, plus the
tenon's bore (1 face; 2 circles, 1 seam). A peg is 3 faces and 3 edges.
"""

import gzip
import itertools
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Compound,
    Cylinder,
    GeomType,
    Pos,
    Rot,
    Solid,
    Vector,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.harness import build_model_solid
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
SWEEP = Path(__file__).resolve().parent / "fixtures" / "timber-frame-sweep.json.gz"
IN = 25.4
#: Frame golden -> width (in); every frame is 192 long, posts 96, girts at 60.
WIDTHS = {"b6-frame-12x16": 144.0, "b6-frame-14x16": 168.0}
#: buildings.md B6: the totals (in^3).
VOLUMES = {
    "timber-mt-8x8": 8775.0,
    "b6-frame-12x16": 56025.0,
    "b6-frame-14x16": 58725.0,
}
ALL = sorted(VOLUMES)

each_golden = pytest.mark.parametrize("name", ALL)
each_frame = pytest.mark.parametrize("name", sorted(WIDTHS))


# --- The independent script --------------------------------------------------------


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Solid:
    return (
        Pos((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, (z0 + z1) / 2 * IN)
        * Box((x1 - x0) * IN, (y1 - y0) * IN, (z1 - z0) * IN)
    ).solid()


def _peg(axis: str, a: float, z: float, s0: float, s1: float) -> Solid:
    """A Ø1 cylinder along *axis* from *s0* to *s1*, through (a, z): *a* is
    X for a peg along Y, Y for one along X."""
    length = (s1 - s0) * IN
    mid = (s0 + s1) / 2 * IN
    if axis == "y":
        return (
            Pos(a * IN, mid, z * IN) * Rot(90, 0, 0) * Cylinder(0.5 * IN, length)
        ).solid()
    return (
        Pos(mid, a * IN, z * IN) * Rot(0, 90, 0) * Cylinder(0.5 * IN, length)
    ).solid()


def _one(shape: Any) -> Solid:
    solids = list(shape.solids())
    assert len(solids) == 1
    return solids[0]


class _Script:
    """Members as build123d solids, joined by :meth:`joint`."""

    def __init__(self) -> None:
        self.members: dict[str, Solid] = {}
        self.pegs: list[Solid] = []
        self.shoulder_boxes: list[Solid] = []

    def member(self, key: str, *box: float) -> None:
        self.members[key] = _box(*box)
        self.shoulder_boxes.append(_box(*box))

    def joint(self, post: str, beam: str, tenon: Solid, peg: Solid) -> None:
        self.members[post] = _one(self.members[post] - tenon - peg)
        self.members[beam] = _one((self.members[beam] + tenon) - peg)
        self.pegs.append(peg)

    def solids(self) -> list[Solid]:
        return [*self.members.values(), *self.pegs]


def script_joint() -> _Script:
    """buildings.md B6 "One joint"."""
    s = _Script()
    s.member("post", 0, 7.5, 0, 7.5, 0, 96)
    s.member("beam", 7.5, 67.5, 0, 7.5, 88.5, 96)
    s.joint(
        "post",
        "beam",
        _box(3.5, 7.5, 3, 4.5, 89.25, 95.25),
        _peg("y", 5.5, 92.25, 0, 7.5),
    )
    return s


def script_frame(width: float) -> _Script:
    """buildings.md B6's frame at *width*: 8x8 posts at the corners of
    X 0..width, Y 0..192; tie beams along X flush with the post tops and the
    outside; girts along Y, tops at Z 60; tenons 1.5 x 6 x 4 centred, pegs
    2 in from the shoulder through the post."""
    length, d = 192.0, 7.5
    s = _Script()
    for y in (0.0, length - d):
        for x in (0.0, width - d):
            s.member(f"post {x} {y}", x, x + d, y, y + d, 0, 96)
    for y in (0.0, length - d):
        s.member(f"tie {y}", d, width - d, y, y + d, 88.5, 96)
        s.joint(
            f"post 0.0 {y}",
            f"tie {y}",
            _box(3.5, d, y + 3, y + 4.5, 89.25, 95.25),
            _peg("y", 5.5, 92.25, y, y + d),
        )
        s.joint(
            f"post {width - d} {y}",
            f"tie {y}",
            _box(width - d, width - 3.5, y + 3, y + 4.5, 89.25, 95.25),
            _peg("y", width - 5.5, 92.25, y, y + d),
        )
    for x in (0.0, width - d):
        s.member(f"girt {x}", x, x + d, d, length - d, 52.5, 60)
        s.joint(
            f"post {x} 0.0",
            f"girt {x}",
            _box(x + 3, x + 4.5, 3.5, d, 53.25, 59.25),
            _peg("x", 5.5, 56.25, x, x + d),
        )
        s.joint(
            f"post {x} {length - d}",
            f"girt {x}",
            _box(x + 3, x + 4.5, length - d, length - 3.5, 53.25, 59.25),
            _peg("x", length - 5.5, 56.25, x, x + d),
        )
    return s


def _script(name: str) -> _Script:
    return script_joint() if name == "timber-mt-8x8" else script_frame(WIDTHS[name])


# --- Helpers -----------------------------------------------------------------------


def _request(name: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def _members(name: str) -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def _built(name: str) -> list[Solid]:
    return list(build_model_solid(_request(name)).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _step_solids(name: str, tmp_path: Path) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request(name).model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path / f"{name}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _key(solid: Solid) -> tuple[float, float, float]:
    c = solid.center()
    return (round(c.X, 3), round(c.Y, 3), round(c.Z, 3))


def _volume(shape: Any) -> float:
    return float(measure_shape(shape).volume) if shape else 0.0


def _is_peg(solid: Solid) -> bool:
    return abs(_volume(solid) / IN**3 - 1.875 * math.pi) < 1e-6


def _boxes_overlap(a: Solid, b: Solid, slack: float) -> bool:
    p, q = a.bounding_box(), b.bounding_box()
    return all(
        min(getattr(p.max, k), getattr(q.max, k))
        - max(getattr(p.min, k), getattr(q.min, k))
        > slack
        for k in ("X", "Y", "Z")
    )


def _overlapping(solids: Sequence[Solid]) -> tuple[int, list[tuple[int, int, float]]]:
    """Pairs whose boxes overlap: how many were probed exactly, and those
    sharing any volume."""
    probed = 0
    bad: list[tuple[int, int, float]] = []
    for i, j in itertools.combinations(range(len(solids)), 2):
        if _boxes_overlap(solids[i], solids[j], 1e-6):
            probed += 1
            probe = probe_overlap(solids[i], solids[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    return probed, bad


# --- Tests -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "tie"),
    [("b6-frame-12x16", (137.0, 12)), ("b6-frame-14x16", (161.0, 14))],
)
def test_the_cut_list_is_buildings_md_b6(name: str, tie: tuple[float, int]) -> None:
    """Post 8x8 4 @ 96 (8 ft); Tie beam 8x8 2 @ 137 overall (12 ft); Girt
    8x8 2 @ 185 (16 ft); Peg Ø1 8 @ 7.5, no stock (buildings.md B6), and the
    14 ft edit's tie beams at 161 (14 ft)."""
    request = _request(name)
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B6 frame",
        length_unit="in",
        pieces=part_pieces(
            BodyExtentsResult.model_validate_json(response.content),
            _members(name),
            request.materials,
        ),
    )
    rows = [
        (
            line.member,
            line.profile,
            line.material,
            line.quantity,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
            [round(v / IN, 6) for v in line.section_mm],
        )
        for line in cut_list.lines
    ]
    assert rows == [
        ("Post", "8x8", "dfl_lumber", 4, 96.0, 8, [7.5, 7.5]),
        ("Tie beam", "8x8", "dfl_lumber", 2, tie[0], tie[1], [7.5, 7.5]),
        ("Girt", "8x8", "dfl_lumber", 2, 185.0, 16, [7.5, 7.5]),
        ("Peg", "Ø1", "white_oak", 8, 7.5, None, [1.0, 1.0]),
    ]
    assert cut_list.unclassified == 0


@each_golden
def test_the_bodies_are_the_independent_scripts(name: str, tmp_path: Path) -> None:
    """Body for body the script's to 1e-4 mm^3 (volume and symmetric
    difference), on the kernel's bodies and on the exported STEP's, and the
    total buildings.md's to 1e-4 in^3."""
    want = sorted(_script(name).solids(), key=_key)
    got = sorted(_built(name), key=_key)
    assert len(got) == len(want) == (3 if name == "timber-mt-8x8" else 16)
    for a, b in zip(got, want, strict=True):
        assert _volume(a) == pytest.approx(_volume(b), abs=1e-4)
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < 1e-4, (_key(a), difference)
    total = sum(_volume(s) for s in got) / IN**3
    assert total == pytest.approx(VOLUMES[name], abs=1e-4)
    assert sum(_volume(s) for s in want) / IN**3 == pytest.approx(
        VOLUMES[name], abs=1e-4
    )
    step = sorted(_step_solids(name, tmp_path), key=_key)
    assert [_key(s) for s in step] == [_key(s) for s in want]
    for a, b in zip(step, want, strict=True):
        assert _volume(a) == pytest.approx(_volume(b), abs=1e-4)
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < 1e-4, (_key(a), difference)


def test_the_one_joints_bodies_are_the_specs() -> None:
    """buildings.md: the post 5 364 - 1.5 pi, the beam 3 411 - 0.375 pi and
    the peg 1.875 pi (in^3)."""
    by_volume = sorted(_volume(s) / IN**3 for s in _built("timber-mt-8x8"))
    assert by_volume == [
        pytest.approx(1.875 * math.pi, abs=1e-9),
        pytest.approx(3411 - 0.375 * math.pi, abs=1e-9),
        pytest.approx(5364 - 1.5 * math.pi, abs=1e-9),
    ]


@each_golden
def test_every_peg_is_coaxial_with_its_three_holes(name: str, tmp_path: Path) -> None:
    """On the STEP: each peg's axis carries exactly three hole walls of its
    radius, two in the post (through the mortise's cheeks, either side of
    the tenon) and one in the beam (through the tenon), and they span the
    peg's length end to end without overlapping."""
    solids = _step_solids(name, tmp_path)
    pegs = [s for s in solids if _is_peg(s)]
    others = [s for s in solids if not _is_peg(s)]
    assert len(pegs) == (1 if name == "timber-mt-8x8" else 8)
    for peg in pegs:
        (wall,) = [f for f in peg.faces() if f.geom_type == GeomType.CYLINDER]
        axis = wall.axis_of_rotation
        assert axis is not None
        direction = axis.direction.normalized()
        ends = sorted(
            (Vector(v) - axis.position).dot(direction) for v in wall.vertices()
        )
        holes: list[tuple[int, float, float]] = []
        for index, body in enumerate(others):
            for face in body.faces():
                if face.geom_type != GeomType.CYLINDER:
                    continue
                other = face.axis_of_rotation
                assert other is not None
                if abs(abs(other.direction.normalized().dot(direction)) - 1) > 1e-12:
                    continue
                offset = other.position - axis.position
                off_axis = (offset - direction * offset.dot(direction)).length
                if off_axis > 1e-6:
                    continue
                assert face.radius == pytest.approx(wall.radius, abs=1e-9)
                span = sorted(
                    (Vector(v) - axis.position).dot(direction) for v in face.vertices()
                )
                if span[0] < ends[0] - 1e-6 or span[-1] > ends[-1] + 1e-6:
                    continue  # another joint's hole on the same line
                holes.append((index, round(span[0], 6), round(span[-1], 6)))
        assert len(holes) == 3, holes
        assert len({body for body, _, _ in holes}) == 2
        spans = sorted((lo, hi) for _, lo, hi in holes)
        # Contiguous: cheek, tenon, cheek, from one face of the post to the other.
        assert spans[0][0] == pytest.approx(ends[0], abs=1e-6)
        assert spans[-1][1] == pytest.approx(ends[-1], abs=1e-6)
        for (_, hi), (lo, _) in itertools.pairwise(spans):
            assert lo == pytest.approx(hi, abs=1e-6)
        middle = spans[1][1] - spans[1][0]
        assert middle == pytest.approx(1.5 * IN, abs=1e-6)  # the tenon's thickness


@each_golden
def test_the_fit_is_line_to_line(name: str, tmp_path: Path) -> None:
    """No two bodies share volume; every peg touches its post and beam and
    every beam its posts (their boxes overlap, so the pairs are probed
    exactly); and together the bodies are exactly the members' shoulder
    boxes: the tenons fill their mortises and the pegs their holes."""
    solids = _step_solids(name, tmp_path)
    probed, bad = _overlapping(solids)
    assert bad == []
    pegs = 1 if name == "timber-mt-8x8" else 8
    assert probed >= 3 * pegs
    script = _script(name)
    first, *rest = script.shoulder_boxes
    filled = first.fuse(*rest)  # pyright: ignore[reportUnknownMemberType]
    first, *rest = solids
    together = first.fuse(*rest)  # pyright: ignore[reportUnknownMemberType]
    difference = _volume(together.cut(filled)) + _volume(filled.cut(together))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert difference < 1e-4
    assert _volume(together) / IN**3 == pytest.approx(VOLUMES[name], abs=1e-4)


def _sweep() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(SWEEP.read_bytes()))
    return cases


@pytest.mark.parametrize("case", _sweep(), ids=[c["name"] for c in _sweep()])
def test_the_overlap_sweep_builds_every_member_touching_only(
    case: dict[str, Any],
) -> None:
    """Inner bents, narrow beams, girts low and high, large sections and the
    most bents: one valid solid per member and peg, at most touching."""
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids: list[Solid] = list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    probed, bad = _overlapping(solids)
    assert bad == [], bad
    pegs = sum(1 for s in solids if _volume(s) < 50 * IN**3)  # Ø1 x 11.5 at most
    assert probed >= 3 * pegs


def _drift(solids: Sequence[Solid], tmp_path: Path, name: str) -> float:
    """Volume after build123d's STEP export and re-import, less before."""
    before = sum(_volume(s) for s in solids)
    path = tmp_path / f"{name}.step"
    export_step(Compound(list(solids)), str(path))
    back = list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
    return sum(_volume(s) for s in back) - before  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


@each_frame
def test_the_frames_step_drift_is_occts(name: str, tmp_path: Path) -> None:
    """The frame goldens' reviewed round-trip bound holds for the plugin's
    bodies, and the independent script's own solids (no Loft code) drift
    through build123d's STEP by the same order: OCCT re-integrating the
    re-imported posts' bores and re-summing the bodies, not Loft's export.
    Measured 2026-10-17 (mm^3): 12x16 plugin +1.5e-6, 14x16 +1.1e-6."""
    bound = json.loads((GOLDENS / name / "expected.json").read_text())[
        "roundtrip_tolerance"
    ]
    ours = abs(_drift(_built(name), tmp_path, "ours"))
    twin = abs(_drift(script_frame(WIDTHS[name]).solids(), tmp_path, "twin"))
    assert ours < bound, ours
    assert twin < bound, twin
