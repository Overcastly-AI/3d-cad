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

#: Tolerance for this probe's adaptive integration.
#:
#: **DELIBERATELY NOT the shipped ``VOLUME_EPS`` (1e-10).** Since F1 was fixed
#: (2026-09-15) the product ALSO integrates adaptively, so a probe using the same
#: eps would compare a number with itself and :func:`gauss_error` would be
#: identically zero — a gate that cannot fail. One decade tighter keeps it a
#: genuine second opinion: it asks "does the shipped reading survive refining the
#: bound further", which is the property that actually matters.
#:
#: The claim this constant used to carry — "volume is stable from 1e-5 through
#: 1e-11, residual wobble ~5e-7" — was measured on the KUKA and is NOT true of
#: every fixture. Re-measured across eps 1e-8…1e-14: `as1-oc-214` is stable to
#: <1e-9 and `gearbox-11752` to ~2e-7, but the `ventilator` wanders by **3.8e-5**
#: and `rc-buggy-suspension` by **4.3e-3** — on the buggy that is MORE than the
#: fixed-order bias the probe was built to expose. OCCT's own returned error
#: estimate stalls at a per-shape floor (7.0e-7 for the KUKA, 1.2e-6 for the
#: buggy) and refuses to improve at any eps. So "converged" is aspirational for
#: some shapes, and a nonzero :func:`gauss_error` on those two is the
#: INTEGRATOR'S OWN NON-CONVERGENCE, not a bias in the shipped call.
CONVERGED_EPS = 1e-9


def converged_volume(shape: BodyShape, eps: float = CONVERGED_EPS) -> float:
    """Volume from OCCT's adaptive integrator, refined to *eps*.

    HISTORY, because this probe is the instrument that found F1 and its own
    docstring is now the record of it. :func:`geometry.kernel.measure_shape`
    USED to call the two-argument ``BRepGProp::VolumeProperties_s``, which
    integrates at a FIXED Gauss order chosen from each surface's degree. For a
    plane or a quadric that order is exact, and every authored golden in this
    repo was planes and quadrics — so no golden could fail for this reason, and
    the gauntlet had to go and find a real part to see it. On the KUKA KR600
    import (4 123 faces) the shipped call read 1 067 269 278.68 mm^3 against this
    function's 1 065 685 171 — **1.5e-3 relative**, ~1.58 litres on a 1.07 m^3
    robot. A third, independent oracle (divergence theorem over a tessellation,
    no GProp anywhere) put the truth within 1.7e-5 of THIS function's answer and
    1.5e-3 from the fixed order's, which is what settled it.

    ``measure_shape`` now integrates adaptively at ``VOLUME_EPS = 1e-10``, so
    this function is no longer measuring a different ALGORITHM — it measures a
    tighter BOUND on the same one. See :data:`CONVERGED_EPS` for why that is
    still worth running and what a nonzero result now means.

    ``onlyClosed=False`` is deliberate, and matches what the shipped call passes.
    ``True`` drops open shells, which would confound an integration difference
    with a deliberate exclusion; on the KUKA that exclusion is worth 5.8e-6.
    """
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, eps, False, False)
    return float(props.Mass())


def gauss_error(shape: BodyShape) -> float:
    """Relative gap between the volume the PRODUCT reports and this tighter one.

    Named for the fixed-order Gauss bias it was built to expose; since that was
    fixed it reads as a CONVERGENCE probe — see :data:`CONVERGED_EPS`. Measured
    on the five gauntlet fixtures before -> after the fix: as1 2.89e-6 ->
    4.21e-13, gearbox 2.32e-5 -> 1.86e-9, KUKA **1.49e-3 -> 6.67e-7**, while
    ventilator (2.73e-5 -> 3.49e-5) and rc-buggy (1.02e-3 -> 1.26e-3) do not
    improve, because on those two the integrator does not converge and the
    residual is its own floor rather than anything the shipped call chose.
    """
    from geometry.kernel import measure_shape

    reported = measure_shape(shape).volume
    converged = converged_volume(shape)
    if not converged:
        return 0.0
    return abs(reported - converged) / abs(converged)
