"""Big-part feature-tree builders for the scaling benchmarks (docs/PERF.md).

Every golden and every e2e part in the repo is 3-8 features and <100 faces, so
nothing measured what a working engineer's real part costs. These builders
generate the two parts the scaling suite sweeps, on two INDEPENDENT axes:

* :func:`housing_tree` — **feature-count** axis. A 360 x 240 x 20 mm shelled
  tray lid with a realistic mixed feature vocabulary (sketch / extrude add /
  extrude cut / hole through / hole blind / fillet-on-picked-edge /
  fillet-on-predicate / shell / revolve / linear-pattern cut / mirror with an
  explicit ``features`` scope / offset datums). ``housing_tree(n)`` returns the
  first ``n`` features of ONE canonical sequence, so every sweep point is a
  strict PREFIX of every larger one and the points are directly comparable.
* :func:`heat_sink_tree` — **face-count** axis. A finned heat sink at a FIXED
  six features whose fin ``count`` drives the topology: 4 faces per fin, so
  face count scales while tree length does not. This isolates topology cost
  (tessellation, the provenance face matcher, export) from tree cost.

The builders emit plain ``dict`` payloads validated by
:class:`~py_kit.schemas.features.EvaluateTreeRequest`, not kernel objects — no
OCCT import here, so a builder bug fails as a pydantic 422 at the test, never as
a mysterious kernel raise.

DESIGN NOTES (measured, not assumed):

* Every drilled hole names the PRISTINE top face signature (area ``W*H``,
  centroid ``(0, 0, T)``). Cuts change that face's area, so the resolver's
  EXACT tier misses and the documented COPLANAR fallback tier resolves it —
  which is exactly the tier a real UI depends on after the second pocket.
* Sites are laid out on a 12 x 8 grid in the ``x > 0`` half of the tray, one
  motif per site, so motifs never intersect and a prefix is always a valid
  solid. The grid pitch (13.83 x 26.5 mm) is wider than the widest motif.
* The mirror uses the v2 ``scope: {"kind": "features"}`` reading. A whole-BODY
  mirror/pattern about a plane of symmetry is a measured DETAIL-DESTROYER on a
  part like this (body union fills every asymmetric pocket: 615975.6 ->
  615759.6 mm^3 for the mirror, 616188.2 -> 619328.3 mm^3 and 84 -> 43 faces
  for a 2-up circular pattern), which is correct per the shipped semantics but
  would make the benchmark part shrink as features are added. The local,
  explicitly-scoped forms add geometry the way a modeller means them to.
"""

from __future__ import annotations

import uuid
from typing import Any

# --- Housing tray: the feature-count axis -------------------------------------

#: Tray blank, centred on the origin (mm).
TRAY_W, TRAY_H, TRAY_T = 360.0, 240.0, 20.0
#: Shell wall left by the ``shell`` feature (bottom face open).
TRAY_WALL = 6.0
#: Radius of the whole-body ``axis_parallel`` Z corner round.
TRAY_CORNER_R = 8.0
#: Motif site grid, in the ``x > 0`` half only.
SITE_COLS, SITE_ROWS = 12, 8
SITE_MARGIN = 14.0
SITE_PITCH_X = (TRAY_W / 2 - SITE_MARGIN) / SITE_COLS
SITE_PITCH_Y = (TRAY_H - 2 * SITE_MARGIN) / SITE_ROWS
#: Features in the fixed base block (sketch, extrude, fillet, shell, datum).
HOUSING_BASE_FEATURES = 5

_XY = {"kind": "datum_plane", "plane": "XY"}


