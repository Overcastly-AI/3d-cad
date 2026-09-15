"""Kernel probes the real-part gauntlet needs that the service does not expose.

Lives HERE, not in `scripts/gauntlet.py`, for two reasons. The service-boundary
rule (CLAUDE.md) says only `services/geometry` imports OCP/build123d, and the
pyright relaxation the stub-less OCP wheel forces has an established home in this
service (`kernel/properties.py` carries the same directives with the same
reason). `scripts/gauntlet.py` loads this module by path, exactly as it loads
`_big_part_builders.py`.

The OCP wheel ships no type stubs, so the raw GProp calls below are opaque to
pyright; the directives scope that relaxation to this file only.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

from geometry.kernel.types import BodyShape
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

#: Tolerance for the adaptive integrator. Volume is stable from 1e-5 through
#: 1e-11 on every fixture measured (the residual wobble is ~5e-7 relative, the
#: integrator's own noise), so this is comfortably inside the converged plateau
#: and not a number that needs tuning per part.
CONVERGED_EPS = 1e-9


def converged_volume(shape: BodyShape, eps: float = CONVERGED_EPS) -> float:
    """Volume from OCCT's ADAPTIVE integrator, refined to *eps*.

    :func:`geometry.kernel.measure_shape` ships the TWO-argument
    ``BRepGProp::VolumeProperties_s``, which integrates at a FIXED Gauss order
    chosen from each surface's degree. For a plane or a quadric that order is
    exact, and every authored golden in this repo is planes and quadrics — box,
    cylinder, sphere and torus all agree with this function to 1e-16 and with
    their closed forms exactly. That is why no golden can fail for this reason,
    and why the gauntlet had to go and find a real part to see it.

    On trimmed NURBS the fixed order is NOT exact. Measured on the KUKA KR600
    import (4 123 faces): the shipped call reads 1 067 269 278.68 mm^3 while this
    one converges to 1 065 685 171 mm^3 — **1.5e-3 relative**, ~1.58 litres on a
    1.07 m^3 robot, in the third significant figure of a number the inspector
    shows a user.

    ``onlyClosed=False`` is deliberate. Passing ``True`` drops open shells, which
    would confound a genuine integration error with a deliberate exclusion; on
    the KUKA fixture that exclusion is worth 5.8e-6 against a 1.5e-3 signal, so
    they are not close — but a comparison with the confound left on would not
    have been evidence of anything.
    """
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, eps, False, False)
    return float(props.Mass())


def gauss_error(shape: BodyShape) -> float:
    """Relative gap between the volume the PRODUCT reports and the converged one."""
    from geometry.kernel import measure_shape

    reported = measure_shape(shape).volume
    converged = converged_volume(shape)
    if not converged:
        return 0.0
    return abs(reported - converged) / abs(converged)
