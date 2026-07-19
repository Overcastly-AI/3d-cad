"""``FlatPattern`` — the sheet-metal unfold's output DTO (SPIKE 0).

The flat pattern is the manufacturing deliverable of a sheet-metal part
(docs/design/sheet-metal.md §1): the 2D blank a laser/punch cuts, annotated
with the **bend lines** (where to fold) and per-bend metadata (angle, radius,
allowance, direction) that feed the shop's bend table.

**Spike scope (why these are plain dataclasses, not pydantic):** the design
doc (§6) specifies the *shipped* output reuses the neutral 2D-edge type drawing
views already emit (``py_kit.schemas.drawings.ProjectedViewEdge``, widened by an
additive ``edge_role`` field). This spike deliberately does NOT wire that DTO —
the feature slice owns the py-kit schema change (SPIKE 0's brief: no wire type
yet). ``FlatEdge2D``/``BendLine``/``FlatPattern`` are in-module dataclasses that
mirror the intended fields (``edge_role`` → ``FlatEdge2D.role``) so the shape is
proven before the schema is committed.

Determinism (RESEARCH §9 / sheet-metal.md §9 golden #4): the flat pattern must
serialize **byte-identically** across a fresh-process restart. ``to_json_bytes``
is the canonical serialization — a sorted-key, compact JSON of the full pattern;
``content_hash`` is its sha256. Because every value flows from a deterministic
OCCT measurement + closed-form bend allowance (no unordered iteration, no
wall-clock, no RNG), the bytes are stable across runs and interpreter restarts —
the same posture the GLB/STEP/PDF/DXF goldens already prove.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class FlatEdge2D:
    """One edge of the flat pattern's 2D outline, in the developed (u, v) frame.

    ``u`` is the developed-length axis (perpendicular to the bend line); ``v`` is
    the bend-width axis (parallel to the bend line). ``role`` mirrors the
    design's additive ``ProjectedViewEdge.edge_role`` discriminator (§6): a
    ``"body"`` edge is a real cut outline; a ``"bend"`` edge is a fold line
    (rendered as its own dashed-blue stroke by the feature slice, not a
    cut/occlusion distinction).
    """

    kind: Literal["line"]
    x1: float
    y1: float
    x2: float
    y2: float
    role: Literal["body", "bend"]


@dataclass(frozen=True)
class BendLine:
    """Per-bend row of the flat pattern's bend table (§6 step 5).

    ``allowance_mm`` is the bend allowance ``BA = angle_rad * (radius + K *
    thickness)`` (§1) — the flat length that replaces the two setback segments a
    naive sharp-corner unfold would use. ``flat_start_mm``/``flat_end_mm`` bound
    the developed bend strip along the ``u`` axis (``flat_end - flat_start ==
    allowance_mm``); the fold centerline sits at their midpoint.
    """

    bend_id: str
    angle_deg: float
    radius_mm: float
    k_factor: float
    allowance_mm: float
    width_mm: float
    direction: Literal["up", "down"]
    flat_start_mm: float
    flat_end_mm: float


@dataclass(frozen=True)
class FlatPattern:
    """The developed flat blank of an unfolded sheet-metal body (§6 output).

    ``flat_length_mm`` is the total developed length along ``u``
    (``Σ flange developed lengths + Σ bend allowances``); ``flat_area_mm2`` is
    the developed blank area (§9 golden #2: ``Σ flange developed areas +
    Σ (BA * bend_width)``). ``outline`` carries the 2D cut edges plus the tagged
    bend lines; ``bends`` carries the bend table.
    """

    thickness_mm: float
    k_factor: float
    flat_length_mm: float
    flat_area_mm2: float
    bend_width_mm: float
    outline: tuple[FlatEdge2D, ...]
    bends: tuple[BendLine, ...]

    def to_json_bytes(self) -> bytes:
        """Canonical, byte-deterministic serialization (the determinism gate).

        Sorted keys + compact separators so the bytes depend only on the values,
        never on field insertion order or whitespace. CPython's ``repr``-based
        float encoding is round-trip stable and deterministic, so identical
        inputs yield identical bytes across runs and interpreter restarts.
        """
        return json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")

    def content_hash(self) -> str:
        """sha256 of :meth:`to_json_bytes` — the byte-identity probe (§9 #4)."""
        return hashlib.sha256(self.to_json_bytes()).hexdigest()
