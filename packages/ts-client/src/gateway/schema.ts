// GENERATED — do not edit; run `just gen`.
// Types for the gateway service (source contract: packages/contracts/gateway.openapi.json).
export interface paths {
    "/api/v1/assemblies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Assemblies
         * @description The caller's assemblies, oldest first.
         */
        get: operations["list_assemblies_api_v1_assemblies_get"];
        put?: never;
        /**
         * Create Assembly
         * @description Create an assembly owned by the caller (201; 409 envelope on duplicate name).
         */
        post: operations["create_assembly_api_v1_assemblies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Assembly
         * @description One owned assembly with its full instance + mate graph (uniform 404).
         */
        get: operations["get_assembly_api_v1_assemblies__assembly_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Assembly
         * @description Delete an owned assembly (204; 409 when instanced as a sub-assembly).
         */
        delete: operations["delete_assembly_api_v1_assemblies__assembly_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Assembly
         * @description Rename an assembly (bumps ``doc_version``; 422 stale / 409 name clash).
         */
        patch: operations["update_assembly_api_v1_assemblies__assembly_id__patch"];
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}/bom": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Assembly Bom
         * @description The assembly's flat bill of materials (direct instances only; uniform 404).
         *
         *     Documents aggregates the read model (one line per referenced document,
         *     quantity = shared-reference count, current name + kind, deleted-ref lines
         *     flagged ``missing``); the gateway proxies faithfully under the same
         *     auth/ownership posture as :func:`get_assembly`.
         */
        get: operations["get_assembly_bom_api_v1_assemblies__assembly_id__bom_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}/instances": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Instance
         * @description Add an instance referencing a part / sub-assembly (201).
         *
         *     Documents enforces cross-document integrity (existence + acyclicity) and
         *     the optimistic-concurrency guard; its 422 envelopes (``ref_document_not_found``,
         *     ``assembly_cycle``, ``stale_assembly_version``) are re-surfaced verbatim.
         */
        post: operations["create_instance_api_v1_assemblies__assembly_id__instances_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}/instances/{instance_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Instance
         * @description Remove an instance (cascades mates naming it); returns the updated graph.
         */
        delete: operations["delete_instance_api_v1_assemblies__assembly_id__instances__instance_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Instance
         * @description Re-place / rename / (un)ground / reorder an instance (bumps ``doc_version``).
         */
        patch: operations["update_instance_api_v1_assemblies__assembly_id__instances__instance_id__patch"];
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}/mates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Mate
         * @description Add a mate (201). Documents checks every named instance belongs to the
         *     assembly (``mate_instance_unknown`` / ``mate_self_reference`` 422 otherwise).
         */
        post: operations["create_mate_api_v1_assemblies__assembly_id__mates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}/mates/{mate_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Mate
         * @description Remove a mate; returns the updated graph (bumps ``doc_version``).
         */
        delete: operations["delete_mate_api_v1_assemblies__assembly_id__mates__mate_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}/redo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Redo Assembly
         * @description Redo one assembly-graph history step (clean no-op at the ring's top).
         */
        post: operations["redo_assembly_api_v1_assemblies__assembly_id__redo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assemblies/{assembly_id}/undo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Undo Assembly
         * @description Undo one assembly-graph history step (docs/design/undo-redo.md UR3).
         *
         *     The restored graph comes back with its new ``doc_version`` (and
         *     ``can_undo``/``can_redo``); at the ring's floor this is documents' clean
         *     no-op (current graph, version unchanged). Stale ``expected_version`` →
         *     422, resurfaced verbatim.
         */
        post: operations["undo_assembly_api_v1_assemblies__assembly_id__undo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description Exchange email + password for an access token (uniform 401 on failure).
         */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Me
         * @description The authenticated account (protected: bearer token required).
         */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Register
         * @description Create an account and sign it in (201, envelope 409 on duplicate).
         */
        post: operations["register_api_v1_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Drawings
         * @description The caller's drawings, oldest first.
         */
        get: operations["list_drawings_api_v1_drawings_get"];
        put?: never;
        /**
         * Create Drawing
         * @description Create a drawing owned by the caller (201; 409 envelope on duplicate name).
         */
        post: operations["create_drawing_api_v1_drawings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Drawing
         * @description One owned drawing with its full sheet/view/dimension/annotation tree.
         */
        get: operations["get_drawing_api_v1_drawings__drawing_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Drawing
         * @description Delete an owned drawing (204; uniform 404 for unknown/foreign ids).
         *
         *     A drawing is a pure LEAF (nothing references it), so its entire
         *     sheet/view/dimension/annotation layout CASCADEs — no dependents pre-check.
         */
        delete: operations["delete_drawing_api_v1_drawings__drawing_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Drawing
         * @description Rename a drawing (bumps ``doc_version``; 422 stale / 409 name clash).
         */
        patch: operations["update_drawing_api_v1_drawings__drawing_id__patch"];
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/annotations/{annotation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Annotation
         * @description Delete an annotation; returns the updated tree (bumps ``doc_version``).
         */
        delete: operations["delete_annotation_api_v1_drawings__drawing_id__annotations__annotation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/dimensions/{dimension_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Dimension
         * @description Delete a dimension; returns the updated tree (bumps ``doc_version``).
         */
        delete: operations["delete_dimension_api_v1_drawings__drawing_id__dimensions__dimension_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Drawing
         * @description Compose the drawing into a downloadable SVG/PDF/DXF artifact (design §4.2).
         *
         *     Auth-gated and rate-limited (an OCCT-CPU compose route, same posture as the
         *     parts export and the drawing-evaluate proxy — engineering audit F7). The
         *     two-hop aggregation: documents serves the drawing tree AND the referenced
         *     part's evaluation-ready feature prefix (principal attached, uniform 404 for an
         *     unknown/foreign drawing re-surfaced verbatim), the gateway assembles the
         *     :class:`ComposeDrawingRequest` from that persisted state, and the stateless
         *     geometry service (identity-free upstream) evaluates + places + serializes it.
         *     The artifact bytes stream back with geometry's ``Content-Type`` +
         *     ``Content-Disposition``; its per-format envelopes (e.g. ``not_implemented`` for
         *     ``dxf``) re-surface verbatim.
         */
        post: operations["export_drawing_api_v1_drawings__drawing_id__export_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/sheet": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Compose Drawing Sheet
         * @description Compose the drawing into the placed ``ComposedSheet`` MODEL (design §4.2, DE-1b).
         *
         *     The JSON-model twin of ``/{drawing_id}/export``: the SAME auth-gated,
         *     rate-limited two-hop aggregation (drawing tree + referenced part's
         *     evaluation-ready feature prefix from documents, principal attached; the compose
         *     hop is identity-free), but it calls geometry's ``/drawing/compose/sheet`` and
         *     returns the typed :class:`ComposedSheet` (placed views/edges/dimensions/title
         *     block in sheet-mm) instead of serialized bytes. This is the single placement
         *     source the DE-1c frontend cutover renders from — deleting the browser's
         *     duplicate placement engine. Deterministic (RESEARCH §9); the gateway just relays.
         */
        post: operations["compose_drawing_sheet_api_v1_drawings__drawing_id__sheet_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/sheets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Sheet
         * @description Add a sheet to a drawing (append at the tip; 422 on a stale version).
         */
        post: operations["create_sheet_api_v1_drawings__drawing_id__sheets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/sheets/{sheet_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Sheet
         * @description Delete a sheet (cascades its views/dimensions/annotations); returns the tree.
         */
        delete: operations["delete_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Sheet
         * @description Update a sheet's header (bumps ``doc_version``; 422 on empty/stale).
         */
        patch: operations["update_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__patch"];
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/annotations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Annotation
         * @description Add an annotation (v1: a note) to a sheet (append at the tip).
         */
        post: operations["create_annotation_api_v1_drawings__drawing_id__sheets__sheet_id__annotations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create View
         * @description Add a view referencing a part / assembly (append at the tip).
         *
         *     Documents enforces cross-document integrity (the referenced document must
         *     exist and belong to the caller); its ``ref_document_not_found`` 422 and the
         *     ``stale_drawing_version`` 422 are re-surfaced verbatim.
         */
        post: operations["create_view_api_v1_drawings__drawing_id__sheets__sheet_id__views_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/views/{view_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete View
         * @description Delete a view (cascades the dimensions it carries); returns the tree.
         */
        delete: operations["delete_view_api_v1_drawings__drawing_id__views__view_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update View
         * @description Re-frame / re-scale / re-place a view (bumps ``doc_version``).
         */
        patch: operations["update_view_api_v1_drawings__drawing_id__views__view_id__patch"];
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Dimension
         * @description Add a dimension to a view (append at the tip, ordered per sheet).
         *
         *     Documents runs the kernel-free write-time checks (a diameter/radius must
         *     name a circular edge, an angular dimension two straight edges); its
         *     ``dimension_requires_circular_edge`` / ``dimension_requires_straight_edges``
         *     422 envelopes are re-surfaced verbatim.
         */
        post: operations["create_dimension_api_v1_drawings__drawing_id__views__view_id__dimensions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/assembly/evaluate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Assembly Evaluate
         * @description Proxy an assembly evaluation to the geometry service (assemblies §4).
         *
         *     Auth-protected (an assembly graph belongs to a signed-in user); the
         *     geometry hop stays identity-free, so the principal never travels upstream
         *     (same posture as measure/overlay, RESEARCH §3). The shared
         *     :class:`EvaluateAssemblyRequest` DTO validates at the gateway before
         *     anything goes upstream. Geometry evaluates each unique part once (shared
         *     content-addressed mesh), solves the mate graph, and returns per-instance
         *     ``{shared mesh id, solved placement}`` plus an analytic combined roll-up. A
         *     bad part / mate / solve is a 200 with a typed per-entry error or a
         *     non-``well_constrained`` status (design §4); the envelope stays reserved
         *     for transport/validation failures of this call itself.
         */
        post: operations["assembly_evaluate_api_v1_geometry_assembly_evaluate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/assembly/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Assembly Export
         * @description Proxy an assembly export to the geometry service; pass the file through.
         *
         *     Auth-protected (an assembly graph belongs to a signed-in user); the geometry
         *     hop stays identity-free, so the principal never travels upstream (same
         *     posture as ``/export`` + ``/assembly/evaluate``, RESEARCH §3). The shared
         *     :class:`ExportAssemblyRequest` DTO validates at the gateway before anything
         *     goes upstream. Geometry solves the assembly and composes it into ONE
         *     multi-instance STEP (AP214 product structure) or STL; a body-less assembly is
         *     a 422 ``assembly_export_no_body`` envelope, re-surfaced verbatim.
         */
        post: operations["assembly_export_api_v1_geometry_assembly_export_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/drawing/evaluate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Drawing Evaluate
         * @description Proxy a drawing-view evaluation to the geometry service (drawings §1.2/§4).
         *
         *     Auth-protected (a drawing belongs to a signed-in user); the geometry hop
         *     stays identity-free, so the principal never travels upstream (same posture
         *     as measure/overlay + assembly-evaluate, RESEARCH §3). The shared
         *     :class:`EvaluateDrawingViewsRequest` DTO validates at the gateway before
         *     anything goes upstream. Geometry evaluates the referenced part body once
         *     (reusing ``evaluate_tree``) then runs exact HLR per requested view, returning
         *     per-view canonically-ordered neutral 2D edges OR a typed per-view projection
         *     error. A feature/HLR failure is a 200 with a typed per-view (or whole-part)
         *     error (design §1.5/§4); the envelope stays reserved for transport/validation
         *     failures of this call itself.
         */
        post: operations["drawing_evaluate_api_v1_geometry_drawing_evaluate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/export": {
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
         * @description Build + export on the geometry service; pass the file bytes through.
         */
        post: operations["export_api_v1_geometry_export_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/measure": {
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
         * @description Proxy a stateless distance measurement to the geometry service.
         *
         *     Auth-protected (a measurement reads a signed-in user's part geometry);
         *     the geometry hop itself stays identity-free, so the principal never goes
         *     upstream (same posture as the mesh-fetch proxy, RESEARCH §3). The shared
         *     :class:`MeasureRequest` DTO validates at the gateway — a malformed target
         *     or an edge target with no ``tree`` is a 422 here and never reaches
         *     geometry. Upstream envelopes (``tree_measure_failed``,
         *     ``edge_index_out_of_range``, …) are re-surfaced verbatim.
         */
        post: operations["measure_api_v1_geometry_measure_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/meshes/{mesh_glb_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Fetch Mesh
         * @description Fetch an evaluated body's GLB artifact through the gateway.
         *
         *     Auth-protected (the artifact comes from a signed-in user's part
         *     evaluation); the geometry hop itself stays identity-free, so the
         *     principal never goes upstream. Upstream 404 ``mesh_not_found`` is the
         *     client's re-evaluate signal and is re-surfaced verbatim (§7.8).
         */
        get: operations["fetch_mesh_api_v1_geometry_meshes__mesh_glb_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/overlay": {
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
         * @description Proxy a stateless selection-overlay query to the geometry service.
         *
         *     Auth-protected (the overlay describes a signed-in user's part geometry);
         *     the geometry hop itself stays identity-free, so the principal never goes
         *     upstream (same posture as the measure + mesh-fetch proxies, RESEARCH §3).
         *     The shared :class:`OverlayRequest` DTO validates at the gateway. Upstream
         *     envelopes (``tree_overlay_failed``, ``overlay_failed``) are re-surfaced
         *     verbatim. The response carries the body's exact pickable vertices + edges,
         *     the edge list index-aligned with ``/measure``'s ``EdgeTarget.index``.
         */
        post: operations["overlay_api_v1_geometry_overlay_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/sketch/chamfer": {
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
         * @description Proxy a stateless sketch corner chamfer to the geometry service.
         *
         *     Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
         *     The shared ``SketchChamferRequest`` DTO validates at the gateway (a duplicate
         *     entity id, or a non-positive/non-finite distance, is a 422 here and never
         *     reaches geometry); upstream envelopes (``sketch_target_not_found``,
         *     ``sketch_unsupported_entity``, ``sketch_corner_not_found``,
         *     ``sketch_corner_too_large``, ``sketch_degenerate_result``) are re-surfaced
         *     verbatim.
         */
        post: operations["sketch_chamfer_api_v1_geometry_sketch_chamfer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/sketch/extend": {
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
         * @description Proxy a stateless sketch extend to the geometry service.
         *
         *     Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
         *     Upstream envelopes (``sketch_extend_no_target``, ``sketch_unsupported_entity``,
         *     ``sketch_target_not_found``, ``sketch_degenerate_result``) are re-surfaced
         *     verbatim.
         */
        post: operations["sketch_extend_api_v1_geometry_sketch_extend_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/sketch/fillet": {
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
         * @description Proxy a stateless sketch corner fillet to the geometry service.
         *
         *     Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
         *     The shared ``SketchFilletRequest`` DTO validates at the gateway (a duplicate
         *     entity id, or a non-positive/non-finite radius, is a 422 here and never
         *     reaches geometry); upstream envelopes (``sketch_target_not_found``,
         *     ``sketch_unsupported_entity``, ``sketch_corner_not_found``,
         *     ``sketch_corner_too_large``, ``sketch_degenerate_result``) are re-surfaced
         *     verbatim.
         */
        post: operations["sketch_fillet_api_v1_geometry_sketch_fillet_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/sketch/mirror": {
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
         * @description Proxy a stateless sketch mirror to the geometry service.
         *
         *     Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
         *     The shared ``SketchMirrorRequest`` DTO validates at the gateway (a duplicate
         *     entity id, or an empty ``targets`` list, is a 422 here and never reaches
         *     geometry); upstream envelopes (``sketch_target_not_found``,
         *     ``sketch_mirror_axis_not_line``, ``sketch_mirror_degenerate_axis``,
         *     ``sketch_unsupported_entity``) are re-surfaced verbatim.
         */
        post: operations["sketch_mirror_api_v1_geometry_sketch_mirror_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/sketch/offset": {
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
         * @description Proxy a stateless sketch offset to the geometry service.
         *
         *     Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
         *     The shared ``SketchOffsetRequest`` DTO validates at the gateway (a duplicate
         *     entity id is a 422 here and never reaches geometry); upstream envelopes
         *     (``sketch_target_not_found``, ``sketch_unsupported_entity``,
         *     ``sketch_offset_zero_distance``, ``sketch_degenerate_result``) are
         *     re-surfaced verbatim.
         */
        post: operations["sketch_offset_api_v1_geometry_sketch_offset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/sketch/trim": {
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
         * @description Proxy a stateless sketch trim to the geometry service.
         *
         *     Auth-protected (the edit rewrites a signed-in user's sketch); the geometry
         *     hop stays identity-free, so the principal never travels upstream (same
         *     posture as measure/overlay, RESEARCH §3). The shared ``SketchEditRequest``
         *     DTO validates at the gateway (a duplicate entity id is a 422 here and never
         *     reaches geometry); upstream envelopes (``sketch_target_not_found``,
         *     ``sketch_pick_not_on_target``, ``sketch_unsupported_entity``, …) are
         *     re-surfaced verbatim.
         */
        post: operations["sketch_trim_api_v1_geometry_sketch_trim_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/tessellate": {
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
         * @description Build + tessellate on the geometry service; pass the GLB through.
         */
        post: operations["tessellate_api_v1_geometry_tessellate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/geometry/tessellate/meta": {
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
        post: operations["tessellate_meta_api_v1_geometry_tessellate_meta_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Parts
         * @description The caller's parts, oldest first.
         */
        get: operations["list_parts_api_v1_parts_get"];
        put?: never;
        /**
         * Create Part
         * @description Create a part owned by the caller (201; 409 envelope on duplicate name).
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
         * @description One of the caller's parts (404 envelope for unknown/foreign ids).
         */
        get: operations["get_part_api_v1_parts__part_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Part
         * @description Delete one of the caller's parts (204; 404 for unknown/foreign ids).
         */
        delete: operations["delete_part_api_v1_parts__part_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Part
         * @description Rename and/or re-unit one of the caller's parts (bumps ``tree_version``).
         *
         *     The document-unit selector (docs/design/units.md §U1) changes ``length_unit``
         *     through this route; 404 envelope for unknown/foreign ids, 422 on a stale
         *     ``expected_tree_version``, 409 on a duplicate name.
         */
        patch: operations["update_part_api_v1_parts__part_id__patch"];
        trace?: never;
    };
    "/api/v1/parts/{part_id}/evaluate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Evaluate Part
         * @description Evaluate the part's current feature tree (feature-tree design §4).
         *
         *     The full loop behind one authenticated call: documents serves the
         *     evaluation-ready list (rollback bar applied, params upcast — §4.2), the
         *     gateway forwards it verbatim to the stateless geometry service, and the
         *     typed result comes back with per-feature statuses and solved-sketch
         *     ``data`` payloads (§7.10). Feature failures are a 200 with per-feature
         *     errors (§4.3); the error envelope here means the aggregation itself
         *     failed (404 unknown part, 502 unreachable upstream, ...).
         */
        post: operations["evaluate_part_api_v1_parts__part_id__evaluate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Part
         * @description Export the part's current evaluated body as a STEP or STL download.
         *
         *     The export twin of :func:`evaluate_part` and the same two-hop aggregation:
         *     documents serves the evaluation-ready feature list (rollback bar applied,
         *     params upcast — §4.2), the gateway wraps it with the requested format into
         *     an ``ExportTreeRequest`` and relays it to the stateless geometry service's
         *     tree-export route, and the file bytes stream back byte-exact. Auth-scoped
         *     like every parts route (the principal reaches documents, never geometry).
         *     A tree with no body is the geometry service's 422 ``tree_export_failed``
         *     envelope, re-surfaced verbatim.
         */
        post: operations["export_part_api_v1_parts__part_id__export_post"];
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
         * @description The part's ordered feature tree (404 for unknown/foreign parts).
         */
        get: operations["get_feature_tree_api_v1_parts__part_id__features_get"];
        put?: never;
        /**
         * Create Feature
         * @description Create a feature (201; 422 envelope on stale version / bad refs).
         */
        post: operations["create_feature_api_v1_parts__part_id__features_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}/features/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Import Step
         * @description Import an uploaded STEP file as the part's base body.
         *
         *     The STEP file is the raw request body. It is size-capped as it streams
         *     (oversize → 422 ``import_too_large`` before the body is fully read — §6),
         *     then decoded and mapped to an ``import`` feature whose inline
         *     ``params.data`` is the STEP text (§2b). Persistence reuses the ordinary
         *     documents feature-append path (``POST /features``), so an import onto a
         *     part that already has a body is documents' legible 422
         *     ``import_with_prior_body`` envelope, re-surfaced verbatim (§1). An empty
         *     upload or a file lacking the ISO-10303-21 header is a clean 422 here,
         *     before anything goes upstream.
         */
        post: operations["import_step_api_v1_parts__part_id__features_import_post"];
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
         * @description Apply a full permutation of the tree (backward-only refs re-checked).
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
         * @description One feature of the caller's part.
         */
        get: operations["get_feature_api_v1_parts__part_id__features__feature_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Feature
         * @description Delete a feature (409 envelope listing dependents when referenced).
         */
        delete: operations["delete_feature_api_v1_parts__part_id__features__feature_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Feature
         * @description Rename and/or replace a feature's params.
         */
        patch: operations["update_feature_api_v1_parts__part_id__features__feature_id__patch"];
        trace?: never;
    };
    "/api/v1/parts/{part_id}/redo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Redo Part
         * @description Redo one feature-tree history step (clean no-op at the ring's top).
         */
        post: operations["redo_part_api_v1_parts__part_id__redo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
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
         * @description Move the rollback bar (null = bar at the tip).
         */
        put: operations["move_rollback_bar_api_v1_parts__part_id__rollback_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/parts/{part_id}/undo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Undo Part
         * @description Undo one feature-tree history step (docs/design/undo-redo.md).
         *
         *     The restored tree comes back with its new ``tree_version``; at the
         *     ring's floor this is documents' clean no-op (current tree, version
         *     unchanged). Stale ``expected_tree_version`` → 422, resurfaced verbatim.
         */
        post: operations["undo_part_api_v1_parts__part_id__undo_post"];
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
         * AngleMate
         * @description Two planar faces held at a fixed angle (fast-follow, design §5).
         *
         *     The angular sibling of :class:`DistanceMate`: the coincident residual with
         *     the angle between the two normals targeted at ``angle_deg`` (§2.3). In the
         *     schema now; not v1-solver scope.
         */
        AngleMate: {
            /** @description First planar face */
            a: components["schemas"]["MateFaceRef"];
            /**
             * Angle Deg
             * @description Target angle between the two face normals (degrees)
             */
            angle_deg: number;
            /** @description Second planar face */
            b: components["schemas"]["MateFaceRef"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "angle";
        };
        /**
         * AngularDimensionParams
         * @description An angular dimension between two straight model edges (design §3.1).
         */
        AngularDimensionParams: {
            /** @description First straight model edge */
            edge_a: components["schemas"]["EdgeSignature"];
            /** @description Second straight model edge */
            edge_b: components["schemas"]["EdgeSignature"];
            /** @description Authored 2D placement */
            placement?: components["schemas"]["DimensionPlacement"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "angular";
        };
        /**
         * AnnotationCreate
         * @description Add an annotation to a sheet (append at the tip; design §2.2).
         */
        AnnotationCreate: {
            /** @description The annotation (v1: a note) */
            annotation: components["schemas"]["NoteAnnotationParams"];
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §2.1)
             */
            expected_version: number;
        };
        /**
         * AnnotationMutationResponse
         * @description Result of a single-annotation mutation: the annotation + the new version.
         */
        AnnotationMutationResponse: {
            annotation: components["schemas"]["AnnotationResponse"];
            /** Doc Version */
            doc_version: number;
        };
        /**
         * AnnotationResponse
         * @description An annotation as stored (design §2.2).
         */
        AnnotationResponse: {
            annotation: components["schemas"]["NoteAnnotationParams"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Order Index
             * @description Stable per-sheet order (dense 0..n-1)
             */
            order_index: number;
            /**
             * Sheet Id
             * Format: uuid
             */
            sheet_id: string;
        };
        /**
         * AssemblyBomResponse
         * @description An assembly's flat bill of materials (design: assemblies.md residual).
         *
         *     A pure documents-side READ MODEL — no writes, no migration: it aggregates
         *     the assembly's DIRECT instances into one :class:`BomLine` per referenced
         *     document (quantity = shared-reference count), resolving each document's
         *     current name from the ``parts`` / ``assemblies`` tables. Deterministically
         *     ordered (resolved name, then ``ref_document_id``) so the list is stable
         *     across reads. ``total_instances`` is the sum of every line's quantity (the
         *     assembly's direct-instance count), so an empty assembly is
         *     ``{lines: [], total_instances: 0}``.
         */
        AssemblyBomResponse: {
            /**
             * Assembly Id
             * Format: uuid
             */
            assembly_id: string;
            /**
             * Lines
             * @description One line per referenced document, deterministically ordered
             */
            lines: components["schemas"]["BomLine"][];
            /**
             * Total Instances
             * @description Sum of all line quantities (direct instance count)
             */
            total_instances: number;
        };
        /**
         * AssemblyCreate
         * @description Create an assembly owned by the calling user (design §1.2).
         */
        AssemblyCreate: {
            /**
             * Length Unit
             * @description Document display unit (docs/design/units.md §1); DISPLAY metadata only — storage stays canonical mm. Defaults to 'mm'.
             * @default mm
             * @enum {string}
             */
            length_unit: "mm" | "cm" | "m" | "in" | "ft";
            /**
             * Name
             * @description Assembly name; unique per owner, whitespace-trimmed, 1-200 characters
             */
            name: string;
        };
        /**
         * AssemblyGraphResponse
         * @description An assembly plus its full instance + mate graph and concurrency token.
         *
         *     The read model a client renders (design §1.2): the assembly header, its
         *     instances in ``order_index`` order, its mates in ``order_index`` order, and
         *     the ``doc_version`` the client echoes as its next ``expected_version``.
         */
        AssemblyGraphResponse: {
            assembly: components["schemas"]["AssemblyResponse"];
            /**
             * Can Redo
             * @description True when a later history snapshot exists to restore (the history cursor is below the ring's top)
             */
            can_redo: boolean;
            /**
             * Can Undo
             * @description True when an earlier history snapshot exists to restore (docs/design/undo-redo.md UR3) — lets the toolbar disable undo without a second call (the part tree's can_undo, applied here)
             */
            can_undo: boolean;
            /**
             * Doc Version
             * @description Echoed OCC token (== assembly.doc_version)
             */
            doc_version: number;
            /** Instances */
            instances: components["schemas"]["InstanceResponse"][];
            /** Mates */
            mates: components["schemas"]["MateResponse"][];
        };
        /**
         * AssemblyListResponse
         * @description The caller's assemblies, oldest first (wrapper leaves room for paging).
         */
        AssemblyListResponse: {
            /** Assemblies */
            assemblies: components["schemas"]["AssemblyResponse"][];
        };
        /**
         * AssemblyResponse
         * @description An assembly as stored — identity, ownership, and its concurrency token.
         *
         *     Mirrors :class:`~py_kit.schemas.parts.PartResponse` plus the ``doc_version``
         *     OCC counter. The full instance/mate graph rides :class:`AssemblyGraphResponse`.
         */
        AssemblyResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Doc Version
             * @description Monotonic optimistic-concurrency counter (design §1.2)
             */
            doc_version: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Length Unit
             * @description Document display unit (docs/design/units.md §1); DISPLAY metadata only — storage stays canonical mm.
             * @enum {string}
             */
            length_unit: "mm" | "cm" | "m" | "in" | "ft";
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
         * AssemblySolveDiagnosis
         * @description Structured diagnosis, mirroring ``SketchConstraintDiagnosis`` (design §2.4).
         *
         *     Read by field, never a parsed message. ``remaining_dof`` is first-class for
         *     the under-constrained case; ``conflicting_mates`` / ``redundant_mates`` name
         *     offending mates by id for the over/conflict cases.
         */
        AssemblySolveDiagnosis: {
            /**
             * Classification
             * @description 'redundant' (removable, still solves) or 'conflicting' (contradictory); None for a purely under-constrained diagnosis.
             */
            classification?: ("redundant" | "conflicting") | null;
            /**
             * Conflicting Mates
             * @description Ids of mutually-unsatisfiable mates (conflicting case).
             */
            conflicting_mates?: string[];
            /**
             * Message
             * @description Human-readable diagnosis.
             */
            message: string;
            /**
             * Redundant Mates
             * @description Ids of consistent-but-superfluous, removable mates.
             */
            redundant_mates?: string[];
            /**
             * Remaining Dof
             * @description Degrees of freedom left free at the seed (0 = fully located).
             * @default 0
             */
            remaining_dof: number;
            /**
             * Removable
             * @description True when the assembly still solves after removing the named redundant mates (the redundant case); False for a genuine conflict.
             * @default false
             */
            removable: boolean;
            /**
             * Suggested Fix
             * @description Actionable hint, e.g. 'Remove mate <id>'.
             */
            suggested_fix?: string | null;
        };
        /**
         * AssemblyUndoRedoRequest
         * @description Restore the adjacent assembly history snapshot (undo-redo.md UR3).
         *
         *     The assembly sibling of the part's
         *     :class:`~py_kit.schemas.features.UndoRedoRequest`: undo/redo ARE document
         *     edits — each bumps ``doc_version`` under the same optimistic-concurrency
         *     guard as every other assembly write (stale → 422,
         *     ``stale_assembly_version``), and the response is the restored graph
         *     (instance/mate ids preserved VERBATIM — the load-bearing snapshot
         *     decision). At a boundary — undo at the ring's floor, redo at its top —
         *     the op is a CLEAN no-op, not an error: 200 with the current graph,
         *     version unchanged. ``can_undo``/``can_redo`` on
         *     :class:`AssemblyGraphResponse` let the UI disable the controls, so a
         *     click racing that state is harmless.
         */
        AssemblyUndoRedoRequest: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §1.2)
             */
            expected_version: number;
        };
        /**
         * AssemblyUpdate
         * @description Rename and/or re-unit an assembly. Bumps ``doc_version`` (any mutation
         *     bumps — §1.2).
         *
         *     Both mutable fields are optional; at least one must be provided (mirroring
         *     :class:`InstanceUpdate`). Changing the display unit is a document edit
         *     (docs/design/units.md §U1) — metadata only, no stored ``*_mm`` value moves.
         */
        AssemblyUpdate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard: the doc_version the client last saw; a stale value is rejected 422 (design §1.2)
             */
            expected_version: number;
            /**
             * Length Unit
             * @description New document display unit (metadata only)
             */
            length_unit?: ("mm" | "cm" | "m" | "in" | "ft") | null;
            /**
             * Name
             * @description New assembly name
             */
            name?: string | null;
        };
        /**
         * AuthTokenResponse
         * @description A signed-in identity: the user plus a bearer access token.
         */
        AuthTokenResponse: {
            /**
             * Access Token
             * @description JWT for `Authorization: Bearer <token>`
             */
            access_token: string;
            /**
             * Expires In
             * @description Access-token lifetime in seconds
             */
            expires_in: number;
            /**
             * Token Type
             * @default bearer
             * @constant
             */
            token_type: "bearer";
            user: components["schemas"]["UserResponse"];
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
         * BendTableRow
         * @description One row of a flat-pattern view's bend table (sheet-metal.md §6/§7).
         *
         *     The shop's fold instructions for one bend line: a stable per-bend label
         *     (``bend_id``), its fold ``angle_deg`` and inner ``radius_mm``, the fold
         *     ``direction`` (up/down relative to the base flange), and the ``bend_allowance_mm``
         *     (``BA = angle_rad * (radius + K * thickness)``, §1 — the developed length the
         *     flat strip replaces). Every value is already computed by the unfold; documents
         *     stores none of it — it is derived geometry-side alongside the flat-pattern edges.
         *
         *     Correlation to the drawing edges is POSITIONAL, not id-based:
         *     :class:`ProjectedViewEdge` carries no id, so the i-th ``edge_role="bend"`` edge
         *     (in the view's edge-list order) is this row's fold line — both the bend edges and
         *     this table are emitted in the same deterministic fold-position order (§6). A
         *     consumer keys a table row to its fold stroke by zipping the ``"bend"`` edges with
         *     ``bend_table`` in order, never by matching ``bend_id`` against an edge field.
         */
        BendTableRow: {
            /**
             * Angle Deg
             * @description Fold angle (degrees)
             */
            angle_deg: number;
            /**
             * Bend Allowance Mm
             * @description Bend allowance BA = angle_rad * (radius + K * thickness), mm (§1)
             */
            bend_allowance_mm: number;
            /**
             * Bend Id
             * @description Stable per-bend label (e.g. 'bend-1'); NOT an edge id — bend rows correlate to 'bend' edges positionally, in fold-position order (§6)
             */
            bend_id: string;
            /**
             * Direction
             * @description Fold sense up/down (§1)
             * @enum {string}
             */
            direction: "up" | "down";
            /**
             * Radius Mm
             * @description Inner bend radius (mm)
             */
            radius_mm: number;
        };
        /**
         * BodyLumpInfo
         * @description Per-body lump count of an evaluated tree (docs/design/multi-body.md §MB-4).
         *
         *     The whole-part aggregate ``properties.topology.shells`` cannot tell a
         *     disjoint-union / multi-solid-import body (one body, several disjoint LUMPS)
         *     from a single-lump body: a sealed hollow inflates the shell count, and the
         *     aggregate sums across every body. This per-body entry carries the honest
         *     lump count so a consumer (the Bodies panel) can flag a multi-lump body.
         *
         *     ``base_feature_id`` is the body's identity — the id of the feature that
         *     CREATED it (§MB-0 Decision 1), the same key ``EvaluationState.bodies`` uses —
         *     so a caller maps the count back to the body/row it names. ``lumps`` is the
         *     number of disjoint connected solids (``>= 1``; a single-lump body reports
         *     ``1``), counted by ``geometry.kernel.lumps.lump_count``.
         */
        BodyLumpInfo: {
            /**
             * Base Feature Id
             * Format: uuid
             * @description Id of the feature that created this body (its §MB-0 identity)
             */
            base_feature_id: string;
            /**
             * Lumps
             * @description Number of disjoint connected solids (lumps) of this body; 1 for a single-lump body, >1 for a disjoint union / multi-solid import.
             */
            lumps: number;
        };
        /**
         * BomLine
         * @description One line of an assembly's bill of materials (a flat, direct-instance BOM).
         *
         *     A BOM line GROUPS the assembly's DIRECT instances by the document they
         *     reference: ``quantity`` is the count of instances sharing this
         *     ``ref_document_id``, ``name`` is the referenced document's CURRENT name, and
         *     ``ref_document_kind`` is ``part`` or ``assembly``. This is the FLAT v1 —
         *     direct instances only, NOT recursive into rigid sub-assemblies (an explicit
         *     follow-up; a sub-assembly instance appears as a single ``kind: "assembly"``
         *     line, never expanded).
         *
         *     A referenced document that was DELETED while still instanced surfaces
         *     honestly, not silently: the line stays (its instances still exist and still
         *     count), with ``name`` null and ``missing`` true, so a client can flag the
         *     dangling reference rather than the read 500-ing or the quantity vanishing.
         */
        BomLine: {
            /**
             * Missing
             * @description True when the referenced document no longer exists (deleted while still instanced) — the line and its quantity are still reported so the dangling reference is visible, never silently dropped
             * @default false
             */
            missing: boolean;
            /**
             * Name
             * @description The referenced document's CURRENT name, or null when it has been deleted while still instanced (see `missing`)
             */
            name: string | null;
            /**
             * Quantity
             * @description Count of direct instances referencing this document
             */
            quantity: number;
            /**
             * Ref Document Id
             * Format: uuid
             * @description The referenced part / sub-assembly document (the group key)
             */
            ref_document_id: string;
            /**
             * Ref Document Kind
             * @description 'part' or 'assembly' (a rigid sub-assembly, not expanded)
             * @enum {string}
             */
            ref_document_kind: "part" | "assembly";
        };
        /**
         * BooleanFeature
         * @description ``{"type": "boolean", "version": 1, "params": {...}}`` envelope.
         *
         *     A body-affecting feature that fuses two independently-built bodies
         *     (docs/design/multi-body.md §Decisions-3 / §MB-1): unlike extrude/revolve/…
         *     it consumes no sketch and produces no new primitive — it combines two
         *     existing bodies named by their base features. ``params`` is
         *     :class:`BooleanParamsV1` (``union`` wired in MB-1a; ``subtract``/``intersect``
         *     defined, wired in MB-2).
         */
        BooleanFeature: {
            params: components["schemas"]["BooleanParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "boolean";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * BooleanParamsV1
         * @description A boolean between two independently-built bodies (design §Decisions-3).
         *
         *     ``target`` and ``tool`` are :class:`FeatureRef`s to the BASE feature of each
         *     operand body (an ``extrude``/``revolve``/``sweep``/``loft``/``import`` — the
         *     body-CREATING features, NOT a modifier like fillet). ``target`` is the
         *     SURVIVING body (for ``subtract``, the minuend); ``tool`` is the CONSUMED body
         *     (the subtrahend). The boolean result takes over the target's identity slot and
         *     the tool body is removed from the part.
         *
         *     All three operations are wired (union MB-1a; subtract/intersect MB-2). By
         *     DEFAULT the v1 single-connected-solid-per-body invariant (§Decisions-3)
         *     governs the result: a union of non-touching bodies, or a subtract that SEVERS
         *     the target into ≥2 pieces, is a ``boolean_disjoint`` rebuild error; a subtract
         *     that removes the whole target, or an intersect with no overlap, is
         *     ``boolean_empty``.
         *
         *     MULTI-LUMP BODIES ARE OPT-IN (MB-4 / design §MB-4). Set ``allow_disjoint`` to
         *     accept a ``>1``-solid result as ONE multi-lump body — a :class:`Compound` of
         *     the disjoint lumps kept under the target's identity slot (a genuine
         *     "combine into one body" of, say, two non-touching bosses). It defaults
         *     ``False`` because a disjoint union is USUALLY a positioning bug, not an
         *     intent, so v1 keeps the safety error unless the author explicitly opts in.
         *     An EMPTY result is still ``boolean_empty`` / ``BooleanError`` regardless of
         *     the flag (there is no material to keep). The flag is additive-optional
         *     (absent reads ``False`` — the ``merge`` / ``flip`` idiom, NO ``param_version``
         *     bump).
         *
         *     v1 MULTI-LUMP LIMIT — coincident lumps are honestly ambiguous
         *     (design §MB-4, stated plainly): a downstream picked-face/edge reference on a
         *     multi-lump body resolves by ABSOLUTE-world-coordinate signature, so a lump at
         *     a distinct position resolves to exactly one subshape. But two lumps that
         *     truly COINCIDE in space (a self-union of congruent bodies) give congruent
         *     signatures and resolve to an honest ``subshape_ambiguous`` — the resolver
         *     refuses to guess, never a wrong-lump modification (topological-naming.md §5).
         *
         *     v1 TOPOLOGICAL-NAMING LIMIT (MB-3 / design §Decisions-4 — stated plainly, not
         *     oversold): a downstream feature (fillet/chamfer) CAN name an edge/face CREATED
         *     by a boolean — the fused body's subshapes get stage-1 signatures like any
         *     primitive's, so a fillet on a boolean-result edge resolves to exactly one edge
         *     on a CLEAN rebuild. But that reference is a best-effort stage-1 signature (see
         *     :class:`SubshapeRef` / :class:`EdgeSubshapeRef`), NOT structurally
         *     non-retargeting: a topology-CHANGING upstream edit that moves or removes the
         *     referenced subshape degrades to an honest ``subshape_unresolved`` /
         *     ``subshape_ambiguous`` — the SAME best-effort posture as every feature,
         *     booleans being its weakest case (a boolean seam is the documented
         *     ``subshape_ambiguous`` source). Never a wrong-edge modification or a crash;
         *     the structural fix is stage-2 provenance naming (topological-naming.md §10).
         */
        BooleanParamsV1: {
            /**
             * Allow Disjoint
             * @description Accept a >1-solid result as ONE multi-lump body (a Compound of the disjoint lumps) instead of a `boolean_disjoint` error (MB-4). Defaults False (a disjoint union is usually a positioning bug). An empty result is still `boolean_empty`. Additive — absent reads False, no param_version bump.
             * @default false
             */
            allow_disjoint: boolean;
            /**
             * Operation
             * @description Boolean operation: union (fuse), subtract (target minus tool) or intersect (common). All three wired (union MB-1a; subtract/intersect MB-2).
             * @enum {string}
             */
            operation: "union" | "subtract" | "intersect";
            /** @description Base feature of the SURVIVING body; the result takes over its identity slot so downstream refs keep resolving (design §Decisions-3) */
            target: components["schemas"]["FeatureRef"];
            /** @description Base feature of the CONSUMED body; removed from the part once the boolean succeeds (design §Decisions-3) */
            tool: components["schemas"]["FeatureRef"];
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
         * CoincidentMate
         * @description Two planar faces made coplanar + flush (design §2.1/§2.3).
         *
         *     ``flush`` chooses the normal sense: ``True`` = normals anti-parallel (the
         *     mating faces touch, the common bolted-flush case); ``False`` = normals
         *     parallel (faces back-to-back). The residual is a coplanar gap of zero plus
         *     the (anti)parallel normal constraint (§2.3).
         */
        CoincidentMate: {
            /** @description First planar face */
            a: components["schemas"]["MateFaceRef"];
            /** @description Second planar face */
            b: components["schemas"]["MateFaceRef"];
            /**
             * Flush
             * @description True = normals anti-parallel (mating faces touch); False = normals parallel (back-to-back)
             * @default true
             */
            flush: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "coincident";
        };
        /**
         * ComposedArrow
         * @description A filled arrowhead triangle — tip + two barb wings, in order (SVG space).
         */
        ComposedArrow: {
            /**
             * Points
             * @description The three triangle vertices
             */
            points: components["schemas"]["ComposedPoint"][];
        };
        /**
         * ComposedBendTable
         * @description A flat-pattern sheet's placed bend-table annotation block (sheet-metal.md §6/§7).
         *
         *     The shop's fold instructions for the placed flat blank, laid out as a quiet-corner
         *     block: the rectangle it occupies (``x``/``y``/``width``/``height`` in FINAL sheet-
         *     SVG space — y-down, top-left origin, the same space every other placed primitive
         *     uses) plus the per-bend ``rows`` (the :class:`BendTableRow` data the flat-pattern
         *     :class:`DrawingViewResult` already carries, passed through unchanged). The block is
         *     placed clear of the flat blank's drawn extent so it never overlaps the geometry.
         *
         *     Correlation to the placed fold strokes is POSITIONAL (sheet-metal.md §6), never an
         *     id linkage: the i-th ``rows`` entry pairs with the i-th ``edge_role="bend"``
         *     :class:`ComposedEdge` of the flat-pattern view, both in the unfold's deterministic
         *     fold-position order. A consumer zips the ``"bend"`` edges with ``rows`` in order.
         */
        ComposedBendTable: {
            /**
             * Height
             * @description Block height (mm)
             */
            height: number;
            /**
             * Rows
             * @description Per-bend fold rows, in fold-position order (positionally paired with the flat-pattern view's `edge_role='bend'` edges, §6)
             */
            rows: components["schemas"]["BendTableRow"][];
            /**
             * Width
             * @description Block width (mm)
             */
            width: number;
            /**
             * X
             * @description Block left edge (mm, SVG space)
             */
            x: number;
            /**
             * Y
             * @description Block top edge (mm, SVG space, y-down)
             */
            y: number;
        };
        /**
         * ComposedCircleEdge
         * @description A placed projected circle — exact (a Ø/radius dimension reads its radius).
         */
        ComposedCircleEdge: {
            /** Cx */
            cx: number;
            /** Cy */
            cy: number;
            /**
             * Edge Role
             * @description Outline role carried through composition (sheet-metal.md §6): 'body' (default, every HLR edge) or 'bend' (a flat-pattern fold line, styled as a distinct dashed-blue stroke). Orthogonal to `visible`.
             * @default body
             * @enum {string}
             */
            edge_role: "body" | "bend";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "circle";
            /** R */
            r: number;
            /**
             * Visible
             * @description True = solid; False = hidden (dashed)
             */
            visible: boolean;
        };
        /**
         * ComposedDimLine
         * @description One straight rule of a placed dimension (extension or dimension line).
         */
        ComposedDimLine: {
            /**
             * Role
             * @description `extension` = thin witness line; `dimension` = arrowed measure
             * @enum {string}
             */
            role: "extension" | "dimension";
            /** X1 */
            x1: number;
            /** X2 */
            x2: number;
            /** Y1 */
            y1: number;
            /** Y2 */
            y2: number;
        };
        /**
         * ComposedDimText
         * @description A placed dimension's stamped value — position, upright angle, label string.
         */
        ComposedDimText: {
            /**
             * Angle
             * @description Upright text angle (degrees)
             */
            angle: number;
            /**
             * Value
             * @description Stamped label ('Ø10.000' / '~40.000' / '90.0°')
             */
            value: string;
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /**
         * ComposedDimensionError
         * @description A placed dimension the model could not measure — an honest marker (§3.3).
         */
        ComposedDimensionError: {
            /** @description Marker position (SVG space) */
            at: components["schemas"]["ComposedPoint"];
            /**
             * Code
             * @description Typed measurement-failure code (never a value)
             */
            code: string;
            /**
             * Dimension Id
             * @description Correlation id (echoes the request), or null
             */
            dimension_id?: string | null;
            /**
             * Dimension Type
             * @description linear/diameter/radius/angular
             * @enum {string}
             */
            dimension_type: "linear" | "diameter" | "radius" | "angular";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "error";
        };
        /**
         * ComposedHatch
         * @description A section view's placed crosshatch (drawings-section.md §5) — the parallel
         *     fill strokes of every cross-section face.
         *
         *     Generated by :func:`geometry.drawings.compose.place_sheet`'s section branch: a set
         *     of parallel lines at the ANSI 45° angle and a fixed sheet-mm spacing, analytically
         *     clipped (even-odd scanline) to each face's outer loop minus its interior loops — so
         *     the hole is left blank. Every coordinate is in FINAL sheet-SVG space (mm, y-DOWN,
         *     top-left origin — the same space every other placed primitive uses), so a
         *     serializer draws each ``lines`` segment verbatim. Deterministic (§6): the loops,
         *     angle, spacing, and clip origin are pure functions of the projected geometry, so
         *     the same section ⇒ byte-identical strokes. Export-only in v1 (§5): the DOM sheet
         *     shows the section's edges + cut-face outline but no on-screen crosshatch.
         */
        ComposedHatch: {
            /**
             * Lines
             * @description Clipped 45° crosshatch strokes (sheet-SVG space), scanline order
             */
            lines: components["schemas"]["ComposedHatchLine"][];
        };
        /**
         * ComposedHatchLine
         * @description One crosshatch stroke of a placed section face (final sheet-SVG space).
         */
        ComposedHatchLine: {
            /** X1 */
            x1: number;
            /** X2 */
            x2: number;
            /** Y1 */
            y1: number;
            /** Y2 */
            y2: number;
        };
        /**
         * ComposedLineEdge
         * @description A placed straight projected edge (sheet-mm SVG space).
         */
        ComposedLineEdge: {
            /**
             * Edge Role
             * @description Outline role carried through composition (sheet-metal.md §6): 'body' (default, every HLR edge) or 'bend' (a flat-pattern fold line, styled as a distinct dashed-blue stroke). Orthogonal to `visible`.
             * @default body
             * @enum {string}
             */
            edge_role: "body" | "bend";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "line";
            /**
             * Visible
             * @description True = solid; False = hidden (dashed)
             */
            visible: boolean;
            /** X1 */
            x1: number;
            /** X2 */
            x2: number;
            /** Y1 */
            y1: number;
            /** Y2 */
            y2: number;
        };
        /**
         * ComposedMeasuredDimension
         * @description A placed, measured dimension: rules + arrowheads + the stamped value.
         */
        ComposedMeasuredDimension: {
            /**
             * Arrows
             * @description Filled arrowhead triangles
             */
            arrows: components["schemas"]["ComposedArrow"][];
            /**
             * Dimension Id
             * @description Correlation id (echoes the request), or null
             */
            dimension_id?: string | null;
            /**
             * Dimension Type
             * @description linear/diameter/radius/angular
             * @enum {string}
             */
            dimension_type: "linear" | "diameter" | "radius" | "angular";
            /**
             * Foreshortened
             * @description True: model-true value, foreshortened drawn length (§3.2)
             * @default false
             */
            foreshortened: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "measured";
            /**
             * Lines
             * @description Extension + dimension lines
             */
            lines: components["schemas"]["ComposedDimLine"][];
            /** @description The stamped value */
            text: components["schemas"]["ComposedDimText"];
        };
        /**
         * ComposedNote
         * @description A placed free-text note annotation (design §2.2 v1 — text at a sheet point).
         *
         *     The composed twin of :class:`NoteAnnotationParams`: the note ``text`` and its
         *     anchor ``x``/``y`` in FINAL sheet-SVG space (mm, y-DOWN, top-left origin — the
         *     same space every other placed primitive on :class:`ComposedSheet` uses), so a
         *     serializer stamps it verbatim (no re-reasoning about axes). The three serializers
         *     render it as left-anchored graphite-ink text, consistent with the title-block
         *     stamped values. Additive to the sheet: an empty ``notes`` list emits nothing, so a
         *     sheet with no notes composes byte-identically to its pre-notes golden. A note whose
         *     anchor falls outside the sheet is placed verbatim (clipped by the viewer), the same
         *     honest posture as a title-block text run — never a crash.
         */
        ComposedNote: {
            /**
             * Text
             * @description The note body, rendered verbatim
             */
            text: string;
            /**
             * X
             * @description Note anchor X (mm, SVG space)
             */
            x: number;
            /**
             * Y
             * @description Note anchor Y (mm, SVG space, y-down)
             */
            y: number;
        };
        /**
         * ComposedPoint
         * @description A 2D point in FINAL sheet-SVG space (mm, y-DOWN, top-left origin).
         */
        ComposedPoint: {
            /**
             * X Mm
             * @description X on the sheet (mm, SVG space)
             */
            x_mm: number;
            /**
             * Y Mm
             * @description Y on the sheet (mm, SVG space, y-down)
             */
            y_mm: number;
        };
        /**
         * ComposedPolylineEdge
         * @description A placed sampled edge (arc / free-form) as a polyline (sheet-mm SVG space).
         */
        ComposedPolylineEdge: {
            /**
             * Edge Role
             * @description Outline role carried through composition (sheet-metal.md §6): 'body' (default, every HLR edge) or 'bend' (a flat-pattern fold line, styled as a distinct dashed-blue stroke). Orthogonal to `visible`.
             * @default body
             * @enum {string}
             */
            edge_role: "body" | "bend";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "polyline";
            /**
             * Points
             * @description Ordered vertices (SVG space)
             */
            points: components["schemas"]["ComposedPoint"][];
            /**
             * Visible
             * @description True = solid; False = hidden (dashed)
             */
            visible: boolean;
        };
        /**
         * ComposedSheet
         * @description A fully placed drawing sheet — the model the three serializers render (§4.2).
         *
         *     Every coordinate is sheet-mm in final SVG space (y-down, top-left origin). The
         *     product of ``geometry.drawings.compose.place_sheet`` — a pure function of the
         *     evaluated geometry + the :class:`SheetLayout` (deterministic, RESEARCH §9). The
         *     paper + border rectangles are pure functions of ``width_mm``/``height_mm``/
         *     ``margin_mm`` (the serializer derives them), keeping this model lean.
         */
        ComposedSheet: {
            /** @description A flat-pattern sheet's placed bend-table block (rows + anchor rect, sheet-metal.md §7); null for every standard (HLR) sheet — additive, so a standard sheet composes byte-identically. */
            bend_table?: components["schemas"]["ComposedBendTable"] | null;
            /**
             * Height Mm
             * @description Sheet height (mm) — the SVG viewBox height
             */
            height_mm: number;
            /**
             * Margin Mm
             * @description Border inset from the sheet edge (mm)
             */
            margin_mm: number;
            /**
             * Notes
             * @description Placed free-text note annotations (design §2.2), each stamped at its sheet anchor; empty for a sheet with no notes — additive, so a note-free sheet composes byte-identically to its pre-notes golden.
             */
            notes?: components["schemas"]["ComposedNote"][];
            /**
             * Scale Label
             * @description The sheet scale label ('1:1')
             */
            scale_label: string;
            /**
             * Title
             * @description Drawing name (metadata / accessible label)
             */
            title: string;
            /** @description The placed title block */
            title_block: components["schemas"]["ComposedTitleBlock"];
            /**
             * Views
             * @description Placed views in canonical (front/top/right/iso) order
             */
            views?: components["schemas"]["ComposedView"][];
            /**
             * Width Mm
             * @description Sheet width (mm) — the SVG viewBox width
             */
            width_mm: number;
        };
        /**
         * ComposedTitleBlock
         * @description The placed bottom-right title block (drawing-export.md §4.2).
         *
         *     Geometry (box + the two internal rules) plus the stamped values: the always-on
         *     drawing ``title`` (truncated to fit), ``scale`` label and ``size`` display, plus
         *     the OPTIONAL free-text :class:`TitleBlock` fields ``author`` / ``date`` / ``notes``
         *     (each truncated to fit its cell, ``None`` when unset). The fixed captions ("TITLE" /
         *     "SCALE" / "SIZE" / "LOFT · PART DRAWING" and, for the optional fields, "DRAWN" /
         *     "DATE" / "NOTES") are the serializer's rendering constants (matching the on-screen
         *     title block). A ``None`` optional field is stamped by NO serializer — caption and
         *     value both omitted — so a title block with no free-text composes byte-identically to
         *     its pre-free-text golden (the additive posture the notes/bend-table fields carry).
         */
        ComposedTitleBlock: {
            /**
             * Author
             * @description Author/drafter, truncated to fit; None (stamps nothing) when the authored field is unset or blank
             */
            author?: string | null;
            /**
             * Date
             * @description Free-text date, truncated to fit; None (stamps nothing) when the authored field is unset or blank
             */
            date?: string | null;
            /** Height */
            height: number;
            /**
             * Mid Y
             * @description Y of the horizontal rule in the right cell
             */
            mid_y: number;
            /**
             * Notes
             * @description Free-text notes, truncated to fit; None (stamps nothing) when the authored field is unset or blank
             */
            notes?: string | null;
            /**
             * Scale
             * @description Scale label ('1:1')
             */
            scale: string;
            /**
             * Size
             * @description Sheet size, display form ('A4', 'ANSI A')
             */
            size: string;
            /**
             * Split X
             * @description X of the vertical rule (left | right cells)
             */
            split_x: number;
            /**
             * Title
             * @description Drawing title, truncated to fit the cell
             */
            title: string;
            /** Width */
            width: number;
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /**
         * ComposedView
         * @description One placed view on the sheet — its edges, dimensions, caption (design §4.2).
         *
         *     ``failed`` marks a view with no projection (an HLR failure or an absent
         *     result): the serializer stamps a "VIEW FAILED" placeholder at ``anchor`` and
         *     ``edges``/``dimensions`` are empty. ``anchor`` is the view-centre in SVG space
         *     (the placeholder + caption reference it); ``label``/``label_pos`` are the
         *     stamped caption ("FRONT") and its position.
         */
        ComposedView: {
            /** @description View-centre in SVG space */
            anchor: components["schemas"]["ComposedPoint"];
            /**
             * Dimensions
             * @description Placed dimensions
             */
            dimensions?: (components["schemas"]["ComposedMeasuredDimension"] | components["schemas"]["ComposedDimensionError"])[];
            /**
             * Edges
             * @description Placed projected edges
             */
            edges?: (components["schemas"]["ComposedLineEdge"] | components["schemas"]["ComposedCircleEdge"] | components["schemas"]["ComposedPolylineEdge"])[];
            /**
             * Failed
             * @description True when the view has no projected geometry
             */
            failed: boolean;
            /** @description A section view's placed crosshatch (drawings-section.md §5); null for every non-section view — additive, so a standard/flat-pattern view composes byte-identically (the `bend_table` pattern). */
            hatch?: components["schemas"]["ComposedHatch"] | null;
            /**
             * Label
             * @description Caption text (e.g. 'FRONT')
             */
            label: string;
            /** @description Caption position (SVG space) */
            label_pos: components["schemas"]["ComposedPoint"];
            /**
             * Projection
             * @description Projection direction
             * @enum {string}
             */
            projection: "front" | "top" | "right" | "iso" | "flat_pattern" | "section";
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
         * ConcentricMate
         * @description Two axes (from circular edges) made collinear (design §2.1/§2.3).
         *
         *     The bolt/pin half of the canonical joint: hole and shaft axes aligned. The
         *     residual makes the two directions parallel and the two lines coincident
         *     (§2.3).
         */
        ConcentricMate: {
            /** @description First axis */
            a: components["schemas"]["MateAxisRef"];
            /** @description Second axis */
            b: components["schemas"]["MateAxisRef"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "concentric";
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
         * DatumFeature
         * @description ``{"type": "datum", "version": 1, "params": {...}}`` envelope.
         *
         *     A non-body-affecting feature that produces a plane a later sketch sits on
         *     (docs/design/datum-planes.md §2b). ``params`` is the discriminated
         *     :data:`DatumParams` union — an ``offset`` plane (§3), an ``on_face`` plane
         *     (§7), an ``offset_from`` chained plane, or a ``midplane`` (§7a). Every
         *     variant after ``offset`` is ADDITIVE with NO ``param_version`` bump: legacy
         *     offset params (persisted before ``on_face`` existed) carry no ``kind``
         *     discriminator, so :meth:`_legacy_offset_kind` injects ``"offset"`` before
         *     validation and every existing datum row/golden validates unchanged
         *     (datum-planes §4/§7).
         */
        DatumFeature: {
            /** Params */
            params: components["schemas"]["DatumOffsetParams"] | components["schemas"]["DatumOnFaceParams"] | components["schemas"]["DatumOffsetFromParams"] | components["schemas"]["DatumMidplaneParams"];
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
         * DatumMidplaneParams
         * @description A plane midway between two references (``kind: "midplane"``).
         *
         *     The midplane slice of docs/design/datum-planes.md §7: each side resolves to
         *     a plane through the same funnels the sketch plane and the ``on_face`` datum
         *     use, and the datum bisects them. Conventions (documented in datum-planes §7a
         *     and implemented by ``geometry.kernel.datum.midplane_between`` — DETERMINISTIC,
         *     RESEARCH §9):
         *
         *     * PARALLEL sides (incl. anti-parallel normals, e.g. a box's top + bottom
         *       faces): the plane midway between them; normal = side ``a``'s normal;
         *       origin = the midpoint of the two resolved origins. Identical/coplanar
         *       sides degenerate cleanly to the plane itself.
         *     * NON-PARALLEL sides: the angular-bisector plane through their intersection
         *       line; normal = ``normalize(n_a + n_b)`` (well-defined for any non-parallel
         *       pair, perpendicular included — the documented normal-sign rule; flipping a
         *       side's normal selects the other bisector); origin = the point of the
         *       intersection line nearest the world origin (the minimum-norm solution —
         *       a pure closed form of the two planes).
         *     * Basis: ``z_dir`` = the convention normal above, ``x_dir`` pinned from it
         *       by ``geometry.kernel.faces.deterministic_x_dir`` (the on_face rule), so
         *       the 2D→3D mapping is stable across rebuilds.
         *
         *     A midplane over two RESOLVED sides is total — parallel, angular, and
         *     identical inputs all yield a valid plane — so its only failures are
         *     reference resolution: ``reference_unresolved`` (a side names a missing/
         *     later/non-datum feature) or ``subshape_unresolved``/``subshape_ambiguous``
         *     (a picked-face side, exactly the ``on_face`` taxonomy).
         */
        DatumMidplaneParams: {
            /**
             * A
             * @description First reference: an origin datum name, an earlier `datum` feature, or a picked planar face. Its normal signs the parallel-case midplane.
             */
            a: components["schemas"]["DatumPlaneRef"] | components["schemas"]["FeatureRef"] | components["schemas"]["SubshapeRef"];
            /**
             * B
             * @description Second reference (same forms as `a`).
             */
            b: components["schemas"]["DatumPlaneRef"] | components["schemas"]["FeatureRef"] | components["schemas"]["SubshapeRef"];
            /**
             * Flip
             * @description Reverse the plane normal (negate z_dir, keeping x_dir so sketch +u is unchanged and +v flips) — the same rule as `offset`.
             * @default false
             */
            flip: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "midplane";
        };
        /**
         * DatumOffsetFromParams
         * @description An EARLIER datum feature's plane slid along its normal (``kind: "offset_from"``).
         *
         *     Offset CHAINING (docs/design/datum-planes.md §7): ``base`` is a
         *     :class:`FeatureRef` to an earlier ``datum`` feature, and the plane is that
         *     datum's RESOLVED plane slid ``offset_mm`` along its normal, with the same
         *     optional ``flip`` an origin offset has. Chains compose left-to-right: origin
         *     → datum A → datum B resolves to the analytic composite (each hop is a pure
         *     ``Plane.offset``). The strict-backward rule (feature-tree §2.2) means the
         *     parent always evaluated first — a self/forward reference NEVER resolves (a
         *     write-time 422; the eval-time backstop is ``reference_unresolved``), so
         *     resolution is a single dict lookup, never a recursion.
         *
         *     DESIGN DECISION — a SEPARATE ``kind``, not a widened ``base`` union on
         *     :class:`DatumOffsetParams` (datum-planes §7 sketched the union): widening
         *     ``base`` to ``Literal[...] | FeatureRef`` changes the GENERATED ts-client
         *     type of every existing offset datum, breaking each consumer that reads
         *     ``params.base`` as a plane name (the viewport derives the offset basis
         *     client-side from it). A new discriminated kind is the established additive
         *     idiom (``on_face`` proved it): existing ``offset`` payloads stay
         *     byte-identical on the wire AND type-identical in the generated client, and
         *     NO ``param_version`` bump is needed.
         */
        DatumOffsetFromParams: {
            /** @description EARLIER `datum` feature whose resolved plane this plane offsets from (its orientation and origin). */
            base: components["schemas"]["FeatureRef"];
            /**
             * Flip
             * @description Reverse the plane normal (negate z_dir, keeping x_dir so sketch +u is unchanged and +v flips) — the same rule as `offset`.
             * @default false
             */
            flip: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "offset_from";
            /**
             * Offset Mm
             * @description Signed distance along the base datum's normal (mm). 0 coincides with the base datum; +/- selects side. Any finite value is valid.
             */
            offset_mm: number;
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
         *     (``geometry.kernel.faces.deterministic_x_dir``) so the 2D→3D mapping is
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
         * DiameterDimensionParams
         * @description A diameter dimension on a circular model edge (design §3.1).
         *
         *     ``edge`` must resolve to a CIRCULAR edge (``curve == "circle"``) — the
         *     identical reuse a ``concentric`` mate makes for its axis (design §3.3), so one
         *     signature names a hole for both mating and dimensioning. The measured value
         *     (2·radius) is computed geometry-side.
         */
        DiameterDimensionParams: {
            /** @description Circular model edge (curve == 'circle') */
            edge: components["schemas"]["EdgeSignature"];
            /** @description Authored 2D placement */
            placement?: components["schemas"]["DimensionPlacement"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "diameter";
        };
        /**
         * DimensionCreate
         * @description Add a dimension to a view (append at the tip; design §3).
         *
         *     ``dimension`` is the discriminated :data:`Dimension` union; its geometry
         *     references (via :class:`~py_kit.schemas.features.EdgeSignature`) resolve
         *     against the view's referenced body geometry-side. ``order_index`` is stable
         *     per sheet, appended at the tip.
         */
        DimensionCreate: {
            /**
             * Dimension
             * @description The dimension (discriminated on `type`)
             */
            dimension: components["schemas"]["LinearDimensionParams"] | components["schemas"]["DiameterDimensionParams"] | components["schemas"]["RadiusDimensionParams"] | components["schemas"]["AngularDimensionParams"];
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §2.1)
             */
            expected_version: number;
        };
        /**
         * DimensionEndpointRef
         * @description One canonical endpoint of a model edge (design §3.3 point-to-point linear).
         *
         *     ``endpoint`` selects ``end_a`` or ``end_b`` of the ``signature``'s
         *     canonically-ordered pair — a vertex named through an EDGE, so v1 needs no
         *     (unshipped) bare-vertex signature (topological-naming Open Q 10).
         */
        DimensionEndpointRef: {
            /**
             * Endpoint
             * @description Which canonical end of the edge (end_a / end_b)
             * @enum {string}
             */
            endpoint: "end_a" | "end_b";
            /** @description The model edge whose endpoint this names (reused EdgeSignature) */
            signature: components["schemas"]["EdgeSignature"];
        };
        /**
         * DimensionMutationResponse
         * @description Result of a single-dimension mutation: the dimension + the new version.
         */
        DimensionMutationResponse: {
            dimension: components["schemas"]["DimensionResponse"];
            /** Doc Version */
            doc_version: number;
        };
        /**
         * DimensionPlacement
         * @description Authored 2D placement of a dimension on the sheet (design §3.1).
         *
         *     Placement is AUTHORED data (which side of the geometry the dimension line +
         *     witness lines sit, and the text position); the measured VALUE is always taken
         *     from the model, never typed (a v1 drawing dimension is driven-by-geometry,
         *     never driving — design §3.1). ``offset_mm`` is the signed distance of the
         *     dimension line from the geometry in the view plane; ``text_pos`` optionally
         *     overrides the text placement.
         */
        DimensionPlacement: {
            /**
             * Offset Mm
             * @description Signed offset of the dimension line from the geometry (mm)
             * @default 0
             */
            offset_mm: number;
            /** @description Optional text-position override (sheet mm) */
            text_pos?: components["schemas"]["SheetPoint"] | null;
        };
        /**
         * DimensionResponse
         * @description A dimension as stored, with its params envelope reassembled (design §3).
         */
        DimensionResponse: {
            /** Dimension */
            dimension: components["schemas"]["LinearDimensionParams"] | components["schemas"]["DiameterDimensionParams"] | components["schemas"]["RadiusDimensionParams"] | components["schemas"]["AngularDimensionParams"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Order Index
             * @description Stable per-sheet order (dense 0..n-1)
             */
            order_index: number;
            /**
             * Sheet Id
             * Format: uuid
             */
            sheet_id: string;
            /**
             * View Id
             * Format: uuid
             */
            view_id: string;
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
         * DistanceMate
         * @description Two planar faces held a fixed distance apart (fast-follow, design §5).
         *
         *     ``coincident`` with a non-zero offset in the residual (§2.3) — the same
         *     solver, one extra scalar. In the schema now so it joins the solver
         *     additively; not v1-solver scope.
         */
        DistanceMate: {
            /** @description First planar face */
            a: components["schemas"]["MateFaceRef"];
            /** @description Second planar face */
            b: components["schemas"]["MateFaceRef"];
            /**
             * Distance Mm
             * @description Signed gap between the two faces along the normal (mm)
             */
            distance_mm: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "distance";
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
         * DrawingCreate
         * @description Create a drawing owned by the calling user (design §2.1).
         */
        DrawingCreate: {
            /**
             * Name
             * @description Drawing name; unique per owner, whitespace-trimmed, 1-200 characters
             */
            name: string;
        };
        /**
         * DrawingDimensionInput
         * @description A dimension to MEASURE against a view in a drawing-evaluate request (§3/§5).
         *
         *     The evaluate-request analogue of a persisted :class:`DimensionResponse`: it
         *     pairs the authored dimension params with the ``view`` whose projection frame
         *     supplies the §3.2 foreshortening reference — the geometry-request twin of the
         *     ``view_id`` a stored dimension carries (here the standard :data:`ViewProjection`
         *     direction the evaluate request already projects). ``id`` is an OPTIONAL
         *     correlation token echoed back on the matching :class:`MeasuredDimensionResult`
         *     so the client maps a measured value onto the dimension it authored (documents'
         *     dimension id); a transient/library measurement may omit it. The measured VALUE
         *     is taken from the MODEL, never the projection (design §3.1) — ``view`` only sets
         *     the foreshortening flag, it never changes the value.
         */
        DrawingDimensionInput: {
            /**
             * Dimension
             * @description The dimension to measure (discriminated on `type`)
             */
            dimension: components["schemas"]["LinearDimensionParams"] | components["schemas"]["DiameterDimensionParams"] | components["schemas"]["RadiusDimensionParams"] | components["schemas"]["AngularDimensionParams"];
            /**
             * Id
             * @description Optional correlation id echoed on the result (the stored dimension id); null for a transient/library measurement
             */
            id?: string | null;
            /**
             * View
             * @description Which requested view's frame measures it — supplies the §3.2 foreshortening reference only; the value is model-true regardless (§3.1)
             * @enum {string}
             */
            view: "front" | "top" | "right" | "iso" | "flat_pattern" | "section";
        };
        /**
         * DrawingListResponse
         * @description The caller's drawings, oldest first (wrapper leaves room for paging).
         */
        DrawingListResponse: {
            /** Drawings */
            drawings: components["schemas"]["DrawingResponse"][];
        };
        /**
         * DrawingResponse
         * @description A drawing header as stored — identity, ownership, and its OCC token.
         */
        DrawingResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Doc Version
             * @description Monotonic optimistic-concurrency counter (design §2.1)
             */
            doc_version: number;
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
         * DrawingTreeResponse
         * @description A drawing plus its full sheet → view/dimension/annotation tree + OCC token.
         *
         *     The read model a client renders (design §2.2): the drawing header, its sheets
         *     in ``order_index`` order (each with its views/dimensions/annotations in
         *     ``order_index`` order), and the ``doc_version`` the client echoes as its next
         *     ``expected_version``.
         */
        DrawingTreeResponse: {
            /**
             * Doc Version
             * @description Echoed OCC token (== drawing.doc_version)
             */
            doc_version: number;
            drawing: components["schemas"]["DrawingResponse"];
            /** Sheets */
            sheets: components["schemas"]["SheetContent"][];
        };
        /**
         * DrawingUpdate
         * @description Rename a drawing. Bumps ``doc_version`` (any mutation bumps — §2.1).
         */
        DrawingUpdate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard: the doc_version the client last saw; a stale value is rejected 422 (design §2.1)
             */
            expected_version: number;
            /**
             * Name
             * @description New drawing name
             */
            name: string;
        };
        /**
         * DrawingViewResult
         * @description One requested view's projection outcome inside a 200 (design §1.3/§1.5).
         *
         *     On success, ``edges`` carries the view's canonically-ordered visible+hidden 2D
         *     edges and ``error`` is null. On an exact-HLR failure (a fragile body — tangent
         *     edges, self-intersections, §1.5), ``edges`` is empty and ``error`` is a typed
         *     ``view_projection_failed`` (the boundary form of
         *     ``geometry.drawings.ViewProjectionError``) — never a 500, never a silently
         *     empty success. A per-view failure NEVER fails the whole request; the other
         *     requested views still project (mirroring the per-feature/per-mate posture).
         *
         *     For a ``flat_pattern`` view (sheet-metal.md §7) the SAME ``edges`` list carries
         *     the unfold's outline — cut edges as ``edge_role="body"``, fold lines as
         *     ``edge_role="bend"`` — and ``bend_table`` carries the per-bend fold data the
         *     frontend renders as an annotation table. ``bend_table`` is empty for every
         *     standard HLR view (additive — a non-sheet-metal consumer is unaffected). A
         *     ``flat_pattern`` asked of a non-sheet-metal body is a typed per-view
         *     ``flat_pattern_not_sheet_metal`` error, and an unresolvable bend a
         *     ``subshape_unresolved`` (never a wrong flat pattern — §5).
         */
        DrawingViewResult: {
            /**
             * Bend Table
             * @description Per-bend fold rows for a flat_pattern view (sheet-metal.md §6/§7); empty for every standard HLR view and on error
             */
            bend_table?: components["schemas"]["BendTableRow"][];
            /**
             * Edges
             * @description Canonically-ordered visible+hidden 2D edges (empty on error)
             */
            edges?: components["schemas"]["ProjectedViewEdge"][];
            /** @description Typed per-view failure (`view_projection_failed` for HLR, `flat_pattern_not_sheet_metal` / `subshape_unresolved` for a flat pattern, `section_plane_not_principal` / `section_plane_misses_body` / `section_empty` for a section), or null on success (design §1.5 / §7) */
            error?: components["schemas"]["FeatureError"] | null;
            /** @description The scale applied (echoes the request) */
            scale: components["schemas"]["ViewScale"];
            /**
             * Section Faces
             * @description Cross-section boundary loops for a `section` view (drawings-section.md §5) — the region the compose layer hatches; empty for every standard HLR / flat_pattern view and on error (additive, existing views unaffected — the `bend_table` pattern).
             */
            section_faces?: components["schemas"]["SectionFaceLoop"][];
            /**
             * View
             * @description The projection direction of this view
             * @enum {string}
             */
            view: "front" | "top" | "right" | "iso" | "flat_pattern" | "section";
        };
        /**
         * EdgeLengthMeasurement
         * @description Measure the length of a single model edge (design §3.1 linear).
         */
        EdgeLengthMeasurement: {
            /** @description The model edge whose length is measured */
            edge: components["schemas"]["EdgeSignature"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            mode: "edge_length";
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
         * EvaluateAssemblyRequest
         * @description Evaluate an assembly graph to solved placements + shared meshes (§4).
         *
         *     Documents flattens rigid sub-assemblies into this recursive structure
         *     before sending (or geometry recurses — the rigid-group result is identical,
         *     §1.4/§4). Deterministic (RESEARCH §9): the same request yields an identical
         *     result — bitwise-stable mesh ids AND solved transforms — in-process and
         *     across an interpreter restart.
         */
        EvaluateAssemblyRequest: {
            /**
             * Assembly Id
             * Format: uuid
             */
            assembly_id: string;
            /**
             * Instances
             * @description The assembly's instances (result order preserved)
             */
            instances: components["schemas"]["EvaluatedInstance"][];
            /**
             * Linear Deflection
             * @description Presentation tessellation parameter (mm), never persisted
             * @default 0.1
             */
            linear_deflection: number;
            /**
             * Mates
             * @description The mate graph; processed in order_index order (determinism)
             */
            mates?: components["schemas"]["EvaluatedMate"][];
            /**
             * Version
             * @description Echoed back; cache/correlation key
             */
            version: number;
        };
        /**
         * EvaluateAssemblyResult
         * @description Per-instance shared-mesh + solved transform, plus the analytic roll-up (§4).
         *
         *     The output is per-instance ``{content-addressed mesh, solved transform}``,
         *     NOT a baked combined GLB (design §4): the viewport instances the shared part
         *     meshes with the solved transforms (r3f instancing). ``properties`` /
         *     ``bounding_box`` are a closed-form roll-up over instances (Σ volumes,
         *     mass-weighted centroid, transformed-bbox union — no re-meshing, no boolean),
         *     ``None`` when no instance produced a body. A feature/mate failure is a 200
         *     with typed per-entry errors; the envelope stays reserved for
         *     transport/validation failures (design §4).
         */
        EvaluateAssemblyResult: {
            /**
             * Assembly Id
             * Format: uuid
             */
            assembly_id: string;
            /** @description Combined assembly AABB (transformed-bbox union) */
            bounding_box?: components["schemas"]["BoundingBox"] | null;
            /** @description Remaining DOF + offending mate ids; None for a clean well_constrained solve (design §2.4) */
            diagnosis?: components["schemas"]["AssemblySolveDiagnosis"] | null;
            /**
             * Instances
             * @description Same order as the request instances
             */
            instances: components["schemas"]["InstancePlacementResult"][];
            /**
             * Mate Errors
             * @description Per-mate resolution failures (dropped from the solve, §4)
             */
            mate_errors?: components["schemas"]["MateEvaluationError"][];
            /** @description Combined assembly mass properties (roll-up, §4) */
            properties?: components["schemas"]["ShapeProperties"] | null;
            /**
             * Status
             * @description Assembly-level solve outcome
             * @enum {string}
             */
            status: "well_constrained" | "under_constrained" | "over_constrained" | "conflicting" | "not_converged";
            /** Version */
            version: number;
        };
        /**
         * EvaluateDrawingViewsRequest
         * @description Project a part into its requested standard drawing views (design §1.2/§4).
         *
         *     documents sends INTENT — the referenced part's ordered, rollback-applied
         *     feature prefix (reusing the feature-tree §4 contract VERBATIM, so geometry
         *     stays the sole evaluator and no kernel body crosses) plus the standard views to
         *     project, the drawing scale, and (optionally) the drawing's dimensions to
         *     measure. geometry evaluates the part body ONCE (``evaluate_tree``) then runs
         *     exact HLR per requested view AND measures each dimension off the SAME exact body
         *     (design §3.1 — model-true, never the projection). Deterministic (RESEARCH §9):
         *     the same request yields byte-identical projected edges + measured values,
         *     in-process AND across an interpreter restart.
         */
        EvaluateDrawingViewsRequest: {
            /**
             * Dimensions
             * @description Dimensions to measure against the evaluated body, each tagged with its view (design §3/§5). Empty (the default) → no measurement and the response is projected edges only, byte-for-byte the slice-#3 behaviour (fully backward-compatible).
             */
            dimensions?: components["schemas"]["DrawingDimensionInput"][];
            /**
             * Features
             * @description The part's ordered feature prefix (feature-tree §4 contract)
             */
            features: components["schemas"]["EvaluatedFeatureInput"][];
            /**
             * Part Id
             * Format: uuid
             * @description The referenced part's identity (echoed)
             */
            part_id: string;
            /**
             * @description Drawing scale (rational; 1:1 default) applied to every view
             * @default {
             *       "denominator": 1,
             *       "numerator": 1
             *     }
             */
            scale: components["schemas"]["ViewScale"];
            /** @description The cutting plane + flip for a `section` view (drawings-section.md §1). Required iff `views` contains `section`; ignored otherwise. Null (the default) → no section view, byte-for-byte the pre-section state. */
            section_params?: components["schemas"]["SectionViewParams"] | null;
            /**
             * Tree Version
             * @description Echoed back; cache/correlation key
             */
            tree_version: number;
            /**
             * Views
             * @description The standard views to project (subset of front/top/right/iso); processed and returned in request order
             */
            views: ("front" | "top" | "right" | "iso" | "flat_pattern" | "section")[];
        };
        /**
         * EvaluateDrawingViewsResult
         * @description Per-view projected geometry for a part, with an honest whole-part failure
         *     channel (design §1.5/§4).
         *
         *     ``views`` carries one :class:`DrawingViewResult` per requested view, in request
         *     order — each either its canonically-ordered 2D edges or a typed per-view
         *     projection error. ``part_error`` is set ONLY when the part tree produced no
         *     body (a strict-prefix feature failure or a body-less tree): there is nothing to
         *     project, so ``views`` is empty and the failing feature's error rides here (the
         *     single-part analogue of the assembly per-instance ``no_body``). A feature/HLR
         *     failure is a 200 with a typed error, never a 500 — the py-kit error envelope
         *     stays reserved for transport/validation failures of this call itself.
         */
        EvaluateDrawingViewsResult: {
            /**
             * Dimensions
             * @description One measured result per requested dimension, in request order (design §3/§5). Empty when no dimensions were requested or when `part_error` is set (no body to measure against).
             */
            dimensions?: components["schemas"]["MeasuredDimensionResult"][];
            /** @description Set when the part evaluated to no body (nothing to project or measure); `views` and `dimensions` are then empty (design §4) */
            part_error?: components["schemas"]["FeatureError"] | null;
            /**
             * Part Id
             * Format: uuid
             */
            part_id: string;
            /** Tree Version */
            tree_version: number;
            /**
             * Views
             * @description One result per requested view, in request order (empty when `part_error` is set)
             */
            views?: components["schemas"]["DrawingViewResult"][];
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
             * Bodies
             * @description Per-body lump count of the last-good body set (§MB-4), tree-ordered by the feature that created each body. Lets a consumer flag a multi-lump (disjoint-union / multi-solid-import) body the whole-part `properties.topology.shells` aggregate cannot distinguish. Additive: absent/empty for a tree with no body-affecting feature.
             */
            bodies?: components["schemas"]["BodyLumpInfo"][];
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"];
            /**
             * Id
             * Format: uuid
             * @description Feature identity for refs + result keying
             */
            id: string;
        };
        /**
         * EvaluatedInstance
         * @description One assembly instance as the evaluator sees it (design §4).
         *
         *     ``part_key`` is the DEDUP key — ``f"{ref_document_id}@{version-or-tip}"`` —
         *     so two instances of the SAME part evaluate once and share one
         *     content-addressed mesh (the central perf win, design §4 step 1). ``features``
         *     is the part's ordered feature prefix (reuses the feature-tree §4 contract
         *     VERBATIM), so geometry stays the sole evaluator and documents sends intent,
         *     never a kernel body. ``placement`` is the authored seed pose the solver
         *     starts from; ``grounded`` fixes it at that pose (0 DOF — the solver anchor).
         */
        EvaluatedInstance: {
            /**
             * Features
             * @description The part's ordered feature prefix (feature-tree §4 contract)
             */
            features: components["schemas"]["EvaluatedFeatureInput"][];
            /**
             * Grounded
             * @description Fix this instance at its placement (0 DOF) — the solver anchor; an assembly with none grounded floats (under_constrained, §1.2)
             * @default false
             */
            grounded: boolean;
            /**
             * Instance Id
             * Format: uuid
             * @description Instance identity (result keying)
             */
            instance_id: string;
            /**
             * Part Key
             * @description Dedup key f'{ref_document_id}@{version-or-tip}': instances sharing it evaluate once and share one content-addressed mesh (§4)
             */
            part_key: string;
            /**
             * @description Authored seed pose (§2.3)
             * @default {
             *       "orientation": {
             *         "w": 1,
             *         "x": 0,
             *         "y": 0,
             *         "z": 0
             *       },
             *       "position": {
             *         "x": 0,
             *         "y": 0,
             *         "z": 0
             *       }
             *     }
             */
            placement: components["schemas"]["Placement"];
        };
        /**
         * EvaluatedMate
         * @description One mate plus the persisted-row identity the solver + diagnosis need.
         *
         *     ``mate_id`` names the mate in the diagnosis (offending / redundant sets) and
         *     in a per-mate resolution error; ``order_index`` fixes the deterministic
         *     processing order (design §2.2). ``mate`` is the discriminated
         *     :data:`Mate` union member. Mirrors :class:`MateResponse` minus the
         *     assembly id (the request already scopes one assembly).
         */
        EvaluatedMate: {
            /**
             * Mate
             * @description The mate (discriminated on `type`)
             */
            mate: components["schemas"]["CoincidentMate"] | components["schemas"]["ConcentricMate"] | components["schemas"]["DistanceMate"] | components["schemas"]["AngleMate"] | components["schemas"]["LockMate"];
            /**
             * Mate Id
             * Format: uuid
             * @description Persisted mate id (names it in diagnosis)
             */
            mate_id: string;
            /**
             * Order Index
             * @description Deterministic processing order (design §2.2)
             */
            order_index: number;
        };
        /**
         * ExportAssemblyRequest
         * @description Evaluate an assembly graph and export it as one multi-instance CAD file.
         *
         *     Extends :class:`EvaluateAssemblyRequest` (the solver runs the identical
         *     evaluate pipeline — same solved world placements), adding only the export
         *     ``format`` and the STL faceting parameter. STEP exports the exact B-rep as
         *     **AP214 product structure**: every instance that produced a body becomes a
         *     named PRODUCT positioned at its SOLVED world placement, so a downstream tool
         *     (or a re-import) recovers each part traceable to its instance. STL bakes the
         *     solved placements into a single faceted compound (no product names — the
         *     format carries none). Byte-deterministic for identical requests (RESEARCH
         *     §9): the STEP creation timestamp is pinned kernel-side and the assembly's
         *     per-occurrence ids are canonicalised, so the same graph in yields identical
         *     bytes out, in-process and across an interpreter restart.
         */
        ExportAssemblyRequest: {
            /**
             * Angular Deflection
             * @description STL facet angular deflection (rad) between adjacent segments; ignored for STEP (exact B-rep)
             * @default 0.1
             */
            angular_deflection: number;
            /**
             * Assembly Id
             * Format: uuid
             */
            assembly_id: string;
            /**
             * Format
             * @description Export file format: STEP (exact B-rep, AP214 product structure) or STL (faceted mesh, placements baked into one compound)
             * @enum {string}
             */
            format: "step" | "stl";
            /**
             * Instances
             * @description The assembly's instances (result order preserved)
             */
            instances: components["schemas"]["EvaluatedInstance"][];
            /**
             * Linear Deflection
             * @description Presentation tessellation parameter (mm), never persisted
             * @default 0.1
             */
            linear_deflection: number;
            /**
             * Mates
             * @description The mate graph; processed in order_index order (determinism)
             */
            mates?: components["schemas"]["EvaluatedMate"][];
            /**
             * Version
             * @description Echoed back; cache/correlation key
             */
            version: number;
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
             * Merge
             * @description Merge result (ADD only): True fuses the new solid into the active body (default, historical single-body behaviour / starts the first body); False starts a NEW body (multi-body, design multi-body.md §MB-0). Ignored for a CUT. Additive — absent reads True, no param_version bump.
             * @default true
             */
            merge: boolean;
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"];
            /**
             * Name
             * @description User-facing name ("Sketch1")
             */
            name: string;
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
            /** @description Typed over-constraint classification for the "sketch_conflicting" code: which constraints conflict vs. are redundant, so the sketcher reads the diagnosis by field instead of parsing ``message`` (BACKLOG #6). None for non-sketch-conflict errors. */
            sketch_diagnosis?: components["schemas"]["SketchConstraintDiagnosis"] | null;
            /**
             * Upstream Feature Id
             * @description Set when the root cause is an earlier feature's output
             */
            upstream_feature_id?: string | null;
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"];
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
         * FeatureTreeResponse
         * @description The ordered feature tree of a part plus its concurrency token.
         */
        FeatureTreeResponse: {
            /**
             * Can Redo
             * @description True when a later history snapshot exists to restore (the history cursor is below the ring's top)
             */
            can_redo: boolean;
            /**
             * Can Undo
             * @description True when an earlier history snapshot exists to restore (docs/design/undo-redo.md) — lets the toolbar disable undo without a second call
             */
            can_undo: boolean;
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
            feature?: (components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"]) | null;
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
         *     A file with ONE solid becomes a bare solid body; a file with TWO OR MORE
         *     solids becomes ONE multi-lump body — a lump-sorted compound of its disjoint
         *     solids (docs/design/multi-body.md §MB-4), not several bodies. STEP import is
         *     not a boolean: the file's solids are preserved AS AUTHORED (touching or
         *     overlapping solids are kept as separate lumps, never silently fused). Only a
         *     file that yields ZERO solids (open shells / surfaces-only / wireframe) is an
         *     honest ``import_no_solid`` rebuild error whose message carries the shape
         *     stats, and unparseable bytes are ``import_parse_failed`` (§5). Sewing/repair,
         *     IGES, and a positioned insert against an existing body are deferred (§7).
         *
         *     ``kind``/``format`` default so a future blob-ref source (§2a) and IGES join
         *     additively with no ``param_version`` bump.
         */
        ImportParamsV1: {
            /**
             * Data
             * @description STEP AP214 part-21 file text (inline). Bounded/non-empty at parse time (422); parsed to one or more solids by the geometry service (multi-solid → one multi-lump body, MB-4b; 0 solids → import_no_solid).
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
         * InstanceCreate
         * @description Add an instance referencing a part/sub-assembly by id (design §1.2).
         *
         *     ``ref_document_id`` is a cross-document reference, not an FK (design §1.2):
         *     documents enforces its integrity at write time (existence, acyclicity), not
         *     the DB. ``placement`` defaults to identity; ``grounded`` fixes the instance
         *     at its placement (0 DOF) — the solver's anchor (v1 wants at least one
         *     grounded instance per assembly, §1.2). ``order_index`` is a stable
         *     display/BOM order, appended at the tip when omitted.
         */
        InstanceCreate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §1.2)
             */
            expected_version: number;
            /**
             * Grounded
             * @description Fix this instance at its placement (0 DOF) — the solver anchor; v1 wants >= 1 grounded instance per assembly (§1.2)
             * @default false
             */
            grounded: boolean;
            /**
             * Name
             * @description Instance name ("Bracket <1>")
             */
            name: string;
            /**
             * @description Authored seed pose (§2.3)
             * @default {
             *       "orientation": {
             *         "w": 1,
             *         "x": 0,
             *         "y": 0,
             *         "z": 0
             *       },
             *       "position": {
             *         "x": 0,
             *         "y": 0,
             *         "z": 0
             *       }
             *     }
             */
            placement: components["schemas"]["Placement"];
            /**
             * Ref Document Id
             * Format: uuid
             * @description The part / sub-assembly document this instance references
             */
            ref_document_id: string;
            /**
             * Ref Document Kind
             * @description 'part' or 'assembly' (a rigid sub-assembly nests, §1.4)
             * @enum {string}
             */
            ref_document_kind: "part" | "assembly";
        };
        /**
         * InstanceMutationResponse
         * @description Result of a single-instance mutation: the instance + the new version.
         */
        InstanceMutationResponse: {
            /** Doc Version */
            doc_version: number;
            instance: components["schemas"]["InstanceResponse"];
        };
        /**
         * InstancePlacementResult
         * @description One instance's evaluation output: its shared mesh + solved pose (§4).
         *
         *     ``part_mesh_glb_id`` is a content address SHARED across every instance of a
         *     part (the dedup contract, §4/§6.4) — ``None`` only when the instance's part
         *     produced no body (``error`` then explains why). ``placement`` is the SOLVED
         *     world pose (the authored seed for a failed / un-solved instance).
         *     ``properties`` are the part's OWN mass properties (for BOM / inspection).
         *     ``error`` is a typed per-instance failure inside a 200 (design §4, mirroring
         *     feature-tree §4.3) — e.g. the part's failing feature error — never a 4xx.
         */
        InstancePlacementResult: {
            /** @description Typed per-instance failure inside a 200 (the part's failing feature error / no_body), never a transport 4xx (design §4) */
            error?: components["schemas"]["FeatureError"] | null;
            /**
             * Instance Id
             * Format: uuid
             */
            instance_id: string;
            /**
             * Part Mesh Glb Id
             * @description Content-addressed shared part mesh (sha256:<hex>), or null when the part produced no body
             */
            part_mesh_glb_id: string | null;
            /** @description SOLVED world pose (seed if unsolved) */
            placement: components["schemas"]["Placement"];
            /** @description The part's own mass properties (BOM/inspection) */
            properties?: components["schemas"]["ShapeProperties"] | null;
        };
        /**
         * InstanceResponse
         * @description An instance as stored (design §1.2).
         */
        InstanceResponse: {
            /**
             * Assembly Id
             * Format: uuid
             */
            assembly_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Grounded */
            grounded: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Order Index
             * @description Stable display/BOM order (NOT an evaluation order — an assembly is a graph, design §1.1)
             */
            order_index: number;
            placement: components["schemas"]["Placement"];
            /**
             * Ref Document Id
             * Format: uuid
             */
            ref_document_id: string;
            /**
             * Ref Document Kind
             * @enum {string}
             */
            ref_document_kind: "part" | "assembly";
            /**
             * Ref Pinned Version
             * @description Pinned referenced-document version, or null = track tip. NULL in v1 (design §1.3 — the schema is pin-ready).
             */
            ref_pinned_version: number | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * InstanceUpdate
         * @description Re-place / rename / (un)ground an instance (design §1.2).
         *
         *     Every field is optional; at least one must be provided. Any mutation bumps
         *     ``doc_version``. Re-pointing the referenced document is NOT an update — that
         *     is a delete + recreate (it changes the graph edge the acyclicity walk sees).
         */
        InstanceUpdate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §1.2)
             */
            expected_version: number;
            /** Grounded */
            grounded?: boolean | null;
            /** Name */
            name?: string | null;
            /**
             * Order Index
             * @description New stable display/BOM position (reorder). Renumbered dense by the service.
             */
            order_index?: number | null;
            placement?: components["schemas"]["Placement"] | null;
        };
        /**
         * LinearDimensionParams
         * @description A linear dimension — an edge length or a point-to-point distance (§3.1).
         */
        LinearDimensionParams: {
            /**
             * Measurement
             * @description What is measured (an edge's length or two endpoints)
             */
            measurement: components["schemas"]["EdgeLengthMeasurement"] | components["schemas"]["PointToPointMeasurement"];
            /** @description Authored 2D placement */
            placement?: components["schemas"]["DimensionPlacement"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "linear";
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
         * LockMate
         * @description Rigidly fix two instances' relative pose — 0 DOF (design §2.1/§2.3).
         *
         *     Trivial for the solver (it fixes a relative pose, 0 iterative work) and
         *     covers weldments/press-fits. References two instances directly by id (no
         *     picked geometry) — the relative-pose residual drives ``b``'s pose to a fixed
         *     transform of ``a``'s (§2.3).
         */
        LockMate: {
            /**
             * A Instance Id
             * Format: uuid
             * @description First (anchor) instance
             */
            a_instance_id: string;
            /**
             * B Instance Id
             * Format: uuid
             * @description Second (locked) instance
             */
            b_instance_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "lock";
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
             * Merge
             * @description Merge result (ADD only): True fuses the new solid into the active body (default, historical single-body behaviour / starts the first body); False starts a NEW body (multi-body, design multi-body.md §MB-0). Ignored for a CUT. Additive — absent reads True, no param_version bump.
             * @default true
             */
            merge: boolean;
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
         * LoginRequest
         * @description Exchange email + password for an access token.
         */
        LoginRequest: {
            /**
             * Email
             * Format: email
             * @description Account email
             */
            email: string;
            /**
             * Password
             * Format: password
             * @description Account password (at most 256 characters — same cap as register, enforced in the route)
             */
            password: string;
        };
        /**
         * MateAxisRef
         * @description An axis derived from a CIRCULAR edge of an instance's part body (§2.1).
         *
         *     v1 derives an axis from a circular edge (``curve == "circle"``) — reusing
         *     :class:`~py_kit.schemas.features.EdgeSignature`, whose seam-point centre and
         *     plane give the axis (design §2.1). This deliberately avoids needing a
         *     cylindrical-face signature (a clean additive future member): a hole rim and
         *     a shaft rim are both circular edges, enough for the canonical bolt joint.
         */
        MateAxisRef: {
            /**
             * Instance Id
             * Format: uuid
             * @description The instance whose part body carries this axis edge
             */
            instance_id: string;
            /**
             * Kind
             * @default axis
             * @constant
             */
            kind: "axis";
            /** @description Stage-1 edge signature (curve == 'circle'; reused from features) whose centre + plane define the axis */
            signature: components["schemas"]["EdgeSignature"];
        };
        /**
         * MateCreate
         * @description Add a mate to an assembly (design §1.2/§2.1).
         *
         *     ``mate`` is the discriminated :data:`Mate` union; the instances it names
         *     (via :func:`mate_instance_ids`) must belong to this assembly (documents
         *     checks membership at write time). ``order_index`` is a stable order for
         *     determinism (§2.2), appended at the tip when omitted.
         */
        MateCreate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §1.2)
             */
            expected_version: number;
            /**
             * Mate
             * @description The mate (discriminated on `type`)
             */
            mate: components["schemas"]["CoincidentMate"] | components["schemas"]["ConcentricMate"] | components["schemas"]["DistanceMate"] | components["schemas"]["AngleMate"] | components["schemas"]["LockMate"];
        };
        /**
         * MateEvaluationError
         * @description A per-mate resolution failure inside a 200 (design §4).
         *
         *     A mate whose geometry could not be resolved against the evaluated bodies —
         *     ``subshape_unresolved`` / ``subshape_ambiguous`` (from the reused stage-1
         *     resolver, #3's chained error) or a reference to an unavailable instance — is
         *     reported here and DROPPED from the solve (the assembly still renders every
         *     instance it can place, degrading to under-constrained rather than failing
         *     the whole evaluation, design §4). A CONFLICTING (unsatisfiable) mate is not
         *     here — it is named in :attr:`AssemblySolveDiagnosis.conflicting_mates`.
         */
        MateEvaluationError: {
            /** @description Typed per-mate failure (code + message) */
            error: components["schemas"]["FeatureError"];
            /**
             * Mate Id
             * Format: uuid
             */
            mate_id: string;
        };
        /**
         * MateFaceRef
         * @description A planar face of an instance's part body (design §1.5/§2.1).
         *
         *     ``signature`` is the SAME :class:`~py_kit.schemas.features.PlanarFaceSignature`
         *     the ``on_face`` datum resolves (topological-naming.md §9) — reused verbatim,
         *     not a parallel taxonomy. ``instance_id`` scopes the face to one instance's
         *     resolved part body (the geometry service resolves the signature against that
         *     body in the part's local frame, §4).
         */
        MateFaceRef: {
            /**
             * Instance Id
             * Format: uuid
             * @description The instance whose part body carries this face
             */
            instance_id: string;
            /**
             * Kind
             * @default face
             * @constant
             */
            kind: "face";
            /** @description Stage-1 planar-face signature (reused from features) */
            signature: components["schemas"]["PlanarFaceSignature"];
        };
        /**
         * MateMutationResponse
         * @description Result of a single-mate mutation: the mate + the new version.
         */
        MateMutationResponse: {
            /** Doc Version */
            doc_version: number;
            mate: components["schemas"]["MateResponse"];
        };
        /**
         * MateResponse
         * @description A mate as stored, with its params envelope reassembled (design §1.2).
         */
        MateResponse: {
            /**
             * Assembly Id
             * Format: uuid
             */
            assembly_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Mate */
            mate: components["schemas"]["CoincidentMate"] | components["schemas"]["ConcentricMate"] | components["schemas"]["DistanceMate"] | components["schemas"]["AngleMate"] | components["schemas"]["LockMate"];
            /**
             * Order Index
             * @description Stable order (determinism, §2.2); relative position only
             */
            order_index: number;
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
         * MeasuredDimension
         * @description A dimension's value measured from the MODEL, or a typed resolution error.
         *
         *     On success ``value`` + ``unit`` carry the model-true measurement and ``error``
         *     is null; ``foreshortened`` flags a feature not parallel to the view plane
         *     (design §3.2 — the value is still model-true). On failure ``value``/``unit``
         *     are null and ``error`` is a typed ``subshape_unresolved`` / ``subshape_ambiguous``
         *     / ``dimension_wrong_type`` (never a 500 — design §3.3). Mirrors the per-view
         *     :class:`DrawingViewResult` success/error envelope for a single dimension.
         */
        MeasuredDimension: {
            /** @description Typed resolution failure (`subshape_unresolved` / `subshape_ambiguous` / `dimension_wrong_type`), or null on success */
            error?: components["schemas"]["FeatureError"] | null;
            /**
             * Foreshortened
             * @description True when the measured feature is not parallel to the view plane (design §3.2). The value is STILL model-true; the flag warns the UI to dimension it in a true-size view.
             * @default false
             */
            foreshortened: boolean;
            /**
             * Unit
             * @description 'mm' or 'deg'; null when `error` is set
             */
            unit?: ("mm" | "deg") | null;
            /**
             * Value
             * @description Model-true measured value (mm for linear/diameter/radius, degrees for angular); null when `error` is set
             */
            value?: number | null;
        };
        /**
         * MeasuredDimensionResult
         * @description One requested dimension's measured outcome inside a 200 (design §3/§5).
         *
         *     Pairs the echoed correlation ``id`` + the ``view`` it was measured in with the
         *     model-true :class:`MeasuredDimension` (value + unit + ``foreshortened``, OR a
         *     typed ``subshape_unresolved`` / ``subshape_ambiguous`` / ``dimension_wrong_type``
         *     error on its ``error`` channel). A per-dimension measurement failure is THAT
         *     dimension's typed error — never a 500, never a failure of the whole request or
         *     of any OTHER dimension/view — the same never-500 posture as the per-view
         *     :class:`DrawingViewResult` and the per-feature/per-mate strict-prefix rule.
         */
        MeasuredDimensionResult: {
            /**
             * Id
             * @description Echoed correlation id (matches the request input), or null
             */
            id?: string | null;
            /** @description Model-true value + unit + foreshortened flag, or a typed error */
            measured: components["schemas"]["MeasuredDimension"];
            /**
             * View
             * @description The view direction this dimension was measured in
             * @enum {string}
             */
            view: "front" | "top" | "right" | "iso" | "flat_pattern" | "section";
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
         * NoteAnnotationParams
         * @description A free text note placed on the sheet (design §2.2 v1 minimal).
         *
         *     v1 ships the ``note`` kind only (text + sheet position); a ``leader`` (a note
         *     with a pointer) joins additively later — hence :data:`Annotation` is a plain
         *     alias today (pydantic forbids a single-member discriminated union), promoted
         *     to a ``type``-discriminated union when the second kind lands.
         */
        NoteAnnotationParams: {
            /** @description Anchor position on the sheet (mm) */
            position: components["schemas"]["SheetPoint"];
            /**
             * Text
             * @description The note body
             */
            text: string;
            /**
             * Type
             * @default note
             * @constant
             */
            type: "note";
        };
        /**
         * OverlayEdge
         * @description One pickable B-rep edge of the evaluated body (transient index).
         *
         *     The list position of this edge in :attr:`OverlayResult.edges` is its
         *     transient 0-based index — the SAME ordinal ``body.edges()`` yields, so
         *     passing it as :class:`~py_kit.schemas.measure.EdgeTarget` ``index`` measures
         *     THIS edge. The transient index is for MEASUREMENT; the STABLE, rebuild-
         *     surviving reference is :attr:`signature` (topological naming) — echo it into
         *     an ``EdgeSubshapeRef`` to fillet/chamfer exactly this edge.
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
            /** @description Stage-1 edge signature (curve/endpoints/midpoint/length) — the SAME fingerprint the fillet/chamfer picked-edge resolver matches against (one enumeration: pick side == resolve side, an order-equality gate proves it). Echo it into an EdgeSubshapeRef to round THIS edge. Unlike the transient index, it survives rebuilds (best-effort, stage 1). */
            signature: components["schemas"]["EdgeSignature"];
            /** @description Edge start vertex, world mm (curve param 0) */
            start: components["schemas"]["Vec3"];
        };
        /**
         * OverlayFace
         * @description One face of the evaluated body — pickable for a sketch datum-on-a-face.
         *
         *     A PLANAR face carries a stage-1
         *     :class:`~py_kit.schemas.features.PlanarFaceSignature` — the SAME fingerprint
         *     a datum-on-face ``SubshapeRef`` stores and the geometry resolver matches
         *     against (one enumeration: the pick side and the resolve side share
         *     ``geometry.kernel.faces.planar_faces``; an order-equality gate proves it). To
         *     place a sketch on a face, echo its ``signature`` into a ``SubshapeRef`` — the
         *     same round-trip a vertex makes into a ``PointTarget``. A NON-planar face has
         *     ``signature = null`` and is not sketchable in v1 (topological naming's face
         *     signatures are planar-only until edge/curved-surface support lands).
         *
         *     ``index`` is TRANSIENT — the ``body.faces()`` position for THIS tree only,
         *     not stable across edits (the persisted reference is the signature, never the
         *     index — topological naming, feature-tree design §2.4).
         */
        OverlayFace: {
            /**
             * Index
             * @description Transient 0-based body.faces() index (this tree only; NOT stable across edits — the stored reference is the signature)
             */
            index: number;
            /**
             * Planar
             * @description True if the face is planar (sketchable — carries a signature)
             */
            planar: boolean;
            /** @description Stage-1 face signature (normal/centroid/area) for a planar face; null for a non-planar face. Echo it into a SubshapeRef to place a datum-on-a-face sketch here. */
            signature?: components["schemas"]["PlanarFaceSignature"] | null;
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
             * Faces
             * @description Faces in body.faces() order; each planar face carries the SAME stage-1 signature the datum-on-face resolver matches against — echo a planar face's signature into a SubshapeRef to sketch on it
             */
            faces: components["schemas"]["OverlayFace"][];
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
         * PartCreate
         * @description Create a part owned by the calling user.
         */
        PartCreate: {
            /**
             * Length Unit
             * @description Document display unit (docs/design/units.md §1); DISPLAY metadata only — storage stays canonical mm. Defaults to 'mm'.
             * @default mm
             * @enum {string}
             */
            length_unit: "mm" | "cm" | "m" | "in" | "ft";
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
         * @description A part as stored — identity, ownership, unit, and timestamps.
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
            /**
             * Length Unit
             * @description Document display unit (docs/design/units.md §1); DISPLAY metadata only — storage stays canonical mm.
             * @enum {string}
             */
            length_unit: "mm" | "cm" | "m" | "in" | "ft";
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
         * PartUpdate
         * @description Rename and/or re-unit a part. Bumps ``tree_version`` (any document edit
         *     bumps — the feature-tree.md §1.2 pattern applied to the part header).
         *
         *     Both mutable fields are optional; at least one must be provided. Changing
         *     the display unit is a document edit (docs/design/units.md §U1) — it does
         *     NOT convert any stored ``*_mm`` value, only relabels how they render.
         */
        PartUpdate: {
            /**
             * Expected Tree Version
             * @description Optimistic-concurrency guard: the tree_version the client last saw; a stale value is rejected 422 (feature-tree.md §1.2)
             */
            expected_tree_version: number;
            /**
             * Length Unit
             * @description New document display unit (metadata only)
             */
            length_unit?: ("mm" | "cm" | "m" | "in" | "ft") | null;
            /**
             * Name
             * @description New part name
             */
            name?: string | null;
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
         * Placement
         * @description A rigid pose — translation + orientation — of an instance (design §2.3).
         *
         *     ``position`` is the world-mm translation; ``orientation`` defaults to the
         *     identity quaternion so an authored instance with no rotation carries a
         *     minimal placement. On the wire everywhere (authored seed AND solved result,
         *     §4) so the solver never converts representation at the boundary.
         */
        Placement: {
            /**
             * @description Unit quaternion orientation; identity (0,0,0,1) by default
             * @default {
             *       "w": 1,
             *       "x": 0,
             *       "y": 0,
             *       "z": 0
             *     }
             */
            orientation: components["schemas"]["Quat"];
            /** @description Translation, world mm */
            position: components["schemas"]["Vec3"];
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
         * PointToPointMeasurement
         * @description Measure the distance between two model-edge endpoints (design §3.1/§3.3).
         */
        PointToPointMeasurement: {
            /** @description First endpoint */
            a: components["schemas"]["DimensionEndpointRef"];
            /** @description Second endpoint */
            b: components["schemas"]["DimensionEndpointRef"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            mode: "point_to_point";
        };
        /**
         * ProjectedPoint
         * @description A 2D point of a projected view edge, in view-plane mm at the view's scale.
         *
         *     View-local millimetres (model-mm x the view scale, design §9 q4) — NOT yet
         *     placed at a sheet position (sheet layout is a later slice). A projected edge's
         *     endpoints, midpoint, centre, and polyline sample points are all this type.
         */
        ProjectedPoint: {
            /**
             * X Mm
             * @description X in the view plane (mm, model-mm x scale)
             */
            x_mm: number;
            /**
             * Y Mm
             * @description Y in the view plane (mm, model-mm x scale)
             */
            y_mm: number;
        };
        /**
         * ProjectedViewEdge
         * @description One classified 2D edge of a projected view (design §1.3) — a neutral
         *     primitive, never a kernel handle (the boundary twin of
         *     ``geometry.drawings.project.ProjectedEdge``).
         *
         *     ``visible`` distinguishes solid-drawn (``True``) from hidden/dashed (``False``,
         *     occluded). ``start``/``end`` are the canonical (orientation-independent)
         *     endpoints and ``midpoint`` a point ON the edge. ``center``/``radius`` are
         *     populated for ``circle``/``arc`` (a real projected circle a Ø/radius dimension
         *     reads off, §1.1); ``points`` holds the sampled vertices of a ``polyline``
         *     (empty for the analytic kinds). Edges arrive in the canonical total order
         *     (§1.4) — a consumer serialising them verbatim gets byte-deterministic output.
         */
        ProjectedViewEdge: {
            /** @description Circle/arc centre (null for line/polyline) */
            center?: components["schemas"]["ProjectedPoint"] | null;
            /**
             * Dimensionable
             * @description True iff `source_edge` is a single unambiguous model edge, so a dimension may attach to this projected edge (design §3.3). False for silhouette/outline edges and ambiguous coincident projections — HONEST un-dimensionability rather than a wrong signature (§1.5).
             * @default false
             */
            dimensionable: boolean;
            /**
             * Edge Role
             * @description Outline role (sheet-metal.md §6): 'body' = a real cut edge (every HLR view edge, the default — additive so existing consumers are unaffected); 'bend' = a flat-pattern fold line, rendered as its own dashed-blue stroke rather than the visible/hidden BODY-edge styling. Orthogonal to `visible` (a bend line is neither a solid nor an occluded body edge).
             * @default body
             * @enum {string}
             */
            edge_role: "body" | "bend";
            /** @description Canonical second endpoint */
            end: components["schemas"]["ProjectedPoint"];
            /** @description A point ON the edge (orientation-independent) */
            midpoint: components["schemas"]["ProjectedPoint"];
            /**
             * Points
             * @description Sampled polyline vertices (empty for line/circle/arc)
             */
            points?: components["schemas"]["ProjectedPoint"][];
            /**
             * Primitive
             * @description Neutral 2D primitive kind
             * @enum {string}
             */
            primitive: "line" | "circle" | "arc" | "polyline";
            /**
             * Radius
             * @description Circle/arc radius, mm x scale (null otherwise)
             */
            radius?: number | null;
            /** @description The MODEL edge this projected edge provenance-maps to (design §3.3) — the shipped EdgeSignature a dimension names (the SAME fingerprint a `concentric` mate and a picked-edge fillet use). Null when the edge has no single clean model source: a silhouette/outline edge (§1.5), a genuinely free-form projection, or an ambiguous coincident projection. A pick on a dimensionable edge yields this ref directly (design §3.3 / §5 form 1). */
            source_edge?: components["schemas"]["EdgeSignature"] | null;
            /** @description Canonical first endpoint */
            start: components["schemas"]["ProjectedPoint"];
            /**
             * Start Is End A
             * @description For a STRAIGHT dimensionable edge (design §3.3): True iff this edge's canonical `start` projected point corresponds to `source_edge`'s canonical `end_a` (False → `end_b`). The model→projected endpoint correspondence the lexicographic canonicalisation of `start`/`end` would otherwise drop — it lets a point-to-point linear dimension name the correct model endpoint (`DimensionEndpointRef.endpoint`) from a picked projected end WITHOUT re-deriving the view frame + projection. Null for a non-straight edge (circle/arc/polyline) or any edge with no single clean model source (silhouette/free-form/ambiguous, §1.5) — same optional-provenance style as `source_edge`.
             */
            start_is_end_a?: boolean | null;
            /**
             * Visible
             * @description True = solid (visible); False = dashed (hidden/occluded)
             */
            visible: boolean;
        };
        /**
         * Quat
         * @description Unit quaternion — the solver's internal orientation representation (§2.3).
         *
         *     Gimbal-free, minimal, and renormalises cleanly under iteration (design
         *     §2.3), so no lossy Euler/matrix conversion crosses the boundary. All four
         *     components are required — a partial quaternion is a request-validation 422,
         *     never a silently-defaulted rotation. Identity is ``(0, 0, 0, 1)``; the
         *     solver renormalises to the unit sphere, so an authored value need not be
         *     exactly unit-length.
         */
        Quat: {
            /**
             * W
             * @description Scalar part (full precision); 1 for identity
             */
            w: number;
            /**
             * X
             * @description Vector part i-component (full precision)
             */
            x: number;
            /**
             * Y
             * @description Vector part j-component (full precision)
             */
            y: number;
            /**
             * Z
             * @description Vector part k-component (full precision)
             */
            z: number;
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
         * RadiusDimensionParams
         * @description A radius dimension on a circular / arc model edge (design §3.1).
         */
        RadiusDimensionParams: {
            /** @description Circular / arc model edge */
            edge: components["schemas"]["EdgeSignature"];
            /** @description Authored 2D placement */
            placement?: components["schemas"]["DimensionPlacement"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "radius";
        };
        /**
         * RegisterRequest
         * @description Create an account. Policy: 8-256 chars, enforced in the route.
         */
        RegisterRequest: {
            /**
             * Email
             * Format: email
             * @description Account email; unique, case-insensitive
             */
            email: string;
            /**
             * Password
             * Format: password
             * @description Plaintext password, 8-256 characters (never stored; argon2id-hashed)
             */
            password: string;
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
             * Merge
             * @description Merge result (ADD only): True fuses the new solid into the active body (default, historical single-body behaviour / starts the first body); False starts a NEW body (multi-body, design multi-body.md §MB-0). Ignored for a CUT. Additive — absent reads True, no param_version bump.
             * @default true
             */
            merge: boolean;
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
         * SectionFaceLoop
         * @description One section cross-section face as canonical projected boundary loops (§5/§6).
         *
         *     A section view's cut face, projected into the view plane (view mm at the view's
         *     scale — the SAME frame as the view's ``edges``, so the hatch lands on the drawn
         *     outline). ``outer`` is the face's outer boundary; ``holes`` are its interior (bore)
         *     boundaries. Each loop is a closed polyline pinned to a deterministic start vertex
         *     and winding (outer CCW, holes CW in the view frame, drawings-section.md §6) so the
         *     payload is byte-stable regardless of OCCT's edge order. The compose layer generates
         *     the crosshatch from these loops (even-odd scanline clip: holes carve gaps); the
         *     projection layer stays purely geometry. Empty for every non-section view — additive,
         *     so existing views are unaffected (the ``bend_table`` pattern).
         */
        SectionFaceLoop: {
            /**
             * Holes
             * @description Interior (bore) boundaries, each a closed projected polyline
             */
            holes?: components["schemas"]["ProjectedPoint"][][];
            /**
             * Outer
             * @description The face's outer boundary as a closed projected polyline
             */
            outer: components["schemas"]["ProjectedPoint"][];
        };
        /**
         * SectionViewParams
         * @description The cutting plane + half selection of a section view (drawings-section.md §1).
         *
         *     v1 specifies the section's cutting plane by DATUM REFERENCE, not a drawn cutting
         *     line (§1): ``plane`` is the shipped :data:`~py_kit.schemas.features.GeomRef`
         *     (``DatumPlaneRef`` for one of the XY/XZ/YZ origin planes, or a ``FeatureRef`` to
         *     an axis-aligned offset / midplane datum FEATURE in the referenced part) — the
         *     EXACT union a sketch's plane reference uses, so no parallel plane taxonomy is
         *     introduced (DRY). The geometry service resolves it, checks the v1 axis-aligned
         *     precondition (a non-principal normal is a typed ``section_plane_not_principal``,
         *     §7), cuts, and hatches. ``flip`` chooses which half is removed (§4): ``false``
         *     (default) removes the eye-side material (the standard "cut away what is between
         *     you and the plane"), ``true`` the far side.
         */
        SectionViewParams: {
            /**
             * Flip
             * @description Which half is removed (§4): false (default) removes the eye-side material; true the far side.
             * @default false
             */
            flip: boolean;
            /**
             * Plane
             * @description The cutting plane, as a datum reference (reused GeomRef): a DatumPlaneRef (XY/XZ/YZ) or a FeatureRef to an axis-aligned offset/midplane datum. A non-principal-axis normal is out of v1 (typed error, §7).
             */
            plane: components["schemas"]["DatumPlaneRef"] | components["schemas"]["FeatureRef"];
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
         * SheetContent
         * @description One sheet plus its views, dimensions, and annotations (design §2.2).
         */
        SheetContent: {
            /** Annotations */
            annotations: components["schemas"]["AnnotationResponse"][];
            /** Dimensions */
            dimensions: components["schemas"]["DimensionResponse"][];
            sheet: components["schemas"]["SheetResponse"];
            /** Views */
            views: components["schemas"]["ViewResponse"][];
        };
        /**
         * SheetCreate
         * @description Add a sheet to a drawing (append at the tip; design §2.2).
         */
        SheetCreate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §2.1)
             */
            expected_version: number;
            /**
             * Name
             * @description Sheet name ("Sheet 1")
             */
            name: string;
            /**
             * Orientation
             * @description Sheet orientation
             * @default landscape
             * @enum {string}
             */
            orientation: "landscape" | "portrait";
            /**
             * Projection
             * @description Projection convention (third-angle default, design §1.2)
             * @default third_angle
             * @enum {string}
             */
            projection: "third_angle" | "first_angle";
            /**
             * Size
             * @description Sheet size (ISO / ANSI)
             * @default A4
             * @enum {string}
             */
            size: "A4" | "A3" | "A2" | "A1" | "A0" | "ANSI_A" | "ANSI_B" | "ANSI_C" | "ANSI_D";
            /** @description Free-text title block (design §9 q6) */
            title_block?: components["schemas"]["TitleBlock"] | null;
        };
        /**
         * SheetMetalBaseFlangeFeature
         * @description ``{"type": "sheet_metal_base_flange", "version": 1, "params": {...}}`` envelope.
         *
         *     A body-CREATING base feature (docs/design/sheet-metal.md §4.1): it thickens a
         *     profile to gauge, producing the sheet-metal part's first body, and anchors the
         *     part's sheet-metal defaults (``k_factor``/``bend_radius_mm``). ``params`` is
         *     :class:`SheetMetalBaseFlangeParamsV1`.
         */
        SheetMetalBaseFlangeFeature: {
            params: components["schemas"]["SheetMetalBaseFlangeParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "sheet_metal_base_flange";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * SheetMetalBaseFlangeParamsV1
         * @description The first body of a sheet-metal part — a profile thickened to gauge (§4.1).
         *
         *     A base flange is a profile sketch extruded by a FIXED gauge ``thickness_mm``
         *     — mechanically an additive extrude, so it shares :class:`ExtrudeParamsV1`'s
         *     ``profile`` FeatureRef (an EARLIER sketch, design §2.2), ``direction``
         *     (which side of the sketch plane the gauge grows), and ``merge`` (the
         *     multi-body ADD flag — a base flange is a body-CREATING base feature, so it
         *     starts the first body, or a second with ``merge=False``). Kernel-side it
         *     calls the SAME ``build_profile_face`` + ``extrude_face`` path extrude uses —
         *     no new geometry code (§4.1).
         *
         *     Unlike a plain extrude it carries the part's SHEET-METAL DEFAULTS
         *     (``k_factor``, ``bend_radius_mm``) — the parameters a later edge-flange /
         *     unfold reads to compute a bend allowance (``BA = angle * (radius + K *
         *     thickness)``, §1). ``k_factor`` defaults to the v1 pinned
         *     :data:`SHEET_METAL_DEFAULT_K_FACTOR` (0.44); ``bend_radius_mm`` is REQUIRED
         *     (no universal default — it is tooling/material dependent) and names the
         *     part-default inner bend radius edge flanges inherit. Neither default affects
         *     the base flange's own geometry (a flat plate) — they ride ON the body for the
         *     downstream slices, exactly as the design's "base flange is the natural anchor
         *     for the sheet-metal parameters" decision intends.
         *
         *     There is NO ``operation`` field: a base flange always CREATES material (it is
         *     the sheet's first body), never a cut. v1 scopes to a single per-part gauge +
         *     K + default radius (§7); a gauge/material rule table is deferred (§10).
         */
        SheetMetalBaseFlangeParamsV1: {
            /**
             * Bend Radius Mm
             * @description Part-default INNER bend radius (mm) a later edge flange inherits (§4.2). Required — no universal default (tooling/material dependent). Does not affect the base flange's own flat-plate geometry.
             */
            bend_radius_mm: number;
            /**
             * Direction
             * @description Which side of the sketch plane the gauge grows: 'normal' along the plane normal, 'reverse' opposite (the extrude `direction` idiom). Additive-optional; absent reads 'normal'.
             * @default normal
             * @enum {string}
             */
            direction: "normal" | "reverse";
            /**
             * K Factor
             * @description Neutral-axis fraction K ∈ [0, 1] from the INNER bend face (§1); the part-default a later edge flange inherits for its bend allowance. Defaults to the v1 baseline 0.44 (air-bent mild steel — a documented default, not a universal constant).
             * @default 0.44
             */
            k_factor: number;
            /**
             * Merge
             * @description Merge result (ADD only): True fuses the new solid into the active body (default, historical single-body behaviour / starts the first body); False starts a NEW body (multi-body, design multi-body.md §MB-0). Ignored for a CUT. Additive — absent reads True, no param_version bump.
             * @default true
             */
            merge: boolean;
            /** @description Must resolve to an EARLIER sketch feature whose entities form the single closed profile wire (design §2.2), thickened to the gauge */
            profile: components["schemas"]["FeatureRef"];
            /**
             * Thickness Mm
             * @description Gauge — the uniform sheet thickness (mm); the fixed distance the profile is thickened by. The part's one material thickness (§1).
             */
            thickness_mm: number;
        };
        /**
         * SheetMetalCornerReliefFeature
         * @description ``{"type": "sheet_metal_corner_relief", "version": 1, "params": {...}}``.
         *
         *     A body-affecting feature (sheet-metal.md §4.4) that cuts a rectangular notch at
         *     the shared corner of two adjacent edge flanges and — via the analytic relieved
         *     unfold — makes that corner develop into a single non-overlapping flat blank. It
         *     names the two bends by :class:`FeatureRef` (the edge-flange features that created
         *     them); the evaluator resolves each to its recorded
         *     :class:`CylindricalFaceSignature` (§5) to drive both relief halves. ``params`` is
         *     :class:`SheetMetalCornerReliefParamsV1`.
         */
        SheetMetalCornerReliefFeature: {
            params: components["schemas"]["SheetMetalCornerReliefParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "sheet_metal_corner_relief";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * SheetMetalCornerReliefParamsV1
         * @description An explicit RECTANGULAR corner relief at two adjacent flanges' corner (§4.4).
         *
         *     Names the two bends whose shared corner it relieves — ``bend_a`` / ``bend_b``,
         *     each a :class:`FeatureRef` at the earlier ``sheet_metal_edge_flange`` feature
         *     that created that bend. The evaluator resolves each ref to that feature's
         *     recorded :class:`CylindricalFaceSignature` (§5) and drives BOTH halves of the
         *     relief from the two signatures: the 3D notch boolean
         *     (:func:`geometry.sheet_metal.apply_corner_relief`) and the relieved flat-pattern
         *     unfold (:func:`unfold_sheet_metal` with ``reliefs=...``) — consistent by
         *     construction (the fold-back guarantee, §4.4.4).
         *
         *     SIZING (§4.4.3): the notch is ``size = relief_ratio * thickness`` by default
         *     (``relief_ratio = 1.0`` — one gauge thickness, the tear-safe SolidWorks Relief
         *     Ratio default), with the part's gauge taken from the base flange. An absolute
         *     ``size_mm`` OVERRIDES the ratio when set (the authoring/UI convenience the golden
         *     pins to an exact number). The manufacturing floor ``size >= bend_radius`` (the
         *     notch should clear the bend arc) is a recommendation, not a hard bound — an
         *     undersized relief is a manufacturing warning, still a fold-back-consistent body.
         *
         *     v1 ships ``relief_type = "rectangular"`` only (the sole purely-rectilinear
         *     developable notch; obround / round / tear are §4.4.1 follow-ons). It MODIFIES the
         *     implicit single sheet body chain (design §7.6) — it carries no ``merge`` — so its
         *     only whole-feature dependencies are the two edge-flange refs + tree order.
         */
        SheetMetalCornerReliefParamsV1: {
            /** @description The FIRST bend of the relieved corner — a FeatureRef at the earlier sheet_metal_edge_flange feature that created it. Resolved to that feature's recorded CylindricalFaceSignature (§5). */
            bend_a: components["schemas"]["FeatureRef"];
            /** @description The SECOND bend of the relieved corner — a FeatureRef at the other sheet_metal_edge_flange feature. Its shared corner with bend_a is the corner the notch relieves; the two bends must be PERPENDICULAR (a real tray corner) or the relief is a typed error (§4.4). */
            bend_b: components["schemas"]["FeatureRef"];
            /**
             * Relief Ratio
             * @description Notch size as a multiple of gauge thickness (size = relief_ratio * thickness) — the SolidWorks Relief Ratio family. Default 1.0 (one thickness, tear-safe). IGNORED when size_mm is set.
             * @default 1
             */
            relief_ratio: number;
            /**
             * Relief Type
             * @description Relief geometry. v1 ships 'rectangular' only (the sole purely-rectilinear developable notch — §4.4.1). Obround / round / tear each need a curved / degenerate cut and are deferred (additive Literal members, no param_version bump). Absent reads 'rectangular'.
             * @default rectangular
             * @constant
             */
            relief_type: "rectangular";
            /**
             * Size Mm
             * @description Absolute notch size (mm). When set, OVERRIDES relief_ratio (the authoring/UI convenience that resolves the ratio to an exact value the golden pins). Omitted (None) uses relief_ratio * the part's gauge thickness.
             */
            size_mm?: number | null;
        };
        /**
         * SheetMetalEdgeFlangeFeature
         * @description ``{"type": "sheet_metal_edge_flange", "version": 1, "params": {...}}`` envelope.
         *
         *     A body-MODIFYING feature (docs/design/sheet-metal.md §4.2): it folds a flange
         *     off a straight edge of the sheet body and fuses it across a cylindrical bend
         *     region, tagging that bend face with a :class:`CylindricalFaceSignature` (§5)
         *     for the unfold's provenance. ``params`` is :class:`SheetMetalEdgeFlangeParamsV1`.
         */
        SheetMetalEdgeFlangeFeature: {
            params: components["schemas"]["SheetMetalEdgeFlangeParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "sheet_metal_edge_flange";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * SheetMetalEdgeFlangeParamsV1
         * @description A flange folded off a straight edge of the base flange (§4.2).
         *
         *     ``edge`` is an :class:`EdgeSubshapeRef` naming the base-flange edge to fold off
         *     — the SAME stage-1 :class:`EdgeSignature` machinery a fillet/chamfer pick uses
         *     (topological-naming §10), resolved against the current sheet body; its
         *     ``feature_id`` materialises the dependency on the base-flange feature exactly
         *     like a picked fillet edge. The flange extends outward from that edge in the
         *     plane of its adjacent flat (plate) face and folds by ``bend_angle_deg`` about a
         *     bend of ``bend_radius_mm`` (inner radius), producing ONE fused sheet body (the
         *     base + flange joined across the cylindrical bend region).
         *
         *     INHERITED DEFAULTS (§4.2): ``bend_radius_mm`` and ``k_factor`` default from the
         *     part's base flange (:class:`SheetMetalBaseFlangeParamsV1` — the gauge/K/radius
         *     anchored on the sheet body) when omitted (``None``), and may be OVERRIDDEN
         *     per-bend. ``flange_length_mm`` is the developed flat length of the flange leg
         *     (to the bend tangent line, §9 golden #1's convention); ``bend_angle_deg`` is
         *     the fold angle (90 deg for a right-angle flange).
         *
         *     Like a fillet/shell it MODIFIES the implicit single body chain (design §7.6) —
         *     it carries no ``merge`` (it always fuses into the sheet body the edge belongs
         *     to) — so its only whole-feature dependency is the named-edge ref + tree order.
         */
        SheetMetalEdgeFlangeParamsV1: {
            /**
             * Bend Angle Deg
             * @description Fold angle (degrees); 90 = a right-angle flange. In (0, 180].
             */
            bend_angle_deg: number;
            /**
             * Bend Radius Mm
             * @description INNER bend radius (mm). Omitted (None) inherits the part's base-flange default `bend_radius_mm` (§4.2); a value overrides it per-bend.
             */
            bend_radius_mm?: number | null;
            /** @description The base-flange STRAIGHT edge to fold off (a stage-1 EdgeSignature reference resolved against the current sheet body). The flange extends from this edge's adjacent flat face and folds about it. */
            edge: components["schemas"]["EdgeSubshapeRef"];
            /**
             * Flange Length Mm
             * @description Developed flat length of the flange leg (mm), measured to the bend tangent line (§9 golden #1 convention).
             */
            flange_length_mm: number;
            /**
             * K Factor
             * @description Neutral-axis fraction K in [0, 1] for this bend's allowance (§1). Omitted (None) inherits the part's base-flange default `k_factor` (0.44 v1 baseline); a value overrides it per-bend.
             */
            k_factor?: number | null;
            /**
             * Offset Mm
             * @description Span OFFSET (mm) from the picked edge's canonical start (its EdgeSignature `end_a`, design §4.5.1). Omitted (None) reads 0 — the span starts at `end_a`. With `width_mm` omitted the flange spans [offset, edge_length]. Nullable-optional (like `width_mm`) so existing clients that never send it stay valid — the additive-field rule.
             */
            offset_mm?: number | null;
            /**
             * Width Mm
             * @description Flange WIDTH (mm) along the picked edge (design §4.5.1). Omitted (None) spans the full edge (or the remainder past `offset_mm`). The span [offset, offset + width] is measured from the edge's CANONICAL start (the lexicographically smaller endpoint — the stored EdgeSignature's `end_a`). `offset + width` must fit the resolved edge length (a typed feature error otherwise). Each span end INTERIOR to the edge gets an automatic rectangular bend-end relief notch, size = 1 x gauge (§4.5.2).
             */
            width_mm?: number | null;
        };
        /**
         * SheetMetalHemFeature
         * @description ``{"type": "sheet_metal_hem", "version": 1, "params": {...}}`` envelope.
         *
         *     A body-MODIFYING feature (parity §2, closed hem): it folds the picked edge ~180
         *     deg back onto the sheet (reusing the edge flange's bend machinery at a fixed 180
         *     deg fold), fusing one clean solid, and tags the bend face with a
         *     :class:`CylindricalFaceSignature` (§5) for the unfold's provenance — exactly as
         *     an edge flange does. ``params`` is :class:`SheetMetalHemParamsV1`.
         */
        SheetMetalHemFeature: {
            params: components["schemas"]["SheetMetalHemParamsV1"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "sheet_metal_hem";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * SheetMetalHemParamsV1
         * @description A hem folded off a straight edge of the sheet — v1 CLOSED hem (parity §2).
         *
         *     A closed hem folds the picked edge ~180 deg back FLAT against the parent face,
         *     with a small inner ``bend_radius_mm`` giving the doubled edge its tight,
         *     near-zero air gap (the gap between the two layers is ~2 * bend_radius). It is a
         *     specialization of the edge flange: the geometry side reuses ``build_edge_flange``
         *     with the fold angle FIXED at 180 deg, so the fused body is one clean solid and
         *     the flat pattern develops it as any bend (``BA = pi * (radius + K * thickness)``,
         *     §1) — its bend-table row reads angle 180 deg.
         *
         *     ``edge`` is an :class:`EdgeSubshapeRef` naming the base-flange edge to hem — the
         *     SAME stage-1 :class:`EdgeSignature` machinery a fillet/chamfer or edge-flange
         *     pick uses (topological-naming §10); its ``feature_id`` materialises the
         *     dependency on the base-flange feature. ``length_mm`` is the developed flat
         *     length of the folded-back return (to the bend tangent line, §9 golden #1's
         *     convention). ``bend_radius_mm`` / ``k_factor`` default from the part's base
         *     flange (:class:`SheetMetalBaseFlangeParamsV1`) when omitted (``None``) and may
         *     be OVERRIDDEN per-hem — a tight closed hem sets a SMALL radius (e.g. ~0.5 *
         *     thickness) rather than the part's general bend radius.
         *
         *     A ZERO ``bend_radius_mm`` (a truly zero-gap / zero-radius closed hem) is a
         *     degenerate fold; the ``gt=0`` bound rejects it as a typed validation error
         *     rather than admitting a degenerate solid (honest degradation — parity §3).
         *
         *     Like a fillet/shell it MODIFIES the implicit single body chain (design §7.6) —
         *     it carries no ``merge`` (it always fuses into the sheet body the edge belongs
         *     to) — so its only whole-feature dependency is the named-edge ref + tree order.
         */
        SheetMetalHemParamsV1: {
            /**
             * Bend Radius Mm
             * @description INNER bend radius (mm) of the hem fold; the layers' air gap is ~2 * this. Omitted (None) inherits the part's base-flange default `bend_radius_mm`; a value overrides it per-hem. A tight closed hem uses a SMALL radius (~0.5 * thickness). A zero radius (zero-gap degenerate fold) is rejected by the `gt=0` bound.
             */
            bend_radius_mm?: number | null;
            /** @description The base-flange STRAIGHT edge to hem (a stage-1 EdgeSignature reference resolved against the current sheet body). The return folds ~180 deg back over this edge's adjacent flat face. */
            edge: components["schemas"]["EdgeSubshapeRef"];
            /**
             * Hem Type
             * @description Hem shape. v1 ships 'closed' only (the return folds flat back against the parent — parity §2). Open / teardrop / rolled hems each need a curved cross-section profile and are deferred (additive Literal members, no param_version bump). Absent reads 'closed'.
             * @default closed
             * @constant
             */
            hem_type: "closed";
            /**
             * K Factor
             * @description Neutral-axis fraction K in [0, 1] for the hem's bend allowance (§1). Omitted (None) inherits the part's base-flange default `k_factor` (0.44 v1 baseline); a value overrides it per-hem.
             */
            k_factor?: number | null;
            /**
             * Length Mm
             * @description Developed flat length of the folded-back return (mm), measured to the bend tangent line (§9 golden #1 convention).
             */
            length_mm: number;
        };
        /**
         * SheetMutationResponse
         * @description Result of a single-sheet mutation: the sheet + the new version.
         */
        SheetMutationResponse: {
            /** Doc Version */
            doc_version: number;
            sheet: components["schemas"]["SheetResponse"];
        };
        /**
         * SheetPoint
         * @description A 2D point in SHEET space (mm), origin at the title-block corner (§9 q4).
         *
         *     Sheet space is millimetres at 1:1; a view's scale maps model-mm → sheet-mm
         *     (design §9 open-q 4). Used for view placement, dimension text, and note
         *     positions. Full precision; a non-finite coordinate is a request-validation
         *     422 (``allow_inf_nan=False``), never a silently-defaulted position.
         */
        SheetPoint: {
            /**
             * X Mm
             * @description X on the sheet, mm from the origin corner
             */
            x_mm: number;
            /**
             * Y Mm
             * @description Y on the sheet, mm from the origin corner
             */
            y_mm: number;
        };
        /**
         * SheetResponse
         * @description A sheet as stored (design §2.2).
         */
        SheetResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Drawing Id
             * Format: uuid
             */
            drawing_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Order Index
             * @description Stable sheet order (dense 0..n-1)
             */
            order_index: number;
            /**
             * Orientation
             * @enum {string}
             */
            orientation: "landscape" | "portrait";
            /**
             * Projection
             * @enum {string}
             */
            projection: "third_angle" | "first_angle";
            /**
             * Size
             * @enum {string}
             */
            size: "A4" | "A3" | "A2" | "A1" | "A0" | "ANSI_A" | "ANSI_B" | "ANSI_C" | "ANSI_D";
            title_block: components["schemas"]["TitleBlock"] | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * SheetUpdate
         * @description Update a sheet's header (design §2.2). At least one field must be provided.
         */
        SheetUpdate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §2.1)
             */
            expected_version: number;
            /** Name */
            name?: string | null;
            /** Orientation */
            orientation?: ("landscape" | "portrait") | null;
            /** Projection */
            projection?: ("third_angle" | "first_angle") | null;
            /** Size */
            size?: ("A4" | "A3" | "A2" | "A1" | "A0" | "ANSI_A" | "ANSI_B" | "ANSI_C" | "ANSI_D") | null;
            /** @description Replacement title block (None leaves it unchanged; clear via an empty TitleBlock) */
            title_block?: components["schemas"]["TitleBlock"] | null;
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
         * SketchConstraintDiagnosis
         * @description Typed classification of an over-constrained sketch (BACKLOG #6).
         *
         *     Exposes the solver's already-computed redundant/conflicting constraint sets
         *     (:class:`SolvedSketch`) as a STRUCTURED diagnosis a caller reads by field —
         *     never a message string the frontend has to parse. It distinguishes the two
         *     over-constraint kinds a working engineer must tell apart (VISION.md
         *     Sketching row): a REDUNDANT constraint is removable and the sketch still
         *     solves, whereas a CONFLICTING constraint makes the sketch unsolvable until
         *     one is relaxed. Built by :func:`classify_overconstraint`; carried on the
         *     :class:`py_kit.schemas.features.FeatureError` (the ``sketch_conflicting``
         *     error path) and on the solved-sketch feature payload (the redundant-but-
         *     solvable path), so BOTH cases surface the same typed shape.
         */
        SketchConstraintDiagnosis: {
            /**
             * Classification
             * @description Over-constraint kind: 'redundant' (removable, still solves) or 'conflicting' (contradictory, unsolvable until relaxed).
             * @enum {string}
             */
            classification: "redundant" | "conflicting";
            /**
             * Conflicting Constraints
             * @description Indices (into the sketch's input constraint list) of the CONTRADICTORY constraints — empty for a purely redundant over-constraint.
             */
            conflicting_constraints?: number[];
            /**
             * Message
             * @description Human-readable diagnosis (kernel/solver detail sanitized).
             */
            message: string;
            /**
             * Redundant Constraints
             * @description Indices (into the sketch's input constraint list) of the REDUNDANT (consistent-but-superfluous, removable) constraints.
             */
            redundant_constraints?: number[];
            /**
             * Removable
             * @description True when the sketch still solves after removing the named constraints (the redundant case); False when a genuine conflict remains (the sketch is unsolvable). Mirrors `classification` for callers that prefer a boolean over the enum.
             */
            removable: boolean;
            /**
             * Suggested Fix
             * @description Actionable hint naming a constraint to remove/relax, e.g. 'Remove constraint 3'. None when no single-constraint fix is offered.
             */
            suggested_fix?: string | null;
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
         * SolvedDimension
         * @description The computed value of one dimension constraint in a solved sketch.
         *
         *     Reported per dimension so the sketcher can show the number next to each
         *     dimension WITHOUT re-parsing expressions itself:
         *
         *     * **driving** — ``value_mm`` is the evaluated literal/expression value that
         *       was fed to the solver (e.g. ``height="width/2"`` with ``width=20`` reports
         *       ``value_mm=10``).
         *     * **driven** — ``value_mm`` is the value MEASURED back from the solved
         *       geometry (a line's length / a circle-or-arc's radius): the read-only
         *       readout that updates as the geometry it dimensions moves.
         *
         *     ``constraint_index`` points into the sketch's input constraint list, so the
         *     UI can line each readout up with the constraint the user authored.
         */
        SolvedDimension: {
            /**
             * Constraint Index
             * @description Index into the sketch's input constraint list.
             */
            constraint_index: number;
            /**
             * Driving
             * @description True = driving (value fed to the solver); False = driven (value measured back from the solved geometry).
             */
            driving: boolean;
            /**
             * Expression
             * @description The dimension's source expression, echoed for the UI (None for a bare literal dimension).
             */
            expression?: string | null;
            /**
             * Name
             * @description The dimension's reference name, if it has one.
             */
            name?: string | null;
            /**
             * Value Mm
             * @description Computed value (mm): the evaluated expression/literal for a driving dimension, or the measured geometry value for a driven one.
             */
            value_mm: number;
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
            /** @description Typed over-constraint classification for a SOLVED-but-over-constrained sketch (``overconstrained`` status): the redundant, removable constraints named so the sketcher can flag them without parsing text (BACKLOG #6). None for a cleanly-constrained sketch. The unsolvable ("conflicting") case rides FeatureError.sketch_diagnosis. */
            diagnosis?: components["schemas"]["SketchConstraintDiagnosis"] | null;
            /**
             * Dimensions
             * @description Per-dimension computed values (driving = evaluated expression/literal; driven = measured from the solved geometry). One entry per dimension constraint, in input order. Empty for a sketch with no dimensions; additive (pre-expression callers ignore it).
             */
            dimensions?: components["schemas"]["SolvedDimension"][];
            /**
             * Dof
             * @description Remaining degrees of freedom (0 = fully constrained); None when the diagnosis cannot determine it (e.g. conflicting systems).
             */
            dof?: number | null;
            /**
             * Entities
             * @description Same entities (ids, kinds, order) as the input. Positions are solved when the numeric solve succeeded (converged, underconstrained, and consistent overconstrained cases); for conflicting/diverged sketches the input positions are returned unchanged.
             */
            entities: (components["schemas"]["SketchPoint"] | components["schemas"]["SketchLine"] | components["schemas"]["SketchCircle"] | components["schemas"]["SketchArc"] | components["schemas"]["SketchSpline"])[];
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
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
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
             * Merge
             * @description Merge result (ADD only): True fuses the new solid into the active body (default, historical single-body behaviour / starts the first body); False starts a NEW body (multi-body, design multi-body.md §MB-0). Ignored for a CUT. Additive — absent reads True, no param_version bump.
             * @default true
             */
            merge: boolean;
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
         * TitleBlock
         * @description Free-text title-block fields (design §9 open-q 6 — v1 holds free text).
         *
         *     Every field is optional; a structured/field-mapped title block auto-filled
         *     from the referenced part is a fast-follow. The composed artifact stamps these
         *     geometry-side (design §4.2).
         */
        TitleBlock: {
            /**
             * Author
             * @description Author / drafter
             */
            author?: string | null;
            /**
             * Date
             * @description Free-text date
             */
            date?: string | null;
            /**
             * Notes
             * @description Free-text notes
             */
            notes?: string | null;
            /**
             * Title
             * @description Drawing title
             */
            title?: string | null;
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
        /**
         * UndoRedoRequest
         * @description Restore the adjacent history snapshot (docs/design/undo-redo.md).
         *
         *     Undo/redo ARE document edits: each bumps ``tree_version`` under the same
         *     optimistic-concurrency guard as every other write (stale → 422), and the
         *     response is the restored tree (ids preserved VERBATIM — the load-bearing
         *     snapshot decision). At a boundary — undo at the ring's floor, redo at its
         *     top — the op is a CLEAN no-op, not an error: 200 with the current tree,
         *     version unchanged. ``can_undo``/``can_redo`` on the tree response let the
         *     UI disable the controls, so a click racing that state is harmless.
         */
        UndoRedoRequest: {
            /** Expected Tree Version */
            expected_tree_version: number;
        };
        /**
         * UserResponse
         * @description Public view of an account — no credential material, ever.
         */
        UserResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Email
             * Format: email
             */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
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
        /**
         * ViewCreate
         * @description Add a view referencing a part / assembly at a projection (design §2.2).
         *
         *     ``ref_document_id`` is a cross-document reference, NOT an FK (design §2.2,
         *     identical to an assembly instance): documents enforces existence at write time
         *     and deleting the referenced document is a 409-with-dependents. v1 tracks the
         *     referenced document's TIP (``ref_pinned_version`` present but NULL — design
         *     §2.3, the schema is pin-ready). ``projection`` is the standard orthographic /
         *     iso direction (all documents stores — mapping it to a 3D frame + HLR is
         *     geometry's job). ``order_index`` is appended at the tip when omitted.
         */
        ViewCreate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §2.1)
             */
            expected_version: number;
            /** @description View placement on the sheet (mm) */
            position: components["schemas"]["SheetPoint"];
            /**
             * Projection
             * @description Projection direction (front / top / right / iso / flat_pattern / section)
             * @enum {string}
             */
            projection: "front" | "top" | "right" | "iso" | "flat_pattern" | "section";
            /**
             * Ref Document Id
             * Format: uuid
             * @description The part / assembly document this view projects
             */
            ref_document_id: string;
            /**
             * Ref Document Kind
             * @description 'part' (v1) or 'assembly' (assembly views are the fast-follow, design §7)
             * @default part
             * @enum {string}
             */
            ref_document_kind: "part" | "assembly";
            /**
             * @description Drawing scale (rational; 1:1 default)
             * @default {
             *       "denominator": 1,
             *       "numerator": 1
             *     }
             */
            scale: components["schemas"]["ViewScale"];
            /** @description The cutting plane + flip for a `section` view (drawings-section.md §1); required iff `projection == 'section'`, NULL for every other view. Documents validates the ref shape and persists it as JSONB (the geometry service resolves + cuts). */
            section_params?: components["schemas"]["SectionViewParams"] | null;
        };
        /**
         * ViewMutationResponse
         * @description Result of a single-view mutation: the view + the new version.
         */
        ViewMutationResponse: {
            /** Doc Version */
            doc_version: number;
            view: components["schemas"]["ViewResponse"];
        };
        /**
         * ViewResponse
         * @description A view as stored (design §2.2).
         */
        ViewResponse: {
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
            /**
             * Order Index
             * @description Stable view order on the sheet (dense 0..n-1)
             */
            order_index: number;
            position: components["schemas"]["SheetPoint"];
            /**
             * Projection
             * @enum {string}
             */
            projection: "front" | "top" | "right" | "iso" | "flat_pattern" | "section";
            /**
             * Ref Document Id
             * Format: uuid
             */
            ref_document_id: string;
            /**
             * Ref Document Kind
             * @enum {string}
             */
            ref_document_kind: "part" | "assembly";
            /**
             * Ref Pinned Version
             * @description Pinned referenced-document version, or null = track tip. NULL in v1 (design §2.3 — the schema is pin-ready).
             */
            ref_pinned_version: number | null;
            scale: components["schemas"]["ViewScale"];
            /** @description The section view's cutting plane + flip (drawings-section.md §1); NULL for every non-section view */
            section_params?: components["schemas"]["SectionViewParams"] | null;
            /**
             * Sheet Id
             * Format: uuid
             */
            sheet_id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * ViewScale
         * @description A view's drawing scale as an exact rational ``numerator:denominator``.
         *
         *     Stored as two integers (design §2.2 ``scale_num``/``scale_den``) so the scale
         *     is EXACT — 1:2 is ``1/2``, never a lossy float. A model-mm length maps to
         *     ``length * numerator / denominator`` sheet-mm. Both are >= 1.
         */
        ViewScale: {
            /**
             * Denominator
             * @description Scale denominator (N for 1:N)
             */
            denominator: number;
            /**
             * Numerator
             * @description Scale numerator (1 for 1:N)
             */
            numerator: number;
        };
        /**
         * ViewUpdate
         * @description Re-frame / re-scale / re-place a view (design §2.2).
         *
         *     Every field is optional; at least one must be provided. Re-pointing the
         *     referenced document is NOT an update (it changes which body the view's
         *     dimensions resolve against) — that is a delete + recreate.
         */
        ViewUpdate: {
            /**
             * Expected Version
             * @description Optimistic-concurrency guard (design §2.1)
             */
            expected_version: number;
            position?: components["schemas"]["SheetPoint"] | null;
            /** Projection */
            projection?: ("front" | "top" | "right" | "iso" | "flat_pattern" | "section") | null;
            scale?: components["schemas"]["ViewScale"] | null;
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
    list_assemblies_api_v1_assemblies_get: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["AssemblyListResponse"];
                };
            };
        };
    };
    create_assembly_api_v1_assemblies_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssemblyCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssemblyResponse"];
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
    get_assembly_api_v1_assemblies__assembly_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
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
                    "application/json": components["schemas"]["AssemblyGraphResponse"];
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
    delete_assembly_api_v1_assemblies__assembly_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
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
    update_assembly_api_v1_assemblies__assembly_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssemblyUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssemblyResponse"];
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
    get_assembly_bom_api_v1_assemblies__assembly_id__bom_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
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
                    "application/json": components["schemas"]["AssemblyBomResponse"];
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
    create_instance_api_v1_assemblies__assembly_id__instances_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InstanceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstanceMutationResponse"];
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
    delete_instance_api_v1_assemblies__assembly_id__instances__instance_id__delete: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard */
                expected_version: number;
            };
            header?: never;
            path: {
                assembly_id: string;
                instance_id: string;
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
                    "application/json": components["schemas"]["AssemblyGraphResponse"];
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
    update_instance_api_v1_assemblies__assembly_id__instances__instance_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
                instance_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InstanceUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstanceMutationResponse"];
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
    create_mate_api_v1_assemblies__assembly_id__mates_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MateCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MateMutationResponse"];
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
    delete_mate_api_v1_assemblies__assembly_id__mates__mate_id__delete: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard */
                expected_version: number;
            };
            header?: never;
            path: {
                assembly_id: string;
                mate_id: string;
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
                    "application/json": components["schemas"]["AssemblyGraphResponse"];
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
    redo_assembly_api_v1_assemblies__assembly_id__redo_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssemblyUndoRedoRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssemblyGraphResponse"];
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
    undo_assembly_api_v1_assemblies__assembly_id__undo_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assembly_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssemblyUndoRedoRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssemblyGraphResponse"];
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
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthTokenResponse"];
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
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
        };
    };
    register_api_v1_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthTokenResponse"];
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
    list_drawings_api_v1_drawings_get: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["DrawingListResponse"];
                };
            };
        };
    };
    create_drawing_api_v1_drawings_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DrawingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DrawingResponse"];
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
    get_drawing_api_v1_drawings__drawing_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
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
                    "application/json": components["schemas"]["DrawingTreeResponse"];
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
    delete_drawing_api_v1_drawings__drawing_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
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
    update_drawing_api_v1_drawings__drawing_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DrawingUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DrawingResponse"];
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
    delete_annotation_api_v1_drawings__drawing_id__annotations__annotation_id__delete: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard */
                expected_version: number;
            };
            header?: never;
            path: {
                drawing_id: string;
                annotation_id: string;
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
                    "application/json": components["schemas"]["DrawingTreeResponse"];
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
    delete_dimension_api_v1_drawings__drawing_id__dimensions__dimension_id__delete: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard */
                expected_version: number;
            };
            header?: never;
            path: {
                drawing_id: string;
                dimension_id: string;
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
                    "application/json": components["schemas"]["DrawingTreeResponse"];
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
    export_drawing_api_v1_drawings__drawing_id__export_post: {
        parameters: {
            query?: {
                /** @description Artifact format to compose: svg | pdf | dxf */
                format?: "svg" | "pdf" | "dxf";
            };
            header?: never;
            path: {
                drawing_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The server-composed drawing artifact, proxied byte-exact from the geometry service: SVG (`image/svg+xml`), PDF (`application/pdf`), or DXF (`image/vnd.dxf`). `Content-Disposition` carries the suggested download filename. Composition is deterministic — identical drawing state produces an identical artifact (drawing-export.md §determinism). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": string;
                    "image/svg+xml": string;
                    "image/vnd.dxf": string;
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
    compose_drawing_sheet_api_v1_drawings__drawing_id__sheet_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
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
                    "application/json": components["schemas"]["ComposedSheet"];
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
    create_sheet_api_v1_drawings__drawing_id__sheets_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SheetCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SheetMutationResponse"];
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
    delete_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__delete: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard */
                expected_version: number;
            };
            header?: never;
            path: {
                drawing_id: string;
                sheet_id: string;
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
                    "application/json": components["schemas"]["DrawingTreeResponse"];
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
    update_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
                sheet_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SheetUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SheetMutationResponse"];
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
    create_annotation_api_v1_drawings__drawing_id__sheets__sheet_id__annotations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
                sheet_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnotationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnotationMutationResponse"];
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
    create_view_api_v1_drawings__drawing_id__sheets__sheet_id__views_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
                sheet_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ViewCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ViewMutationResponse"];
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
    delete_view_api_v1_drawings__drawing_id__views__view_id__delete: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard */
                expected_version: number;
            };
            header?: never;
            path: {
                drawing_id: string;
                view_id: string;
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
                    "application/json": components["schemas"]["DrawingTreeResponse"];
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
    update_view_api_v1_drawings__drawing_id__views__view_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
                view_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ViewUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ViewMutationResponse"];
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
    create_dimension_api_v1_drawings__drawing_id__views__view_id__dimensions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                drawing_id: string;
                view_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DimensionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DimensionMutationResponse"];
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
    assembly_evaluate_api_v1_geometry_assembly_evaluate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvaluateAssemblyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvaluateAssemblyResult"];
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
    assembly_export_api_v1_geometry_assembly_export_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExportAssemblyRequest"];
            };
        };
        responses: {
            /** @description The exported assembly CAD file, proxied byte-exact from the geometry service: STEP AP214 part 21 (`model/step`, exact B-rep with product structure — each instance a named PRODUCT at its solved placement) or binary STL (`model/stl`, faceted mesh). `Content-Disposition` carries the suggested download filename. Byte-deterministic: identical requests produce identical files. */
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
    drawing_evaluate_api_v1_geometry_drawing_evaluate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvaluateDrawingViewsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvaluateDrawingViewsResult"];
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
    export_api_v1_geometry_export_post: {
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
            /** @description The exported CAD file, proxied byte-exact from the geometry service: STEP AP214 part 21 (`model/step`, exact B-rep) or binary STL (`model/stl`, faceted mesh). `Content-Disposition` carries the suggested download filename. Byte-deterministic: identical requests produce identical files. */
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
    measure_api_v1_geometry_measure_post: {
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
    fetch_mesh_api_v1_geometry_meshes__mesh_glb_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Content address of the GLB artifact (`sha256:<hex>`), from `EvaluateTreeResult.mesh_glb_id`. */
                mesh_glb_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Binary glTF (GLB) mesh addressed by an `EvaluateTreeResult.mesh_glb_id` content hash (`sha256:<hex>`), proxied byte-exact from the geometry service. A 404 `mesh_not_found` envelope means evicted or unknown: re-evaluate the tree to regenerate the artifact (feature-tree design §4.4/§7.8). */
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
    overlay_api_v1_geometry_overlay_post: {
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
    sketch_chamfer_api_v1_geometry_sketch_chamfer_post: {
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
    sketch_extend_api_v1_geometry_sketch_extend_post: {
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
    sketch_fillet_api_v1_geometry_sketch_fillet_post: {
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
    sketch_mirror_api_v1_geometry_sketch_mirror_post: {
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
    sketch_offset_api_v1_geometry_sketch_offset_post: {
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
    sketch_trim_api_v1_geometry_sketch_trim_post: {
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
    tessellate_api_v1_geometry_tessellate_post: {
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
            /** @description Binary glTF (GLB) mesh of the requested shape, proxied from the geometry service. The `X-Loft-Properties` header carries `TessellationMetadata` as compact JSON (see `POST /api/v1/geometry/tessellate/meta` for the same payload as a typed JSON body). */
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
    tessellate_meta_api_v1_geometry_tessellate_meta_post: {
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
    list_parts_api_v1_parts_get: {
        parameters: {
            query?: never;
            header?: never;
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
        };
    };
    create_part_api_v1_parts_post: {
        parameters: {
            query?: never;
            header?: never;
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
            header?: never;
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
            header?: never;
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
    update_part_api_v1_parts__part_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PartUpdate"];
            };
        };
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
    evaluate_part_api_v1_parts__part_id__evaluate_post: {
        parameters: {
            query?: never;
            header?: never;
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
    export_part_api_v1_parts__part_id__export_post: {
        parameters: {
            query: {
                /** @description Export file format: STEP or STL */
                format: "step" | "stl";
            };
            header?: never;
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The exported CAD file of the part's current evaluated body, proxied byte-exact from the geometry service: STEP AP214 part 21 (`model/step`, exact B-rep) or binary STL (`model/stl`, faceted mesh). `Content-Disposition` carries the suggested download filename. A tree that evaluates to no body is a 422 `tree_export_failed` envelope. */
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
    get_feature_tree_api_v1_parts__part_id__features_get: {
        parameters: {
            query?: never;
            header?: never;
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
            header?: never;
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
    import_step_api_v1_parts__part_id__features_import_post: {
        parameters: {
            query: {
                /** @description Optimistic-concurrency guard: the tree_version the client last saw (as on every feature mutation) */
                expected_tree_version: number;
                /** @description User-facing name for the created import feature */
                name?: string;
            };
            header?: never;
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        /** @description The STEP part-21 file bytes (raw request body). */
        requestBody: {
            content: {
                "application/octet-stream": string;
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
            header?: never;
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
            header?: never;
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
                /** @description Optimistic-concurrency guard */
                expected_tree_version: number;
            };
            header?: never;
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
            header?: never;
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
    redo_part_api_v1_parts__part_id__redo_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UndoRedoRequest"];
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
    move_rollback_bar_api_v1_parts__part_id__rollback_put: {
        parameters: {
            query?: never;
            header?: never;
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
    undo_part_api_v1_parts__part_id__undo_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                part_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UndoRedoRequest"];
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
