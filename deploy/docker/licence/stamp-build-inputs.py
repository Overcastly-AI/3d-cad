#!/usr/bin/env python3
"""Record the header-only libraries compiled INTO the geometry image's planegcs.

planegcs is built from vendor/planegcs in the image's build stage
(SKETCH-SOLVE-HEAP-ORDER). Eigen (MPL-2.0) and Boost (BSL-1.0) are header-only,
so their code ends up inside ``_planegcs.cpython-*.so`` and the binary carries
no version of either. Eigen's MPL-2.0 §3.2 duty (make the Source Code Form
available) needs to know WHICH Eigen that was, so this writes the Debian
package versions the build compiled against into the venv:

    /app/.venv/loft-build-inputs.json

The runtime stage's licence gate (scripts/check-licences.py, detector
``build-stamp`` in scripts/corresponding_source.py) compares that record with
the version pinned in deploy/licenses/corresponding-source.json and fails the
image build on a mismatch, exactly as it does when a wheel bump moves OCCT.

Usage (geometry build stage, after the headers are installed):
    python3 stamp-build-inputs.py /app/.venv/loft-build-inputs.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PACKAGES = ("libeigen3-dev", "libboost-dev")


def dpkg_version(package: str) -> str:
    out = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", package],
        capture_output=True,
        text=True,
        check=True,
    )
    version = out.stdout.strip()
    if not version:
        raise SystemExit(f"stamp-build-inputs: {package} is not installed")
    return version


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    record = {package: dpkg_version(package) for package in PACKAGES}
    dest = Path(argv[0])
    dest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"stamp-build-inputs: {dest}: {record}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
