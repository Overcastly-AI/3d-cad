"""Library thumbnails: a headless software render of a document (LIBRARY-THUMBNAILS).

The Parts / Assemblies / Drawings registers and the assembly Add panel show a
small picture of each document, as Fusion's Data Panel and Onshape's document
list do. This module turns what geometry already produces into that picture:

- a PART or ASSEMBLY thumbnail rasterises the evaluated GLB (the part's
  content-addressed body mesh, or the assembly's solved one-file GLB export with
  placements baked in) from the standard isometric direction — front-right-top,
  the view an engineer's "Home" key gives — under fixed lighting;
- a DRAWING thumbnail rasterises the first sheet's :class:`ComposedSheet` (paper,
  border, title block and the visible projected edges), the same placement the
  sheet editor and the SVG/PDF exports draw from.

**Renderer: numpy + Pillow, nothing else.** No GPU, no OpenGL/EGL/OSMesa, no
headless browser and nothing fetched at runtime, so it runs in the geometry
container as-is and inside an air gap. Pillow (MIT-CMU) is already in the image
for the PDF export; numpy is a kernel dependency. Both are permissive. The
algorithm is the classic one for a flat-shaded preview:

1. back-face cull (normals oriented by the mesh's own ``NORMAL`` attribute), then
   paint triangles far-to-near (painter's algorithm) at 2x supersampling;
2. paint the same triangles into a FACE-ID buffer, and draw an edge wherever two
   neighbouring pixels belong to different B-rep faces or to the background. That
   gives exactly the visible model edges and the silhouette, occluded the same
   way the shading is — the CAD look, with no hidden-line pass;
3. downsample with a Lanczos filter on premultiplied alpha.

Output is a byte-deterministic 256x256 RGBA PNG on a transparent background (the
web supplies the tile colour, so one picture serves the light and dark themes).
Determinism matters because the PNG is cached under the content address of its
inputs (:mod:`geometry.thumbnail_store`): a rebuild never produces a different
picture for the same tree.
"""

import json
import struct
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import numpy as np
from loft_wire.drawings import ComposedSheet
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from geometry.kernel.tessellate import FACE_TRIANGLES_KEY

#: Bump when the picture for an unchanged model changes (colours, view, size,
#: algorithm): it is folded into every cache key, so old pictures fall out.
RENDERER_VERSION = 1

#: Final edge length in pixels. Thumbnails are a fixed size: the register tile
#: and the Add-panel tile both display it at <= 128 CSS px, so 256 covers 2x DPR.
THUMBNAIL_PX = 256

#: Supersampling factor; the painted image is ``THUMBNAIL_PX * SUPERSAMPLE``.
SUPERSAMPLE = 2

#: The fraction of the tile left empty around the model on each side.
MARGIN = 0.08

#: Rendering refuses a mesh above this many triangles (cost bound): a library
#: tile is not worth more than a few seconds of a geometry worker. The caller
#: answers with the placeholder.
MAX_TRIANGLES = 1_500_000

#: Isometric view direction (towards the eye) in glTF's Y-up world. The GLBs are
#: Z-up models under a -90 deg X rotation, so (1, 1, 1) here is (+X, -Y, +Z) in
#: model space: looking at the front, right and top faces (Onshape/SolidWorks iso).
_VIEW = np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)
_UP = np.array([0.0, 1.0, 0.0])

#: Fixed lighting, in view-independent world directions (towards the light).
_KEY_LIGHT = np.array([0.35, 0.9, 0.55]) / np.linalg.norm([0.35, 0.9, 0.55])
_FILL_LIGHT = np.array([-0.8, 0.1, 0.4]) / np.linalg.norm([-0.8, 0.1, 0.4])
_AMBIENT = 0.38
_KEY = 0.55
_FILL = 0.18

#: A neutral machined-metal grey-blue, legible on both themes' tiles.
_BODY_RGB = np.array([182.0, 192.0, 204.0])
_EDGE_RGBA = (38, 44, 52, 255)

