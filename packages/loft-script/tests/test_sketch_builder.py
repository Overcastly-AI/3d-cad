"""The sketch builder is the only sugar in this library, so it is the only part
that can be wrong on its own — everything else is a call to a declared route.

These tests are pure: no transport, no stack. They assert the DTOs the builder
produces, because those DTOs are what the solver sees.
"""

from __future__ import annotations

from typing import cast

import pytest
from loft.sketch import XY, Sketch, resolve_plane
from py_kit.schemas.features import DatumPlaneRef
from py_kit.schemas.sketch import (
    CoincidentConstraint,
    DiameterConstraint,
    DistanceConstraint,
    FixedConstraint,
    RadiusConstraint,
    SketchCircle,
    SketchLine,
)


def _sketch() -> Sketch:
    """A builder with no part behind it — nothing here touches the network."""
    return Sketch(cast("object", None), XY)  # type: ignore[arg-type]


# --- the rectangle ----------------------------------------------------------


def test_rect_emits_four_ccw_lines_from_the_lower_left() -> None:
    """Entity ORDER is part of the contract with the solver, not an accident.

    The sketcher emits bottom, right, top, left counter-clockwise from the
    lower-left corner (``apps/web/src/sketch/tools.ts::rectangleCorners``), and
    the rigidity set below indexes that order. A rectangle authored in a
    different order would produce a different — still correct, but different —
    constraint system, so the script and the browser would stop being the same
    input to the same solver.
    """
    sketch = _sketch()
    rect = sketch.rect(40, 25)
    lines = [cast(SketchLine, entity) for entity in sketch.entities]
    assert [line.id for line in lines] == list(rect.edges)
    corners = [(0.0, 0.0), (40.0, 0.0), (40.0, 25.0), (0.0, 25.0)]
    for index, line in enumerate(lines):
        assert (line.start.x, line.start.y) == corners[index]
        assert (line.end.x, line.end.y) == corners[(index + 1) % 4]


def test_rect_authors_the_sketchers_rigidity_set() -> None:
    """Four corner coincidences, then H/H/V/V — the set the drag authors.

    Compared against the shapes rather than a count: "9 constraints" would pass
    for nine of the wrong ones.
    """
    sketch = _sketch()
    rect = sketch.rect(40, 25, ground=False, dimension=False)
    assert len(sketch.constraints) == 8

    loop = rect.edges
    for index in range(4):
        constraint = cast(CoincidentConstraint, sketch.constraints[index])
        assert constraint.kind == "coincident"
        assert (constraint.a.entity, constraint.a.point) == (loop[index], "end")
        assert (constraint.b.entity, constraint.b.point) == (
            loop[(index + 1) % 4],
            "start",
        )

    tail = [(c.kind, getattr(c, "entity", None)) for c in sketch.constraints[4:]]
    assert tail == [
        ("horizontal", rect.bottom),
        ("horizontal", rect.top),
        ("vertical", rect.right),
        ("vertical", rect.left),
    ]


def test_rect_grounds_and_dimensions_by_default() -> None:
    """A script's rectangle should arrive fully constrained — dof 0.

    The browser reaches the same place by clicking the first corner on the
    origin (which grounds it); a script has no gesture, so the anchor is the
    default and ``ground=False`` is the opt-out.
    """
    sketch = _sketch()
    rect = sketch.rect(40, 25)
    assert len(sketch.constraints) == 11  # 8 rigidity + 1 anchor + 2 dimensions

    anchor = cast(FixedConstraint, sketch.constraints[8])
    assert anchor.kind == "fixed"
    assert (anchor.point.entity, anchor.point.point) == (rect.bottom, "start")

    width = cast(DistanceConstraint, sketch.constraints[9])
    height = cast(DistanceConstraint, sketch.constraints[10])
    assert (width.kind, width.entity, width.value_mm) == ("distance", rect.bottom, 40)
    assert (height.kind, height.entity, height.value_mm) == ("distance", rect.right, 25)
    assert width.driving is True


