"""The extrude twist is DEPRECATED: read-only legacy, never authored anew.

Founder decision 2026-10-09 (docs/VISION.md "Base tooling and plugins"): base
tooling is the Fusion 360 / SolidWorks / Onshape core, and none of them twists
an extrude. A twisted prism is a Sweep with twist along a straight path, which
builds the same solid through the same kernel call.

User data is never lost: a stored extrude that carries ``twist_angle_deg``
still loads and rebuilds exactly as before, and an edit that carries its twist
and axis through unchanged (a distance change, a rename, a no-op save) is
allowed, as is one that removes the twist. Only a write that SETS a twist where
there was none, or CHANGES the stored one, is refused, with
:data:`EXTRUDE_TWIST_DEPRECATED_CODE`. The check runs where a feature is
authored (``POST``/``PATCH`` of a feature in the documents service); a version
restore, a ``.loft`` import and a duplicate copy stored data and do not run it.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from loft_wire.features import ExtrudeFeature, ExtrudeParamsV1, FeatureEnvelope

#: The typed error code of a refused extrude twist (a 422 envelope).
EXTRUDE_TWIST_DEPRECATED_CODE = "extrude_twist_deprecated"

#: The one message every authoring surface (API, loft-script) refuses with.
EXTRUDE_TWIST_DEPRECATED_MESSAGE = (
    "Extrude twist is deprecated: existing twisted extrudes still rebuild "
    "unchanged, but a twist cannot be added or changed on an extrude. Use a "
    "Sweep with twist along a straight path instead (the same solid)."
)


def _stored_twist(stored_params: Mapping[str, Any] | None) -> tuple[object, object]:
    """The stored row's (twist, axis), normalised as the wire model does; no
    twist for a row that is absent or does not parse as an extrude."""
    if stored_params is None:
        return (None, None)
    try:
        stored = ExtrudeParamsV1.model_validate(stored_params)
    except ValidationError:
        return (None, None)
    return (stored.twist_angle_deg, stored.twist_center)


def authors_extrude_twist(
    feature: FeatureEnvelope, stored_params: Mapping[str, Any] | None = None
) -> bool:
    """Whether writing *feature* would author a NEW or CHANGED extrude twist.

    *stored_params* is the row being replaced (``None`` on create). False for
    every non-extrude, for an untwisted extrude, and for a twisted one whose
    twist and axis equal the stored row's (the legacy data carried through).
    """
    if not isinstance(feature, ExtrudeFeature) or not feature.params.is_twisted:
        return False
    incoming = (feature.params.twist_angle_deg, feature.params.twist_center)
    return incoming != _stored_twist(stored_params)
