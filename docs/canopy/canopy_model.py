"""Bracket-supported lean-to door canopy — modelled with Loft's own CAD.

Every solid here is built by the geometry service's feature pipeline: a sketch
on a YZ datum plane, extruded along +X.  Nothing calls the kernel directly, so
the canopy is a real Loft feature tree and its mass properties come from the
same evaluator the product uses.

    uv run python docs/canopy/canopy_model.py --out docs/canopy/build

Coordinate system (inches; the tree is emitted in millimetres):

    X  left / right across the house wall, 0 = canopy centreline
    Y  outward from the wall, 0 = face of the finished wall
    Z  up, 0 = top of the stoop at the threshold

The canopy is a cantilever: it carries no ground supports, so every pound of it
is held by the two wall brackets.  `attachment_check()` sizes that connection,
and it is the part of this design that a site survey can invalidate.
"""

from __future__ import annotations

import argparse
import math
import uuid
from dataclasses import dataclass
from pathlib import Path

from geometry.features.evaluate import evaluate_tree
from geometry.kernel.export import export_step_bytes
from py_kit.schemas.features import EvaluatedFeatureInput, EvaluateTreeRequest

IN = 25.4  # inches -> millimetres

# --------------------------------------------------------------------------
# Design parameters
# --------------------------------------------------------------------------

DOOR_W = 36.0  # door leaf
CASING_W = 3.5  # flat casing each side
HEAD_TOP = 84.0  # top of the door head casing above the stoop

WIDTH = 72.0  # overall canopy width
ARM_RUN = 36.0  # wall face to the plumb-cut arm tail
PITCH = 4.0 / 12.0  # 4:12 -- the reference canopy's 17 degrees, on a US pitch
BRACKET_X = 27.0  # bracket centreline, each side of centre

Z_POST_TOP = 102.0  # top of the wall post == underside of the arm at the wall
POST_H = 36.0  # wall post height (the reference's 0.92 m)

# Member sizes (actual, not nominal)
POST_T = 3.5  # 4x4 wall post
ARM_T, ARM_D = 3.5, 5.5  # 4x6 arm
BRACE_T, BRACE_W = 3.5, 3.5  # curved knee brace, cut from a 4x10 blank
PURLIN_W, PURLIN_T = 5.5, 1.5  # 2x6 laid flat
PURLIN_COUNT = 4
FASCIA_T = 0.75  # 1x8 ripped
PANEL_T = 0.5  # standing-seam metal panel
PANEL_OVERHANG = 2.25  # drip past the arm tail
APRON_UP = 6.0  # apron flashing leg up the wall

BRACE_SAG = 4.5  # how far the brace bows away from the corner
BRACE_FOOT = 2.0  # brace heel above the bottom of the post
BRACE_LAND = 23.5  # where the brace meets the underside of the arm

# --------------------------------------------------------------------------
# Derived geometry
# --------------------------------------------------------------------------

SLOPE = math.hypot(12.0, 12.0 * PITCH) / 12.0  # plumb -> along-slope factor
ROOF_ANGLE = math.degrees(math.atan(PITCH))

Z_POST_BOT = Z_POST_TOP - POST_H
ARM_PLUMB_D = ARM_D * SLOPE
HALF_W = WIDTH / 2.0


def arm_bot(y: float) -> float:
    """Underside of the arm at distance *y* from the wall."""
    return Z_POST_TOP - PITCH * y


def arm_top(y: float) -> float:
    """Top of the arm — the plane the purlins bear on."""
    return arm_bot(y) + ARM_PLUMB_D


FASCIA_Y = ARM_RUN
PANEL_Y = ARM_RUN + PANEL_OVERHANG
DRIP_Z = arm_top(PANEL_Y) + (PURLIN_T + PANEL_T) * SLOPE
RIDGE_Z = arm_top(0.0) + (PURLIN_T + PANEL_T) * SLOPE

# Purlin inner edges, spaced so the outermost finishes flush with the arm tail
PURLIN_Y_SPAN = PURLIN_W * math.cos(math.radians(ROOF_ANGLE))
PURLIN_STEP = (ARM_RUN - PURLIN_Y_SPAN) / (PURLIN_COUNT - 1)
PURLIN_YS = [i * PURLIN_STEP for i in range(PURLIN_COUNT)]


# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------

Pt = tuple[float, float]


