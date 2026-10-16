"""Re-derive this golden's mass properties in closed form (no GProp, no OCCT).

The golden is a ring pipe (OD 2R = 20, wall 2, so r = 8) along three picked
lines with two square corners, MITRED. The picks are e1 (drawn (100,80) ->
(100,0)), e3 ((40,80) -> (100,80)) and e2 ((0,0) -> (100,0)); the chain runs
so the first pick is travelled start to end, so it starts at the free end on
e1's start side: (40,80) -> (100,80) -> (100,0) -> (0,0).

A mitred run from P0 along unit d for length L, with in-plane lateral unit n,
is the set {P0 + s d + y n + z b : (y, z) in the ring, s_s(y) <= s <= L + s_e(y)}
where each end is the plane bisecting the turn there. With the turn into the
next direction d', the end plane through the corner gives s_e = -k_e y,
k_e = (n . d') / (1 + d . d'); the start plane (turn from d_prev) gives
s_s = -k_s y, k_s = (n . d_prev) / (1 + d . d_prev); an open end has k = 0.
Writing A = pi (R^2 - r^2) and I = int y^2 dA = pi (R^4 - r^4) / 4:

    volume  = A L                       (the linear terms integrate to 0)
    moment  = A L P0 + d (A L^2 + (k_e^2 - k_s^2) I) / 2 + n (k_s - k_e) I
    area    = 2 pi (R + r) L per run, plus A per open end cap

so the centroid is sum(moment) / sum(volume). ``tests/test_golden_derivations.py``
re-runs this against expected.json.
"""

import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
R, WALL = 10.0, 2.0


@dataclass(frozen=True)
class Derivation:
    volume: float
    surface_area: float
    centroid: tuple[float, float, float]


Vec = tuple[float, float]


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _unit(a: Vec) -> Vec:
    length = math.hypot(*a)
    return (a[0] / length, a[1] / length)


def derive(model: dict[str, Any]) -> Derivation:
    entities = {
        e["id"]: e for e in model["features"][0]["feature"]["params"]["entities"]
    }

    def point(eid: str, end: str) -> Vec:
        return (entities[eid][end]["x"], entities[eid][end]["y"])

    # Travel order by hand (module docstring): e3 forward, e1 forward, e2 reversed.
    path = [point("e3", "start"), point("e1", "start"), point("e1", "end")]
    path.append(point("e2", "start"))
    r = R - WALL
    area_section = math.pi * (R**2 - r**2)
    inertia = math.pi * (R**4 - r**4) / 4
    directions = [_unit(_sub(b, a)) for a, b in itertools.pairwise(path)]
    volume = 0.0
    moment = [0.0, 0.0]
    surface = 2 * area_section
    for index, (start, d) in enumerate(zip(path, directions, strict=False)):
        length = math.dist(start, path[index + 1])
        n = (-d[1], d[0])
        k_s = k_e = 0.0
        if index > 0:
            before = directions[index - 1]
            k_s = _dot(n, before) / (1 + _dot(d, before))
        if index + 1 < len(directions):
            after = directions[index + 1]
            k_e = _dot(n, after) / (1 + _dot(d, after))
        volume += area_section * length
        along = (area_section * length**2 + (k_e**2 - k_s**2) * inertia) / 2
        across = (k_s - k_e) * inertia
        for axis in (0, 1):
            moment[axis] += (
                area_section * length * start[axis] + d[axis] * along + n[axis] * across
            )
        surface += 2 * math.pi * (R + r) * length
    return Derivation(
        volume=volume,
        surface_area=surface,
        centroid=(moment[0] / volume, moment[1] / volume, 0.0),
    )


def main() -> int:
    model = json.loads((HERE / "model.json").read_text())
    expected = json.loads((HERE / "expected.json").read_text())
    derived = derive(model)
    pinned = expected["properties"]
    print(f"volume   {derived.volume!r} (expected.json {pinned['volume']!r})")
    print(
        f"area     {derived.surface_area!r} (expected.json {pinned['surface_area']!r})"
    )
    print(f"centroid {derived.centroid!r}")
    tolerance = float(expected["tolerance"])
    ok = abs(derived.volume - pinned["volume"]) <= tolerance and all(
        abs(c - pinned["centroid"][axis]) <= tolerance
        for c, axis in zip(derived.centroid, "xyz", strict=True)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
