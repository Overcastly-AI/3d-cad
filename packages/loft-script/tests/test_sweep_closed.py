"""A sweep along a CLOSED path, scripted against a real stack (SWEEP-CLOSED-PATH).

The numbers are the torus golden's (``sweep-closed-torus-ring-R50-r5``): an r5
circle swept once around an R50 circle is the ring torus, 2 pi^2 R r^2. A square
path, whose four corners are not tangent-continuous, is the typed refusal.
"""

from __future__ import annotations

import itertools
import math

import loft
import pytest

from .conftest import Stack

PASSWORD = "loft-script-passphrase"
_emails = (f"closed-sweep-{n}@example.com" for n in itertools.count())

#: The torus golden's own bound (curved GProp quadrature plus OCCT's 1e-7 box
#: enlargement); the volume itself lands ~1e-11 from the closed form.
TORUS_TOLERANCE = 2e-7


def test_a_scripted_ring_is_the_torus_and_a_square_loop_is_refused(
    stack: Stack,
) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Tube ring")
        profile = part.sketch(on="XZ", name="Section")
        profile.circle((50, 0), radius=5)
        profile.solve()
        path = part.sketch(on="XY", name="Loop")
        path.circle((0, 0), radius=50)
        path.solve()
        part.sweep(profile, path)
        ring = part.mass_properties()

        square = session.new_part("Square loop")
        section = square.sketch(on="XZ", name="Section")
        section.circle((50, 0), radius=5)
        section.solve()
        loop = square.sketch(on="XY", name="Loop")
        loop.rect(100, 100)
        loop.solve()
        square.sweep(section, loop)
        refused = square.evaluate()

    assert ring.volume == pytest.approx(2 * math.pi**2 * 50 * 25, abs=TORUS_TOLERANCE)
    assert ring.topology.faces == 1
    assert ring.topology.shells == 1
    errors = [r.error for r in refused.result.features if r.error is not None]
    assert [e.code for e in errors] == ["sweep_path_not_tangent"]
    assert "90 deg" in errors[0].message
