// GENERATED — do not edit; run `just gen`.
// Types for the documents service (source contract: packages/contracts/documents.openapi.json).
export interface paths {
    "/api/v1/parts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Parts
         * @description The caller's parts, oldest first (deterministic id tiebreak).
         */
        get: operations["list_parts_api_v1_parts_get"];
        put?: never;
        /**
         * Create Part
         * @description Create a part (201; envelope 409 on a duplicate name for this owner).
         */
        post: operations["create_part_api_v1_parts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Part
         * @description One owned part (uniform 404 for unknown/foreign ids).
         */
        get: operations["get_part_api_v1_parts__part_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Part
         * @description Delete an owned part (204; uniform 404 for unknown/foreign ids).
         *
         *     Deletion is unconditional BY DESIGN even when the part has a feature
         *     tree: the parts→features CASCADE removes the tree, and the deferred
         *     target-side FK on feature_dependencies makes that legal at commit time
         *     (docs/design/feature-tree.md §2.3 — the 409-with-dependents pre-check
         *     applies to deleting a single FEATURE, never the whole part).
         */
        delete: operations["delete_part_api_v1_parts__part_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}/evaluation-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Evaluation Request
         * @description The evaluation-ready feature list (design §4.2), for the gateway to
         *     forward to the geometry service verbatim.
         *
         *     Documents owns everything geometry must never know about: the rollback
         *     bar is applied HERE (only the prefix up to and including the bar is
         *     returned, §3), params are upcast to current versions on read (§1.4), and
         *     the order is the total ``order_index`` order. ``tree_version`` rides
         *     along as the cache/correlation key.
         */
        get: operations["get_evaluation_request_api_v1_parts__part_id__evaluation_request_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}/features": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Feature Tree
         * @description The ordered feature tree (uniform 404 for unknown/foreign parts).
         */
        get: operations["get_feature_tree_api_v1_parts__part_id__features_get"];
        put?: never;
        /**
         * Create Feature
         * @description Append a feature — or, while rolled back, insert it immediately after
         *     the bar and move the bar to it (design §3).
         */
        post: operations["create_feature_api_v1_parts__part_id__features_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}/features/order": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Reorder Features
         * @description Apply a full permutation of the tree, re-checking backward-only refs
         *     (§2.2 rule 2) under the new order before renumbering.
         */
        put: operations["reorder_features_api_v1_parts__part_id__features_order_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}/features/{feature_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Feature
         * @description One feature of an owned part.
         */
        get: operations["get_feature_api_v1_parts__part_id__features__feature_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Feature
         * @description Delete a feature; 409 listing dependents when it is still referenced.
         *
         *     The friendly conflict comes from documents' pre-check on the materialized
         *     edges (design §2.3); the deferred target-side FK remains the DB backstop.
         *     Returns the renumbered tree (the client's new ``tree_version``).
         */
        delete: operations["delete_feature_api_v1_parts__part_id__features__feature_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Feature
         * @description Rename and/or replace params. ANY mutation bumps ``tree_version``
         *     (uniform rule, design §1.2) — including a name-only change.
         */
        patch: operations["update_feature_api_v1_parts__part_id__features__feature_id__patch"];
        trace?: never;
    };
    "/api/v1/parts/{part_id}/rollback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Move Rollback Bar
         * @description Move the rollback bar (design §3). Nothing below the bar is deleted or
         *     mutated; features after it are only MARKED rolled back.
         */
        put: operations["move_rollback_bar_api_v1_parts__part_id__rollback_put"];
        post?: never;
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
         * EvaluatedFeatureInput
         * @description One ordered entry of an evaluation request.
         */
        EvaluatedFeatureInput: {
            /** Feature */
            feature: components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["PatternFeature"];
            /**
             * Id
             * Format: uuid
             * @description Feature identity for refs + result keying
             */
            id: string;
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
         * FeatureCreate
         * @description Create a feature. Appends at the tip; while rolled back, inserts
         *     immediately after the bar and moves the bar to the new feature (§3).
         */
        FeatureCreate: {
            /**
             * Expected Tree Version
             * @description Optimistic-concurrency guard: the tree_version the client last saw; a stale value is rejected 422 (design §1.2)
             */
            expected_tree_version: number;
            /** Feature */
            feature: components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["PatternFeature"];
            /**
             * Name
             * @description User-facing name ("Sketch1")
             */
            name: string;
        };
        /**
         * FeatureMutationResponse
         * @description Result of a single-feature mutation: the affected feature + the new
         *     tree version (the client's next ``expected_tree_version``).
         */
        FeatureMutationResponse: {
            feature: components["schemas"]["FeatureResponse"];
            /** Tree Version */
            tree_version: number;
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
         * FeatureReorderRequest
         * @description Reorder the whole tree: the complete permutation of feature ids in the
         *     desired evaluation order. Backward-only references (design §2.2 rule 2)
         *     are re-checked under the new order.
         */
        FeatureReorderRequest: {
            /** Expected Tree Version */
            expected_tree_version: number;
            /**
             * Order
             * @description ALL feature ids of the part, in the desired order
             */
            order: string[];
        };
        /**
         * FeatureResponse
         * @description A feature as stored, with the envelope reassembled (design §1.3) and
         *     params already upcast to the current version (design §1.4).
         */
        FeatureResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Feature */
            feature: components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["PatternFeature"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Order Index
             * @description Dense 0..n-1 evaluation order; only relative position is meaningful to clients (design §1.2)
             */
            order_index: number;
            /**
             * Part Id
             * Format: uuid
             */
            part_id: string;
            /**
             * Rolled Back
             * @description True when the feature sits after the rollback bar (§3)
             */
            rolled_back: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * FeatureTreeResponse
         * @description The ordered feature tree of a part plus its concurrency token.
         */
        FeatureTreeResponse: {
            /** Features */
            features: components["schemas"]["FeatureResponse"][];
            /**
             * Part Id
             * Format: uuid
             */
            part_id: string;
            /**
             * Rollback Feature Id
             * @description Last INCLUDED feature; null = bar at the tip (§3)
             */
            rollback_feature_id: string | null;
            /** Tree Version */
            tree_version: number;
        };
        /**
         * FeatureUpdate
         * @description Rename and/or replace a feature's param envelope (both bump
         *     ``tree_version`` — any mutation bumps, design §1.2). The feature ``type``
         *     is immutable — replace the feature to change its kind.
         */
        FeatureUpdate: {
            /** Expected Tree Version */
            expected_tree_version: number;
            /** Feature */
            feature?: (components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["PatternFeature"]) | null;
            /** Name */
            name?: string | null;
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
         * PartCreate
         * @description Create a part owned by the calling user.
         */
        PartCreate: {
            /**
             * Name
             * @description Part name; unique per owner, whitespace-trimmed, 1-200 characters
             */
            name: string;
        };
        /**
         * PartListResponse
         * @description The caller's parts, oldest first (wrapper leaves room for pagination).
         */
        PartListResponse: {
            /** Parts */
            parts: components["schemas"]["PartResponse"][];
        };
        /**
         * PartResponse
         * @description A part as stored — identity, ownership, and timestamps.
         *
         *     The feature tree is NOT here yet: it lands as its own tables per
         *     docs/design/feature-tree.md once the implementation item ships.
         */
        PartResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Owner Id
             * Format: uuid
             * @description Owning user id (gateway-verified)
             */
            owner_id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
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
         * RollbackBarMove
         * @description Move the rollback bar (§3): the id of the last included feature, or
         *     null for the tip. Bumps ``tree_version`` (it changes what an evaluation
         *     of the part means).
         */
        RollbackBarMove: {
            /** Expected Tree Version */
            expected_tree_version: number;
            /** Rollback Feature Id */
            rollback_feature_id: string | null;
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
    list_parts_api_v1_parts_get: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PartListResponse"];
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
    create_part_api_v1_parts_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PartCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PartResponse"];
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
    get_part_api_v1_parts__part_id__get: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PartResponse"];
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
    delete_part_api_v1_parts__part_id__delete: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    get_evaluation_request_api_v1_parts__part_id__evaluation_request_get: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvaluateTreeRequest"];
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
    get_feature_tree_api_v1_parts__part_id__features_get: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureTreeResponse"];
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
    create_feature_api_v1_parts__part_id__features_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeatureCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureMutationResponse"];
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
    reorder_features_api_v1_parts__part_id__features_order_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeatureReorderRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureTreeResponse"];
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
    get_feature_api_v1_parts__part_id__features__feature_id__get: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
                feature_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureResponse"];
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
    delete_feature_api_v1_parts__part_id__features__feature_id__delete: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard (see FeatureCreate) */
                expected_tree_version: number;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
                feature_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureTreeResponse"];
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
    update_feature_api_v1_parts__part_id__features__feature_id__patch: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
                feature_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeatureUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureMutationResponse"];
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
    move_rollback_bar_api_v1_parts__part_id__rollback_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RollbackBarMove"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureTreeResponse"];
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
