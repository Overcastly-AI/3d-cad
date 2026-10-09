"""The reference vocabulary every feature's params share (design §2.1).

Split out of :mod:`loft_wire.features` (FILE-SIZE-RATCHET) so that param
modules living beside it — :mod:`loft_wire.datum_angle` — can name an origin
plane, an earlier feature or a picked planar face without importing the
feature registry. :mod:`loft_wire.features` re-exports every name here, so
``from loft_wire.features import FeatureRef`` keeps working and the generated
contracts are unchanged (pydantic names schemas by class, not module).
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from loft_wire.signatures import PlanarFaceSignature

# --- §2.1 GeomRef — the reference vocabulary -----------------------------------


class DatumPlaneRef(BaseModel):
    """One of the three origin datum planes."""

    kind: Literal["datum_plane"]
    plane: Literal["XY", "XZ", "YZ"]


class FeatureRef(BaseModel):
    """A whole earlier feature of the same part (e.g. a sketch)."""

    kind: Literal["feature"]
    feature_id: uuid.UUID


#: Discriminated reference union. A ``subshape`` variant remains reserved here
#: for a future DIRECT sketch-on-subshape reference; the shipped sketch-on-a-face
#: path does NOT need it — a sketch sits on an ``on_face`` datum by the existing
#: ``FeatureRef`` variant (datum-planes §7), and the :class:`SubshapeRef` lives
#: inside that datum's params, not in this union.
GeomRef = Annotated[DatumPlaneRef | FeatureRef, Field(discriminator="kind")]


# --- Stage-1 topological naming: SubshapeRef (docs/design/topological-naming.md) --
#
# A SubshapeRef names ONE planar face of an earlier body-affecting feature's
# result by a geometric SIGNATURE (§2b), NOT an enumeration index (§1.3 rejects
# indices — they silently retarget). v1 scope is PLANAR FACES only (the
# sketch-on-a-face / datum-from-face foundation); edge/vertex signatures and the
# stage-2 provenance half are future additive members (§3, §10). The signature is
# pure pydantic — no kernel type crosses the boundary (§7.4): the geometry
# service computes it from the recomputed body and resolves it back to a face,
# entirely service-internal.
#
# HONEST STABILITY LIMIT (§7.3 — stated plainly, NOT oversold): a stage-1
# signature is BEST-EFFORT, not a provably-stable structural reference. It
# resolves the same face across the common edits (parametric changes that do not
# move the face; upstream inserts that do not touch it) and FAILS HONESTLY
# (``subshape_unresolved`` / ``subshape_ambiguous``) for most others — but under
# a drastic model change it CAN retarget to a coincidentally-congruent face (same
# normal/centroid/area) without erroring. It does NOT "never silently retarget";
# only the stage-2 provenance half (coordinate-blind) makes that structural.


class SelectorV1(BaseModel):
    """Stage-1 selector payload: the geometric signature alone (§3, §4).

    ``selector_version`` is the discriminator of the (currently single-member)
    ``Selector`` union — decoupled from feature ``param_version`` (§4). Stage 2
    adds a ``SelectorV2`` member (signature + provenance) additively, at which
    point ``Selector`` becomes ``Annotated[SelectorV1 | SelectorV2,
    Field(discriminator="selector_version")]`` with no change to persisted v1
    rows. pydantic forbids a discriminated single-member union, so ``Selector``
    is a plain alias until then (same idiom as :data:`FeatureData`).
    """

    selector_version: Literal[1] = 1
    signature: PlanarFaceSignature


#: Version-discriminated selector union (§4). One member (stage 1) today, so a
#: plain alias; stage 2 promotes it to a ``selector_version``-discriminated union.
Selector = SelectorV1


class SubshapeRef(BaseModel):
    """Stage-1 reference to ONE planar face of a body-affecting feature's result.

    (docs/design/topological-naming.md §4.) ``feature_id`` is the stage-1 anchor
    — "the prior body-affecting feature whose body I signature-match against"
    (§4), NOT necessarily the originating feature (stage 2 shifts it to the true
    originating feature). It materializes into ``feature_dependencies`` like a
    :class:`FeatureRef` (via the widened :func:`iter_feature_refs` /
    :func:`feature_references`), so deleting that feature is a write-time
    409-with-dependents. ``subshape_type`` is ``"face"`` only in v1 (edge/vertex
    reserved — §10).
    """

    kind: Literal["subshape"]
    feature_id: uuid.UUID
    subshape_type: Literal["face"]
    selector: Selector


#: One side of a midplane: an origin datum plane name, an EARLIER ``datum``
#: feature, or a picked PLANAR model face (the stage-1 signature the ``on_face``
#: datum resolves — topological-naming.md §4, reused not reinvented).
#: Discriminated on ``kind`` (``datum_plane`` | ``feature`` | ``subshape``);
#: only FACE subshape refs validate (an edge ref has ``subshape_type: "edge"``
#: and is a request-validation 422).
MidplaneSide = Annotated[
    DatumPlaneRef | FeatureRef | SubshapeRef, Field(discriminator="kind")
]
