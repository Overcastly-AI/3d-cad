"""A sharp shell leaves a sharp cavity corner at every concave edge
(SHELL-SHARP-DEFAULT).

SolidWorks, Onshape and Fusion shell with sharp inside corners by default:
behind a concave edge of the body, the two inward walls are extended until
they meet. Loft's shells were all Arc (rounded) until 2026-10-07, and stored
shells stay so; a new shell is ``shell_type: "sharp"``, OCCT's Intersection
join.

The truth here comes from neither offset join. Every body is a convex box
minus pockets (boxes and cylinders, blind or breaking through the side), and
a sharp shell moves every face's plane (or cylinder) inward by ``t``, so its
cavity is the same construction with every face moved: the box shrunk by
``t`` on each side, minus each pocket grown by ``t`` on each side (a
cylinder's radius and both its ends). That is built by booleans of
primitives. Each sharp shell must raise a typed error or read that volume,
with one more shell than the cavity has pockets.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from build123d import Axis, Compound, Face, Location, Plane, Solid
from geometry.kernel import shell as shell_module
from geometry.kernel.fillet_isolation import run_isolated
from geometry.kernel.naming import OpHistory
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell import (
    SHARP_OP,
    ShellError,
    ShellThicknessError,
    ShellTimeout,
    _concave_edge_count,
    shell_body,
)
from geometry.kernel.shell_walls import FaultKind, ShellDefinition
from geometry.kernel.types import BodyShape
from loft_wire.features import ShellParamsV1
from OCP.BinTools import BinTools

#: Planes and cylinders only, integrated by the same rule on both sides.
VOLUME_REL = 1e-9

Grown = Callable[[float], Solid]


def _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> Grown:
    """An axis-aligned box, and the same box with every face moved out by g."""

    def make(g: float) -> Solid:
        return Solid.make_box(x1 - x0 + 2 * g, y1 - y0 + 2 * g, z1 - z0 + 2 * g).moved(
            Location((x0 - g, y0 - g, z0 - g))
        )

    return make


def _cyl(x: float, y: float, z0: float, z1: float, r: float) -> Grown:
    """A z cylinder, and the same with its radius and both ends moved out by g."""

    def make(g: float) -> Solid:
        return Solid.make_cylinder(
            r + g, z1 - z0 + 2 * g, Plane.XY.offset(z0 - g).move(Location((x, y, 0)))
        )

    return make


@dataclass(frozen=True)
class Case:
    """A box minus pockets, both for any grow ``g``: the body at g = 0, and its
    sharp cavity (box shrunk by t, pockets grown by t)."""

    name: str
    thickness: float
    size: tuple[float, float, float]
    pockets: tuple[Grown, ...]

    def _outer(self, g: float) -> Solid | None:
        x, y, z = self.size
        if min(x, y, z) <= 2 * g:
            return None
        return _box(g, g, g, x - g, y - g, z - g)(0.0)

    def body(self) -> Solid:
        outer = self._outer(0.0)
        assert outer is not None
        (solid,) = outer.cut(*[pocket(0.0) for pocket in self.pockets]).solids()
        return solid

    def cavity(self) -> list[Solid]:
        outer = self._outer(self.thickness)
        if outer is None:
            return []
        grown = [pocket(self.thickness) for pocket in self.pockets]
        return list(outer.cut(*grown).solids())


def _cases() -> list[Case]:
    cases: list[Case] = []
    for a, b in ((30.0, 20.0), (20.0, 10.0), (10.0, 25.0)):
        for t in (1.0, 2.0, 3.0):
            cases.append(  # an L: one notch through the full height
                Case(
                    f"l-notch-{a}x{b}-t{t}",
                    t,
                    (40, 30, 20),
                    (_box(40 - a, 30 - b, -1, 41, 31, 21),),
                )
            )
    for t in (1.0, 2.0, 4.0):
        cases.append(  # a step across the full width
            Case(f"step-t{t}", t, (40, 30, 20), (_box(20, -1, 10, 41, 31, 21),))
        )
    for t in (1.0, 2.0, 3.0, 4.5):
        cases.append(  # a U channel
            Case(f"u-channel-t{t}", t, (40, 30, 20), (_box(10, -1, 8, 30, 31, 21),))
        )
    for t in (1.0, 2.0):
        cases.append(  # a Z: notches at opposite corners
            Case(
                f"z-notches-t{t}",
                t,
                (40, 30, 20),
                (_box(-1, 20, -1, 25, 31, 21), _box(15, -1, -1, 41, 10, 21)),
            )
        )
    for r in (4.0, 6.0, 10.0):
        for depth in (4.0, 8.0):
            for t in (1.0, 1.5, 2.0):
                cases.append(  # a blind bore from the bottom
                    Case(
                        f"blind-bore-r{r}-d{depth}-t{t}",
                        t,
                        (60, 40, 12),
                        (_cyl(30, 20, -1, depth, r),),
                    )
                )
    for depth in (5.0, 10.0):
        for t in (1.0, 2.0):
            cases.append(  # a blind rectangular pocket from the top
                Case(
                    f"pocket-d{depth}-t{t}",
                    t,
                    (40, 30, 15),
                    (_box(10, 10, 15 - depth, 30, 20, 16),),
                )
            )
    for gap in (1.0, 3.0, 6.0):
        cases.append(  # two blind pockets, the wall between them thin or not
            Case(
                f"two-pockets-gap{gap}-t1.5",
                1.5,
                (50, 30, 15),
                (
                    _box(5, 5, 6, 25 - gap / 2, 25, 16),
                    _box(25 + gap / 2, 5, 6, 45, 25, 16),
                ),
            )
        )
    return cases


CASES = _cases()

#: The cases refused, each as the rounded shell refuses it (2026-10-07). Where
#: the plate is 12 thick and the bore floor at z 8, the wall over the floor is
#: 4 = 2 t at t 2: the slit SH-1 refuses (kernel/shell.py). The U's 10 mm legs
#: at t 4.5: both joins raise.
REFUSED: dict[str, type[Exception]] = {
    "blind-bore-r4.0-d8.0-t2.0": ShellThicknessError,
    "blind-bore-r6.0-d8.0-t2.0": ShellThicknessError,
    "blind-bore-r10.0-d8.0-t2.0": ShellThicknessError,
    "u-channel-t4.5": ShellError,
}


def test_every_case_has_a_concave_edge() -> None:
    """The sweep tests the sharp join, not the route a body without a concave
    edge takes (the rounded one)."""
    for case in CASES:
        assert _concave_edge_count(case.body(), case.thickness) > 0, case.name


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_a_sharp_shell_is_its_construction_or_refused(case: Case) -> None:
    body = case.body()
    pockets = case.cavity()
    try:
        shelled = shell_body(body, [], case.thickness, sharp=True)
    except (ShellError, ShellThicknessError) as refusal:
        assert type(refusal) is REFUSED.get(case.name), f"{case.name}: {refusal}"
        return
    assert case.name not in REFUSED
    truth = volume_properties(body).volume - sum(
        volume_properties(pocket).volume for pocket in pockets
    )
    assert pockets, "no cavity fits, yet the shell built one"
    assert volume_properties(shelled).volume == pytest.approx(truth, rel=VOLUME_REL)
    assert len(shelled.shells()) == 1 + len(pockets)
    # Nothing but the cavity is gone: the result and the truth differ by no
    # material either way.
    truth_solid = body.cut(*pockets) if pockets else body
    assert shelled.cut(truth_solid).volume == pytest.approx(0, abs=1e-6)
    assert truth_solid.cut(shelled).volume == pytest.approx(0, abs=1e-6)


# --- the definition tells the two kinds apart ---------------------------------


def _l_bracket() -> Solid:
    """The golden's L: (0,0) (40,0) (40,10) (10,10) (10,30) (0,30), 25 tall."""
    return Case("l", 2.0, (40, 30, 25), (_box(10, 10, -1, 41, 31, 26),)).body()


