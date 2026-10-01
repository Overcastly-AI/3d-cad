"""Ordered sketch sections → ruled loft → solid → boolean against the body.

The kernel half of the loft feature (feature-tree design §4.3; BACKLOG #8) —
the second non-prismatic body-affecting feature after sweep. Where sweep
follows ONE profile along a path, a loft blends a solid THROUGH two or more
ordered cross-section sketches (the transitional-solid primitive named in the
Part-modeling scorecard notes). The feature layer hands in the *solved* sketch
entities (pydantic DTOs from :mod:`loft_wire.sketch`) of each section plus
its datum plane; this module owns every OCCT/build123d call. Failures raise the
typed exceptions below with **sanitized messages** (no kernel internals) — the
feature layer maps them 1:1 onto ``FeatureError`` codes so geometry outcomes
stay values at the boundary.

Each section is built by the SHARED :func:`geometry.kernel.extrude.
build_profile_face` (construction geometry excluded there, the single
profile-exclusion point) — its OUTER wire is the loft rail — and the
``add``/``cut`` boolean is the SHARED :func:`geometry.kernel.extrude.
combine_body`; loft owns only the section assembly and the ThruSections step.
So a loft section and an extrude profile can never disagree on how a sketch
becomes a closed wire (CLAUDE.md DRY rule).

Section contract (v1 DESIGN DECISION, docs/GEOMETRY-QA.md 2026-07-12):

* each section is a whole earlier SKETCH feature (referenced by id at the
  feature layer) — never a picked sub-edge, so loft is independent of
  topological naming (#1), exactly like sweep's profile/path slots;
* a section's non-construction entities form either a single CLOSED profile
  wire OR a single POINT (an APEX vertex). Lofting a closed section down to an
  apex point is the standard loft-to-a-point capability (a cone/pyramid tip);
  an apex may appear ONLY as the FIRST or LAST section (OCCT's own rule — a
  vertex cannot sit between two wires). This apex support was what made the
  first analytic loft golden constructible in v1 (a section-to-apex pyramid,
  whose analytic volume is the golden anchor); offset datum planes have since
  landed (df308e4), so two parallel offset circular sections — a
  cylinder/frustum — are now authorable too (the ``loft-cylinder-offset``
  golden). See GEOMETRY-QA for the full rationale.

v1 limits (stated plainly — documented scope, not bugs): a RULED (straight)
loft through the sections in list order — no guide rails, no tangency/normal
end conditions, no periodic (closed) loft, no per-section twist/alignment
control (all later, additive params — no ``param_version`` bump). Sections
are coplanar-or-parallel profiles as authored (each sketch carries its own
plane). Incompatible sections (self-intersecting rails, or a loft that OCCT
cannot skin into exactly one solid) are a kernel ``loft_failed`` rebuild
error, never a silently bad body.

Determinism (RESEARCH §9): section wires/vertices are built in the request's
section list order, and ThruSections + the boolean are pure OCCT algorithms on
identical inputs — no unordered iteration participates.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

from collections.abc import Sequence

from build123d import Face, Plane, Solid, Vertex, Wire
from loft_wire.sketch import SketchEntity, SketchPoint
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS, TopoDS_Shape

from geometry.kernel.extrude import (
    ProfileNotClosedError,
    build_profile_face,
    plane_point_to_world,
)
from geometry.kernel.healing import clean_shape
from geometry.kernel.naming import OpHistory

#: One built loft section: a closed profile wire, or an apex vertex.
LoftSection = Wire | Vertex


class LoftError(RuntimeError):
    """The OCCT loft failed or produced an unsupported result — e.g.
    incompatible sections (crossed rails), an apex placed between two wire
    sections, or a skin that is not exactly one solid."""


def build_loft_section(plane: Plane, entities: Sequence[SketchEntity]) -> LoftSection:
    """Assemble one section sketch's solved entities into a loft rail.

    Returns the section's single closed profile wire (the OUTER wire of the
    SHARED :func:`build_profile_face`, so construction geometry is excluded and
    the single-closed-loop rule is enforced exactly as for extrude), or — when
    the section's only non-construction entity is a single point — an apex
    :class:`~build123d.Vertex` at that point in world space (the loft-to-a-point
    tip). ``loft_sections`` enforces that an apex may sit only at an end.

    Raises:
        ProfileNotClosedError: the section has no profile curve and is not a
            single apex point (empty, construction-only, or multiple points),
            or its curve entities do not close into a loop.
        ProfileUnsupportedError: the section closes into more than one loop
            (single-loop sections in v1, mirroring extrude/sweep).
    """
    non_construction = [entity for entity in entities if not entity.construction]
    curves = [
        entity for entity in non_construction if not isinstance(entity, SketchPoint)
    ]
    if curves:
        # A real profile: reuse the shared builder (it re-filters construction
        # and validates the single closed loop) and take its outer boundary as
        # the loft rail. A stray point entity contributes no edge, so a
        # circle+point section is a wire section, never an apex.
        return build_profile_face(plane, entities).outer_wire()

    points = [entity for entity in non_construction if isinstance(entity, SketchPoint)]
    if len(points) == 1:
        world = plane_point_to_world(plane, points[0].position)
        return Vertex(world.X, world.Y, world.Z)

    raise ProfileNotClosedError(
        "Loft section has no profile curve and is not a single apex point "
        "(it is empty, construction-only, or has multiple points); each "
        "section must be one closed wire or one apex point."
    )


def loft_sections(
    sections: Sequence[LoftSection], history: OpHistory | None = None
) -> Solid:
    """Ruled-loft the ordered *sections* into a single solid.

    A straight (ruled) skin through the sections in list order (v1 — no guide
    rails / tangency / periodic loft). ``clean()`` collapses redundant seams so
    topology counts stay meaningful (and golden-assertable).

    *history*, when given, receives the skin's OCCT history for face naming
    (:mod:`geometry.kernel.naming`): each edge of the FIRST wire section paired
    with every side face of its column, span by span (``ThruSections``
    ``Generated`` lists them in span order), and the two caps. The skin is the
    one ``Solid.make_loft`` builds (``BRepOffsetAPI_ThruSections(True, True)``
    on the same sections, in order), kept here only so its history can be read.

    Raises:
        LoftError: an apex vertex sits between two wire sections (OCCT allows a
            vertex only at an end), the OCCT loft failed (incompatible /
            self-intersecting sections), or it produced other than exactly one
            solid (single body chain per part in v1, design §7.6).
    """
    for index, section in enumerate(sections):
        if isinstance(section, Vertex) and 0 < index < len(sections) - 1:
            raise LoftError(
                "An apex point section may only be the first or last section; "
                "a point cannot sit between two profile sections."
            )
    try:
        result = _thru_sections(sections, history)
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise LoftError(
            f"Loft failed in the kernel ({type(exc).__name__}); the sections "
            "may be incompatible (crossed rails) or cannot be skinned into one "
            "solid."
        ) from exc

    if len(solids) != 1:
        raise LoftError(
            f"Loft produced {len(solids)} solids; parts are a single body in "
            "v1 (design §7.6)."
        )
    return clean_shape(solids[0])


def _thru_sections(sections: Sequence[LoftSection], history: OpHistory | None) -> Solid:
    """``Solid.make_loft(sections, ruled=True)``, reading the history on the way.

    The same guards (build123d raises ``ValueError`` for an all-vertex loft; the
    caller maps any exception to :class:`LoftError`) and the same OCCT calls in
    the same order, so a loft built here is the loft built before naming.
    """
    if history is None:
        return Solid.make_loft(list(sections), ruled=True)
    if all(isinstance(section, Vertex) for section in sections):
        raise ValueError("A loft needs at least one profile section.")
    builder = BRepOffsetAPI_ThruSections(True, True)
    for section in sections:
        if isinstance(section, Vertex):
            builder.AddVertex(section.wrapped)
        else:
            builder.AddWire(section.wrapped)
    builder.Build()
    solid = Solid(TopoDS.Solid_s(builder.Shape()))
    first = next(section for section in sections if isinstance(section, Wire))
    for edge in first.edges():
        for produced in builder.Generated(edge.wrapped):
            history.generated.append((edge, Face(TopoDS.Face_s(produced))))
    history.start = _cap(builder.FirstShape())
    history.end = _cap(builder.LastShape())
    return solid


def _cap(shape: TopoDS_Shape) -> Face | None:
    """A ``ThruSections`` end cap, or ``None`` at an apex (a null shape)."""
    if shape.IsNull() or shape.ShapeType() != TopAbs_FACE:
        return None
    return Face(TopoDS.Face_s(shape))