def _uid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _rect_entities(
    cx: float, cy: float, w: float, h: float, tag: str
) -> list[dict[str, Any]]:
    """Four closed lines of an axis-aligned rectangle, sketch-local ids ``tag0..3``."""
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [
        {
            "id": f"{tag}{i}",
            "kind": "line",
            "start": {"x": pts[i][0], "y": pts[i][1]},
            "end": {"x": pts[(i + 1) % 4][0], "y": pts[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]


def _sketch(plane: dict[str, Any], entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "sketch",
        "version": 1,
        "params": {"plane": plane, "entities": entities, "constraints": []},
    }


def _planar_face_ref(
    anchor: str, normal_z: float, centroid: tuple[float, float, float], area: float
) -> dict[str, Any]:
    """A stage-1 planar face ``SubshapeRef`` — what a pick UI echoes from /overlay."""
    return {
        "kind": "subshape",
        "feature_id": anchor,
        "subshape_type": "face",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "face",
                "surface": "plane",
                "normal": {"x": 0.0, "y": 0.0, "z": normal_z},
                "centroid": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
                "area_mm2": area,
            },
        },
    }


def _vertical_edge_ref(
    anchor: str, x: float, y: float, z_low: float, z_high: float
) -> dict[str, Any]:
    """A stage-1 ``EdgeSignature`` ref for a vertical straight edge.

    Analytic, not inspected: a pocket's corner edge runs from ``z_low`` to
    ``z_high`` at ``(x, y)``, and ``end_a``/``end_b`` are the canonically
    (lexicographically) ordered endpoints, which for a vertical edge means
    lower z first.
    """
    return {
        "kind": "subshape",
        "feature_id": anchor,
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "edge",
                "curve": "line",
                "end_a": {"x": x, "y": y, "z": z_low},
                "end_b": {"x": x, "y": y, "z": z_high},
                "midpoint": {"x": x, "y": y, "z": (z_low + z_high) / 2},
                "length_mm": z_high - z_low,
            },
        },
    }


def _site_centre(index: int) -> tuple[float, float]:
    col, row = index % SITE_COLS, (index // SITE_COLS) % SITE_ROWS
    return (
        SITE_MARGIN / 2 + SITE_PITCH_X * (col + 0.5),
        -TRAY_H / 2 + SITE_MARGIN + SITE_PITCH_Y * (row + 0.5),
    )


#: Features contributed by each motif of the 8-long cycle, in cycle order —
#: the sequence a caller needs to predict how many sites an ``n`` spans.
MOTIF_FEATURE_COUNTS = (3, 2, 2, 2, 3, 3, 2, 4)


class _TreeWriter:
    """Accumulates ``{"id", "feature"}`` envelopes with sequential UUIDs."""

    def __init__(self) -> None:
        self.features: list[dict[str, Any]] = []
        self._next = 1

    def add(self, payload: dict[str, Any]) -> str:
        feature_id = _uid(self._next)
        self._next += 1
        self.features.append({"id": feature_id, "feature": payload})
        return feature_id

    def __len__(self) -> int:
        return len(self.features)


def _housing_base(writer: _TreeWriter) -> tuple[str, dict[str, Any]]:
    """Plate -> corner rounds -> shell (bottom open) -> top-face datum."""
    profile = writer.add(_sketch(_XY, _rect_entities(0.0, 0.0, TRAY_W, TRAY_H, "o")))
    body = writer.add(
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": profile},
                "distance_mm": TRAY_T,
                "operation": "add",
                "direction": "normal",
            },
        }
    )
    writer.add(
        {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {"kind": "axis_parallel", "axis": "Z"},
                "radius_mm": TRAY_CORNER_R,
            },
        }
    )
    writer.add(
        {
            "type": "shell",
            "version": 1,
            "params": {
                "thickness_mm": TRAY_WALL,
                "faces": {
                    "kind": "faces",
                    "refs": [
                        _planar_face_ref(body, -1.0, (0.0, 0.0, 0.0), TRAY_W * TRAY_H)
                    ],
                },
            },
        }
    )
    top_datum = writer.add(
        {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "offset",
                "base": "XY",
                "offset_mm": TRAY_T,
                "flip": False,
            },
        }
    )
    return body, {"kind": "feature", "feature_id": top_datum}


