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
  original OCCT shape, which is then certainly the named face;
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
from dataclasses import dataclass, field

from build123d import Edge, Face
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

from geometry.kernel.provenance import SurfaceKey, explore_faces, surface_key
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


@dataclass(frozen=True)
class _Entry:
    face: TopoDS_Shape
    name: str | None
    key: SurfaceKey | None


def _key_of(face: TopoDS_Shape) -> SurfaceKey | None:
    return surface_key(Face(TopoDS.Face_s(face)))


class BodyNames:
    """The names of one body's faces, keyed by OCCT face identity.

    Keyed by identity (``hash`` + ``IsSame``), never by enumeration index: an
    OCCT op may rewrite a shared subshape in place, and an index-aligned list
    would then silently name the wrong face. A face this map does not hold simply
    has no name.
    """

    __slots__ = ("_by_hash", "_by_key", "_entries")

    def __init__(self, entries: Iterable[_Entry] = ()) -> None:
        self._entries: tuple[_Entry, ...] = tuple(entries)
        self._by_hash: dict[int, list[_Entry]] = {}
        self._by_key: dict[SurfaceKey, list[str | None]] = {}
        for entry in self._entries:
            self._by_hash.setdefault(hash(entry.face), []).append(entry)
            if entry.key is not None:
                self._by_key.setdefault(entry.key, []).append(entry.name)

    @classmethod
    def of_pairs(cls, pairs: Iterable[tuple[Face, str | None]]) -> "BodyNames":
        """Entries for explicit ``(face, name)`` pairs (an op's naming hook)."""
        return cls(
            _Entry(face.wrapped, name, _key_of(face.wrapped)) for face, name in pairs
        )

    def _lookup(self, face: TopoDS_Shape) -> _Entry | None:
        for entry in self._by_hash.get(hash(face), ()):
            if face.IsSame(entry.face):
                return entry
        return None

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
        than misnaming anything.
        """
        seen = explore_faces(original)
        copied = explore_faces(copy)
        if len(seen) != len(copied):
            return BodyNames()
        entries: list[_Entry] = []
        for face, twin in zip(seen, copied, strict=True):
            entry = self._lookup(face)
            if entry is not None:
                entries.append(_Entry(twin, entry.name, entry.key))
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
    2. SURFACE - the face lies on the exact supporting surface of source faces
       (the op re-bounded it: a boolean trimmed it, a fillet cut its corner);
    3. SURFACE OF A HOOK FACE - likewise against the hook's raw faces (the op's
       own result, before :func:`~geometry.kernel.healing.clean_shape`).

    A rule that finds more than one distinct value (two names, or a name and an
    unnamed face) names the face ``None``. Sources win over the hook in rule 2,
    so a base face a boss was fused onto keeps the base's name rather than the
    boss's coplanar cap's. Finally a name held by more than one face is
    withdrawn (see the module docstring).
    """
    hook = BodyNames.of_pairs(generated)
    holders = (*sources, hook)
    entries: list[_Entry] = []
    certain: list[bool] = []
    for face in explore_faces(body):
        hits = [entry for src in holders if (entry := src._lookup(face)) is not None]  # pyright: ignore[reportPrivateUsage]
        if hits:
            names = {entry.name for entry in hits}
            key = hits[0].key
        else:
            key = _key_of(face)
            names = set[str | None]()
            if key is not None:
                for src in sources:
                    names.update(src._by_key.get(key, ()))  # pyright: ignore[reportPrivateUsage]
                if not names:
                    names.update(hook._by_key.get(key, ()))  # pyright: ignore[reportPrivateUsage]
        name = next(iter(names)) if len(names) == 1 else None
        entries.append(_Entry(face, name, key))
        certain.append(bool(hits))
    return BodyNames(_withdraw_duplicates(entries, certain))


def _withdraw_duplicates(entries: list[_Entry], certain: list[bool]) -> list[_Entry]:
    """Withdraw every name more than one face holds, unless exactly one holder
    is the original OCCT face (``certain``): then the others are not it."""
    counts = Counter(entry.name for entry in entries if entry.name is not None)
    certain_holders: dict[str, list[int]] = {}
    for index, entry in enumerate(entries):
        if entry.name is not None and counts[entry.name] > 1 and certain[index]:
            certain_holders.setdefault(entry.name, []).append(index)
    out: list[_Entry] = []
    for index, entry in enumerate(entries):
        name = entry.name
        # Two certain holders would mean the history contradicts itself: none.
        if (
            name is not None
            and counts[name] > 1
            and certain_holders.get(name) != [index]
        ):
            entry = _Entry(entry.face, None, entry.key)
        out.append(entry)
    return out


def edge_names(
    body: BodyShape,
    face_names: Sequence[str | None],
    edges: Sequence[Edge] | None = None,
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
        names = [name_of(pair_of(edge.wrapped)) for edge in body.edges()]
        counts = Counter(name for name in names if name is not None)
        return [name if name is None or counts[name] == 1 else None for name in names]

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
