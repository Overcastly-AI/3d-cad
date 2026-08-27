"""3MF and GLB export gates (EXPORT-2) — **units and scale first**.

The founder's question was "are we only going to accept one file format as an
export?", and the cheap answer (add two enum members, wire two writers) is the
one that ships parts at the wrong size. So the load-bearing assertion in this
module is not "the file parses" — it is **the extents of the re-read file,
converted through the format's own declared unit, equal the source solid's
bounding box**, over the whole golden inventory. That is the same class of
defect as the flat-pattern DXF's half-size blank: a file that opens cleanly,
declares millimetres, and is wrong.

The two formats declare DIFFERENT units, which is exactly why the table is a
constant (``py_kit.schemas.geometry.EXPORT_UNITS``) rather than a literal here:

* **3MF** writes millimetres and SAYS SO — ``<model unit="millimeter">`` in
  ``3D/3dmodel.model``. Asserted on the emitted XML, then re-read through
  lib3mf and re-measured.
* **GLB** is **metres and Y-up** by the glTF 2.0 specification, so its numbers
  are the mm geometry / 1000 with the axes permuted by the scene's node
  transform. A GLB written in mm renders 1000x oversized in every conformant
  viewer, and nothing in the file would say so — hence the node-transform walk
  below rather than reading the accessor bounds and hoping.

Tolerances are DERIVED, never ad-hoc (CLAUDE.md): both formats are faceted by
the same relative-deflection mesher the STL path uses, so a facet lies within
``linear_deflection x edge size`` of the true surface and no edge exceeds the
AABB diagonal. ``extent_tolerance`` is that ceiling. It is a ceiling and not a
fit — planar goldens facet exactly and measure 0.0 deviation.

Determinism (RESEARCH §9) is split across three places, deliberately, because
the expensive part is the REBUILD and not the export. Fresh-interpreter
determinism for all four formats lives in ``test_export.py`` (shape goldens) and
``test_assembly_export.py`` (both assembly goldens); IN-PROCESS determinism for
3MF and GLB over the whole 51-model inventory rides along in the extents sweep
below, where the rebuild is already paid for. ``test_export.py``'s TREE sweeps
stay on STEP/STL on purpose — 49 goldens x 4 formats x a rebuild each would add
~200 rebuilds to the slowest module in the suite.

The mechanism that makes 3MF deterministic at all is asserted here directly:
lib3mf mints five random production-extension UUIDs per write, and
``_canonicalise_3mf_ids`` pins them.
"""

import io
import json
import math
import struct
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from build123d import Box, Compound, Pos
from geometry.harness import build_model_solid, load_model_request
from geometry.kernel import (
    AssemblyComponent,
    export_3mf_assembly_bytes,
    export_glb_assembly_bytes,
    export_solid,
    measure_shape,
)
from geometry.kernel.export import (
    THREE_MF_MODEL_PART,
    THREE_MF_UUID_NAMESPACE,
    MeshExportNotManifoldError,
    export_3mf_bytes,
    export_glb_bytes,
)
from geometry.kernel.tessellate import tessellate_glb
from geometry.kernel.types import BodyShape
from geometry.schemas import ExportFormat, ShapeProperties
from py_kit.schemas.geometry import (
    DEFAULT_ANGULAR_DEFLECTION,
    DEFAULT_LINEAR_DEFLECTION,
    EXPORT_MEDIA_TYPES,
    EXPORT_UNITS,
)

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"
MODEL_FILES = sorted(GOLDENS_DIR.glob("*/model.json"))

each_model = pytest.mark.parametrize(
    "model_path", MODEL_FILES, ids=[path.parent.name for path in MODEL_FILES]
)

