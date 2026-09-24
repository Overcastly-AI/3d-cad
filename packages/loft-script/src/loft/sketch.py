"""The sketch builder — the one place this library is *sugar* rather than plumbing.

A sketch is the only part of the modelling surface where the wire format is
genuinely awkward to type by hand: a rectangle is four line entities, four
corner coincidences, two horizontals, two verticals and two driving dimensions,
and every one of them refers to entities by generated id. The browser hides
that behind a drag; a script needs something equivalent, or it is not a
scripting API, it is ``curl`` with extra imports.

So :meth:`Sketch.rect` authors exactly what the sketcher authors on a drag —
see the RIGIDITY note on that method — while :meth:`Sketch.add` /
:meth:`Sketch.constrain` stay open underneath for anything the sugar does not
cover. Nothing here computes geometry: entities carry their drawn positions and
the SERVER solves. That is the boundary this whole package exists to respect.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, NamedTuple

from loft_wire.features import (
    DatumPlaneRef,
    FeatureRef,
    GeomRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.sketch import (
    CoincidentConstraint,
    ConcentricConstraint,
    DiameterConstraint,
    DistanceConstraint,
    EntityPointRef,
    EqualConstraint,
    FixedConstraint,
    HorizontalConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    Point2D,
    PointName,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SolvedSketch,
    TangentConstraint,
    VerticalConstraint,
)

from loft.errors import SketchNotSolved

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to the checker
    from loft.part import Part

__all__ = ["XY", "XZ", "YZ", "Rect", "Sketch"]

#: A 2D point as a script writes it: ``(40, 25)`` or ``Point2D(x=40, y=25)``.
PointLike = tuple[float, float] | Point2D

#: The three origin datum planes, ready to pass to :meth:`loft.Part.sketch`.
XY = DatumPlaneRef(kind="datum_plane", plane="XY")
XZ = DatumPlaneRef(kind="datum_plane", plane="XZ")
YZ = DatumPlaneRef(kind="datum_plane", plane="YZ")

_ORIGIN_PLANES: dict[str, DatumPlaneRef] = {"XY": XY, "XZ": XZ, "YZ": YZ}

#: Solver outcomes that count as SOLVED — the same set the workspace uses to
#: enable extrude. ``overconstrained`` is included because a redundant-but-
#: consistent sketch still returns usable geometry (py_kit SketchSolveStatus);
#: ``conflicting`` and ``diverged`` do not, and are a refusal.
SOLVED_STATUSES = frozenset({"converged", "underconstrained", "overconstrained"})


def as_point(value: PointLike) -> Point2D:
    """Accept either a tuple or a DTO, store the DTO."""
    if isinstance(value, Point2D):
        return value
    x, y = value
    return Point2D(x=float(x), y=float(y))


class Rect(NamedTuple):
    """The four edge ids of a rectangle, named by side.

    Returned so a caller can keep constraining it — ``sketch.distance(r.top,
    40)``, ``sketch.equal(r.left, r.right)`` — without having to know how the
    ids were generated.
    """

    bottom: str
    right: str
    top: str
    left: str

    @property
    def edges(self) -> tuple[str, str, str, str]:
        """All four edge ids, counter-clockwise from the bottom."""
        return (self.bottom, self.right, self.top, self.left)


class Sketch:
    """A sketch being authored, and (once saved) the feature that holds it.

    Buffered locally until :meth:`save`, exactly like the sketcher's own draft:
    a script builds a whole profile and persists it once, rather than issuing a
    round trip per line. ``feature_id`` is ``None`` until then, and is the
    stable handle afterwards — :meth:`loft.Part.sketch_by_id` rebuilds this
    object from it alone, so an agent holding only an id has lost nothing.
    """

    def __init__(
        self,
        part: Part,
        plane: GeomRef,
        *,
        name: str = "Sketch",
        feature_id: uuid.UUID | None = None,
        entities: Sequence[SketchEntity] = (),
        constraints: Sequence[SketchConstraint] = (),
    ) -> None:
        self.part = part
        self.plane = plane
        self.name = name
        self.feature_id = feature_id
        self.entities: list[SketchEntity] = list(entities)
        self.constraints: list[SketchConstraint] = list(constraints)
        self._solved: SolvedSketch | None = None
        self._next_id = len(self.entities) + 1

    def __repr__(self) -> str:
        return (
            f"Sketch(name={self.name!r}, entities={len(self.entities)}, "
            f"constraints={len(self.constraints)}, saved={self.feature_id is not None})"
        )

    # -- identity ----------------------------------------------------------

    @property
    def id(self) -> uuid.UUID:
        """The sketch feature's id. Saves first if it has never been persisted."""
        if self.feature_id is None:
            self.save()
        assert self.feature_id is not None
        return self.feature_id

    @property
    def solved(self) -> SolvedSketch | None:
        """The last solve result, or ``None`` if it has not been solved yet."""
        return self._solved

    # -- entities ----------------------------------------------------------

    def _new_id(self) -> str:
        """``e1``, ``e2``, ... — the sketcher's own id scheme, so a sketch
        authored here is indistinguishable from one drawn in the browser."""
        while True:
            candidate = f"e{self._next_id}"
            self._next_id += 1
            if all(entity.id != candidate for entity in self.entities):
                return candidate

    def add(self, entity: SketchEntity) -> str:
        """Append a raw entity DTO; returns its id. The escape hatch under the sugar."""
        self.entities.append(entity)
        self._solved = None
        return entity.id

    def constrain(self, constraint: SketchConstraint) -> int:
        """Append a raw constraint DTO; returns its INDEX.

        The index, not an id, because that is the space the solver reports
        conflicts in (``SolvedSketch.conflicting_constraints``) — so a caller
        can map a refusal straight back to the line that caused it.
        """
        self.constraints.append(constraint)
        self._solved = None
        return len(self.constraints) - 1

    def point(self, at: PointLike, *, construction: bool = False) -> str:
        """A free point — an anchor, an arc centre to snap to, a datum stand-in."""
        return self.add(
            SketchPoint(
                id=self._new_id(),
                kind="point",
                position=as_point(at),
                construction=construction,
            )
        )

    def line(
        self, start: PointLike, end: PointLike, *, construction: bool = False
    ) -> str:
        """A line segment."""
        return self.add(
            SketchLine(
                id=self._new_id(),
                kind="line",
                start=as_point(start),
                end=as_point(end),
                construction=construction,
            )
        )

    def circle(
        self,
        center: PointLike,
        *,
        radius: float | None = None,
        diameter: float | None = None,
        construction: bool = False,
        dimension: bool = True,
    ) -> str:
        """A circle, sized by ``radius`` OR ``diameter`` (exactly one).

        ``diameter`` is offered and preferred for a reason: holes are specified
        by diameter on every drawing, fastener table and drill chart, so a
        scripting API that only took a radius would make an engineer halve every
        number they were given (the same argument
        :class:`~loft_wire.sketch.DiameterConstraint` exists for). When
        ``dimension`` is true the size also becomes a DRIVING dimension of the
        kind that matches how it was given, so the number in the script is the
        number in the model rather than a starting guess.
        """
        if (radius is None) == (diameter is None):
            raise ValueError("give exactly one of radius= or diameter=")
        value = radius if radius is not None else (diameter or 0.0) / 2.0
        entity_id = self.add(
            SketchCircle(
                id=self._new_id(),
                kind="circle",
                center=as_point(center),
                radius=value,
                construction=construction,
            )
        )
        if dimension:
            if diameter is not None:
                self.diameter(entity_id, diameter)
            elif radius is not None:
                self.radius(entity_id, radius)
        return entity_id

    def arc(self, center: PointLike, start: PointLike, end: PointLike) -> str:
        """A circular arc, counter-clockwise from ``start`` to ``end``."""
        return self.add(
            SketchArc(
                id=self._new_id(),
                kind="arc",
                center=as_point(center),
                start=as_point(start),
                end=as_point(end),
            )
        )

    def rect(
        self,
        width: float,
        height: float,
        *,
        at: PointLike = (0.0, 0.0),
        center: bool = False,
        dimension: bool = True,
        ground: bool = True,
    ) -> Rect:
        """A dimensioned rectangle: four CCW lines, held rigid, sized by
        driving dimensions.

        **The rigidity set is the sketcher's, not an invention here.** Four
        corner coincidences (``end`` of each edge onto ``start`` of the next),
        horizontal on the two horizontal edges, vertical on the two vertical
        ones — byte for byte what ``apps/web/src/sketch/drawDimensions.ts``
        authors the moment a rectangle is dragged out, in the same order, over
        entities emitted in the same order (bottom, right, top, left, CCW from
        the lower-left corner). That is not a coincidence worth admiring: a
        rectangle that arrives held together is the difference between retyping
        a width and watching the shape shear, and duplicating the *wrong* set
        here would give scripts a subtly different solver system from the one
        the UI produces.

        ``dimension`` adds the two driving dimensions (width on the bottom
        edge, height on the right) — the pair the user types in the browser.
        ``ground`` anchors the lower-left corner where it was drawn, which takes
        the sketch to zero degrees of freedom; without it the profile solves but
        floats, and reports ``underconstrained``. Pass ``ground=False`` when the
        rectangle is to be located by constraints of your own.
        """
        origin = as_point(at)
        x0 = origin.x - width / 2.0 if center else origin.x
        y0 = origin.y - height / 2.0 if center else origin.y
        x1, y1 = x0 + width, y0 + height
        corners = [
            Point2D(x=x0, y=y0),
            Point2D(x=x1, y=y0),
            Point2D(x=x1, y=y1),
            Point2D(x=x0, y=y1),
        ]
        ids = [
            self.line(corners[i], corners[(i + 1) % 4], construction=False)
            for i in range(4)
        ]
        rect = Rect(bottom=ids[0], right=ids[1], top=ids[2], left=ids[3])

        for index, entity_id in enumerate(rect.edges):
            self.coincident((entity_id, "end"), (rect.edges[(index + 1) % 4], "start"))
        self.horizontal(rect.bottom)
        self.horizontal(rect.top)
        self.vertical(rect.right)
        self.vertical(rect.left)

        if ground:
            self.fixed((rect.bottom, "start"))
        if dimension:
            self.distance(rect.bottom, width)
            self.distance(rect.right, height)
        return rect

    # -- constraints -------------------------------------------------------

    @staticmethod
    def _ref(value: tuple[str, PointName] | EntityPointRef) -> EntityPointRef:
        if isinstance(value, EntityPointRef):
            return value
        entity, point = value
        return EntityPointRef(entity=entity, point=point)

    def coincident(
        self,
        a: tuple[str, PointName] | EntityPointRef,
        b: tuple[str, PointName] | EntityPointRef,
    ) -> int:
        """Two named points share a location.

        ``sketch.coincident((e1, "end"), (e2, "start"))``
        """
        return self.constrain(
            CoincidentConstraint(kind="coincident", a=self._ref(a), b=self._ref(b))
        )

    def horizontal(self, entity: str) -> int:
        """A line is parallel to the sketch X axis."""
        return self.constrain(HorizontalConstraint(kind="horizontal", entity=entity))

    def vertical(self, entity: str) -> int:
        """A line is parallel to the sketch Y axis."""
        return self.constrain(VerticalConstraint(kind="vertical", entity=entity))

    def fixed(self, point: tuple[str, PointName] | EntityPointRef) -> int:
        """Anchor a named point where it currently sits."""
        return self.constrain(FixedConstraint(kind="fixed", point=self._ref(point)))

    def parallel(self, a: str, b: str) -> int:
        """Two lines have equal direction."""
        return self.constrain(ParallelConstraint(kind="parallel", a=a, b=b))

    def perpendicular(self, a: str, b: str) -> int:
        """Two lines meet at a right angle."""
        return self.constrain(PerpendicularConstraint(kind="perpendicular", a=a, b=b))

    def tangent(self, a: str, b: str) -> int:
        """A line/arc and an arc/circle touch without crossing."""
        return self.constrain(TangentConstraint(kind="tangent", a=a, b=b))

    def equal(self, a: str, b: str) -> int:
        """Two entities have equal length (lines) or radius (arcs/circles)."""
        return self.constrain(EqualConstraint(kind="equal", a=a, b=b))

    def concentric(self, a: str, b: str) -> int:
        """Two arcs/circles share a centre."""
        return self.constrain(ConcentricConstraint(kind="concentric", a=a, b=b))

    def distance(
        self,
        entity: str,
        value_mm: float,
        *,
        name: str | None = None,
        expression: str | None = None,
        driving: bool = True,
    ) -> int:
        """Dimension the LENGTH of a line (mm).

        ``expression`` makes the dimension a formula over other dimensions'
        ``name``s (``height`` carrying ``expression="width/2"``), which is the
        parametric half of the sketcher and costs nothing extra to expose here.
        """
        return self.constrain(
            DistanceConstraint(
                kind="distance",
                entity=entity,
                value_mm=value_mm,
                name=name,
                expression=expression,
                driving=driving,
            )
        )

    def radius(
        self,
        entity: str,
        value_mm: float,
        *,
        name: str | None = None,
        expression: str | None = None,
        driving: bool = True,
    ) -> int:
        """Dimension the radius of a circle or arc (mm)."""
        return self.constrain(
            RadiusConstraint(
                kind="radius",
                entity=entity,
                value_mm=value_mm,
                name=name,
                expression=expression,
                driving=driving,
            )
        )

    def diameter(
        self,
        entity: str,
        value_mm: float,
        *,
        name: str | None = None,
        expression: str | None = None,
        driving: bool = True,
    ) -> int:
        """Dimension the DIAMETER of a circle or arc (mm)."""
        return self.constrain(
            DiameterConstraint(
                kind="diameter",
                entity=entity,
                value_mm=value_mm,
                name=name,
                expression=expression,
                driving=driving,
            )
        )

    # -- persistence + solve ----------------------------------------------

    def params(self) -> SketchParamsV1:
        """The sketch as the wire DTO — solver input and stored params in one."""
        return SketchParamsV1(
            plane=self.plane, entities=self.entities, constraints=self.constraints
        )

    def feature(self) -> SketchFeature:
        """The ``{type, version, params}`` envelope the tree stores."""
        return SketchFeature(type="sketch", version=1, params=self.params())

    def save(self) -> Sketch:
        """Persist the sketch and solve it, exactly as closing the sketcher does.

        The browser's "save" is one gesture with two effects — the feature is
        written, and the tree evaluates so the sketch comes back solved — and
        this is the same gesture, for the same reason: a saved-but-unsolved
        sketch is a state no user can reach, so a scripting API that could
        reach it would be offering a path the product does not have.

        Idempotent in the useful direction: creates on first call, PATCHes the
        whole param envelope afterwards (the re-save of the live parametric
        loop).
        """
        if self.feature_id is None:
            created = self.part.create_feature(self.name, self.feature())
            self.feature_id = created.feature.id
            self.name = created.feature.name
        else:
            self.part.update_feature(self.feature_id, feature=self.feature())
        self.solve()
        return self

    def solve(self) -> SolvedSketch:
        """Evaluate the part and return THIS sketch's solved geometry.

        Raises :class:`~loft.errors.SketchNotSolved` when the solver could not
        satisfy the constraints — the state in which the workspace leaves
        extrude disabled. Returning a ``conflicting`` result as an ordinary
        value would be the library succeeding where the UI stops you.
        """
        if self.feature_id is None:
            self.save()
            assert self._solved is not None
            return self._solved
        evaluation = self.part.evaluate()
        result = evaluation.feature(self.feature_id)
        if result is not None and result.status == "error" and result.error is not None:
            # A CONTRADICTORY sketch is a feature ERROR carrying a typed
            # diagnosis, not a solved payload with a `conflicting` status — the
            # solved-payload route only ever reports the redundant-but-solvable
            # kind (``SolvedSketchData.diagnosis``), because an unsolvable
            # system has no geometry to return. Measured the first time this
            # test ran: two contradictory dimensions came back as
            # `sketch_conflicting` with `sketch_diagnosis.conflicting_constraints
            # = [9, 11]`, which is strictly MORE than a generic failure — so
            # lift it into the typed refusal instead of letting it surface as an
            # anonymous FeatureFailed.
            diagnosis = result.error.sketch_diagnosis
            if diagnosis is not None:
                raise SketchNotSolved(
                    result.error.message,
                    code=result.error.code,
                    solve_status="conflicting",
                    conflicting_constraints=tuple(diagnosis.conflicting_constraints),
                    redundant_constraints=tuple(diagnosis.redundant_constraints),
                    details={
                        "feature_id": str(self.feature_id),
                        "removable": diagnosis.removable,
                    },
                )
        solved = evaluation.sketch_data(self.feature_id)
        if solved is None:
            # Any other error (or a skip because an earlier feature failed)
            # surfaces with ITS own code rather than a generic "not solved".
            evaluation.raise_for_feature(self.feature_id)
            raise SketchNotSolved(
                f"the evaluate returned no solved geometry for sketch {self.name!r}",
                solve_status="unknown",
                details={"feature_id": str(self.feature_id)},
            )
        if solved.status not in SOLVED_STATUSES:
            raise SketchNotSolved(
                f"sketch {self.name!r} did not solve ({solved.status})",
                solve_status=solved.status,
                conflicting_constraints=tuple(solved.conflicting_constraints),
                redundant_constraints=tuple(solved.redundant_constraints),
                details={
                    "feature_id": str(self.feature_id),
                    "dof": solved.dof,
                },
            )
        self._solved = solved
        # The solver may have MOVED the geometry to satisfy the constraints, and
        # the authored positions are also the next solve's starting guess — so
        # keep the solved positions, exactly as the sketcher's buffer does.
        # Without this a second save would re-send the pre-solve guess and ask
        # the solver to do the same work from further away.
        self.entities = list(solved.entities)
        return solved

    def ref(self) -> FeatureRef:
        """A :class:`~loft_wire.features.FeatureRef` to this sketch feature."""
        return FeatureRef(kind="feature", feature_id=self.id)


def resolve_plane(plane: GeomRef | Literal["XY", "XZ", "YZ"] | str) -> GeomRef:
    """``"XY"`` -> the origin datum ref; a ``GeomRef`` passes through.

    The string form is the one a script actually types, and it is checked here
    rather than at the server: ``on="xy"`` should be a ``ValueError`` naming the
    three planes, not a 422 from two services away.
    """
    if isinstance(plane, str):
        try:
            return _ORIGIN_PLANES[plane]
        except KeyError:
            raise ValueError(
                f"unknown origin plane {plane!r}; expected one of "
                f"{sorted(_ORIGIN_PLANES)} (or a datum feature's ref)"
            ) from None
    return plane
