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
from typing import TYPE_CHECKING, Literal, NoReturn, TypeVar

from loft_wire.extrude_extent import ExtrudeExtent
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
    SweepFeature,
    SweepParamsV1,
)
from loft_wire.geometry import ExportFormat, ShapeProperties
from loft_wire.legacy_twist import (
    EXTRUDE_TWIST_DEPRECATED_CODE,
    EXTRUDE_TWIST_DEPRECATED_MESSAGE,
)
from loft_wire.loft_file import LOFT_SUFFIX, LoftWarning
from loft_wire.parts import PartCreate, PartListResponse, PartResponse, PartUpdate
from loft_wire.units import LengthUnit
from loft_wire.versions import (
    PartVersion,
    PartVersionCreate,
    PartVersionListResponse,
    PartVersionRestore,
)

from loft import _operations as ops
from loft.datum import LineLike, ReferenceLike, plane_at_angle_feature
from loft.errors import FeatureFailed, InvalidRequest, NoBody, StaleDocument
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


def _refuse_extrude_twist() -> NoReturn:
    """The extrude twist is deprecated (loft_wire.legacy_twist): say so, and
    point to Sweep, with the server's own code and message."""
    raise InvalidRequest(
        EXTRUDE_TWIST_DEPRECATED_MESSAGE, code=EXTRUDE_TWIST_DEPRECATED_CODE
    )


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
        #: What :meth:`loft.Session.open` noticed while importing this part (a
        #: hand-edited tree, a volume that differs from the file's, features
        #: that failed to rebuild). Empty for every other handle.
        self.import_warnings: tuple[LoftWarning, ...] = ()

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
        """Delete a feature. Refused (409) when later features depend on it.

        The version guard travels in the QUERY here, not in a body — DELETE has
        none — which is the whole reason this method shipped broken: it was the
        one write whose concurrency token does not ride a pydantic model, so the
        contract check that guards every other write had nothing to look at and
        every call 422'd. :meth:`Transport._send` now enforces
        ``required_query`` the same way it enforces the body model, so the
        omission is a refusal here rather than a server rejection.
        """
        self._write(
            lambda version: self.session.transport.call(
                ops.DELETE_PARTS_PART_ID_FEATURES_FEATURE_ID,
                FeatureTreeResponse,
                path_params={"part_id": self.id, "feature_id": feature_id},
                query={"expected_tree_version": version},
            ),
            # The route returns the SURVIVING tree, so the new version is in the
            # response — no refetch, and the same shape the browser gets back.
            after=lambda tree: tree.tree_version,
        )

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
        extent: ExtrudeExtent = "one_side",
        merge: bool = True,
        name: str = "Extrude",
        twist_angle_deg: float | None = None,
        twist_center: object = None,
    ) -> FeatureResponse:
        """Extrude an earlier sketch's profile.

        ``profile`` takes whichever handle the caller has: the
        :class:`~loft.sketch.Sketch` object (saved and solved if it is not
        already — the workspace enables extrude only once the sketch solve
        round-trips back, so this reaches the same state by the same route), a
        ``FeatureRef``, or a bare feature id for the agent that holds only that.

        ``extent="symmetric"`` extrudes ``distance_mm / 2`` each side of the
        sketch plane, so ``distance_mm`` is the whole length (SolidWorks Mid
        Plane, Onshape and Fusion Symmetric); ``direction`` then only names
        which cap is ``start`` and which ``end``, as one-sided.
        It works for add and cut.

        Extrude has no twist: the extrude twist is deprecated, read-only legacy
        (:mod:`loft_wire.legacy_twist`). A twisted prism is :meth:`sweep` with
        ``twist_angle_deg`` along a straight path. A stored twisted extrude
        still rebuilds unchanged, and :meth:`set_extrude_distance` carries its
        twist through. Passing ``twist_angle_deg`` or ``twist_center`` raises
        :class:`~loft.errors.InvalidRequest` (``extrude_twist_deprecated``)
        before anything is sent.

        A non-positive ``distance_mm`` or a non-finite value is refused
        CLIENT-side by the shared DTO (a ``ValueError``, the same validator the
        server runs), so no payload the server would reject is ever sent. An
        open profile is a ``profile_not_closed`` feature error, raised by
        :meth:`evaluate`.
        """
        if twist_angle_deg is not None or twist_center is not None:
            _refuse_extrude_twist()
        created = self.create_feature(
            name,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=_sketch_ref(profile),
                    distance_mm=distance_mm,
                    operation=operation,
                    direction=direction,
                    extent=extent,
                    merge=merge,
                ),
            ),
        )
        return created.feature

    def plane_at_angle(
        self,
        line: LineLike,
        angle_deg: float,
        *,
        reference: ReferenceLike | None = None,
        flip: bool = False,
        name: str = "Plane",
    ) -> FeatureRef:
        """A datum plane through *line*, turned *angle_deg* from *reference*.

        Fusion 360's Plane at Angle, SolidWorks' Plane "At angle". *line* is
        ``"X"``/``"Y"``/``"Z"``, ``(sketch, entity_id)`` for a sketch line, or
        a picked edge's ref; *reference* is ``"XY"``/``"XZ"``/``"YZ"``, a
        datum's ref or a face ref, and defaults to a sketch line's own sketch
        plane. The line must be parallel to the reference. Returns the datum's
        ref, ready for ``part.sketch(on=...)``. The plane follows both inputs
        on every rebuild (:mod:`loft.datum`; RESEARCH §18).
        """
        created = self.create_feature(
            name,
            plane_at_angle_feature(line, angle_deg, reference=reference, flip=flip),
        )
        return FeatureRef(kind="feature", feature_id=created.feature.id)

    def sweep(
        self,
        profile: Sketch | FeatureRef | uuid.UUID,
        path: Sketch | FeatureRef | uuid.UUID,
        *,
        operation: Literal["add", "cut"] = "add",
        merge: bool = True,
        twist_angle_deg: float | None = None,
        name: str = "Sweep",
    ) -> FeatureResponse:
        """Sweep an earlier sketch's closed profile along another sketch's path.

        ``profile`` and ``path`` each take a :class:`~loft.sketch.Sketch`
        (saved if it is not already), a ``FeatureRef`` or a bare feature id,
        exactly as :meth:`extrude`'s ``profile`` does. The path sketch's
        entities must form one connected wire, open or CLOSED. A closed path (a
        loop of tube, a ring frame) sweeps once around into one closed solid,
        seated where the path passes nearest the profile; every joint of a
        closed path must be tangent-continuous, or :meth:`evaluate` raises the
        ``sweep_path_not_tangent`` feature error naming the joint.

        ``twist_angle_deg`` turns the profile uniformly about the path by that
        many degrees from one end of the sweep to the other — a true helix for
        every profile point, e.g. a helical gear's tooth gap cut with
        ``operation="cut"`` along the gear's axis. Positive is right-handed
        about the direction of travel, from the profile along the path. A twist
        needs a straight path perpendicular to the profile's sketch plane that
        does not cross it; any other path is a ``twist_path_unsupported``
        feature error, and a twist with too many turns for the profile a
        ``twist_failed`` one, both raised by :meth:`evaluate`. ``None`` or ``0``
        is the plain sweep. A non-finite twist, or one beyond ten turns, is
        refused client-side by the shared DTO (a ``ValueError``).
        """
        created = self.create_feature(
            name,
            SweepFeature(
                type="sweep",
                version=1,
                params=SweepParamsV1(
                    profile=_sketch_ref(profile),
                    path=_sketch_ref(path),
                    operation=operation,
                    merge=merge,
                    twist_angle_deg=twist_angle_deg,
                ),
            ),
        )
        return created.feature

    def set_sweep_twist(
        self, feature_id: uuid.UUID, twist_angle_deg: float | None
    ) -> FeatureResponse:
        """Change an existing sweep's twist (``None``/``0`` removes it).

        The same whole-envelope replacement, re-validated client-side, as
        :meth:`set_extrude_distance`: profile, path, operation and merge stay as
        stored, and a NaN or infinite twist is a pydantic ``ValidationError``
        naming the field before anything is sent.
        """
        record = self.feature(feature_id)
        stored = record.feature
        if not isinstance(stored, SweepFeature):
            raise TypeError(f"feature {feature_id} is a {stored.type!r}, not a sweep")
        params = SweepParamsV1.model_validate(
            {**stored.params.model_dump(), "twist_angle_deg": twist_angle_deg}
        )
        updated = self.update_feature(
            feature_id, feature=SweepFeature(type="sweep", version=1, params=params)
        )
        return updated.feature

    def set_extrude_distance(
        self, feature_id: uuid.UUID, distance_mm: float
    ) -> FeatureResponse:
        """Re-parametrize an existing extrude — the live parametric loop.

        Replaces the whole param envelope, like the workspace's distance field,
        keeping every other parameter as stored (a PATCH that dropped
        ``operation`` would silently turn a cut into an add, and one that
        dropped a stored legacy twist would straighten the part).
        """
        return self._update_extrude(feature_id, distance_mm=distance_mm)

    def set_extrude_twist(
        self, feature_id: uuid.UUID, twist_angle_deg: float | None
    ) -> FeatureResponse:
        """Removed: the extrude twist is deprecated, read-only legacy.

        Always raises :class:`~loft.errors.InvalidRequest`
        (``extrude_twist_deprecated``), pointing to :meth:`sweep` with
        ``twist_angle_deg``; nothing is sent.
        """
        del feature_id, twist_angle_deg
        _refuse_extrude_twist()

    def _update_extrude(
        self, feature_id: uuid.UUID, **changes: object
    ) -> FeatureResponse:
        record = self.feature(feature_id)
        stored = record.feature
        if not isinstance(stored, ExtrudeFeature):
            raise TypeError(
                f"feature {feature_id} is a {stored.type!r}, not an extrude"
            )
        # Re-VALIDATE the merged envelope; model_copy(update=...) does not. That
        # is the same client-side refusal `extrude` gets from constructing the
        # DTO. Without it (measured, review of d823af9) a NaN is carried by the
        # unvalidated copy into the request and dies in the HTTP client's JSON
        # encoder with an opaque "Out of range float values" error.
        params = type(stored.params).model_validate(
            {**stored.params.model_dump(), **changes}
        )
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

    # -- named versions ------------------------------------------------------

    def save_version(
        self, name: str, *, message: str = "", author: str | None = None
    ) -> PartVersion:
        """Save the part's current tree as a named version, e.g. ``"Rev B"``.

        Versions are never pruned and travel in the part's ``.loft``. *author*
        is a display name only. The save names the tree this handle last saw
        (``expected_tree_version``), refetching and retrying once if it moved.
        Saving is not a tree edit: ``tree_version`` does not change.
        """
        return self._write(
            lambda version: self.session.transport.call(
                ops.POST_PARTS_PART_ID_VERSIONS,
                PartVersion,
                path_params={"part_id": self.id},
                body=PartVersionCreate(
                    name=name,
                    message=message,
                    author=author,
                    expected_tree_version=version,
                ),
            ),
            after=lambda _saved: self.tree_version,
        )

    def versions(self) -> list[PartVersion]:
        """The part's named versions, newest first."""
        listing = self.session.transport.call(
            ops.GET_PARTS_PART_ID_VERSIONS,
            PartVersionListResponse,
            path_params={"part_id": self.id},
        )
        return listing.versions

    def restore_version(self, seq: int) -> FeatureTreeResponse:
        """Make version *seq* the part's tree, as ONE undoable edit.

        Later versions are kept; the edit before the restore is one undo away.
        """
        return self._write(
            lambda version: self.session.transport.call(
                ops.POST_PARTS_PART_ID_VERSIONS_SEQ_RESTORE,
                FeatureTreeResponse,
                path_params={"part_id": self.id, "seq": seq},
                body=PartVersionRestore(expected_tree_version=version),
            ),
            after=lambda tree: tree.tree_version,
        )

    # -- .loft files ---------------------------------------------------------

    def loft_bytes(self) -> bytes:
        """The part as a ``.loft`` file, byte-exact as the browser downloads it."""
        return self.session.transport.call_bytes(
            ops.GET_PARTS_PART_ID_EXPORT_LOFT, path_params={"part_id": self.id}
        )

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Save the part's parametric tree as a ``.loft`` file (docs/FILE-FORMAT.md).

        ``part.save("bracket.loft")``. The file is the whole feature tree plus a
        cached STEP body; :meth:`loft.Session.open` turns it back into a part on
        any Loft install, with the part's named versions. It is not a backup:
        undo history and other documents are not in it. Same part, same Loft
        build: same bytes, so a ``.loft`` diffs cleanly in git.
        """
        target = Path(path)
        if target.suffix.lower() != LOFT_SUFFIX:
            raise ValueError(
                f"a .loft file must end in {LOFT_SUFFIX!r}; got {target.suffix!r} "
                "(use Part.export() for STEP / STL / 3MF / GLB)"
            )
        target.write_bytes(self.loft_bytes())
        return target


def _sketch_ref(handle: Sketch | FeatureRef | uuid.UUID) -> FeatureRef:
    """A ``FeatureRef`` to a sketch, from whichever handle the caller holds.

    A :class:`~loft.sketch.Sketch` that has not been solved is saved first —
    the workspace enables a feature on a sketch only once its solve
    round-trips back, so a script reaches the same state by the same route.
    """
    if isinstance(handle, Sketch):
        if handle.solved is None:
            handle.save()
        return handle.ref()
    if isinstance(handle, FeatureRef):
        return handle
    return FeatureRef(kind="feature", feature_id=handle)


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
