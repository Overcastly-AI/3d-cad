"""The flat pattern as a PROFILE-ONLY DXF — a cut path, not a picture (F-2a).

The gap this closes, in the product audit's words: the only way to get a flat
pattern out of Loft was wrapped in an A4 drawing sheet, where the cut geometry was
**5 of 29 entities** and the overall extents were 10..287 x 10..200 mm (a page). An
operator had to import the sheet and delete the border, title block and bend table
by hand, for every revision. Every incumbent ships a one-click flat-pattern DXF
containing the cut outline and (optionally) the fold lines and nothing else; it is
the artifact a sheet-metal vendor's nesting and quoting software ingests unmodified,
and the one they ask for by name.

Two properties are asserted structurally rather than by example, because they are
what makes the file safe to send:

* **1:1 whatever the drawing says.** The request has no scale field, and the
  serializer divides out whatever scale the sheet drew the pattern at, so the F-1
  half-size-blank defect is unrepresentable here — asserted at four sheet scales.
* **A typed refusal, never an empty file.** A part with no developable blank is a
  422 envelope. An empty DXF is the worse outcome: it is a valid file, so a shop
  cannot tell "not sheet metal" from "the export broke".

Measured against the audit's own L-bracket fixture so the before/after numbers are
directly comparable, and read back through the conftest `read_dxf` fixture, which
derives the encoding from the file's own header (F-3).
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from ezdxf import units as ezdxf_units
from ezdxf.document import Drawing
from fastapi.testclient import TestClient
from geometry.drawings import (
    FlatPatternExportError,
    serialize_dxf,
    serialize_flat_pattern_dxf,
)
from geometry.main import app
from py_kit.schemas.drawings import (
    ComposedSheet,
    FlatPatternDxfRequest,
    flat_pattern_filename,
)
from py_kit.schemas.features import EvaluateTreeRequest

_GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-sheet-metal"

_ROUTE = "/api/v1/drawing/flat-pattern/dxf"

#: THIS MODEL'S documented tolerance, read from its own shipped golden
#: (``goldens-sheet-metal/l-bracket-flat-pattern-view/expected.json``) exactly as the
#: F-1 scale suite does — never an epsilon fitted to whatever this code happens to
#: produce (CLAUDE.md). The profile-only path adds only a rigid translation to the
#: arithmetic F-1 already measured at <= 2.8e-14 mm across scales, and a translation
#: introduces no scale error, so the same bound applies unchanged.
_TOL_MM = float(
    json.loads(
        (_GOLDENS_DIR / "l-bracket-flat-pattern-view" / "expected.json").read_text(
            "utf-8"
        )
    )["tolerance"]
)

#: The audit's sheet-wrapped measurement, for the docstring comparison above.
_SHEET_ENTITY_COUNT = 29

_SCALES: tuple[tuple[int, int], ...] = ((1, 1), (1, 2), (2, 1), (1, 3))
each_scale = pytest.mark.parametrize(
    "numerator,denominator", _SCALES, ids=[f"{n}-{d}" for n, d in _SCALES]
)

client = TestClient(app)


def _cut_extents(doc: Drawing) -> tuple[float, float, float, float]:
    """``(min_x, min_y, width, height)`` of every LINE in the file."""
    xs: list[float] = []
    ys: list[float] = []
    for entity in doc.modelspace():
        if entity.dxftype() != "LINE":
            continue
        xs += [float(entity.dxf.start.x), float(entity.dxf.end.x)]
        ys += [float(entity.dxf.start.y), float(entity.dxf.end.y)]
    assert xs, "the file carries no LINE entities at all"
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _developed_blank_mm(sheet: ComposedSheet) -> tuple[float, float]:
    """The TRUE developed blank, derived from the composed bend table."""
    table = sheet.bend_table
    assert table is not None and table.rows
    return (50.0 + table.rows[0].bend_allowance_mm + 30.0, 20.0)


# --- the artifact -----------------------------------------------------------------


def test_the_file_is_cut_geometry_and_nothing_else(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """THE F-2a gate. Five entities, all geometry, no annotation of any kind.

    The audit's sheet-wrapped file had the same five inside 29; this asserts the
    other 24 are gone rather than merely that the five are present.
    """
    sheet = compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")
    doc = read_dxf(serialize_flat_pattern_dxf(sheet))
    kinds = [entity.dxftype() for entity in doc.modelspace()]
    assert kinds == ["LINE"] * 5, f"expected 5 LINEs, got {kinds}"
    assert len(kinds) < _SHEET_ENTITY_COUNT
    layers = {entity.dxf.layer for entity in doc.modelspace()}
    assert layers == {"VISIBLE", "BEND"}, f"unexpected layers: {layers}"


def test_no_sheet_furniture_survives(
    compose_flat_pattern: Callable[..., ComposedSheet],
    dxf_texts: Callable[..., list[str]],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """Named individually, because each was a thing the operator deleted by hand:
    the A4 border, the title block, the bend table, the view caption."""
    sheet = compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")
    raw = serialize_flat_pattern_dxf(sheet)
    assert dxf_texts(raw) == [], "the cut path carries TEXT"
    doc = read_dxf(raw)
    assert not [e for e in doc.modelspace() if e.dxftype() == "LWPOLYLINE"], (
        "an LWPOLYLINE survived — the sheet border and table boxes are drawn as one"
    )
    declared = {layer.dxf.name for layer in doc.layers}
    for furniture in ("TITLE", "DIMENSION", "BEND_TABLE", "NOTES", "HATCH"):
        assert furniture not in declared, f"the {furniture} layer is still declared"


def test_the_blank_is_parked_at_the_origin(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """A file with no sheet in it must not carry an A4 page's coordinates.

    On the sheet the same blank sits at x 105.45..191.55, y 95..115 — the middle of
    a landscape A4. Here it starts at (0, 0).
    """
    sheet = compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")
    min_x, min_y, _w, _h = _cut_extents(read_dxf(serialize_flat_pattern_dxf(sheet)))
    assert min_x == pytest.approx(0.0, abs=_TOL_MM)
    assert min_y == pytest.approx(0.0, abs=_TOL_MM)


def test_it_declares_millimetres(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """``$INSUNITS`` is millimetres. A cut path whose units are a guess is scrap metal.

    **This assertion used to read ``== 6`` and was green** (AUDIT-PRODUCT T-16 /
    DXF-5): ``6`` is ``ezdxf.units.M``, metres, so this path shipped a 1000x lie under
    a test whose NAME said millimetres. The sibling assertion on the drawing-sheet path
    (``test_drawings_dxf_model_scale.py``) made the identical mistake, which is why the
    fix had to be one shared document factory rather than a patch to whichever writer
    was in front of us. Expected value taken from ``ezdxf.units`` — the library that
    writes the header — rather than restated as a literal.
    """
    sheet = compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")
    doc = read_dxf(serialize_flat_pattern_dxf(sheet))
    assert doc.header["$INSUNITS"] == ezdxf_units.MM
    assert ezdxf_units.decode(doc.header["$INSUNITS"]) == "mm"


# --- 1:1 by construction ----------------------------------------------------------


@each_scale
def test_the_cut_path_is_the_true_blank_at_every_sheet_scale(
    numerator: int,
    denominator: int,
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """86.094690 x 20.000000 mm from a 1:1, 1:2, 2:1 or 1:3 sheet alike.

    The F-1 defect (a 1:2 sheet shipping a 43.047 x 10.000 blank) cannot occur on
    this path even if a caller hands it a scaled sheet, and there is no parameter
    with which to ask for anything else.
    """
    sheet = compose_flat_pattern(
        "l-bracket",
        "L-Bracket Flat Pattern",
        numerator=numerator,
        denominator=denominator,
    )
    _x, _y, width, height = _cut_extents(read_dxf(serialize_flat_pattern_dxf(sheet)))
    expected_w, expected_h = _developed_blank_mm(sheet)
    assert width == pytest.approx(expected_w, abs=_TOL_MM), (
        f"{numerator}:{denominator} sheet exported a {width:.6f} mm blank; the "
        f"developed length is {expected_w:.6f} mm at any drawing scale"
    )
    assert height == pytest.approx(expected_h, abs=_TOL_MM)


def test_the_cut_path_matches_the_drawing_sheet_it_came_from(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """One unfold, one truth: the profile-only path is the SAME geometry the drawing
    shows, translated — not a re-projection that could drift from it.

    Compares segment-for-segment against the sheet DXF's own cut layers, which the
    F-1 suite independently pins to the developed blank.
    """
    sheet = compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")
    profile = read_dxf(serialize_flat_pattern_dxf(sheet))
    drawn = read_dxf(serialize_dxf(sheet))

    def segments(doc: Drawing) -> list[tuple[float, float, float, float]]:
        out: list[tuple[float, float, float, float]] = []
        for e in doc.modelspace():
            if e.dxftype() != "LINE" or e.dxf.layer not in {"VISIBLE", "BEND"}:
                continue
            out.append(
                (
                    float(e.dxf.start.x),
                    float(e.dxf.start.y),
                    float(e.dxf.end.x),
                    float(e.dxf.end.y),
                )
            )
        return out

    mine = segments(profile)
    theirs = segments(drawn)
    assert len(mine) == len(theirs) == 5
    # Same shape, differing only by the rigid translation to the origin.
    dx = theirs[0][0] - mine[0][0]
    dy = theirs[0][1] - mine[0][1]
    for a, b in zip(mine, theirs, strict=True):
        assert a[0] + dx == pytest.approx(b[0], abs=_TOL_MM)
        assert a[1] + dy == pytest.approx(b[1], abs=_TOL_MM)
        assert a[2] + dx == pytest.approx(b[2], abs=_TOL_MM)
        assert a[3] + dy == pytest.approx(b[3], abs=_TOL_MM)


# --- determinism ------------------------------------------------------------------


def test_the_same_sheet_serializes_byte_identically(
    compose_flat_pattern: Callable[..., ComposedSheet],
) -> None:
    """Determinism is a product property (RESEARCH §9), not a test convenience: a
    revision that changed nothing must not produce a file a vendor re-quotes."""
    sheet = compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")
    assert serialize_flat_pattern_dxf(sheet) == serialize_flat_pattern_dxf(sheet)


# --- a refusal, never an empty file -----------------------------------------------


def test_a_sheet_with_no_flat_pattern_raises_rather_than_writing_nothing(
    compose_flat_pattern: Callable[..., ComposedSheet],
) -> None:
    """A DXF with no entities is a VALID file, so a shop that receives one cannot
    tell "this part is not sheet metal" from "the export broke". Refuse instead."""
    sheet = compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")
    without = sheet.model_copy(update={"views": []})
    with pytest.raises(FlatPatternExportError) as caught:
        serialize_flat_pattern_dxf(without)
    assert caught.value.code == "flat_pattern_not_sheet_metal"


# --- the shipped route ------------------------------------------------------------


def _tree(stem: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (_GOLDENS_DIR / f"{stem}-flat-pattern-view" / "model.json").read_text("utf-8")
    )


def _payload(stem: str, **extra: object) -> dict[str, object]:
    tree = _tree(stem)
    return {
        "part_id": str(tree.part_id),
        "tree_version": tree.tree_version,
        "features": [f.model_dump(mode="json") for f in tree.features],
        **extra,
    }


def test_the_route_returns_a_named_dxf_from_a_PART(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """Reachable in ONE action from a part — no drawing, no sheet, no view.

    That is the whole point of the ticket: the incumbents' flat-pattern export does
    not ask you to author a drawing first, and neither does this.
    """
    response = client.post(_ROUTE, json=_payload("l-bracket", name="L Bracket"))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/vnd.dxf"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="l-bracket-flat.dxf"'
    )
    doc = read_dxf(response.content)
    assert [e.dxftype() for e in doc.modelspace()] == ["LINE"] * 5


def test_an_unnamed_part_still_gets_a_unique_filename() -> None:
    """Falls back to the part id — never a collision, never a blank name."""
    tree = _tree("l-bracket")
    filename = flat_pattern_filename(
        FlatPatternDxfRequest(
            part_id=tree.part_id,
            tree_version=tree.tree_version,
            features=tree.features,
        )
    )
    assert filename == f"part-{tree.part_id}-flat.dxf"


def test_a_non_sheet_metal_part_is_a_typed_422_not_a_file() -> None:
    """The refusal reaches the wire as an envelope with a code a client can branch
    on, and carries no bytes that could be mistaken for a cut path."""
    response = client.post(_ROUTE, json=_payload("l-bracket", features=[]))
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"].startswith("flat_pattern_")
    assert "sheet-metal" in error["message"] or "flat pattern" in error["message"]


def test_the_route_is_byte_deterministic() -> None:
    """Two identical requests, identical bytes (RESEARCH §9)."""
    payload = _payload("u-channel", name="U Channel")
    first = client.post(_ROUTE, json=payload)
    second = client.post(_ROUTE, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
