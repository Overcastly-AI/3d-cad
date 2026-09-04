"""Shared fixtures for the geometry test suite.

The workspace runs pytest with ``--import-mode=importlib`` (root
pyproject.toml), so test modules cannot import from each other —
cross-suite constants and assertion helpers live here as fixtures instead
(single source of truth, CLAUDE.md DRY rule).
"""

import io
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import ezdxf.recover
import pytest
from ezdxf.document import Drawing
from geometry.drawings import evaluate_drawing_views, place_sheet
from geometry.features.evaluate import reset_rebuild_cache
from geometry.schemas import ShapeProperties
from py_kit.schemas.drawings import (
    ComposeDrawingRequest,
    ComposedSheet,
    SheetLayout,
    SheetPoint,
    SheetViewPlacement,
    ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest

#: Round-trip tolerance for mass properties: the CLAUDE.md kernel linear
#: tolerance (1e-7), NOT a fitted epsilon — the measured round-trip deviation
#: for the planar box is exactly 0.0 (docs/GEOMETRY-QA.md), so the bound is a
#: ceiling, not a fit. Shared by the kernel-level (test_step_roundtrip) and
#: endpoint-level (test_export) STEP round-trip gates. Loosening it is a
#: reviewed decision recorded in docs/GEOMETRY-QA.md, never a quick fix.
ROUNDTRIP_TOL = 1e-7


@pytest.fixture(autouse=True)
def _cold_rebuild_cache() -> None:
    """Every test starts with an EMPTY rebuild cache (docs/PERF.md fix #1).

    The rebuild cache (:mod:`geometry.rebuild_cache`) resumes any tree whose
    feature prefix hashes identically — which in production is exactly right,
    because the code that evaluates a feature does not change under a running
    worker. **A test suite breaks that assumption on purpose**: a test that
    monkeypatches a kernel op to fail, then evaluates a tree an earlier test
    already evaluated successfully, would be served the earlier (unpatched)
    answer and assert against a stale one. Measured, not imagined — it turned
    ``test_hem_kernel_failure_maps_to_typed_edge_flange_failed`` green-for-the-
    wrong-reason within minutes of the cache landing.

    So the cache is per-test cold. Tests that WANT a hit warm it themselves
    inside the test (``tests/test_rebuild_cache.py``), which also keeps every
    other gate — goldens, determinism, timings — measuring a real rebuild.
    """
    reset_rebuild_cache()


@pytest.fixture(scope="session")
def roundtrip_tol() -> float:
    """``ROUNDTRIP_TOL`` as a fixture (importlib mode blocks cross-module imports).

    For gates that compare mass properties themselves rather than through
    :func:`assert_roundtrip_preserved` — e.g. the assembly-export round-trip,
    which matches re-imported solids to solved placements — so the one documented
    kernel bound stays the single source of truth (DRY), never re-hardcoded.
    """
    return ROUNDTRIP_TOL


@pytest.fixture(scope="session")
def assert_roundtrip_preserved() -> Callable[
    [str, ShapeProperties, ShapeProperties], None
]:
    """Assert re-imported geometry matches the original B-rep.

    Mass properties (volume, area, centroid, exact AABB) within
    ``ROUNDTRIP_TOL``; topology counts exactly. A deviation is a DEFECT to
    root-cause to export, import, or kernel — never tolerance noise to
    absorb (geometry-gates skill rules).
    """

    def check(
        name: str, reimported: ShapeProperties, original: ShapeProperties
    ) -> None:
        checks: list[tuple[str, float, float]] = [
            ("volume", reimported.volume, original.volume),
            ("surface_area", reimported.surface_area, original.surface_area),
            ("centroid.x", reimported.centroid.x, original.centroid.x),
            ("centroid.y", reimported.centroid.y, original.centroid.y),
            ("centroid.z", reimported.centroid.z, original.centroid.z),
            ("bbox.min.x", reimported.bounding_box.min.x, original.bounding_box.min.x),
            ("bbox.min.y", reimported.bounding_box.min.y, original.bounding_box.min.y),
            ("bbox.min.z", reimported.bounding_box.min.z, original.bounding_box.min.z),
            ("bbox.max.x", reimported.bounding_box.max.x, original.bounding_box.max.x),
            ("bbox.max.y", reimported.bounding_box.max.y, original.bounding_box.max.y),
            ("bbox.max.z", reimported.bounding_box.max.z, original.bounding_box.max.z),
        ]
        for label, got, want in checks:
            assert got == pytest.approx(want, abs=ROUNDTRIP_TOL), (
                f"{name}: round-trip {label} drifted — exported {want!r}, "
                f"re-imported {got!r} (tol {ROUNDTRIP_TOL!r}). This is a defect "
                f"to root-cause (export/import/kernel), not noise."
            )

        assert reimported.topology == original.topology, (
            f"{name}: topology changed across round-trip — "
            f"exported {original.topology.model_dump()}, "
            f"re-imported {reimported.topology.model_dump()}"
        )

    return check


@pytest.fixture(scope="session")
def assert_validation_envelope() -> Callable[[dict[str, Any]], None]:
    """Assert a body is the py-kit error envelope with the validation code."""

    def check(body: dict[str, Any]) -> None:
        assert set(body) == {"error"}
        error: dict[str, Any] = body["error"]
        assert set(error) == {"code", "message", "details", "request_id"}
        assert error["code"] == "validation_error"
        assert error["details"]  # pydantic locates the offending field(s)

    return check


# --- part 21 read-back (STEPNAME-1 / STEPNAME-2) ---------------------------------

#: A part-21 string literal: any run of characters in which a literal quote
#: appears DOUBLED (the standard's own escape, which OCCT emits). Written out
#: rather than ``[^']*`` because the naive form stops at the first quote of an
#: escaped pair and silently truncates every name containing an apostrophe —
#: which reads exactly like "the name is missing from the file".
_STEP_LITERAL = r"'((?:[^']|'')*)'"
_STEP_PRODUCT_RE = re.compile(
    (r"PRODUCT\s*\(\s*" + _STEP_LITERAL + r"\s*,\s*" + _STEP_LITERAL).encode()
)
_STEP_NAUO_RE = re.compile(
    (
        r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*"
        + _STEP_LITERAL
        + r"\s*,\s*"
        + _STEP_LITERAL
    ).encode()
)
_STEP_FILE_NAME_RE = re.compile(rb"FILE_NAME\s*\((.*?)\)\s*;", re.S)
_STEP_DATA_RE = re.compile(rb"\bDATA\s*;(.*)\bENDSEC\s*;", re.S)

#: OCCT stamps its own translator PRODUCTs into every ASSEMBLY file; they are not
#: ours and asserting over them would make every name assertion vacuously pass.
_OCCT_PRODUCT_PREFIX = "Open CASCADE STEP translator"


def _step_unescape(literal: bytes) -> str:
    """A part-21 string literal's bytes as the string the writer meant.

    Part 21 gives a string two escapes, and BOTH have to be undone or a name that
    contains either reads as absent from the file: a literal quote is doubled
    (``''``), and a literal backslash is doubled (``\\\\``) because backslash
    introduces the standard's control directives. Measured, in that order —
    undoing the quote first cannot corrupt a backslash pair and vice versa, since
    neither escape can produce the other's marker.

    Then UTF-8, and **the UTF-8 decode is the assertion**, not a convenience:
    before the encoding fix the same bytes decoded to the mojibake rather than to
    the submitted name, so an oracle that compared latin-1 text would have passed
    against corrupted output.
    """
    return literal.replace(b"''", b"'").replace(b"\\\\", b"\\").decode("utf-8")


def _step_product_pairs(data: bytes) -> list[tuple[str, str]]:
    """OUR ``PRODUCT`` ``(id, name)`` pairs, in file order.

    OCCT stamps its own translator PRODUCTs into an assembly file; they are not
    ours, and including them would make every name assertion vacuously pass.
    """
    return [
        (_step_unescape(pid), name)
        for pid, raw in _STEP_PRODUCT_RE.findall(data)
        if not (name := _step_unescape(raw)).startswith(_OCCT_PRODUCT_PREFIX)
    ]


@pytest.fixture(scope="session")
def step_product_pairs() -> Callable[[bytes], list[tuple[str, str]]]:
    """OUR ``PRODUCT`` ``(id, name)`` pairs — the duplicate-id evidence."""
    return _step_product_pairs


@pytest.fixture(scope="session")
def step_product_names() -> Callable[[bytes], list[str]]:
    """OUR ``PRODUCT`` names, in file order (see :func:`_step_product_pairs`)."""

    def names(data: bytes) -> list[str]:
        return [name for _, name in _step_product_pairs(data)]

    return names


@pytest.fixture(scope="session")
def step_occurrence_names() -> Callable[[bytes], list[str]]:
    """Every NON-EMPTY ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` name, in file order.

    OCCT writes a second, unnamed NAUO level per component whose body is a
    compound (it becomes a sub-assembly); those carry ``''`` and are dropped. A
    SINGLE-BODY export has no occurrences at all, and the empty list is the
    assertion that owning its writer added none.
    """

    def names(data: bytes) -> list[str]:
        return [
            name
            for _, raw in _STEP_NAUO_RE.findall(data)
            if (name := _step_unescape(raw))
        ]

    return names


@pytest.fixture(scope="session")
def step_file_name_record() -> Callable[[bytes], str]:
    """The ``FILE_NAME`` header record's argument text (the provenance fields)."""

    def record(data: bytes) -> str:
        match = _STEP_FILE_NAME_RE.search(data)
        assert match is not None, "no FILE_NAME record in the exported STEP"
        return match.group(1).decode("utf-8")

    return record


@pytest.fixture(scope="session")
def step_data_section() -> Callable[[bytes], bytes]:
    """Everything between ``DATA;`` and ``ENDSEC;`` — the model, not the header.

    The discriminator for "did the file's SHAPE change": entity ids, product
    structure and geometry all live here, while provenance (timestamp,
    originating system) lives in the header. Comparing data sections is how
    ``test_step_names_part`` shows that owning the single-body writer added no
    assembly level, no ``PRODUCT`` and no occurrence.
    """

    def section(data: bytes) -> bytes:
        match = _STEP_DATA_RE.search(data)
        assert match is not None, "no DATA section in the exported STEP"
        return match.group(1)

    return section


# --- DXF read-back (AUDIT-PRODUCT F-3) -------------------------------------------

#: The sheet-metal golden trees the DXF fixtures compose from.
_GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-sheet-metal"


@pytest.fixture(scope="session")
def read_dxf() -> Callable[[bytes], Drawing]:
    """Reopen serialized DXF bytes the way a CONFORMING READER would.

    Every DXF assertion in this suite used to open the bytes as
    ``ezdxf.read(io.StringIO(raw.decode("utf-8")))`` — which is not a measurement of
    the file, it is a restatement of the serializer's own assumption. A pre-R2007 DXF
    declares its code page in ``$DWGCODEPAGE``; ours says ``ANSI_1252`` and the bytes
    said UTF-8, so ezdxf handed back ``'90.0Â°'`` for the bend angle (AUDIT-PRODUCT
    F-3) and every test agreed with the defect because every test decoded the same
    wrong way.

    ``ezdxf.recover.read`` takes a BINARY stream and derives the encoding from the
    file's OWN header, then decodes ``\\U+xxxx`` escapes. It therefore never consults
    :data:`geometry.drawings.DXF_ENCODING`: if the bytes and the declared code page
    disagree again, strings come back mangled here and the assertion fails. Get the
    second opinion from a different derivation, not a louder assertion of the first.
    """

    def read(raw: bytes) -> Drawing:
        doc, auditor = ezdxf.recover.read(io.BytesIO(raw))
        assert not auditor.errors, f"DXF did not reopen cleanly: {auditor.errors}"
        return doc

    return read


@pytest.fixture(scope="session")
def dxf_texts(
    read_dxf: Callable[[bytes], Drawing],
) -> Callable[..., list[str]]:
    """Every model-space TEXT string, in emitted order; optionally one layer only."""

    def texts(raw: bytes, *, layer: str | None = None) -> list[str]:
        return [
            entity.dxf.text
            for entity in read_dxf(raw).modelspace().query("TEXT")
            if layer is None or entity.dxf.layer == layer
        ]

    return texts


@pytest.fixture(scope="session")
def compose_flat_pattern() -> Callable[..., ComposedSheet]:
    """Compose one sheet-metal golden's ``flat_pattern`` onto an A4 sheet.

    The shared builder for the DXF suites (encoding, layers, profile-only export):
    one part, one view, scale 1:1 unless a case is deliberately varying it.
    """

    def compose(
        stem: str,
        title: str,
        *,
        numerator: int = 1,
        denominator: int = 1,
    ) -> ComposedSheet:
        tree = EvaluateTreeRequest.model_validate_json(
            (_GOLDENS_DIR / f"{stem}-flat-pattern-view" / "model.json").read_text(
                "utf-8"
            )
        )
        scale = ViewScale(numerator=numerator, denominator=denominator)
        request = ComposeDrawingRequest(
            part_id=tree.part_id,
            tree_version=tree.tree_version,
            features=tree.features,
            views=["flat_pattern"],
            scale=scale,
            dimensions=[],
            layout=SheetLayout(
                size="A4",
                orientation="landscape",
                title=title,
                views=[
                    SheetViewPlacement(
                        projection="flat_pattern",
                        position=SheetPoint(x_mm=0.0, y_mm=0.0),
                        scale=scale,
                    )
                ],
            ),
            format="dxf",
        )
        return place_sheet(
            evaluate_drawing_views(request), request.dimensions, request.layout
        )

    return compose


#: Lines the sketch-solver sweep (``test_sketch_solver_sweep.py``) wants a human
#: to see on a GREEN run. A passing test prints nothing under ``-q``, so
#: "generated 2000, solvable 1327, violated 0" — the numbers that say the sweep
#: exercised anything at all — would otherwise exist only in the source.
_SWEEP_CENSUS: list[str] = []


@pytest.fixture
def sweep_census() -> list[str]:
    """Collector for the sweep's census; printed by :func:`pytest_unconfigure`.

    A fixture rather than an import because ``--import-mode=importlib`` blocks
    test modules from importing each other (this file's docstring), and the
    census has to reach a hook that lives here.
    """
    return _SWEEP_CENSUS


def pytest_unconfigure() -> None:
    """Print the sweep census AFTER everything else pytest prints.

    Not ``pytest_terminal_summary``: that hook runs before the short test
    summary, so on a red run the census lands in the middle of the log where a
    fixed ``tail_lines`` read cannot reach it (measured — the trap CLAUDE.md
    records for the e2e shards and for the documents verdict). ``pytest_
    unconfigure`` runs after the reporter's final stats line.
    """
    if _SWEEP_CENSUS:
        print("\n== sketch solver sweep ==\n" + "\n".join(_SWEEP_CENSUS))