@dataclass(frozen=True)
class Seg:
    """One profile segment: a line, or an arc swept about *center*."""

    end: Pt
    center: Pt | None = None


@dataclass(frozen=True)
class Member:
    """One timber (or panel): a YZ cross-section extruded *thickness* along +X."""

    name: str
    kind: str
    x0: float
    thickness: float
    start: Pt
    segs: tuple[Seg, ...]
    material: str
    stock: str
    cut_note: str = ""

    def points(self) -> list[Pt]:
        return [self.start, *(s.end for s in self.segs)]


def _rect(y0: float, z0: float, y1: float, z1: float) -> tuple[Pt, tuple[Seg, ...]]:
    return (y0, z0), (Seg((y1, z0)), Seg((y1, z1)), Seg((y0, z1)), Seg((y0, z0)))


def _offset_along_slope(y: float, z: float, perp: float) -> Pt:
    """Move a point *perp* inches perpendicular to the roof plane (upward)."""
    nz = 1.0 / SLOPE
    ny = PITCH / SLOPE
    return (y - perp * ny, z + perp * nz)


def _slab(
    y0: float, y1: float, below: float, above: float
) -> tuple[Pt, tuple[Seg, ...]]:
    """A slab parallel to the roof plane, between two perpendicular offsets.

    ``below``/``above`` are perpendicular distances from the top of the arms, so
    a purlin is ``(0, PURLIN_T)`` and the panel sits on top of it.  The ends are
    cut PLUMB (vertical), which is how a purlin and a metal panel are actually
    trimmed at the wall and at the drip edge.
    """
    p0 = _offset_along_slope(y0, arm_top(y0), below)
    p1 = _offset_along_slope(y1, arm_top(y1), below)
    q1 = _offset_along_slope(y1, arm_top(y1), above)
    q0 = _offset_along_slope(y0, arm_top(y0), above)
    # Re-cut the ends plumb at y0 / y1 rather than leaving them skewed.
    p0, q0 = (y0, p0[1] + (y0 - p0[0]) * -PITCH), (y0, q0[1] + (y0 - q0[0]) * -PITCH)
    p1, q1 = (y1, p1[1] + (y1 - p1[0]) * -PITCH), (y1, q1[1] + (y1 - q1[0]) * -PITCH)
    return p0, (Seg(p1), Seg(q1), Seg(q0), Seg(p0))


def _brace_profile() -> tuple[Pt, tuple[Seg, ...]]:
    """The curved knee brace: two concentric arcs, cut to the post and the arm.

    The centreline bows AWAY from the inside corner by ``BRACE_SAG`` — the shape
    in the reference photograph — and the member keeps a constant ``BRACE_W``.
    Both end cuts follow the member the brace lands on, so the joint has a real
    shoulder rather than a knife edge.
    """
    heel = (POST_T, Z_POST_BOT + BRACE_FOOT)
    land = (BRACE_LAND, arm_bot(BRACE_LAND))

    chord = math.dist(heel, land)
    mid = ((heel[0] + land[0]) / 2.0, (heel[1] + land[1]) / 2.0)
    d = ((land[0] - heel[0]) / chord, (land[1] - heel[1]) / chord)
    n = (d[1], -d[0])
    corner = (POST_T, arm_bot(BRACE_LAND))
    if (corner[0] - mid[0]) * n[0] + (corner[1] - mid[1]) * n[1] > 0:
        n = (-n[0], -n[1])  # n must point AWAY from the inside corner

    r_out = chord**2 / (8.0 * BRACE_SAG) + BRACE_SAG / 2.0
    center = (mid[0] - (r_out - BRACE_SAG) * n[0], mid[1] - (r_out - BRACE_SAG) * n[1])
    r_in = r_out - BRACE_W

    def on_arc(radius: float, y: float, upper: bool) -> Pt:
        """Where the arc of *radius* crosses the vertical line at *y*."""
        dz = math.sqrt(max(radius**2 - (y - center[0]) ** 2, 0.0))
        return (y, center[1] + (dz if upper else -dz))

    def arc_meets_arm(radius: float) -> Pt:
        """Where the arc of *radius* crosses the underside of the arm."""
        # (y - cy0)^2 + (arm_bot(y) - cz)^2 = r^2, expanded into a quadratic.
        a = 1.0 + PITCH**2
        k = Z_POST_TOP - center[1]
        b = -2.0 * center[0] - 2.0 * PITCH * k
        c = center[0] ** 2 + k**2 - radius**2
        disc = math.sqrt(max(b * b - 4 * a * c, 0.0))
        y = max((-b + disc) / (2 * a), (-b - disc) / (2 * a))
        return (y, arm_bot(y))

    outer_heel = on_arc(r_out, POST_T, upper=False)
    inner_heel = on_arc(r_in, POST_T, upper=False)
    outer_land = arc_meets_arm(r_out)
    inner_land = arc_meets_arm(r_in)

    return outer_heel, (
        Seg(outer_land, center),  # outer arc, heel -> arm
        Seg(inner_land),  # shoulder cut along the underside of the arm
        Seg(inner_heel, center),  # inner arc, arm -> heel
        Seg(outer_heel),  # heel cut on the face of the post
    )