def _emit_motif(
    writer: _TreeWriter, site: int, body: str, top_plane: dict[str, Any]
) -> None:
    """Append one site's motif — the 8-long realistic cycle."""
    cx, cy = _site_centre(site)
    kind = site % len(MOTIF_FEATURE_COUNTS)

    def top_face() -> dict[str, Any]:
        return _planar_face_ref(body, 1.0, (0.0, 0.0, TRAY_T), TRAY_W * TRAY_H)

    def cut(profile: str, depth: float) -> str:
        return writer.add(
            {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": profile},
                    "distance_mm": depth,
                    "operation": "cut",
                    "direction": "reverse",
                },
            }
        )

    if kind == 0:  # blind rectangular pocket + one rounded corner
        profile = writer.add(
            _sketch(top_plane, _rect_entities(cx, cy, 9.0, 8.0, f"p{site}_"))
        )
        pocket = cut(profile, 3.0)
        writer.add(
            {
                "type": "fillet",
                "version": 1,
                "params": {
                    "edges": {
                        "kind": "edges",
                        "refs": [
                            _vertical_edge_ref(
                                pocket, cx - 4.5, cy - 4.0, TRAY_T - 3.0, TRAY_T
                            )
                        ],
                    },
                    "radius_mm": 2.0,
                },
            }
        )
    elif kind in (1, 6):  # a through hole and a blind hole
        writer.add(
            {
                "type": "hole",
                "version": 1,
                "params": {
                    "face": top_face(),
                    "position": {"x": cx - 3.0, "y": cy, "z": TRAY_T},
                    "diameter_mm": 4.0,
                    "depth": {"kind": "through_all"},
                },
            }
        )
        writer.add(
            {
                "type": "hole",
                "version": 1,
                "params": {
                    "face": top_face(),
                    "position": {"x": cx + 3.0, "y": cy, "z": TRAY_T},
                    "diameter_mm": 3.0,
                    "depth": {"kind": "blind", "depth_mm": 4.0},
                },
            }
        )
    elif kind == 2:  # cylindrical boss
        profile = writer.add(
            _sketch(
                top_plane,
                [
                    {
                        "id": f"b{site}",
                        "kind": "circle",
                        "center": {"x": cx, "y": cy},
                        "radius": 3.5,
                    }
                ],
            )
        )
        writer.add(
            {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": profile},
                    "distance_mm": 6.0,
                    "operation": "add",
                    "direction": "normal",
                },
            }
        )
    elif kind == 3:  # shallow slot
        profile = writer.add(
            _sketch(top_plane, _rect_entities(cx, cy, 7.0, 4.0, f"q{site}_"))
        )
        cut(profile, 2.0)
    elif kind == 4:  # revolved turret on its own XZ-parallel datum
        datum = writer.add(
            {
                "type": "datum",
                "version": 1,
                "params": {"kind": "offset", "base": "XZ", "offset_mm": -cy},
            }
        )
        profile = writer.add(
            _sketch(
                {"kind": "feature", "feature_id": datum},
                [
                    *_rect_entities(cx + 2.0, TRAY_T + 3.0, 4.0, 6.0, f"r{site}_"),
                    {
                        "id": f"ax{site}",
                        "kind": "line",
                        "construction": True,
                        "start": {"x": cx, "y": TRAY_T},
                        "end": {"x": cx, "y": TRAY_T + 6.0},
                    },
                ],
            )
        )
        writer.add(
            {
                "type": "revolve",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": profile},
                    "axis": {"kind": "sketch_line", "entity": f"ax{site}"},
                    "angle_deg": 360.0,
                    "operation": "add",
                },
            }
        )
    elif kind == 5:  # vent: one slot cut, arrayed by a linear pattern (cut mode)
        profile = writer.add(
            _sketch(top_plane, _rect_entities(cx, cy - 8.0, 5.0, 2.0, f"v{site}_"))
        )
        cut(profile, 3.0)
        writer.add(
            {
                "type": "pattern",
                "version": 1,
                "params": {
                    "pattern": {
                        "kind": "linear",
                        "direction": {"x": 0.0, "y": 1.0, "z": 0.0},
                        "spacing_mm": 8.0,
                        "count": 3,
                    }
                },
            }
        )
    else:  # kind == 7: a pocket mirrored about a local datum (features scope)
        datum = writer.add(
            {
                "type": "datum",
                "version": 1,
                "params": {"kind": "offset", "base": "YZ", "offset_mm": cx},
            }
        )
        profile = writer.add(
            _sketch(top_plane, _rect_entities(cx - 3.0, cy, 4.0, 4.0, f"m{site}_"))
        )
        pocket = cut(profile, 3.0)
        writer.add(
            {
                "type": "mirror",
                "version": 1,
                "params": {
                    "plane": {"kind": "feature", "feature_id": datum},
                    "scope": {
                        "kind": "features",
                        "features": [{"kind": "feature", "feature_id": pocket}],
                    },
                },
            }
        )