#: Drawing-sheet palette: paper, ink, and the frame's lighter ink.
_PAPER_RGBA = (250, 250, 247, 255)
_INK_RGBA = (30, 34, 40, 255)
_FRAME_RGBA = (120, 126, 134, 255)

_GLB_MAGIC = 0x46546C67
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942
_TRIANGLES_MODE = 4

_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_DTYPES: dict[int, Any] = {
    5121: np.uint8,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}


class ThumbnailError(Exception):
    """There is nothing honest to draw (no triangles, or too many to afford)."""


@dataclass(frozen=True)
class TriangleSoup:
    """World-space triangles ``(n, 3, 3)``, their outward normals, B-rep face ids."""

    triangles: NDArray[np.float64]
    normals: NDArray[np.float64]
    face_ids: NDArray[np.int64]


# --- GLB reading ---------------------------------------------------------------


def _split_glb(glb: bytes) -> tuple[dict[str, Any], bytes]:
    magic, _version, _length = struct.unpack_from("<III", glb, 0)
    if magic != _GLB_MAGIC:
        raise ThumbnailError("not a GLB")
    offset = 12
    document: dict[str, Any] | None = None
    blob = b""
    while offset < len(glb):
        chunk_length, chunk_type = struct.unpack_from("<II", glb, offset)
        payload = glb[offset + 8 : offset + 8 + chunk_length]
        if chunk_type == _JSON_CHUNK:
            document = json.loads(payload)
        elif chunk_type == _BIN_CHUNK:
            blob = payload
        offset += 8 + chunk_length
    if document is None:
        raise ThumbnailError("GLB has no JSON chunk")
    return document, blob


def _accessor(document: dict[str, Any], blob: bytes, index: int) -> NDArray[Any]:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = np.dtype(_DTYPES[int(accessor["componentType"])])
    width = _COMPONENTS[accessor["type"]]
    count = int(accessor["count"])
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    stride = int(view.get("byteStride", 0)) or dtype.itemsize * width
    if stride == dtype.itemsize * width:
        flat = np.frombuffer(blob, dtype=dtype, count=count * width, offset=start)
        return flat.reshape(count, width) if width > 1 else flat
    rows = np.ndarray(
        shape=(count, width),
        dtype=dtype,
        buffer=blob,
        offset=start,
        strides=(stride, dtype.itemsize),
    )
    return np.array(rows) if width > 1 else np.array(rows[:, 0])


def _quaternion_matrix(q: list[float]) -> NDArray[np.float64]:
    x, y, z, w = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0.0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0.0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def _node_matrix(node: dict[str, Any]) -> NDArray[np.float64]:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    if "scale" in node:
        matrix = np.diag([*node["scale"], 1.0]) @ matrix
    if "rotation" in node:
        matrix = _quaternion_matrix(node["rotation"]) @ matrix
    if "translation" in node:
        translate = np.eye(4)
        translate[:3, 3] = node["translation"]
        matrix = translate @ matrix
    return matrix


