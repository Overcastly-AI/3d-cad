"""The volume of an offset-surface body is fast AND right (GEOMETRY-QA 2026-09-25 F2).

``b29fa88`` routed every body with a ``Geom_OffsetSurface`` face to OCCT's
Gauss-Kronrod rule. It is accurate, but on ordinary shelled spline parts it took
43-196 s (QA case 2: 51.5 s; the spline-slot disc shelled 1 mm: 148 s, 196 s
after a STEP import), past the gateway's 90 s. Before it, the adaptive rule took
0.2-2.5 s and was wrong by up to 97 mm^3.

:func:`geometry.kernel.properties.volume_properties` now integrates each offset
face ITSELF: Gauss-Legendre per knot span of its basis over the face's
parameter rectangle, where the face is bounded by two u- and two v-isolines
(every shell of an extrude is). It uses the same divergence-theorem field as
OCCT's per-face integrator, so the other faces are summed with it unchanged.
The rest of the body goes through OCCT's adaptive per-face rule as before.

Pinned here, on QA's own bodies (built by QA's helpers, loaded from its file):

* the time, against ceilings stated below, on case 2 and on the shelled disc
  (as built and after a STEP re-import);
* the reading, against the Gauss-Kronrod reading of the same body where
  Gauss-Kronrod is affordable (the golden), and against the analytic truth;
* the bounded-time fallback for an offset face that is NOT an isoline
  rectangle, within its documented accuracy.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import importlib.util
import json
import time
from functools import cache
from pathlib import Path
from types import ModuleType

import geometry.kernel.properties as properties
import pytest
from build123d import Solid
from geometry.harness import build_model_solid, load_model_request
from geometry.kernel import export_step_bytes
from geometry.kernel.imports import import_step_solid
from geometry.kernel.properties import VOLUME_EPS, volume_integrand, volume_properties
from geometry.kernel.shell import shell_body
from geometry.kernel.types import BodyShape
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

TESTS = Path(__file__).resolve().parent
GOLDENS = TESTS.parent / "goldens"

#: Ceilings (s) on ``volume_properties`` alone, on this 4-core box. Measured
#: with the per-face route: case 2 0.10 s, the shelled disc 1.4 s as built and
#: 1.3 s re-imported; the pre-b29fa88 adaptive rule took 0.20 s and 2.47 s. On
#: Gauss-Kronrod they took 51.5 s, 148 s and 196 s. Each ceiling is about 10x the
#: measured cost and a tenth of the Gauss-Kronrod one.
CASE2_CEILING_S = 5.0
DISC_CEILING_S = 15.0

#: Largest disagreement (mm^3) allowed between the per-face route and OCCT's
#: Gauss-Kronrod rule on the golden, where both are affordable. Measured:
#: 1.0e-8 (per-face +1.85e-7, Gauss-Kronrod +1.775e-7 from the analytic truth).
AGREEMENT_MM3 = 5e-8

#: The fallback for an offset face that is not an isoline rectangle converts it
#: with ``BRepBuilderAPI_NurbsConvert``, which APPROXIMATES an offset (1.7e-6 mm
#: from the true surface on the golden). Measured on the golden: +6.65e-6 mm^3
#: from the truth. The bound states the accuracy that route gives up.
FALLBACK_MM3 = 2e-5


@cache
def _qa() -> ModuleType:
    """Geometry QA's test module, for its case-2 body and its truth method."""
    path = TESTS / "test_offset_surface_qa.py"
    spec = importlib.util.spec_from_file_location("offset_surface_qa", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _golden(name: str) -> BodyShape:
    model = (GOLDENS / name / "model.json").read_text()
    return build_model_solid(load_model_request(model))


@cache
def _shelled_disc() -> Solid:
    """QA's slowest body: the spline-slot golden shelled 1 mm, top open."""
    disc = _golden("extrude-cut-spline-slots-6x-disc-r20-h10")
    top = max(disc.faces(), key=lambda f: f.center().Z)
    body = shell_body(disc, [top], 1.0)
    assert isinstance(body, Solid)
    return body


def _timed(body: BodyShape) -> tuple[float, float]:
    start = time.perf_counter()
    reading = volume_properties(body)
    return time.perf_counter() - start, reading.volume


def test_case2_volume_is_fast() -> None:
    elapsed, _ = _timed(_qa()._case2())
    assert elapsed < CASE2_CEILING_S, f"{elapsed:.1f} s"


def test_the_shelled_disc_volume_is_fast() -> None:
    elapsed, _ = _timed(_shelled_disc())
    assert elapsed < DISC_CEILING_S, f"{elapsed:.1f} s"


def test_the_reimported_shelled_disc_volume_is_fast() -> None:
    body = import_step_solid(export_step_bytes(_shelled_disc()).decode())
    elapsed, _ = _timed(body)
    assert elapsed < DISC_CEILING_S, f"{elapsed:.1f} s"


def _gauss_kronrod(body: BodyShape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumePropertiesGK_s(
        volume_integrand(body), props, VOLUME_EPS, False, False, True, False, False
    )
    return float(props.Mass())


def test_the_per_face_route_agrees_with_gauss_kronrod() -> None:
    body = _golden("shell-spline-prism-30x10-t1")
    assert volume_properties(body).volume == pytest.approx(
        _gauss_kronrod(body), abs=AGREEMENT_MM3
    )


def test_a_non_rectangular_offset_face_falls_back_in_bounded_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An offset face the route cannot integrate itself is converted instead:
    bounded time, and the accuracy the conversion gives up, stated."""

    def no_rectangle(_face: object) -> None:
        return None

    monkeypatch.setattr(properties, "_isoline_rectangle", no_rectangle)
    body = _golden("shell-spline-prism-30x10-t1")
    truth = json.loads(
        (GOLDENS / "shell-spline-prism-30x10-t1" / "expected.json").read_text()
    )["properties"]["volume"]
    elapsed, volume = _timed(body)
    assert elapsed < CASE2_CEILING_S
    assert volume == pytest.approx(truth, abs=FALLBACK_MM3)
