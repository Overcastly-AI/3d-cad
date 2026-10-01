"""The per-dimension readouts a solved sketch payload carries.

Moved out of :mod:`geometry.sketch.planegcs_solver` unchanged (FILE-SIZE-
RATCHET, SKETCH-FILLET-KEEP-DIMS). ``SATISFIED_TOL_MM`` is that module's
constant, restated here rather than imported to keep the import one-way;
``test_sketch_virtual_sharp`` pins the two equal.
"""

import math

from geometry.sketch.angles import AngleFrame
from geometry.sketch.expression import measure_angle, measure_dimension
from geometry.sketch.schemas import (
    AngleConstraint,
    DimensionConstraint,
    SketchConstraint,
    SketchEntity,
    SolvedAngle,
    SolvedDimension,
)

#: :data:`geometry.sketch.planegcs_solver.SATISFIED_TOL_MM`.
SATISFIED_TOL_MM = 1e-7


def dimension_readouts(
    constraints: list[SketchConstraint],
    entities: list[SketchEntity],
    driving_values: dict[int, float],
) -> list[SolvedDimension]:
    """Per-dimension computed values for the solved payload.

    A driving dimension reports the value fed to the solver (evaluated
    expression / literal); a driven dimension reports the value MEASURED back
    from the solved geometry (the read-only readout that tracks the geometry it
    dimensions). One entry per dimension constraint, in input order.

    **Invariant (SOLVE-1): no readout disagrees with the ``entities`` beside it
    in the same payload by more than :data:`SATISFIED_TOL_MM`.** A driving
    dimension's requested value is therefore VERIFIED against the geometry
    before it is reported, and where it does not describe that geometry — a
    conflicting or diverged solve returns the input entities untouched, so the
    requested number is exactly the one they do not have — the MEASURED value is
    reported instead. Reporting the request unchecked is how the service came to
    claim a 12 mm dimension on an 8 mm line (docs/AUDIT-ENGINEERING.md Pass 8
    N1); nothing in the payload contradicted it.
    """
    entities_by_id = {entity.id: entity for entity in entities}
    readouts: list[SolvedDimension] = []
    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, DimensionConstraint):
            continue
        if isinstance(constraint, AngleConstraint):
            continue  # degrees — reported on `angles`, never under an `_mm` name
        measured = measure_dimension(constraint, entities_by_id)
        requested = driving_values.get(index)
        value = (
            requested
            if requested is not None and abs(measured - requested) <= SATISFIED_TOL_MM
            else measured
        )
        readouts.append(
            SolvedDimension(
                constraint_index=index,
                name=constraint.name,
                driving=constraint.is_driving,
                value_mm=value,
                expression=constraint.expression,
            )
        )
    return readouts


def angle_readouts(
    constraints: list[SketchConstraint],
    entities: list[SketchEntity],
    driving_values: dict[int, float],
    frames: dict[int, AngleFrame],
) -> list[SolvedAngle]:
    """Per-angle computed values (degrees) for the solved payload.

    The angular half of :func:`dimension_readouts`, and it carries that
    function's invariant unchanged: **no readout disagrees with the geometry
    beside it in the same payload**. A driving angle's requested value is
    VERIFIED against the solved lines before it is reported, and where it does
    not describe them the MEASURED angle is reported instead — the same rule
    that stopped the service claiming a 12 mm dimension on an 8 mm line
    (docs/AUDIT-ENGINEERING.md Pass 8 N1), applied before an angle dimension
    could ever make the equivalent claim.

    The comparison is made in DEGREES against a degree-scaled tolerance:
    :data:`SATISFIED_TOL_MM` is read on the constraint's own scale (radians for
    the angular kinds), so the readout check converts once here rather than
    letting a millimetre-named constant leak into a degree comparison.
    """
    entities_by_id = {entity.id: entity for entity in entities}
    readouts: list[SolvedAngle] = []
    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, AngleConstraint):
            continue
        frame = frames.get(index)
        measured = measure_angle(constraint, entities_by_id, frame)
        requested = driving_values.get(index)
        tolerance_deg = math.degrees(SATISFIED_TOL_MM)
        value = (
            requested
            if requested is not None and abs(measured - requested) <= tolerance_deg
            else measured
        )
        readouts.append(
            SolvedAngle(
                constraint_index=index,
                name=constraint.name,
                driving=constraint.is_driving,
                value_deg=value,
                expression=constraint.expression,
            )
        )
    return readouts
