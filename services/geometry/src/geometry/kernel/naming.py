"""History-based face and edge names (DESIGN-INTENT-REFS, docs/RESEARCH.md).

WHY. Every stage-1 signature tier (:mod:`geometry.kernel.faces`,
:mod:`geometry.kernel.edges`) re-finds a picked face or edge by WHERE it is.
An early dimension edit moves things, and some moves no geometric invariant
survives: a 1.5 deg drafted wall that moves 5 mm along X also shifts 0.13 mm
within its own plane, so the face tiers (which pin the in-plane centroid) lose
it, and the corner edges picked against it go with it. Fusion 360, SolidWorks
and Onshape keep such picks because they name a face by HOW IT WAS MADE ("the
side Extrude1 swept from sketch line e2, tilted by Draft1"), not by where it is.
This module is that name.

WHAT A NAME IS. A face name is ``"<feature id>:<label>"``, a pure function of
the feature tree, never of a coordinate:

* an op that CREATES a face names it from what generated it (OCCT history): an
  extrude's side face from its sketch entity id (``side:e2``) and its caps
  (``start`` / ``end``); a fillet or chamfer face from the name of the edge it
  replaced;
* an op that MODIFIES a face in place (a draft tilting it) passes the face's old
  name to the new face;
* every other face KEEPS its name if the op kept it: the same OCCT shape, or
  (when the op rebuilt its boundary) the same supporting surface
  (:class:`~geometry.kernel.provenance.SurfaceKey`, compared exactly).

An edge name is the canonical pair of its two face names.

REFUSE, NEVER GUESS. A wrong name is worse than no name, because a wrong name
moves a fillet to the wrong corner with no error. So every doubt is ``None``,
and ``None`` means "use the old geometric tiers, exactly as before":

* a face two sources claim (two names on one surface, or a named and an
  unnamed face on one surface) gets no name;
* a name two faces end up holding (a face split by a cut, coplanar pattern
  copies) is withdrawn from all of them, unless exactly one holder kept the
  original OCCT shape, which is then certainly the named face; the pieces
  of a split face are instead named by their neighbours (step 2,
  :func:`_qualify_splits`), and a piece whose neighbourhood does not pin it
  stays unnamed;
* an edge whose two faces are not both named, or whose pair names more than one
  edge, gets no name;
* an op with no naming hook names the faces it creates ``None``.

DETERMINISM. Names are built from feature ids, sketch entity ids and OCCT
history, all pure functions of the tree, and the walk orders are OCCT's
deterministic explorer orders. A rebuild-cache fork re-anchors the names on the
copied body face for face (:meth:`BodyNames.fork`), so a resumed rebuild names
exactly what a cold one does (``tests/test_naming.py``).
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from build123d import Edge, Face
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepTools import BRepTools
from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCP.gp import gp_Pnt2d
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_IN,
    TopAbs_OUT,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

from geometry.kernel.provenance import SurfaceKey, explore_faces, surface_key
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape

#: A name longer than this is replaced by a digest of its label. Nested names
#: (a fillet face is named from an edge, which is named from two faces) would
#: otherwise grow with every level; 128 bits of SHA-256 keep them unique.
_MAX_NAME_CHARS = 256


def face_name(feature_id: uuid.UUID, label: str) -> str:
    """The name of a face *feature_id* created, from its generator *label*."""
    name = f"{feature_id}:{label}"
    if len(name) <= _MAX_NAME_CHARS:
        return name
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:32]
    return f"{feature_id}:#{digest}"


def edge_name(a: str, b: str) -> str:
    """The name of the edge between faces named *a* and *b* (order-free).

    JSON-encoded so that no pair of face names can spell another pair."""
    return json.dumps(sorted((a, b)), separators=(",", ":"))


#: An op's naming hook: faces of its raw result, each with its name (or ``None``).
NameHook = Sequence[tuple[Face, str | None]]


@dataclass
class OpHistory:
    """Where a kernel op's new faces came from, filled in by the op.

    ``generated`` pairs each SOURCE subshape of the op's input (a filleted edge,
    a drafted face, a profile edge) with a face of the op's raw result it
    produced. ``start`` / ``end`` are a prism's two caps. The kernel op reports
    OCCT history only; turning it into names is the feature layer's job, because
    only it knows the feature id and the sources' names.
    """

    generated: list[tuple[Edge | Face, Face]] = field(
        default_factory=list[tuple[Edge | Face, Face]]
    )
    start: Face | None = None
    end: Face | None = None


#: A free-form face's identity across an op: its supporting ``Geom_Surface``
#: OBJECT (compared by handle, never by value) and the 3x4 matrix of its
#: location. A boolean or ``clean`` that re-bounds a B-spline face keeps the very
#: same surface object, and pattern copies (which share one ``TShape`` at
#: different locations) differ in the matrix, so this tells copies apart.
GeomKey = tuple[object, tuple[float, ...]]


@dataclass(frozen=True)
class _Entry:
    face: TopoDS_Shape
    name: str | None
    key: SurfaceKey | None
    #: Set only for a face without a :class:`SurfaceKey` (free-form).
    geom: GeomKey | None = None
    #: The name before split qualification (:func:`_qualify_splits`): equal to
    #: ``name`` for an unsplit face, ``None`` exactly when ``name`` is.
    base: str | None = None


def _key_of(face: TopoDS_Shape) -> SurfaceKey | None:
    return surface_key(Face(TopoDS.Face_s(face)))


def _geom_of(face: TopoDS_Shape) -> GeomKey:
    location = TopLoc_Location()
    surface = BRep_Tool.Surface_s(TopoDS.Face_s(face), location)
    matrix = location.Transformation()
    return (
        surface,
        tuple(matrix.Value(row, col) for row in (1, 2, 3) for col in (1, 2, 3, 4)),
    )


def _entry(face: TopoDS_Shape, name: str | None, base: str | None = None) -> _Entry:
    key = _key_of(face)
    return _Entry(
        face,
        name,
        key,
        _geom_of(face) if key is None else None,
        (name if base is None else base) if name is not None else None,
    )


class BodyNames:
    """The names of one body's faces, keyed by OCCT face identity.

    Keyed by identity (``hash`` + ``IsSame``, which compares the location too,
    so two pattern copies sharing one ``TShape`` are two faces), never by
    enumeration index: an OCCT op may rewrite a shared subshape in place, and an
    index-aligned list would then silently name the wrong face. A face this map
    does not hold simply has no name.
    """

    __slots__ = ("_by_geom", "_by_hash", "_by_key", "_entries")

    def __init__(self, entries: Iterable[_Entry] = ()) -> None:
        self._entries: tuple[_Entry, ...] = tuple(entries)
        self._by_hash: dict[int, list[_Entry]] = {}
        self._by_key: dict[SurfaceKey, list[_Entry]] = {}
        self._by_geom: dict[GeomKey, list[_Entry]] = {}
        for entry in self._entries:
            self._by_hash.setdefault(hash(entry.face), []).append(entry)
            if entry.key is not None:
                self._by_key.setdefault(entry.key, []).append(entry)
            elif entry.geom is not None:
                self._by_geom.setdefault(entry.geom, []).append(entry)

    @classmethod
    def of_pairs(cls, pairs: Iterable[tuple[Face, str | None]]) -> "BodyNames":
        """Entries for explicit ``(face, name)`` pairs (an op's naming hook)."""
        return cls(_entry(face.wrapped, name) for face, name in pairs)

    def _lookup(self, face: TopoDS_Shape) -> _Entry | None:
        for entry in self._by_hash.get(hash(face), ()):
            if face.IsSame(entry.face):
                return entry
        return None

    def _on_surface(self, key: SurfaceKey | None, geom: GeomKey | None) -> list[_Entry]:
        """The entries on the same supporting surface: the same
        :class:`SurfaceKey`, or for a free-form face the same surface object at
        the same location."""
        if key is not None:
            return self._by_key.get(key, [])
        if geom is not None:
            return self._by_geom.get(geom, [])
        return []

    def name_of(self, face: Face) -> str | None:
        """The name of *face*, or ``None`` when it has none (or is not held)."""
        entry = self._lookup(face.wrapped)
        return None if entry is None else entry.name

    def face_names(self, body: BodyShape) -> list[str | None]:
        """Names aligned with ``body.faces()`` (the enumeration every resolver
        and the selection overlay walk)."""
        return [
            None if (entry := self._lookup(face)) is None else entry.name
            for face in explore_faces(body)
        ]

    def fork(self, original: BodyShape, copy: BodyShape) -> "BodyNames":
        """These names re-anchored on *copy*, a ``BRepBuilderAPI_Copy`` of
        *original* (a rebuild-cache rung).

        The copy keeps the explorer order face for face (the same alignment
        :meth:`~geometry.kernel.provenance.FaceProvenanceRecorder.fork` relies
        on). A copy that walks to a different face count is not trusted: the
        fork then holds no names, which degrades to the geometric tiers rather
        than misnaming anything. A free-form face's surface identity is read
        again on the copy (the copy has its own surface objects).
        """
        seen = explore_faces(original)
        copied = explore_faces(copy)
        if len(seen) != len(copied):
            return BodyNames()
        entries: list[_Entry] = []
        for face, twin in zip(seen, copied, strict=True):
            entry = self._lookup(face)
            if entry is not None:
                geom = None if entry.key is not None else _geom_of(twin)
                entries.append(_Entry(twin, entry.name, entry.key, geom, entry.base))
        return BodyNames(entries)


def carry_names(
    body: BodyShape,
    sources: Sequence[BodyNames],
    generated: NameHook = (),
) -> BodyNames:
    """Name every face of *body*, the result of an op on the bodies *sources*
    names, plus the faces the op's hook named in *generated*.

    Per face, the first rule that finds anything decides:

    1. IDENTITY - the face IS a face a source or the hook holds (``IsSame``);
    2. SURFACE - the face lies on the supporting surface of source faces (the op
       re-bounded it: a boolean trimmed it, a fillet cut its corner). "The same
       surface" is the exact :class:`SurfaceKey` for an analytic face, and the
       same ``Geom_Surface`` object at the same location for a free-form one (a
       loft's B-spline side, which has no analytic key);
    3. SURFACE OF A HOOK FACE - likewise against the hook's raw faces (the op's
       own result, before :func:`~geometry.kernel.healing.clean_shape`).

    When faces with DIFFERENT names share the surface (coplanar faces: a boss
    flush with its base's side, a mirrored boss whose sides lie in its
    original's planes), the face takes the name of the one claimant whose region
    contains it (:func:`_containing`: every sample point of the face inside that
    claimant and outside every other). Otherwise rules 2 and 3 stand: a rule that
    finds more than one distinct value (two names, or a name and an unnamed
    face) names the face ``None``, with one exception: names that are all pieces
    of ONE split face (:func:`_qualify_splits`) give the face that face's name,
    to be qualified again below. Sources win over the hook in rule 2, so a base
    face a boss was fused onto keeps the base's name rather than the boss's
    coplanar cap's. A face named by rule 2 or 3 that lies clear of every face
    that carried the name (disjoint bounding boxes) shares only the surface and
    is new material, so it gets no name: an op without a hook names nothing,
    even on an old face's plane. Finally :func:`_qualify_splits` settles every
    name more than one face holds.
    """
    hook = BodyNames.of_pairs(generated)
    holders = (*sources, hook)
    entries: list[_Entry] = []
    certain: list[bool] = []
    for face in explore_faces(body):
        hits = [entry for src in holders if (entry := src._lookup(face)) is not None]  # pyright: ignore[reportPrivateUsage]
        if hits:
            key, geom = hits[0].key, hits[0].geom
            name, base = _settle(hits)
        else:
            key = _key_of(face)
            geom = _geom_of(face) if key is None else None
            ours = [e for src in sources for e in src._on_surface(key, geom)]  # pyright: ignore[reportPrivateUsage]
            theirs = hook._on_surface(key, geom)  # pyright: ignore[reportPrivateUsage]
            name, base = _settle(ours or theirs)
            claimants = [*ours, *theirs]
            if len({entry.name for entry in claimants}) > 1:
                region = _containing(face, claimants)
                if region is not None:
                    name, base = region.name, region.base
            if base is not None and not _near_any(
                face, [e.face for e in claimants if e.base == base]
            ):
                # Only the surface is shared: the face lies clear of every face
                # that carried the name, so it is new material, not that face.
                name = base = None
        entries.append(_Entry(face, name, key, geom, base))
        certain.append(bool(hits))
    return BodyNames(_qualify_splits(body, entries, certain))


def _near_any(face: TopoDS_Shape, others: Sequence[TopoDS_Shape]) -> bool:
    """Whether *face*'s bounding box meets any of *others*' (kernel tolerance
    gap). Boxes are conservative, so ``False`` proves the faces are apart."""
    box = _box(face)
    return any(not box.IsOut(_box(other)) for other in others)


def _box(face: TopoDS_Shape) -> Bnd_Box:
    box = Bnd_Box()
    BRepBndLib.Add_s(face, box, False)
    box.Enlarge(_CLASSIFY_TOL)
    return box


def _containing(face: TopoDS_Shape, claimants: Sequence[_Entry]) -> _Entry | None:
    """The claimant whose face CONTAINS *face* (all on one surface), or ``None``.

    A few points strictly inside *face* are classified against each claimant's
    face: a claimant contains it when every point is IN, and is ruled out when
    every point is OUT. Any other outcome (a point ON a claimant's boundary, or
    points on both sides: *face* is a merge of several claimants) decides
    nothing, and neither do containers with different names. Doubt is ``None``.
    """
    points = _interior_points(TopoDS.Face_s(face))
    if not points:
        return None
    inside: list[_Entry] = []
    for entry in claimants:
        claimant = TopoDS.Face_s(entry.face)
        states = {
            BRepClass_FaceClassifier(claimant, point, _CLASSIFY_TOL).State()
            for point in points
        }
        if states == {TopAbs_IN}:
            inside.append(entry)
        elif states != {TopAbs_OUT}:
            return None
    return inside[0] if len({entry.name for entry in inside}) == 1 else None


#: Point-classification tolerance (mm), the kernel's linear tolerance.
_CLASSIFY_TOL = KERNEL_LINEAR_TOL_MM


def _interior_points(face: TopoDS_Shape, wanted: int = 3) -> list[object]:
    """Up to *wanted* points strictly inside *face*, from a parameter grid
    (deterministic: the grid order). Empty when no grid point lands inside."""
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    inside = BRepTopAdaptor_FClass2d(face, _CLASSIFY_TOL)
    surface = BRepAdaptor_Surface(face)
    points: list[object] = []
    for steps in (4, 16):
        for i in range(steps):
            for j in range(steps):
                u = umin + (umax - umin) * (i + 0.5) / steps
                v = vmin + (vmax - vmin) * (j + 0.5) / steps
                if inside.Perform(gp_Pnt2d(u, v)) == TopAbs_IN:
                    points.append(surface.Value(u, v))
                    if len(points) == wanted:
                        return points
        if points:
            return points
    return points


def _settle(hits: Sequence[_Entry]) -> tuple[str | None, str | None]:
    """``(name, base)`` for a face the entries *hits* claim (see
    :func:`carry_names`): one name, or one base when the claimants are all pieces
    of one split face, else nothing."""
    names = {entry.name for entry in hits}
    if len(names) == 1:
        (only,) = hits[:1]
        return only.name, only.base
    bases = {entry.base for entry in hits}
    if None in names or len(bases) != 1:
        return None, None
    (base,) = bases
    return base, base


def _qualify_splits(
    body: BodyShape, entries: list[_Entry], certain: list[bool]
) -> list[_Entry]:
    """Settle every base name more than one face holds, then withdraw any name
    still held twice.

    A base held by several faces is a face an op SPLIT (a hub cylinder the
    blades of a pattern cut into strips, a top face a slot cut in two). The base
    alone cannot say which piece is which, so step 1 withdrew it; Onshape and
    Fusion instead name each piece by what bounds it, and so does this: each
    piece is ``"<base>/<digest of its neighbours' base names>"``. The piece of
    the hub between blade 2 and blade 3 is "the hub side bounded by the caps,
    blade 2's trailing side and blade 3's leading side", whatever the hub
    diameter. A piece is left UNNAMED when any neighbour has no name (the
    neighbourhood would not pin it), and two pieces with the same neighbourhood
    are both withdrawn, so a qualified name is held by exactly one face or none.

    Exception kept from step 1: when exactly one holder IS the original OCCT face
    and still carries the plain base name, it keeps it, since the others are
    certainly not it; they are qualified as above.
    """
    by_base: dict[str, list[int]] = {}
    for index, entry in enumerate(entries):
        if entry.base is not None:
            by_base.setdefault(entry.base, []).append(index)
    shared = {base: held for base, held in by_base.items() if len(held) > 1}
    out = list(entries)
    if shared:
        neighbours = _face_neighbours(body, len(entries))
        for base, held in shared.items():
            keepers = [i for i in held if certain[i] and entries[i].name == base]
            keeper = keepers[0] if len(keepers) == 1 else None
            for index in held:
                if index == keeper:
                    continue
                around = [entries[j].base for j in neighbours[index]]
                out[index] = replace(entries[index], name=_split_name(base, around))
    counts = Counter(entry.name for entry in out if entry.name is not None)
    return [
        entry
        if entry.name is None or counts[entry.name] == 1
        else replace(entry, name=None, base=None)
        for entry in out
    ]


def _split_name(base: str, around: Sequence[str | None]) -> str | None:
    """The name of one piece of the split face *base*, from the base names of
    the faces *around* it; ``None`` if any of them is unnamed."""
    if any(name is None for name in around):
        return None
    others = sorted({name for name in around if name is not None and name != base})
    if not others:
        return None
    digest = hashlib.sha256(json.dumps(others).encode("utf-8")).hexdigest()[:32]
    return f"{base}/{digest}"


def _face_neighbours(body: BodyShape, count: int) -> list[list[int]]:
    """For each face of *body* (explorer order), the indices of the OTHER faces
    it shares an edge with (a seam edge, shared with itself, adds nothing)."""
    faces = explore_faces(body)
    if len(faces) != count:
        return [[] for _ in range(count)]
    index = TopTools_IndexedMapOfShape()
    for face in faces:
        index.Add(face)
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    around: list[set[int]] = [set() for _ in range(count)]
    for i in range(1, ancestors.Extent() + 1):
        incident = {index.FindIndex(face) - 1 for face in ancestors.FindFromIndex(i)}
        incident.discard(-1)
        for face_index in incident:
            around[face_index].update(incident - {face_index})
    return [sorted(s) for s in around]


def edge_names(
    body: BodyShape,
    face_names: Sequence[str | None],
    edges: Sequence[Edge] | None = None,
    *,
    runs: bool = False,
) -> list[str | None]:
    """Names of *edges* (default: every edge, aligned with ``body.edges()``),
    from *face_names* (aligned with ``body.faces()``).

    An edge is named only when it bounds exactly two DISTINCT faces, both named,
    and no other edge bounds the same pair (two faces meeting along two runs).
    Asking for a few edges (a fillet's, before it runs) checks that last rule
    on the two faces alone instead of naming the whole body.
    """
    faces = explore_faces(body)
    if len(faces) != len(face_names):
        return [None] * (len(body.edges()) if edges is None else len(edges))
    face_index = TopTools_IndexedMapOfShape()
    for face in faces:
        face_index.Add(face)
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)

    def pair_of(edge: TopoDS_Shape) -> tuple[int, int] | None:
        if not ancestors.Contains(edge):
            return None
        incident = list(ancestors.FindFromKey(edge))
        if len(incident) != 2 or incident[0].IsSame(incident[1]):
            return None
        a, b = (face_index.FindIndex(shape) for shape in incident)
        return (a, b) if a > 0 and b > 0 else None

    def name_of(pair: tuple[int, int] | None) -> str | None:
        if pair is None:
            return None
        a, b = face_names[pair[0] - 1], face_names[pair[1] - 1]
        return edge_name(a, b) if a is not None and b is not None and a != b else None

    if edges is None:
        all_edges = body.edges()
        pairs = [pair_of(edge.wrapped) for edge in all_edges]
        names = [name_of(pair) for pair in pairs]
        counts = Counter(name for name in names if name is not None)
        whole = {
            name
            for name, count in counts.items()
            if count > 1
            and runs
            and _one_run(
                body,
                [e for e, n in zip(all_edges, names, strict=True) if n == name],
                ancestors,
            )
        }
        return [
            name if name is None or counts[name] == 1 or name in whole else None
            for name in names
        ]

    out: list[str | None] = []
    for edge in edges:
        pair = pair_of(edge.wrapped)
        name = name_of(pair)
        if pair is not None and name is not None:
            shared = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(faces[pair[0] - 1], TopAbs_EDGE, shared)
            other = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(faces[pair[1] - 1], TopAbs_EDGE, other)
            common = sum(
                1
                for i in range(1, other.Extent() + 1)
                if shared.Contains(other.FindKey(i))
            )
            if common != 1:
                name = None
        out.append(name)
    return out


