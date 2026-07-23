"""THROWAWAY feasibility spike + probes for SECTION VIEWS (drawings-section.md).

NOT production tests — these prove the core kernel operation and the two audit-
flagged v1-scope risks are tractable with our stack (OCP/build123d + the shipped
datum/boolean/HLR infrastructure) BEFORE we commit to building the feature.

Functions are deliberately NOT named ``test_*`` so ``just test`` (pytest) does not
collect them — a throwaway spike must never become a de-facto gate. Run explicitly:

  uv run python services/geometry/tests/spike_section_view.py

Contents:

* ``run_core_spike`` (§9 core, LOW-risk third): cut-on-a-principal-plane +
  coplanar-section-face-area + HLR-of-behind, on the shipped ``project_view`` seam.
* ``probe_multilump_sever`` (audit 🟡9): a real ``boolean_bodies(allow_disjoint=True)``
  cut that SEVERS a part into 2 lumps, proving the lumps are all kept and the
  section faces extract from the CLEANED lumps.
* ``probe_multiloop_hatch_clip`` (audit 🔴2b): the multi-loop scanline hatch clip
  over a face with an interior hole loop, proving even-odd determinism.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import math

from build123d import Compound, Face, Plane, Pos, Solid, Vector
from geometry.drawings.project import project_view
from geometry.kernel import boolean_bodies

# --- analytic model -------------------------------------------------------------
BOX_X, BOX_Y, BOX_Z = 40.0, 20.0, 30.0
HOLE_R = 5.0
# Cut plane = world XZ (normal +Y) through the box centre (Y=0), through the hole
# axis (Z). The FRONT view (outward normal N = (0,-1,0)) looks straight at it — the
# incumbent "full section on a PRINCIPAL plane" case v1 targets (N is a standard
# view direction, so no frame generalization is needed — the load-bearing v1 rule).
CUT_PLANE = Plane.XZ  # origin (0,0,0), z_dir = (0,1,0)


def _box_with_through_hole() -> Solid:
    """A 40x20x30 box centred on the origin with a Ø10 hole bored through +Z."""
    box = Solid.make_box(BOX_X, BOX_Y, BOX_Z).locate(
        Pos(-BOX_X / 2, -BOX_Y / 2, -BOX_Z / 2)
    )
    hole = Solid.make_cylinder(HOLE_R, BOX_Z * 2).locate(Pos(0, 0, -BOX_Z))
    return box.cut(hole).solids()[0]


def _half_space_eye_side(plane: Plane, body: Solid | Compound) -> Solid:
    """The eye-side half-space tool, SIZED AND POSITIONED from the body bbox
    PROJECTED ONTO *plane* (audit 🟡3) — never centred at the plane origin.

    The tool covers the body's full in-plane (u,v) extent and extends along +N
    (the eye side, local +z) to just past the body. An origin-centred tool would
    leave a NOTCH (not a half cut) whenever the plane origin is not the body
    centre (an on_face / offset datum) — silently wrong, uncaught by the miss /
    swallow checks. Positioning from the projected bbox is what prevents that.
    """
    local = plane.to_local_coords(body)
    bb = local.bounding_box()
    pad = (bb.max - bb.min).length + 1.0  # provably exceeds the body in every axis
    # In-plane (u,v): cover the whole projected extent with pad on each side.
    u0, u1 = bb.min.X - pad, bb.max.X + pad
    v0, v1 = bb.min.Y - pad, bb.max.Y + pad
    # Along N (+z local = eye side): from the cut plane (w=0) out past the body.
    w1 = bb.max.Z + pad  # provably past the eye-side extent of the body
    tool_local = Solid.make_box(u1 - u0, v1 - v0, w1).locate(Pos(u0, v0, 0.0))
    return tool_local.moved(plane.location)


def _coplanar_section_faces(remaining: Solid | Compound, plane: Plane) -> list[Face]:
    """Faces of *remaining* lying ON *plane* — the cross-section to hatch.

    A face is a section face iff its normal is parallel to the cut normal AND a
    point on it satisfies the plane equation (within the kernel linear tol).
    """
    n = plane.z_dir
    d = n.dot(plane.origin)
    out: list[Face] = []
    for face in remaining.faces():
        fn = face.normal_at()
        if abs(abs(fn.dot(n)) - 1.0) > 1e-7:
            continue
        c = face.center()
        if abs(n.dot(c) - d) > 1e-6:
            continue
        out.append(face)
    return out


# --- §9 core spike (LOW-risk third: principal-plane cut + face area + HLR) -------
def run_core_spike() -> None:
    body = _box_with_through_hole()
    tool = _half_space_eye_side(CUT_PLANE, body)

    # (i) the cut — half-space subtract → remaining solid behind the plane.
    remaining = body.cut(tool)
    lumps = remaining.solids()
    print(f"[i]   cut produced {len(lumps)} lump(s); volume={remaining.volume:.3f}")
    half_box = BOX_X * (BOX_Y / 2) * BOX_Z
    half_hole = math.pi * HOLE_R**2 * BOX_Z / 2
    expected_vol = half_box - half_hole
    assert abs(remaining.volume - expected_vol) < 1e-3, (remaining.volume, expected_vol)

    # (ii) the section cross-section face(s) — the region to hatch.
    faces = _coplanar_section_faces(remaining, CUT_PLANE)
    area = sum(f.area for f in faces)
    expected_area = BOX_X * BOX_Z - (2 * HOLE_R) * BOX_Z
    print(
        f"[ii]  {len(faces)} section face(s); area={area:.3f} "
        f"(analytic {expected_area:.3f})"
    )
    assert abs(area - expected_area) < 1e-3, (area, expected_area)

    # (iii) HLR-project the remaining (behind) geometry through the shipped seam.
    proj = project_view(remaining, "front", scale=1.0)
    print(
        f"[iii] front-view HLR of remaining: {len(proj.visible_edges)} visible, "
        f"{len(proj.hidden_edges)} hidden"
    )
    assert len(proj.visible_edges) > 0
    print("CORE SPIKE: principal-plane cut + face area + behind-HLR TRACTABLE.\n")


# --- audit 🟡9 probe: multi-lump SEVER through boolean_bodies(allow_disjoint) ----
def _pi_channel() -> Solid:
    """A "П" part: two upright legs joined by a top bar (a U-channel opening down).

    A horizontal cut that removes the top bar SEVERS the remaining material into
    two disconnected leg stubs — the multi-lump case a valid section legitimately
    produces (a U-channel cut through both walls), which ``boolean_bodies`` rejects
    UNLESS ``allow_disjoint=True``.
    """
    leg_l = Solid.make_box(10, 10, 40).locate(Pos(-30, -5, 0))
    leg_r = Solid.make_box(10, 10, 40).locate(Pos(20, -5, 0))
    top = Solid.make_box(60, 10, 10).locate(Pos(-30, -5, 30))
    return leg_l.fuse(leg_r).fuse(top).solids()[0]


def probe_multilump_sever() -> None:
    body = _pi_channel()
    # Cut plane z=25 (below the top bar at z∈[30,40], above the leg bottoms at z=0):
    # its origin is NOT the body centre — so the bbox-POSITIONED tool (not an origin-
    # centred one) is what makes this a clean half cut, exercising audit 🟡3.
    plane = Plane(origin=(0, 0, 25), z_dir=(0, 0, 1))
    tool = _half_space_eye_side(plane, body)

    # Reuse the SHIPPED boolean surface with the disjoint-tolerant posture — the
    # section op does NOT fork build123d.cut; it uses allow_disjoint=True, which
    # clean()s each lump and assemble_lumps-orders them into one Compound (§2).
    remaining = boolean_bodies(body, tool, "subtract", allow_disjoint=True)
    lumps = remaining.solids()
    total_vol = sum(s.volume for s in lumps)
    # Analytic: two leg stubs, each 10x10x25 = 2500 → 5000.
    print(f"[a-i]  severed lumps kept: {len(lumps)}; total volume={total_vol:.3f}")
    assert len(lumps) == 2, len(lumps)
    assert abs(total_vol - 5000.0) < 1e-3, total_vol
    assert isinstance(remaining, Compound), type(remaining).__name__

    # Section faces must extract correctly from the CLEANED lumps in the returned
    # Compound (the clean() interaction audit 🟡9 flagged): one cut face per leg.
    faces = _coplanar_section_faces(remaining, plane)
    area = sum(f.area for f in faces)
    print(f"[a-ii] section faces from cleaned lumps: {len(faces)}; area={area:.3f}")
    assert len(faces) == 2, len(faces)
    assert abs(area - 200.0) < 1e-3, area  # two 10x10 leg tops
    print("PROBE a (multi-lump sever): PASS — lumps kept, faces from cleaned lumps.\n")


# --- audit 🔴2b probe: multi-loop scanline hatch clip determinism ----------------
def _face_with_interior_hole_loop() -> tuple[Face, Plane]:
    """A cut face that is a rectangle with an INTERIOR circular hole loop.

    Box 40(x) x 20(y) x 30(z) bored Ø10 ALONG Y (the cut normal): the y=0 cut face
    is the 40x30 rectangle with the bore appearing as an interior circle — outer
    loop + one inner loop, the multi-loop clip case (distinct from the spike's
    through-slot which splits into two faces).
    """
    box = Solid.make_box(40, 20, 30).locate(Pos(-20, -10, -15))
    bore = Solid.make_cylinder(5, 40, Plane(origin=(0, -20, 0), z_dir=(0, 1, 0)))
    body = box.cut(bore).solids()[0]
    plane = Plane.XZ  # normal +Y, origin at y=0
    tool = _half_space_eye_side(plane, body)
    remaining = body.cut(tool)
    faces = _coplanar_section_faces(remaining, plane)
    assert len(faces) == 1, len(faces)  # one face, outer + one inner loop
    return faces[0], plane


def _loops_2d(face: Face, plane: Plane) -> list[list[tuple[float, float]]]:
    """Project the face's outer + inner wires into the view plane as 2D polylines.

    Loops are canonicalized (audit 🔴7): outer_wire vs inner_wires are distinguished
    by build123d (never by winding heuristics), and each loop is pinned to a
    deterministic START VERTEX (lexicographically smallest projected (u,v)) so the
    polyline is byte-stable regardless of OCCT edge-enumeration order.
    """
    samples = 64  # deterministic per-edge sampling for the probe's polyline clip

    def wire_to_polyline(wire: object) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for edge in wire.edges():  # type: ignore[attr-defined]
            for i in range(samples):
                p: Vector = edge @ (i / samples)
                lp = plane.to_local_coords(p)
                pts.append((round(float(lp.X), 9), round(float(lp.Y), 9)))
        # Pin the start vertex to the lexicographically smallest point.
        k = min(range(len(pts)), key=lambda i: pts[i])
        return pts[k:] + pts[:k]

    loops = [wire_to_polyline(face.outer_wire())]
    loops += [wire_to_polyline(w) for w in face.inner_wires()]
    return loops


def _scanline_hatch(
    loops: list[list[tuple[float, float]]], angle_deg: float, spacing: float
) -> list[tuple[float, float, float, float]]:
    """Analytic scanline hatch clip over multi-loop faces (even-odd rule).

    Rotate the plane so hatch lines are horizontal, sweep scanlines at fixed
    *spacing* from a deterministic origin (the min rotated-v of all loops snapped
    to the spacing grid), intersect every loop edge, sort crossings, and pair them
    even-odd (so interior hole loops carve out gaps). GRAZING handling (audit 🔴7):
    an edge whose lower endpoint lies exactly on the scanline is counted, its upper
    endpoint is not (half-open [lo, hi)), so a vertex touched by a scanline yields
    exactly one crossing — no double count, no dropped span.
    """
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)

    def rot(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] * ca + p[1] * sa, -p[0] * sa + p[1] * ca)

    redges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for loop in loops:
        rl = [rot(p) for p in loop]
        for i in range(len(rl)):
            redges.append((rl[i], rl[(i + 1) % len(rl)]))
    vmin = min(min(e[0][1], e[1][1]) for e in redges)
    vmax = max(max(e[0][1], e[1][1]) for e in redges)
    v0 = math.ceil(vmin / spacing) * spacing  # snap to a deterministic grid
    segs: list[tuple[float, float, float, float]] = []
    v = v0
    while v <= vmax + 1e-12:
        xs: list[float] = []
        for (x1, y1), (x2, y2) in redges:
            lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
            if lo <= v < hi:  # half-open: grazing vertex counted once
                t = (v - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):  # even-odd pairing → interior spans
            segs.append((xs[i], v, xs[i + 1], v))
        v += spacing
    return segs


def probe_multiloop_hatch_clip() -> None:
    face, plane = _face_with_interior_hole_loop()
    loops = _loops_2d(face, plane)
    print(f"[b-i]  loops: 1 outer + {len(loops) - 1} inner (interior hole)")
    assert len(loops) == 2, len(loops)

    run1 = _scanline_hatch(loops, 45.0, 3.0)
    run2 = _scanline_hatch(loops, 45.0, 3.0)
    assert run1 == run2, "hatch clip is NON-deterministic"
    # Some scanlines must produce >1 span (the hole splits them) — proves the
    # even-odd multi-loop carve actually excludes the interior loop.
    scan_rows = {round(s[1], 6) for s in run1}
    split_rows = sum(
        1 for r in scan_rows if sum(1 for s in run1 if round(s[1], 6) == r) > 1
    )
    print(
        f"[b-ii] {len(run1)} hatch segments over {len(scan_rows)} scanlines; "
        f"{split_rows} scanline(s) split by the hole; deterministic across 2 runs"
    )
    assert split_rows > 0, "the interior hole loop did not carve any scanline"
    print("PROBE b (multi-loop hatch clip): PASS — even-odd carve, deterministic.\n")


if __name__ == "__main__":
    run_core_spike()
    probe_multilump_sever()
    probe_multiloop_hatch_clip()
    print("ALL SPIKE + PROBES PASSED.")
