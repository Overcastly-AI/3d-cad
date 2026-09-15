"""Parts, features and evaluation results — the verbs a script spends its day in.

Every method here is a gateway call named out of the generated operation table.
Nothing computes geometry, nothing touches a database, nothing imports a kernel;
the part you model from a script is built by the same three services, in the
same order, as the part you model in the browser.

State, and why there is so little of it
---------------------------------------
A :class:`Part` holds an id and a CACHED ``tree_version`` — and the cache is an
optimisation, never a requirement. Every write sends the version it last saw as
``expected_tree_version``; if the document moved underneath (another script, a
collaborator, a browser tab), the gateway answers ``stale_tree_version`` and
:meth:`Part._write` refetches and retries exactly once. So an agent that
constructs ``session.part(id)`` fresh for every tool call is never wrong, merely
one HTTP request slower — which is the property an MCP server needs and the
reason the retry is here rather than in a caller.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

from loft_wire.features import (
    EvaluateTreeResult,
    ExtrudeFeature,
    ExtrudeParamsV1,
    Feature,
    FeatureCreate,
    FeatureMutationResponse,
    FeatureRef,
    FeatureResponse,
    FeatureResult,
    FeatureTreeResponse,
    FeatureUpdate,
    GeomRef,
    SketchFeature,
    SolvedSketchData,
)
from loft_wire.geometry import ExportFormat, ShapeProperties
from loft_wire.parts import PartCreate, PartListResponse, PartResponse, PartUpdate
from loft_wire.units import LengthUnit

from loft import _operations as ops
from loft.errors import FeatureFailed, NoBody, StaleDocument
from loft.sketch import Sketch, resolve_plane

if TYPE_CHECKING:  # pragma: no cover
    from loft.session import Session

__all__ = ["EXPORT_SUFFIXES", "Evaluation", "Part"]

WriteT = TypeVar("WriteT")

#: File suffix -> export format, so ``part.export("bracket.step")`` needs no
#: second argument. The formats are the contract's own
#: :data:`~loft_wire.geometry.ExportFormat` literals; ``.gltf`` is absent
#: deliberately (the gateway emits BINARY glTF, whose suffix is ``.glb``, and a
#: ``.gltf`` file containing GLB bytes is a file no viewer will open).
EXPORT_SUFFIXES: dict[str, ExportFormat] = {
    ".step": "step",
    ".stp": "step",
    ".stl": "stl",
    ".3mf": "3mf",
    ".glb": "glb",
}


class Evaluation:
    """The result of rebuilding a part — statuses, mass properties, provenance.

    Wraps :class:`~loft_wire.features.EvaluateTreeResult` rather than
    replacing it: ``evaluation.result`` is the untouched DTO, and everything
    here is a question a script actually asks of it.
    """

    def __init__(self, result: EvaluateTreeResult) -> None:
        self.result = result

    def __repr__(self) -> str:
        properties = self.result.properties
        volume = properties.volume if properties else None
        return (
            f"Evaluation(ok={self.ok}, features={len(self.result.features)}, "
            f"volume={volume})"
        )

    @property
    def ok(self) -> bool:
        """True when no feature errored. Says nothing about whether a body exists."""
        return all(f.status != "error" for f in self.result.features)

    @property
    def properties(self) -> ShapeProperties | None:
        """Mass properties of the last-good body, or ``None`` for a bodiless tree."""
        return self.result.properties

    @property
    def tree_version(self) -> int:
        """The tree version this result was BUILT FROM (its provenance)."""
        return self.result.tree_version

    def feature(self, feature_id: uuid.UUID) -> FeatureResult | None:
        """The per-feature status for one feature, if it was in the evaluation."""
        return next(
            (f for f in self.result.features if f.feature_id == feature_id), None
        )

    def sketch_data(self, feature_id: uuid.UUID) -> SolvedSketchData | None:
        """The solved-sketch payload a sketch feature returned, if any."""
        entry = self.feature(feature_id)
        if entry is None or entry.data is None:
            return None
        return entry.data

    def raise_for_features(self) -> Evaluation:
        """Raise :class:`~loft.errors.FeatureFailed` for the first errored feature.

        The strict-prefix rule means there is only ever one genuine failure: the
        first error, with every later feature ``skipped``. So raising on the
        first one names the cause rather than a consequence.
        """
        for entry in self.result.features:
            if entry.status == "error":
                raise _feature_error(entry)
        return self

    def raise_for_feature(self, feature_id: uuid.UUID) -> None:
        """Raise if ONE named feature errored (or was skipped because an
        earlier one did)."""
        entry = self.feature(feature_id)
        if entry is not None and entry.status == "error":
            raise _feature_error(entry)
        if entry is not None and entry.status == "skipped":
            self.raise_for_features()


def _feature_error(entry: FeatureResult) -> FeatureFailed:
    """Turn a per-feature error status into a typed, coded exception."""
    error = entry.error
    return FeatureFailed(
        error.message if error else "the feature failed to evaluate",
        code=error.code if error else None,
        feature_id=str(entry.feature_id),
        details=error.model_dump(mode="json") if error else None,
    )


class Part:
    """One part document: its tree, its evaluation, its exports."""

    def __init__(
        self, session: Session, part_id: uuid.UUID, *, tree_version: int | None = None
    ) -> None:
        self.session = session
        self.id = part_id
        self._tree_version = tree_version

    def __repr__(self) -> str:
        return f"Part(id={self.id})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Part) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    # -- identity / header -------------------------------------------------

    def refresh(self) -> PartResponse:
        """Fetch the part header (name, unit, material, rebuild health)."""
        record = self.session.transport.call(
            ops.GET_PARTS_PART_ID, PartResponse, path_params={"part_id": self.id}
        )
        self._tree_version = record.tree_version
        return record

    @property
    def name(self) -> str:
        """The part's name, as the register shows it."""
        return self.refresh().name

    @property
    def tree_version(self) -> int:
        """The current optimistic-concurrency token, fetched if not already known."""
        if self._tree_version is None:
            self.refresh()
        assert self._tree_version is not None
        return self._tree_version

    def rename(self, name: str) -> PartResponse:
        """Rename the part."""
        return self._write(
            lambda version: self.session.transport.call(
                ops.PATCH_PARTS_PART_ID,
                PartResponse,
                path_params={"part_id": self.id},
                body=PartUpdate(name=name, expected_tree_version=version),
            ),
            after=lambda record: record.tree_version,
        )

    def set_units(self, unit: LengthUnit) -> PartResponse:
        """Change the DISPLAY unit. Metadata only — storage stays canonical mm."""
        return self._write(
            lambda version: self.session.transport.call(
                ops.PATCH_PARTS_PART_ID,
                PartResponse,
                path_params={"part_id": self.id},
                body=PartUpdate(length_unit=unit, expected_tree_version=version),
            ),
            after=lambda record: record.tree_version,
        )

    def delete(self) -> None:
        """Delete the part."""
        self.session.transport.call_none(
            ops.DELETE_PARTS_PART_ID, path_params={"part_id": self.id}
        )

    # -- optimistic concurrency -------------------------------------------

    def _write(
        self, send: Callable[[int], WriteT], *, after: Callable[[WriteT], int]
    ) -> WriteT:
        """Run a versioned write, refetching and retrying ONCE on a stale version.

        Once, not forever: a second loss means a genuinely concurrent editor,
        and silently re-applying a write against whatever they just did is how a
        script overwrites a person. The second failure reaches the caller as
        :class:`~loft.errors.StaleDocument`, which names the remedy.
        """
        try:
            result = send(self.tree_version)
        except StaleDocument:
            self.refresh()
            result = send(self.tree_version)
        self._tree_version = after(result)
        return result

    # -- feature tree ------------------------------------------------------

    def tree(self) -> FeatureTreeResponse:
        """The ordered feature tree plus its concurrency token."""
        tree = self.session.transport.call(
            ops.GET_PARTS_PART_ID_FEATURES,
            FeatureTreeResponse,
            path_params={"part_id": self.id},
        )
        self._tree_version = tree.tree_version
        return tree

    def features(self) -> list[FeatureResponse]:
        """The features, in evaluation order."""
        return self.tree().features

    def feature(self, feature_id: uuid.UUID) -> FeatureResponse:
        """One feature of this part."""
        return self.session.transport.call(
            ops.GET_PARTS_PART_ID_FEATURES_FEATURE_ID,
            FeatureResponse,
            path_params={"part_id": self.id, "feature_id": feature_id},
        )

    def create_feature(self, name: str, feature: Feature) -> FeatureMutationResponse:
        """Append any feature envelope the contract declares — the escape hatch.

        The typed verbs (:meth:`extrude`, :meth:`sketch`) are sugar over this.
        It is public because the typed verbs deliberately cover only a slice of
        the feature registry: a script that needs a revolve, a fillet or a hole
        TODAY can build the ``loft_wire.features`` envelope itself and pass
        it here, rather than waiting for a method. The version guard, the
        optimistic-concurrency retry and the contract check all still apply.
        """
        return self._write(
            lambda version: self.session.transport.call(
                ops.POST_PARTS_PART_ID_FEATURES,
                FeatureMutationResponse,
                path_params={"part_id": self.id},
                body=FeatureCreate(
                    name=name, feature=feature, expected_tree_version=version
                ),
            ),
            after=lambda response: response.tree_version,
        )

    def update_feature(
        self,
        feature_id: uuid.UUID,
        *,
        feature: Feature | None = None,
        name: str | None = None,
    ) -> FeatureMutationResponse:
        """Rename a feature and/or replace its whole param envelope.

        Params are replaced WHOLESALE, as the workspace replaces them: a PATCH
        carrying a partial envelope would silently drop the fields it omits.
        """
        return self._write(
            lambda version: self.session.transport.call(
                ops.PATCH_PARTS_PART_ID_FEATURES_FEATURE_ID,
                FeatureMutationResponse,
                path_params={"part_id": self.id, "feature_id": feature_id},
                body=FeatureUpdate(
                    feature=feature, name=name, expected_tree_version=version
                ),
            ),
            after=lambda response: response.tree_version,
        )

    def delete_feature(self, feature_id: uuid.UUID) -> None:
        """Delete a feature. Refused (409) when later features depend on it."""
        self.session.transport.call_none(
            ops.DELETE_PARTS_PART_ID_FEATURES_FEATURE_ID,
            path_params={"part_id": self.id, "feature_id": feature_id},
        )
        self.refresh()

    # -- modelling verbs ---------------------------------------------------

    def sketch(
        self,
        on: GeomRef | Literal["XY", "XZ", "YZ"] | str = "XY",
        *,
        name: str = "Sketch",
    ) -> Sketch:
        """Start a sketch on an origin datum plane (or an earlier datum feature).

        Returns an UNSAVED builder — nothing has been sent yet. Draw into it,
        then :meth:`~loft.sketch.Sketch.save` (or pass it to :meth:`extrude`,
        which saves it for you), exactly as the sketcher buffers a draft and
        persists it on close.
        """
        return Sketch(self, resolve_plane(on), name=name)

    def sketch_by_id(self, feature_id: uuid.UUID) -> Sketch:
        """Rebuild a :class:`~loft.sketch.Sketch` from a stored feature id alone.

        The reconstruction path an agent needs: a tool call that received only
        an id can carry on editing the sketch — adding constraints, retyping a
        dimension — with no memory of how it was authored.
        """
        record = self.feature(feature_id)
        stored = record.feature
        if not isinstance(stored, SketchFeature):
            raise TypeError(f"feature {feature_id} is a {stored.type!r}, not a sketch")
        return Sketch(
            self,
            stored.params.plane,
            name=record.name,
            feature_id=record.id,
            entities=stored.params.entities,
            constraints=stored.params.constraints,
        )

    def sketches(self) -> list[Sketch]:
        """Every sketch feature of this part, in tree order."""
        return [
            Sketch(
                self,
                record.feature.params.plane,
                name=record.name,
                feature_id=record.id,
                entities=record.feature.params.entities,
                constraints=record.feature.params.constraints,
            )
            for record in self.features()
            if isinstance(record.feature, SketchFeature)
        ]

    def extrude(
        self,
        profile: Sketch | FeatureRef | uuid.UUID,
        distance_mm: float,
        *,
        operation: Literal["add", "cut"] = "add",
        direction: Literal["normal", "reverse"] = "normal",
        merge: bool = True,
        name: str = "Extrude",
    ) -> FeatureResponse:
        """Extrude an earlier sketch's profile.

        ``profile`` takes whichever handle the caller has: the
        :class:`~loft.sketch.Sketch` object (saved and solved if it is not
        already — the workspace enables extrude only once the sketch solve
        round-trips back, so this reaches the same state by the same route), a
        ``FeatureRef``, or a bare feature id for the agent that holds only that.

        Refusals are the server's: a non-positive ``distance_mm`` is a 422 from
        the same validator the browser's request hits, and an open profile is a
        ``profile_not_closed`` feature error raised by :meth:`evaluate`.
        """
        if isinstance(profile, Sketch):
            if profile.solved is None:
                profile.save()
            ref = profile.ref()
        elif isinstance(profile, FeatureRef):
            ref = profile
        else:
            ref = FeatureRef(kind="feature", feature_id=profile)

        created = self.create_feature(
            name,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=ref,
                    distance_mm=distance_mm,
                    operation=operation,
                    direction=direction,
                    merge=merge,
                ),
            ),
        )
        return created.feature

    def set_extrude_distance(
        self, feature_id: uuid.UUID, distance_mm: float
    ) -> FeatureResponse:
        """Re-parametrize an existing extrude — the live parametric loop.

        Replaces the whole param envelope, like the workspace's distance field,
        keeping every other parameter as stored (a PATCH that dropped
        ``operation`` would silently turn a cut into an add).
        """
        record = self.feature(feature_id)
        stored = record.feature
        if not isinstance(stored, ExtrudeFeature):
            raise TypeError(
                f"feature {feature_id} is a {stored.type!r}, not an extrude"
            )
        params = stored.params.model_copy(update={"distance_mm": distance_mm})
        updated = self.update_feature(
            feature_id,
            feature=ExtrudeFeature(type="extrude", version=1, params=params),
        )
        return updated.feature

    # -- evaluation, measurement, export -----------------------------------

    def evaluate(self, *, strict: bool = False) -> Evaluation:
        """Rebuild the part's current tree and return the result.

        ``strict=False`` by default because a feature failure is a legitimate
        200 with per-feature statuses (feature-tree.md §4.3) and a caller often
        wants to READ those statuses — that is what the tree panel does. Pass
        ``strict=True`` (or call :meth:`Evaluation.raise_for_features`) to turn
        the first feature error into a typed exception.
        """
        result = self.session.transport.call(
            ops.POST_PARTS_PART_ID_EVALUATE,
            EvaluateTreeResult,
            path_params={"part_id": self.id},
        )
        self._tree_version = result.tree_version
        evaluation = Evaluation(result)
        return evaluation.raise_for_features() if strict else evaluation

    def mass_properties(self) -> ShapeProperties:
        """Volume, surface area, centroid, bounding box and B-rep counts.

        Real OCCT mass properties of the evaluated body — the numbers the
        inspector shows. Raises :class:`~loft.errors.NoBody` for a tree that
        evaluates to no solid (a sketch-only part), because a script that got
        ``None`` back here would most likely go on to divide by it.

        ``mass_g`` and ``center_of_mass`` are honestly ``None`` until the part
        has a material: unknown, never zero.
        """
        evaluation = self.evaluate(strict=True)
        if evaluation.properties is None:
            raise NoBody(
                "the part's tree evaluated cleanly but produced no body",
                details={
                    "part_id": str(self.id),
                    "tree_version": evaluation.tree_version,
                },
            )
        return evaluation.properties

    def export_bytes(self, format: ExportFormat) -> bytes:
        """The exported CAD file as bytes, byte-exact as the browser downloads it.

        ONE request. An earlier draft evaluated first so it could refuse a
        bodiless tree client-side; that was a second round trip buying a refusal
        the server already gives — geometry answers a 422 ``tree_export_failed``,
        which :mod:`loft.errors` maps to :class:`~loft.errors.NoBody`. Deriving
        the refusal from the server's own verdict is also the safer of the two:
        a client-side pre-check is a second opinion that can disagree with the
        thing it is standing in for.
        """
        return self.session.transport.call_bytes(
            ops.POST_PARTS_PART_ID_EXPORT,
            path_params={"part_id": self.id},
            query={"format": format},
        )

    def export(
        self,
        path: str | os.PathLike[str],
        *,
        format: ExportFormat | None = None,
    ) -> Path:
        """Export to a file, inferring the format from the suffix.

        ``part.export("bracket.step")`` — the line a script actually wants to
        write. An unknown suffix raises here, naming the formats, rather than
        travelling to the gateway to come back as a 422 about a query parameter.
        """
        target = Path(path)
        resolved = format or EXPORT_SUFFIXES.get(target.suffix.lower())
        if resolved is None:
            raise ValueError(
                f"cannot infer an export format from {target.suffix!r}; pass "
                f"format= explicitly (one of {sorted(set(EXPORT_SUFFIXES.values()))})"
            )
        target.write_bytes(self.export_bytes(resolved))
        return target


def create_part(
    session: Session,
    name: str,
    *,
    folder_id: uuid.UUID | None = None,
    length_unit: LengthUnit = "mm",
) -> Part:
    """POST a new part and wrap it. Used by :meth:`loft.Session.new_part`."""
    record = session.transport.call(
        ops.POST_PARTS,
        PartResponse,
        body=PartCreate(name=name, folder_id=folder_id, length_unit=length_unit),
    )
    return Part(session, record.id, tree_version=record.tree_version)


def list_parts(session: Session) -> Sequence[Part]:
    """GET the caller's parts, oldest first."""
    listing = session.transport.call(ops.GET_PARTS, PartListResponse)
    return [
        Part(session, record.id, tree_version=record.tree_version)
        for record in listing.parts
    ]