#: Goldens whose TRIANGULATION is not a manifold, oriented mesh, and which 3MF
#: therefore REFUSES (:class:`MeshExportNotManifoldError`). This is an
#: allow-list of ONE, written down rather than tolerated: if a second golden
#: joins it, that is a finding, and if this one starts passing, the gate below
#: says so instead of quietly widening.
#:
#: Measured on ``mirror-revolve-groove-tangent-wall-40x40x10``: V 513, F 1024,
#: E 1535 — Euler characteristic **1**, not 2 — with exactly ONE edge carrying
#: 4 triangles instead of 2, the 8 mm segment from (0, 0, 10) to (0, 0, 2) on
#: the revolve axis where the two mirrored groove lobes meet. The SOLID is
#: fine (BRepCheck-valid, STEP round-trips, STL and GLB both write it); it
#: touches itself along a line, which no manifold mesh can express and no
#: printer can print.
NON_MANIFOLD_MESH_GOLDENS = frozenset({"mirror-revolve-groove-tangent-wall-40x40x10"})

Extents = tuple[float, float, float]

#: glTF stores POSITION as float32 (component type 5126), so a coordinate of
#: magnitude ``|v|`` carries up to ``2^-24`` relative representation error and an
#: EXTENT — the difference of two such coordinates — up to twice that. This is
#: the format's storage precision, not a slack knob: asserting a GLB extent to
#: 1e-9 m asserts a property float32 cannot carry (measured: the 70 mm two-block
#: assembly reads 0.069999998 m, 1.6e-9 m short, and that is the file being
#: correct).
GLB_FLOAT32_REL_TOL = 2**-23

#: 3MF writes vertex coordinates as ``%.6f`` decimal text, so the file's own
#: quantisation is 5e-7 mm. Exact-extent assertions are held to one ULP of that
#: rather than to a float epsilon, for the same reason as above.
THREE_MF_TEXT_TOL_MM = 1e-6


# --- derived tolerances ------------------------------------------------------


def extent_tolerance(properties: ShapeProperties, linear_deflection: float) -> float:
    """Derived bound on how far a faceted extent may sit from the B-rep's.

    Same derivation as ``test_export.stl_volume_tolerance``'s first step, and
    for the same reason (OCCT meshes with ``isRelative=True``): the deviation
    budget for an edge is ``linear_deflection x edge size``, and no edge is
    longer than the AABB diagonal, so ``linear_deflection x diagonal`` bounds
    how far any meshed point can be from the true surface — and therefore how
    far a bounding-box face can move. A chord always lies INSIDE a convex arc,
    so the realistic error is one-sided and smaller; this is the ceiling.

    A golden that exceeds it is a finding to root-cause, never a reason to
    widen the formula.
    """
    box = properties.bounding_box
    diagonal = math.dist(
        (box.min.x, box.min.y, box.min.z), (box.max.x, box.max.y, box.max.z)
    )
    return linear_deflection * diagonal


def source_extents(properties: ShapeProperties) -> Extents:
    """The source solid's exact bounding-box extents (mm), from the B-rep."""
    box = properties.bounding_box
    return (
        box.max.x - box.min.x,
        box.max.y - box.min.y,
        box.max.z - box.min.z,
    )


# --- 3MF readers -------------------------------------------------------------


def three_mf_model_xml(data: bytes) -> str:
    """The ``3D/3dmodel.model`` XML of a 3MF package (a real OPC zip read)."""
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return package.read(THREE_MF_MODEL_PART).decode("utf-8")


def three_mf_vertices(data: bytes) -> np.ndarray:
    """Every ``<vertex>`` coordinate in a 3MF package, as an (N, 3) array.

    Parsed from the model XML rather than through lib3mf's reader on purpose:
    this asserts what the FILE says, which is what a slicer will read, and it
    cannot be rescued by a reader that silently applies a unit conversion.
    """
    import re

    pattern = re.compile(
        r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"\s*/>',
    )
    values = [
        (float(x), float(y), float(z))
        for x, y, z in pattern.findall(three_mf_model_xml(data))
    ]
    assert values, "3MF package carries no vertices"
    return np.array(values, dtype=float)


def three_mf_extents(data: bytes) -> Extents:
    """Extents of a 3MF package's geometry, in the unit the file declares."""
    points = three_mf_vertices(data)
    size = points.max(axis=0) - points.min(axis=0)
    return (float(size[0]), float(size[1]), float(size[2]))


