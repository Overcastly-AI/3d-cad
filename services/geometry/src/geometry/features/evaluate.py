"""Feature-tree evaluation — ordered dispatch + strict-prefix rule (design §4).

Implements the stateless documents→geometry evaluation contract of
docs/design/feature-tree.md §4 over the shared DTOs in
:mod:`loft_wire.features`. The evaluator walks the request's ordered
feature list exactly as given (§4.2 — documents applies the rollback bar
BEFORE sending, so a rolled-back tree arrives simply as a shorter list;
geometry never knows rollback exists) and applies the strict-prefix
partial-result rule (§4.3): the FIRST failure is marked ``error``, every
subsequent feature ``skipped``, and the artifact fields reflect the
last-good state.

Dispatch is a ``type → handler`` registry (:data:`FEATURE_HANDLERS`):
``datum`` (resolves an offset/parallel plane a later sketch sits on — not
body-affecting, total; docs/design/datum-planes.md), ``sketch`` (produces
input geometry, not body-affecting), ``extrude`` (the
first **body-affecting** feature, §4.3 — mutates the part's active body
via add/cut booleans; an additive ``merge=False`` starts a second body,
docs/design/multi-body.md §MB-0), ``revolve`` (sweeps a profile about a sketch-line
axis, sharing extrude's profile + boolean plumbing), ``sweep`` (the first
non-prismatic feature — sweeps a profile along a SECOND sketch's open path
wire), ``loft`` (blends a solid through two or more ordered section sketches),
``fillet`` (rounds
selected edges of that body chain), ``chamfer`` (bevels selected edges; both
body-affecting and both resolving edges through the shared geometric selector)
and ``shell`` (hollows the body to a uniform wall, opening picked faces resolved
through the SAME stage-1 planar-face signature the ``on_face`` datum uses) and
``draft`` (tapers picked faces by an angle about a principal-datum neutral plane
— the molding/casting release, reusing that SAME picked-face resolver) and
``import`` (brings an external STEP part in as the part's BASE body — the first
non-modeled body source, docs/design/step-import.md) and ``boolean`` (combines two
independently-built bodies named by their base features — the headline
multi-body feature; union/subtract/intersect all wired, docs/design/multi-body.md
§MB-1/§MB-2).
A feature that
validates against
the shared ``Feature`` union but has no registered handler is a per-feature
``feature_type_unsupported`` error — never a transport failure (§4.3: the
py-kit error envelope is reserved for transport/validation failures of the
evaluation call itself, not for geometry outcomes).

When the evaluated prefix ends with a body, the last-good body is measured
(GProp) and tessellated, and the GLB is stored content-addressed behind the
interim §7.8 seam (:mod:`geometry.mesh_store` — in-process LRU today, object
storage when the compose/queue item lands); ``mesh_glb_id`` carries the
content address either way. With no body-affecting feature ``ok``, the
artifact fields stay honestly ``null`` — exactly the §6 failure-flavour
shape.

Determinism (RESEARCH §9): evaluation order is the request list order, the
registry is consulted by key only (no iteration order participates), the
solver backend is bitwise-deterministic, and kernel builds/booleans are pure
functions of their inputs — the same request yields an identical result,
including ``mesh_glb_id`` (a content hash of a deterministic GLB).

Layout. This module is the public entry point and re-exports the names callers
import; the implementation is split by feature family:

* :mod:`geometry.features.tree` — :func:`evaluate_tree`, :func:`warm_rebuild_cache`,
  the ordered dispatch pass, publishing, and the rebuild-cache ladder;
* :mod:`geometry.features.dispatch` — :data:`FEATURE_HANDLERS`,
  :data:`BODY_AFFECTING_TYPES` and the guarded per-feature call;
* :mod:`geometry.features.state` — :class:`EvaluationState` (and its CM-6
  invalid-body gate) plus the shared add/cut body ops;
* :mod:`geometry.features.datum_sketch` — datum planes, sketches, and the plane /
  profile resolvers their consumers share;
* :mod:`geometry.features.sketch_solids` — extrude, revolve, sweep, loft;
* :mod:`geometry.features.modify` — fillet, chamfer, shell, draft;
* :mod:`geometry.features.hole` — the Hole feature;
* :mod:`geometry.features.pattern_mirror` — pattern and mirror;
* :mod:`geometry.features.sheet_metal_features` — base flange, edge flange, hem,
  corner relief;
* :mod:`geometry.features.bodies` — STEP import and the multi-body boolean.
"""

from geometry.features.datum_sketch import resolve_sketch_plane
from geometry.features.dispatch import BODY_AFFECTING_TYPES, FEATURE_HANDLERS
from geometry.features.state import (
    EvaluationState,
    FeatureHandler,
    InvalidBodyError,
    RecordedFeatureTools,
    RecordedToolGroup,
    ToolOp,
)
from geometry.features.tree import (
    TreeEvaluation,
    evaluate_tree,
    features_have_twist,
    rebuild_cache_stats,
    reset_rebuild_cache,
    tree_has_twist,
    tree_no_body_error,
    warm_rebuild_cache,
)

__all__ = [
    "BODY_AFFECTING_TYPES",
    "FEATURE_HANDLERS",
    "EvaluationState",
    "FeatureHandler",
    "InvalidBodyError",
    "RecordedFeatureTools",
    "RecordedToolGroup",
    "ToolOp",
    "TreeEvaluation",
    "evaluate_tree",
    "features_have_twist",
    "rebuild_cache_stats",
    "reset_rebuild_cache",
    "resolve_sketch_plane",
    "tree_has_twist",
    "tree_no_body_error",
    "warm_rebuild_cache",
]