def housing_tree(n: int) -> dict[str, Any]:
    """An ``EvaluateTreeRequest`` payload for the first *n* features of the tray.

    ``n`` must be at least :data:`HOUSING_BASE_FEATURES`; the sequence is
    canonical, so ``housing_tree(a)["features"]`` is a strict prefix of
    ``housing_tree(b)["features"]`` for ``a <= b``. Truncation can land mid-motif
    (e.g. a sketch whose extrude is the next feature); that is a legitimate
    authored state — an unconsumed sketch is ``ok`` and contributes no body — and
    it is what keeps the sweep points comparable.
    """
    if n < HOUSING_BASE_FEATURES:
        raise ValueError(f"housing_tree needs n >= {HOUSING_BASE_FEATURES}, got {n}")
    writer = _TreeWriter()
    body, top_plane = _housing_base(writer)
    site = 0
    while len(writer) < n:
        _emit_motif(writer, site, body, top_plane)
        site += 1
    return {
        "part_id": _uid(0xF00),
        "tree_version": 1,
        "features": writer.features[:n],
        "linear_deflection": 0.1,
    }


# --- Finned heat sink: the face-count axis -------------------------------------

FIN_PITCH = 4.0
FIN_SPAN = 60.0
FIN_BASE_T = 6.0
FIN_T = 1.6
FIN_H = 22.0
#: Features in a heat-sink tree with a pattern (sketch, extrude, datum, sketch,
#: extrude, pattern). Fixed regardless of fin count — that is the point.
HEAT_SINK_FEATURES = 6


def heat_sink_tree(fins: int) -> dict[str, Any]:
    """An ``EvaluateTreeRequest`` payload for a *fins*-fin heat sink.

    Six features whatever *fins* is: a one-pitch base tile, a fin on top of it,
    and an ADD linear pattern that replicates the whole body along +X. Adjacent
    base tiles abut and fuse into one slab, so the result is a single connected
    solid of ``fins`` ridges — 4 faces per fin plus 6 on the slab (measured), so
    face count is a clean linear function of one parameter while the tree length
    is constant. ``fins = 1`` omits the pattern (five features, the seed tile).
    """
    ids = [_uid(i) for i in range(1, HEAT_SINK_FEATURES + 1)]
    features: list[dict[str, Any]] = [
        {
            "id": ids[0],
            "feature": _sketch(
                _XY,
                _rect_entities(
                    FIN_PITCH / 2, FIN_SPAN / 2, FIN_PITCH, FIN_SPAN, "base"
                ),
            ),
        },
        {
            "id": ids[1],
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": ids[0]},
                    "distance_mm": FIN_BASE_T,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
        {
            "id": ids[2],
            "feature": {
                "type": "datum",
                "version": 1,
                "params": {
                    "kind": "offset",
                    "base": "XY",
                    "offset_mm": FIN_BASE_T,
                    "flip": False,
                },
            },
        },
        {
            "id": ids[3],
            "feature": _sketch(
                {"kind": "feature", "feature_id": ids[2]},
                _rect_entities(FIN_PITCH / 2, FIN_SPAN / 2, FIN_T, FIN_SPAN, "fin"),
            ),
        },
        {
            "id": ids[4],
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": ids[3]},
                    "distance_mm": FIN_H,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ]
    if fins > 1:
        features.append(
            {
                "id": ids[5],
                "feature": {
                    "type": "pattern",
                    "version": 1,
                    "params": {
                        "pattern": {
                            "kind": "linear",
                            "direction": {"x": 1.0, "y": 0.0, "z": 0.0},
                            "spacing_mm": FIN_PITCH,
                            "count": fins,
                        }
                    },
                },
            }
        )
    return {
        "part_id": _uid(0xF11),
        "tree_version": 1,
        "features": features,
        "linear_deflection": 0.1,
    }
