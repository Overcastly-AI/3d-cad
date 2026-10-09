"""The boolean INTEGRITY GUARD: a boolean result that cannot be right never ships.

BOOLEAN-COINCIDENT-TUBE (docs/RESEARCH.md "Boolean integrity guard"). The moto
frame golden with its cross tubes ending flush on the rails' outer skin built
with every feature ``ok``, one ``BRepCheck``-valid lump, and 732801.92 mm^3:
more than the 725460.9 its members add up to, against an independently derived
718211.506. The defect is OCCT's: fusing an annular tube whose end face lies
TANGENT to an equal-diameter annular rail's toroidal bend, the general fuse
dropped the void shell of the sealed compartment (the tube's bore inside the
rail's bore, closed off by the tube wall and the rail's inner wall), so the
compartment came back as solid material: +7295.2 mm^3 per joint. The smallest
reproduction is two solids, a revolved annular torus segment and a straight
annular tube ending on its skin (tests/test_boolean_coincident_tube.py); two
STRAIGHT tubes do not reproduce it (64 orientations measured right).

``BRepCheck`` cannot see it: every face is well formed, the body is simply the
wrong shape. What CAN see it is arithmetic every boolean must obey. So after
every boolean the kernel ships (the ``boolean`` feature; the in-chain add / cut
that merging extrudes, revolves, sweeps, lofts and holes go through; and the
one-shot fuse / cut of a mirror, both scopes, and of a pattern,
:func:`guarded_variadic`) this module checks the result against its operands.
The sheet-metal edge flange is not guarded yet (docs/BACKLOG.md Notes).

* volume bounds: union in [max, A + sum B]; subtract in [A - sum B, A];
  intersect in [0, min], each within :data:`GUARD_REL_TOL` of the operands' scale;
* per solid, exactly ONE outer shell (positive oriented volume), every other
  shell a real void (negative), and every shell closed.

The bounds are first read on GProp's fixed-order volumes, which are cheap and
already paid for, but which read a lofted B-spline solid ~10 % off (the
freeform fixture of tests/test_rebuild_cache.py: 2984.4 against 2635.1). So a
bound that fails there is CONFIRMED on the volumes the product reports
(:func:`~geometry.kernel.properties.volume_properties`) before anything acts on
it; only that rare path pays for the adaptive integration.

A violation is first REPAIRED by re-running the same boolean with a fuzzy value
(:data:`FUZZY_RETRY_MM`), accepted only if the retry passes the same guard;
otherwise the feature is refused with :class:`BooleanIntegrityError`
(``boolean_failed``), naming the coincident contact. A body that passes on the
first attempt is returned untouched, so every body that shipped before this
guard ships byte-identical.

COST. The result's volume comes from the integration the simplification check
(:func:`~geometry.kernel.healing.clean_and_read`) already performs, and a solid
without voids has one shell whose sign is that volume's; only a solid WITH voids
integrates its shells, for their signs. The operand volumes come from the
evaluation's per-body memo
(:attr:`geometry.features.state.EvaluationState.body_volumes`), so a chain of
booleans measures each body once. Only a fresh tool (a prism, a bore) and a body
last changed by a non-boolean op are integrated here.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from build123d import Compound, Solid
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.Precision import Precision
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_ListOfShape

from geometry.kernel.healing import (
    BodyReading,
    body_is_valid,
    clean_and_read_shape,
    shape_volume,
)
from geometry.kernel.properties import volume_properties
from geometry.kernel.types import BodyShape

GuardedOperation = Literal["union", "subtract", "intersect"]


class BooleanError(RuntimeError):
    """A boolean against the body failed or left an unsupported result."""


class BooleanIntegrityError(BooleanError):
    """A boolean result broke the arithmetic every boolean obeys, and no repair held.

    A :class:`BooleanError` so every caller already maps it (``boolean_failed``)
    and the tree stops at the feature that made it, with the last good body.
    """


#: The fuzzy value of the repair retry, in mm: 100 x ``Precision::Confusion()``
#: (1e-7 mm), i.e. 1e-5 mm. Measured on the reproductions (docs/RESEARCH.md):
#: 1 x Confusion changes nothing (it IS the default); 10 x repairs the frame but
#: splits the two-solid torus reproduction into 7 lumps; 100 x repairs both, to
#: 2e-3 mm^3 of the analytic frame volume and within GProp noise of the torus
#: one; 1e-4 mm (the kernel linear tolerance, 1000 x) also repairs them but moves
#: the frame by 0.5 mm^3. Only a result that FAILED the guard is ever re-run, so
#: no body that passes is touched by it.
FUZZY_RETRY_MM = 100.0 * Precision.Confusion_s()

#: Slack of the volume bounds, RELATIVE to the operands' combined volume. A
#: bound that fails here is only a TRIGGER: it is confirmed on
#: :func:`~geometry.kernel.properties.volume_properties` (adaptive, the volume the
#: product reports) at the same slack before anything acts on it, so the slack
#: answers to that rule's accuracy, not to the cheap one's. 1e-6 keeps a lost
#: 7295 mm^3 compartment visible on bodies up to ~7e9 mm^3 (1e-4 hid it above
#: ~7e7). Over the whole geometry suite the worst excursion past a bound of a
#: right result was 1.4e-13 (cheap rule), except a lofted fixture whose cheap
#: volumes are 13 % off and which the confirmation clears; the defect broke the
#: bound by 1.1e-2.
GUARD_REL_TOL = 1e-6

#: Absolute floor under :data:`GUARD_REL_TOL`, in mm^3 (the planar golden tier).
GUARD_FLOOR_MM3 = 1e-9


@dataclass(frozen=True)
class MeasuredBody:
    """A guarded boolean's result body and its volume (for the next boolean)."""

    shape: BodyShape
    volume: float