def glb_triangles(glb: bytes) -> TriangleSoup:
    """Every triangle of every mesh instance in *glb*, in world space.

    Each glTF primitive's triangles get one face id, except a FUSED primitive
    (PERF-4b), whose ``extras`` run-length table splits it back into B-rep faces.
    Normals come from the triangle winding, flipped where they disagree with the
    mesh's ``NORMAL`` attribute (the writer's authority on outward).
    """
    document, blob = _split_glb(glb)
    triangles: list[NDArray[np.float64]] = []
    normals: list[NDArray[np.float64]] = []
    face_ids: list[NDArray[np.int64]] = []
    next_face = 0
    nodes: list[dict[str, Any]] = document.get("nodes", [])
    scene = document.get("scenes", [{}])[int(document.get("scene", 0))]
    stack: list[tuple[int, NDArray[np.float64]]] = [
        (int(index), np.eye(4)) for index in scene.get("nodes", range(len(nodes)))
    ]
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        world = parent @ _node_matrix(node)
        stack.extend((int(child), world) for child in node.get("children", []))
        if "mesh" not in node:
            continue
        for primitive in document["meshes"][int(node["mesh"])]["primitives"]:
            if primitive.get("mode", _TRIANGLES_MODE) != _TRIANGLES_MODE:
                continue
            attributes = primitive["attributes"]
            positions = _accessor(document, blob, int(attributes["POSITION"]))
            positions = positions.astype(np.float64) @ world[:3, :3].T + world[:3, 3]
            if "indices" in primitive:
                indices = _accessor(document, blob, int(primitive["indices"]))
                indices = indices.astype(np.int64).reshape(-1, 3)
            else:
                indices = np.arange(len(positions), dtype=np.int64).reshape(-1, 3)
            soup = positions[indices]
            normal = np.cross(soup[:, 1] - soup[:, 0], soup[:, 2] - soup[:, 0])
            if "NORMAL" in attributes:
                vertex_normals = _accessor(document, blob, int(attributes["NORMAL"]))
                vertex_normals = vertex_normals.astype(np.float64) @ world[:3, :3].T
                hint = vertex_normals[indices].sum(axis=1)
                flip = np.einsum("ij,ij->i", normal, hint) < 0
                normal[flip] *= -1
            length = np.linalg.norm(normal, axis=1)
            keep = length > 0
            soup, normal, length = soup[keep], normal[keep], length[keep]
            normal = normal / length[:, None]
            runs: list[int] | None = primitive.get("extras", {}).get(FACE_TRIANGLES_KEY)
            if runs:
                counts = np.asarray(runs, dtype=np.int64)
                ids = np.repeat(np.arange(next_face, next_face + len(runs)), counts)[
                    keep
                ]
                next_face += len(runs)
            else:
                ids = np.full(len(soup), next_face, dtype=np.int64)
                next_face += 1
            triangles.append(soup)
            normals.append(normal)
            face_ids.append(ids.astype(np.int64))
    if not triangles:
        raise ThumbnailError("the mesh has no triangles")
    return TriangleSoup(
        np.concatenate(triangles), np.concatenate(normals), np.concatenate(face_ids)
    )


# --- rasterising ----------------------------------------------------------------


def _encode_png(image: Image.Image) -> bytes:
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _downsample(image: Image.Image) -> Image.Image:
    """Lanczos to the final size on PREMULTIPLIED alpha (no dark fringes)."""
    return (
        image.convert("RGBa")
        .resize((THUMBNAIL_PX, THUMBNAIL_PX), Image.Resampling.LANCZOS)
        .convert("RGBA")
    )


