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
            edges: components["schemas"]["AllEdgesSelector"] | components["schemas"]["AxisParallelEdgesSelector"] | components["schemas"]["PickedEdgesSelector"];
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
         * DatumFeature
         * @description ``{"type": "datum", "version": 1, "params": {...}}`` envelope.
         *
         *     A non-body-affecting feature that produces a plane a later sketch sits on
         *     (docs/design/datum-planes.md §2b). ``params`` is the discriminated
         *     :data:`DatumParams` union — an ``offset`` plane (§3) or an ``on_face`` plane
         *     (§7). Adding the ``on_face`` variant is ADDITIVE with NO ``param_version``
         *     bump: legacy offset params (persisted before ``on_face`` existed) carry no
         *     ``kind`` discriminator, so :meth:`_legacy_offset_kind` injects ``"offset"``
         *     before validation and every existing datum row/golden validates unchanged
         *     (datum-planes §4/§7).
         */
        DatumFeature: {
            /** Params */
            params: components["schemas"]["DatumOffsetParams"] | components["schemas"]["DatumOnFaceParams"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "datum";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * DatumOffsetParams
         * @description An origin datum slid ``offset_mm`` along its normal (``kind: "offset"``).
         *
         *     The v1 face-free slice (docs/design/datum-planes.md §3): ``base`` is one of
         *     the three stable origin datums, ``offset_mm`` slides the plane along that
         *     datum's normal, and ``flip`` optionally reverses the normal. No picked
         *     geometry, no reference to another feature's output — so this is independent
         *     of topological naming (#1), exactly like revolve's world-axis or a pattern's
         *     world-vector. A datum is NOT body-affecting: it produces a plane, contributes
         *     no body, and is TOTAL — any finite ``offset_mm`` yields a valid plane, so an
         *     offset datum never carries an ``error`` status (§3b). A non-finite offset is
         *     a parse-time 422 (``allow_inf_nan=False``), never a rebuild error.
         *
         *     ``kind`` defaults to ``"offset"`` so LEGACY params (persisted before the
         *     ``on_face`` variant, which carry no discriminator) validate here unchanged —
         *     :class:`DatumFeature`'s before-validator injects it (additive, NO
         *     ``param_version`` bump — datum-planes §4/§7).
         */
        DatumOffsetParams: {
            /**
             * Base
             * @description Origin datum this plane is parallel to (its orientation).
             * @enum {string}
             */
            base: "XY" | "XZ" | "YZ";
            /**
             * Flip
             * @description Reverse the plane normal (negate z_dir, keeping x_dir so sketch +u is unchanged and +v flips). Additive-optional; absent reads as False. Position is fully covered by signed `offset_mm`; `flip` only chooses which way 'normal' points for authoring/extrude-side.
             * @default false
             */
            flip: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "offset";
            /**
             * Offset Mm
             * @description Signed distance along `base`'s normal (mm). 0 coincides with the origin datum; +/- selects side. Any finite value is valid.
             */
            offset_mm: number;
        };
        /**
         * DatumOnFaceParams
         * @description A datum plane adopted from a picked PLANAR face (``kind: "on_face"``).
         *
         *     The v2 on-a-face slice (docs/design/datum-planes.md §7): the datum's plane
         *     resolves to the plane of a planar face of an EARLIER body-affecting feature's
         *     result, named by a stage-1 :class:`SubshapeRef` signature
         *     (docs/design/topological-naming.md), with an optional ``offset_mm`` along the
         *     face normal. This is the sketch-on-a-face foundation — a sketch sits on this
         *     datum by the SAME ``FeatureRef`` it uses for an offset datum, so on-face
         *     reuses the datum node rather than a new mechanism (datum-planes §2b/§7).
         *
         *     The derived sketch basis is DETERMINISTIC (RESEARCH §9): origin at the face
         *     area centroid (plus ``offset_mm`` along the normal), ``z_dir`` the outward
         *     face normal, and an ``x_dir`` pinned from the normal
         *     (``geometry.kernel.faces._deterministic_x_dir``) so the 2D→3D mapping is
         *     stable across rebuilds, independent of OCCT's face parametrisation.
         *
         *     HONEST v1 limits: the face reference is a stage-1 signature — best-effort,
         *     NOT structurally non-retargeting (see :class:`SubshapeRef`). A rebuild that
         *     removes the face is an honest ``subshape_unresolved`` on this datum; a
         *     congruent twin is ``subshape_ambiguous``; a drastic change can (rarely)
         *     retarget to a congruent face. Only PLANAR faces carry a signature, so a
         *     non-planar face cannot be referenced (the pick UI omits them from the
         *     sketchable set — a non-planar pick is rejected before a datum is authored).
         */
        DatumOnFaceParams: {
            /** @description Planar face of an earlier body-affecting feature whose plane this datum adopts (stage-1 signature reference) */
            face: components["schemas"]["SubshapeRef"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "on_face";
            /**
             * Offset Mm
             * @description Signed offset along the face normal (mm); 0 sits on the face. Optional (datum-planes §7).
             * @default 0
             */
            offset_mm: number;
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
         * @description Dimension: the length of a line (mm). Driving by default; see
         *     :class:`DimensionConstraint` for the expression/name/driving fields.
         */
        DistanceConstraint: {
            /**
             * Driving
             * @description Driving/driven flag. None (absent, the default) or True = DRIVING: the value is fed to the solver. False = DRIVEN: excluded from the constraint system; the value is measured back from the solved geometry for display (read-only, never fed as a constraint, so a driven dimension cannot over-constrain). Nullable+None-default (rather than a bare `bool`) keeps it an ADDITIVE optional field: a sketch persisted before it reads as None = driving, and the generated TS client leaves it optional. Read it through `is_driving`, never the raw tri-state.
             */
            driving?: boolean | null;
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /**
             * Expression
             * @description Optional math expression over other dimension NAMES (`+ - * / ( )`, unary minus, decimals), e.g. `"width/2"`. When present it SUPERSEDES `value_mm` and the geometry service re-evaluates it each solve. A bare literal dimension leaves this None. Only *driving* dimensions may be referenced; a bad expression / unknown or driven reference / cycle / division-by-zero is a clean `sketch_invalid` error, never a crash. Capped at 256 chars: an expression is a short formula over dimension names (`(width+gap)/2`), never prose, and the cap bounds parser paren-depth (<=128) and evaluator AST-depth (<=128) well under Python's recursion limit, so a hostile deeply-nested / very-long string 422s at request validation BEFORE the recursive-descent parser runs — it can never reach the kernel as an uncaught RecursionError. The parser also carries its own depth guard (defense in depth) should this cap ever be raised.
             */
            expression?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "distance";
            /**
             * Name
             * @description Optional stable name so another dimension's `expression` can reference this one. Unique within a sketch (enforced on SketchDefinition). None = unnamed: still solves, just not referenceable.
             */
            name?: string | null;
            /**
             * Value Mm
             * @description Resolved dimension value (mm). The literal value when `expression` is None; otherwise the last solved/resolved value (the expression supersedes it on the next solve, but a positive placeholder is still required so a pre-solve read has a value).
             */
            value_mm: number;
        };
        /**
         * DraftFeature
         * @description ``{"type": "draft", "version": 1, "params": {...}}`` envelope.
         */
        DraftFeature: {
            params: components["schemas"]["DraftParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "draft";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * DraftNeutralPlaneV1
         * @description v1 draft neutral plane = a principal origin datum, offset + flipped.
         *
         *     The plane that stays FIXED under the draft (picked faces rotate about their
         *     intersection with it), and — because build123d's ``Solid.draft`` derives the
         *     PULL DIRECTION from ``neutral_plane.z_dir`` — also the pull direction (its
         *     normal). Reuses the datum machinery (``geometry.kernel.build_datum_plane``,
         *     the same ``base``/``offset_mm``/``flip`` an offset ``datum`` feature uses), so
         *     the plane is a DETERMINISTIC pure function of its params (RESEARCH §9), needs
         *     no picked geometry, and carries NO feature reference (independent of
         *     topological naming #1).
         *
         *     ``kind`` defaults to ``"datum"`` and seeds a future additive union (a face-
         *     picked or datum-feature-referenced neutral plane joins as another ``kind``
         *     with NO ``param_version`` bump — the :data:`PatternGeometry` / RevolveAxis
         *     idiom).
         */
        DraftNeutralPlaneV1: {
            /**
             * Base
             * @description Origin datum the neutral plane is parallel to; its normal is the PULL direction (out of the mold). +Z for the default XY base.
             * @enum {string}
             */
            base: "XY" | "XZ" | "YZ";
            /**
             * Flip
             * @description Reverse the pull direction (negate the plane normal) — the OTHER mold half. Additive-optional; absent reads as False.
             * @default false
             */
            flip: boolean;
            /**
             * Kind
             * @default datum
             * @constant
             */
            kind: "datum";
            /**
             * Offset Mm
             * @description Signed distance along `base`'s normal (mm) to the neutral plane; 0 sits on the origin datum (the base). Any finite value is valid.
             * @default 0
             */
            offset_mm: number;
        };
        /**
         * DraftParamsV1
         * @description Taper picked faces of the current body by a constant angle (design §4.3).
         *
         *     The molding/casting RELEASE primitive (also tapered bosses/walls): the faces
         *     named by ``faces`` are tilted by ``angle_deg`` about their intersection with
         *     the ``neutral_plane``, so a body pulls cleanly from a mold along the neutral
         *     plane's normal. Like a fillet/chamfer/shell it modifies the implicit single
         *     body chain (design §7.6), so it carries no whole-feature ``FeatureRef`` — its
         *     dependency on the prior body-affecting feature is tree order. The picked faces
         *     ARE named references, though: each :class:`SubshapeRef` in ``faces``
         *     materializes into ``feature_dependencies`` exactly like a shell opening or an
         *     ``on_face`` datum's face ref, so deleting the referenced body feature is a
         *     write-time 409-with-dependents and a reorder re-checks strict-backward.
         *
         *     ``faces`` reuses the SAME :class:`FaceSelector` shell uses (topo-naming §4).
         *     Unlike shell — where an EMPTY selection is a meaningful sealed hollow — a
         *     draft with NO faces has nothing to taper, so an empty selection is a
         *     ``no_draft_faces`` rebuild error (draft must pick at least one face), never a
         *     silent no-op.
         *
         *     SIGN CONVENTION (measured against OCCT, docs/GEOMETRY-QA.md 2026-07-13): a
         *     POSITIVE ``angle_deg`` tapers each face INWARD toward the pull direction —
         *     the top (the ``neutral_plane``-normal end) NARROWS, the standard mold
         *     release. A NEGATIVE angle tapers OUTWARD (the far end widens — the opposite
         *     mold half). An angle too large for the geometry (the tapered faces collapse
         *     to zero width / self-intersect) is a ``draft_failed`` rebuild error — OCCT
         *     RAISES on that path, it never silently returns a bad body (unlike shell, so
         *     no material-validity guard is needed — investigation recorded in
         *     docs/GEOMETRY-QA.md), so ``draft_failed`` is never a silently wrong solid.
         *
         *     v1 limits (documented scope, not bugs): ONE constant angle, principal-datum
         *     neutral plane only (see :class:`DraftNeutralPlaneV1`), planar/cylindrical/
         *     conical faces only (a face OCCT cannot draft is a ``draft_failed``). NO
         *     variable-angle, NO parting-line, NO face-picked neutral plane (all later,
         *     additive — no ``param_version`` bump).
         */
        DraftParamsV1: {
            /**
             * Angle Deg
             * @description Draft angle (degrees). POSITIVE tapers INWARD toward the pull direction (top narrows — mold release); NEGATIVE tapers outward. An angle too large for the geometry is a `draft_failed` rebuild error.
             */
            angle_deg: number;
            /** @description The faces to TAPER (a picked-face selector, the SAME stage-1 signature shell/on_face use). Must name at least one face — an empty selection is a `no_draft_faces` rebuild error (draft is not a no-op). */
            faces: components["schemas"]["FaceSelector"];
            /** @description The fixed plane the picked faces rotate about; its normal is the pull direction (:class:`DraftNeutralPlaneV1`). */
            neutral_plane: components["schemas"]["DraftNeutralPlaneV1"];
        };
        /**
         * EdgeSelectorV1
         * @description Stage-1 edge selector payload: the geometric signature alone (§3, §4).
         *
         *     The edge sibling of :class:`SelectorV1`. ``selector_version`` is the
         *     discriminator of the (currently single-member) edge selector union,
         *     decoupled from feature ``param_version`` (§4); stage 2 adds a signature +
         *     provenance member additively, with no change to persisted v1 rows.
         */
        EdgeSelectorV1: {
            /**
             * Selector Version
             * @default 1
             * @constant
             */
            selector_version: 1;
            signature: components["schemas"]["EdgeSignature"];
        };
        /**
         * EdgeSignature
         * @description §2b stage-1 geometric fingerprint of an EDGE — typed, kernel-free.
         *
         *     Full-precision invariants (§7.2 forbids quantizing the stored identity),
         *     chosen to distinguish the edges of a manifold solid: the ``curve`` family
         *     (line/circle/other — a straight edge and an arc of equal length never
         *     collide), the two canonically-ordered endpoints ``end_a``/``end_b`` (sorted
         *     lexicographically so the signature is INDEPENDENT of the topological edge
         *     orientation OCCT happens to assign), the ``midpoint`` (curve param 0.5 — it
         *     separates two collinear edges that share an endpoint, and pins a full-circle
         *     seam edge whose endpoints coincide), and the ``length_mm``. Two DISTINCT
         *     edges of an authored part differ in at least one field (endpoints/midpoint
         *     by whole mm, or length, or curve kind) — including the mirror-congruent
         *     edges of a symmetric part, which have DISTINCT absolute positions and so do
         *     NOT tie. Only edges that truly coincide in space (a boolean seam, a
         *     non-manifold duplicate) resolve to an honest ``subshape_ambiguous`` (§5),
         *     never a guess. Matching is nearest-within-tolerance at the documented
         *     subshape tolerance (geometry.kernel.edges / docs/GEOMETRY-QA.md), never an
         *     ad-hoc epsilon.
         */
        EdgeSignature: {
            /**
             * Curve
             * @description Curve family — line | circle | other (spline/ellipse/…)
             * @enum {string}
             */
            curve: "line" | "circle" | "other";
            /** @description One endpoint, world mm; the lexicographically SMALLER of the two so the pair is orientation-independent (full precision) */
            end_a: components["schemas"]["Vec3"];
            /** @description The other endpoint, world mm; the lexicographically LARGER. Equals end_a for a closed edge (a full circle's coincident seam). */
            end_b: components["schemas"]["Vec3"];
            /**
             * Length Mm
             * @description Edge arc length (mm), full precision
             */
            length_mm: number;
            /** @description Curve midpoint (param 0.5), world mm (full precision) */
            midpoint: components["schemas"]["Vec3"];
            /**
             * Subshape Type
             * @default edge
             * @constant
             */
            subshape_type: "edge";
        };
        /**
         * EdgeSubshapeRef
         * @description Stage-1 reference to ONE edge of a body-affecting feature's result.
         *
         *     The edge sibling of :class:`SubshapeRef` (topological-naming.md §4/§10).
         *     ``feature_id`` is the stage-1 anchor — "the prior body-affecting feature
         *     whose body I signature-match against" (§4) — and materializes into
         *     ``feature_dependencies`` like a :class:`SubshapeRef`/:class:`FeatureRef` (via
         *     the widened :func:`iter_feature_refs` / :func:`feature_references`), so
         *     deleting that feature is a write-time 409-with-dependents and a reorder
         *     re-checks strict-backward. ``subshape_type`` is ``"edge"``. A pick UI echoes
         *     a picked edge's ``/overlay`` :class:`EdgeSignature` straight into ``selector``.
         */
        EdgeSubshapeRef: {
            /**
             * Feature Id
             * Format: uuid
             */
            feature_id: string;
            /**
             * Kind
             * @constant
             */
            kind: "subshape";
            selector: components["schemas"]["EdgeSelectorV1"];
            /**
             * Subshape Type
             * @constant
             */
            subshape_type: "edge";
        };
        /**
         * EntityPointRef
         * @description Names one point of one entity, e.g. ``{"entity": "e1", "point": "end"}``.
         *
         *     ``point`` is a fixed named point (``start``/``end``/``center``/``position``)
         *     for a line/arc/circle/point entity, or a spline fit point (``"fit0"``,
         *     ``"fit1"``, …) for a :class:`SketchSpline` — a constraint addresses a
         *     spline's Nth fit point exactly as it addresses a line's endpoint.
         */
        EntityPointRef: {
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /** Point */
            point: ("start" | "end" | "center" | "position") | string;
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"];
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
         * FaceSelector
         * @description The faces to REMOVE (leave open) in a shell, named by stage-1 signatures.
         *
         *     Each ref is a :class:`SubshapeRef` — the SAME planar-face signature the
         *     ``on_face`` datum uses (topo-naming §4), resolved against the current body
         *     nearest-within-tolerance, exactly one or an honest error. The face
         *     signatures the geometry service resolves are the ones a pick UI echoes
         *     straight from ``/overlay`` (the sketch-on-face pick set).
         *
         *     DESIGN DECISION (v1, docs/GEOMETRY-QA.md 2026-07-13): an EMPTY ``refs`` list
         *     is a valid, meaningful selection — a **fully-enclosed hollow** (the standard
         *     "hollow but sealed" case: a closed shell with a uniform-thickness cavity and
         *     NO opening). A non-empty list opens exactly those faces. So — unlike the
         *     picked-EDGE selector, whose empty list is a request-validation 422 (an empty
         *     fillet is a silent no-op) — an empty picked-FACE list is a real operation and
         *     carries no ``min_length``. Duplicate refs that resolve to the same face
         *     collapse to one (idempotent) at resolution.
         */
        FaceSelector: {
            /**
             * Kind
             * @constant
             */
            kind: "faces";
            /**
             * Refs
             * @description The planar faces to leave OPEN (each a stage-1 face SubshapeRef resolved against the current body). EMPTY = a fully-enclosed hollow (no opening) — a valid selection, not a 422 (design decision).
             */
            refs?: components["schemas"]["SubshapeRef"][];
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"];
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"];
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
            feature?: (components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"]) | null;
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
            edges: components["schemas"]["AllEdgesSelector"] | components["schemas"]["AxisParallelEdgesSelector"] | components["schemas"]["PickedEdgesSelector"];
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
         * ImportFeature
         * @description ``{"type": "import", "version": 1, "params": {...}}`` envelope.
         *
         *     A body-affecting BASE feature (docs/design/step-import.md §1): it produces
         *     the imported solid as the part's base body, rather than modifying a prior
         *     one. ``params`` is :class:`ImportParamsV1` (inline STEP text in v1).
         */
        ImportFeature: {
            params: components["schemas"]["ImportParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "import";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * ImportParamsV1
         * @description Bring an external STEP solid in as the part's base body (v1, inline).
         *
         *     ``data`` is the STEP AP214 part-21 TEXT inline (docs/design/step-import.md
         *     §2b), bounded by :data:`MAX_INLINE_STEP_CHARS` — an oversize or empty payload
         *     is a request-validation 422 at the boundary (§6), never a per-feature rebuild
         *     error. The geometry service reads it deterministically through a pinned
         *     ``STEPControl_Reader`` (units pinned to mm, RESEARCH §9): the same bytes yield
         *     a byte-identical body/mesh across rebuilds and interpreter restarts.
         *
         *     v1 accepts EXACTLY ONE solid; a compound / open shells / surfaces-only file
         *     is an honest ``import_not_single_solid`` rebuild error whose message carries
         *     the shape stats (the v1 "healing report" — §4), and unparseable bytes are
         *     ``import_parse_failed`` (§5). Sewing/repair, multi-solid assemblies, IGES,
         *     and a positioned insert against an existing body are deferred (§7).
         *
         *     ``kind``/``format`` default so a future blob-ref source (§2a) and IGES join
         *     additively with no ``param_version`` bump.
         */
        ImportParamsV1: {
            /**
             * Data
             * @description STEP AP214 part-21 file text (inline). Bounded/non-empty at parse time (422); parsed to exactly one solid by the geometry service.
             */
            data: string;
            /**
             * Format
             * @default step
             * @constant
             */
            format: "step";
            /**
             * Kind
             * @default inline
             * @constant
             */
            kind: "inline";
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
         * LoftFeature
         * @description ``{"type": "loft", "version": 1, "params": {...}}`` envelope.
         */
        LoftFeature: {
            params: components["schemas"]["LoftParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "loft";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * LoftParamsV1
         * @description Blend a solid THROUGH two or more ordered section sketches (design §4.3).
         *
         *     The loft sibling of :class:`SweepParamsV1` and the second non-prismatic
         *     body-affecting feature: where sweep drives ONE profile along a path, a loft
         *     skins a solid through an ORDERED list of cross-section sketches (the
         *     transitional-solid / cone / adapter primitive named in the Part-modeling
         *     scorecard notes). It shares the SAME ``add``/``cut`` boolean against the body
         *     chain as extrude/revolve/sweep; the new ingredient is ``profiles``, a list
         *     of ``FeatureRef``s (min 2) to earlier sketch features, blended in list order.
         *
         *     Section representation (v1 DESIGN DECISION — docs/GEOMETRY-QA.md
         *     2026-07-12): each ``profiles`` entry is a whole earlier SKETCH feature
         *     referenced by id — the same stable-feature-id mechanism the extrude/revolve
         *     ``profile`` and sweep ``profile``/``path`` slots use. This is NOT topological
         *     naming (#1): it references a whole feature's evaluated wire, never a picked
         *     sub-edge. A section's non-construction entities form either a single CLOSED
         *     profile wire (built by the shared ``build_profile_face``) OR a single POINT,
         *     interpreted as an APEX vertex (the standard loft-to-a-point tip); an apex may
         *     appear only as the FIRST or LAST section.
         *
         *     Why apex support in v1 (honest limit, not gold-plating): datum planes are
         *     origin-only and mutually perpendicular (never parallel), so two parallel
         *     offset circular sections — a cylinder/frustum — are not authorable until
         *     offset datum planes land. A closed section lofted to an apex point IS
         *     authorable and gives an analytic solid (a pyramid/cone), which is the loft
         *     golden's mass-property anchor.
         *
         *     v1 limits (stated plainly — documented scope, not bugs):
         *
         *     * a RULED (straight) loft through the sections in list order — NO guide
         *       rails, NO tangency/normal end conditions, NO periodic (closed) loft, NO
         *       per-section twist/alignment control (all later, additive params — no
         *       ``param_version`` bump);
         *     * sections are coplanar-or-parallel profiles as authored (each sketch
         *       carries its own plane); an open/non-closed section is a
         *       ``profile_not_closed`` rebuild error, a multi-loop section is
         *       ``profile_unsupported``, and a section ref that is not an earlier ok
         *       sketch is ``reference_unresolved`` (exactly like extrude/sweep);
         *     * incompatible sections (crossed rails), an apex wedged between two wire
         *       sections, or a skin OCCT cannot reduce to exactly one solid is a kernel
         *       ``loft_failed`` rebuild error, never a silently bad body.
         */
        LoftParamsV1: {
            /**
             * Operation
             * @enum {string}
             */
            operation: "add" | "cut";
            /**
             * Profiles
             * @description Ordered earlier sketch features (>= 2) to blend through; each forms a single closed profile wire or a single apex point (design §2.2). Fewer than 2 is a request-validation 422.
             */
            profiles: components["schemas"]["FeatureRef"][];
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
         * PickedEdgesSelector
         * @description SPECIFIC picked edges, named by stage-1 :class:`EdgeSignature` refs.
         *
         *     The topological-naming variant (design §2.4/§10) — the "the edge I clicked"
         *     selection the predicates (``all_edges`` / ``axis_parallel``) structurally
         *     cannot express: an engineer rounds ONE edge and leaves its neighbour sharp.
         *     Each ref is an :class:`EdgeSubshapeRef` carrying an :class:`EdgeSignature`
         *     the geometry service resolves against the current body — nearest-within-
         *     tolerance, exactly one or an honest error. At least one ref (``min_length=1``
         *     — an empty picked-edge selection is a request-validation 422, never a silent
         *     no-op). Added BESIDE the predicates (design §7.6), not replacing them:
         *     ``all_edges``/``axis_parallel`` remain the right tool for SET selections.
         */
        PickedEdgesSelector: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "edges";
            /**
             * Refs
             * @description The specific picked edges (>= 1), each a stage-1 EdgeSignature reference resolved against the current body
             */
            refs: components["schemas"]["EdgeSubshapeRef"][];
        };
        /**
         * PlanarFaceSignature
         * @description §2b stage-1 geometric fingerprint of a PLANAR face — typed, kernel-free.
         *
         *     Full-precision invariants (§7.2 forbids quantizing the stored identity): the
         *     outward unit ``normal``, the area ``centroid`` (world mm), and the
         *     ``area_mm2``. A planar face is uniquely fixed among a body's faces by
         *     (normal, centroid, area) in the common case; congruent twins of a symmetric
         *     part tie and resolve to an honest ``subshape_ambiguous`` (§5), never a guess.
         *     Matching is nearest-within-tolerance at the documented subshape tolerance
         *     (geometry.kernel.faces / docs/GEOMETRY-QA.md), never an ad-hoc epsilon.
         */
        PlanarFaceSignature: {
            /**
             * Area Mm2
             * @description Face area (mm^2), full precision
             */
            area_mm2: number;
            /** @description Area centroid of the face, world mm (full precision) */
            centroid: components["schemas"]["Vec3"];
            /** @description Outward unit normal of the planar face (full precision) */
            normal: components["schemas"]["Vec3"];
            /**
             * Subshape Type
             * @default face
             * @constant
             */
            subshape_type: "face";
            /**
             * Surface
             * @default plane
             * @constant
             */
            surface: "plane";
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
         * @description Dimension: the radius of a circle or arc (mm). Driving by default; see
         *     :class:`DimensionConstraint` for the expression/name/driving fields.
         */
        RadiusConstraint: {
            /**
             * Driving
             * @description Driving/driven flag. None (absent, the default) or True = DRIVING: the value is fed to the solver. False = DRIVEN: excluded from the constraint system; the value is measured back from the solved geometry for display (read-only, never fed as a constraint, so a driven dimension cannot over-constrain). Nullable+None-default (rather than a bare `bool`) keeps it an ADDITIVE optional field: a sketch persisted before it reads as None = driving, and the generated TS client leaves it optional. Read it through `is_driving`, never the raw tri-state.
             */
            driving?: boolean | null;
            /**
             * Entity
             * @description Sketch-local entity id, e.g. 'e1'
             */
            entity: string;
            /**
             * Expression
             * @description Optional math expression over other dimension NAMES (`+ - * / ( )`, unary minus, decimals), e.g. `"width/2"`. When present it SUPERSEDES `value_mm` and the geometry service re-evaluates it each solve. A bare literal dimension leaves this None. Only *driving* dimensions may be referenced; a bad expression / unknown or driven reference / cycle / division-by-zero is a clean `sketch_invalid` error, never a crash. Capped at 256 chars: an expression is a short formula over dimension names (`(width+gap)/2`), never prose, and the cap bounds parser paren-depth (<=128) and evaluator AST-depth (<=128) well under Python's recursion limit, so a hostile deeply-nested / very-long string 422s at request validation BEFORE the recursive-descent parser runs — it can never reach the kernel as an uncaught RecursionError. The parser also carries its own depth guard (defense in depth) should this cap ever be raised.
             */
            expression?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "radius";
            /**
             * Name
             * @description Optional stable name so another dimension's `expression` can reference this one. Unique within a sketch (enforced on SketchDefinition). None = unnamed: still solves, just not referenceable.
             */
            name?: string | null;
            /**
             * Value Mm
             * @description Resolved dimension value (mm). The literal value when `expression` is None; otherwise the last solved/resolved value (the expression supersedes it on the next solve, but a positive placeholder is still required so a pre-solve read has a value).
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
         * SelectorV1
         * @description Stage-1 selector payload: the geometric signature alone (§3, §4).
         *
         *     ``selector_version`` is the discriminator of the (currently single-member)
         *     ``Selector`` union — decoupled from feature ``param_version`` (§4). Stage 2
         *     adds a ``SelectorV2`` member (signature + provenance) additively, at which
         *     point ``Selector`` becomes ``Annotated[SelectorV1 | SelectorV2,
         *     Field(discriminator="selector_version")]`` with no change to persisted v1
         *     rows. pydantic forbids a discriminated single-member union, so ``Selector``
         *     is a plain alias until then (same idiom as :data:`FeatureData`).
         */
        SelectorV1: {
            /**
             * Selector Version
             * @default 1
             * @constant
             */
            selector_version: 1;
            signature: components["schemas"]["PlanarFaceSignature"];
        };
        /**
         * ShellFeature
         * @description ``{"type": "shell", "version": 1, "params": {...}}`` envelope.
         */
        ShellFeature: {
            params: components["schemas"]["ShellParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "shell";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * ShellParamsV1
         * @description Hollow the current body to a uniform wall thickness, opening picked faces.
         *
         *     The housing / enclosure / cup primitive (a Part-modeling scorecard item):
         *     the solid is thinned inward to a uniform wall of ``thickness_mm`` and the
         *     faces named by ``faces`` are REMOVED, leaving those sides open. Like a
         *     fillet/chamfer/pattern it modifies the implicit single body chain (design
         *     §7.6), so it carries no whole-feature ``FeatureRef`` — its dependency on the
         *     prior body-affecting feature is tree order. The picked openings ARE named
         *     references, though: each :class:`SubshapeRef` in ``faces`` materializes into
         *     ``feature_dependencies`` exactly like an ``on_face`` datum's face ref, so
         *     deleting the referenced body feature is a write-time 409-with-dependents and
         *     a reorder re-checks strict-backward.
         *
         *     Thickness is a UNIFORM INWARD offset (the wall grows into the solid, so the
         *     outer envelope is unchanged). An empty ``faces`` list hollows to a sealed
         *     (fully-enclosed) cavity; a non-empty list opens those faces
         *     (:class:`FaceSelector`). A thickness that would collapse or self-intersect
         *     the cavity (≥ the smallest half-wall) is a per-feature
         *     ``shell_thickness_too_large`` rebuild error, never a silently wrong body
         *     (docs/GEOMETRY-QA.md 2026-07-13).
         */
        ShellParamsV1: {
            /** @description The faces to leave OPEN (a picked-face selector). Empty = a fully-enclosed hollow with no opening (design decision). */
            faces: components["schemas"]["FaceSelector"];
            /**
             * Thickness Mm
             * @description Uniform inward wall thickness (mm). Must be small enough that the inward cavity does not self-intersect; too large is a `shell_thickness_too_large` rebuild error.
             */
            thickness_mm: number;
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
         * @description Sketch on a plane — an origin datum, or a ``datum`` feature (design §2.1).
         *
         *     ``plane`` is a :data:`GeomRef`: a :class:`DatumPlaneRef` names one of the
         *     three origin datums (XY/XZ/YZ), or a :class:`FeatureRef` points at an earlier
         *     ``datum`` feature (an offset/parallel plane — docs/design/datum-planes.md).
         *     The ``FeatureRef`` variant is now accepted when it resolves to a ``datum``
         *     feature (widened in :func:`feature_references` from no acceptable target to
         *     ``{datum}``); the stored shape is unchanged, so this is purely additive — no
         *     ``param_version`` bump.
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
         * SketchSpline
         * @description A smooth **fit-point** curve — a C2 B-spline interpolating ``points``.
         *
         *     The free-form/organic profile entity (the last hard Sketching capability
         *     gap): the curve passes **through** every fit point in order (an *interpolating*
         *     B-spline, OCCT ``GeomAPI_Interpolate`` via ``Edge.make_spline``), so a closed
         *     profile wire containing a spline edge can extrude/revolve. ``points`` are the
         *     ordered fit points (mm, sketch-plane); **at least two** are required (two fit
         *     points degenerate to a straight interpolant — still valid). Consecutive fit
         *     points must be distinct; a coincident pair is a degenerate spline the profile
         *     builder rejects (``profile_not_closed``, like the degenerate-arc precedent).
         *
         *     Additive optional-free field-set (docs/design/feature-tree.md §1.3): this is
         *     a NEW entity **kind**, not a changed field. Persisted sketches are unaffected
         *     — the discriminated ``SketchEntity`` union keys on ``kind``, and no existing
         *     sketch carries ``kind: "spline"``, so every stored sketch still parses to the
         *     exact same entity it did before (totality holds; ``param_version`` unchanged).
         *
         *     **Solver interaction — constrainable FIT POINTS (v1.1).** planegcs still has
         *     no spline *primitive*, so the CURVE itself carries no tangent/curvature
         *     constraints. What v1.1 adds is that each fit point is addressable as a solver
         *     point: a constraint may name it ``{"entity": <spline id>, "point": "fitN"}``
         *     (:data:`SplineFitPointName`), and the solver adds THAT fit point to the
         *     constraint system so it takes the point-level constraints any other point can
         *     (coincident, fixed, symmetric — and, via a coincident-linked line, distance /
         *     horizontal / vertical). After the solve the spline is rebuilt through the
         *     solved fit-point positions, so it reshapes to satisfy its constraints.
         *
         *     A fit point contributes DOF **only when constrained**: a fit point no
         *     constraint references is left out of the constraint system entirely, so an
         *     UNCONSTRAINED spline still solves as fixed geometry (zero added DOF, fit
         *     points preserved bitwise) exactly as before. A reference to an out-of-range
         *     fit index (``"fit9"`` on a 3-point spline) is a malformed definition
         *     (``SketchDefinitionError``), like any unknown-point reference.
         *
         *     **Spline tangency stays DEFERRED (honest limit):** a common tangent between a
         *     spline and its neighbouring edge (curvature-continuity at a fit point) needs a
         *     native spline primitive in the solver and is not offered here — only fit-point
         *     *position* constraints are. It remains behind the ``SketchSolver`` protocol
         *     for a future solver (or a planegcs spline extension).
         */
        SketchSpline: {
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
            kind: "spline";
            /**
             * Points
             * @description Ordered fit points (mm) the curve interpolates through; at least two. Consecutive points must be distinct (a coincident pair is a degenerate spline, rejected at profile build).
             */
            points: components["schemas"]["Point2D"][];
        };
        /**
         * SubshapeRef
         * @description Stage-1 reference to ONE planar face of a body-affecting feature's result.
         *
         *     (docs/design/topological-naming.md §4.) ``feature_id`` is the stage-1 anchor
         *     — "the prior body-affecting feature whose body I signature-match against"
         *     (§4), NOT necessarily the originating feature (stage 2 shifts it to the true
         *     originating feature). It materializes into ``feature_dependencies`` like a
         *     :class:`FeatureRef` (via the widened :func:`iter_feature_refs` /
         *     :func:`feature_references`), so deleting that feature is a write-time
         *     409-with-dependents. ``subshape_type`` is ``"face"`` only in v1 (edge/vertex
         *     reserved — §10).
         */
        SubshapeRef: {
            /**
             * Feature Id
             * Format: uuid
             */
            feature_id: string;
            /**
             * Kind
             * @constant
             */
            kind: "subshape";
            selector: components["schemas"]["SelectorV1"];
            /**
             * Subshape Type
             * @constant
             */
            subshape_type: "face";
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