# --- GLB readers -------------------------------------------------------------

_GLB_HEADER = struct.Struct("<4sII")
_GLB_CHUNK_HEADER = struct.Struct("<I4s")
_COMPONENT_DTYPE = {
    5120: "<i1",
    5121: "<u1",
    5122: "<i2",
    5123: "<u2",
    5125: "<u4",
    5126: "<f4",
}
_TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def glb_parts(glb: bytes) -> tuple[dict[str, Any], bytes]:
    """``(json_document, binary_chunk)`` of a GLB v2 payload.

    A real container parse — magic, version, declared length and chunk walk —
    not a four-byte magic check. A truncated or mis-lengthed payload fails
    here, which is the failure mode a `startswith(b"glTF")` assertion misses.
    """
    magic, version, length = _GLB_HEADER.unpack_from(glb, 0)
    assert magic == b"glTF", f"not a GLB payload (magic {magic!r})"
    assert version == 2, f"GLB version {version}, expected 2"
    assert length == len(glb), f"GLB header says {length} bytes, got {len(glb)}"
    offset = _GLB_HEADER.size
    document: dict[str, Any] | None = None
    blob = b""
    while offset < len(glb):
        chunk_length, chunk_type = _GLB_CHUNK_HEADER.unpack_from(glb, offset)
        start = offset + _GLB_CHUNK_HEADER.size
        payload = glb[start : start + chunk_length]
        if chunk_type == b"JSON":
            document = json.loads(payload.decode("utf-8"))
        elif chunk_type == b"BIN\x00":
            blob = payload
        offset = start + chunk_length
    assert document is not None, "GLB has no JSON chunk"
    return document, blob