@dataclass
class ChainVolume:
    """The volume of the body a chain of variadic booleans is at, where known.

    A mirror or pattern applies one or several variadic booleans in a row, each
    to the previous one's result. The feature seeds this with the active body's
    memoised volume (:attr:`~geometry.features.state.EvaluationState.body_volumes`,
    ``None`` when unknown), :func:`guarded_variadic` reads it as the target's
    volume instead of integrating the body again and, on success, overwrites it
    with the volume its guard measured on the result. After the chain it
    describes the body the chain returned, so the feature records it when it
    installs that body. Only a returned result writes it; a call that raises
    leaves it as it was, and so does a path that applies no boolean (the body
    it returns is the one the value describes).
    """

    volume: float | None = None


#: One run of a boolean at a fuzzy value (``None`` = the plain boolean): the
#: result body and its reading. Raises :class:`BooleanError` for a result the
#: op's own rules refuse (empty, wrong lump count).
Attempt = Callable[[float | None], tuple[BodyShape, BodyReading]]


def integrity_violation(
    operation: GuardedOperation,
    target_volume: float,
    tool_volume: float | Sequence[float],
    reading: BodyReading,
) -> str | None:
    """What makes *reading* an impossible result of the boolean, or ``None``.

    The cheap check: the shell rules, then the volume bounds on the volumes as
    given (:func:`guarded_boolean` confirms a failed bound on reported volumes).
    """
    return shell_violation(reading) or volume_violation(
        operation, target_volume, tool_volume, reading.volume
    )


def shell_violation(reading: BodyReading) -> str | None:
    """A lump without exactly one outer shell, or with an open one, or ``None``."""
    for index, solid in enumerate(reading.solids):
        shells = solid.shells
        if any(not shell.closed for shell in shells):
            return f"lump {index + 1} has an open shell"
        outer = [shell for shell in shells if shell.volume > 0]
        if len(outer) != 1:
            return (
                f"lump {index + 1} has {len(outer)} outer shells where a solid "
                "has exactly one"
            )
    return None


