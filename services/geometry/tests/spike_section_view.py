"""THROWAWAY feasibility spike for SECTION VIEWS (docs/design/drawings-section.md).

NOT a production test — proves the core kernel operation is tractable with our
stack (OCP/build123d + the shipped datum/boolean/HLR infrastructure) BEFORE we
commit to building the feature. Delete after the auditor signs off on the design.

What it proves, on a real evaluated-style solid (a 40x20x30 box with a Ø10 through
hole — the WB-64 "interior cavity" shape in miniature):

  (i)  a datum plane can CUT the solid (half-space subtract) into the
       "remaining solid behind the cut", reusing build123d's boolean surface;
  (ii) the SECTION CROSS-SECTION FACE(S) coplanar with the cut plane can be
       extracted and their area checked ANALYTICALLY (the region to hatch); and
  (iii) the remaining solid HLR-projects through the SHIPPED ``project_view`` seam
       (the behind-geometry), with the hole now open on the cut face.

Run:  uv run python -m pytest services/geometry/tests/spike_section_view.py -s
  or: uv run python services/geometry/tests/spike_section_view.py
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import math

from build123d import Compound, Face, Plane, Pos, Solid
from geometry.drawings.project import project_view

# --- analytic model -------------------------------------------------------------
BOX_X, BOX_Y, BOX_Z = 40.0, 20.0, 30.0
HOLE_R = 5.0
# Cut plane = world XZ (normal +Y) through the box centre (Y=0), through the hole
# axis (Z). The FRONT view (outward normal N = (0,-1,0)) looks straight at it — the
# incumbent "full section on a principal plane" case v1 targets.
CUT_PLANE = Plane.XZ  # origin (0,0,0), z_dir = (0,1,0)


def _box_with_through_hole() -> Solid:
    """A 40x20x30 box centred on the origin with a Ø10 hole bored through +Z.

    Stands in for an ``evaluate_tree`` body — same concrete ``build123d.Solid`` the
    drawings pipeline already feeds to ``project_view``.
    """
    box = Solid.make_box(BOX_X, BOX_Y, BOX_Z).locate(
        Pos(-BOX_X / 2, -BOX_Y / 2, -BOX_Z / 2)
    )
    hole = Solid.make_cylinder(HOLE_R, BOX_Z * 2).locate(Pos(0, 0, -BOX_Z))
    return box.cut(hole).solids()[0]


def _half_space_behind(plane: Plane, bbox_reach: float) -> Solid:
    """A big box occupying the +normal (eye) side of *plane* — the material to
    REMOVE so the cut face is exposed to the viewer.

    The FRONT view eye sits on -Y (N = model->eye = (0,-1,0)); we remove everything
    on the -Y side so the Y=0 cut face is the nearest surface. The half-space box is
    placed with one face ON the plane, extending ``bbox_reach`` along -normal and
    spanning +/- reach in-plane — provably larger than the solid, so the subtract is
    a clean planar cut, not a partial notch.
    """
    reach = bbox_reach
    # Local box: corner at (-reach,-reach,-2*reach), size (2reach)^3 in the plane's
    # frame, so it fills the -z_dir (behind-the-plane, eye) side; then move it into
    # the plane's coordinate frame (plane z_dir is the cut normal +Y).
    local = Solid.make_box(2 * reach, 2 * reach, 2 * reach).locate(
        Pos(-reach, -reach, -2 * reach)
    )
    return local.moved(plane.location)


def _coplanar_section_faces(remaining: Solid | Compound, plane: Plane) -> list[Face]:
    """Faces of *remaining* lying ON *plane* — the cross-section to hatch.

    A face is a section face iff its normal is parallel to the cut normal AND a
    point on it satisfies the plane equation (within the kernel linear tol). This
    is the "which faces did the cut create" question the production op must answer.
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


def run_spike() -> None:
    body = _box_with_through_hole()
    reach = max(BOX_X, BOX_Y, BOX_Z) * 4
    tool = _half_space_behind(CUT_PLANE, reach)

    # (i) the cut — half-space subtract → remaining solid behind the plane.
    remaining = body.cut(tool)
    lumps = remaining.solids()
    print(f"[i]   cut produced {len(lumps)} lump(s); volume={remaining.volume:.3f}")
    # Analytic: half the box (40*10*30) minus half the hole cylinder through it.
    half_box = BOX_X * (BOX_Y / 2) * BOX_Z
    half_hole = math.pi * HOLE_R**2 * BOX_Z / 2
    expected_vol = half_box - half_hole
    assert abs(remaining.volume - expected_vol) < 1e-3, (
        remaining.volume,
        expected_vol,
    )

    # (ii) the section cross-section face(s) — the region to hatch.
    faces = _coplanar_section_faces(remaining, CUT_PLANE)
    area = sum(f.area for f in faces)
    # Analytic: rectangle 40(x) x 30(z) minus the hole's slot (2R wide in x, full z).
    expected_area = BOX_X * BOX_Z - (2 * HOLE_R) * BOX_Z
    print(
        f"[ii]  {len(faces)} section face(s); area={area:.3f} "
        f"(analytic {expected_area:.3f})"
    )
    assert abs(area - expected_area) < 1e-3, (area, expected_area)

    # (iii) HLR-project the remaining (behind) geometry through the shipped seam.
    proj = project_view(remaining, "front", scale=1.0)
    visible = len(proj.visible_edges)
    hidden = len(proj.hidden_edges)
    print(f"[iii] front-view HLR of remaining: {visible} visible, {hidden} hidden")
    assert visible > 0

    print("SPIKE VERDICT: core section op is TRACTABLE on the shipped stack.")


def test_spike_section_view_tractable() -> None:
    run_spike()


if __name__ == "__main__":
    run_spike()
