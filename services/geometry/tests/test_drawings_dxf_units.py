"""Every DXF we ship declares the unit its coordinates are in (AUDIT-PRODUCT T-16).

The defect, measured on the shipped bytes of BOTH export paths:

    serialize_dxf              (drawing sheet)  ->  $INSUNITS = 6
    serialize_flat_pattern_dxf (cut path)       ->  $INSUNITS = 6

and ``6`` is ``ezdxf.units.M`` — **metres** — on a file whose every coordinate is a
millimetre. ``$MEASUREMENT = 1`` (metric) sat two lines away contradicting it. A
nesting/CAM front end that honours ``$INSUNITS`` scales such a file by 1000.

Nobody chose metres. ``ezdxf.new``'s signature is ``new(dxfversion, setup, units=6)``
and neither call site passed ``units``, so both silently took the library default while
the docstring beside one of them asserted "``$INSUNITS = 6`` (millimetres)" — the code
and its comment agreed with each other and both were wrong. That is why the ticket's
"fix the writer" framing was too narrow and the audit's "TWO export paths" was right: a
default inherited in two places is wrong in two places, and patching one leaves a file
that is confidently, machine-readably wrong still going out the other door.

This is the F-1 half-size-blank defect with a different multiplier, and the same class
as F-3's mojibake bend angle: a header that lies about its own body, so every
downstream check agrees with itself and the shop cuts the wrong part.

Two things this file does deliberately.

* **It reads the emitted BYTES back** through the ``read_dxf`` fixture
  (``ezdxf.recover.read``, which derives the encoding from the file's own header), not
  the ``Drawing`` object our writer happens to hold. On a defect of this exact shape —
  the writer believing one thing and the file saying another — our writer's opinion is
  worthless as evidence. F-3 was found precisely because a test stopped restating the
  serializer's assumption and asked a real reader.
* **It ties the declaration to the geometry.** Asserting ``$INSUNITS == 4`` alone would
  pass equally well on a file whose numbers were metres, which is the same defect
  mirrored. So each path also measures a quantity of KNOWN millimetre size out of the
  file it just declared, and the pair is the assertion.
"""

import ast
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from ezdxf import units as ezdxf_units
from ezdxf.document import Drawing
from ezdxf.entities.line import Line
from ezdxf.entities.lwpolyline import LWPolyline
from geometry.drawings import (
    DXF_UNITS,
    serialize_dxf,
    serialize_flat_pattern_dxf,
)
from geometry.drawings import compose as compose_module
from py_kit.schemas.drawings import ComposedSheet

_GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-sheet-metal"

#: THIS MODEL'S documented tolerance, read from its own shipped golden exactly as the
#: sibling DXF suites do (``test_drawings_dxf_model_scale.py``,
#: ``test_drawings_flat_pattern_dxf.py``) — never an epsilon fitted to whatever this
#: code happens to emit (CLAUDE.md). Both quantities measured here ride ``_DxfFrame``
#: with ``correction == 1.0``, i.e. the identity plus a subtraction, so the residual is
#: far inside it; the point of the bound is that it is a documented one.
_TOL_MM = float(
    json.loads(
        (_GOLDENS_DIR / "l-bracket-flat-pattern-view" / "expected.json").read_text(
            "utf-8"
        )
    )["tolerance"]
)

#: The DXF header variable that declares metric vs imperial. It is INDEPENDENT of
#: ``$INSUNITS`` and already said metric while ``$INSUNITS`` said metres, so a file can
#: contradict itself; that contradiction is asserted away below.
_METRIC = 1

#: Both export paths, named, so every assertion in this file runs against BOTH and a
#: fix that lands on only one cannot go green. The ticket described one path; the
#: audit measured two.
_PATHS: tuple[tuple[str, Callable[[ComposedSheet], bytes]], ...] = (
    ("serialize_dxf", serialize_dxf),
    ("serialize_flat_pattern_dxf", serialize_flat_pattern_dxf),
)
each_path = pytest.mark.parametrize(
    "serialize", [p[1] for p in _PATHS], ids=[p[0] for p in _PATHS]
)


def _sheet(compose_flat_pattern: Callable[..., ComposedSheet]) -> ComposedSheet:
    """One composed sheet that BOTH serializers accept (it carries a flat pattern)."""
    return compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")


def _line_extents(doc: Drawing, layer: str) -> tuple[float, float]:
    """``(width, height)`` in model space of every LINE/LWPOLYLINE on one layer."""
    xs: list[float] = []
    ys: list[float] = []
    for entity in doc.modelspace():
        if entity.dxf.layer != layer:
            continue
        # isinstance rather than `dxftype()` string matching: it narrows for pyright,
        # so `get_points`/`start`/`end` are typed accesses rather than `Any`.
        if isinstance(entity, Line):
            xs += [float(entity.dxf.start.x), float(entity.dxf.end.x)]
            ys += [float(entity.dxf.start.y), float(entity.dxf.end.y)]
        elif isinstance(entity, LWPolyline):
            for x, y in entity.get_points("xy"):
                xs.append(float(x))
                ys.append(float(y))
    assert xs, f"no LINE/LWPOLYLINE geometry on layer {layer}"
    return (max(xs) - min(xs), max(ys) - min(ys))


# --- the defect --------------------------------------------------------------------