def volume_violation(
    operation: GuardedOperation,
    target_volume: float,
    tool_volume: float | Sequence[float],
    volume: float,
) -> str | None:
    """The bound *volume* breaks for this boolean of these operands, or ``None``.

    *tool_volume* is one tool's volume, or each tool's of a variadic boolean (a
    mirror or pattern applies several at once): union in [max of all, A + sum],
    subtract in [A - sum, A], intersect in [0, min of all].
    """
    tools = [tool_volume] if isinstance(tool_volume, float | int) else list(tool_volume)
    total = sum(tools)
    scale = abs(target_volume) + sum(abs(tool) for tool in tools)
    slack = max(GUARD_FLOOR_MM3, GUARD_REL_TOL * scale)
    if operation == "union":
        lower, upper = max(target_volume, *tools), target_volume + total
        bound = "the sum of the bodies", "the largest body"
    elif operation == "subtract":
        lower, upper = target_volume - total, target_volume
        bound = "the target body", "the target less every tool"
    else:
        lower, upper = 0.0, min(target_volume, *tools)
        bound = "the smallest body", "zero"
    if volume > upper + slack:
        return f"its volume {volume:.3f} mm^3 exceeds {bound[0]} ({upper:.3f} mm^3)"
    if volume < lower - slack:
        return f"its volume {volume:.3f} mm^3 is below {bound[1]} ({lower:.3f} mm^3)"
    return None


def fuzzy_boolean(
    target: BodyShape,
    tools: Sequence[BodyShape],
    operation: GuardedOperation,
    fuzzy: float,
) -> Compound:
    """An OCCT boolean of *target* with every tool, run with *fuzzy* (mm), serially.

    The repair path only. The plain path keeps the build123d call it always
    made, so a body that passes the guard is byte-identical to before.
    """
    if operation == "union":
        op = BRepAlgoAPI_Fuse()
    elif operation == "subtract":
        op = BRepAlgoAPI_Cut()
    else:
        op = BRepAlgoAPI_Common()
    arguments = TopTools_ListOfShape()
    arguments.Append(target.wrapped)
    tool_list = TopTools_ListOfShape()
    for tool in tools:
        tool_list.Append(tool.wrapped)
    op.SetArguments(arguments)
    op.SetTools(tool_list)
    op.SetFuzzyValue(fuzzy)
    op.SetRunParallel(False)
    op.Build()
    if not op.IsDone():
        raise BooleanError(f"Boolean {operation} failed in the kernel.")
    solids: list[Solid] = []
    walk = TopExp_Explorer(op.Shape(), TopAbs_SOLID)
    while walk.More():
        solids.append(Solid(TopoDS.Solid_s(walk.Current())))
        walk.Next()
    return Compound(solids)


def fuzzy_boolean_solids(
    target: BodyShape, tool: BodyShape, operation: GuardedOperation, fuzzy: float
) -> list[Solid]:
    """The solids of :func:`fuzzy_boolean` with one tool."""
    return list(fuzzy_boolean(target, [tool], operation, fuzzy).solids())


