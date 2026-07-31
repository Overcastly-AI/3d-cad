#!/usr/bin/env python3
"""Build-time proof that removing the GPL library did not change the geometry.

Run inside the geometry image, after strip-gpl-jbig.sh has replaced jbigkit.
Two things are asserted, and both have to hold or the image build fails:

1. **The GPL library really is gone from the running process.** We import the
   kernel and then read /proc/self/maps: the mapped `libjbig` must be OUR stub
   (marker string present, "JBIG-KIT" absent). A static file check can be
   fooled by a second copy elsewhere on the loader path; the address space
   cannot.

2. **The kernel still computes the right answer.** A box minus a cylinder has
   a closed-form volume, so this is checked against arithmetic rather than
   against a recorded number that could have been recorded from a broken build:

       10 x 20 x 30 - pi x 3^2 x 30 = 5151.769983530756 mm^3

   Then a tessellation and a STEP export, because those are the two OCCT
   subsystems that actually touch the image/IO libraries the stub sits under.

If any of this fails, the stub is not inert and the whole LIC-1 analysis needs
redoing — do not "fix" it by loosening the tolerance. docs/LICENSING.md §4.
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

STUB_MARKER = b"LOFT-GPL-FREE-JBIG-STUB"
TOLERANCE_MM3 = 1e-6


def main() -> int:
    import OCP.BRepPrimAPI  # noqa: F401  (import for its side effect: load OCCT)

    # --- 1. what is actually mapped into this process -----------------------
    mapped = {
        line.split()[-1]
        for line in Path("/proc/self/maps").read_text().splitlines()
        if "libjbig" in line
    }
    if not mapped:
        print(
            "verify-kernel: FAILED — no libjbig is mapped at all. Either the "
            "library was deleted (eager binding means this import should have "
            "died) or the OCP wheel changed shape; re-run the LIC-1 analysis.",
            file=sys.stderr,
        )
        return 1
    for path in sorted(mapped):
        blob = Path(path).read_bytes()
        if STUB_MARKER not in blob or b"JBIG-KIT" in blob:
            print(
                f"verify-kernel: FAILED — {path} is mapped into a process that "
                "imports the kernel and it is NOT our GPL-free stub. Publishing "
                "this image would convey GPL-2.0 code.",
                file=sys.stderr,
            )
            return 1
        print(f"verify-kernel: mapped {path} is the GPL-free stub ({len(blob)} bytes)")

    # --- 2. real geometry through the stubbed stack -------------------------
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.GProp import GProp_GProps
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    box = BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()
    cylinder = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(5.0, 10.0, 0.0), gp_Dir(0.0, 0.0, 1.0)), 3.0, 30.0
    ).Shape()
    cut = BRepAlgoAPI_Cut(box, cylinder).Shape()

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(cut, props)
    measured = props.Mass()
    analytic = 10.0 * 20.0 * 30.0 - math.pi * 3.0**2 * 30.0
    if abs(measured - analytic) > TOLERANCE_MM3:
        print(
            f"verify-kernel: FAILED — boolean cut measured {measured:.9f} mm^3, "
            f"analytic {analytic:.9f} mm^3. The stub is NOT inert; stop and "
            "re-open docs/LICENSING.md §4 before shipping anything.",
            file=sys.stderr,
        )
        return 1
    print(f"verify-kernel: boolean cut {measured:.6f} mm^3 == analytic to 1e-6")

    BRepMesh_IncrementalMesh(cut, 0.1, False, 0.5, True)
    with tempfile.TemporaryDirectory() as tmp:
        step = Path(tmp) / "cut.step"
        writer = STEPControl_Writer()
        writer.Transfer(cut, STEPControl_AsIs)
        writer.Write(str(step))
        size = step.stat().st_size
    if size < 1024:
        print(f"verify-kernel: FAILED — STEP export is {size} bytes", file=sys.stderr)
        return 1
    print(f"verify-kernel: tessellation ok, STEP export {size} bytes")
    print("verify-kernel: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