def _one_run(
    body: BodyShape,
    pieces: Sequence[Edge],
    ancestors: TopTools_IndexedDataMapOfShapeListOfShape,
) -> bool:
    """Whether *pieces* (edges between the same two faces) are ONE boundary run
    cut at vertices: a single open or closed chain, joined only at vertices
    where nothing else meets but a seam (an edge with one face on both sides).
    Two faces that meet along two separate runs (the two ends of a D-shape's
    chord) are not one run, and neither is a chain a third face touches."""
    piece_map = TopTools_IndexedMapOfShape()
    for piece in pieces:
        piece_map.Add(piece.wrapped)
    by_vertex = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_VERTEX, TopAbs_EDGE, by_vertex)
    links: dict[int, set[int]] = {i: set() for i in range(len(pieces))}
    for piece_index, piece in enumerate(pieces):
        for vertex in piece.vertices():
            if not by_vertex.Contains(vertex.wrapped):
                return False
            touching = [
                edge
                for edge in by_vertex.FindFromKey(vertex.wrapped)
                if not edge.IsSame(piece.wrapped)
            ]
            for edge in touching:
                if piece_map.Contains(edge):
                    links[piece_index].add(piece_map.FindIndex(edge) - 1)
                elif not _is_seam(edge, ancestors) and any(
                    piece_map.Contains(e) for e in touching
                ):
                    # A third face meets the chain between two pieces.
                    return False
    if any(len(linked) > 2 for linked in links.values()):
        return False
    seen, todo = {0}, [0]
    while todo:
        for nxt in links[todo.pop()] - seen:
            seen.add(nxt)
            todo.append(nxt)
    return len(seen) == len(pieces)