_MEMBER_OVERRIDE: list[Member] = []


def members() -> list[Member]:
    """Every component of the canopy, in build order."""
    if _MEMBER_OVERRIDE:
        return list(_MEMBER_OVERRIDE)
    out: list[Member] = []

    for side in (-1, 1):
        cx = side * BRACKET_X
        tag = "L" if side < 0 else "R"

        start, segs = _rect(0.0, Z_POST_BOT, POST_T, Z_POST_TOP)
        out.append(
            Member(
                f"wall post {tag}",
                "post",
                cx - POST_T / 2,
                POST_T,
                start,
                segs,
                "PT or cedar 4x4",
                "4x4 x 3'-0\"",
                "lag or through-bolt to a stud - see attachment_check()",
            )
        )

        start, segs = _rect(0.0, arm_bot(0.0), 0.0, 0.0)  # replaced below
        arm_pts = (
            (0.0, arm_bot(0.0)),
            (ARM_RUN, arm_bot(ARM_RUN)),
            (ARM_RUN, arm_top(ARM_RUN)),
            (0.0, arm_top(0.0)),
        )
        out.append(
            Member(
                f"arm {tag}",
                "arm",
                cx - ARM_T / 2,
                ARM_T,
                arm_pts[0],
                tuple(Seg(p) for p in (*arm_pts[1:], arm_pts[0])),
                "PT or cedar 4x6",
                "4x6 x 3'-2\"",
                f"plumb cuts both ends; sits on the post top, {ROOF_ANGLE:.1f} deg",
            )
        )

        bstart, bsegs = _brace_profile()
        out.append(
            Member(
                f"curved brace {tag}",
                "brace",
                cx - BRACE_T / 2,
                BRACE_T,
                bstart,
                bsegs,
                "PT or cedar",
                "4x10 x 3'-0\" blank",
                "band-saw the two arcs; or laminate two 2x10",
            )
        )

    for i, y in enumerate(PURLIN_YS):
        start, segs = _slab(y, y + PURLIN_Y_SPAN, 0.0, PURLIN_T)
        out.append(
            Member(
                f"purlin {i + 1}",
                "purlin",
                -HALF_W,
                WIDTH,
                start,
                segs,
                "PT or cedar 2x6",
                "2x6 x 6'-0\"",
                "laid flat on the arms; purlin 1 also lands the apron flashing",
            )
        )

    start, segs = _rect(
        FASCIA_Y, arm_bot(ARM_RUN) - 1.0, FASCIA_Y + FASCIA_T, arm_top(ARM_RUN)
    )
    out.append(
        Member(
            "fascia",
            "fascia",
            -HALF_W,
            WIDTH,
            start,
            segs,
            "cedar or PVC 1x8",
            "1x8 x 6'-0\"",
            "ripped; drops 1 in below the arm to throw the drip",
        )
    )

    start, segs = _slab(0.0, PANEL_Y, PURLIN_T, PURLIN_T + PANEL_T)
    out.append(
        Member(
            "roof panel",
            "roof",
            -HALF_W,
            WIDTH,
            start,
            segs,
            "24 ga standing seam",
            "6'-0\" x 3'-4\" panel",
            "one panel run; ribs perpendicular to the purlins",
        )
    )

    apron_bot = _offset_along_slope(0.0, arm_top(0.0), PURLIN_T + PANEL_T)
    apron = (
        (0.0, apron_bot[1]),
        (PURLIN_Y_SPAN, apron_bot[1] - PURLIN_Y_SPAN * PITCH),
        (PURLIN_Y_SPAN, apron_bot[1] - PURLIN_Y_SPAN * PITCH + 0.05),
        (0.0, apron_bot[1] + 0.05),
        (0.0, apron_bot[1] + APRON_UP),
        (-0.05, apron_bot[1] + APRON_UP),
        (-0.05, apron_bot[1]),
    )
    out.append(
        Member(
            "apron flashing",
            "flashing",
            -HALF_W,
            WIDTH,
            apron[0],
            tuple(Seg(p) for p in (*apron[1:], apron[0])),
            "0.032 aluminium",
            '6\'-0" x 8" apron',
            "up the wall behind the WRB, out over the panel - see the design doc",
        )
    )
    return out