@each_path
def test_every_export_path_declares_millimetres(
    serialize: Callable[[ComposedSheet], bytes],
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """THE regression gate for T-16 / DXF-5, on BOTH paths.

    On the pre-fix code this reddens twice — once per path — with the audit's own
    measured number: ``$INSUNITS = 6 (m)`` where ``4 (mm)`` is the truth.
    """
    doc = read_dxf(serialize(_sheet(compose_flat_pattern)))
    declared = doc.header.get("$INSUNITS")
    assert declared == ezdxf_units.MM, (
        f"the file declares $INSUNITS = {declared} "
        f"({ezdxf_units.decode(declared) if declared is not None else 'absent'}); "
        f"every coordinate in it is a millimetre, so it must declare "
        f"{ezdxf_units.MM} ({ezdxf_units.decode(ezdxf_units.MM)}) — a CAM front end "
        f"that honours this field scales the part by 1000"
    )


@each_path
def test_the_header_does_not_contradict_itself(
    serialize: Callable[[ComposedSheet], bytes],
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """``$MEASUREMENT`` (metric) and ``$INSUNITS`` (mm) agree inside the same file.

    The audit's sharpest tell that ``$INSUNITS`` was unchosen rather than merely wrong:
    ``$MEASUREMENT`` already said metric, so the file disagreed with itself and a
    reader had no way to know which half to believe.
    """
    doc = read_dxf(serialize(_sheet(compose_flat_pattern)))
    assert doc.header.get("$MEASUREMENT") == _METRIC
    assert ezdxf_units.decode(doc.header.get("$INSUNITS")) == "mm"


def test_the_sheet_path_declaration_matches_its_own_coordinates(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The drawing sheet declares mm AND its border measures the A4 page in mm.

    The border is the one entity in the file whose true millimetre size is known
    without re-deriving any geometry: ``place_sheet`` draws it inset by the margin on
    every side of the page. So if the numbers were metres, this is a 0.277 x 0.190 m
    page and the assertion fails — which is what makes the unit claim above a
    measurement rather than a restatement.
    """
    sheet = _sheet(compose_flat_pattern)
    doc = read_dxf(serialize_dxf(sheet))
    width, height = _line_extents(doc, "TITLE")
    assert width == pytest.approx(sheet.width_mm - 2 * sheet.margin_mm, abs=_TOL_MM)
    assert height == pytest.approx(sheet.height_mm - 2 * sheet.margin_mm, abs=_TOL_MM)
    assert doc.header.get("$INSUNITS") == ezdxf_units.MM


def test_the_flat_pattern_path_declaration_matches_its_own_coordinates(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The cut path declares mm AND measures the TRUE developed blank in mm.

    The blank is ``50 (base flange) + BA + 30 (edge flange)`` by ``20`` wide, with the
    bend allowance read from the sheet's OWN composed bend table rather than restated,
    so the truth has one source (the same derivation the F-1 suite uses).
    """
    sheet = _sheet(compose_flat_pattern)
    table = sheet.bend_table
    assert table is not None and table.rows
    expected = (50.0 + table.rows[0].bend_allowance_mm + 30.0, 20.0)

    doc = read_dxf(serialize_flat_pattern_dxf(sheet))
    width, height = _line_extents(doc, "VISIBLE")
    assert width == pytest.approx(expected[0], abs=_TOL_MM), (
        f"the cut path measures {width:.6f} against a {expected[0]:.6f} mm developed "
        f"blank; the header's unit is only meaningful if the numbers are mm"
    )
    assert height == pytest.approx(expected[1], abs=_TOL_MM)
    assert doc.header.get("$INSUNITS") == ezdxf_units.MM


# --- the structure that keeps it fixed ---------------------------------------------


def test_no_document_can_leave_the_module_declaring_another_unit(
    compose_flat_pattern: Callable[..., ComposedSheet],
) -> None:
    """A DXF built OUTSIDE the factory cannot become bytes (the third-path lock).

    ``_new_dxf_document`` decides ``$INSUNITS`` once, but a factory can be bypassed —
    that is literally how this defect happened, a second serializer calling
    ``ezdxf.new`` directly. ``_dxf_bytes`` is the chokepoint every DXF must pass to
    become bytes at all, so the guard lives there: a future export path that invents
    its own document fails loudly instead of shipping a file that lies about itself.
    This is the same posture as the encoding guard beside it (F-3).
    """
    doc = compose_module._new_dxf_document()  # pyright: ignore[reportPrivateUsage]
    doc.units = ezdxf_units.M  # the defect, injected deliberately
    with pytest.raises(RuntimeError, match=r"\$INSUNITS=6"):
        compose_module._dxf_bytes(doc, "")  # pyright: ignore[reportPrivateUsage]


def test_the_factory_is_the_only_place_a_dxf_document_is_created() -> None:
    """One place decides the header; there is no second way to build a document.

    A source-level assertion because the property is structural, not behavioural: the
    runtime guard above catches a bypass at export time, and this catches it at review
    time, which is where a 1000x unit error is cheapest to catch.

    Counted over the AST, not with ``source.count("ezdxf.new(")`` — the first draft of
    this test did the latter and reddened on its own prose, because the factory's
    docstring names the call it replaced. A textual gate that a comment can trip is a
    gate people learn to edit around.
    """
    tree = ast.parse(Path(compose_module.__file__).read_text("utf-8"))
    sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "new"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ezdxf"
    ]
    assert len(sites) == 1, (
        f"{len(sites)} ezdxf.new() call sites in compose.py (lines "
        f"{[n.lineno for n in sites]}); the DXF header's unit declaration is decided "
        f"in _new_dxf_document() and nowhere else — route the new export path through "
        f"it rather than inheriting a second default"
    )
    assert any(
        isinstance(kw.arg, str) and kw.arg == "units" for kw in sites[0].keywords
    ), "the one ezdxf.new() call must pass units EXPLICITLY, never inherit the default"


def test_the_declared_unit_constant_is_millimetres() -> None:
    """:data:`DXF_UNITS` is the library's own mm enum, not a restated ``4``."""
    assert DXF_UNITS == ezdxf_units.MM
    assert ezdxf_units.decode(DXF_UNITS) == "mm"