def _is_seam(
    edge: TopoDS_Shape, ancestors: TopTools_IndexedDataMapOfShapeListOfShape
) -> bool:
    if not ancestors.Contains(edge):
        return False
    faces = list(ancestors.FindFromKey(edge))
    return len(faces) == 2 and faces[0].IsSame(faces[1])


class ShapeNames:
    """Subshapes of an op's INPUT (edges or faces) by identity, with their
    names, so the history's sources can be named (``IsSame`` decides). Taken
    BEFORE the op runs: an OCCT op may rewrite a shared input subshape in place.
    """

    __slots__ = ("_by_hash",)

    def __init__(
        self, shapes: Sequence[Edge] | Sequence[Face], names: Sequence[str | None]
    ) -> None:
        self._by_hash: dict[int, list[tuple[TopoDS_Shape, str | None]]] = {}
        for shape, name in zip(shapes, names, strict=True):
            raw = shape.wrapped
            self._by_hash.setdefault(hash(raw), []).append((raw, name))

    def name_of(self, shape: Edge | Face) -> str | None:
        """The name of input subshape *shape*, or ``None``."""
        raw = shape.wrapped
        for candidate, name in self._by_hash.get(hash(raw), ()):
            if raw.IsSame(candidate):
                return name
        return None


def generated_names(
    feature_id: uuid.UUID, kind: str, history: OpHistory, sources: ShapeNames
) -> list[tuple[Face, str | None]]:
    """Hook names for faces an op GENERATED from named sources (fillet, chamfer).

    Each produced face is named ``"<feature id>:<kind>:<source name>"``; a face
    generated from an unnamed source is ``None``.
    """
    out: list[tuple[Face, str | None]] = []
    for source, produced in history.generated:
        name = sources.name_of(source)
        label = None if name is None else face_name(feature_id, f"{kind}:{name}")
        out.append((produced, label))
    return out


