"""Thread-schedule gates — a tapped hole reaching the PRINT (BACKLOG #50).

`19c9dc2` shipped cosmetic threads: the kernel bores the ISO tap drill and carries a
typed designation, the editor shows it, the tree badges it — and it reached NO output.
A tapped hole's SOLID is byte-identical to its bore, so unless the callout is stamped
on the drawing, an M6x1 tapped hole and a plain 5 mm drilled hole are the same part
and the shop makes the wrong one.

Every assertion here is on the SERIALIZED ARTIFACT (SVG text, PDF bytes, DXF entities)
— never on the composer's return value. The lesson is recent and specific: a commit
claimed the composer printed "REFERENCE LOST" in all three formats; the function was
right, a CALLER dropped it, and the unit test passed while the claim was false. The
route-level test below closes that gap for this feature: it POSTs to the real
``/api/v1/drawing/compose`` and reads the bytes that come back.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from ezdxf.document import Drawing
from fastapi.testclient import TestClient
from geometry.drawings import (
    evaluate_drawing_views,
    place_sheet,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
    thread_schedule_rows,
)
from geometry.main import app
from py_kit.schemas.drawings import (
    ComposeDrawingRequest,
    SheetLayout,
    SheetPoint,
    SheetViewPlacement,
    ViewScale,
)
from py_kit.schemas.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    HoleFeature,
    HoleParamsV1,
    IsoMetricThread,
)

client = TestClient(app)

_GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
#: The shipped tapped-hole golden (M10x1.5 in a 40x25x10 plate) — reused so the
#: schedule is exercised over a REAL evaluated tapped part, not a hand-rigged tree.
_TAPPED_MODEL = _GOLDENS / "hole-tapped-m10x1.5-40x25x10" / "model.json"
_SCALE = ViewScale(numerator=1, denominator=1)


def _tapped_tree() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        _TAPPED_MODEL.read_text(encoding="utf-8")
    )


def _compose_request(
    features: list[EvaluatedFeatureInput], tree: EvaluateTreeRequest
) -> ComposeDrawingRequest:
    return ComposeDrawingRequest(
        part_id=tree.part_id,
        tree_version=tree.tree_version,
        features=features,
        views=["front"],
        scale=_SCALE,
        dimensions=[],
        layout=SheetLayout(
            size="A3",
            orientation="landscape",
            title="MMB-001 Bracket",
            views=[
                SheetViewPlacement(
                    projection="front",
                    position=SheetPoint(x_mm=0.0, y_mm=0.0),
                    scale=_SCALE,
                )
            ],
        ),
        format="svg",
    )


def _compose_svg(request: ComposeDrawingRequest) -> str:
    evaluation = evaluate_drawing_views(request)
    sheet = place_sheet(
        evaluation,
        request.dimensions,
        request.layout,
        request.annotations,
        threads=thread_schedule_rows(request.features),
    )
    return serialize_svg(sheet)


def _tapped_hole(
    nominal: float, pitch: float, x: float
) -> tuple[EvaluatedFeatureInput, HoleParamsV1]:
    """One extra tapped hole feature, bored at the ISO tap drill (D - P)."""
    base = _tapped_tree().features[-1]
    assert isinstance(base.feature, HoleFeature)
    params = base.feature.params.model_copy(
        update={
            "diameter_mm": nominal - pitch,
            "position": base.feature.params.position.model_copy(update={"x": x}),
            "thread": IsoMetricThread(
                standard="iso_metric", nominal_diameter_mm=nominal, pitch_mm=pitch
            ),
        }
    )
    return (
        EvaluatedFeatureInput(
            id=uuid.uuid4(), feature=HoleFeature(type="hole", version=1, params=params)
        ),
        params,
    )


# --- derivation ------------------------------------------------------------------


def test_rows_are_derived_from_the_feature_params() -> None:
    """The designation AND the tap drill come from the kernel, not from this module."""
    rows = thread_schedule_rows(_tapped_tree().features)
    assert [(r.designation, r.quantity, r.tap_drill_mm) for r in rows] == [
        ("M10x1.5", 1, 8.5)
    ]


def test_untapped_part_schedules_nothing() -> None:
    """A part with no tapped hole gets no block: additive, no empty box on a print."""
    tree = _tapped_tree()
    untapped = [
        f
        for f in tree.features
        if not (isinstance(f.feature, HoleFeature) and f.feature.params.thread)
    ]
    assert thread_schedule_rows(untapped) == []
    assert "drawing-thread-schedule" not in _compose_svg(
        _compose_request(untapped, tree)
    )


def test_repeated_designations_roll_up_into_one_quantified_row() -> None:
    """Three M6x1 holes are ONE row reading 3x — what a shop counts, not three rows."""
    tree = _tapped_tree()
    features = list(tree.features)
    for i in range(3):
        entry, _ = _tapped_hole(6.0, 1.0, 8.0 + 8.0 * i)
        features.append(entry)
    rows = thread_schedule_rows(features)
    by_designation = {r.designation: r for r in rows}
    assert by_designation["M6x1"].quantity == 3
    assert by_designation["M6x1"].tap_drill_mm == pytest.approx(5.0)
    assert by_designation["M10x1.5"].quantity == 1


def test_row_order_is_tree_order_not_request_array_order() -> None:
    """RESEARCH §9: the same part composes to the same rows however features arrive.

    Reversing the feature list is a DIFFERENT tree (the reversal IS the order), so the
    guard is that the rows follow the list given — first appearance, deterministically
    — rather than, say, a dict/set iteration or an alphabetical sort that would make
    M10 and M6 swap places for reasons the user never authored.
    """
    tree = _tapped_tree()
    m6, _ = _tapped_hole(6.0, 1.0, 8.0)
    m8, _ = _tapped_hole(8.0, 1.25, 24.0)
    forward = thread_schedule_rows([*tree.features, m6, m8])
    assert [r.designation for r in forward] == ["M10x1.5", "M6x1", "M8x1.25"]
    later_first = thread_schedule_rows([*tree.features, m8, m6])
    assert [r.designation for r in later_first] == ["M10x1.5", "M8x1.25", "M6x1"]


def test_unresolvable_designation_is_skipped_not_invented() -> None:
    """A thread the kernel refuses to cut must never appear as a callout.

    The evaluator rejects it before geometry, so this cannot normally reach compose —
    but compose is a separate call taking any feature list, and printing "M7x1.1
    TAPPED" for a thread nobody can tap is worse than printing nothing.
    """
    tree = _tapped_tree()
    bogus, _ = _tapped_hole(6.0, 1.0, 8.0)
    assert isinstance(bogus.feature, HoleFeature)
    thread = bogus.feature.params.thread
    assert thread is not None
    invalid = bogus.model_copy(
        update={
            "feature": bogus.feature.model_copy(
                update={
                    "params": bogus.feature.params.model_copy(
                        update={
                            "thread": thread.model_copy(
                                update={"nominal_diameter_mm": 7.0, "pitch_mm": 1.1}
                            )
                        }
                    )
                }
            )
        }
    )
    assert thread_schedule_rows([*tree.features, invalid]) == thread_schedule_rows(
        tree.features
    )


# --- the artifacts (assert on the EXPORTED BYTES) --------------------------------


def test_svg_stamps_the_designation_quantity_and_tap_drill() -> None:
    """The exported SVG carries all three columns' values for the tapped hole."""
    tree = _tapped_tree()
    svg = _compose_svg(_compose_request(list(tree.features), tree))
    assert 'data-testid="drawing-thread-schedule"' in svg
    assert ">M10x1.5<" in svg, "the designation is not on the sheet"
    assert ">1x<" in svg, "the quantity is not on the sheet"
    assert ">8.50<" in svg, "the tap drill is not on the sheet"
    for caption in ("QTY", "THREAD", "TAP DRILL"):
        assert f">{caption}<" in svg


