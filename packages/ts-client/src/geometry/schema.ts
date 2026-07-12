// GENERATED — do not edit; run `just gen`.
// Types for the geometry service (source contract: packages/contracts/geometry.openapi.json).
export interface paths {
    "/api/v1/evaluate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Evaluate
         * @description Evaluate an ordered feature-tree prefix (feature-tree design §4).
         *
         *     Stateless: documents sends the full ordered, validated, current-version
         *     feature list (rollback bar already applied); the response is per-feature
         *     statuses plus object-storage artifact references, under the strict-prefix
         *     rule (§4.3 — first failure ``error``, the rest ``skipped``). A feature
         *     failure is a **200 with per-feature errors**; the py-kit error envelope
         *     stays reserved for transport/validation failures of this call itself.
         */
        post: operations["evaluate_api_v1_evaluate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export
         * @description Build a parametric shape and export it as a STEP or STL download.
         */
        post: operations["export_api_v1_export_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/export/tree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Tree
         * @description Evaluate a feature tree and export its LAST-GOOD body as STEP/STL.
         *
         *     Reuses the evaluate-tree machinery verbatim (``evaluate_tree`` — the same
         *     ordered dispatch + strict-prefix rule as ``POST /api/v1/evaluate``, no
         *     duplicated logic), then exports the resulting kernel body through the
         *     SAME format dispatch parametric shapes use (``export_solid``). A tree that
         *     produces no body — a strict-prefix failure or a body-less tree — is a
         *     clean 422 ``tree_export_failed`` envelope (never a 500, never a partial
         *     file); the failing ``FeatureError`` rides in the envelope details.
         *     Deterministic: the STEP timestamp is pinned exactly as on the shape path.
         */
        post: operations["export_tree_api_v1_export_tree_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/measure": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Measure
         * @description Exact nearest distance between two transient measurement targets.
         *
         *     **Stateless** (CLAUDE.md): a one-shot query, nothing persisted. Each
         *     target is either a POINT (explicit world coordinates — a picked
         *     vertex/snap point, exact on its own) or an EDGE (a transient 0-based index
         *     into the deterministic edge list of a body geometry recomputes from the
         *     supplied ``tree``). Distances come from the exact B-rep via OCCT, so every
         *     supported case — point-point, point-edge, edge-edge, straight OR curved —
         *     is EXACT; nothing is read from the tessellation. The response carries the
         *     minimum distance, its (dx, dy, dz) components, the two witness points, and
         *     (for two straight edges) the acute angle between them. See
         *     :mod:`py_kit.schemas.measure` for the full contract + fidelity rationale.
         *
         *     A tree that recomputes to no body is a clean 422 ``tree_measure_failed``
         *     envelope; an out-of-range edge index is a 422 ``edge_index_out_of_range``.
         */
        post: operations["measure_api_v1_measure_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/meshes/{mesh_glb_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Fetch Mesh
         * @description Fetch the GLB artifact a tree evaluation returned by content address.
         *
         *     The interim §7.8 mesh-delivery path: `mesh_glb_id` is a pure content
         *     address, so this route keeps the same contract when the in-process store
         *     is replaced by object storage (docs/design/feature-tree.md §7.8).
         */
        get: operations["fetch_mesh_api_v1_meshes__mesh_glb_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/overlay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Overlay
         * @description Pickable selection geometry of an evaluated feature tree's body (#6b).
         *
         *     **Stateless** (CLAUDE.md): recomputes ``request.tree`` (the SAME ordered
         *     dispatch + strict-prefix rule as ``/evaluate`` and ``/measure``, reusing
         *     ``evaluate_tree``) and returns the last-good body's EXACT pickable geometry:
         *     ``vertices`` (world-mm snap points in ``body.vertices()`` order — echo one
         *     back as a measure ``PointTarget`` for an exact point measurement) and
         *     ``edges`` in ``body.edges()`` order — the SAME enumeration ``/measure``
         *     resolves ``EdgeTarget.index`` against, so ``edges[i]`` IS the edge
         *     ``EdgeTarget(index=i)`` measures. Each edge carries a kind tag, its two
         *     endpoint coordinates, and a polyline sampled at the tree's
         *     ``linear_deflection`` (the SAME tolerance the mesh uses — no new epsilon).
         *
         *     Both index spaces are TRANSIENT — valid for this request/tree only, NOT
         *     stable across edits (stable named references are topological naming, Phase
         *     2). A tree that recomputes to no body is a clean 422 ``tree_overlay_failed``
         *     envelope. See :mod:`py_kit.schemas.overlay` for the full contract.
         */
        post: operations["overlay_api_v1_overlay_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sketch/chamfer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sketch Chamfer
         * @description Bevel a sketch corner between two lines with a straight line (BACKLOG #5).
         *
         *     **Stateless** (CLAUDE.md): the corner between lines ``a`` and ``b`` is
         *     replaced by a straight chamfer line across two equal-setback points at
         *     ``distance`` along each leg: both lines are trimmed to those points (ids
         *     preserved) and the chamfer line is appended with a fresh deterministic id
         *     ``f"{a}.{n}"``. Same corner contract, result shape, and determinism as
         *     ``/sketch/fillet``. **v1 is line-line only.**
         *
         *     Errors are the same 422 codes as fillet: ``sketch_target_not_found``,
         *     ``sketch_unsupported_entity``, ``sketch_corner_not_found``,
         *     ``sketch_corner_too_large`` (distance exceeds a leg's available length),
         *     ``sketch_degenerate_result``.
         */
        post: operations["sketch_chamfer_api_v1_sketch_chamfer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sketch/extend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sketch Extend
         * @description Extend a sketch curve's picked end to the nearest neighbor it meets.
         *
         *     **Stateless** (CLAUDE.md): the picked end (the endpoint nearer ``pick``)
         *     grows along the target's own supporting line/circle to the closest entity
         *     in that direction. Line and arc targets are supported; a circle or point
         *     has no free end (``sketch_unsupported_entity``). Deterministic (RESEARCH
         *     §9). Errors are 422s: ``sketch_target_not_found``,
         *     ``sketch_unsupported_entity``, ``sketch_extend_no_target`` (nothing to meet
         *     in the extension direction), ``sketch_degenerate_result``.
         */
        post: operations["sketch_extend_api_v1_sketch_extend_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sketch/fillet": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sketch Fillet
         * @description Round a sketch corner between two lines with a tangent arc (BACKLOG #5).
         *
         *     **Stateless** (CLAUDE.md): a one-shot geometry edit, nothing persisted and no
         *     kernel type crosses the boundary. The corner between lines ``a`` and ``b`` is
         *     replaced by a tangent arc of ``radius``: both lines are trimmed to their
         *     tangent points (ids preserved) and the arc is appended with a fresh
         *     deterministic id ``f"{a}.{n}"`` (see
         *     :class:`py_kit.schemas.sketch.SketchCornerResult`). Exact closed-form and
         *     deterministic (RESEARCH §9). **v1 is line-line only.**
         *
         *     Errors are 422s with legible codes, never 500s: ``sketch_target_not_found``
         *     (a target id absent), ``sketch_unsupported_entity`` (a non-line target — a
         *     line-arc/arc-arc corner is deferred), ``sketch_corner_not_found`` (the lines
         *     are parallel/collinear or the same entity — no isolated corner),
         *     ``sketch_corner_too_large`` (radius exceeds a leg's available length),
         *     ``sketch_degenerate_result`` (a zero-length result).
         */
        post: operations["sketch_fillet_api_v1_sketch_fillet_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sketch/mirror": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sketch Mirror
         * @description Mirror sketch curves — reflected copies about an axis line (symmetry).
         *
         *     **Stateless** (CLAUDE.md): a one-shot geometry op, nothing persisted and no
         *     kernel type crosses the boundary. Like offset (and unlike trim), mirror
         *     **ADDS** geometry: the sources are unchanged and the response carries only
         *     the NEW reflected copies — one per ``target``, in order — each with a fresh
         *     deterministic id ``f"{source}.{n}"`` inheriting the source's construction
         *     flag. Every entity kind is reflectable; a mirrored **arc** is start/end-
         *     swapped to stay CCW (reflection reverses orientation). The axis is a line
         *     entity id or two points (see ``MirrorAxis``).
         *
         *     Distinct from the ``symmetric`` CONSTRAINT: this CREATES geometry, it does
         *     not enforce symmetry, and v1 does NOT auto-add symmetric constraints between
         *     a source and its copy (geometry-only). Exact closed-form (rational foot-of-
         *     perpendicular) and deterministic (RESEARCH §9).
         *
         *     Every entity kind (point, line, circle, arc) is reflectable, so there is no
         *     unsupported-target path. Errors are 422s with legible codes, never 500s:
         *     ``sketch_target_not_found`` (a target id — or a ``MirrorAxisEntity`` axis id
         *     — absent), ``sketch_mirror_axis_not_line`` (axis entity is not a line),
         *     ``sketch_mirror_degenerate_axis`` (zero-length axis).
         */
        post: operations["sketch_mirror_api_v1_sketch_mirror_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sketch/offset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sketch Offset
         * @description Offset a sketch curve — a parallel copy at a signed distance (rib/web).
         *
         *     **Stateless** (CLAUDE.md): a one-shot geometry op, nothing persisted and no
         *     kernel type crosses the boundary. Unlike trim (which rewrites the target),
         *     offset **ADDS** geometry: the source is unchanged and the response carries
         *     only the NEW offset entity, with a fresh deterministic id ``f"{target}.{n}"``
         *     inheriting the source's construction flag. Sign convention: the copy is
         *     displaced along the curve's **left-hand normal** (forward direction rotated
         *     +90° CCW), so ``+distance`` = left of the directed curve; a CCW arc/circle's
         *     left normal points inward, so ``+distance`` shrinks its radius. Line / arc /
         *     circle are supported (single-entity v1; chain offset is deferred).
         *     Exact closed-form and deterministic (RESEARCH §9).
         *
         *     Errors are 422s with legible codes, never 500s: ``sketch_target_not_found``,
         *     ``sketch_unsupported_entity`` (a free-point target),
         *     ``sketch_offset_zero_distance`` (zero/NaN/inf distance),
         *     ``sketch_degenerate_result`` (inward offset drives an arc/circle radius ≤ 0).
         */
        post: operations["sketch_offset_api_v1_sketch_offset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sketch/trim": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sketch Trim
         * @description Trim a sketch curve at the pick, returning the rewritten entity list.
         *
         *     **Stateless** (CLAUDE.md): a one-shot geometry edit, nothing persisted and
         *     no kernel type crosses the boundary. The target curve is cut at its nearest
         *     intersection with the other entities on each side of ``pick`` and the picked
         *     segment removed (Onshape/Fusion "cut at intersection"); an unbounded side
         *     runs to the curve end, and a curve with no intersection at all is deleted
         *     whole. Splits may add a second entity with a fresh deterministic id (see
         *     :class:`py_kit.schemas.sketch.SketchEditResult`). Deterministic (RESEARCH
         *     §9): identical input yields coordinate-identical output.
         *
         *     Errors are 422s with legible codes, never 500s: ``sketch_target_not_found``
         *     (target id absent), ``sketch_unsupported_entity`` (a free-point target),
         *     ``sketch_pick_not_on_target`` (pick projects off the curve's extent).
         */
        post: operations["sketch_trim_api_v1_sketch_trim_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tessellate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Tessellate
         * @description Build a parametric shape, tessellate it, return the GLB mesh.
         */
        post: operations["tessellate_api_v1_tessellate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tessellate/meta": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Tessellate Meta
         * @description JSON twin of ``/tessellate``: mass properties + mesh stats, no mesh.
         */
        post: operations["tessellate_meta_api_v1_tessellate_meta_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AllEdgesSelector
         * @description Every edge of the target body (the whole-body round-over).
         */
        AllEdgesSelector: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "all_edges";
        };
        /**
         * AxisParallelEdgesSelector
         * @description Every straight edge parallel to a world axis (e.g. Z = the vertical
         *     edges of an upright prism). Curved edges never match — an arc has no
         *     single direction. Deterministic and rebuild-stable: a geometric predicate,
         *     not a stored edge id.
         */
        AxisParallelEdgesSelector: {
            /**
             * Axis
             * @enum {string}
             */
            axis: "X" | "Y" | "Z";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "axis_parallel";
        };
        /**
         * BoundingBox
         * @description Axis-aligned bounding box (mm), exact (not mesh-inflated).
         */
        BoundingBox: {
            max: components["schemas"]["Vec3"];
            min: components["schemas"]["Vec3"];
        };
        /**
         * BoxParams
         * @description Axis-aligned box dimensions (mm); the min corner sits at the origin.
         */
        BoxParams: {
            /**
             * X
             * @description Size along X (mm)
             */
            x: number;
            /**
             * Y
             * @description Size along Y (mm)
             */
            y: number;
            /**
             * Z
             * @description Size along Z (mm)
             */
            z: number;
        };
        /**
         * ChamferFeature
         * @description ``{"type": "chamfer", "version": 1, "params": {...}}`` envelope.
         */
        ChamferFeature: {
            params: components["schemas"]["ChamferParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "chamfer";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * ChamferParamsV1
         * @description Bevel selected edges of the current body chain with a symmetric distance.
         *
         *     The chamfer sibling of :class:`FilletParamsV1`: it reuses the SAME
         *     :class:`EdgeSelector` predicate (the shared edge-reference plumbing —
         *     design §2.4, NOT topological naming; Phase 2 is ``SubshapeRef``), so a UI
         *     or caller names chamfer edges exactly as it names fillet edges. Like a
         *     fillet it operates on the implicit single body chain (design §7.6), so it
         *     carries no ``FeatureRef``; its dependency on the prior body-affecting
         *     feature is the tree order.
         *
         *     ``distance_mm`` is the symmetric setback measured along each of the edge's
         *     two adjacent faces (a 45° bevel): the flat chamfer face is the hypotenuse.
         */
        ChamferParamsV1: {
            /**
             * Distance Mm
             * @description Symmetric chamfer setback along each adjacent face (mm) — a 45° bevel
             */
            distance_mm: number;
            /**
             * Edges
             * @description Which edges of the current body to bevel (geometric predicate, not topological naming — design §2.4; same selector union as fillet)
             */
            edges: components["schemas"]["AllEdgesSelector"] | components["schemas"]["AxisParallelEdgesSelector"];
        };
        /**
         * CircularPatternParamsV1
         * @description A circular (ring) pattern about a world-space axis.
         *
         *     ``count`` INCLUDES the seed. Instances are placed every ``angle_deg /
         *     count`` degrees about the axis for ``k = 1..count-1``, so the closing
         *     position at ``angle_deg`` is EXCLUSIVE (omitted): ``angle_deg = 360`` with
         *     ``count = 4`` yields a clean 4-up ring at 0/90/180/270° with no overlapping
         *     twin at 360° ≡ 0°. To place N instances INCLUSIVELY across a partial arc of
         *     ``a`` degrees (both ends occupied), set ``angle_deg = a * count / (count -
         *     1)``. See the module design note above for the connected-solid requirement.
         */
        CircularPatternParamsV1: {
            /**
             * Angle Deg
             * @description TOTAL sweep about the axis (degrees). Instances are spaced `angle_deg / count`, so `angle_deg = 360` is a full ring; the closing instance at `angle_deg` is EXCLUSIVE. Must be in (0, 360] when count > 1 (a `pattern_bad_angle` rebuild error otherwise).
             */
            angle_deg: number;
            /** @description Direction of the axis of rotation; only its DIRECTION is used (magnitude ignored; a zero-length vector is a `pattern_bad_axis` rebuild error) */
            axis_direction: components["schemas"]["Vec3"];
            /** @description A point on the world-space axis of rotation (mm) */
            axis_point: components["schemas"]["Vec3"];
            /**
             * Count
             * @description TOTAL instances INCLUDING the seed; an integer >= 1. `count < 1` is a `pattern_bad_count` rebuild error; `count = 1` is a no-op.
             */
            count: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "circular";
        };
        /**
         * CoincidentConstraint
         * @description Two named points share a location.
         */
        CoincidentConstraint: {
            a: components["schemas"]["EntityPointRef"];
            b: components["schemas"]["EntityPointRef"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "coincident";
        };
        /**
         * ConcentricConstraint
         * @description Two circles/arcs share a center point.
         *
         *     Relates two whole circle/arc entities by id (order immaterial); the solver
         *     ties their centers together (there is no separate radius relation — use
         *     :class:`EqualConstraint` for that). Removes two degrees of freedom. Both
         *     entities must be a circle or an arc; a line has no center and is rejected.
         */
        ConcentricConstraint: {
            /**
             * A
             * @description Sketch-local entity id, e.g. 'e1'
             */
            a: string;
            /**
             * B
             * @description Sketch-local entity id, e.g. 'e1'
             */
            b: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "concentric";
        };
        /**
         * CylinderParams
         * @description Right circular cylinder (mm): base disc centred at the origin in the
         *     XY plane, axis along +Z.
         */
        CylinderParams: {
            /**
             * Height
             * @description Height along +Z (mm)
             */
            height: number;
            /**
             * Radius
             * @description Radius (mm)
             */
            radius: number;
        };
        /**
         * DatumPlaneRef
         * @description One of the three origin datum planes.
         */
        DatumPlaneRef: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "datum_plane";
            /**
             * Plane
             * @enum {string}
             */
            plane: "XY" | "XZ" | "YZ";
        };
        /**
         * DistanceConstraint
         * @description Driving dimension: the length of a line (mm).
         */
        DistanceConstraint: {
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "distance";
            /**
             * Value Mm
             * @description Line length (mm)
             */
            value_mm: number;
        };
        /**
         * EdgeTarget
         * @description A measurement endpoint that is a B-rep edge of the recomputed body.
         *
         *     ``index`` is a TRANSIENT 0-based index into the recomputed body's
         *     deterministic edge list (build123d ``.edges()`` / OCCT exploration order —
         *     the same order the B-rep edge overlay enumerates). It is meaningful only
         *     against the ``tree`` sent in the SAME request and is NOT stable across
         *     edits (stable named references are topological naming, Phase 2 —
         *     feature-tree design §2.4). Requires :attr:`MeasureRequest.tree`.
         */
        EdgeTarget: {
            /**
             * Index
             * @description 0-based index into the recomputed body's deterministic edge list (transient — valid for this request/tree only, not stable across edits)
             */
            index: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "edge";
        };
        /**
         * EntityPointRef
         * @description Names one point of one entity, e.g. ``{"entity": "e1", "point": "end"}``.
         */
        EntityPointRef: {
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /**
             * Point
             * @enum {string}
             */
            point: "start" | "end" | "center" | "position";
        };
        /**
         * EqualConstraint
         * @description Two entities of the same class have equal size.
         *
         *     Two lines get equal length; two circles, two arcs, or a circle-and-arc
         *     pair get equal radius. Relates two **whole** entities by id (order is
         *     immaterial — equality is symmetric); the solver dispatches to the matching
         *     planegcs variant from the resolved entity kinds. A mismatched pair
         *     (e.g. a line and a circle) has no equal-size relation and is rejected at
         *     solve time. Removes one degree of freedom.
         */
        EqualConstraint: {
            /**
             * A
             * @description Sketch-local entity id, e.g. 'e1'
             */
            a: string;
            /**
             * B
             * @description Sketch-local entity id, e.g. 'e1'
             */
            b: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "equal";
        };
        /**
         * EvaluateTreeRequest
         * @description Evaluate an ordered, validated, current-version feature list (§4.2).
         *
         *     Documents applies the rollback bar BEFORE sending: geometry receives
         *     exactly the prefix to evaluate and never needs to know rollback exists.
         */
        EvaluateTreeRequest: {
            /**
             * Features
             * @description Ordered prefix (rollback already applied)
             */
            features: components["schemas"]["EvaluatedFeatureInput"][];
            /**
             * Linear Deflection
             * @description Presentation parameter (mm), NEVER persisted per feature (design §8.3)
             * @default 0.1
             */
            linear_deflection: number;
            /**
             * Part Id
             * Format: uuid
             */
            part_id: string;
            /**
             * Tree Version
             * @description Echoed back; cache/correlation key
             */
            tree_version: number;
        };
        /**
         * EvaluateTreeResult
         * @description Statuses plus object-storage references — never kernel types, never
         *     inline meshes (§4.1). A feature failure is a 200 with per-feature errors;
         *     the envelope stays reserved for transport/validation failures (§4.3).
         */
        EvaluateTreeResult: {
            /**
             * Features
             * @description Same order as the request
             */
            features: components["schemas"]["FeatureResult"][];
            /**
             * Last Good Feature Id
             * @description Which feature the artifact reflects
             */
            last_good_feature_id: string | null;
            /**
             * Mesh Glb Id
             * @description Content-addressed artifact key (sha256:<hex>) of the LAST-GOOD body mesh; fetch via the geometry service's GET /api/v1/meshes/{mesh_glb_id} (interim §7.8 path — the key becomes the object-storage key when that successor lands)
             */
            mesh_glb_id: string | null;
            /**
             * Part Id
             * Format: uuid
             */
            part_id: string;
            /** @description Mass properties of the last-good body */
            properties: components["schemas"]["ShapeProperties"] | null;
            /** Tree Version */
            tree_version: number;
        };
        /**
         * EvaluatedFeatureInput
         * @description One ordered entry of an evaluation request.
         */
        EvaluatedFeatureInput: {
            /** Feature */
            feature: components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["PatternFeature"];
            /**
             * Id
             * Format: uuid
             * @description Feature identity for refs + result keying
             */
            id: string;
        };
        /**
         * ExportRequest
         * @description Build a parametric shape and export it as a downloadable CAD file.
         *
         *     STEP exports the exact B-rep — the deflection fields are meaningless for
         *     it and ignored. STL is a faceted approximation; its quality fields default
         *     to the tessellation defaults so the exported mesh matches what the
         *     viewport shows.
         */
        ExportRequest: {
            /**
             * Angular Deflection
             * @description STL facet angular deflection (rad) between adjacent segments; ignored for STEP (exact B-rep)
             * @default 0.1
             */
            angular_deflection: number;
            /**
             * Format
             * @description Export file format: STEP (exact B-rep) or STL (faceted mesh)
             * @enum {string}
             */
            format: "step" | "stl";
            /**
             * Linear Deflection
             * @description STL facet linear deflection (mm), same semantics as tessellation; ignored for STEP (exact B-rep)
             * @default 0.1
             */
            linear_deflection: number;
            /**
             * Params
             * @description Parameters of the selected shape kind
             */
            params: components["schemas"]["BoxParams"] | components["schemas"]["CylinderParams"];
            /**
             * Shape
             * @description Shape kind; must match the params model
             * @enum {string}
             */
            shape: "box" | "cylinder";
        };
        /**
         * ExportTreeRequest
         * @description Evaluate a feature tree and export its LAST-GOOD body as a CAD file.
         *
         *     Extends :class:`EvaluateTreeRequest` — the SAME ordered, rollback-applied
         *     feature list the evaluate endpoint takes (DRY: one tree contract,
         *     evaluated then exported) — with the export format selection. The geometry
         *     service reuses the evaluate-tree dispatch to produce the body, then exports
         *     THAT body (never a re-modelled shape).
         *
         *     STEP exports the exact B-rep, so the deflection fields are meaningless for
         *     it and ignored. STL is a faceted approximation; ``linear_deflection``
         *     (inherited) and ``angular_deflection`` default to the tessellation defaults
         *     so the exported mesh matches what the viewport shows.
         *
         *     If the tree produces no body — a strict-prefix failure (§4.3) or a tree
         *     with no body-affecting feature — export is a clean error, never a file:
         *     the geometry service answers a 422 ``tree_export_failed`` envelope, not a
         *     partial download.
         */
        ExportTreeRequest: {
            /**
             * Angular Deflection
             * @description STL facet angular deflection (rad) between adjacent segments; ignored for STEP (exact B-rep)
             * @default 0.1
             */
            angular_deflection: number;
            /**
             * Features
             * @description Ordered prefix (rollback already applied)
             */
            features: components["schemas"]["EvaluatedFeatureInput"][];
            /**
             * Format
             * @description Export file format: STEP (exact B-rep) or STL (faceted mesh)
             * @enum {string}
             */
            format: "step" | "stl";
            /**
             * Linear Deflection
             * @description Presentation parameter (mm), NEVER persisted per feature (design §8.3)
             * @default 0.1
             */
            linear_deflection: number;
            /**
             * Part Id
             * Format: uuid
             */
            part_id: string;
            /**
             * Tree Version
             * @description Echoed back; cache/correlation key
             */
            tree_version: number;
        };
        /**
         * ExtrudeFeature
         * @description ``{"type": "extrude", "version": 1, "params": {...}}`` envelope.
         */
        ExtrudeFeature: {
            params: components["schemas"]["ExtrudeParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "extrude";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * ExtrudeParamsV1
         * @description Linear extrusion of an earlier sketch feature's profile.
         */
        ExtrudeParamsV1: {
            /**
             * Direction
             * @default normal
             * @enum {string}
             */
            direction: "normal" | "reverse";
            /**
             * Distance Mm
             * @description Extrusion depth (mm)
             */
            distance_mm: number;
            /**
             * Operation
             * @enum {string}
             */
            operation: "add" | "cut";
            /** @description Must resolve to an EARLIER sketch feature (design §2.2) */
            profile: components["schemas"]["FeatureRef"];
        };
        /**
         * FeatureError
         * @description Why one feature failed to evaluate (§4.3).
         */
        FeatureError: {
            /**
             * Code
             * @description Machine-readable: "profile_not_closed", "boolean_failed", "reference_unresolved", ...
             */
            code: string;
            /**
             * Message
             * @description Human-readable, kernel detail sanitized
             */
            message: string;
            /**
             * Upstream Feature Id
             * @description Set when the root cause is an earlier feature's output
             */
            upstream_feature_id?: string | null;
        };
        /**
         * FeatureRef
         * @description A whole earlier feature of the same part (e.g. a sketch).
         */
        FeatureRef: {
            /**
             * Feature Id
             * Format: uuid
             */
            feature_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "feature";
        };
        /**
         * FeatureResult
         * @description Per-feature evaluation status. Strict-prefix rule (§4.3): the first
         *     failure is ``error``, every subsequent feature ``skipped``.
         */
        FeatureResult: {
            /** @description Typed per-feature payload for ok features that produce one (§7.10): solved sketch geometry today; future feature types add kind-tagged variants additively. */
            data?: components["schemas"]["SolvedSketchData"] | null;
            error?: components["schemas"]["FeatureError"] | null;
            /**
             * Feature Id
             * Format: uuid
             */
            feature_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "error" | "skipped";
        };
        /**
         * FilletFeature
         * @description ``{"type": "fillet", "version": 1, "params": {...}}`` envelope.
         */
        FilletFeature: {
            params: components["schemas"]["FilletParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "fillet";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * FilletParamsV1
         * @description Round selected edges of the current body chain with a constant radius.
         *
         *     ``edges`` is a geometric :class:`EdgeSelector` predicate over the body that
         *     exists at this feature's point in the tree — NOT a topological-naming
         *     reference (design §2.4; that is Phase 2). No feature reference: like an
         *     extrude ``cut``, a fillet operates on the implicit single body chain
         *     (design §7.6), so its dependency on the prior body-affecting feature is the
         *     tree order, not a ``FeatureRef``.
         */
        FilletParamsV1: {
            /**
             * Edges
             * @description Which edges of the current body to round (geometric predicate, not topological naming — design §2.4)
             */
            edges: components["schemas"]["AllEdgesSelector"] | components["schemas"]["AxisParallelEdgesSelector"];
            /**
             * Radius Mm
             * @description Fillet radius (mm)
             */
            radius_mm: number;
        };
        /**
         * FixedConstraint
         * @description Anchor a named point at its current (input) coordinates.
         *
         *     Every fully-constrained sketch needs an anchor — without one, a rigid
         *     solution still floats with two translational degrees of freedom.
         */
        FixedConstraint: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "fixed";
            point: components["schemas"]["EntityPointRef"];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HorizontalConstraint
         * @description A line is parallel to the sketch X axis.
         */
        HorizontalConstraint: {
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "horizontal";
        };
        /**
         * LinearPatternParamsV1
         * @description A linear (row/grid-line) pattern along a world-space direction.
         *
         *     ``count`` INCLUDES the seed (instance 0 = the existing body), so a row of
         *     N total bodies is ``count = N``; ``count = 1`` is a no-op (seed only).
         *     Copies are placed at ``spacing_mm * k`` along the unit ``direction`` for
         *     ``k = 1..count-1``. See the module design note above for what "the body"
         *     means and the connected-solid requirement.
         */
        LinearPatternParamsV1: {
            /**
             * Count
             * @description TOTAL instances INCLUDING the seed (instance 0); an integer >= 1. `count < 1` is a `pattern_bad_count` rebuild error; `count = 1` is a no-op (the body is unchanged).
             */
            count: number;
            /** @description World-space direction of the row; only its DIRECTION is used (magnitude ignored; a zero-length vector is a `pattern_bad_direction` rebuild error) */
            direction: components["schemas"]["Vec3"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "linear";
            /**
             * Spacing Mm
             * @description Centre-to-centre step between consecutive instances along `direction` (mm); must be > 0 (a `pattern_bad_spacing` rebuild error otherwise). Validated at rebuild, not at parse (see module note).
             */
            spacing_mm: number;
        };
        /**
         * MeasureRequest
         * @description Measure the nearest distance between two targets (stateless, one-shot).
         *
         *     ``tree`` is required iff either target is an edge — geometry recomputes
         *     that feature tree (reusing the ``POST /api/v1/evaluate`` machinery, so the
         *     same ordered dispatch + strict-prefix rule applies) and measures the exact
         *     B-rep edge. For point-point, ``tree`` is omitted and no body is built.
         */
        MeasureRequest: {
            /**
             * A
             * @description First measurement target
             */
            a: components["schemas"]["PointTarget"] | components["schemas"]["EdgeTarget"];
            /**
             * B
             * @description Second measurement target
             */
            b: components["schemas"]["PointTarget"] | components["schemas"]["EdgeTarget"];
            /** @description Feature tree to recompute for edge targets (required iff a or b is an edge); ignored for point-point. Its linear_deflection is unused — measurement reads the exact B-rep, never the mesh. */
            tree?: components["schemas"]["EvaluateTreeRequest"] | null;
        };
        /**
         * MeasureResult
         * @description Nearest distance between the two targets plus its components.
         *
         *     ``distance`` is the exact minimum distance; ``delta`` are the signed
         *     component distances from the nearest point on A to the nearest point on B
         *     (its magnitude equals ``distance``). ``point_on_a``/``point_on_b`` are the
         *     witness points (what a UI draws the measurement line between). ``angle_deg``
         *     is the acute angle between the two targets, reported only for edge-edge
         *     where BOTH edges are straight lines (else null — no single direction).
         */
        MeasureResult: {
            /**
             * Angle Deg
             * @description Acute angle between the two targets in degrees [0, 90], reported only for edge-edge where both edges are straight lines; null otherwise (a point or a curved edge has no single direction)
             */
            angle_deg?: number | null;
            /** @description Component distances from the nearest point on A to the nearest point on B (mm): (dx, dy, dz); |delta| == distance */
            delta: components["schemas"]["Vec3"];
            /**
             * Distance
             * @description Exact nearest (minimum) distance between the targets (mm)
             */
            distance: number;
            /**
             * Kind
             * @description Which pair of target flavours was measured
             * @enum {string}
             */
            kind: "point_point" | "point_edge" | "edge_edge";
            /** @description Nearest point on target A (mm) */
            point_on_a: components["schemas"]["Vec3"];
            /** @description Nearest point on target B (mm) */
            point_on_b: components["schemas"]["Vec3"];
        };
        /**
         * MeshStats
         * @description Statistics of the tessellated GLB artifact.
         */
        MeshStats: {
            /**
             * Glb Bytes
             * @description Size of the binary glTF payload in bytes
             */
            glb_bytes: number;
            /** Triangles */
            triangles: number;
            /** Vertices */
            vertices: number;
        };
        /**
         * MirrorAxisEntity
         * @description Mirror axis named by an existing **line** entity id.
         *
         *     The cleanest "mirror about this construction centerline" case: ``entity``
         *     must resolve to a :class:`SketchLine` in the request's ``entities`` (else
         *     ``sketch_target_not_found``; a non-line axis entity is
         *     ``sketch_mirror_axis_not_line``). The line's start/end define the axis.
         */
        MirrorAxisEntity: {
            /**
             * Entity
             * @description Id of the line entity to mirror about; must be in `entities`.
             */
            entity: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "entity";
        };
        /**
         * MirrorAxisPoints
         * @description Mirror axis given directly as the infinite line through two points.
         *
         *     More general than :class:`MirrorAxisEntity` — no axis entity need exist in
         *     the sketch. ``a`` and ``b`` must be distinct (a zero-length axis is
         *     ``sketch_mirror_degenerate_axis``).
         */
        MirrorAxisPoints: {
            /** @description First point on the mirror axis line (mm). */
            a: components["schemas"]["Point2D"];
            /** @description Second point on the mirror axis line (mm). */
            b: components["schemas"]["Point2D"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "points";
        };
        /**
         * OverlayEdge
         * @description One pickable B-rep edge of the evaluated body (transient index).
         *
         *     The list position of this edge in :attr:`OverlayResult.edges` is its
         *     transient 0-based index — the SAME ordinal ``body.edges()`` yields, so
         *     passing it as :class:`~py_kit.schemas.measure.EdgeTarget` ``index`` measures
         *     THIS edge. Not stable across edits (topological naming is Phase 2).
         */
        OverlayEdge: {
            /** @description Edge end vertex, world mm (curve param 1); equals start for a closed edge such as a full circle */
            end: components["schemas"]["Vec3"];
            /**
             * Kind
             * @description Curve family (line/circle/other) — a rendering hint only; measurement reads the exact B-rep, never this tag
             * @enum {string}
             */
            kind: "line" | "circle" | "other";
            /**
             * Polyline
             * @description Ordered world-mm points to draw the edge as a polyline (>= 2 points, start..end inclusive). A straight edge is exactly [start, end]; a curved edge is sampled to the request tree's linear_deflection — the SAME tolerance policy as the mesh, no new epsilon.
             */
            polyline: components["schemas"]["Vec3"][];
            /** @description Edge start vertex, world mm (curve param 0) */
            start: components["schemas"]["Vec3"];
        };
        /**
         * OverlayRequest
         * @description Request the pickable selection geometry of an evaluated feature tree.
         *
         *     ``tree`` is recomputed with the SAME ordered dispatch + strict-prefix rule
         *     as ``POST /api/v1/evaluate`` / ``/measure`` (reusing ``evaluate_tree``); the
         *     overlay is built from the last-good body. Its ``linear_deflection`` also
         *     fixes the curved-edge polyline sampling (one tolerance, no ad-hoc epsilon).
         *     A tree that recomputes to no body is a clean 422 ``tree_overlay_failed``.
         */
        OverlayRequest: {
            /** @description Feature tree to recompute; the overlay describes its last-good body */
            tree: components["schemas"]["EvaluateTreeRequest"];
        };
        /**
         * OverlayResult
         * @description Pickable selection geometry of the evaluated body (all coords world mm).
         *
         *     ``vertices`` and ``edges`` are index-aligned with the recomputed body's
         *     deterministic ``.vertices()`` / ``.edges()`` lists. A client snaps to a
         *     vertex (exact point-point / point-edge) by echoing its coordinates as a
         *     ``PointTarget``, and measures an edge by sending its list index as an
         *     ``EdgeTarget``. Both index spaces are TRANSIENT — this request/tree only.
         */
        OverlayResult: {
            /**
             * Edges
             * @description Pickable edges in body.edges() order — the SAME enumeration measure resolves EdgeTarget.index against
             */
            edges: components["schemas"]["OverlayEdge"][];
            /**
             * Vertices
             * @description Exact world-mm snap points in body.vertices() order; echo one back as a measure PointTarget for an exact point measurement
             */
            vertices: components["schemas"]["Vec3"][];
        };
        /**
         * ParallelConstraint
         * @description Two lines have equal direction.
         *
         *     Relates two **whole** line entities (by id, not by endpoint) — contrast
         *     with :class:`CoincidentConstraint`, whose ``a``/``b`` name single points.
         *     Removes one rotational degree of freedom. Both entities must be lines.
         */
        ParallelConstraint: {
            /**
             * A
             * @description Sketch-local entity id, e.g. 'e1'
             */
            a: string;
            /**
             * B
             * @description Sketch-local entity id, e.g. 'e1'
             */
            b: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "parallel";
        };
        /**
         * PatternFeature
         * @description ``{"type": "pattern", "version": 1, "params": {...}}`` envelope.
         */
        PatternFeature: {
            params: components["schemas"]["PatternParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "pattern";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * PatternParamsV1
         * @description Repeat the current single body into a linear row or circular ring.
         *
         *     Wraps the discriminated :data:`PatternGeometry` under ``pattern`` (the
         *     nested-discriminator idiom of :class:`RevolveParamsV1`'s ``axis``). Like a
         *     fillet/chamfer, a pattern carries NO ``FeatureRef``: it operates on the
         *     implicit single body chain that exists at its point in the tree (design
         *     §7.6), so its dependency on the prior body-affecting feature is tree order,
         *     not a reference. See the module-level DESIGN DECISION note for the v1
         *     "pattern the whole body + union" semantics and its stated limitations.
         */
        PatternParamsV1: {
            /**
             * Pattern
             * @description Linear or circular pattern geometry (discriminated on `kind`)
             */
            pattern: components["schemas"]["LinearPatternParamsV1"] | components["schemas"]["CircularPatternParamsV1"];
        };
        /**
         * PerpendicularConstraint
         * @description Two lines are orthogonal (their directions differ by 90°).
         *
         *     Relates two whole line entities by id; removes one rotational degree of
         *     freedom. Both entities must be lines.
         */
        PerpendicularConstraint: {
            /**
             * A
             * @description Sketch-local entity id, e.g. 'e1'
             */
            a: string;
            /**
             * B
             * @description Sketch-local entity id, e.g. 'e1'
             */
            b: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "perpendicular";
        };
        /**
         * Point2D
         * @description A point in sketch-plane coordinates (mm).
         */
        Point2D: {
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /**
         * PointTarget
         * @description A measurement endpoint given by explicit world coordinates (mm).
         *
         *     Exact on its own — a picked vertex/snap point already has exact world
         *     coordinates, so no body recomputation is needed for a point target.
         */
        PointTarget: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "point";
            /** @description World-space coordinates of the point (mm) */
            position: components["schemas"]["Vec3"];
        };
        /**
         * RadiusConstraint
         * @description Driving dimension: the radius of a circle or arc (mm).
         */
        RadiusConstraint: {
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "radius";
            /**
             * Value Mm
             * @description Radius (mm)
             */
            value_mm: number;
        };
        /**
         * RevolveAxis
         * @description The axis of revolution: a straight LINE entity of the profile's sketch.
         *
         *     v1 references a line entity by its sketch-local id (design §2.4 entity ids)
         *     within the SAME sketch the profile comes from. A **construction** line is
         *     the natural choice — a centerline is reference-only (excluded from the
         *     closed-wire profile) and is exactly what an axis of revolution is — but any
         *     line entity resolves; the axis is defined by the line's two solved
         *     endpoints, mapped to world space through the profile's datum plane.
         *
         *     The ``kind`` discriminator seeds a future additive ``datum_axis`` variant
         *     (the §2.1 ``GeomRef`` pattern) without forcing a ``param_version`` bump: a
         *     persisted axis is always ``{"kind": "sketch_line", "entity": ...}`` today,
         *     and a later datum-axis reference joins as ``kind: "datum_axis"``.
         */
        RevolveAxis: {
            /**
             * Entity
             * @description Sketch-local id of a LINE entity in the profile's sketch (a construction centerline is ideal) used as the axis of revolution
             */
            entity: string;
            /**
             * Kind
             * @default sketch_line
             * @constant
             */
            kind: "sketch_line";
        };
        /**
         * RevolveFeature
         * @description ``{"type": "revolve", "version": 1, "params": {...}}`` envelope.
         */
        RevolveFeature: {
            params: components["schemas"]["RevolveParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "revolve";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * RevolveParamsV1
         * @description Revolution of an earlier sketch feature's profile about a sketch-line axis.
         *
         *     The revolve sibling of :class:`ExtrudeParamsV1` (design §4.3, second core
         *     body-affecting feature): it consumes the SAME ``profile`` FeatureRef to an
         *     earlier sketch and the SAME ``add``/``cut`` boolean against the body chain,
         *     swapping the linear prism for a swept revolution. The ``axis`` is a
         *     :class:`RevolveAxis` (a line entity of that same sketch — no picked
         *     sub-geometry reference, so this is independent of topological naming), and
         *     ``angle_deg`` is the sweep (full 360° by default). The profile must clear
         *     the axis: a profile the axis crosses would revolve into self-intersecting
         *     material and is a per-feature ``axis_intersects_profile`` error (design
         *     §4.3), never a silent bad body.
         */
        RevolveParamsV1: {
            /**
             * Angle Deg
             * @description Sweep angle about the axis (degrees); 360 = full solid of revolution
             * @default 360
             */
            angle_deg: number;
            /** @description Axis of revolution — a line entity of the profile's sketch */
            axis: components["schemas"]["RevolveAxis"];
            /**
             * Direction
             * @description Sweep sense about the axis for a partial revolution (irrelevant at a full 360°): 'reverse' sweeps the opposite way
             * @default normal
             * @enum {string}
             */
            direction: "normal" | "reverse";
            /**
             * Operation
             * @enum {string}
             */
            operation: "add" | "cut";
            /** @description Must resolve to an EARLIER sketch feature (design §2.2) */
            profile: components["schemas"]["FeatureRef"];
        };
        /**
         * ShapeProperties
         * @description Mass properties + topology of the evaluated B-rep shape.
         */
        ShapeProperties: {
            bounding_box: components["schemas"]["BoundingBox"];
            /** @description Centre of mass (mm) */
            centroid: components["schemas"]["Vec3"];
            /**
             * Surface Area
             * @description Total surface area (mm^2)
             */
            surface_area: number;
            topology: components["schemas"]["TopologyCounts"];
            /**
             * Volume
             * @description Volume (mm^3)
             */
            volume: number;
        };
        /**
         * SketchArc
         * @description A circular arc traversed **counterclockwise** from start to end.
         *
         *     The radius is implied by ``|start - center|``; the solver keeps start and
         *     end on the circle (they may move to satisfy constraints).
         */
        SketchArc: {
            center: components["schemas"]["Point2D"];
            /**
             * Construction
             * @description Reference-only geometry (centerlines, symmetry/mirror axes, diagonals): solves and can be constrained/referenced, but is excluded from the profile that gates extrude/revolve. Absent in pre-construction-field sketches, which read as False.
             * @default false
             */
            construction: boolean;
            end: components["schemas"]["Point2D"];
            /**
             * Id
             * @description Sketch-local entity id, e.g. 'e1'
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "arc";
            start: components["schemas"]["Point2D"];
        };
        /**
         * SketchChamferRequest
         * @description Input for a sketch **chamfer** (bevel a corner with a straight line).
         *
         *     Same corner contract as :class:`SketchFilletRequest` (``a``/``b`` two
         *     distinct line curves present in ``entities``). ``distance`` is the equal
         *     setback (mm) measured along each leg from the corner; strictly positive and
         *     finite. Both lines are trimmed to their setback points and a straight
         *     chamfer line is added between them. Errors are the same 422 codes as fillet
         *     (``sketch_corner_not_found``, ``sketch_corner_too_large`` when ``distance``
         *     exceeds a leg's available length, ``sketch_degenerate_result``,
         *     ``sketch_target_not_found``, ``sketch_unsupported_entity``).
         */
        SketchChamferRequest: {
            /**
             * A
             * @description Id of the first corner line; must be in `entities`.
             */
            a: string;
            /**
             * B
             * @description Id of the second corner line; must be in `entities`, distinct from `a`.
             */
            b: string;
            /**
             * Distance
             * @description Equal setback distance (mm) along each leg from the corner; strictly positive and finite.
             */
            distance: number;
            /**
             * Entities
             * @description The whole sketch's entities (chamfer rewrites the two corner curves and ADDS the bevel line).
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
        };
        /**
         * SketchCircle
         * @description A full circle.
         */
        SketchCircle: {
            center: components["schemas"]["Point2D"];
            /**
             * Construction
             * @description Reference-only geometry (centerlines, symmetry/mirror axes, diagonals): solves and can be constrained/referenced, but is excluded from the profile that gates extrude/revolve. Absent in pre-construction-field sketches, which read as False.
             * @default false
             */
            construction: boolean;
            /**
             * Id
             * @description Sketch-local entity id, e.g. 'e1'
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "circle";
            /**
             * Radius
             * @description Radius (mm)
             */
            radius: number;
        };
        /**
         * SketchCornerResult
         * @description Output of a fillet/chamfer: the whole rewritten entity list.
         *
         *     Like :class:`SketchEditResult` (and unlike the additive offset/mirror
         *     results), a corner op returns the FULL entity set: order is preserved, the
         *     two corner curves are replaced **in place** by their trimmed selves (ids and
         *     construction flags unchanged, only the corner-side endpoint moved to the
         *     tangent/setback point), and the bridging entity — a tangent arc (fillet) or
         *     straight line (chamfer) — is **appended at the end** with a fresh
         *     deterministic id ``f"{a}.{n}"`` (lowest ``n`` >= 2 not already in use, seeded
         *     from the whole input set) inheriting the first curve's construction flag. A
         *     fillet arc is emitted CCW-from-start (the minor corner arc), honouring the
         *     :class:`SketchArc` invariant. Deterministic: identical input yields identical
         *     output entities, coordinates included (RESEARCH §9).
         */
        SketchCornerResult: {
            /**
             * Entities
             * @description The sketch entities after the corner op: the two source curves trimmed in place (ids preserved) plus the appended bridge (fresh id `f"{a}.{n}"`).
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
        };
        /**
         * SketchEditRequest
         * @description Input for a sketch trim or extend edit (stateless, one-shot).
         *
         *     ``entities`` is the whole sketch's entity list (same shapes the solver
         *     consumes — a construction entity is trimmed/extended like any other).
         *     ``target`` names the entity being edited; it MUST be present in
         *     ``entities`` (else a 422 ``sketch_target_not_found``). ``pick`` is the
         *     2D sketch-plane point the user clicked:
         *
         *     * **trim** — ``pick`` selects WHICH segment of ``target`` to delete: the
         *       target curve is cut at its nearest intersection(s) with the other
         *       entities on each side of the pick, and the segment containing the pick
         *       is removed (standard Onshape/Fusion "cut at intersection" gesture). With
         *       no intersection bounding a side, that side runs to the curve's end; with
         *       no intersection at all, the whole target is deleted. The pick must
         *       project onto the target's drawn extent (else 422
         *       ``sketch_pick_not_on_target``).
         *     * **extend** — ``pick`` selects WHICH END of ``target`` to lengthen (the
         *       nearer endpoint): the curve grows along its own supporting line/circle
         *       from that end to the nearest neighboring entity it meets in that
         *       direction (else 422 ``sketch_extend_no_target``).
         *
         *     Units are millimetres (:mod:`py_kit.schemas.sketch` convention).
         */
        SketchEditRequest: {
            /**
             * Entities
             * @description The whole sketch's entities (the edit rewrites this set).
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
            /** @description Sketch-plane pick point (mm): the segment to delete (trim) or the end to lengthen (extend, nearest endpoint wins). */
            pick: components["schemas"]["Point2D"];
            /**
             * Target
             * @description Id of the entity to trim/extend; must be in `entities`.
             */
            target: string;
        };
        /**
         * SketchEditResult
         * @description Output of a trim/extend edit: the rewritten entity list.
         *
         *     Order is preserved: unedited entities keep their position and id; the
         *     target is replaced **in place** by its resulting piece(s). Trim may leave
         *     the target shortened (one piece, id unchanged), split it into two (the
         *     piece from the target's start keeps the id; the second piece gets a fresh
         *     deterministic id ``f"{target}.{n}"``, the lowest ``n`` >= 2 not already in
         *     use), convert a trimmed circle into a single arc (id unchanged), or delete
         *     it entirely (target absent from the result). Extend returns the target
         *     lengthened (id unchanged). Deterministic: identical input yields identical
         *     output entities, coordinates included (RESEARCH §9).
         */
        SketchEditResult: {
            /**
             * Entities
             * @description The sketch entities after the edit (see class docstring for how the target is rewritten and how split ids are assigned).
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
        };
        /**
         * SketchFeature
         * @description ``{"type": "sketch", "version": 1, "params": {...}}`` envelope.
         */
        SketchFeature: {
            params: components["schemas"]["SketchParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "sketch";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * SketchFilletRequest
         * @description Input for a sketch **fillet** (round a corner with a tangent arc).
         *
         *     ``entities`` is the whole sketch's entity list (so the new arc gets a fresh
         *     id that cannot collide, and to mirror the trim/offset contract). ``a`` and
         *     ``b`` name the two curves forming the corner; each MUST be present in
         *     ``entities`` (else ``sketch_target_not_found``), be **distinct**, and — in
         *     v1 — be **lines** (a non-line, or a line-arc/arc-arc pair, is
         *     ``sketch_unsupported_entity``). ``radius`` is the tangent-arc radius (mm),
         *     strictly positive and finite.
         *
         *     Both lines are trimmed to their tangent points (``radius`` from the corner
         *     along each leg, scaled by the corner half-angle) and a tangent arc is added.
         *     Errors are 422s, never 500s: ``sketch_corner_not_found`` (the supports are
         *     parallel/collinear, or ``a``/``b`` name the same entity — no isolated
         *     corner), ``sketch_corner_too_large`` (the tangent point falls past a leg's
         *     far end — radius too large for the available length),
         *     ``sketch_degenerate_result`` (a zero-length result), plus the target/kind
         *     codes above.
         */
        SketchFilletRequest: {
            /**
             * A
             * @description Id of the first corner line; must be in `entities`.
             */
            a: string;
            /**
             * B
             * @description Id of the second corner line; must be in `entities`, distinct from `a`.
             */
            b: string;
            /**
             * Entities
             * @description The whole sketch's entities (fillet rewrites the two corner curves and ADDS the arc).
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
            /**
             * Radius
             * @description Fillet (tangent-arc) radius (mm); strictly positive and finite.
             */
            radius: number;
        };
        /**
         * SketchLine
         * @description A line segment between two endpoints.
         */
        SketchLine: {
            /**
             * Construction
             * @description Reference-only geometry (centerlines, symmetry/mirror axes, diagonals): solves and can be constrained/referenced, but is excluded from the profile that gates extrude/revolve. Absent in pre-construction-field sketches, which read as False.
             * @default false
             */
            construction: boolean;
            end: components["schemas"]["Point2D"];
            /**
             * Id
             * @description Sketch-local entity id, e.g. 'e1'
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "line";
            start: components["schemas"]["Point2D"];
        };
        /**
         * SketchMirrorRequest
         * @description Input for a sketch mirror (stateless, one-shot).
         *
         *     ``entities`` is the whole sketch's entity list — passed so each new copy
         *     gets a fresh id that cannot collide with an existing one (and to resolve a
         *     :class:`MirrorAxisEntity` axis). ``targets`` names the entities to reflect;
         *     each MUST be present in ``entities`` (else ``sketch_target_not_found``) and
         *     at least one is required. ``axis`` is the mirror line (see :data:`MirrorAxis`).
         *
         *     Mirror **adds** geometry: the sources are untouched and the response carries
         *     only the NEW reflected copies (see :class:`SketchMirrorResult`). Every entity
         *     kind is reflectable (point, line, circle, arc). Units are millimetres
         *     (:mod:`py_kit.schemas.sketch` convention).
         */
        SketchMirrorRequest: {
            /**
             * Axis
             * @description The mirror axis: a line entity id or two points (see MirrorAxis).
             */
            axis: components["schemas"]["MirrorAxisEntity"] | components["schemas"]["MirrorAxisPoints"];
            /**
             * Entities
             * @description The whole sketch's entities (mirror ADDS to this set; the sources stay unchanged).
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
            /**
             * Targets
             * @description Ids of the entities to reflect; each must be in `entities`.
             */
            targets: string[];
        };
        /**
         * SketchMirrorResult
         * @description Output of a mirror: the NEW reflected copies (sources unchanged).
         *
         *     Like :class:`SketchOffsetResult` (and unlike :class:`SketchEditResult`),
         *     mirror **adds** geometry, so this carries ONLY the newly created copies —
         *     one per ``target``, in ``targets`` order — each with a fresh deterministic
         *     id ``f"{source}.{n}"`` (lowest ``n`` >= 2 not already in use, seeded from the
         *     whole sketch AND the copies already minted) and the source's construction
         *     flag inherited. The caller appends these to its own entity list.
         *
         *     Reflection reverses orientation, so a mirrored **arc** has its start/end
         *     **swapped** (``start`` = reflected source ``end``, ``end`` = reflected source
         *     ``start``) to preserve the CCW-from-start invariant :class:`SketchArc`
         *     documents. Deterministic: identical input yields identical output entities,
         *     coordinates included (RESEARCH §9).
         */
        SketchMirrorResult: {
            /**
             * Entities
             * @description The newly created mirrored copies (sources are unchanged and NOT echoed here). One per target; fresh id `f"{source}.{n}"`, construction flag inherited, arcs start/end-swapped for CCW.
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
        };
        /**
         * SketchOffsetRequest
         * @description Input for a sketch offset (stateless, one-shot).
         *
         *     ``entities`` is the whole sketch's entity list — passed so the new offset
         *     entity gets a fresh id that cannot collide with an existing one (and to
         *     mirror the trim/extend contract). ``target`` names the entity to offset; it
         *     MUST be present in ``entities`` (else a 422 ``sketch_target_not_found``).
         *     ``distance`` is the **signed** offset distance in millimetres (see the
         *     module comment above for the left-hand-normal sign convention); it must be
         *     a nonzero, finite value (else 422 ``sketch_offset_zero_distance``).
         */
        SketchOffsetRequest: {
            /**
             * Distance
             * @description Signed offset distance (mm): +distance = left of the directed curve (a CCW arc/circle's left normal points inward, so +distance shrinks its radius). Must be nonzero and finite.
             */
            distance: number;
            /**
             * Entities
             * @description The whole sketch's entities (offset ADDS to this set; the source stays unchanged).
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
            /**
             * Target
             * @description Id of the entity to offset; must be in `entities`.
             */
            target: string;
        };
        /**
         * SketchOffsetResult
         * @description Output of an offset: the NEW offset entity/entities (source unchanged).
         *
         *     Offset **adds** geometry, so — unlike :class:`SketchEditResult` (which
         *     returns the whole rewritten set) — this carries ONLY the newly created
         *     offset entities. In v1 that is exactly one entity, with a fresh
         *     deterministic id ``f"{target}.{n}"`` and the source's construction flag
         *     inherited. The caller appends these to its own entity list. Deterministic:
         *     identical input yields identical output entities, coordinates included
         *     (RESEARCH §9).
         */
        SketchOffsetResult: {
            /**
             * Entities
             * @description The newly created offset entities (source entities are unchanged and NOT echoed here). One entity in v1 (single-entity offset); fresh id `f"{target}.{n}"`, construction flag inherited.
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
        };
        /**
         * SketchParamsV1
         * @description Sketch on a plane — datum planes only in v1 (design §2.1).
         *
         *     Extends :class:`py_kit.schemas.sketch.SketchDefinition` (typed
         *     ``entities``/``constraints`` — the §1.4 placeholder finalized by the
         *     "Sketch model + solver API" item), so a persisted sketch's params ARE
         *     valid solver input: same validation (unique sketch-local entity ids per
         *     design §2.4) on the documents write path and the geometry request path.
         */
        SketchParamsV1: {
            /** Constraints */
            constraints: (components["schemas"]["CoincidentConstraint"] | components["schemas"]["HorizontalConstraint"] | components["schemas"]["VerticalConstraint"] | components["schemas"]["DistanceConstraint"] | components["schemas"]["RadiusConstraint"] | components["schemas"]["FixedConstraint"] | components["schemas"]["ParallelConstraint"] | components["schemas"]["PerpendicularConstraint"] | components["schemas"]["TangentConstraint"] | components["schemas"]["EqualConstraint"] | components["schemas"]["SymmetricConstraint"] | components["schemas"]["ConcentricConstraint"])[];
            /** Entities */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
            /** Plane */
            plane: components["schemas"]["DatumPlaneRef"] | components["schemas"]["FeatureRef"];
        };
        /**
         * SketchPoint
         * @description A free point (construction geometry, arc centers to snap to, …).
         */
        SketchPoint: {
            /**
             * Construction
             * @description Reference-only geometry (centerlines, symmetry/mirror axes, diagonals): solves and can be constrained/referenced, but is excluded from the profile that gates extrude/revolve. Absent in pre-construction-field sketches, which read as False.
             * @default false
             */
            construction: boolean;
            /**
             * Id
             * @description Sketch-local entity id, e.g. 'e1'
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "point";
            position: components["schemas"]["Point2D"];
        };
        /**
         * SolvedSketchData
         * @description Per-feature solved-sketch payload (§7.10): the solver's solved entity
         *     positions, status, and DOF diagnosis for an ``ok`` sketch feature — what
         *     the sketcher UI renders. ``kind`` is the :data:`FeatureData` union tag.
         */
        SolvedSketchData: {
            /**
             * Conflicting Constraints
             * @description Indices into the input constraint list that conflict.
             */
            conflicting_constraints?: number[];
            /**
             * Dof
             * @description Remaining degrees of freedom (0 = fully constrained); None when the diagnosis cannot determine it (e.g. conflicting systems).
             */
            dof?: number | null;
            /**
             * Entities
             * @description Same entities (ids, kinds, order) as the input. Positions are solved when the numeric solve succeeded (converged, underconstrained, and consistent overconstrained cases); for conflicting/diverged sketches the input positions are returned unchanged.
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"])[];
            /**
             * Kind
             * @default solved_sketch
             * @constant
             */
            kind: "solved_sketch";
            /**
             * Redundant Constraints
             * @description Indices into the input constraint list that are redundant.
             */
            redundant_constraints?: number[];
            /**
             * Status
             * @enum {string}
             */
            status: "converged" | "underconstrained" | "overconstrained" | "conflicting" | "diverged";
        };
        /**
         * SweepFeature
         * @description ``{"type": "sweep", "version": 1, "params": {...}}`` envelope.
         */
        SweepFeature: {
            params: components["schemas"]["SweepParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "sweep";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * SweepParamsV1
         * @description Sweep an earlier sketch's closed profile along an earlier sketch's open path.
         *
         *     The first NON-PRISMATIC body-affecting feature (design §4.3): where extrude
         *     sweeps a profile along the plane normal and revolve about an axis, sweep
         *     follows an arbitrary open PATH wire — the shaft / pipe / rib primitive named
         *     in the Part-modeling scorecard notes. It consumes the SAME ``profile``
         *     FeatureRef to an earlier sketch (a single closed wire, built by the shared
         *     ``build_profile_face``) and the SAME ``add``/``cut`` boolean against the body
         *     chain as extrude/revolve; the new ingredient is ``path``, a SECOND
         *     FeatureRef to an earlier sketch whose entities form a single OPEN wire.
         *
         *     Path representation (v1 DESIGN DECISION — docs/design/feature-tree.md
         *     §2.1/§2.2, docs/GEOMETRY-QA.md 2026-07-12): the path is a whole earlier
         *     SKETCH feature referenced by id (option A — the most general model, matching
         *     how production CAD names a sweep path, and reusing the tree's stable feature
         *     ids exactly as the ``profile`` slot does). This is NOT topological naming
         *     (#1): it references a whole feature's evaluated wire, never a picked
         *     sub-edge — the same mechanism extrude/revolve already use for their profile.
         *
         *     v1 limits (stated plainly — documented scope, not bugs):
         *
         *     * the path must resolve to a single **open** wire; a closed path is a
         *       ``sweep_path_closed`` rebuild error, disjoint path loops are
         *       ``sweep_path_not_connected``, and a path with no curve entities is
         *       ``sweep_path_empty`` (construction geometry is excluded from the path
         *       exactly as it is from the profile);
         *     * the sweep is **anchored at the profile** — build123d applies the path as a
         *       relative trajectory from the profile's own location, so the path's
         *       absolute position is not used. Author the path starting at the profile
         *       origin, with its first segment perpendicular to the profile plane, for a
         *       predictable result (as the golden's vertical path over an XY circle is);
         *     * NO twist, NO scale-along-path, NO multi-section, NO guide rails, NO
         *       per-segment transition control — one profile rigidly swept along one path
         *       (all later, additive params — no ``param_version`` bump);
         *     * a self-intersecting path, or a corner tighter than the profile can turn
         *       without sweeping through itself, is a kernel ``sweep_failed`` rebuild
         *       error, never a silently bad body.
         */
        SweepParamsV1: {
            /**
             * Operation
             * @enum {string}
             */
            operation: "add" | "cut";
            /** @description Must resolve to an EARLIER sketch feature whose entities form a single OPEN wire — the sweep trajectory (design §2.2) */
            path: components["schemas"]["FeatureRef"];
            /** @description Must resolve to an EARLIER sketch feature whose entities form the single CLOSED profile wire (design §2.2) */
            profile: components["schemas"]["FeatureRef"];
        };
        /**
         * SymmetricConstraint
         * @description Two points are mirror images about a line.
         *
         *     ``a`` and ``b`` name single points (like :class:`CoincidentConstraint`);
         *     ``line`` is the whole line entity they are symmetric about — cleanest with
         *     a construction centerline, but any line works. Removes two degrees of
         *     freedom (the pair collapses to one point's worth of freedom plus a
         *     reflection). ``line`` must be a line entity.
         */
        SymmetricConstraint: {
            a: components["schemas"]["EntityPointRef"];
            b: components["schemas"]["EntityPointRef"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "symmetric";
            /**
             * Line
             * @description Sketch-local entity id, e.g. 'e1'
             */
            line: string;
        };
        /**
         * TangentConstraint
         * @description Two curves touch with a common tangent at the contact point.
         *
         *     Relates a line and an arc/circle, or two arcs/circles, by whole-entity id.
         *     A line-and-line pair is not tangency-capable and is rejected at solve time.
         *     Order is immaterial (tangency is symmetric); the solver dispatches to the
         *     matching planegcs variant from the resolved entity kinds.
         */
        TangentConstraint: {
            /**
             * A
             * @description Sketch-local entity id, e.g. 'e1'
             */
            a: string;
            /**
             * B
             * @description Sketch-local entity id, e.g. 'e1'
             */
            b: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "tangent";
        };
        /**
         * TessellateRequest
         * @description Build a parametric shape and tessellate it to GLB.
         */
        TessellateRequest: {
            /**
             * Linear Deflection
             * @description Max distance (mm) between a curve and its tessellation; lower = finer mesh
             * @default 0.1
             */
            linear_deflection: number;
            /**
             * Params
             * @description Parameters of the selected shape kind
             */
            params: components["schemas"]["BoxParams"] | components["schemas"]["CylinderParams"];
            /**
             * Shape
             * @description Shape kind; must match the params model
             * @enum {string}
             */
            shape: "box" | "cylinder";
        };
        /**
         * TessellationMetadata
         * @description Everything about a tessellation except the mesh itself.
         *
         *     Returned as JSON by the ``.../tessellate/meta`` routes and carried,
         *     compact-serialized, in the ``X-Loft-Properties`` response header of the
         *     binary ``.../tessellate`` routes (geometry service and gateway proxy).
         */
        TessellationMetadata: {
            mesh: components["schemas"]["MeshStats"];
            properties: components["schemas"]["ShapeProperties"];
        };
        /**
         * TopologyCounts
         * @description B-rep entity counts — asserted exactly by the golden-model suite.
         */
        TopologyCounts: {
            /** Edges */
            edges: number;
            /** Faces */
            faces: number;
            /** Shells */
            shells: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * Vec3
         * @description A 3D point/vector in model space (mm).
         */
        Vec3: {
            /** X */
            x: number;
            /** Y */
            y: number;
            /** Z */
            z: number;
        };
        /**
         * VerticalConstraint
         * @description A line is parallel to the sketch Y axis.
         */
        VerticalConstraint: {
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "vertical";
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    evaluate_api_v1_evaluate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvaluateTreeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvaluateTreeResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_api_v1_export_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExportRequest"];
            };
        };
        responses: {
            /** @description The exported CAD file: STEP AP214 part 21 (`model/step`, exact B-rep) or binary STL (`model/stl`, faceted mesh). `Content-Disposition` carries the suggested download filename. Byte-deterministic: identical requests produce identical files. */
            200: {
                headers: {
                    /** @description attachment; filename="<shape>.<format>" */
                    "Content-Disposition"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "model/step": string;
                    "model/stl": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_tree_api_v1_export_tree_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExportTreeRequest"];
            };
        };
        responses: {
            /** @description The exported CAD file: STEP AP214 part 21 (`model/step`, exact B-rep) or binary STL (`model/stl`, faceted mesh). `Content-Disposition` carries the suggested download filename. Byte-deterministic: identical requests produce identical files. */
            200: {
                headers: {
                    /** @description attachment; filename="<shape>.<format>" */
                    "Content-Disposition"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "model/step": string;
                    "model/stl": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    measure_api_v1_measure_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MeasureRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeasureResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    fetch_mesh_api_v1_meshes__mesh_glb_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                mesh_glb_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Binary glTF (GLB) mesh addressed by an `EvaluateTreeResult.mesh_glb_id` content hash (`sha256:<hex>`). 404 = evicted or unknown: re-evaluate the tree (results are pure functions of the request; feature-tree design §4.4/§7.8). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "model/gltf-binary": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    overlay_api_v1_overlay_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OverlayRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverlayResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sketch_chamfer_api_v1_sketch_chamfer_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SketchChamferRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SketchCornerResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sketch_extend_api_v1_sketch_extend_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SketchEditRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SketchEditResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sketch_fillet_api_v1_sketch_fillet_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SketchFilletRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SketchCornerResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sketch_mirror_api_v1_sketch_mirror_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SketchMirrorRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SketchMirrorResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sketch_offset_api_v1_sketch_offset_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SketchOffsetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SketchOffsetResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sketch_trim_api_v1_sketch_trim_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SketchEditRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SketchEditResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    tessellate_api_v1_tessellate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TessellateRequest"];
            };
        };
        responses: {
            /** @description Binary glTF (GLB) mesh of the requested shape. The `X-Loft-Properties` header carries `TessellationMetadata` as compact JSON (see `POST /api/v1/tessellate/meta` for the same payload as a typed JSON body). */
            200: {
                headers: {
                    /** @description TessellationMetadata as compact JSON */
                    "X-Loft-Properties"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "model/gltf-binary": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    tessellate_meta_api_v1_tessellate_meta_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TessellateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TessellationMetadata"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