def _accessor_values(document: dict[str, Any], blob: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    components = _TYPE_COMPONENTS[accessor["type"]]
    dtype = np.dtype(_COMPONENT_DTYPE[int(accessor["componentType"])])
    count = int(accessor["count"])
    view = document["bufferViews"][int(accessor["bufferView"])]
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    packed = components * dtype.itemsize
    stride = int(view.get("byteStride", 0)) or packed
    if stride == packed:
        flat = np.frombuffer(blob, dtype=dtype, count=count * components, offset=start)
        return flat.reshape(count, components).astype(float)
    rows = np.empty((count, components), dtype=float)
    for row in range(count):
        rows[row] = np.frombuffer(
            blob, dtype=dtype, count=components, offset=start + row * stride
        )
    return rows


def _node_matrix(node: dict[str, Any]) -> np.ndarray:
    """A glTF node's local transform as a 4x4 matrix (TRS or explicit)."""
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    matrix = np.eye(4)
    if "scale" in node:
        matrix = np.diag([*node["scale"], 1.0]) @ matrix
    if "rotation" in node:
        x, y, z, w = (float(v) for v in node["rotation"])
        rotation = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        homogeneous = np.eye(4)
        homogeneous[:3, :3] = rotation
        matrix = homogeneous @ matrix
    if "translation" in node:
        translation = np.eye(4)
        translation[:3, 3] = node["translation"]
        matrix = translation @ matrix
    return matrix


def glb_world_positions(glb: bytes) -> np.ndarray:
    """Every vertex of a GLB, in SCENE coordinates (node transforms applied).

    The transforms are the point: build123d writes the Z-up mm geometry into
    the mesh buffers and hands the Z-up -> Y-up conversion to a node rotation,
    so reading the POSITION accessors alone reports the wrong AXES with the
    right numbers — an error that looks like a pass on a cube and fails a real
    part. A viewer applies these; so does this reader.
    """
    document, blob = glb_parts(glb)
    meshes = document.get("meshes", [])
    scene = document.get("scenes", [{}])[int(document.get("scene", 0))]
    nodes = document.get("nodes", [])
    collected: list[np.ndarray] = []

    def visit(index: int, parent: np.ndarray) -> None:
        node = nodes[index]
        world = parent @ _node_matrix(node)
        if "mesh" in node:
            for primitive in meshes[int(node["mesh"])]["primitives"]:
                local = _accessor_values(
                    document, blob, int(primitive["attributes"]["POSITION"])
                )
                homogeneous = np.hstack([local, np.ones((local.shape[0], 1))])
                collected.append((world @ homogeneous.T).T[:, :3])
        for child in node.get("children", []):
            visit(int(child), world)

    for root in scene.get("nodes", []):
        visit(int(root), np.eye(4))
    assert collected, "GLB carries no mesh positions"
    return np.vstack(collected)


def glb_extents(glb: bytes) -> Extents:
    """Scene-space extents of a GLB, in the unit the glTF spec mandates (m)."""
    points = glb_world_positions(glb)
    size = points.max(axis=0) - points.min(axis=0)
    return (float(size[0]), float(size[1]), float(size[2]))


def assert_same_box(
    name: str,
    got: Extents,
    want: Extents,
    tolerance: float,
    unit: str,
    rel: float = 0.0,
) -> None:
    """Extents match as an unordered triple, within *tolerance*.

    Unordered because a format may permute the axes — GLB's Y-up conversion
    does exactly that — and this gate is about SCALE. Orientation is asserted
    separately, on the node transform, where it can be stated precisely
    instead of being smuggled into an extents comparison.
    """
    got_sorted = sorted(got)
    want_sorted = sorted(want)
    for measured, expected in zip(got_sorted, want_sorted, strict=True):
        assert measured == pytest.approx(expected, abs=tolerance, rel=rel), (
            f"{name}: exported extents {tuple(round(v, 6) for v in got_sorted)} {unit} "
            f"vs source {tuple(round(v, 6) for v in want_sorted)} {unit} "
            f"exceeds the faceting bound {tolerance!r}. A scale error here is a "
            f"file that cuts the wrong part."
        )


# --- the contract table ------------------------------------------------------


def test_every_export_format_declares_a_media_type_and_a_unit() -> None:
    """A new ``ExportFormat`` member cannot ship without saying what it writes.

    The two tables are what the routes and this gate read; a format missing
    from either is a 500 (media type) or an unasserted scale (unit), and both
    are silent. Derived from the Literal itself so adding a member fails here
    rather than in production.
    """
    formats = set(ExportFormat.__args__)
    assert formats == {"step", "stl", "3mf", "glb"}
    assert formats <= set(EXPORT_MEDIA_TYPES), "format without a media type"
    assert formats <= set(EXPORT_UNITS), "format without a declared length unit"
    assert EXPORT_UNITS["glb"] == 1e-3, "glTF is metres by specification"


# --- 3MF ---------------------------------------------------------------------


def test_3mf_is_an_opc_package_declaring_millimetres() -> None:
    """The container and the unit declaration — what STL cannot say."""
    data = export_3mf_bytes(Box(40, 25, 10), 0.1, 0.1, name="Motor Mount Bracket")

    with zipfile.ZipFile(io.BytesIO(data)) as package:
        members = set(package.namelist())
    assert {THREE_MF_MODEL_PART, "[Content_Types].xml", "_rels/.rels"} <= members

    xml = three_mf_model_xml(data)
    assert 'unit="millimeter"' in xml, "3MF must DECLARE its unit; that is the point"
    assert "<object " in xml and "<build" in xml
    assert 'name="Motor Mount Bracket"' in xml, (
        "the document name should reach the file"
    )


def test_3mf_extents_are_the_solid_in_declared_millimetres() -> None:
    """A 40 x 25 x 10 mm box measures 40 x 25 x 10 in the file it declares mm in."""
    solid = Box(40, 25, 10)
    data = export_3mf_bytes(solid, 0.1, 0.1)
    assert three_mf_extents(data) == pytest.approx(
        (40.0, 25.0, 10.0), abs=THREE_MF_TEXT_TOL_MM
    )


def test_3mf_uuids_are_pinned_not_random() -> None:
    """The determinism mechanism, asserted at the mechanism (RESEARCH §9).

    lib3mf stamps a fresh random UUID onto every object, component, build item
    and the build itself, so two writes of one box differ in five places and in
    total length. This asserts the pinned values are present — a regression
    that reverted the pinning would leave the file parseable, valid, and
    non-reproducible, which no other assertion in the suite would notice
    except as an intermittent failure.
    """
    import uuid as uuid_module

    xml = three_mf_model_xml(export_3mf_bytes(Box(40, 25, 10), 0.1, 0.1))
    expected_object = str(uuid_module.uuid5(THREE_MF_UUID_NAMESPACE, "object-0"))
    expected_item = str(uuid_module.uuid5(THREE_MF_UUID_NAMESPACE, "item-0"))
    expected_build = str(uuid_module.uuid5(THREE_MF_UUID_NAMESPACE, "build"))
    assert expected_object in xml
    assert expected_item in xml
    assert expected_build in xml


def test_3mf_writes_one_object_per_body() -> None:
    """Multi-body §MB-0: 3MF keeps the bodies apart; STL merges them.

    This is the capability that justifies the format sitting next to STL, so
    it is asserted rather than assumed.
    """
    bodies = Compound([Box(10, 10, 10), Pos(50, 0, 0) * Box(20, 5, 5)])
    xml = three_mf_model_xml(export_3mf_bytes(bodies, 0.1, 0.1, name="Two Blocks"))
    assert xml.count("<object ") == 2, "one 3MF object per solid"
    assert xml.count("<item ") == 2, "each object placed as its own build item"
    assert xml.count('name="Two Blocks"') == 2, "both objects carry the document name"


def test_3mf_rejects_a_non_positive_deflection() -> None:
    """Kernel-level guard (the API layer rejects these at parse)."""
    with pytest.raises(ValueError, match="strictly positive"):
        export_3mf_bytes(Box(1, 1, 1), 0.0, 0.1)
    with pytest.raises(ValueError, match="strictly positive"):
        export_3mf_bytes(Box(1, 1, 1), 0.1, -1.0)


# --- GLB ---------------------------------------------------------------------


def test_glb_is_metres_and_y_up() -> None:
    """The scale AND the axis convention, stated separately and both asserted.

    A 40 (X) x 25 (Y) x 10 (Z) mm box in Z-up millimetres becomes, in glTF's
    Y-up metres, 0.040 (X) x 0.010 (Y) x 0.025 (Z): divided by 1000, and with
    the kernel's +Z mapped to the scene's -Z... i.e. the model's HEIGHT is the
    scene's Y. Reading the accessors without the node transform would report
    (0.040, 0.025, 0.010) and look almost right, which is why this asserts the
    ordered triple and not a sorted one.
    """
    glb = export_glb_bytes(Box(40, 25, 10), 0.1)
    points = glb_world_positions(glb)
    size = points.max(axis=0) - points.min(axis=0)
    assert tuple(size) == pytest.approx((0.040, 0.010, 0.025), rel=GLB_FLOAT32_REL_TOL)

    # And the +Z-up -> +Y-up rotation is a real node transform, not baked into
    # the buffer: the mesh's own accessor bounds are still the Z-up triple.
    document, blob = glb_parts(glb)
    local = _accessor_values(
        document,
        blob,
        int(document["meshes"][0]["primitives"][0]["attributes"]["POSITION"]),
    )
    assert local.max(axis=0).max() == pytest.approx(0.020, rel=GLB_FLOAT32_REL_TOL)


def test_glb_export_is_byte_identical_to_the_viewport_payload() -> None:
    """GLB export reuses the tessellation artifact; it does not re-mesh.

    The property this asserts is worth more than it looks: the mesh store is
    keyed on the payload's sha256, so an export and a viewport tessellation of
    one body at one deflection are ONE artifact, and the file a user hands to
    a colleague is provably the mesh they were both looking at. A second
    meshing path would break that silently — same geometry, different bytes.
    """
    solid = Box(40, 25, 10)
    payload, _stats = tessellate_glb(solid, 0.1)
    assert export_glb_bytes(solid, 0.1) == payload
    assert export_solid(solid, "glb", 0.1, 0.1, name="Motor Mount Bracket") == payload


def test_glb_rejects_a_non_positive_deflection() -> None:
    with pytest.raises(ValueError, match="linear_deflection"):
        export_glb_bytes(Box(1, 1, 1), 0.0)


# --- the golden sweep: both formats, every model -----------------------------


@each_model
def test_mesh_export_extents_match_the_source_solid(model_path: Path) -> None:
    """THE units gate: every golden, both new formats, extents in real units.

    One solid build shared by both formats (the build dominates the cost), and
    the comparison is against the B-rep's own measured bounding box — not
    against a number written into the golden, which could be wrong in the same
    direction as the exporter.
    """
    name = model_path.parent.name
    request = load_model_request(model_path.read_text(encoding="utf-8"))
    solid: BodyShape = build_model_solid(request)
    properties = measure_shape(solid)
    want_mm = source_extents(properties)
    tolerance_mm = extent_tolerance(properties, DEFAULT_LINEAR_DEFLECTION)

    if name in NON_MANIFOLD_MESH_GOLDENS:
        # Refusal, not a skip: the typed error IS the asserted behaviour, and
        # the body's other three formats are asserted to still work below.
        with pytest.raises(MeshExportNotManifoldError):
            export_3mf_bytes(
                solid, DEFAULT_LINEAR_DEFLECTION, DEFAULT_ANGULAR_DEFLECTION
            )
    else:
        three_mf = export_3mf_bytes(
            solid, DEFAULT_LINEAR_DEFLECTION, DEFAULT_ANGULAR_DEFLECTION
        )
        assert 'unit="millimeter"' in three_mf_model_xml(three_mf)
        assert_same_box(
            f"{name} 3mf", three_mf_extents(three_mf), want_mm, tolerance_mm, "mm"
        )
        # Determinism over the WHOLE inventory rides along here (RESEARCH §9):
        # the rebuild is what costs, and it is already paid.
        assert three_mf == export_3mf_bytes(
            solid, DEFAULT_LINEAR_DEFLECTION, DEFAULT_ANGULAR_DEFLECTION
        ), f"{name}: 3MF export bytes differ between runs"

    glb = export_glb_bytes(solid, DEFAULT_LINEAR_DEFLECTION)
    assert glb == export_glb_bytes(solid, DEFAULT_LINEAR_DEFLECTION), (
        f"{name}: GLB export bytes differ between runs"
    )
    scale = EXPORT_UNITS["glb"]
    want_m = tuple(value * scale for value in want_mm)
    assert_same_box(
        f"{name} glb",
        glb_extents(glb),
        (want_m[0], want_m[1], want_m[2]),
        tolerance_mm * scale,
        "m",
        rel=GLB_FLOAT32_REL_TOL,
    )


# --- the one body 3MF refuses ------------------------------------------------


def _non_manifold_solid() -> BodyShape:
    (name,) = NON_MANIFOLD_MESH_GOLDENS
    path = GOLDENS_DIR / name / "model.json"
    return build_model_solid(load_model_request(path.read_text(encoding="utf-8")))


def test_non_manifold_body_refuses_3mf_but_writes_every_other_format() -> None:
    """The refusal is about 3MF's spec, NOT about the body being broken.

    Both halves matter. If only the raise were asserted, a regression that
    started refusing every body would pass. So this also writes the same solid
    as STEP, STL and GLB and checks all three come back non-empty — the body is
    exportable, it is the manifold-mesh CONTRACT it cannot satisfy.
    """
    solid = _non_manifold_solid()

    with pytest.raises(MeshExportNotManifoldError) as raised:
        export_3mf_bytes(solid, DEFAULT_LINEAR_DEFLECTION, DEFAULT_ANGULAR_DEFLECTION)
    assert raised.value.code == "export_mesh_not_manifold"
    # The message must name a way out, not just a refusal.
    assert "STEP" in str(raised.value) and "fillet" in str(raised.value)

    for fmt in ("step", "stl", "glb"):
        data = export_solid(
            solid, fmt, DEFAULT_LINEAR_DEFLECTION, DEFAULT_ANGULAR_DEFLECTION
        )
        assert len(data) > 0, f"{fmt} should still export this body"


def test_non_manifold_3mf_is_a_typed_envelope_not_a_500() -> None:
    """Through the real route: a 422 with the code, never an unhandled 500."""
    from fastapi.testclient import TestClient
    from geometry.main import app
    from py_kit.schemas.features import EvaluateTreeRequest, ExportTreeRequest

    (name,) = NON_MANIFOLD_MESH_GOLDENS
    path = GOLDENS_DIR / name / "model.json"
    tree = EvaluateTreeRequest.model_validate_json(path.read_text(encoding="utf-8"))
    request = ExportTreeRequest.model_validate(
        {**tree.model_dump(mode="json"), "format": "3mf"}
    )

    client = TestClient(app)
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "export_mesh_not_manifold"

    # ...and the same tree still writes the other three through the same route.
    for fmt in ("step", "stl", "glb"):
        other = ExportTreeRequest.model_validate(
            {**tree.model_dump(mode="json"), "format": fmt}
        )
        ok = client.post("/api/v1/export/tree", json=other.model_dump(mode="json"))
        assert ok.status_code == 200, f"{fmt} regressed on the same tree"
        assert ok.headers["content-type"] == EXPORT_MEDIA_TYPES[fmt]


# --- assemblies --------------------------------------------------------------


def _two_block_assembly() -> list[AssemblyComponent]:
    """Two instances 50 mm apart — a 70 x 25 x 10 mm assembly bounding box."""
    identity = (0.0, 0.0, 0.0, 1.0)
    return [
        AssemblyComponent(
            name="Block <1>",
            body=Box(20, 25, 10),
            translation=(0.0, 0.0, 0.0),
            quaternion=identity,
        ),
        AssemblyComponent(
            name="Block <2>",
            body=Box(20, 25, 10),
            translation=(50.0, 0.0, 0.0),
            quaternion=identity,
        ),
    ]


def test_assembly_3mf_keeps_one_named_object_per_instance() -> None:
    """3MF is the mesh format that survives the assembly's structure.

    Extents: two 20 mm blocks centred at x=0 and x=50 span -10..60 = 70 mm.
    """
    data = export_3mf_assembly_bytes(_two_block_assembly(), 0.1, 0.1)
    xml = three_mf_model_xml(data)
    assert xml.count("<object ") == 2
    assert 'name="Block &lt;1&gt;"' in xml or 'name="Block <1>"' in xml
    assert 'name="Block &lt;2&gt;"' in xml or 'name="Block <2>"' in xml
    assert three_mf_extents(data) == pytest.approx(
        (70.0, 25.0, 10.0), abs=THREE_MF_TEXT_TOL_MM
    )


def test_assembly_glb_bakes_the_placements_in_metres() -> None:
    """The assembly GLB spans the whole assembly, in metres and Y-up."""
    glb = export_glb_assembly_bytes(_two_block_assembly(), 0.1)
    points = glb_world_positions(glb)
    size = points.max(axis=0) - points.min(axis=0)
    assert tuple(size) == pytest.approx((0.070, 0.010, 0.025), rel=GLB_FLOAT32_REL_TOL)


def test_assembly_mesh_exports_refuse_an_empty_graph() -> None:
    """Never a zero-body file — the same posture the STEP/STL composers hold."""
    with pytest.raises(ValueError, match="at least one placed body"):
        export_3mf_assembly_bytes([], 0.1, 0.1)
    with pytest.raises(ValueError, match="at least one placed body"):
        export_glb_assembly_bytes([], 0.1)
