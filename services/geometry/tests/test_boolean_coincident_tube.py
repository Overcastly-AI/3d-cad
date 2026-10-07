"""Cross tubes that end on, past, or at the skin of a same-diameter rail tube.

BOOLEAN-COINCIDENT-TUBE. The moto-frame golden's four Y cross tubes end 6 mm
inside the rail centrelines. An engineer models them centreline to centreline
(220 long), or butted flush on the far rail's outer skin (245.4 long), so this
drives the SAME tree with the tubes ending where they would: the shipped answer
must be right or refused, never a silently wrong solid.

THE EXPECTED VOLUMES ARE DERIVED, not recorded (:func:`_frame_volume`). The rail
is the 12.7/11.1 annulus swept along a planar G1 centreline whose R80 fillets
exceed the tube radius, so its material is exactly the points whose distance to
the centreline lies in [11.1, 12.7]. At a point of the cross tube's annulus
whose in-plane distance to the centreline is d, the rail therefore occupies
|y - 110| in [sqrt(11.1^2 - d^2), sqrt(12.7^2 - d^2)], a closed form; the overlap
of a tube segment with the rail is a 2D Gauss/midpoint quadrature of that
length over the annulus. Growing each tube from the golden's y = 104 (703888.377,
itself checked against an independent build123d twin and Pappus) gives:

* y = 110 (centreline): 708479.161. The tree reads 708479.158, and the twin
  extrapolated from tubes ending at 109.99 and below gives 708479.161, which
  validates the derivation. STEP re-read differs by 1.1e-2.
* y = 110.5: refused (``invalid_body`` on the last union, strict prefix). Right.
* y = 122.7 (the rail's outer skin): 718211.506. Before the boolean integrity
  guard the tree shipped 732801.92 with every feature ``ok``, one
  BRepCheck-valid lump and 18 shells, ABOVE the 725460.9 its members sum to.
  (The 729620 "truth" this file once quoted came from the twin fused 0.1 mm past
  the skin, 729715.6, which is also above its members' sum: the twin's fuse was
  wrong the same way.)

ROOT CAUSE (kernel/boolean_guard.py). Where a cross tube crosses a rail, the
tube's bore inside the rail's bore is a sealed compartment, a void shell of
7295.2 mm^3. At the front-apex tube, which crosses the rail's R80 bend (a
torus), with its end face tangent to the bend's skin, OCCT's general fuse drops
that void shell, so the compartment comes back as solid. The smallest
reproduction is two solids: a revolved annular torus segment and a straight
annular tube ending on its skin (:func:`_bend`, :func:`_tube`). Two straight
tubes do not reproduce it. The guard sees the union exceed the sum of its
operands and re-runs the boolean fuzzy, which keeps the void.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import json
import math
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from build123d import (
    Axis,
    Edge,
    Face,
    Plane,
    Solid,
    Wire,
    export_step,
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.features import evaluate_tree
from geometry.kernel import (
    BooleanError,
    BooleanIntegrityError,
    boolean_bodies,
    combine_body,
    measure_shape,
)
from geometry.kernel.boolean_guard import (
    FUZZY_RETRY_MM,
    GuardedOperation,
    guarded_boolean,
    integrity_violation,
    volume_violation,
)
from geometry.kernel.healing import (
    BodyReading,
    ShellReading,
    SolidReading,
    read_solids,
)
from geometry.kernel.mirror import fuse_reflected_tools
from geometry.kernel.pattern import _fuse_and_finalize
from geometry.kernel.types import BodyShape
from loft_wire.features import EvaluateTreeRequest
from numpy.typing import NDArray

GOLDEN_DIR = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "frame-moto-cradle-tube-od25.4-t1.6"
)
GOLDEN = GOLDEN_DIR / "model.json"

RO, RI = 12.7, 11.1
ANNULUS_AREA = math.pi * (RO**2 - RI**2)
RAIL_PLANE_Y = 110.0
RAIL_VOLUME = ANNULUS_AREA * 1766.0415908222212  # Pappus, closed loop length
HEAD_VOLUME = math.pi * (25.0**2 - 16.0**2) * 160.0

#: The golden's tolerance and STEP round-trip tolerance (its expected.json).
GOLDEN_TOL = 0.05
ROUNDTRIP_TOL = 0.5

#: :func:`_frame_volume` at 110 and 122.7, pinned so a change to the derivation
#: shows up as a diff here (n = 400; n = 200 and 800 agree to 5e-3).
CENTRELINE_VOLUME = 708479.161
SKIN_VOLUME = 718211.506

#: The sealed compartment OCCT drops: the tube's bore inside the rail's bore.
COMPARTMENT_VOLUME = 7295.2

Distance = Callable[[NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]]


def _frame_with_tubes_ending_at(y: float) -> EvaluateTreeRequest:
    """The golden's tree, the four cross tubes extruded from y to -y."""
    data: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for item in data["features"]:
        params = item["feature"]["params"]
        if item["feature"]["type"] == "datum" and item["id"].endswith("04"):
            params["offset_mm"] = -y  # the XZ datum's normal is -Y
        if item["feature"]["type"] == "extrude":
            params["distance_mm"] = 2 * y
    return EvaluateTreeRequest.model_validate(data)


