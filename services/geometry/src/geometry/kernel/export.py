"""CAD file export — STEP (exact B-rep) and binary STL (faceted mesh).

Uses build123d's exporters (OCCT ``STEPControl_Writer`` / ``StlAPI_Writer``
underneath). Both outputs are **byte-deterministic** for identical requests
(RESEARCH §9); the geometry export gate asserts it:

* **STEP:** OCCT stamps the file's ``FILE_NAME`` record with the wall-clock
  creation time — the one nondeterministic byte range in the output. We pin
  it to :data:`STEP_EXPORT_TIMESTAMP` via ``export_step(timestamp=...)``
  (decision + evidence recorded in docs/GEOMETRY-QA.md, gap #4). Exporting
  through ``BytesIO`` also keeps filesystem paths out of the file — the
  ``FILE_NAME`` name field stays the fixed writer default, verified on
  build123d 0.11.1.
* **STL:** binary format, fixed 80-byte OCCT header + mesher output, no
  timestamps. ``export_stl`` runs the SAME ``BRepMesh_IncrementalMesh`` call
  as the GLB tessellation path (``Shape.mesh``: relative linear deflection,
  parallel flag), so a given ``linear_deflection`` / ``angular_deflection``
  pair means the same facets in the viewport and in the exported file.
  Defaults come from :mod:`py_kit.schemas.geometry`
  (``DEFAULT_LINEAR_DEFLECTION`` = 0.1 mm, ``DEFAULT_ANGULAR_DEFLECTION`` =
  0.1 rad — the viewport-quality tessellation settings).

Kernel objects never leave ``geometry.kernel``: callers receive bytes.

**Assembly export (AP214 product structure).** :func:`export_step_assembly_bytes`
composes N placed part bodies into ONE multi-instance STEP where every instance
is a named PRODUCT at its solved world placement (RESEARCH §10/§11). It reuses
build123d's own XCAF path (``export_step`` drives ``STEPCAFControl_Writer`` with
a full XDE document — auto-naming off so our per-child labels become the PRODUCT
names), so the timestamp pinning above applies unchanged. The one EXTRA
nondeterministic byte range that path introduces is a **process-global**
occurrence counter OCCT stamps into each ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` id
(it increments across writer invocations within a worker, so a second export of
the same graph would differ); we canonicalise it to appearance order
(:func:`_canonicalise_occurrence_ids`) so identical requests stay byte-identical
(RESEARCH §9; decision + evidence in docs/GEOMETRY-QA.md). The NAUO id is an
arbitrary label — STEP cross-references use ``#N`` entity ids, not this string —
so renumbering it is semantically inert.

The OCP wheel ships no type stubs, so the raw ``gp_Trsf`` / ``gp_Quaternion``
transform calls the assembly placement uses are opaque to pyright; the directives
scope that relaxation to this file only (same posture as
:mod:`geometry.kernel.properties` / :mod:`geometry.kernel.imports`), and the
fully-typed :data:`BodyShape` return keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import io
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from build123d import Compound, Location
from build123d.exporters3d import (
    export_step,  # pyright: ignore[reportUnknownVariableType]  (Shape[Unknown] param upstream)
    export_stl,  # pyright: ignore[reportUnknownVariableType]
)
from OCP.gp import gp_Quaternion, gp_Trsf, gp_Vec

from geometry.kernel.types import BodyShape

#: Pinned STEP creation timestamp (determinism decision, GEOMETRY-QA gap #4).
#: STEP consumers treat ``FILE_NAME``'s timestamp as provenance metadata, not
#: geometry; a fixed sentinel value makes identical requests byte-identical.
STEP_EXPORT_TIMESTAMP = datetime(2000, 1, 1, 0, 0, 0)

#: Marker every STEP part 21 file starts with (sanity-checked after export).
STEP_MAGIC = b"ISO-10303-21"

#: Binary STL layout: 80-byte header + uint32 triangle count, then 50 bytes
#: per triangle (normal + 3 vertices as float32 triples + uint16 attribute).
STL_HEADER_BYTES = 84
STL_TRIANGLE_RECORD_BYTES = 50


def export_step_bytes(shape: BodyShape) -> bytes:
    """Export *shape* as a STEP AP214 part 21 file (exact B-rep, mm units).

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid` or a
    :class:`~build123d.Compound` of a multi-body part's solids (multi-body §MB-0);
    a STEP file holds multiple solids natively (valid AP214). Deterministic: the
    creation timestamp is pinned (module docstring).
    """
    buffer = io.BytesIO()
    if not export_step(shape, buffer, timestamp=STEP_EXPORT_TIMESTAMP):
        raise RuntimeError("STEP export failed")
    data = buffer.getvalue()
    if not data.startswith(STEP_MAGIC):
        raise RuntimeError("STEP export produced a non-part-21 payload")
    return data


def export_stl_bytes(
    shape: BodyShape, linear_deflection: float, angular_deflection: float
) -> bytes:
    """Export *shape* as a binary STL (faceted, mm units).

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid` or a
    multi-body :class:`~build123d.Compound` (multi-body §MB-0); STL emits every
    triangle of every solid. Deflection semantics match the GLB tessellation path
    (module docstring).

    Raises:
        ValueError: if a deflection is not strictly positive (the API layer
            rejects these at validation time; this guards direct kernel use).
    """
    if linear_deflection <= 0 or angular_deflection <= 0:
        raise ValueError(
            "Deflections must be strictly positive, got "
            f"linear={linear_deflection}, angular={angular_deflection}"
        )
    # StlAPI_Writer only speaks paths — write to a tempfile like the GLB
    # exporter does. The path never leaks into binary STL output.
    with tempfile.TemporaryDirectory(prefix="loft-stl-") as tmp:
        target = Path(tmp) / "shape.stl"
        ok = export_stl(
            shape,
            target,
            tolerance=linear_deflection,
            angular_tolerance=angular_deflection,
            ascii_format=False,
        )
        if not ok:
            raise RuntimeError("STL export failed")
        data = target.read_bytes()
    if len(data) < STL_HEADER_BYTES:
        raise RuntimeError("STL export produced a truncated payload")
    return data


@dataclass(frozen=True)
class AssemblyComponent:
    """One instance to compose into an assembly export — body + world pose + name.

    ``body`` is a resolved part :data:`BodyShape` in its LOCAL frame;
    ``translation`` / ``quaternion`` (the latter ``(x, y, z, w)``, matching
    :class:`py_kit.schemas.assemblies.Quat`) are its SOLVED world placement; the
    exporter positions the body by ``world = R(q)·local + t``. ``name`` becomes
    the STEP PRODUCT / occurrence name (traceability back to the instance).
    """

    name: str
    body: BodyShape
    translation: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]


def place_body(
    body: BodyShape,
    translation: tuple[float, float, float],
    quaternion: tuple[float, float, float, float],
) -> BodyShape:
    """Copy *body* to a world placement (``world = R(q)·local + t``).

    THE single source of the assembly rigid-placement transform (CLAUDE.md DRY
    rule): the STEP/STL composer (:func:`_placed_body`) and the interference
    check (:mod:`geometry.kernel.interference`) both position a solved instance
    through here, so no path reinvents the quaternion→``gp_Trsf`` conversion
    (rotation order geometry-QA-verified to 1e-14). ``quaternion`` is
    ``(x, y, z, w)`` matching :class:`py_kit.schemas.assemblies.Quat`. Returns a
    LOCATED copy — build123d ``.located`` leaves the original (and its shared
    underlying geometry) untouched, so placing two instances of one part never
    mutates the shared body. Deterministic: a fixed sequence of OCCT ops on the
    numeric pose.
    """
    qx, qy, qz, qw = quaternion
    rotation = gp_Quaternion(qx, qy, qz, qw)
    rotation.Normalize()  # belt-and-braces; the solver already emits unit q
    trsf = gp_Trsf()
    trsf.SetRotation(rotation)
    tx, ty, tz = translation
    trsf.SetTranslationPart(gp_Vec(tx, ty, tz))
    return body.located(Location(trsf))


def _placed_body(component: AssemblyComponent) -> BodyShape:
    """Copy *component*'s body to its world placement (see :func:`place_body`)."""
    return place_body(component.body, component.translation, component.quaternion)