def _solid(shape: BodyShape) -> Solid:
    assert isinstance(shape, Solid)
    return shape


def _top(body: Solid) -> list[Face]:
    return [body.faces().sort_by(Axis.Z)[-1]]


def test_the_l_bracket_reads_the_hand_derivation() -> None:
    """The golden's numbers by hand: the L (600 mm^2, 25 tall) less the inset L
    (336 mm^2) from z 2 up through the opened top (23); sealed, z 2..23."""
    body = _l_bracket()
    opened = shell_body(body, _top(body), 2.0, sharp=True)
    assert volume_properties(opened).volume == pytest.approx(15000 - 336 * 23, 1e-12)
    assert opened.area == pytest.approx(7552, rel=1e-12)
    assert len(opened.faces()) == 15
    sealed = shell_body(body, [], 2.0, sharp=True)
    assert volume_properties(sealed).volume == pytest.approx(15000 - 336 * 21, 1e-12)
    # Rounded keeps an r2 quarter tube: more cavity by (4 - pi) * 23 open.
    rounded = shell_body(body, _top(body), 2.0)
    gap = volume_properties(opened).volume - volume_properties(rounded).volume
    assert gap == pytest.approx((4 - 3.141592653589793) * 23, rel=1e-9)


def test_the_sharp_definition_refuses_a_rounded_cavity() -> None:
    """A rounded result has every wall at t, so the distance test alone would
    pass it: the sharp corner line is what refuses it."""
    body = _l_bracket()
    rounded = _solid(shell_body(body, _top(body), 2.0))
    fault = ShellDefinition(body, _top(body), 2.0, sharp=True).fault(rounded)
    assert fault is not None and fault.kind is FaultKind.CORNER
    assert fault.at[0] == pytest.approx(8.0) and fault.at[1] == pytest.approx(8.0)