# --- the derivation -----------------------------------------------------------


def _rail_overlap(
    centre: tuple[float, float], ya: float, yb: float, distance: Distance, n: int
) -> float:
    """Volume of the annular Y tube at *centre* (x, z), ya <= y <= yb, inside the
    rail whose centreline lies in the plane y = 110 at in-plane *distance*.

    Gauss-Legendre in the radius, midpoint in the angle (periodic, so spectral).
    """
    nodes, weights = np.polynomial.legendre.leggauss(n)
    radius = RI + (RO - RI) * (nodes + 1) / 2
    weights = weights * (RO - RI) / 2
    m = 4 * n
    angle = (np.arange(m) + 0.5) * 2 * math.pi / m
    r, phi = np.meshgrid(radius, angle, indexing="ij")
    d = distance(centre[0] + r * np.cos(phi), centre[1] + r * np.sin(phi))
    outer = np.sqrt(np.clip(RO**2 - d**2, 0.0, None))
    inner = np.sqrt(np.clip(RI**2 - d**2, 0.0, None))

    def within(lo: NDArray[np.float64], hi: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.clip(np.minimum(hi, yb) - np.maximum(lo, ya), 0.0, None)

    y0 = RAIL_PLANE_Y
    length = np.where(
        d < RI,
        within(y0 - outer, y0 - inner) + within(y0 + inner, y0 + outer),
        np.where(d < RO, within(y0 - outer, y0 + outer), 0.0),
    )
    return float((((length * r).sum(axis=1)) * (2 * math.pi / m) * weights).sum())


def _frame_centreline() -> tuple[Distance, list[tuple[float, float]]]:
    """In-plane distance to the rail centreline, and the four tube centres."""
    data: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    lines: list[tuple[NDArray[np.float64], NDArray[np.float64]]] = []
    arcs: list[tuple[NDArray[np.float64], float, float, float]] = []
    centres: list[tuple[float, float]] = []

    def point(p: dict[str, float]) -> NDArray[np.float64]:
        return np.array([p["x"], p["y"]])

    for item in data["features"]:
        params = item["feature"]["params"]
        if item["id"].endswith(("0a", "0d")):  # the two rail centreline halves
            for entity in params["entities"]:
                if entity["kind"] == "line":
                    lines.append((point(entity["start"]), point(entity["end"])))
                    continue
                c = point(entity["center"])
                s, e = point(entity["start"]) - c, point(entity["end"]) - c
                a0 = math.atan2(s[1], s[0])
                sweep = (math.atan2(e[1], e[0]) - a0 + math.pi) % (
                    2 * math.pi
                ) - math.pi
                arcs.append((c, float(np.hypot(*s)), a0, sweep))  # fillets < 180 deg
        if item["id"][-2:] in ("14", "16", "18", "1a"):  # the cross tube sketches
            circle = params["entities"][0]["center"]
            centres.append((circle["x"], circle["y"]))

    def distance(x: NDArray[np.float64], z: NDArray[np.float64]) -> NDArray[np.float64]:
        best = np.full(x.shape, np.inf)
        for p0, p1 in lines:
            v = p1 - p0
            t = np.clip(((x - p0[0]) * v[0] + (z - p0[1]) * v[1]) / (v @ v), 0, 1)
            best = np.minimum(
                best, np.hypot(x - p0[0] - t * v[0], z - p0[1] - t * v[1])
            )
        for c, radius, a0, sweep in arcs:
            off = np.mod(
                (np.arctan2(z - c[1], x - c[0]) - a0) * np.sign(sweep), 2 * math.pi
            )
            on_arc = np.abs(np.hypot(x - c[0], z - c[1]) - radius)
            ends = [
                c + radius * np.array([math.cos(a), math.sin(a)])
                for a in (a0, a0 + sweep)
            ]
            to_end = np.minimum(*(np.hypot(x - q[0], z - q[1]) for q in ends))
            best = np.minimum(best, np.where(off <= abs(sweep), on_arc, to_end))
        return best

    return distance, centres


def _frame_volume(y: float, n: int = 400) -> float:
    """The frame with its cross tubes ending at +-y, grown from the y=104 golden.

    Each tube gains ANNULUS_AREA * (y - 104) at each end, less what the gained
    length overlaps of the rail (mirror symmetry: both ends alike).
    """
    expected = json.loads((GOLDEN_DIR / "expected.json").read_text(encoding="utf-8"))
    volume = float(expected["properties"]["volume"])
    distance, centres = _frame_centreline()
    for centre in centres:
        gained = _rail_overlap(centre, 104.0, y, distance, n)
        volume += 2 * (ANNULUS_AREA * (y - 104.0) - gained)
    return volume


def test_the_derivation_reproduces_independent_numbers() -> None:
    """The centreline case against the twin extrapolation and the tree, and the
    straight-run tube against the closed form of two crossing annular tubes."""
    assert _frame_volume(110.0) == pytest.approx(CENTRELINE_VOLUME, abs=5e-3)
    assert _frame_volume(122.7) == pytest.approx(SKIN_VOLUME, abs=5e-3)
    # Half the intersection of two perpendicular equal annular cylinders,
    # (1/2)[F(ro,ro) - 2F(ro,ri) + F(ri,ri)] = 340.193 (the golden's derivation):
    # the tube on the straight lower run gains it between centreline and skin.
    distance, centres = _frame_centreline()
    straight = centres[2]
    gained = _rail_overlap(straight, 110.0, 122.7, distance, 400)
    assert gained == pytest.approx(340.193, abs=1e-3)


# --- the frame through the product's path ------------------------------------


def _shells(body: BodyShape) -> list[float]:
    """Every shell's oriented volume (outer positive, voids negative)."""
    assert body.wrapped is not None
    solids = read_solids(body.wrapped).solids
    return [shell.volume for solid in solids for shell in solid.shells]


def test_tubes_ending_on_the_rail_centreline_are_right() -> None:
    evaluation = evaluate_tree(_frame_with_tubes_ending_at(110.0))
    assert all(r.status == "ok" for r in evaluation.result.features)
    assert evaluation.body is not None
    assert measure_shape(evaluation.body).volume == pytest.approx(
        CENTRELINE_VOLUME, abs=GOLDEN_TOL
    )
    assert len(evaluation.body.solids()) == 1


def _symmetric_frame() -> EvaluateTreeRequest:
    """The skin-case frame modelled symmetrically (the review of 89edf74): each
    cross tube extruded from y=0 to the near rail's skin, MERGED into the rails,
    then a features-scope mirror about XZ reflects the four tube extrudes, so
    the joints on the far rail are made by the MIRROR's fuse."""
    data: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    tubes: list[str] = []
    features: list[dict[str, Any]] = []
    for item in data["features"]:
        kind, params = item["feature"]["type"], item["feature"]["params"]
        if kind == "boolean" and params["tool"]["feature_id"] in tubes:
            continue  # the tubes merge instead
        if kind == "datum" and item["id"].endswith("04"):
            params["offset_mm"] = 0.0
        if kind == "extrude":
            params["distance_mm"] = 122.7  # y = 0 to the y = -110 rail's skin
            params["merge"] = True
            tubes.append(item["id"])
        if kind == "sketch" and item["id"].endswith("1e"):  # before the head
            scope = {
                "kind": "features",
                "features": [{"kind": "feature", "feature_id": t} for t in tubes],
            }
            features.append(
                {
                    "id": "00000000-0000-0000-0000-0000000000f0",
                    "feature": {
                        "type": "mirror",
                        "version": 1,
                        "params": {
                            "plane": {"kind": "datum_plane", "plane": "XZ"},
                            "scope": scope,
                        },
                    },
                }
            )
        features.append(item)
    data["features"] = features
    return EvaluateTreeRequest.model_validate(data)


def test_a_features_scope_mirror_of_skin_tubes_is_right() -> None:
    """The mirror's fuse is guarded too: unguarded it shipped 725506.71."""
    evaluation = evaluate_tree(_symmetric_frame())
    assert all(r.status == "ok" for r in evaluation.result.features), [
        (r.feature_id, r.error) for r in evaluation.result.features if r.error
    ]
    assert evaluation.body is not None
    assert len(evaluation.body.solids()) == 1
    assert measure_shape(evaluation.body).volume == pytest.approx(
        SKIN_VOLUME, abs=GOLDEN_TOL
    )


def test_tubes_ending_past_the_centreline_are_refused_not_shipped_wrong() -> None:
    evaluation = evaluate_tree(_frame_with_tubes_ending_at(110.5))
    errors = [r for r in evaluation.result.features if r.error is not None]
    assert errors, "a body the kernel rejects must not build clean"
    assert {r.error.code for r in errors if r.error} == {"invalid_body"}


@pytest.fixture(scope="module")
def skin_body() -> BodyShape:
    """The frame with its cross tubes butted on the rails' outer skin."""
    evaluation = evaluate_tree(_frame_with_tubes_ending_at(122.7))
    assert all(r.status == "ok" for r in evaluation.result.features), [
        (r.feature_id, r.error) for r in evaluation.result.features if r.error
    ]
    assert evaluation.body is not None
    return evaluation.body


def test_tubes_ending_at_the_rail_skin_are_right(skin_body: BodyShape) -> None:
    """732801.92 (above the member sum) before the guard; the derived 718211.506
    after its fuzzy repair of the front-apex union."""
    members = 2 * RAIL_VOLUME + 4 * ANNULUS_AREA * 2 * 122.7 + HEAD_VOLUME
    volume = measure_shape(skin_body).volume
    assert volume <= members
    assert volume == pytest.approx(SKIN_VOLUME, abs=GOLDEN_TOL)
    assert len(skin_body.solids()) == 1
    shells = _shells(skin_body)
    assert sum(1 for v in shells if v > 0) == 1
    # The front-apex tube's two sealed compartments are voids again (the other
    # tubes' compartments differ in size: they cross straight runs or corners).
    apex = [v for v in shells if v == pytest.approx(-COMPARTMENT_VOLUME, abs=1)]
    assert len(apex) == 2


def test_the_skin_frame_round_trips_through_step(
    skin_body: BodyShape, tmp_path: Path
) -> None:
    path = tmp_path / "skin.step"
    export_step(skin_body, path)
    imported = import_step(path).solids()
    assert len(imported) == 1
    assert measure_shape(imported[0]).volume == pytest.approx(
        measure_shape(skin_body).volume, abs=ROUNDTRIP_TOL
    )


# --- the two-solid reproduction ----------------------------------------------

BEND_RADIUS = 80.0
TUBE_START_Y = 70.0
SKIN_Y = RAIL_PLANE_Y + RO


def _bend() -> Solid:
    """A 90 deg annular R80 bend about the Y axis, centred on the y=110 plane,
    spanning -45..45 deg about +X (the frame's front-apex fillet, isolated)."""
    start = math.radians(-45.0)
    centre = (
        BEND_RADIUS * math.cos(start),
        RAIL_PLANE_Y,
        -BEND_RADIUS * math.sin(start),
    )
    plane = Plane(
        origin=centre,
        x_dir=(math.cos(start), 0.0, -math.sin(start)),
        z_dir=(math.sin(start), 0.0, math.cos(start)),
    )
    annulus = Face(
        Wire([Edge.make_circle(RO, plane)]), [Wire([Edge.make_circle(RI, plane)])]
    )
    return Solid.revolve(annulus, 90.0, Axis((0, 0, 0), (0, 1, 0)))


def _tube(y_end: float) -> Solid:
    """The annular Y tube through the bend's centre circle, from y=70 to *y_end*."""
    plane = Plane(origin=(BEND_RADIUS, TUBE_START_Y, 0.0), z_dir=(0, 1, 0))
    length = y_end - TUBE_START_Y
    tube = Solid.make_cylinder(RO, length, plane).cut(
        Solid.make_cylinder(RI, length, plane)
    )
    return tube.solids()[0]


def _bend_distance(
    x: NDArray[np.float64], z: NDArray[np.float64]
) -> NDArray[np.float64]:
    """In-plane distance to the bend's centre circle (the tube stays in its span)."""
    return np.abs(np.hypot(x, z) - BEND_RADIUS)


def _repro_union_volume() -> float:
    """Bend (Pappus) + tube - their overlap (the quadrature above)."""
    bend = math.pi / 2 * BEND_RADIUS * ANNULUS_AREA
    tube = ANNULUS_AREA * (SKIN_Y - TUBE_START_Y)
    overlap = _rail_overlap(
        (BEND_RADIUS, 0.0), TUBE_START_Y, SKIN_Y, _bend_distance, 400
    )
    return bend + tube - overlap


def test_occt_drops_the_void_of_a_tube_ending_on_a_bends_skin() -> None:
    """The kernel defect itself, unguarded: the union exceeds its members' sum.

    A canary: if an OCCT upgrade fixes it, this fails, and the docstrings that
    describe the defect need revisiting (the guard stays; it is the class).
    """
    bend, tube = _bend(), _tube(SKIN_Y)
    raw = bend.fuse(tube)
    assert raw.volume > bend.volume + tube.volume + 1000.0


def test_the_guarded_union_of_the_two_solid_reproduction_is_right() -> None:
    bend, tube = _bend(), _tube(SKIN_Y)
    expected = _repro_union_volume()
    for body in (boolean_bodies(bend, tube, "union"), combine_body(bend, tube, "add")):
        assert len(body.solids()) == 1
        assert measure_shape(body).volume == pytest.approx(expected, abs=GOLDEN_TOL)
        shells = _shells(body)
        assert len(shells) == 2 and shells[0] > 0
        assert shells[1] == pytest.approx(-COMPARTMENT_VOLUME, abs=1)


def test_the_mirror_and_pattern_fuses_of_the_reproduction_are_right() -> None:
    """The same defect through a mirror's and a pattern's one-shot fuse (raw:
    27747.27 against a member sum of 21337.98)."""
    expected = _repro_union_volume()
    for body in (
        fuse_reflected_tools(_bend(), [_tube(SKIN_Y)]),
        _fuse_and_finalize(_bend(), [_tube(SKIN_Y)], 2),
    ):
        assert len(body.solids()) == 1
        assert measure_shape(body).volume == pytest.approx(expected, abs=GOLDEN_TOL)


def test_two_straight_tubes_ending_on_the_skin_need_no_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The straight case OCCT gets right: the guard passes it, never retrying."""

    def no_retry(*_: object) -> None:
        raise AssertionError("a right result must not be re-run fuzzy")

    monkeypatch.setattr("geometry.kernel.boolean.fuzzy_boolean_solids", no_retry)
    rail_plane = Plane(origin=(-100.0, 0.0, 0.0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    rail = Solid.make_cylinder(RO, 200.0, rail_plane).cut(
        Solid.make_cylinder(RI, 200.0, rail_plane)
    )
    cross_plane = Plane(origin=(0.0, -60.0, 0.0), z_dir=(0, 1, 0))
    cross = Solid.make_cylinder(RO, 60.0 + RO, cross_plane).cut(
        Solid.make_cylinder(RI, 60.0 + RO, cross_plane)
    )
    guarded = boolean_bodies(rail.solids()[0], cross.solids()[0], "union")
    # rail + cross - the full crossing of two equal annular tubes (2 x 340.193)
    expected = ANNULUS_AREA * (200.0 + 60.0 + RO) - 2 * 340.1929
    assert measure_shape(guarded).volume == pytest.approx(expected, abs=GOLDEN_TOL)


#: Repairs the two-solid reproduction in a pristine interpreter and prints its
#: fingerprint (worker-restart emulation, RESEARCH §9).
_RESTART_PROBE = """\
import importlib.util
spec = importlib.util.spec_from_file_location("tube_probe", {module!r})
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
print(mod._repaired_fingerprint())
"""


def _repaired_fingerprint() -> str:
    """Volume, area and topology of the repaired union, to the last bit."""
    body = boolean_bodies(_bend(), _tube(SKIN_Y), "union")
    props = measure_shape(body)
    return (
        f"{props.volume!r} {props.surface_area!r} {len(body.faces())} "
        f"{len(body.edges())} {_shells(body)!r}"
    )


def test_the_repair_is_deterministic_across_a_worker_restart() -> None:
    here = _repaired_fingerprint()
    assert _repaired_fingerprint() == here
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE.format(module=__file__)],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout.strip() == here


# --- the guard's rules ---------------------------------------------------------


def _reading(*shells: float, closed: bool = True) -> BodyReading:
    solid = SolidReading(sum(shells), tuple(ShellReading(v, closed) for v in shells))
    return BodyReading((solid,))


@pytest.mark.parametrize(
    ("operation", "a", "b", "result", "words"),
    [
        ("union", 100.0, 50.0, 151.0, "exceeds the sum of the bodies"),
        ("union", 100.0, 50.0, 99.0, "below the largest body"),
        ("subtract", 100.0, 50.0, 101.0, "exceeds the target"),
        ("subtract", 100.0, 50.0, 49.0, "below the target less every tool"),
        ("intersect", 100.0, 50.0, 51.0, "exceeds the smallest body"),
    ],
)
def test_each_volume_bound_is_enforced(
    operation: GuardedOperation, a: float, b: float, result: float, words: str
) -> None:
    violation = integrity_violation(operation, a, b, _reading(result))
    assert violation is not None and words in violation


@pytest.mark.parametrize(
    ("operation", "result"),
    [
        ("union", 150.0),
        ("union", 100.0),
        ("subtract", 100.0),
        ("subtract", 50.0),
        ("intersect", 50.0),
        ("intersect", 1e-3),
    ],
)
def test_a_result_on_its_bounds_passes(
    operation: GuardedOperation, result: float
) -> None:
    assert integrity_violation(operation, 100.0, 50.0, _reading(result)) is None


def test_a_variadic_boolean_is_bounded_by_all_its_tools() -> None:
    """A mirror's or pattern's one-shot boolean: union in [max, A + sum], cut in
    [A - sum, A]; overlapping tools legitimately sum past the union."""
    tools = [50.0, 50.0]
    assert volume_violation("union", 100.0, tools, 199.0) is None
    assert volume_violation("union", 100.0, tools, 120.0) is None
    assert volume_violation("union", 100.0, tools, 201.0) is not None
    assert volume_violation("subtract", 100.0, tools, 1.0) is None
    assert volume_violation("subtract", 100.0, tools, -1.0) is not None


def test_shell_rules_are_enforced() -> None:
    two_outer = integrity_violation("union", 100.0, 50.0, _reading(80.0, 40.0))
    assert two_outer is not None and "2 outer shells" in two_outer
    inverted = integrity_violation("union", 100.0, 50.0, _reading(-120.0))
    assert inverted is not None and "0 outer shells" in inverted
    opened = integrity_violation("union", 100.0, 50.0, _reading(120.0, closed=False))
    assert opened is not None and "open shell" in opened
    assert integrity_violation("union", 100.0, 50.0, _reading(130.0, -10.0)) is None


#: Fake operands (1 and 0.5 mm^3) and an impossible "union" of them (5 mm^3),
#: real solids so the confirmation on reported volumes sees the same numbers.
TARGET, TOOL = Solid.make_box(1, 1, 1), Solid.make_box(0.5, 1, 1)
TOO_BIG = Solid.make_box(5, 1, 1)


def test_a_passing_result_is_returned_as_is_and_never_retried() -> None:
    calls: list[float | None] = []

    def attempt(fuzzy: float | None) -> tuple[BodyShape, BodyReading]:
        calls.append(fuzzy)
        return TARGET, _reading(1.0)

    measured = guarded_boolean(attempt, "union", (TARGET, TOOL), 1.0, 0.5)
    assert measured.shape is TARGET and measured.volume == 1.0
    assert calls == [None]


def test_a_violation_is_retried_fuzzy_once_then_refused() -> None:
    calls: list[float | None] = []

    def attempt(fuzzy: float | None) -> tuple[BodyShape, BodyReading]:
        calls.append(fuzzy)
        return TOO_BIG, _reading(5.0)

    with pytest.raises(BooleanIntegrityError, match="tangent contact"):
        guarded_boolean(attempt, "union", (TARGET, TOOL), 1.0, 0.5)
    assert calls == [None, FUZZY_RETRY_MM]


def test_a_retry_the_op_itself_refuses_is_a_refusal_too() -> None:
    def attempt(fuzzy: float | None) -> tuple[BodyShape, BodyReading]:
        if fuzzy is not None:
            raise BooleanError("seven lumps")
        return TOO_BIG, _reading(5.0)

    with pytest.raises(BooleanIntegrityError):
        guarded_boolean(attempt, "union", (TARGET, TOOL), 1.0, 0.5)


def test_a_bound_the_cheap_rule_misreads_is_confirmed_before_acting() -> None:
    """GProp's fixed-order rule reads a lofted solid ~10 % off; a bound that
    fails only on it is checked on the reported volumes, and passes there."""
    calls: list[float | None] = []

    def attempt(fuzzy: float | None) -> tuple[BodyShape, BodyReading]:
        calls.append(fuzzy)
        return TARGET, _reading(5.0)  # misread: the solid itself holds 1 mm^3

    measured = guarded_boolean(attempt, "union", (TARGET, TOOL), 1.0, 0.5)
    assert measured.shape is TARGET
    assert calls == [None]
