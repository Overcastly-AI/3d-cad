"""Test-local L-bracket body builder for the sheet-metal unfold spike (SPIKE 0).

NOT a test module (leading underscore → not collected). Mirrors how the drawings
goldens build bodies with test helpers: the sheet-metal FEATURE schema (base
flange + edge flange) is the NEXT slice, so this spike builds the folded bracket
directly — two flat flanges joined by a constant-thickness quarter-cylinder bend,
swept along the bend-width axis — purely to exercise the unfold math + the OCCT
face resolution.

Single source of the builder (CLAUDE.md DRY rule): imported by
``tests/test_sheet_metal.py`` (in-process) via ``importlib`` file-path loading
(the workspace runs ``--import-mode=importlib``, so test modules cannot import
each other by name) AND run as ``__main__`` by that test's cross-process
determinism probe, so both legs unfold the byte-identical body.

The OCP wheel ships no type stubs, so the raw build123d calls are opaque to
pyright; the directive scopes that relaxation to this file only.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false

import math

from build123d import Edge, Face, Solid, Vector, Wire
from geometry.kernel.types import BodyShape


def build_l_bracket(
    leg1_mm: float,
    leg2_mm: float,
    thickness_mm: float,
    bend_radius_mm: float,
    bend_width_mm: float,
) -> BodyShape:
    """A constant-thickness L-bracket: base flange + one 90° edge flange.

    Cross-section (in the world XZ plane, swept ``bend_width_mm`` along +Y):

    * base flange — flat, INNER surface at ``z = -r`` running ``x ∈ [-leg1, 0]``
      (free edge at ``x = -leg1``, bend tangent line at ``x = 0``),
    * a quarter-cylinder bend, inner radius ``r = bend_radius_mm`` about the axis
      line ``x = z = 0`` (parallel to Y), outer radius ``r + thickness``,
    * edge flange — flat, INNER surface at ``x = r`` running ``z ∈ [0, leg2]``
      (bend tangent line at ``z = 0``, free edge at ``z = leg2``).

    So each flange's flat planar face length runs EXACTLY from its free edge to
    the bend tangent line — the leg developed length the flat pattern measures
    (§9 golden #1's tangent-line convention). ``leg1_mm``/``leg2_mm`` ARE those
    developed legs; the 90° fold makes the flanges perpendicular.
    """
    r = bend_radius_mm
    outer = r + thickness_mm
    inv = 1.0 / math.sqrt(2.0)

    def p(x: float, z: float) -> tuple[float, float, float]:
        return (x, 0.0, z)

    edges = [
        # base flange inner surface: free edge -> tangent line
        Edge.make_line(p(-leg1_mm, -r), p(0.0, -r)),
        # inner bend arc (radius r), tangent (0,-r) -> tangent (r,0)
        Edge.make_three_point_arc(p(0.0, -r), p(r * inv, -r * inv), p(r, 0.0)),
        # edge flange inner surface: tangent line -> free edge
        Edge.make_line(p(r, 0.0), p(r, leg2_mm)),
        # edge flange free end (thickness)
        Edge.make_line(p(r, leg2_mm), p(outer, leg2_mm)),
        # edge flange outer surface: free edge -> tangent
        Edge.make_line(p(outer, leg2_mm), p(outer, 0.0)),
        # outer bend arc (radius r+thickness)
        Edge.make_three_point_arc(
            p(outer, 0.0), p(outer * inv, -outer * inv), p(0.0, -outer)
        ),
        # base flange outer surface: tangent -> free edge
        Edge.make_line(p(0.0, -outer), p(-leg1_mm, -outer)),
        # base flange free end (thickness)
        Edge.make_line(p(-leg1_mm, -outer), p(-leg1_mm, -r)),
    ]
    wires = Wire.combine(edges)
    if len(wires) != 1 or not wires[0].is_closed:
        raise ValueError("L-bracket cross-section did not close into one wire")
    solid = Solid.extrude(Face(wires[0]), Vector(0.0, bend_width_mm, 0.0))
    return solid


def _main() -> None:
    """CLI: ``python _l_bracket_builder.py <model.json>`` → print the unfold's
    content hash + JSON. The cross-process determinism leg of the golden test."""
    import json
    import sys
    from pathlib import Path

    from geometry.sheet_metal import unfold_l_bracket

    model = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    body = build_l_bracket(
        leg1_mm=model["leg1_mm"],
        leg2_mm=model["leg2_mm"],
        thickness_mm=model["thickness_mm"],
        bend_radius_mm=model["bend_radius_mm"],
        bend_width_mm=model["bend_width_mm"],
    )
    pattern = unfold_l_bracket(body, model["thickness_mm"], model["k_factor"])
    sys.stdout.write(pattern.content_hash() + "\n")
    sys.stdout.write(pattern.to_json_bytes().decode("utf-8") + "\n")


if __name__ == "__main__":
    _main()
