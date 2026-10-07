"""Motorcycle cradle tube frame through the PUBLIC scripting API (loft-script).

A reference part (``docs/VISION.md``), the standing tube-frame test case. It is
the golden ``services/geometry/goldens/frame-moto-cradle-tube-od25.4-t1.6``
built through the gateway, the same routes the browser calls, so a run can
separate "the kernel cannot" from "the UI cannot reach it".

Part (mm, X forward, Z up, symmetric about the XZ plane): tube OD 25.4 x 1.6
wall (an annulus swept along each path); two side rails along a closed loop
through (0,520) (-520,560) (-760,600) (-560,300) (-80,120), every corner
filleted R80 (tangent-continuous), at y = +110 and mirrored to y = -110; four
Y cross tubes; a 50/32 x 160 steering-head tube raked 25 deg back; one body.

What Loft cannot do directly, and what this script does instead (each is a
finding, see the BACKLOG notes of 2026-10-07):

* a sweep along a CLOSED path is refused (``sweep_path_closed``), so each rail
  is two open sweeps, split where the path tangent is parallel to a datum
  normal, because a sweep is anchored at its profile and the profile sits on an
  axis-aligned datum;
* there is no tilted datum plane, so the head is a REVOLVE of its radial
  section about a tilted sketch axis;
* there is no symmetric (midplane) extrude, so the cross tubes extrude from a
  datum at y = +104 by 208;
* a merging extrude cannot bridge the two lumps a mirror leaves
  (``boolean_failed``), so each cross tube and the head are their own body
  (``merge=False``) joined by a ``boolean`` union.

The cross tubes stop 6 mm short of the rail centrelines: ending ON the
centreline makes OCCT's fuse of equal-diameter crossing tubes unreliable.

Run against a live gateway::

    uv run python docs/reference-parts/moto-frame.py --url http://127.0.0.1:8000

It prints the app's volume and the golden's; they must agree to the golden's
tolerance (0.05).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from pathlib import Path

import loft
from loft.part import Part
from loft.sketch import Sketch
from loft_wire.features import (
    BooleanFeature,
    BooleanParamsV1,
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    FeatureRef,
    MirrorFeature,
    MirrorParamsV1,
    RevolveFeature,
    RevolveParamsV1,
    SketchLineAxis,
)

GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "services/geometry/goldens/frame-moto-cradle-tube-od25.4-t1.6/expected.json"
)

TUBE_OD, TUBE_ID = 25.4, 22.2
BEND_R = 80.0
RAIL_Y = 110.0  # rail centreline offset
TUBE_Y = 104.0  # cross tubes end here, 6 mm inside the rail centreline
CORNERS = [
    (0.0, 520.0),
    (-520.0, 560.0),
    (-760.0, 600.0),
    (-560.0, 300.0),
    (-80.0, 120.0),
]
HEAD_OD, HEAD_ID, HEAD_LEN, HEAD_RAKE_DEG = 50.0, 32.0, 160.0, 25.0

Pt = tuple[float, float]


def _sub(a: Pt, b: Pt) -> Pt:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Pt, b: Pt) -> Pt:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Pt, k: float) -> Pt:
    return (a[0] * k, a[1] * k)


def _unit(a: Pt) -> Pt:
    n = math.hypot(*a)
    return (a[0] / n, a[1] / n)


class Fillet:
    """The R80 round at one corner: tangent points, centre, turn direction."""

    def __init__(self, prev: Pt, corner: Pt, nxt: Pt) -> None:
        d_in, d_out = _unit(_sub(corner, prev)), _unit(_sub(nxt, corner))
        cross = d_in[0] * d_out[1] - d_in[1] * d_out[0]
        self.left = cross > 0
        turn = math.acos(max(-1.0, min(1.0, d_in[0] * d_out[0] + d_in[1] * d_out[1])))
        t = BEND_R * math.tan(turn / 2)
        self.tin = _sub(corner, _mul(d_in, t))
        self.tout = _add(corner, _mul(d_out, t))
        side = 1.0 if self.left else -1.0
        self.centre = _add(self.tin, _mul((-d_in[1], d_in[0]), BEND_R * side))
        self.corner = corner

    def at_heading(self, deg: float) -> Pt:
        """The arc point where the travel direction points at ``deg``."""
        a = math.radians(deg + (-90.0 if self.left else 90.0))
        return (
            self.centre[0] + BEND_R * math.cos(a),
            self.centre[1] + BEND_R * math.sin(a),
        )

    def apex(self) -> Pt:
        """The arc point nearest the (un-filleted) corner."""
        v = _sub(self.corner, self.centre)
        return _add(self.centre, _mul(v, BEND_R / math.hypot(*v)))


def draw_arc(sk: Sketch, f: Fillet, start: Pt, end: Pt) -> None:
    """An arc from ``start`` to ``end`` in travel order (sketch arcs run CCW)."""
    if f.left:
        sk.arc(f.centre, start, end)
    else:
        sk.arc(f.centre, end, start)


def annulus(sk: Sketch, centre: Pt) -> None:
    sk.circle(centre, diameter=TUBE_OD, dimension=False)
    sk.circle(centre, diameter=TUBE_ID, dimension=False)


def ref(feature_id: uuid.UUID) -> FeatureRef:
    return FeatureRef(kind="feature", feature_id=feature_id)


def datum(part: Part, name: str, base: str, offset: float) -> uuid.UUID:
    created = part.create_feature(
        name,
        DatumFeature(
            type="datum",
            version=1,
            params=DatumOffsetParams(base=base, offset_mm=offset),  # type: ignore[arg-type]
        ),
    )
    return created.feature.id


def union(part: Part, name: str, target: uuid.UUID, tool: uuid.UUID) -> None:
    part.create_feature(
        name,
        BooleanFeature(
            type="boolean",
            version=1,
            params=BooleanParamsV1(
                operation="union", target=ref(target), tool=ref(tool)
            ),
        ),
    )


def build(part: Part) -> None:
    n = len(CORNERS)
    fil = [Fillet(CORNERS[i - 1], CORNERS[i], CORNERS[(i + 1) % n]) for i in range(n)]
    a, b, c, d, e = fil  # the corners, front to back to front
    s1 = a.at_heading(90.0)  # front: travel straight up; profile on a horizontal datum
    s2 = c.at_heading(180.0)  # rear: travel straight forward; profile on a YZ datum

    # Datum planes. The XZ datum's normal is -Y, so y = +110 is offset -110.
    rail = datum(part, "Rail plane y=+110", "XZ", -RAIL_Y)
    d_s1 = datum(part, "Rail profile plane (front split)", "XY", s1[1])
    d_s2 = datum(part, "Rail profile plane (rear split)", "YZ", s2[0])
    tube = datum(part, "Cross tube plane y=+104", "XZ", -TUBE_Y)

    # Rail, upper half: front split -> backbone -> seat rail -> rear split.
    path = part.sketch(on=ref(rail), name="Rail path, upper half")
    draw_arc(path, a, s1, a.tout)
    path.line(a.tout, b.tin)
    draw_arc(path, b, b.tin, b.tout)
    path.line(b.tout, c.tin)
    draw_arc(path, c, c.tin, s2)
    path.save()
    prof = part.sketch(on=ref(d_s1), name="Tube profile, front split")
    annulus(prof, (s1[0], RAIL_Y))
    prof.save()
    upper = part.sweep(prof, path, name="Rail, upper half")

    # Rail, lower half: rear split -> drop -> lower cradle -> down tube -> front split.
    path = part.sketch(on=ref(rail), name="Rail path, lower half")
    draw_arc(path, c, s2, c.tout)
    path.line(c.tout, d.tin)
    draw_arc(path, d, d.tin, d.tout)
    path.line(d.tout, e.tin)
    draw_arc(path, e, e.tin, e.tout)
    path.line(e.tout, a.tin)
    draw_arc(path, a, a.tin, s1)
    path.save()
    prof = part.sketch(on=ref(d_s2), name="Tube profile, rear split")
    annulus(prof, (RAIL_Y, s2[1]))
    prof.save()
    part.sweep(prof, path, name="Rail, lower half")

    part.create_feature(
        "Mirror rail to y=-110",
        MirrorFeature(
            type="mirror",
            version=1,
            params=MirrorParamsV1(plane=DatumPlaneRef(kind="datum_plane", plane="XZ")),
        ),
    )

    # Cross tubes: three on the rail centreline, the fourth at the front apex,
    # through whose centre the head axis passes.
    apex = a.apex()
    for k, at in enumerate([(-520.0, 560.0), (-560.0, 300.0), (-300.0, 202.5), apex]):
        sk = part.sketch(on=ref(tube), name=f"Cross tube {k + 1} profile")
        annulus(sk, at)
        sk.save()
        t = part.extrude(sk, 2 * TUBE_Y, merge=False, name=f"Cross tube {k + 1}")
        union(part, f"Join cross tube {k + 1}", upper.id, t.id)

    # Steering head: a revolve of its radial section about the raked axis.
    rake = math.radians(HEAD_RAKE_DEG)
    axis_dir = (-math.sin(rake), math.cos(rake))
    normal = (math.cos(rake), math.sin(rake))

    def on_axis(s: float, r: float) -> Pt:
        return (
            apex[0] + s * axis_dir[0] + r * normal[0],
            apex[1] + s * axis_dir[1] + r * normal[1],
        )

    h = HEAD_LEN / 2
    ro, ri = HEAD_OD / 2, HEAD_ID / 2
    corners = [on_axis(-h, ri), on_axis(-h, ro), on_axis(h, ro), on_axis(h, ri)]
    head = part.sketch(on="XZ", name="Steering head section")
    for i in range(4):
        head.line(corners[i], corners[(i + 1) % 4])
    axis = head.line(on_axis(-h - 10, 0), on_axis(h + 10, 0), construction=True)
    head.save()
    rev = part.create_feature(
        "Steering head (revolve, raked 25 deg)",
        RevolveFeature(
            type="revolve",
            version=1,
            params=RevolveParamsV1(
                profile=head.ref(),
                axis=SketchLineAxis(kind="sketch_line", entity=axis),
                angle_deg=360.0,
                operation="add",
                merge=False,
            ),
        ),
    )
    union(part, "Join steering head", upper.id, rev.feature.id)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    email = f"moto-frame-{uuid.uuid4().hex[:8]}@example.com"
    with loft.register(args.url, email=email, password="moto-frame-pw-123") as session:
        part = session.new_part("Moto cradle frame")
        try:
            build(part)
            evaluation = part.evaluate(strict=True)
        except loft.LoftError as exc:
            print(f"FAILED: {exc.as_dict()}")
            return 1
        props = evaluation.properties
        assert props is not None
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        want, tol = golden["properties"]["volume"], golden["tolerance"]
        topo = props.topology
        print(f"volume {props.volume:.4f} mm^3 (golden {want:.4f}, tol {tol})")
        print(
            f"area {props.surface_area:.3f}  centroid ({props.centroid.x:.3f}, "
            f"{props.centroid.y:.3f}, {props.centroid.z:.3f})  "
            f"faces {topo.faces} edges {topo.edges} shells {topo.shells}"
        )
        print(f"part id: {part.id}  (log in as {email} / moto-frame-pw-123)")
        if abs(props.volume - want) > tol:
            print("MISMATCH against the golden")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