#: Matches the id (first) field of every ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` in a
#: part-21 file — the one byte range OCCT's assembly writer fills from a
#: process-global counter. The name/reference fields that follow are untouched.
_NAUO_ID_RE = re.compile(rb"(NEXT_ASSEMBLY_USAGE_OCCURRENCE\(')([^']*)(')")


def _canonicalise_occurrence_ids(data: bytes) -> bytes:
    """Renumber ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` ids to appearance order (§9).

    OCCT stamps each usage occurrence's id string from a counter that persists
    ACROSS writer invocations in a worker process, so a second export of the
    same graph would differ only in those ids. The id is an arbitrary label
    (STEP cross-refs use ``#N`` entity ids, never this string), so rewriting it
    to a deterministic ``1..N`` in file order — itself deterministic — makes the
    whole file byte-identical for identical requests without touching geometry.
    """
    counter = 0

    def _renumber(match: re.Match[bytes]) -> bytes:
        nonlocal counter
        counter += 1
        return match.group(1) + str(counter).encode("ascii") + match.group(3)

    return _NAUO_ID_RE.sub(_renumber, data)


def export_step_assembly_bytes(
    assembly_name: str, components: Sequence[AssemblyComponent]
) -> bytes:
    """Export *components* as ONE AP214 STEP with named product structure.

    Each component becomes a named PRODUCT positioned at its solved world
    placement under a single assembly root (``assembly_name``): re-opening the
    file recovers every part body at its placement, traceable to its instance
    name (RESEARCH §10/§11). Reuses build123d's XCAF writer (module docstring),
    so the pinned creation timestamp applies; the per-occurrence id counter is
    canonicalised so identical requests are byte-identical (RESEARCH §9).

    Raises:
        ValueError: if *components* is empty (nothing to place — the caller maps
            this to a clean 422, never a zero-solid file).
    """
    if not components:
        raise ValueError("assembly STEP export requires at least one placed body")
    children: list[BodyShape] = []
    for component in components:
        placed = _placed_body(component)
        placed.label = component.name
        children.append(placed)
    root = Compound(children=children)
    root.label = assembly_name

    buffer = io.BytesIO()
    if not export_step(root, buffer, timestamp=STEP_EXPORT_TIMESTAMP):
        raise RuntimeError("assembly STEP export failed")
    data = _canonicalise_occurrence_ids(buffer.getvalue())
    if not data.startswith(STEP_MAGIC):
        raise RuntimeError("assembly STEP export produced a non-part-21 payload")
    return data


def export_stl_assembly_bytes(
    components: Sequence[AssemblyComponent],
    linear_deflection: float,
    angular_deflection: float,
) -> bytes:
    """Export *components* as ONE binary STL with placements baked in (faceted).

    STL carries no product structure, so the solved world placements are baked
    into a single :class:`~build123d.Compound` of every instance's positioned
    body and emitted through the SAME mesher as the single-body path
    (:func:`export_stl_bytes`). Deflection semantics match tessellation.

    Raises:
        ValueError: if *components* is empty, or a deflection is not strictly
            positive (delegated to :func:`export_stl_bytes`).
    """
    if not components:
        raise ValueError("assembly STL export requires at least one placed body")
    compound = Compound([_placed_body(component) for component in components])
    return export_stl_bytes(compound, linear_deflection, angular_deflection)
