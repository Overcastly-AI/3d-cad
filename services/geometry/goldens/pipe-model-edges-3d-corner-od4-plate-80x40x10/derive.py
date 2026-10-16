"""Re-derive this golden's mass properties in closed form (no GProp, no OCCT).

The golden is the 80 x 40 x 10 plate (extruded from the origin, +Z) and, as a
NEW BODY, a solid pipe of OD 4 (r = 2) along three of the plate's edges picked
in the viewport: (0,40,0)-(0,0,0), (0,0,0)-(80,0,0), (80,0,0)-(80,0,10). They
chain into the 3D polyline (0,40,0) -> (0,0,0) -> (80,0,0) -> (80,0,10) with a
square corner in the XY plane and a square corner in the XZ plane, both
MITRED. The solid is the same whichever way the chain is travelled.

A mitred run from P0 along unit d for length L is
{P0 + s d + u : u in the disc normal to d, s_s(u) <= s <= L + s_e(u)}. With
the turn into the next direction d' = cos(phi) d + sin(phi) m' (m' the unit
component of d' normal to d), the bisecting end plane through the corner gives
s_e = -k_e (u . m'), k_e = tan(phi / 2); the start plane (turn from d_prev,
m its unit normal component) gives s_s = -k_s (u . m). An open end has k = 0.
With A = pi r^2 and I = int (u . m)^2 dA = pi r^4 / 4 for any unit m normal
to d:

    volume  = A L                       (the linear terms integrate to 0)
    moment  = A L P0 + d (A L^2 + (k_e^2 - k_s^2) I) / 2 + (k_s m - k_e m') I
    area    = 2 pi r L per run, plus A per open end cap

This is the planar derive.py of pipe-mitred-corners-ring-od20-t2-100x80x60
with the two ends' turn directions m and m' kept apart (here the run along X
turns in from -Y and out to +Z). The plate adds 80 * 40 * 10 at (40, 20, 5)
and 2 (80*40 + 80*10 + 40*10) of area; the two bodies only touch along the
edges' quarter-discs, and the measured body is their compound, so volume,
area and moment add. ``tests/test_golden_derivations.py`` re-runs this
against expected.json.
"""

import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PLATE = (80.0, 40.0, 10.0)

Vec = tuple[float, float, float]


@dataclass(frozen=True)
class Derivation:
    volume: float
    surface_area: float
    centroid: tuple[float, float, float]


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _unit(a: Vec) -> Vec:
    return _scale(a, 1.0 / math.sqrt(_dot(a, a)))


def _turn(d: Vec, other: Vec) -> tuple[float, Vec]:
    """(tan of half the turn between d and other, unit normal part of other)."""
    normal = _sub(other, _scale(d, _dot(d, other)))
    sin = math.sqrt(_dot(normal, normal))
    return sin / (1 + _dot(d, other)), _scale(normal, 1.0 / sin)


def derive(model: dict[str, Any]) -> Derivation:
    pipe = model["features"][-1]["feature"]["params"]
    radius = pipe["outer_diameter_mm"] / 2

    def end(segment: dict[str, Any], key: str) -> Vec:
        p = segment["selector"]["signature"][key]
        return (p["x"], p["y"], p["z"])

    first, second, third = pipe["path"]
    # Travel order by hand (module docstring): the picks' shared ends join them.
    path = [end(first, "end_b"), end(first, "end_a"), end(second, "end_b")]
    path.append(end(third, "end_b"))
    assert end(second, "end_a") == path[1] and end(third, "end_a") == path[2]

    area_section = math.pi * radius**2
    inertia = math.pi * radius**4 / 4
    directions = [_unit(_sub(b, a)) for a, b in itertools.pairwise(path)]
    volume = 0.0
    moment = [0.0, 0.0, 0.0]
    surface = 2 * area_section
    zero: Vec = (0.0, 0.0, 0.0)
    for index, (start, d) in enumerate(zip(path, directions, strict=False)):
        length = math.dist(start, path[index + 1])
        k_s, m_s = (0.0, zero) if index == 0 else _turn(d, directions[index - 1])
        k_e, m_e = (
            (0.0, zero)
            if index + 1 == len(directions)
            else _turn(d, directions[index + 1])
        )
        volume += area_section * length
        along = (area_section * length**2 + (k_e**2 - k_s**2) * inertia) / 2
        for axis in range(3):
            moment[axis] += (
                area_section * length * start[axis]
                + d[axis] * along
                + (k_s * m_s[axis] - k_e * m_e[axis]) * inertia
            )
        surface += 2 * math.pi * radius * length

    w, h, t = PLATE
    plate_volume = w * h * t
    for axis, centre in enumerate((w / 2, h / 2, t / 2)):
        moment[axis] += plate_volume * centre
    volume += plate_volume
    surface += 2 * (w * h + w * t + h * t)
    return Derivation(
        volume=volume,
        surface_area=surface,
        centroid=(moment[0] / volume, moment[1] / volume, moment[2] / volume),
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