def test_the_rounded_definition_refuses_a_sharp_cavity() -> None:
    body = _l_bracket()
    sharp = _solid(shell_body(body, _top(body), 2.0, sharp=True))
    fault = ShellDefinition(body, _top(body), 2.0).fault(sharp)
    assert fault is not None and fault.kind is FaultKind.WALL
    assert ShellDefinition(body, _top(body), 2.0, sharp=True).fault(sharp) is None


# --- a body with no concave edge is shelled as before -------------------------


def _bytes(solid: BodyShape) -> bytes:
    out = io.BytesIO()
    BinTools.Write_s(solid.wrapped, out)
    return out.getvalue()


@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize(
    "make",
    [
        lambda: Solid.make_box(40, 25, 10),
        lambda: Case("plate", 1.0, (40, 20, 10), (_cyl(20, 10, -1, 11, 5),)).body(),
    ],
    ids=["box", "through-bored-plate"],
)
def test_without_a_concave_edge_sharp_is_the_rounded_shell_byte_for_byte(
    make: Callable[[], Solid], opened: bool
) -> None:
    """Both joins build the same faces where no edge is concave, so a sharp
    shell takes the rounded route: the same bytes as before the field."""
    body = make()
    assert _concave_edge_count(body, 2.0) == 0
    faces = _top(body) if opened else []
    assert _bytes(shell_body(body, faces, 2.0, sharp=True)) == _bytes(
        shell_body(body, faces, 2.0)
    )


# --- the budget: the sharp offset is the outcome, refused past it ----------------


Call = tuple[str, float]


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    calls: list[Call] = []
    real = run_isolated

    def spy(op: str, *args: Any, **kwargs: Any) -> Any:
        calls.append((op, kwargs["cpu_seconds"]))
        return real(op, *args, **kwargs)

    monkeypatch.setattr(shell_module, "run_isolated", spy)
    return calls


def test_a_sharp_offset_runs_in_a_child_on_the_features_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two L lumps: each sharp offset in its own child, the second given what
    the first left of the one offset budget; the result's untouched faces are
    the children's copies, in the body's face order."""
    body = Compound([_l_bracket(), _l_bracket().moved(Location((300, 0, 0)))])
    calls = _spy(monkeypatch)
    history = OpHistory()
    shelled = shell_body(body, [], 2.0, sharp=True, history=history)
    assert [op for op, _cpu in calls] == [SHARP_OP, SHARP_OP]
    assert calls[0][1] == shell_module.ARC_CPU_SECONDS
    assert calls[1][1] <= shell_module.ARC_CPU_SECONDS
    assert len(shelled.solids()) == 2
    assert volume_properties(shelled).volume == pytest.approx(
        2 * (15000 - 336 * 21), rel=1e-12
    )
    worked = history.worked_on
    assert worked is not None and worked is not body
    assert [tuple(f.center()) for f in worked.faces()] == [
        tuple(f.center()) for f in body.faces()
    ]


def test_a_sharp_offset_past_its_budget_is_a_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real child, really stopped (by its wall clock here): a ShellTimeout,
    which the feature reports as shell_failed. It never falls back to Arc,
    which would ship the shape the user did not ask for."""
    body = _l_bracket()
    monkeypatch.setattr(shell_module, "ARC_WALL_SECONDS", 0.0)
    with pytest.raises(ShellTimeout) as refusal:
        shell_body(body, _top(body), 2.0, sharp=True)
    assert isinstance(refusal.value, ShellError)


def test_a_spent_budget_starts_no_sharp_child(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _l_bracket()
    monkeypatch.setattr(shell_module, "ARC_CPU_SECONDS", 0.0)
    calls = _spy(monkeypatch)
    with pytest.raises(ShellTimeout):
        shell_body(body, [], 2.0, sharp=True)
    assert calls == []


# --- the wire: stored shells stay rounded, byte for byte ----------------------


def test_a_stored_shell_reads_rounded_and_dumps_as_it_was() -> None:
    stored = {"thickness_mm": 2.0, "faces": {"kind": "faces", "refs": []}}
    params = ShellParamsV1.model_validate(stored)
    assert params.shell_type == "rounded"
    assert params.model_dump(mode="json") == stored
    sharp = ShellParamsV1.model_validate({**stored, "shell_type": "sharp"})
    assert sharp.model_dump(mode="json") == {**stored, "shell_type": "sharp"}