# --------------------------------------------------------------------------
# Analysis — all of it derived from the evaluated solids
# --------------------------------------------------------------------------

#: Assumed loads. Local code governs; these are the values every number below
#: is derived from, so substituting yours re-derives the whole check.
SNOW_PSF = 30.0
UPLIFT_PSF = 30.0  # net uplift on an open canopy (ASCE 7 components & cladding)
DENSITY_PCF = {"timber": 31.0, "metal": 0.0, "flashing": 0.0}  # lb per cubic foot
PANEL_PSF = 1.5  # 24 ga standing seam, fixings included


def member_volumes() -> dict[str, float]:
    """Cubic inches per member, measured by the kernel one body at a time."""
    volumes: dict[str, float] = {}
    for member in members():
        features, _ = _single_member_tree(member)
        request = EvaluateTreeRequest(
            part_id=uuid.uuid4(), tree_version=1, features=features
        )
        props = evaluate_tree(request).result.properties
        volumes[member.name] = props.volume / IN**3
    return volumes


def _single_member_tree(member: Member) -> tuple[list[EvaluatedFeatureInput], None]:
    saved = _MEMBER_OVERRIDE.copy()
    try:
        _MEMBER_OVERRIDE.clear()
        _MEMBER_OVERRIDE.append(member)
        features, _ = feature_tree()
        return features, None
    finally:
        _MEMBER_OVERRIDE.clear()
        _MEMBER_OVERRIDE.extend(saved)


def roof_area_sf() -> float:
    return WIDTH * PANEL_Y / 144.0


def bill_of_materials() -> str:
    volumes = member_volumes()
    rows = [("Component", "Qty", "Stock", "Material", "cu in", "Notes")]
    seen: dict[str, tuple[Member, int, float]] = {}
    for member in members():
        key = member.kind + member.stock
        if key in seen:
            m, n, v = seen[key]
            seen[key] = (m, n + 1, v + volumes[member.name])
        else:
            seen[key] = (member, 1, volumes[member.name])
    total = 0.0
    for member, qty, vol in seen.values():
        total += vol
        head, _, tail = member.name.rpartition(" ")
        label = head if tail in ("L", "R") or tail.isdigit() else member.name
        rows.append(
            (
                label,
                str(qty),
                member.stock,
                member.material,
                f"{vol:.0f}",
                member.cut_note,
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(6)]
    out = []
    for n, row in enumerate(rows):
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())
        if n == 0:
            out.append("  ".join("-" * w for w in widths))
    timber = sum(
        v for name, v in volumes.items() if not name.startswith(("roof", "apron"))
    )
    out.append("")
    out.append(f"timber volume  {timber:.0f} cu in  ({timber / 144.0:.1f} board feet)")
    out.append(f"timber weight  {timber / 1728.0 * DENSITY_PCF['timber']:.0f} lb")
    out.append(f"roof area      {roof_area_sf():.1f} sq ft")
    return "\n".join(out)


def dead_load_lb() -> float:
    volumes = member_volumes()
    timber = sum(
        v for name, v in volumes.items() if not name.startswith(("roof", "apron"))
    )
    return timber / 1728.0 * DENSITY_PCF["timber"] + roof_area_sf() * PANEL_PSF