def test_pdf_and_dxf_carry_the_same_callout_as_the_svg(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """All three deliverables agree — a shop that gets the DXF reads the same thread.

    The PDF is checked through its uncompressed content stream (``pageCompression=0``,
    base-14 Courier — the text is literally in the bytes) and the DXF by reopening it
    and reading real TEXT entities, so neither is judged by a hash of itself.
    """
    tree = _tapped_tree()
    request = _compose_request(list(tree.features), tree)
    evaluation = evaluate_drawing_views(request)
    sheet = place_sheet(
        evaluation,
        request.dimensions,
        request.layout,
        request.annotations,
        threads=thread_schedule_rows(request.features),
    )
    assert sheet.thread_schedule is not None

    pdf = serialize_pdf(sheet)
    assert b"M10x1.5" in pdf, "the designation never reached the PDF a shop prints"
    assert b"TAP DRILL" in pdf

    dxf_bytes = serialize_dxf(sheet)
    doc = read_dxf(dxf_bytes)
    texts = {entity.dxf.text for entity in doc.modelspace().query("TEXT")}
    assert {"M10x1.5", "1x", "8.50", "THREAD", "TAP DRILL"} <= texts, (
        f"the DXF is missing thread-schedule text: {sorted(texts)}"
    )


def test_the_block_sits_inside_the_border_and_clear_of_the_title_block() -> None:
    """Placement guard: bottom-LEFT inside the margin, never over the title block."""
    tree = _tapped_tree()
    request = _compose_request(list(tree.features), tree)
    evaluation = evaluate_drawing_views(request)
    sheet = place_sheet(
        evaluation,
        request.dimensions,
        request.layout,
        request.annotations,
        threads=thread_schedule_rows(request.features),
    )
    block = sheet.thread_schedule
    assert block is not None
    assert block.x >= sheet.margin_mm
    assert block.y + block.height <= sheet.height_mm - sheet.margin_mm + 1e-9
    title = sheet.title_block
    assert block.x + block.width < title.x, (
        "the thread schedule overlaps the title block horizontally"
    )


def test_route_stamps_the_thread_on_the_downloaded_artifact() -> None:
    """END TO END over HTTP: the bytes the user downloads carry the callout.

    The gate that a green unit test cannot give: a composer that derives the right
    rows is worthless if the ROUTE never passes the features to it (the exact defect
    class the "REFERENCE LOST" claim turned out to be).
    """
    tree = _tapped_tree()
    request = _compose_request(list(tree.features), tree)
    response = client.post(
        "/api/v1/drawing/compose", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    assert b"M10x1.5" in response.content, (
        "the tapped designation did not reach the downloaded SVG — the route dropped it"
    )
