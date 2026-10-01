"""A sealed shell whose cavity pinches rebuilds the same in every process
(SHELL-HEAL-NONDETERMINISM, kernel/shell_heal.py).

A rod r10 x 40 with a through cross-bore r6, sealed at t = 2: the rod's and the
bore's offsets are equal r8 cylinders, so the cavity is two pieces touching at
(0, +-8, 0). OCCT's Arc offset builds it one of two ways depending on where
malloc put the input's faces; one of them used to be refused (31 of 60 rebuilds
over 3 processes). The r4 sibling has no pinch and must not change.

Truths, by hand (no offset): the body is pi 10^2 40 less the bore, the integral
over |y| < r of 4 sqrt(r^2 - y^2) sqrt(100 - y^2) dy. The r6 cavity is the r8
rod (36 long) less the r8 bore through it, a Steinmetz solid of 16/3 8^3. The r4
cavity is the r8 rod less the r6 bore through it, the same integral with 64 for
100.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import copy
import json
import math
import os
import subprocess
import sys

import pytest
from build123d import Axis, Cylinder, Solid
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell_heal import split_pinched_faces

#: Hand-computed shelled volumes (module docstring), mm^3.
TRUTH = {6.0: 5903.845186930, 4.0: 6014.604053811}

#: Fresh interpreters, each with its own hash seed and a different amount of
#: allocation before the body is built, so the input's faces land at different
#: addresses. Before the fix about half of all processes refused r6.
PROCESSES = 6
#: Rebuilds per process, each on a fresh copy (fresh addresses) of the body.
REBUILDS = 3

_WORKER = """
import copy, json, sys
from build123d import Axis, Box, Cylinder
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell import ShellError, ShellThicknessError, shell_body

ballast = [Box(1, 1, 1) for _ in range(int(sys.argv[1]))]
outcomes = {}
for radius in (6.0, 4.0):
    rod = Cylinder(10, 40).solids()[0]
    bore = Cylinder(radius, 200).solids()[0].rotate(Axis.Y, 90)
    body = rod.cut(bore).solids()[0]
    seen = []
    for _ in range(int(sys.argv[2])):
        try:
            shelled = shell_body(copy.deepcopy(body), [], 2.0)
            seen.append(
                [
                    len(shelled.shells()),
                    len(shelled.faces()),
                    shelled.is_valid,
                    round(volume_properties(shelled).volume, 6),
                ]
            )
        except (ShellError, ShellThicknessError) as refusal:
            seen.append(type(refusal).__name__)
    outcomes[str(radius)] = seen
print(json.dumps(outcomes))
"""


def _rod(radius: float) -> Solid:
    rod = Cylinder(10, 40).solids()[0]
    bore = Cylinder(radius, 200).solids()[0].rotate(Axis.Y, 90)
    return rod.cut(bore).solids()[0]


def test_the_truths_are_the_closed_forms() -> None:
    def bored(r: float, rod_r: float) -> float:
        # Midpoint rule on the substitution y = r sin(a): smooth, so 20000
        # steps are exact far below the 1e-6 the truths are quoted to.
        steps = 20000
        total = 0.0
        for i in range(steps):
            a = -math.pi / 2 + (i + 0.5) * math.pi / steps
            y = r * math.sin(a)
            total += 4 * r * math.cos(a) ** 2 * r * math.sqrt(rod_r**2 - y * y)
        return total * math.pi / steps

    body_6 = math.pi * 100 * 40 - bored(6, 10)
    assert body_6 - (math.pi * 64 * 36 - 16 / 3 * 8**3) == pytest.approx(
        TRUTH[6.0], abs=1e-6
    )
    body_4 = math.pi * 100 * 40 - bored(4, 10)
    cavity_4 = math.pi * 64 * 36 - bored(6, 8)
    assert body_4 - cavity_4 == pytest.approx(TRUTH[4.0], abs=1e-6)


def test_a_pinched_cavity_rebuilds_the_same_in_every_process() -> None:
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(index * 37), str(REBUILDS)],
            env={**os.environ, "PYTHONHASHSEED": str(index * 7919 + 1)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(PROCESSES)
    ]
    runs: list[dict[str, list[object]]] = []
    for worker in workers:
        out, err = worker.communicate(timeout=600)
        assert worker.returncode == 0, err
        runs.append(json.loads(out.strip().splitlines()[-1]))
    for radius, truth in TRUTH.items():
        outcomes = {json.dumps(outcome) for run in runs for outcome in run[str(radius)]}
        assert len(outcomes) == 1, (radius, outcomes)
        shells, faces, valid, volume = json.loads(outcomes.pop())
        assert valid
        assert volume == pytest.approx(truth, abs=1e-6)
        # r6: the outside and one shell per cavity piece; r4: one cavity.
        assert (shells, faces) == ((3, 11) if radius == 6.0 else (2, 8))


def test_the_pinched_variant_heals_into_the_two_cavities() -> None:
    """The variant that used to be refused. Which one OCCT builds depends on
    addresses, so fresh copies are hollowed until it appears (each copy draws
    it about half the time; 64 misses in a row is 5e-20)."""
    body = _rod(6.0)
    pinched = None
    for _ in range(64):
        raw = copy.deepcopy(body).hollow([], -2.0)
        if not raw.is_valid:
            pinched = raw
            break
    assert pinched is not None, "OCCT no longer builds the pinched variant"
    assert len(pinched.shells()) == 2

    healed = split_pinched_faces(pinched)

    # The bore's face spanning both lobes (512 mm^2) is 128 + 128 + 256, the
    # rod's (1297.557) two of 648.779, so 8 faces become 11.
    assert len(healed.faces()) == 11
    areas = sorted(round(face.area, 3) for face in healed.faces())
    assert areas.count(648.779) == 2
    assert [a for a in areas if a in (128.0, 256.0)] == [128.0, 128.0, 256.0]
    assert volume_properties(healed).volume == pytest.approx(
        volume_properties(pinched).volume, abs=1e-9
    )


def test_a_valid_solid_is_returned_as_is() -> None:
    body = _rod(4.0)
    assert split_pinched_faces(body) is body
