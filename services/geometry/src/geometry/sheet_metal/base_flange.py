"""Sheet-metal base flange — the part's gauge + defaults, riding on the body.

The base flange is mechanically an additive extrude (docs/design/sheet-metal.md
§4.1): the geometry evaluator builds it through the SAME
``geometry.kernel.build_profile_face`` + ``extrude_face`` thicken path a plain
extrude uses — there is **no new kernel geometry code** for this feature. What a
base flange adds over a plain extrude is the part's **sheet-metal metadata**:
the gauge ``thickness_mm`` plus the default ``k_factor`` / ``bend_radius_mm`` a
later edge-flange / unfold slice reads to compute a bend allowance
(``BA = angle * (radius + K * thickness)``, §1).

:class:`SheetMetalDefaults` is that metadata, carried on the evaluation state
keyed by the base-flange feature id (a body's identity IS its base-feature id,
multi-body §MB-0). It crosses NO service boundary — it is a pure-Python record
the geometry service threads internally, exactly like the kernel bodies in
``EvaluationState.bodies`` (CLAUDE.md service boundaries). The wire-level source
of truth for these values is
``py_kit.schemas.features.SheetMetalBaseFlangeParamsV1``; this record is the
service-internal projection the unfold consumes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SheetMetalDefaults:
    """The part's sheet-metal parameters, anchored on its base flange (§4.1/§5).

    ``thickness_mm`` is the uniform gauge; ``k_factor`` and ``bend_radius_mm`` are
    the part-defaults a later edge flange inherits (each edge flange may override
    them per-feature, §4.2). Frozen + deterministic — the same params always
    project to the same record (RESEARCH §9).
    """

    thickness_mm: float
    k_factor: float
    bend_radius_mm: float