def modified_names(
    history: OpHistory, sources: ShapeNames
) -> list[tuple[Face, str | None]]:
    """Hook names for faces an op MODIFIED (draft): the source's own name."""
    return [
        (produced, sources.name_of(source)) for source, produced in history.generated
    ]


def tool_face_names(tool: BodyShape, generated: NameHook) -> list[str | None]:
    """The names of a feature's TOOL solid (aligned with ``tool.faces()``), from
    the feature's naming hook, so a ``features``-scope pattern or mirror that
    repeats the tool can name each copy's faces after the original's."""
    return carry_names(tool, [], generated).face_names(tool)


def copied_names(
    feature_id: uuid.UUID,
    label: str,
    source: BodyShape,
    names: Sequence[str | None] | None,
    copy: BodyShape,
) -> list[tuple[Face, str | None]]:
    """Hook names for *copy*, a rigid copy of *source* (a pattern instance, a
    mirror image) whose faces, in explorer order, are named *names*.

    Each face of the copy is ``"<feature id>:<label>:<source face name>"``: the
    instance (``i3``) or the reflection (``m``) plus the face it copies, so
    every copy of a face has a name of its own although pattern copies share
    one ``TShape``. A rigid copy keeps the explorer order face for face; a copy
    that does not (a different face count, or a different surface family at
    some position) gets no names rather than shifted ones.
    """
    if names is None:
        return []
    originals, copies = explore_faces(source), explore_faces(copy)
    if not len(originals) == len(copies) == len(names):
        return []
    out: list[tuple[Face, str | None]] = []
    for original, twin, name in zip(originals, copies, names, strict=True):
        twin_face = Face(TopoDS.Face_s(twin))
        if Face(TopoDS.Face_s(original)).geom_type != twin_face.geom_type:
            return []
        label_name = None if name is None else face_name(feature_id, f"{label}:{name}")
        out.append((twin_face, label_name))
    return out