def attachment_check() -> str:
    """Size the wall connection — the whole design rests on it.

    With no ground supports the brackets are a pure cantilever, so the fixings
    carry a couple: the roof's weight tries to rotate the post AWAY from the
    wall at the top, and wind uplift reverses it and pulls the BOTTOM out. Both
    directions have to be fastened.
    """
    area = roof_area_sf()
    dead = dead_load_lb()
    gravity = dead + SNOW_PSF * area
    per_bracket = gravity / 2.0
    arm = PANEL_Y / 2.0  # load centroid, out from the wall
    moment = per_bracket * arm
    couple = moment / POST_H

    uplift_total = UPLIFT_PSF * area - dead
    uplift_bracket = max(uplift_total, 0.0) / 2.0
    uplift_couple = uplift_bracket * arm / POST_H

    return "\n".join(
        [
            f"Roof area                         {area:6.1f} sq ft",
            f"Dead load (measured timber+panel) {dead:6.0f} lb",
            f"Gravity case, dead + {SNOW_PSF:.0f} psf snow  {gravity:6.0f} lb"
            f"   ({per_bracket:.0f} lb per bracket)",
            f"Load centroid, out from the wall  {arm:6.1f} in",
            "",
            "PER BRACKET, gravity case:",
            f"  vertical shear on the fixings   {per_bracket:6.0f} lb",
            f"  couple over the {POST_H:.0f} in post      "
            f"{couple:6.0f} lb  (top pulls OUT, bottom bears IN)",
            "",
            f"PER BRACKET, {UPLIFT_PSF:.0f} psf uplift case:",
            f"  net uplift                      {uplift_bracket:6.0f} lb",
            f"  couple reverses to              {uplift_couple:6.0f} lb"
            "  (BOTTOM pulls out)",
            "",
            "Specify per post: 4 no. 1/2 in through-bolts into solid blocking, or",
            "4 no. 3/8 x 6 in structural screws into a stud - two near the top and",
            "two near the bottom, staggered. Both pairs are load-bearing; a post",
            "fixed only at the top is a hinge.",
        ]
    )


def shelter_analysis() -> str:
    """How far off vertical rain can blow before it reaches the door."""
    half_case = DOOR_W / 2.0 + CASING_W

    def ang(run: float, rise: float) -> float:
        return math.degrees(math.atan2(run, rise))

    head_on_head = ang(PANEL_Y, DRIP_Z - HEAD_TOP)
    head_on_sill = ang(PANEL_Y, DRIP_Z)
    side_at_wall = ang(HALF_W - half_case, RIDGE_Z - HEAD_TOP)
    side_at_drip = ang(HALF_W - half_case, DRIP_Z - HEAD_TOP)

    return "\n".join(
        [
            f"Drip line stands off the door face by   {PANEL_Y:5.1f} in "
            f"({PANEL_Y / 12:.1f} ft)",
            f"Roof covers each side of the casing by  {HALF_W - half_case:5.1f} in",
            f"Underside of the arm at the tail        {arm_bot(ARM_RUN):5.1f} in"
            f"   ({arm_bot(ARM_RUN) - HEAD_TOP:.0f} in above the head casing)",
            "",
            "Wind-driven rain must exceed these angles off vertical to land on:",
            f"  the head of the door, from ahead      {head_on_head:5.0f} deg",
            f"  the threshold, from ahead             {head_on_sill:5.0f} deg",
            f"  the head of the door, from the side   {side_at_drip:5.0f} deg"
            f" (outer end) / {side_at_wall:.0f} deg (at the wall)",
            "",
            "A 3 ft projection keeps straight-down rain and roof runoff off the",
            "door, the threshold and anyone standing at it. It does NOT shelter",
            "the stoop the way a 5 ft deep portico would: rain steeper than",
            f"{head_on_sill:.0f} deg off vertical still reaches the threshold. That is"
            " the",
            "cost of carrying the whole roof on the wall, and it is the reason the",
            "projection stops at 3 ft rather than going further.",
        ]
    )


# --------------------------------------------------------------------------
# Feature tree
# --------------------------------------------------------------------------


