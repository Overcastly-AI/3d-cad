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
class FlatCutEdge2D:
    """One edge of an INTERIOR cut loop of the blank, in the developed (u, v) frame.

    The holes, slots and cutouts a laser drives after it has cut the outline (DXF-4).
    Kept separate from :attr:`FlatPattern.outline` on purpose: ``outline`` is the
    blank's single closed boundary plus its fold lines, and a consumer that walks it as
    one loop (the outline-closure invariant, §5) must not have interior loops
    interleaved into it. Every entry here is a real CUT — it goes on the same layer as
    the outline, never the ``BEND`` layer.

    ``kind`` mirrors the neutral drawing primitives so the translation to
    :class:`~py_kit.schemas.drawings.ProjectedViewEdge` is a field copy: a ``circle``
    is a closed circular loop (``cx``/``cy``/``r``, the common through hole), an
    ``arc`` a circular segment (a slot end), a ``line`` a straight segment.
    ``xm``/``ym`` is a point ON the edge — the drawing DTO's ``midpoint``, which is
    what a Ø/R dimension and an arc's sampler both read.
    """

    kind: Literal["line", "circle", "arc"]
    x1: float
    y1: float
    x2: float
    y2: float
    xm: float
    ym: float
    cx: float | None = None
    cy: float | None = None
    r: float | None = None


@dataclass(frozen=True)
class BendLine:
    """Per-bend row of the flat pattern's bend table (§6 step 5).

    ``allowance_mm`` is the bend allowance ``BA = angle_rad * (radius + K *
    thickness)`` (§1) — the flat length that replaces the two setback segments a
    naive sharp-corner unfold would use.

    ``flat_start_mm``/``flat_end_mm`` bound the developed bend strip, and only their
    DIFFERENCE is contract-stable: ``flat_end - flat_start == allowance_mm`` always
    holds (the strip is one bend allowance long, its fold centerline at the
    midpoint). Their ABSOLUTE values are frame-relative and their meaning depends on
    the pattern's dimensionality:

    * **1D strip** (an all-parallel star — L-bracket / U-channel): every bend folds
      about the SAME axis, so ``flat_start``/``flat_end`` are a shared developed-``u``
      coordinate and are directly comparable across bends (fold-line placement).
    * **2D plus/cross** (a non-parallel tray / pan): each arm folds about its OWN
      axis, so a bend's ``flat_start``/``flat_end`` is an AXIAL coordinate **in that
      arm's frame** — bend-1's may be a frame-X coordinate while bend-2's is a
      frame-Y coordinate, in DIFFERENT axes with no shared origin. They are NOT
      comparable across bends and must NOT be used for 2D fold-line placement.

    The authoritative, dimensionality-independent geometry for placing a fold line
    is the ``role="bend"`` edge in :attr:`FlatPattern.outline` (its endpoints are
    real 2D coordinates in the developed frame). Consumers rendering or dimensioning
    fold lines MUST use those outline bend edges; ``flat_start``/``flat_end`` are the
    per-bend TABLE metadata (which bend, how long its allowance), not a 2D locator.
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
    Σ (BA * bend_width)``), NET of every interior cut — a holed face's exact B-rep area
    already excludes its holes, and the ones the unfold's clean reference body has not
    seen are reconciled against the live body (``cutouts.DevelopedRegion``). ``outline``
    carries the blank's boundary plus the tagged bend lines; ``cutouts`` carries the
    INTERIOR cut loops (holes / slots / cutouts, DXF-4); ``bends`` the bend table.
    """

    thickness_mm: float
    k_factor: float
    flat_length_mm: float
    flat_area_mm2: float
    bend_width_mm: float
    outline: tuple[FlatEdge2D, ...]
    bends: tuple[BendLine, ...]
    cutouts: tuple[FlatCutEdge2D, ...] = ()

    def to_json_bytes(self) -> bytes:
        """Canonical, byte-deterministic serialization (the determinism gate).

        Sorted keys + compact separators so the bytes depend only on the values,
        never on field insertion order or whitespace. CPython's ``repr``-based
        float encoding is round-trip stable and deterministic, so identical
        inputs yield identical bytes across runs and interpreter restarts.

        ``cutouts`` — the one field with a default — is omitted when EMPTY: the
        canonical form encodes the pattern's CONTENT, and a blank with no interior cuts
        and a blank with an empty cut list are the same blank. That rule is what let
        ``cutouts`` (DXF-4) be added without moving a single committed
        ``content_hash``, so the hole-free goldens stay a real regression guard rather
        than being re-blessed alongside the very change they exist to guard. Any future
        additive field takes the same treatment, for the same reason.
        """
        payload = asdict(self)
        if not self.cutouts:
            del payload["cutouts"]
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")

    def content_hash(self) -> str:
        """sha256 of :meth:`to_json_bytes` — the byte-identity probe (§9 #4)."""
        return hashlib.sha256(self.to_json_bytes()).hexdigest()
