"""Test-local depth->=2 bend-chain body builder (sheet-metal bend-chain SPIKE).

NOT a test module (leading underscore -> not collected). The spike proves the
depth->=2 unfold (a flange folded off ANOTHER flange — a box corner / return), so
this helper builds that body through the SHIPPED edge-flange feature path
(:func:`geometry.sheet_metal.edge_flange.build_edge_flange`) applied TWICE:

    base plate  --B1-->  edge flange F1 (depth 1)  --B2-->  return flange F2 (depth 2)

Building through the real feature builder (not a hand-authored cross-section) does
two things the spike needs: it proves a depth-2 body is author-reachable with shipped
code (the design's sec 4.3 claim), and it yields the genuine construction-time
:class:`CylindricalFaceSignature` / base-face :class:`PlanarFaceSignature` provenance
for BOTH bends — so the unfold is driven by provenance, never blind detection.

Two axis relationships are exercised:

* ``"perp"`` — F2 folds off a SIDE edge of F1 (bend axis PERPENDICULAR to B1): the
  genuine box corner, the 2D-and-composed case graph relaxation is feared for.
* ``"parallel"`` — F2 folds off F1's TOP FREE edge (bend axis PARALLEL to B1): the
  sequential chain (a Z / offset), still depth-2 (folds off a moved flange) but a 1D
  development — proves the recursion also covers the parallel chain the shipped
  unfold defers.

Single source of the builder (CLAUDE.md DRY): imported by
``tests/test_sheet_metal_bend_chain.py`` via importlib file-path loading AND run as
``__main__`` for the cross-process determinism leg, so both unfold the byte-identical
body + provenance.

The OCP wheel ships no type stubs, so the raw build123d calls are opaque to pyright;
the directive scopes that relaxation to this file only.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

from dataclasses import dataclass
from typing import Literal

from build123d import Box, Edge, GeomType
from geometry.kernel.types import BodyShape
from geometry.sheet_metal.edge_flange import build_edge_flange
from geometry.sheet_metal.unfold import BendProvenance

ChainKind = Literal["perp", "parallel"]


@dataclass(frozen=True)
class BendChainBody:
    """A built depth-2 body + the construction-time provenance of both its bends."""

    body: BodyShape
    bends: list[BendProvenance]


def _straight_lines(body: BodyShape) -> list[Edge]:
    return [e for e in body.edges() if e.geom_type == GeomType.LINE]


def build_bend_chain(
    base_x_mm: float,
    base_y_mm: float,
    thickness_mm: float,
    bend_radius_mm: float,
    leg1_mm: float,
    leg2_mm: float,
    k_factor: float,
    kind: ChainKind,
) -> BendChainBody:
    """Build a depth-2 bend chain via two shipped edge-flange folds.

    A ``base_x_mm x base_y_mm x thickness_mm`` base plate (centred on the origin,
    top face at ``+t/2``); F1 folds up 90 deg off the ``y = +base_y/2`` top edge
    (bend axis +X), developing ``leg1_mm``; F2 folds 90 deg off F1 (``leg2_mm``),
    with its bend axis PERPENDICULAR (``kind="perp"``, off F1's ``x = +base_x/2``
    side edge — a box corner) or PARALLEL (``kind="parallel"``, off F1's top free
    edge — a sequential chain) to B1.
    """
    t = thickness_mm
    r = bend_radius_mm
    half_x = base_x_mm / 2.0
    half_y = base_y_mm / 2.0
    base = Box(base_x_mm, base_y_mm, t)

    # F1: fold off the top edge parallel to X at y = +half_y.
    def is_f1_edge(e: Edge) -> bool:
        p0 = e @ 0.0
        p1 = e @ 1.0
        d = (p1 - p0).normalized()
        return (
            abs(abs(d.X) - 1.0) < 1e-6
            and abs(p0.Z - t / 2.0) < 1e-6
            and abs(p1.Z - t / 2.0) < 1e-6
            and abs(p0.Y - half_y) < 1e-6
        )

    e1 = next(e for e in _straight_lines(base) if is_f1_edge(e))
    res1 = build_edge_flange(
        base,
        e1,
        flange_length_mm=leg1_mm,
        bend_angle_deg=90.0,
        bend_radius_mm=r,
        thickness_mm=t,
    )
    body1 = res1.body

    # F1 is vertical; it folds OUTWARD, so its inner flat sits at y = half_y + r
    # (tangent to the inner bend cylinder). Pick the F2 edge on that inner flat.
    inner_y = half_y + r

    if kind == "perp":
        # F2 off F1's vertical side edge (axis +Z, perpendicular to B1's +X).
        def is_f2_edge(e: Edge) -> bool:
            p0 = e @ 0.0
            p1 = e @ 1.0
            d = p1 - p0
            if d.length < 1e-9:
                return False
            d = d.normalized()
            return (
                abs(abs(d.Z) - 1.0) < 1e-6
                and abs(p0.X - half_x) < 1e-6
                and abs(p1.X - half_x) < 1e-6
                and abs(p0.Y - inner_y) < 1e-6
            )

        e2 = max(
            (e for e in _straight_lines(body1) if is_f2_edge(e)),
            key=lambda e: float(e.length),
        )
    else:
        # F2 off F1's top free edge (axis +X, parallel to B1) — highest Z on inner flat.
        def is_top_free(e: Edge) -> bool:
            p0 = e @ 0.0
            p1 = e @ 1.0
            d = (p1 - p0).normalized()
            return (
                abs(abs(d.X) - 1.0) < 1e-6
                and abs(p0.Y - inner_y) < 1e-6
                and abs(p1.Y - inner_y) < 1e-6
            )

        e2 = max(
            (e for e in _straight_lines(body1) if is_top_free(e)),
            key=lambda e: ((e @ 0.0).Z + (e @ 1.0).Z) / 2.0,
        )

    res2 = build_edge_flange(
        body1,
        e2,
        flange_length_mm=leg2_mm,
        bend_angle_deg=90.0,
        bend_radius_mm=r,
        thickness_mm=t,
    )

    bends = [
        BendProvenance(res1.cyl_signature, res1.base_face_signature, k_factor),
        BendProvenance(res2.cyl_signature, res2.base_face_signature, k_factor),
    ]
    return BendChainBody(body=res2.body, bends=bends)


def _main() -> None:
    """CLI: ``python _bend_chain_builder.py <model.json>`` -> print the unfold's
    content hash + JSON (the cross-process determinism leg of the spike golden)."""
    import json
    import sys
    from pathlib import Path

    from geometry.sheet_metal._spike_bend_chain import unfold_bend_chain

    model = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    built = build_bend_chain(
        base_x_mm=model["base_x_mm"],
        base_y_mm=model["base_y_mm"],
        thickness_mm=model["thickness_mm"],
        bend_radius_mm=model["bend_radius_mm"],
        leg1_mm=model["leg1_mm"],
        leg2_mm=model["leg2_mm"],
        k_factor=model["k_factor"],
        kind=model["kind"],
    )
    result = unfold_bend_chain(
        built.body, built.bends, model["thickness_mm"], model["k_factor"]
    )
    sys.stdout.write(result.pattern.content_hash() + "\n")
    sys.stdout.write(result.pattern.to_json_bytes().decode("utf-8") + "\n")


if __name__ == "__main__":
    _main()