def _sketch_params(member: Member, datum_id: uuid.UUID | None) -> dict[str, object]:
    plane: dict[str, object] = (
        {"kind": "datum_plane", "plane": "YZ"}
        if datum_id is None
        else {"kind": "feature", "feature_id": str(datum_id)}
    )
    pts = member.points()
    entities: list[dict[str, object]] = []
    for i, seg in enumerate(member.segs):
        a, b = pts[i], pts[i + 1]
        if seg.center is None:
            entities.append(
                {
                    "id": f"e{i}",
                    "kind": "line",
                    "start": {"x": a[0] * IN, "y": a[1] * IN},
                    "end": {"x": b[0] * IN, "y": b[1] * IN},
                }
            )
            continue
        cy, cz = seg.center
        # Edge.make_circle sweeps CCW from start to end; order the endpoints so
        # the swept arc is the minor one rather than the long way round.
        ang_a = math.degrees(math.atan2(a[1] - cz, a[0] - cy))
        ang_b = math.degrees(math.atan2(b[1] - cz, b[0] - cy))
        start, end = (a, b) if (ang_b - ang_a) % 360.0 <= 180.0 else (b, a)
        entities.append(
            {
                "id": f"e{i}",
                "kind": "arc",
                "center": {"x": cy * IN, "y": cz * IN},
                "start": {"x": start[0] * IN, "y": start[1] * IN},
                "end": {"x": end[0] * IN, "y": end[1] * IN},
            }
        )
    return {"plane": plane, "entities": entities, "constraints": []}


def feature_tree() -> tuple[
    list[EvaluatedFeatureInput], list[tuple[Member, uuid.UUID]]
]:
    """The Loft feature tree: datum -> sketch -> extrude, once per member."""
    features: list[EvaluatedFeatureInput] = []
    bodies: list[tuple[Member, uuid.UUID]] = []
    for member in members():
        datum_id: uuid.UUID | None = None
        if abs(member.x0) > 1e-9:
            datum_id = uuid.uuid4()
            features.append(
                EvaluatedFeatureInput.model_validate(
                    {
                        "id": datum_id,
                        "feature": {
                            "type": "datum",
                            "version": 1,
                            "params": {
                                "kind": "offset",
                                "base": "YZ",
                                "offset_mm": member.x0 * IN,
                            },
                        },
                    }
                )
            )
        sketch_id, extrude_id = uuid.uuid4(), uuid.uuid4()
        features.append(
            EvaluatedFeatureInput.model_validate(
                {
                    "id": sketch_id,
                    "feature": {
                        "type": "sketch",
                        "version": 1,
                        "params": _sketch_params(member, datum_id),
                    },
                }
            )
        )
        features.append(
            EvaluatedFeatureInput.model_validate(
                {
                    "id": extrude_id,
                    "feature": {
                        "type": "extrude",
                        "version": 1,
                        "params": {
                            "profile": {
                                "kind": "feature",
                                "feature_id": str(sketch_id),
                            },
                            "distance_mm": member.thickness * IN,
                            "operation": "add",
                            "direction": "normal",
                            "merge": False,
                        },
                    },
                }
            )
        )
        bodies.append((member, extrude_id))
    return features, bodies


def evaluate() -> tuple[object, list[tuple[Member, uuid.UUID]]]:
    features, bodies = feature_tree()
    request = EvaluateTreeRequest(
        part_id=uuid.UUID("c0000000-0000-0000-0000-00000000cafe"),
        tree_version=1,
        features=features,
    )
    return evaluate_tree(request), bodies


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("docs/canopy/build"))
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args()

    evaluation, bodies = evaluate()
    result = evaluation.result  # type: ignore[attr-defined]
    if result.features_failed if hasattr(result, "features_failed") else False:
        raise SystemExit("evaluation reported failures")
    props = result.properties
    bb = props.bounding_box
    print("=== GEOMETRY ===")
    print(f"bodies: {len(result.bodies)} of {len(bodies)} members")
    print(f"volume: {props.volume / IN**3:.1f} cu in")
    print(
        "bbox in:"
        f"  X {bb.min.x / IN:7.2f}..{bb.max.x / IN:7.2f}"
        f"  Y {bb.min.y / IN:7.2f}..{bb.max.y / IN:7.2f}"
        f"  Z {bb.min.z / IN:7.2f}..{bb.max.z / IN:7.2f}"
    )

    print()
    print("=== WEATHER PROTECTION ===")
    print(shelter_analysis())
    print()
    print("=== WALL ATTACHMENT ===")
    print(attachment_check())
    print()
    print("=== BILL OF MATERIALS ===")
    print(bill_of_materials())

    if not args.no_export:
        args.out.mkdir(parents=True, exist_ok=True)
        step = export_step_bytes(evaluation.body, name="door_canopy")  # type: ignore[attr-defined]
        (args.out / "canopy.step").write_bytes(step)
        print(f"exported -> {args.out}/canopy.step ({len(step) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