def render_soup(soup: TriangleSoup) -> bytes:
    """Rasterise world-space triangles to the isometric thumbnail PNG."""
    if len(soup.triangles) > MAX_TRIANGLES:
        raise ThumbnailError(f"{len(soup.triangles)} triangles is over the cap")
    right = np.cross(_UP, _VIEW)
    right /= np.linalg.norm(right)
    up = np.cross(_VIEW, right)

    facing = soup.normals @ _VIEW > 1e-9
    triangles = soup.triangles[facing]
    normals = soup.normals[facing]
    faces = soup.face_ids[facing]
    if len(triangles) == 0:
        raise ThumbnailError("nothing faces the camera")

    screen_x = triangles @ right
    screen_y = triangles @ up
    depth = (triangles @ _VIEW).mean(axis=1)

    size = THUMBNAIL_PX * SUPERSAMPLE
    low = np.array([screen_x.min(), screen_y.min()])
    high = np.array([screen_x.max(), screen_y.max()])
    extent = float(max(high[0] - low[0], high[1] - low[1], 1e-12))
    scale = size * (1 - 2 * MARGIN) / extent
    centre = (low + high) / 2
    pixel_x = (screen_x - centre[0]) * scale + size / 2
    pixel_y = size / 2 - (screen_y - centre[1]) * scale

    shade = (
        _AMBIENT
        + _KEY * np.clip(normals @ _KEY_LIGHT, 0, None)
        + _FILL * np.clip(normals @ _FILL_LIGHT, 0, None)
    )
    colours = np.clip(_BODY_RGB[None, :] * shade[:, None], 0, 255).astype(np.uint8)

    colour_image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    id_image = Image.new("I", (size, size), 0)
    paint = ImageDraw.Draw(colour_image)
    label = ImageDraw.Draw(id_image)
    # Far to near; a stable sort keeps equal-depth ties in mesh order, so the
    # picture is deterministic.
    order = np.argsort(depth, kind="stable")
    xs = pixel_x[order].tolist()
    ys = pixel_y[order].tolist()
    rgb = colours[order].tolist()
    ids = (faces[order] + 1).tolist()
    for (x0, x1, x2), (y0, y1, y2), (r, g, b), face in zip(
        xs, ys, rgb, ids, strict=True
    ):
        polygon = [(x0, y0), (x1, y1), (x2, y2)]
        # The outline in the fill colour closes the hairline cracks between
        # neighbouring triangles of one face.
        paint.polygon(polygon, fill=(r, g, b, 255), outline=(r, g, b, 255))
        label.polygon(polygon, fill=face, outline=face)

    face_map = np.asarray(id_image, dtype=np.int64)
    boundary = np.zeros(face_map.shape, dtype=bool)
    horizontal = face_map[:, 1:] != face_map[:, :-1]
    vertical = face_map[1:, :] != face_map[:-1, :]
    boundary[:, 1:] |= horizontal
    boundary[:, :-1] |= horizontal
    boundary[1:, :] |= vertical
    boundary[:-1, :] |= vertical
    pixels = np.asarray(colour_image).copy()
    pixels[boundary] = _EDGE_RGBA
    return _encode_png(_downsample(Image.fromarray(pixels, mode="RGBA")))


def render_glb(glb: bytes) -> bytes:
    """The isometric thumbnail PNG of a GLB (a part body or a solved assembly)."""
    return render_soup(glb_triangles(glb))


def render_sheet(sheet: ComposedSheet) -> bytes:
    """The thumbnail PNG of a composed drawing sheet: paper, frame and visible edges.

    The sheet keeps its aspect ratio, centred on the transparent square tile.
    Hidden (dashed) edges, dimensions and text are left out: at this size they
    are noise, and the views' outlines are what identify the drawing.
    """
    size = THUMBNAIL_PX * SUPERSAMPLE
    extent = max(sheet.width_mm, sheet.height_mm)
    if extent <= 0:
        raise ThumbnailError("the sheet has no size")
    scale = size * (1 - MARGIN) / extent
    offset_x = (size - sheet.width_mm * scale) / 2
    offset_y = (size - sheet.height_mm * scale) / 2

    def at(x_mm: float, y_mm: float) -> tuple[float, float]:
        return (offset_x + x_mm * scale, offset_y + y_mm * scale)

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [at(0, 0), at(sheet.width_mm, sheet.height_mm)],
        fill=_PAPER_RGBA,
        outline=_FRAME_RGBA,
    )
    margin = sheet.margin_mm
    draw.rectangle(
        [at(margin, margin), at(sheet.width_mm - margin, sheet.height_mm - margin)],
        outline=_FRAME_RGBA,
        width=2,
    )
    block = sheet.title_block
    draw.rectangle(
        [at(block.x, block.y), at(block.x + block.width, block.y + block.height)],
        outline=_FRAME_RGBA,
        width=2,
    )
    for view in sheet.views:
        for edge in view.edges:
            if not edge.visible:
                continue
            if edge.kind == "line":
                draw.line(
                    [at(edge.x1, edge.y1), at(edge.x2, edge.y2)],
                    fill=_INK_RGBA,
                    width=2,
                )
            elif edge.kind == "circle":
                cx, cy = at(edge.cx, edge.cy)
                radius = edge.r * scale
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    outline=_INK_RGBA,
                    width=2,
                )
            else:
                draw.line(
                    [at(point.x_mm, point.y_mm) for point in edge.points],
                    fill=_INK_RGBA,
                    width=2,
                )
    return _encode_png(_downsample(image))
