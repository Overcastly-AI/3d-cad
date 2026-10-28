"""The manifest's list input (CASEWORK, RESEARCH §23): an ordered list of rows
of number and choice fields, as a cabinet run's boxes, generic to any plugin.

A row's fields are typed and bounded like top-level inputs, a field a row
leaves out takes its default, a refusal names the row, and an empty list is
no value. Stored rows round-trip through the custom feature's envelope, and
a list of picks is never read as rows.
"""

import uuid
from typing import Any

import pytest
from loft_plugins import ExpandInputs, PluginError, canonical_inputs
from loft_wire.features import CustomFeature, FeatureRef
from loft_wire.plugins import ListInput, PluginManifest
from pydantic import ValidationError

IN = 25.4


def _rows(**over: Any) -> dict[str, Any]:
    return {
        "kind": "list",
        "name": "rungs",
        "label": "Rungs",
        "item_label": "Rung",
        "fields": [
            {
                "kind": "length",
                "name": "width_mm",
                "label": "Width",
                "default": 10.0,
                "minimum": 1.0,
                "maximum": 100.0,
            },
            {
                "kind": "count",
                "name": "pegs",
                "label": "Pegs",
                "default": 2,
                "maximum": 9,
            },
            {
                "kind": "choice",
                "name": "finish",
                "label": "Finish",
                "options": [
                    {"value": "oiled", "label": "Oiled"},
                    {"value": "raw", "label": "Raw"},
                ],
                "default": "raw",
            },
        ],
        **over,
    }


def _manifest(**over: Any) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": "test.ladder",
            "version": "1.0.0",
            "title": "Ladder",
            "description": "Rungs.",
            "inputs": [_rows(**over)],
            "members": [{"role": "rung", "title": "Rung"}],
        }
    )


def test_a_row_takes_its_fields_defaults_and_types() -> None:
    m = _manifest()
    stored = canonical_inputs(m, {"rungs": [{"width_mm": 30}, {"finish": "oiled"}]})
    assert stored == {
        "rungs": [
            {"width_mm": 30.0, "pegs": 2, "finish": "raw"},
            {"width_mm": 10.0, "pegs": 2, "finish": "oiled"},
        ]
    }
    assert isinstance(stored["rungs"][0]["width_mm"], float)  # type: ignore[index]
    rows = ExpandInputs(uuid.uuid4(), stored).rows("rungs")
    assert [
        (r.number("width_mm"), r.count("pegs"), r.choice("finish")) for r in rows
    ] == [
        (30.0, 2, "raw"),
        (10.0, 2, "oiled"),
    ]


def test_an_empty_optional_list_is_no_value_and_a_default_fills_one() -> None:
    assert canonical_inputs(_manifest(), {}) == {}
    with_default = _manifest(default=[{"pegs": 3}], min_items=1)
    assert canonical_inputs(with_default, {}) == {
        "rungs": [{"width_mm": 10.0, "pegs": 3, "finish": "raw"}]
    }


BAD_ROWS: list[tuple[list[dict[str, Any]], str]] = [
    ([{"width_mm": 0.5}], r"Rung 1, .*Width.*at least 1"),
    ([{}, {"pegs": 10}], r"Rung 2, .*Pegs.*from 0 to 9"),
    ([{}, {}, {"finish": "gilt"}], r"Rung 3, .*Finish.*not one of its options"),
    ([{"colour": "red"}], r"Rung 1 has no field 'colour'"),
    ([{}] * 4, r"at most 3 rows"),
]


@pytest.mark.parametrize(("rows", "words"), BAD_ROWS)
def test_a_bad_row_is_refused_by_number(rows: list[dict[str, Any]], words: str) -> None:
    with pytest.raises(PluginError, match=words) as err:
        canonical_inputs(_manifest(max_items=3), {"rungs": rows})
    assert err.value.input == "rungs"


def test_bounds_wait_for_formulas() -> None:
    """Before formulas are resolved only kinds are checked, as at the top level."""
    stored = canonical_inputs(_manifest(), {"rungs": [{"width_mm": 0.5}]}, bounds=False)
    assert stored["rungs"] == [{"width_mm": 0.5, "pegs": 2, "finish": "raw"}]


BAD_LISTS: list[tuple[dict[str, Any], str]] = [
    ({"min_items": 4, "max_items": 3}, "min_items is above max_items"),
    ({"default": [{"colour": "red"}]}, "no field 'colour'"),
    ({"default": [{"finish": "gilt"}]}, "not an option of 'finish'"),
    ({"default": [{}], "max_items": 1, "min_items": 2}, "min_items is above"),
]


@pytest.mark.parametrize(("over", "words"), BAD_LISTS)
def test_a_list_manifest_is_checked(over: dict[str, Any], words: str) -> None:
    with pytest.raises(ValidationError, match=words):
        _manifest(**over)


def test_a_row_field_is_never_superseded_nor_repeated() -> None:
    fields = _rows()["fields"]
    with pytest.raises(ValidationError, match="repeats a field"):
        ListInput.model_validate(_rows(fields=[fields[0], fields[0]]))
    sup = {**fields[1], "superseded_by": "width_mm"}
    with pytest.raises(ValidationError, match="never superseded"):
        ListInput.model_validate(_rows(fields=[fields[0], sup]))


def test_rows_and_picks_round_trip_through_the_envelope() -> None:
    """Rows stay rows and picks stay picks: the stored value is tried left to
    right, so a list of references is never read as a list of rows."""
    ref = FeatureRef(kind="feature", feature_id=uuid.UUID(int=1))
    env = CustomFeature.model_validate(
        {
            "type": "custom",
            "version": 1,
            "params": {
                "plugin_id": "test.ladder",
                "plugin_version": "1.0.0",
                "inputs": {
                    "rungs": [{"width_mm": 30.0, "pegs": 2, "finish": "raw"}],
                    "walls": [ref.model_dump(mode="json")],
                },
            },
            "expressions": {"/inputs/rungs/0/width_mm": "W/2"},
        }
    )
    assert env.params.inputs["walls"] == [ref]
    assert env.params.inputs["rungs"] == [
        {"width_mm": 30.0, "pegs": 2, "finish": "raw"}
    ]
    again = CustomFeature.model_validate_json(env.model_dump_json())
    assert again == env
