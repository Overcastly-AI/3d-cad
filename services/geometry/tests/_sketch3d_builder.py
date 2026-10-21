"""Trees for the 3D sketch tests and golden (SKETCH-3D).

Plain JSON builders, kernel-free, so the golden's ``model.json`` is generated
from the same code the tests read (``python`` this file with an output path
regenerates it; the expected numbers are worked out by hand in
:func:`reference_points` and the golden's ``expected.json``).

The bike skeleton is the reference part's frame (docs/reference-parts/bike.md)
in MODEL space: BB at the origin, X forward, Z up, Y to the left. The main
triangle is the 2D skeleton's (seat tube 500 at 73.5 deg, head tube top at
reach 390 / stack 570, head tube 150 at 73 deg); the rear triangle is what a
2D sketch cannot hold: the rear axle 410 from the BB (chainstay) and 70 above
it (BB drop), the two dropouts 130 apart across Y (road hub spacing), so the
chain and seat stays splay out of the XZ plane.

The points are TYPED a little off, as a user types rounded coordinates, and
the dimensions put them on the reference numbers: the seat tube's free end
slides 2 mm along its line to 500, the head tube's 2 mm to 150, and the two
dropouts 1 mm each across Y to 130 apart, along their Y line.
"""

import json
import math
import sys
from pathlib import Path
from typing import Any

PART = "00000000-0000-0000-0000-0000000003d1"

SEAT_ANGLE_DEG = 73.5
SEAT_TUBE_MM = 500.0
REACH_MM, STACK_MM = 390.0, 570.0
HEAD_TUBE_MM = 150.0
HEAD_ANGLE_DEG = 73.0
CHAINSTAY_MM = 410.0
BB_DROP_MM = 70.0
HUB_SPACING_MM = 130.0

#: (OD, wall) per tube: the 2D skeleton golden's main tubes, and road stays.
TUBES = {
    "down": (44.0, 1.2),
    "seat": (31.8, 1.0),
    "top": (35.0, 1.0),
    "head": (50.0, 3.0),
    "cs_l": (22.0, 1.0),
    "cs_r": (22.0, 1.0),
    "ss_l": (16.0, 1.0),
    "ss_r": (16.0, 1.0),
}

#: Line id -> (start point, end point).
LINES = {
    "seat": ("bb", "st"),
    "top": ("st", "ht"),
    "head": ("ht", "hb"),
    "down": ("bb", "hb"),
    "cs_l": ("bb", "dl"),
    "cs_r": ("bb", "dr"),
    "ss_l": ("st", "dl"),
    "ss_r": ("st", "dr"),
    "axle": ("dl", "dr"),
}


def fid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012x}"


def reference_points() -> dict[str, tuple[float, float, float]]:
    """Every skeleton point in world (X, Y, Z) mm, by hand."""
    seat = math.radians(SEAT_ANGLE_DEG)
    head = math.radians(HEAD_ANGLE_DEG)
    axle_x = -math.sqrt(CHAINSTAY_MM**2 - BB_DROP_MM**2)
    half = HUB_SPACING_MM / 2
    return {
        "bb": (0.0, 0.0, 0.0),
        "st": (-SEAT_TUBE_MM * math.cos(seat), 0.0, SEAT_TUBE_MM * math.sin(seat)),
        "ht": (REACH_MM, 0.0, STACK_MM),
        "hb": (
            REACH_MM + HEAD_TUBE_MM * math.cos(head),
            0.0,
            STACK_MM - HEAD_TUBE_MM * math.sin(head),
        ),
        "dl": (axle_x, half, BB_DROP_MM),
        "dr": (axle_x, -half, BB_DROP_MM),
    }


def typed_points() -> dict[str, tuple[float, float, float]]:
    """Where the points are typed: the free ends short of their dimensions."""
    seat = math.radians(SEAT_ANGLE_DEG)
    head = math.radians(HEAD_ANGLE_DEG)
    ref = reference_points()
    short = 2.0
    return {
        **ref,
        "st": (
            -(SEAT_TUBE_MM - short) * math.cos(seat),
            0.0,
            (SEAT_TUBE_MM - short) * math.sin(seat),
        ),
        "hb": (
            REACH_MM + (HEAD_TUBE_MM - short) * math.cos(head),
            0.0,
            STACK_MM - (HEAD_TUBE_MM - short) * math.sin(head),
        ),
        "dl": (ref["dl"][0], ref["dl"][1] - 1.0, ref["dl"][2]),
        "dr": (ref["dr"][0], ref["dr"][1] + 1.0, ref["dr"][2]),
    }


def _vec(p: tuple[float, float, float]) -> dict[str, float]:
    return {"x": p[0], "y": p[1], "z": p[2]}


def skeleton_3d(n: int) -> dict[str, Any]:
    """The 3D sketch: BB snapped to the origin, the head tube top fixed where
    typed, three driving dimensions and one Along Y."""
    entities: list[dict[str, Any]] = []
    for key, p in typed_points().items():
        point: dict[str, Any] = {"id": key, "kind": "point", "position": _vec(p)}
        if key == "bb":
            point["snap"] = {"kind": "origin"}
        entities.append(point)
    for key, (a, b) in LINES.items():
        line: dict[str, Any] = {"id": key, "kind": "line", "start": a, "end": b}
        if key == "axle":
            line["construction"] = True
        entities.append(line)
    constraints: list[dict[str, Any]] = [
        {"kind": "fixed", "point": "ht"},
        {"kind": "length", "line": "seat", "value_mm": SEAT_TUBE_MM},
        {"kind": "length", "line": "head", "value_mm": HEAD_TUBE_MM},
        {"kind": "along", "line": "axle", "axis": "y"},
        {"kind": "distance", "a": "dl", "b": "dr", "value_mm": HUB_SPACING_MM},
    ]
    return {
        "id": fid(n),
        "feature": {
            "type": "sketch_3d",
            "version": 1,
            "params": {"entities": entities, "constraints": constraints},
        },
    }


def pipe(n: int, sketch_n: int, line: str) -> dict[str, Any]:
    od, wall = TUBES[line]
    return {
        "id": fid(n),
        "feature": {
            "type": "pipe",
            "version": 1,
            "params": {
                "path": [
                    {
                        "kind": "sketch_curve",
                        "sketch": {"kind": "feature", "feature_id": fid(sketch_n)},
                        "entity": line,
                    }
                ],
                "outer_diameter_mm": od,
                "wall_thickness_mm": wall,
                "operation": "add",
                "merge": True,
            },
        },
    }


#: The golden's tubes: the main triangle, the 2D skeleton golden's four, so
#: the golden's numbers are that golden's hand-derived ones. The stays are in
#: the skeleton and piped in tests/test_sketch_3d.py against a build123d twin;
#: their oblique tube-tube faces move 4e-5 mm in a STEP round trip (OCCT's
#: re-approximation, the twin's too), past the golden gates' 1e-7 centroid bound.
GOLDEN_TUBES = ("down", "seat", "top", "head")


def bike_frame_3d(tubes: tuple[str, ...] = GOLDEN_TUBES) -> dict[str, Any]:
    """The 3D skeleton and one ring Pipe per tube, joined into one body."""
    features = [skeleton_3d(1)]
    features += [pipe(n, 1, name) for n, name in enumerate(tubes, start=2)]
    return {
        "part_id": PART,
        "tree_version": 1,
        "features": features,
        "linear_deflection": 0.1,
    }


if __name__ == "__main__":  # pragma: no cover - golden regeneration helper
    Path(sys.argv[1]).write_text(json.dumps(bike_frame_3d(), indent=2) + "\n")
