"""Trees for the Pipe / Plane Along Path tests and goldens (PIPE-ALONG-PATH).

Plain JSON builders, kernel-free, so the goldens' ``model.json`` files are
generated from the same code the tests read (``python -m`` this file with an
output directory regenerates them; the expected numbers are hand-derived in
each golden's ``expected.json``, never read back from the kernel).

The bike skeleton is the reference part's frame (docs/reference-parts/bike.md):
BB at the origin, X forward, Z up, on the XZ plane (sketch y is world Z). One
construction line is the horizontal the angles are measured from; four lines
are the seat, top, head and down tubes; and the dimensions make it fully
constrained: seat tube 500 at 73.5 deg, head tube top at reach 390 / stack
570, head tube 150 long at the head angle.
"""

import json
import math
import sys
from pathlib import Path
from typing import Any

PART = "00000000-0000-0000-0000-0000000000b1"


def fid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012x}"


def feature(n: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"id": fid(n), "feature": body}


def request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "part_id": PART,
        "tree_version": 1,
        "features": features,
        "linear_deflection": 0.1,
    }


def line(
    eid: str,
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    construction: bool = False,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }
    if construction:
        entity["construction"] = True
    return entity


def arc(
    eid: str,
    centre: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "arc",
        "center": {"x": centre[0], "y": centre[1]},
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def sketch(
    n: int,
    entities: list[dict[str, Any]],
    plane: str = "XY",
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return feature(
        n,
        {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": plane},
                "entities": entities,
                "constraints": constraints or [],
            },
        },
    )


def curve(sketch_n: int, entity: str) -> dict[str, Any]:
    return {
        "kind": "sketch_curve",
        "sketch": {"kind": "feature", "feature_id": fid(sketch_n)},
        "entity": entity,
    }


def pipe(
    n: int,
    path: list[dict[str, Any]],
    od: float,
    wall: float | None = None,
    *,
    operation: str = "add",
    merge: bool = True,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "path": path,
        "outer_diameter_mm": od,
        "operation": operation,
        "merge": merge,
    }
    if wall is not None:
        params["wall_thickness_mm"] = wall
    return feature(n, {"type": "pipe", "version": 1, "params": params})


def along_path(
    n: int,
    path: dict[str, Any],
    *,
    ratio: float | None = None,
    distance: float | None = None,
    flip: bool = False,
) -> dict[str, Any]:
    params: dict[str, Any] = {"kind": "along_path", "path": path, "flip": flip}
    if distance is not None:
        params.update(measure="distance", distance_mm=distance)
    else:
        params.update(measure="ratio", ratio=0.0 if ratio is None else ratio)
    return feature(n, {"type": "datum", "version": 1, "params": params})


# --- the bike skeleton -------------------------------------------------------------

SEAT_ANGLE_DEG = 73.5
SEAT_TUBE_MM = 500.0
REACH_MM, STACK_MM = 390.0, 570.0
HEAD_TUBE_MM = 150.0
HEAD_ANGLE_DEG = 73.0

#: (OD, wall) per tube, the reference attempt's sections (top tube 35 x 1).
TUBES = {
    "down": (44.0, 1.2),
    "seat": (31.8, 1.0),
    "top": (35.0, 1.0),
    "head": (50.0, 3.0),
}


def skeleton_points(
    head_angle_deg: float = HEAD_ANGLE_DEG,
) -> dict[str, tuple[float, float]]:
    """The skeleton's joints in sketch (x, y) = world (X, Z), by hand."""
    seat = math.radians(SEAT_ANGLE_DEG)
    head = math.radians(head_angle_deg)
    st_top = (-SEAT_TUBE_MM * math.cos(seat), SEAT_TUBE_MM * math.sin(seat))
    ht_top = (REACH_MM, STACK_MM)
    ht_bottom = (
        REACH_MM + HEAD_TUBE_MM * math.cos(head),
        STACK_MM - HEAD_TUBE_MM * math.sin(head),
    )
    return {
        "bb": (0.0, 0.0),
        "st_top": st_top,
        "ht_top": ht_top,
        "ht_bottom": ht_bottom,
    }


def _at(entity: str, point: str) -> dict[str, str]:
    return {"entity": entity, "point": point}


def skeleton(n: int, head_angle_deg: float = HEAD_ANGLE_DEG) -> dict[str, Any]:
    """The fully-constrained skeleton, drawn ROUGHLY (1-3 mm and ~1 deg off) so
    the solve, not the drawing, puts every joint where the dimensions say."""
    p = skeleton_points(HEAD_ANGLE_DEG)
    rough = {k: (x + 1.5, y - 2.0) if k != "bb" else (x, y) for k, (x, y) in p.items()}
    entities = [
        line("h", (0.0, 0.0), (600.0, 0.0), construction=True),
        line("seat", rough["bb"], rough["st_top"]),
        line("top", rough["st_top"], rough["ht_top"]),
        line("head", rough["ht_top"], rough["ht_bottom"]),
        line("down", rough["bb"], rough["ht_bottom"]),
    ]
    constraints: list[dict[str, Any]] = [
        {"kind": "fixed", "point": _at("h", "start")},
        {"kind": "horizontal", "entity": "h"},
        {"kind": "distance", "entity": "h", "value_mm": 600.0},
        {"kind": "coincident", "a": _at("seat", "start"), "b": _at("h", "start")},
        {"kind": "coincident", "a": _at("down", "start"), "b": _at("h", "start")},
        {"kind": "coincident", "a": _at("top", "start"), "b": _at("seat", "end")},
        {"kind": "coincident", "a": _at("top", "end"), "b": _at("head", "start")},
        {"kind": "coincident", "a": _at("down", "end"), "b": _at("head", "end")},
        {"kind": "distance", "entity": "seat", "value_mm": SEAT_TUBE_MM},
        # Seat and horizontal share the BB corner, so the angle is the interior
        # one between them: 180 - 73.5.
        {"kind": "angle", "a": "h", "b": "seat", "value_deg": 180.0 - SEAT_ANGLE_DEG},
        {
            "kind": "point_distance",
            "a": _at("h", "start"),
            "b": _at("head", "start"),
            "direction": "horizontal",
            "value_mm": REACH_MM,
        },
        {
            "kind": "point_distance",
            "a": _at("h", "start"),
            "b": _at("head", "start"),
            "direction": "vertical",
            "value_mm": STACK_MM,
        },
        {"kind": "distance", "entity": "head", "value_mm": HEAD_TUBE_MM},
        # Head and horizontal share no corner: the angle between their drawn
        # directions, (1, 0) and down-and-forward along the head tube.
        {"kind": "angle", "a": "h", "b": "head", "value_deg": head_angle_deg},
    ]
    return sketch(n, entities, "XZ", constraints)


def bike_frame(head_angle_deg: float = HEAD_ANGLE_DEG) -> dict[str, Any]:
    """Four ring Pipes on ONE skeleton sketch, joined into one body."""
    features = [skeleton(1, head_angle_deg)]
    for n, name in enumerate(("down", "seat", "top", "head"), start=2):
        od, wall = TUBES[name]
        features.append(pipe(n, [curve(1, name)], od, wall))
    return request(features)


if __name__ == "__main__":  # pragma: no cover - golden regeneration helper
    out = Path(sys.argv[1])
    out.write_text(json.dumps(bike_frame(), indent=2) + "\n")