def guarded_boolean(
    attempt: Attempt,
    operation: GuardedOperation,
    operands: Sequence[BodyShape],
    target_volume: float,
    tool_volume: float | Sequence[float],
) -> MeasuredBody:
    """Run *attempt*, check it, repair it once with a fuzzy retry, or refuse.

    *operands* are the target then the tool(s), measured on the reported rule
    only to confirm a failed bound; *target_volume* / *tool_volume* are their
    cheap (GProp fixed-order) volumes, one per tool for a variadic boolean.
    Errors the plain attempt raises (an empty or disjoint result, a kernel
    failure) propagate unchanged: they are the op's own verdicts, not integrity
    violations.

    A violating result that ``BRepCheck`` ALSO rejects is returned as it is: the
    admission gate (:meth:`~geometry.features.state.EvaluationState._admit`)
    refuses it with ``invalid_body``, exactly as before this guard existed. The
    repair is scoped to what used to SHIP, a valid-looking wrong solid, so no
    stored part that was refused starts building. (The retry does repair many of
    those too: on the moto frame, tubes ending 0.5 to 12.6 mm past the bend's
    centreline build to within 0.08 mm^3 of the derived volume. Widening the
    scope is a product decision, docs/RESEARCH.md.)

    A repaired (fuzzy) result is checked here against the same bounds and
    shell rules only; its ``BRepCheck`` validity is asked by the admission gate
    when the feature installs it, like every other body.

    Raises:
        BooleanIntegrityError: a ``BRepCheck``-valid result violates the guard
            and the fuzzy retry either fails or violates it too.
    """
    reported: list[float] = []

    def violation_of(shape: BodyShape, reading: BodyReading) -> str | None:
        found = integrity_violation(operation, target_volume, tool_volume, reading)
        if found is None or shell_violation(reading) is not None:
            return found
        # A failed BOUND may be the fixed-order rule's error on spline faces:
        # confirm it on the volumes the product reports before acting on it.
        if not reported:
            reported.extend(volume_properties(operand).volume for operand in operands)
        volume = volume_properties(shape).volume
        return volume_violation(operation, reported[0], reported[1:], volume)

    shape, reading = attempt(None)
    violation = violation_of(shape, reading)
    if violation is None or not body_is_valid(shape):
        return MeasuredBody(shape, reading.volume)
    try:
        shape, reading = attempt(FUZZY_RETRY_MM)
    except Exception:  # any refusal of the retry means "no repair"
        pass
    else:
        if violation_of(shape, reading) is None:
            return MeasuredBody(shape, reading.volume)
    raise BooleanIntegrityError(
        f"Boolean {operation} produced a solid that cannot be right: {violation}. "
        "The two bodies meet at a coincident or tangent contact the kernel cannot "
        "resolve (for example a tube whose end face lies exactly on another "
        "tube's skin). Move that contact off tangency: end the tube inside the "
        "other body, or clear of it."
    )


def guarded_variadic(
    body: BodyShape,
    tools: Sequence[BodyShape],
    operation: GuardedOperation,
    *,
    plain: Callable[[], BodyShape],
    finish: Callable[[list[Solid]], BodyShape],
    kernel_failure: Callable[[Exception], Exception],
    refusal: Callable[[str], Exception],
    chain: ChainVolume | None = None,
) -> BodyShape:
    """:func:`guarded_boolean` for a mirror's or a pattern's one-shot boolean.

    *plain* is the op's own raw boolean (its build123d call, unchanged, so a
    passing body is byte-identical); its result is cleaned as ONE shape exactly
    as :func:`~geometry.kernel.healing.clean_shape` did, and *finish* turns the
    lumps into the body, raising the op's own errors (empty, lump count). A
    kernel exception is wrapped by *kernel_failure*, and an integrity refusal is
    raised as *refusal* of its message, so each op keeps its error taxonomy.
    *chain*, when given, supplies *body*'s volume if known and receives the
    result's (:class:`ChainVolume`).
    """

    def attempt(fuzzy: float | None) -> tuple[BodyShape, BodyReading]:
        try:
            raw = (
                plain()
                if fuzzy is None
                else fuzzy_boolean(body, tools, operation, fuzzy)
            )
            cleaned, reading = clean_and_read_shape(raw)
            solids = list(cleaned.solids())
        except Exception as exc:  # OCCT failure modes are not a stable taxonomy
            raise kernel_failure(exc) from exc
        return finish(solids), reading

    known = None if chain is None else chain.volume
    try:
        measured = guarded_boolean(
            attempt,
            operation,
            (body, *tools),
            shape_volume(body) if known is None else known,
            [shape_volume(tool) for tool in tools],
        )
    except BooleanIntegrityError as exc:
        raise refusal(str(exc)) from exc
    if chain is not None:
        chain.volume = measured.volume
    return measured.shape
