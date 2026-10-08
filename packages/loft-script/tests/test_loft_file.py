"""``Part.save`` / ``Session.open`` / ``loft.open`` against a real stack.

The script path to a ``.loft`` is the browser's path (the same two gateway
routes), so the assertions are on results: the volume of the part an import
rebuilds, the tree an offline read finds, the error code a bad file earns.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import loft
import pytest

from .conftest import Stack

PASSWORD = "loft-script-passphrase"
EXPECTED_VOLUME_MM3 = 40.0 * 25.0 * 10.0
VOLUME_TOLERANCE_MM3 = 1e-6

_emails = (f"loft-file-{n}@example.com" for n in itertools.count())


def _session(stack: Stack) -> loft.Session:
    return loft.register(stack.gateway_url, email=next(_emails), password=PASSWORD)


def _bracket(session: loft.Session) -> loft.Part:
    part = session.new_part("Bracket")
    sketch = part.sketch(on="XY")
    sketch.rect(40.0, 25.0)
    sketch.solve()
    part.extrude(sketch, 10.0)
    return part


def test_save_then_open_rebuilds_the_same_part(stack: Stack, tmp_path: Path) -> None:
    with _session(stack) as session:
        part = _bracket(session)
        path = part.save(tmp_path / "bracket.loft")
        assert path.read_bytes() == part.loft_bytes()  # same part, same bytes

        archive = loft.open(path)  # offline: no request
        assert archive.tree.name == "Bracket"
        assert [f.type for f in archive.tree.features] == ["sketch", "extrude"]
        assert archive.cache is not None and archive.cache.properties is not None
        assert archive.cache.properties.volume_mm3 == pytest.approx(
            EXPECTED_VOLUME_MM3, abs=VOLUME_TOLERANCE_MM3
        )

        opened = session.open(path)
        assert opened.id != part.id  # same install: a copy, with new ids
        assert opened.name == "Bracket copy"
        assert opened.import_warnings == ()
        assert opened.mass_properties().volume == pytest.approx(
            EXPECTED_VOLUME_MM3, abs=VOLUME_TOLERANCE_MM3
        )


def test_save_refuses_a_foreign_suffix(stack: Stack, tmp_path: Path) -> None:
    with _session(stack) as session:
        part = session.new_part("Plate")
        with pytest.raises(ValueError, match=r"\.loft"):
            part.save(tmp_path / "plate.step")


def test_a_bad_file_is_a_typed_refusal(stack: Stack, tmp_path: Path) -> None:
    path = tmp_path / "junk.loft"
    path.write_bytes(b"not a zip")
    with pytest.raises(loft.LoftFileError) as offline:
        loft.open(path)
    assert offline.value.code == "loft_not_zip"
    with _session(stack) as session, pytest.raises(loft.InvalidRequest) as online:
        session.open(path)
    assert online.value.code == "loft_not_zip"