def test_rect_centered_places_the_middle_at_the_given_point() -> None:
    sketch = _sketch()
    sketch.rect(40, 20, at=(10, 10), center=True)
    first = cast(SketchLine, sketch.entities[0])
    assert (first.start.x, first.start.y) == (-10.0, 0.0)
    third = cast(SketchLine, sketch.entities[2])
    assert (third.start.x, third.start.y) == (30.0, 20.0)


# --- circles ----------------------------------------------------------------


def test_circle_by_diameter_stores_the_radius_and_dimensions_by_diameter() -> None:
    """A hole is specified by diameter everywhere an engineer reads a number.

    The wire stores a radius (``SketchCircle.radius``), so the halving happens
    once, here, and the DRIVING dimension stays a ``diameter`` — otherwise the
    number in the script and the number on a drawing would differ by 2x.
    """
    sketch = _sketch()
    entity_id = sketch.circle((5, 5), diameter=8)
    circle = cast(SketchCircle, sketch.entities[0])
    assert circle.radius == 4.0
    dimension = cast(DiameterConstraint, sketch.constraints[0])
    assert dimension.kind == "diameter"
    assert dimension.entity == entity_id
    assert dimension.value_mm == 8.0


def test_circle_by_radius_dimensions_by_radius() -> None:
    sketch = _sketch()
    sketch.circle((0, 0), radius=3)
    dimension = cast(RadiusConstraint, sketch.constraints[0])
    assert (dimension.kind, dimension.value_mm) == ("radius", 3.0)


def test_circle_refuses_both_or_neither_size() -> None:
    sketch = _sketch()
    with pytest.raises(ValueError, match="exactly one"):
        sketch.circle((0, 0))
    with pytest.raises(ValueError, match="exactly one"):
        sketch.circle((0, 0), radius=1, diameter=2)


def test_a_non_positive_radius_is_refused_by_the_dto() -> None:
    """The schema's own ``gt=0`` — proof the builder does not route around it."""
    sketch = _sketch()
    with pytest.raises(ValueError):
        sketch.circle((0, 0), radius=0)


# --- ids, expressions, planes ----------------------------------------------


def test_entity_ids_follow_the_sketchers_scheme_and_never_collide() -> None:
    sketch = _sketch()
    sketch.rect(10, 10)
    assert [entity.id for entity in sketch.entities] == ["e1", "e2", "e3", "e4"]
    assert sketch.line((0, 0), (1, 1)) == "e5"


def test_a_dimension_can_be_an_expression_over_a_named_dimension() -> None:
    """The parametric half: ``height = width / 2`` as an engineer would write it."""
    sketch = _sketch()
    rect = sketch.rect(40, 25, dimension=False)
    sketch.distance(rect.bottom, 40, name="width")
    sketch.distance(rect.right, 20, expression="width/2")
    height = cast(DistanceConstraint, sketch.constraints[-1])
    assert height.expression == "width/2"
    # The params model validates dimension-name uniqueness across siblings.
    assert sketch.params().constraints[-1] is height


def test_resolve_plane_accepts_the_three_origin_planes_and_names_them_on_error() -> (
    None
):
    assert resolve_plane("XY") == DatumPlaneRef(kind="datum_plane", plane="XY")
    assert resolve_plane(XY) is XY
    with pytest.raises(ValueError, match=r"XY.*XZ.*YZ"):
        resolve_plane("xy")


def test_duplicate_entity_ids_are_refused_by_the_params_model() -> None:
    """The escape hatch does not escape validation."""
    from py_kit.schemas.sketch import SketchPoint

    sketch = _sketch()
    sketch.point((0, 0))
    sketch.add(
        SketchPoint(id="e1", kind="point", position=sketch.entities[0].position)  # type: ignore[attr-defined]
    )
    with pytest.raises(ValueError, match="Duplicate sketch entity id"):
        sketch.params()
