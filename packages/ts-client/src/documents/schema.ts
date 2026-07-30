// GENERATED — do not edit; run `just gen`.
// Types for the documents service (source contract: packages/contracts/documents.openapi.json).
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
         * @description The caller's assemblies, oldest first (deterministic id tiebreak).
         */
        get: operations["list_assemblies_api_v1_assemblies_get"];
        put?: never;
        /**
         * Create Assembly
         * @description Create an assembly (201; envelope 409 on a duplicate name for this owner).
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
         * @description Delete an owned assembly; 409 when instanced as a sub-assembly elsewhere.
         *
         *     The assembly→instances/mates CASCADE removes its own graph. A 409-with-
         *     dependents pre-check (design §1.2, mirroring the part 409) refuses the
         *     delete while ANOTHER assembly still instances this one as a sub-assembly,
         *     listing the referencing assemblies.
         */
        delete: operations["delete_assembly_api_v1_assemblies__assembly_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Assembly
         * @description Rename and/or re-unit an assembly (bumps ``doc_version``; 409 on a name
         *     clash).
         *
         *     Changing ``length_unit`` is a document edit (docs/design/units.md §U1) —
         *     metadata only, storage stays canonical mm — and bumps ``doc_version`` like
         *     any header mutation. Unlike a part rename (outside UR1 history), this IS a
         *     UR3 history event — the snapshot state carries the mutable header fields,
         *     so undo restores them (docs/design/undo-redo.md UR3).
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
         *     A pure read model (assemblies.md residual): groups the assembly's DIRECT
         *     instances by referenced document, resolving each to its current name and
         *     kind. NOT recursive into rigid sub-assemblies — a sub-assembly instance is a
         *     single ``kind: "assembly"`` line (recursive/indented BOM is a tracked
         *     follow-up). A referenced document deleted while still instanced is reported
         *     as a ``missing`` line with a null name, never a 500.
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
    "/api/v1/assemblies/{assembly_id}/evaluation-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Assembly Evaluation Request
         * @description The evaluation-ready assembly graph (design §4/§7), for the gateway to forward
         *     to the geometry service verbatim.
         *
         *     The assembly sibling of ``GET /parts/{id}/evaluation-request``: documents resolves
         *     the instance + mate graph + each instanced part's rollback-applied feature prefix
         *     into the :class:`EvaluateAssemblyRequest` geometry solves (uniform 404 for an
         *     unknown / foreign assembly). Kernel-free — pure INTENT crosses the boundary
         *     (CLAUDE.md). The gateway threads this into an assembly-kind drawing view's
         *     ``ComposeDrawingRequest.assembly`` so the view projects the SOLVED assembly compound
         *     (§7), then folds the per-view HLR edges into the sheet exactly as a part view.
         */
        get: operations["get_assembly_evaluation_request_api_v1_assemblies__assembly_id__evaluation_request_get"];
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
         * @description Add an instance referencing a part / sub-assembly (append at the tip).
         *
         *     Enforces cross-document integrity (§1.2): the referenced document must exist
         *     and belong to the caller (else ``ref_document_not_found`` 422), and a
         *     sub-assembly reference must not create a cycle (``assembly_cycle`` 422 —
         *     walked here, never a stack overflow at eval).
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
         * @description Remove an instance; also removes mates that reference it (bumps version).
         *
         *     A mate is a constraint EDGE, meaningless without both endpoints — so
         *     deleting an instance cascades to the mates naming it (documents-side, since
         *     the mate's instance refs live in JSONB, not a DB FK). Both instances and
         *     mates are renumbered dense. Returns the updated graph (the client's new
         *     ``doc_version``).
         */
        delete: operations["delete_instance_api_v1_assemblies__assembly_id__instances__instance_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Instance
         * @description Re-place / rename / (un)ground / reorder an instance (bumps ``doc_version``).
         *
         *     Re-pointing the referenced document is deliberately NOT an update (it
         *     changes the graph edge the acyclicity walk sees) — delete + recreate.
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
         * @description Add a mate (append at the tip). Every instance it names must belong to
         *     this assembly (``mate_instance_unknown`` 422 otherwise).
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
         * @description Remove a mate; renumbers the rest dense (bumps ``doc_version``).
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
         * Redo
         * @description Restore the next history snapshot VERBATIM (ids preserved).
         *
         *     Clean no-op at the top of the ring; stale ``expected_version`` → 422.
         */
        post: operations["redo_api_v1_assemblies__assembly_id__redo_post"];
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
         * Undo
         * @description Restore the previous history snapshot VERBATIM (ids preserved).
         *
         *     Clean no-op at the baseline; stale ``expected_version`` → 422.
         */
        post: operations["undo_api_v1_assemblies__assembly_id__undo_post"];
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
         * @description The caller's drawings, oldest first (deterministic id tiebreak).
         */
        get: operations["list_drawings_api_v1_drawings_get"];
        put?: never;
        /**
         * Create Drawing
         * @description Create a drawing (201; envelope 409 on a duplicate name for this owner).
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
         *     A drawing is a pure LEAF (nothing references it — design §2.2), so there is no
         *     dependents pre-check: the drawing→sheets→views→dimensions and
         *     sheets→annotations CASCADE removes its entire layout.
         */
        delete: operations["delete_drawing_api_v1_drawings__drawing_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Drawing
         * @description Rename a drawing (bumps ``doc_version``; envelope 409 on a name clash).
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
         * @description Delete an annotation; renumbers the sheet's annotations dense (bumps
         *     version).
         */
        delete: operations["delete_annotation_api_v1_drawings__drawing_id__annotations__annotation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/drawings/{drawing_id}/bom": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Drawing Bom
         * @description The sheet's bill of materials — numbered items derived from its assembly.
         *
         *     A pure READ MODEL (no table, no migration, no write path): the sheet's single
         *     source document must be an ASSEMBLY, and its DIRECT instances roll up into
         *     ``item_number``-ed lines. **The numbers are derived on every read from the
         *     assembly's stable instance order and are never persisted on the drawing** —
         *     the drift class a stored number would create (the assembly changes; the print
         *     keeps the old number and is silently wrong) is designed out rather than
         *     detected. ``assembly_version`` is echoed so a tip-tracking client can see the
         *     source move under it.
         *
         *     Typed refusals, never a misleading empty list: ``sheet_not_found`` (404),
         *     ``sheet_has_no_views`` / ``drawing_bom_source_not_assembly`` /
         *     ``drawing_bom_source_missing`` (422). Uniform 404 for an unknown or foreign
         *     drawing.
         */
        get: operations["get_drawing_bom_api_v1_drawings__drawing_id__bom_get"];
        put?: never;
        post?: never;
        delete?: never;
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
         * @description Delete a dimension; renumbers the sheet's dimensions dense (bumps version).
         */
        delete: operations["delete_dimension_api_v1_drawings__drawing_id__dimensions__dimension_id__delete"];
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
         * @description Add a sheet to a drawing (append at the tip).
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
         * @description Delete a sheet (cascades its views/dimensions/annotations); renumbers the
         *     remaining sheets dense (bumps ``doc_version``).
         */
        delete: operations["delete_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Sheet
         * @description Update a sheet's header (bumps ``doc_version``).
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
         *     Enforces cross-document integrity (§2.2): the referenced document must exist
         *     and belong to the caller (else ``ref_document_not_found`` 422). No acyclicity
         *     check — a drawing is a leaf consumer (§2.2). ``ref_pinned_version`` is stored
         *     NULL: v1 tracks the referenced document's tip (§2.3).
         *
         *     Also enforces the SHEET-consistency invariant (design §2.2 "one sheet, one
         *     source"; engineering audit H2): every view of a sheet must reference the SAME
         *     document at the SAME scale, because composition threads exactly one source +
         *     one scale per sheet (``ComposeDrawingRequest``). A mismatch is a typed
         *     ``sheet_source_document_mismatch`` / ``sheet_view_scale_mismatch`` 422 —
         *     the alternative was silently projecting every view from the first view's part
         *     at the first view's scale, i.e. a wrong drawing a shop would cut from.
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
         * @description Delete a view; also removes the dimensions it carries (bumps version).
         *
         *     A dimension is meaningless without the view it annotates — the ``view_id``
         *     CASCADE removes the view's dimensions. Both the sheet's views AND its
         *     dimensions are then renumbered dense (the cascade can leave gaps in the
         *     per-sheet dimension order). Returns the updated tree (the client's new
         *     ``doc_version``).
         */
        delete: operations["delete_view_api_v1_drawings__drawing_id__views__view_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update View
         * @description Re-frame / re-scale / re-place a view (bumps ``doc_version``).
         *
         *     The drag-to-place write path (drawing-export.md §4.2): a frontend PERSISTS a
         *     dragged position by patching ``position`` + ``auto_place=false`` — the position
         *     then survives reload and the compose/export path honors it verbatim (threaded
         *     into ``SheetViewPlacement.auto_place``) instead of auto-placing. ``auto_place=true``
         *     returns the view to bounds-aware auto-layout.
         *
         *     Re-pointing the referenced document is deliberately NOT an update (it changes
         *     which body the view's dimensions resolve against) — delete + recreate.
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
         *     The dimension's geometry references resolve against the view's referenced body
         *     geometry-side (design §3.3); documents stores the reference + type and runs
         *     the kernel-free write-time checks (:func:`_validate_dimension`).
         */
        post: operations["create_dimension_api_v1_drawings__drawing_id__views__view_id__dimensions_post"];
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
         *     Deletion removes the part's own feature tree unconditionally: the
         *     parts→features CASCADE removes the tree, and the deferred target-side FK on
         *     feature_dependencies makes that legal at commit time (docs/design/feature-
         *     tree.md §2.3 — the intra-part 409-with-dependents pre-check applies to
         *     deleting a single FEATURE, never the whole part).
         *
         *     But a part still INSTANCED by an assembly is a cross-document dependent
         *     (docs/design/assemblies.md §1.2): deleting it is a friendly 409-with-
         *     dependents listing the referencing assemblies, mirroring the feature 409,
         *     so an assembly is never left with a dangling instance reference.
         */
        delete: operations["delete_part_api_v1_parts__part_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Part
         * @description Rename and/or re-unit a part (bumps ``tree_version``; uniform 404).
         *
         *     Changing the display unit is a document edit (docs/design/units.md §U1) —
         *     it bumps ``tree_version`` like any header mutation but touches no stored
         *     ``*_mm`` value (storage stays canonical mm). Stale ``expected_tree_version``
         *     is a 422 (mirroring the feature-tree write guard); 409 stays reserved for a
         *     duplicate-name conflict.
         */
        patch: operations["update_part_api_v1_parts__part_id__patch"];
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
    "/api/v1/parts/{part_id}/features/{feature_id}/suppress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Suppress Feature
         * @description Flip ONLY a feature's suppress flag (feature-tree.md §4.3a).
         *
         *     A dedicated, minimal mutation: unlike :func:`update_feature` it never
         *     touches ``params`` (no re-validation, no dependency-edge rewrite) — it sets
         *     the envelope-level ``suppressed`` column and, like every tree write, bumps
         *     ``tree_version`` under the optimistic-concurrency guard (stale → 422) and
         *     records a history snapshot so the toggle is undoable. A suppressed feature
         *     is SKIPPED at rebuild (the evaluation-request marks it, geometry skips it),
         *     so this changes what an evaluation of the part means.
         */
        patch: operations["suppress_feature_api_v1_parts__part_id__features__feature_id__suppress_patch"];
        trace?: never;
    };
    "/api/v1/parts/{part_id}/last-evaluation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Record Last Evaluation
         * @description Record the outcome of an evaluate on the part row (§4.4a bookkeeping).
         *
         *     INTERNAL, like every documents route, and deliberately without a public
         *     gateway twin (the same posture as ``GET /{part_id}/evaluation-request``):
         *     the gateway calls this itself after geometry has answered, so the stored
         *     verdict is derived from what geometry actually said and is never a claim a
         *     browser could POST about its own health.
         *
         *     Three guards make the record honest rather than merely present:
         *
         *     - **Monotonic in ``tree_version``.** A late write for an older version is a
         *       clean no-op (200, record unchanged), so two concurrent evaluates cannot
         *       resurrect a superseded verdict.
         *     - **``last_eval_at`` is documents' clock**, never the caller's — one clock
         *       orders every record.
         *     - **``updated_at`` does NOT move**, and neither does ``tree_version``: this
         *       is bookkeeping, not a document edit. Opening a part triggers an evaluate,
         *       and a register that showed "last worked: just now" because someone LOOKED
         *       at a part would be lying about the thing it exists to report. The column's
         *       ``onupdate`` default is suppressed by naming ``updated_at`` explicitly in
         *       the UPDATE.
         */
        put: operations["record_last_evaluation_api_v1_parts__part_id__last_evaluation_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
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
         * Redo
         * @description Restore the next history snapshot VERBATIM (ids preserved).
         *
         *     Clean no-op at the top of the ring; stale ``expected_tree_version`` → 422.
         */
        post: operations["redo_api_v1_parts__part_id__redo_post"];
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
         * Undo
         * @description Restore the previous history snapshot VERBATIM (ids preserved).
         *
         *     Clean no-op at the baseline; stale ``expected_tree_version`` → 422.
         */
        post: operations["undo_api_v1_parts__part_id__undo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/step-import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create From Step Import
         * @description Materialise a geometry STEP read into an assembly or a single-body part.
         *
         *     Atomic (module docstring): the whole graph commits once or not at all. A
         *     product count over :data:`MAX_IMPORT_ASSEMBLY_PRODUCTS` is a 422
         *     ``import_too_many_products`` (defence-in-depth behind the gateway's own cap);
         *     a read with no solid product is a 422 ``import_no_solid``; a document-name
         *     collision is a 409 (``assembly_name_taken`` / ``part_name_taken``) — all
         *     before any commit, so no orphan documents are left behind.
         */
        post: operations["create_from_step_import_api_v1_step_import_post"];
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
         * AssemblyImportResult
         * @description A STEP that carried product structure became a Loft assembly (SLICE-2b).
         *
         *     ``assembly`` is the freshly-created assembly graph (its N named instances at
         *     their imported placements, ready to render — the same read model every other
         *     assembly route serves). ``part_ids`` are the DEDUPED part documents created:
         *     one per unique ``body_step_id``, so a part occurring twice is ONE id here but
         *     two instances in ``assembly.instances``.
         */
        AssemblyImportResult: {
            /** @description The created assembly with its instances at imported placements */
            assembly: components["schemas"]["AssemblyGraphResponse"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "assembly";
            /**
             * Part Ids
             * @description Deduped part documents created (one per unique body_step_id)
             */
            part_ids: string[];
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
         * ChamferFeature
         * @description ``{"type": "chamfer", "version": 1, "params": {...}}`` envelope.
         */
        ChamferFeature: {
            params: components["schemas"]["ChamferParamsV1"];
            /**
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * @description TOTAL instances INCLUDING the seed; an integer >= 1, at most MAX_PATTERN_COUNT (work bound, audit G2 — over the ceiling is a parse-time 422). `count < 1` is a `pattern_bad_count` rebuild error; `count = 1` is a no-op.
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
         * DrawingBomLine
         * @description One NUMBERED line of a drawing's bill of materials (design §7 BOM).
         *
         *     The shipped assembly :class:`~py_kit.schemas.assemblies.BomLine` (group key +
         *     resolved name + `missing` + quantity, reused VERBATIM — no parallel taxonomy)
         *     plus the one thing a *drawing* adds: the ``item_number`` a balloon stamps.
         *
         *     ``item_number`` is **derived**, not authored: lines are numbered 1..n in the
         *     order each referenced document FIRST appears in the assembly's stable instance
         *     ``order_index``. It is therefore a pure function of the assembly graph — two
         *     reads of an unchanged assembly number identically, and a part RENAME (which
         *     re-sorts the name-ordered assembly BOM) leaves every number untouched.
         */
        DrawingBomLine: {
            /**
             * Item Number
             * @description 1-based item number, DERIVED from the assembly's stable instance order (first appearance of this referenced document) — never stored on the drawing, so it can never drift from the assembly
             */
            item_number: number;
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
         * DrawingBomResponse
         * @description A drawing sheet's bill of materials — the item list a balloon numbers (§7).
         *
         *     A pure READ MODEL (no table, no migration): the sheet's single source document
         *     (the enforced one-sheet-one-source invariant, §2.2) must be an ASSEMBLY, and its
         *     DIRECT instances are rolled up into numbered :class:`DrawingBomLine` s. FLAT —
         *     a rigid sub-assembly instance is one ``kind: "assembly"`` line, never expanded
         *     (the same v1 bound the assembly BOM states; recursive/indented is a follow-up).
         *
         *     A sheet drafting a PART has no bill of materials: that is a typed
         *     ``drawing_bom_source_not_assembly`` 422, not a 200 with an empty list — an empty
         *     BOM would read as "this assembly has no parts", which is a different and false
         *     statement (the honest-degradation posture the whole drawings pillar takes).
         *
         *     ``assembly_version`` is the source assembly's ``doc_version`` AT READ TIME. v1
         *     tracks the assembly TIP (§2.3), so this is the staleness handle: a client that
         *     balloons a sheet and later reads a different ``assembly_version`` knows the item
         *     list may have renumbered, without the numbers themselves ever having been stored
         *     and gone quietly wrong.
         */
        DrawingBomResponse: {
            /**
             * Assembly Id
             * Format: uuid
             * @description The assembly this sheet drafts
             */
            assembly_id: string;
            /**
             * Assembly Version
             * @description The source assembly's `doc_version` at read time — the staleness handle for a tip-tracking (unpinned) view, §2.3
             */
            assembly_version: number;
            /**
             * Drawing Id
             * Format: uuid
             */
            drawing_id: string;
            /**
             * Lines
             * @description One numbered line per referenced document, in derived `item_number` order (an assembly with no instances yields an empty list)
             */
            lines?: components["schemas"]["DrawingBomLine"][];
            /**
             * Sheet Id
             * Format: uuid
             * @description The sheet whose source was rolled up
             */
            sheet_id: string;
            /**
             * Total Instances
             * @description Sum of every line's quantity (direct-instance count)
             */
            total_instances: number;
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
            /**
             * Sheets
             * @description The drawing's sheets in order_index order, bounded by MAX_DRAWING_SHEETS (work bound, audit H5 — every drawing read serializes the whole tree). documents refuses to persist past the ceiling (`sheet_limit_exceeded` 422), so the bound can never make a stored drawing unreadable.
             */
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
             * @description The assembly's instances (result order preserved), bounded by MAX_ASSEMBLY_INSTANCES (work bound, audit G2)
             */
            instances: components["schemas"]["EvaluatedInstance"][];
            /**
             * Linear Deflection
             * @description Presentation tessellation parameter (mm), never persisted. Floored at MIN_LINEAR_DEFLECTION (work bound, audit G2).
             * @default 0.1
             */
            linear_deflection: number;
            /**
             * Mates
             * @description The mate graph; processed in order_index order (determinism), bounded by MAX_ASSEMBLY_MATES (work bound, audit G2)
             */
            mates?: components["schemas"]["EvaluatedMate"][];
            /**
             * Version
             * @description Echoed back; cache/correlation key
             */
            version: number;
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
             * @description Ordered prefix (rollback already applied), bounded by MAX_TREE_FEATURES (work bound, audit G2)
             */
            features: components["schemas"]["EvaluatedFeatureInput"][];
            /**
             * Linear Deflection
             * @description Presentation parameter (mm), NEVER persisted per feature (design §8.3). Floored at MIN_LINEAR_DEFLECTION (work bound, audit G2).
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["HoleFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["MirrorFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"];
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
             * @description The part's ordered feature prefix (feature-tree §4 contract), bounded by MAX_TREE_FEATURES (work bound, audit G2)
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
             * Name
             * @description Human-readable instance name ('Bracket <1>'), threaded into the STEP export as the PRODUCT name so a Loft->STEP->Loft round trip preserves part identity instead of writing the instance UUID (FINDINGS #7). Optional: evaluate/interference ignore it; the export path falls back to the instance id when absent (a nameless request stays valid).
             */
            name?: string | null;
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
         * ExtrudeFeature
         * @description ``{"type": "extrude", "version": 1, "params": {...}}`` envelope.
         */
        ExtrudeFeature: {
            params: components["schemas"]["ExtrudeParamsV1"];
            /**
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * @description The planar faces to leave OPEN (each a stage-1 face SubshapeRef resolved against the current body), bounded by MAX_SELECTOR_REFS (work bound, audit G2). EMPTY = a fully-enclosed hollow (no opening) — a valid selection, not a 422 (design decision).
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["HoleFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["MirrorFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"];
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
            feature: components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["HoleFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["MirrorFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"];
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
         * FeatureSuppressRequest
         * @description Toggle ONLY a feature's suppress flag (feature-tree.md §4.3a).
         *
         *     A DEDICATED, minimal mutation — distinct from :class:`FeatureUpdate` — so
         *     suppressing/un-suppressing never touches ``params`` (no re-validation of
         *     the payload, no dependency-edge rewrite): it flips the envelope-level
         *     ``suppressed`` flag and bumps ``tree_version`` under the same
         *     optimistic-concurrency guard as every other write (stale value → 422). A
         *     suppressed feature is SKIPPED at rebuild (the body is built from the
         *     non-suppressed prefix), so this changes what an evaluation of the part
         *     means and is a normal history-recording tree edit (undoable).
         */
        FeatureSuppressRequest: {
            /**
             * Expected Tree Version
             * @description Optimistic-concurrency guard: the tree_version the client last saw; a stale value is rejected 422 (design §1.2)
             */
            expected_tree_version: number;
            /**
             * Suppressed
             * @description New suppress state: True skips the feature at rebuild, False re-includes it (feature-tree.md §4.3a).
             */
            suppressed: boolean;
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
            feature?: (components["schemas"]["DatumFeature"] | components["schemas"]["SketchFeature"] | components["schemas"]["ExtrudeFeature"] | components["schemas"]["RevolveFeature"] | components["schemas"]["SweepFeature"] | components["schemas"]["LoftFeature"] | components["schemas"]["FilletFeature"] | components["schemas"]["ChamferFeature"] | components["schemas"]["ShellFeature"] | components["schemas"]["DraftFeature"] | components["schemas"]["HoleFeature"] | components["schemas"]["PatternFeature"] | components["schemas"]["MirrorFeature"] | components["schemas"]["ImportFeature"] | components["schemas"]["SheetMetalBaseFlangeFeature"] | components["schemas"]["SheetMetalEdgeFlangeFeature"] | components["schemas"]["SheetMetalHemFeature"] | components["schemas"]["SheetMetalCornerReliefFeature"] | components["schemas"]["BooleanFeature"]) | null;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
         * HoleBlindDepth
         * @description A blind hole drilled ``depth_mm`` into the material (``kind: "blind"``).
         *
         *     ``depth_mm`` is measured from the placement face INTO the solid along the
         *     (inward) drill axis. A depth that exceeds the available material — the drill
         *     would break through the far side — is a per-feature ``hole_too_deep`` rebuild
         *     error (use a through-all hole instead), never a silently wrong body.
         */
        HoleBlindDepth: {
            /**
             * Depth Mm
             * @description Depth of the blind hole from the face into the material (mm)
             */
            depth_mm: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "blind";
        };
        /**
         * HoleCounterbore
         * @description A larger coaxial CYLINDRICAL recess at the face (``kind: "counterbore"``).
         *
         *     Seats a socket-head cap screw: a flat-bottomed cylinder of
         *     ``cbore_diameter_mm`` sunk ``cbore_depth_mm`` from the placement face, coaxial
         *     with the bore, subtracted ALONGSIDE the bore. The recess diameter must exceed
         *     the bore ``diameter_mm`` and its depth must fit within the body's thickness —
         *     an invalid recess degrades to a typed ``hole_cbore_invalid`` (diameter) /
         *     ``hole_too_deep`` (depth) rebuild error, never a raise or a silently wrong
         *     body (the never-500 posture the simple hole already holds).
         */
        HoleCounterbore: {
            /**
             * Cbore Depth Mm
             * @description Depth of the counterbore recess from the face into the material (mm); must fit the body thickness (a `hole_too_deep` otherwise)
             */
            cbore_depth_mm: number;
            /**
             * Cbore Diameter Mm
             * @description Counterbore recess diameter (mm); must EXCEED the bore `diameter_mm` (a `hole_cbore_invalid` rebuild error otherwise)
             */
            cbore_diameter_mm: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "counterbore";
        };
        /**
         * HoleCountersink
         * @description A coaxial CONICAL recess at the face (``kind: "countersink"``).
         *
         *     Seats a flat-head screw: a truncated cone — ``csink_diameter_mm`` wide at the
         *     surface, tapering at the ``csink_angle_deg`` INCLUDED angle (82° and 90° are
         *     the fastener standards) down to the bore diameter — subtracted alongside the
         *     bore. The mouth diameter must exceed the bore ``diameter_mm`` and the cone
         *     depth the angle implies must fit the body — an invalid recess degrades to a
         *     typed ``hole_csink_invalid`` (diameter) / ``hole_too_deep`` (depth) rebuild
         *     error, never a raise.
         */
        HoleCountersink: {
            /**
             * Csink Angle Deg
             * @description INCLUDED cone angle (degrees); 82 and 90 are the flat-head fastener standards. The cone tapers from the mouth diameter down to the bore diameter over a depth the angle implies.
             */
            csink_angle_deg: number;
            /**
             * Csink Diameter Mm
             * @description Countersink mouth diameter at the face surface (mm); must EXCEED the bore `diameter_mm` (a `hole_csink_invalid` otherwise)
             */
            csink_diameter_mm: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "countersink";
        };
        /**
         * HoleFeature
         * @description ``{"type": "hole", "version": 1, "params": {...}}`` envelope.
         *
         *     A body-MODIFYING feature (design §7.6): it drills a cylinder into the current
         *     body at a point on a picked planar face (through-all or blind). ``params`` is
         *     :class:`HoleParamsV1`.
         */
        HoleFeature: {
            params: components["schemas"]["HoleParamsV1"];
            /**
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "hole";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * HoleParamsV1
         * @description A face-placed cylindrical hole — through-all or blind, plain or recessed.
         *
         *     The dedicated Hole feature (BACKLOG P2): drill a straight cylinder of
         *     ``diameter_mm`` into the current body at ``position`` on the planar ``face``,
         *     cutting INTO the material (opposite the face's outward normal — the correct
         *     direction, chosen automatically, no direction knob to get wrong). Like a
         *     fillet/shell/draft it modifies the implicit single body chain (design §7.6),
         *     so it carries no whole-feature ``FeatureRef`` — its dependency on the prior
         *     body-affecting feature is tree order. The placement face IS a named reference,
         *     though: ``face`` is the SAME stage-1 planar-face :class:`SubshapeRef` the
         *     ``on_face`` datum / shell openings resolve, so it materialises into
         *     ``feature_dependencies`` (deleting that body feature is a 409-with-dependents;
         *     a reorder re-checks strict-backward).
         *
         *     ``position`` is a WORLD-space point; the geometry service projects it onto the
         *     resolved face plane to fix the drill axis (a pick that lands a hair off-plane
         *     still drills clean and perpendicular). A point that projects OUTSIDE the body
         *     — or a resolved direction into empty space — removes no material and is a
         *     ``hole_off_body`` rebuild error, never a silent no-op.
         *
         *     ``depth`` is a :data:`HoleDepth`: ``through_all`` cuts fully through;
         *     ``blind`` drills a ``depth_mm`` pocket. A blind depth that exceeds the
         *     available material is ``hole_too_deep``. A non-planar / missing / congruent
         *     face reference degrades exactly as the ``on_face`` datum does
         *     (``subshape_unresolved`` / ``subshape_ambiguous``) — planar faces only carry a
         *     signature, so a non-planar pick cannot be authored.
         *
         *     ``type`` is a :data:`HoleType`: ``simple`` (the default when omitted — the
         *     slice-1 plain bore) or a bore PLUS a coaxial recess at the face —
         *     ``counterbore`` (a larger cylinder) or ``countersink`` (a cone). A recess
         *     whose diameter does not exceed the bore is ``hole_cbore_invalid`` /
         *     ``hole_csink_invalid``; a recess deeper than the material is ``hole_too_deep``.
         *
         *     ``thread`` (optional, ``None`` = an untapped hole) makes the hole TAPPED: a
         *     cosmetic :class:`IsoMetricThread` callout over the tap-drill bore, ORTHOGONAL
         *     to ``type`` (a counterbored tapped hole sets both). It adds NO geometry — the
         *     solid is byte-identical to the same hole without it — so a tapped hole
         *     mirrors, patterns, shells and exports exactly as its bore does. An unknown
         *     designation is ``hole_thread_unsupported``; a bore the thread cannot be tapped
         *     in is ``hole_thread_mismatch``.
         */
        HoleParamsV1: {
            /**
             * Depth
             * @description Through-all, or a blind pocket depth (:data:`HoleDepth`)
             */
            depth: components["schemas"]["HoleThroughAll"] | components["schemas"]["HoleBlindDepth"];
            /**
             * Diameter Mm
             * @description Hole diameter (mm)
             */
            diameter_mm: number;
            /** @description Planar face of an earlier body-affecting feature to drill into (the SAME stage-1 signature reference the on_face datum uses) */
            face: components["schemas"]["SubshapeRef"];
            /** @description World-space placement point, projected onto the face plane to fix the drill axis (mm) */
            position: components["schemas"]["Vec3"];
            /** @description Optional COSMETIC thread callout making this a TAPPED hole (`null`/omitted = untapped). Carries the designation for drawing/BOM callouts; adds no geometry — `diameter_mm` is the tap-drill bore (:class:`IsoMetricThread`) */
            thread?: components["schemas"]["IsoMetricThread"] | null;
            /**
             * Type
             * @description Hole type: a plain bore (`simple`, the default when omitted — slice-1 behaviour) or a bore plus a coaxial counterbore / countersink recess at the face (:data:`HoleType`)
             */
            type?: components["schemas"]["HoleSimple"] | components["schemas"]["HoleCounterbore"] | components["schemas"]["HoleCountersink"];
        };
        /**
         * HoleSimple
         * @description A plain straight drilled hole — no recess (``kind: "simple"``, the default).
         *
         *     The slice-1 shape: the bore alone (``diameter_mm`` + the through-all|blind
         *     ``depth``), with no counterbore/countersink recess at the face. ``kind``
         *     DEFAULTS to ``"simple"`` so a legacy :class:`HoleParamsV1` that carries NO
         *     ``type`` validates unchanged — the discriminated :data:`HoleType` is a purely
         *     ADDITIVE member (NO ``param_version`` bump; the RevolveAxis / DatumParams
         *     idiom).
         */
        HoleSimple: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "simple";
        };
        /**
         * HoleThroughAll
         * @description A hole that cuts fully THROUGH the body (``kind: "through_all"``).
         *
         *     No depth to specify — the drill clears the body on both sides regardless of
         *     the local wall thickness (the geometry service spans the bounding box). The
         *     default ``kind`` makes ``{"kind": "through_all"}`` explicit while a future
         *     additive depth mode joins the discriminated union without a bump.
         */
        HoleThroughAll: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "through_all";
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
         * ImportAssemblyRequest
         * @description documents-side request: materialise a geometry read into Loft documents.
         *
         *     ``result`` is the geometry service's structured read (forwarded verbatim by
         *     the gateway); ``name`` is the caller-chosen name for the created document —
         *     the assembly name (``has_assembly_structure=True``) or the single part's name
         *     (the MB-4b fallback). Each product's editable body — resolved from the read's
         *     shared ``bodies`` map by ``body_step_id`` — seeds a part's ``import`` feature
         *     (:class:`~py_kit.schemas.features.ImportParamsV1` — ZERO new ingest path),
         *     products sharing a ``body_step_id`` collapse to ONE part with N instances, and
         *     the whole graph is created atomically (all-or-nothing — a failure leaves no
         *     orphan docs).
         */
        ImportAssemblyRequest: {
            /**
             * Name
             * @description Name for the created document — the assembly's name (product structure present) or the single part's name (single-body fallback)
             */
            name: string;
            /** @description The geometry service's structured read of the uploaded STEP */
            result: components["schemas"]["StepAssemblyImportResult"];
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
         * ImportedProduct
         * @description One product recovered from an assembly STEP — name + placement + body.
         *
         *     ``name`` is the STEP PRODUCT name (``None`` when the file names no product —
         *     the caller supplies a fallback instance name). ``placement`` is the
         *     product's WORLD pose (reusing :class:`~py_kit.schemas.assemblies.Placement` —
         *     identity for a flat single-body STEP), matched to the exported placement
         *     within the kernel round-trip tolerance.
         *
         *     Two body surfaces, both referenced by CONTENT ADDRESS and SHARED across
         *     repeated occurrences of one part (the dedup contract, as slice 1 does for
         *     meshes) — neither is inlined per occurrence:
         *
         *     * ``body_step_id`` — the address (``sha256:<hex>``) of the product's editable
         *       **LOCAL-frame B-rep**: a STEP AP214 part-21 fragment with the instance
         *       placement STRIPPED (that is ``placement``, kept separate), stored ONCE under
         *       this key in :attr:`StepAssemblyImportResult.bodies`. The text is exactly what
         *       the single-body ``import`` feature ingests
         *       (:class:`~py_kit.schemas.features.ImportParamsV1` ``data``), so the documents
         *       service seeds each part with ``ImportParamsV1(data=<resolved body>)`` — ZERO
         *       new ingest path. A mesh is not editable geometry; this is what lets 2b build
         *       a REAL part per instance. ``None`` when the product produced no solid.
         *       Because the id is EQUAL for two occurrences of one part, the caller groups
         *       products by it to create ONE stored B-rep (one part) with N instances.
         *     * ``mesh_glb_id`` — a content-addressed presentation mesh for the viewport.
         *
         *     ``properties`` are the body's OWN (local-frame) mass properties for BOM /
         *     inspection.
         *
         *     ``body_step`` is a PRODUCER-SIDE construction convenience only: a producer may
         *     pass the body text alongside the product and the parent result hoists it into
         *     its shared ``bodies`` map (so the geometry reader needs no separate bookkeeping),
         *     but the field is NEVER serialized — the wire form carries each body once.
         *     Consumers MUST resolve through
         *     :meth:`StepAssemblyImportResult.body_step_for`.
         */
        ImportedProduct: {
            /**
             * Body Step
             * @description Producer-side convenience: the product's LOCAL-frame B-rep as a STEP AP214 part-21 fragment. NOT serialized — the parent result hoists it into its shared `bodies` map so the transport carries each body once; consumers resolve via StepAssemblyImportResult.body_step_for().
             */
            body_step?: string | null;
            /**
             * Body Step Id
             * @description Content address (sha256:<hex>) of this product's LOCAL-frame B-rep, whose text lives ONCE under this key in the result's `bodies` map. EQUAL across repeated occurrences of one part, so the caller creates ONE part and N instances (the dedup key, as meshes share mesh_glb_id). Null when the product produced no solid.
             */
            body_step_id?: string | null;
            /**
             * Mesh Glb Id
             * @description Content-addressed shared presentation mesh (sha256:<hex>), or null when the product produced no mesh
             */
            mesh_glb_id: string | null;
            /**
             * Name
             * @description STEP PRODUCT name, or null when the file names no product
             */
            name: string | null;
            /** @description World placement of this product (identity for a flat STEP) */
            placement: components["schemas"]["Placement"];
            /** @description The product body's own (local-frame) mass properties */
            properties?: components["schemas"]["ShapeProperties"] | null;
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
         * IsoMetricThread
         * @description An ISO 261 metric thread callout on a hole (``standard: "iso_metric"``).
         *
         *     The COSMETIC thread representation: the kernel cuts the tap-drill bore only
         *     (``diameter_mm``) and carries this designation as metadata for drawing/BOM/
         *     export callouts — it does NOT model helical geometry (decision + rationale +
         *     the upgrade path in ``geometry.kernel.threads``). ``standard`` is required so
         *     a future thread standard (UNC/UNF, NPT) joins as a discriminated union member
         *     without a ``param_version`` bump.
         *
         *     The pair (``nominal_diameter_mm``, ``pitch_mm``) must be a real ISO 261
         *     combination — M10 x 1.5 (coarse) or M10 x 1.25/1/0.75 (fine), say — and the
         *     hole's ``diameter_mm`` must be a hole the tap can actually cut, i.e. within
         *     ``[D - 1.0825*P, D)``. The ISO recommended tap drill is ``D - P`` (5.0 mm for
         *     M6 x 1, 8.5 mm for M10 x 1.5 — the published tables' values). Violations are
         *     the typed rebuild errors ``hole_thread_unsupported`` / ``hole_thread_mismatch``
         *     — never a silent fallback to an untapped hole.
         */
        IsoMetricThread: {
            /**
             * Nominal Diameter Mm
             * @description Nominal (major) thread diameter — the `M` number, mm: 10.0 for M10x1.5. Must be an ISO 261 size (a `hole_thread_unsupported` rebuild error otherwise)
             */
            nominal_diameter_mm: number;
            /**
             * Pitch Mm
             * @description Thread pitch (mm): 1.5 for M10x1.5. Must be a standard pitch for that nominal diameter (a `hole_thread_unsupported` otherwise)
             */
            pitch_mm: number;
            /**
             * Standard
             * @constant
             */
            standard: "iso_metric";
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
             * @description TOTAL instances INCLUDING the seed (instance 0); an integer >= 1, at most MAX_PATTERN_COUNT (work bound, audit G2 — over the ceiling is a parse-time 422). `count < 1` is a `pattern_bad_count` rebuild error; `count = 1` is a no-op (the body is unchanged).
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * @description Ordered earlier sketch features (>= 2, bounded by MAX_LOFT_SECTIONS — work bound, audit G2) to blend through; each forms a single closed profile wire or a single apex point (design §2.2). Fewer than 2 is a request-validation 422.
             */
            profiles: components["schemas"]["FeatureRef"][];
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
         * MirrorBodyScope
         * @description ``scope: {"kind": "body"}`` — reflect the CURRENT BODY (the v1 reading).
         *
         *     The v1 semantic, NAMED rather than implied (design §3.1): the mirror reflects
         *     the body that exists at its point in the tree, cut-aware — when the active body
         *     carries a recorded cut whose reflected tool still reaches it the mirror reflects
         *     that REMOVAL, otherwise it reflects and unions the whole body. Kept verbatim
         *     (§6.1): the shipped goldens' byte identity is STRUCTURAL, not measured, because
         *     this scope dispatches to code the v2 work did not touch.
         */
        MirrorBodyScope: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "body";
        };
        /**
         * MirrorFeature
         * @description ``{"type": "mirror", "version": 1, "params": {...}}`` envelope.
         *
         *     A body-affecting feature (design §7.6): it reflects the current body about a
         *     plane and boolean-unions the reflection into the single body chain — the
         *     reflective sibling of :class:`PatternFeature`. ``params`` is
         *     :class:`MirrorParamsV1`.
         */
        MirrorFeature: {
            params: components["schemas"]["MirrorParamsV1"];
            /**
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "mirror";
            /**
             * Version
             * @constant
             */
            version: 1;
        };
        /**
         * MirrorFeaturesScope
         * @description ``scope: {"kind": "features", "features": [...]}`` — reflect these features.
         *
         *     The v2 reading (design §2b/§4): each selected feature's RECORDED RIGID TOOL
         *     SOLID(S) are reflected about the plane and that feature's OWN operation
         *     (``fuse``/``cut``) is re-applied to the active body, in TREE order — never array
         *     order (§8.1: array order is UI-incidental, so honouring it would make identical
         *     models tessellate to different bytes). Parameters are never re-derived: a
         *     reflected circular pattern is correct precisely because its PLACEMENTS are
         *     reflected, where re-deriving the axis would wind the ring backwards (§4.5).
         *
         *     ``features`` names :class:`FeatureRef`s rather than bare UUIDs so each selection
         *     materialises into ``feature_dependencies`` for free (feature-tree §2.3): deleting
         *     a mirrored feature is a 409-with-dependents, a reorder re-checks the
         *     strict-backward rule, and a forward/self reference is a write-time 422. A
         *     non-body-affecting or non-reflectable kind (``sketch``/``datum``, and every
         *     MODIFIER — fillet/chamfer/shell/draft and the sheet-metal family, which have a
         *     RESULT and no tool, §4.3) is refused with the typed per-feature
         *     ``mirror_feature_unsupported`` at rebuild.
         *
         *     ``min_length=1`` because an empty selection is authoring nonsense, not a no-op
         *     mirror (§3.1), and duplicate ids are a 422 rather than silently deduplicated —
         *     naming a feature twice leaves the intent (twice? once?) unstated, which is the
         *     mistake v1 made.
         */
        MirrorFeaturesScope: {
            /**
             * Features
             * @description The features to reflect, each a `FeatureRef` to an earlier body-affecting feature of this tree. Applied in TREE order (the array order is ignored — design §8.1); at least one, at most MAX_MIRROR_SCOPE_FEATURES (work bound); duplicates are a 422.
             */
            features: components["schemas"]["FeatureRef"][];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "features";
        };
        /**
         * MirrorParamsV1
         * @description Reflect the current body about a plane and union the reflection in.
         *
         *     The mirror feature (BACKLOG P2): a whole-body reflection about ``plane``,
         *     boolean-unioned into the single body chain (design §7.6) — the reflective
         *     sibling of the ADD pattern (see the module note for the shared "replicate the
         *     current body + union" semantics). Like a fillet/chamfer/pattern it carries NO
         *     source ``FeatureRef``: it mirrors the implicit body chain that exists at its
         *     point in the tree, so its dependency on the prior body-affecting feature is
         *     tree order.
         *
         *     ``plane`` is a :data:`GeomRef` — the SAME plane reference a sketch uses (no
         *     new plane taxonomy, DRY): a :class:`DatumPlaneRef` (an origin datum XY/XZ/YZ)
         *     or a :class:`FeatureRef` to an earlier ``datum`` feature (an offset / on-face
         *     / midplane plane). A ``FeatureRef`` that does not resolve to a ``datum`` of
         *     this prefix is a write-time 422 (the eval-time backstop is
         *     ``reference_unresolved``, pinned to the referenced feature).
         *
         *     The reflection is a true handedness-reversing isometry, NOT a translation
         *     (proven by the ``mirror-triangle-prism-2x`` golden). It handles every case
         *     sanely: a body that CLEARS the plane mirrors to a disjoint TWO-lump body
         *     (volume ``2V``); an OVERLAPPING reflection merges to one solid; a SYMMETRIC
         *     body is unchanged. A degenerate/failed reflection is a per-feature
         *     ``mirror_failed`` rebuild error; a mirror with no prior body is
         *     ``no_target_body`` — never a silently wrong body.
         *
         *     ``scope`` (v2, design §3) states WHAT is reflected — the whole ``body`` (the
         *     reading above, kept verbatim) or an explicit selection of ``features``. It
         *     defaults to ``body`` and a persisted params blob with no ``scope`` key reads as
         *     ``body`` (:meth:`_legacy_body_scope`), so every mirror authored before v2
         *     evaluates on unchanged code.
         */
        MirrorParamsV1: {
            /**
             * Plane
             * @description Mirror plane — an origin datum (XY/XZ/YZ `DatumPlaneRef`) or an earlier `datum` feature (`FeatureRef`); the SAME plane vocabulary a sketch uses (discriminated on `kind`)
             */
            plane: components["schemas"]["DatumPlaneRef"] | components["schemas"]["FeatureRef"];
            /**
             * Scope
             * @description WHAT to reflect (discriminated on `kind`): `body` reflects the current body (the v1 reading — cut-aware, with the reflect-and-union fallback), `features` reflects the recorded tool solids of an explicit tree-ordered selection and re-applies each feature's own boolean. Absent reads `body`, so pre-v2 mirrors are unchanged (design §3.2).
             */
            scope?: components["schemas"]["MirrorBodyScope"] | components["schemas"]["MirrorFeaturesScope"];
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
         * PartEvaluationRecord
         * @description Record the outcome of an evaluate onto the part row (§4.4a bookkeeping).
         *
         *     Written by the GATEWAY — the only place that holds both the verified
         *     principal and geometry's actual answer — after a real evaluate returned, so
         *     the value on a register can never be a browser's claim about its own health.
         *     The client never supplies a timestamp: documents stamps ``last_eval_at``
         *     from its own clock, so one clock orders every record.
         *
         *     ``tree_version`` is the version of the tree the result BELONGS to (echoed
         *     through :class:`~py_kit.schemas.features.EvaluateTreeResult`), which is what
         *     makes staleness derivable instead of assumed. Recording is monotonic in it:
         *     a late-arriving write for an older version is a no-op, never a resurrection
         *     of a superseded claim.
         */
        PartEvaluationRecord: {
            /**
             * Status
             * @description 'failed' when any evaluated feature returned an error, else 'ok' (feature-tree.md §4.3 strict-prefix rule)
             * @enum {string}
             */
            status: "ok" | "failed";
            /**
             * Tree Version
             * @description The part tree_version this result was computed from (EvaluateTreeResult.tree_version); older-than-stored is ignored
             */
            tree_version: number;
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
         * @description A part as stored — identity, ownership, unit, timestamps, rebuild health.
         *
         *     The feature tree itself is not inlined here (it is its own
         *     ``GET /parts/{id}/features`` response, docs/design/feature-tree.md); what
         *     IS here is the fixed-size last-evaluate record (§4.4a) so a register can
         *     tell the truth about a whole drawer of parts in one query — four scalars per
         *     row, never per-feature or per-sheet growth.
         */
        PartResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Eval State
             * @description Rebuild health a consumer may act on NOW: 'never' (not evaluated), 'ok'/'failed' (evaluated, and that verdict still applies to the current tree), or 'stale' (evaluated, but the tree changed since — status unknown). Derived server-side from the three last_eval_* fields against the part's current tree_version (feature-tree.md §4.4a), so a stale claim is never dressed up as a current one.
             * @enum {string}
             */
            eval_state: "never" | "ok" | "failed" | "stale";
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Last Eval At
             * @description When that evaluate was recorded (documents' clock); null if never evaluated. For display ('failed 20 min ago'), NOT for deciding staleness.
             */
            last_eval_at: string | null;
            /**
             * Last Eval Status
             * @description Raw recorded outcome of the last evaluate, or null if the part was never evaluated. Read `eval_state` for the verdict — this field alone cannot say whether it still applies.
             */
            last_eval_status: ("ok" | "failed") | null;
            /**
             * Last Eval Tree Version
             * @description The tree_version the recorded status describes; null if never evaluated. Differs from the part's current tree_version exactly when `eval_state` is 'stale'.
             */
            last_eval_tree_version: number | null;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * @description The specific picked edges (>= 1, bounded by MAX_SELECTOR_REFS — work bound, audit G2), each a stage-1 EdgeSignature reference resolved against the current body
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
         * SingleBodyImportResult
         * @description A flat STEP became a single-body part — the MB-4b fallback (SLICE-2b).
         *
         *     Backward-compatible with the pre-assembly import: one part document seeded
         *     with the ``import`` base feature, no assembly. ``tree_version`` is the part's
         *     post-import concurrency token (1 — the single import feature).
         */
        SingleBodyImportResult: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "part";
            /** @description The created single-body part */
            part: components["schemas"]["PartResponse"];
            /**
             * Tree Version
             * @description The part's concurrency token after the import feature (== 1)
             */
            tree_version: number;
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
            /**
             * Constraints
             * @description The sketch's constraints, bounded by MAX_SKETCH_CONSTRAINTS (work bound, audit G2)
             */
            constraints: (components["schemas"]["CoincidentConstraint"] | components["schemas"]["HorizontalConstraint"] | components["schemas"]["VerticalConstraint"] | components["schemas"]["DistanceConstraint"] | components["schemas"]["RadiusConstraint"] | components["schemas"]["FixedConstraint"] | components["schemas"]["ParallelConstraint"] | components["schemas"]["PerpendicularConstraint"] | components["schemas"]["TangentConstraint"] | components["schemas"]["EqualConstraint"] | components["schemas"]["SymmetricConstraint"] | components["schemas"]["ConcentricConstraint"])[];
            /**
             * Entities
             * @description The sketch's entities, bounded by MAX_SKETCH_ENTITIES (work bound, audit G2)
             */
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
             * @description Ordered fit points (mm) the curve interpolates through; at least two, at most MAX_SPLINE_POINTS (work bound, audit G2). Consecutive points must be distinct (a coincident pair is a degenerate spline, rejected at profile build).
             */
            points: components["schemas"]["Point2D"][];
        };
        /**
         * StepAssemblyImportResult
         * @description Structured read of an assembly STEP — products + the shared body map.
         *
         *     ``has_assembly_structure`` is True when the file carried
         *     ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` product structure (multiple positioned,
         *     named products); False for a flat / single-body STEP, whose single product
         *     signals the caller to fall back to the single-body MB-4b import (backward
         *     compatible). ``products`` are in the deterministic order the geometry service
         *     walks the product tree (RESEARCH §9) and reference their editable B-rep by
         *     ``body_step_id``; ``bodies`` holds each distinct B-rep exactly ONCE, keyed by
         *     that address, so a part instanced N times ships its (possibly multi-MB) STEP
         *     fragment once instead of N times.
         */
        StepAssemblyImportResult: {
            /**
             * Bodies
             * @description Each distinct product body ONCE: content address (sha256:<hex>, == a product's body_step_id) -> its LOCAL-frame STEP AP214 part-21 fragment (placement stripped). A part instanced N times appears here once; resolve a product's body by its body_step_id.
             */
            bodies?: {
                [key: string]: string;
            };
            /**
             * Has Assembly Structure
             * @description True when the file carried NAUO product structure; False for a flat / single-body STEP (fall back to single-body import)
             */
            has_assembly_structure: boolean;
            /**
             * Products
             * @description Recovered products, in deterministic product-tree order
             */
            products: components["schemas"]["ImportedProduct"][];
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
             * Suppressed
             * @description Feature suppress flag: when True a tree rebuild SKIPS this feature and downstream features rebuild off the last non-suppressed body (BACKLOG feature suppress). Additive-optional — absent reads False, no param_version bump.
             */
            suppressed?: boolean;
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
             * Auto Place
             * @description Placement mode (drawing-export.md §4.2, mirrors :class:`SheetViewPlacement`): True (default) = the composer DERIVES the anchor (bounds-aware auto-layout), so `position` rides along for persistence but does not drive anchoring; False = the composer HONORS `position` verbatim (the drag-to-place seam). Additive — an omitted value keeps the auto-layout behaviour byte-identical.
             * @default true
             */
            auto_place: boolean;
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
             * Auto Place
             * @description Placement mode (mirrors :class:`SheetViewPlacement`): True (default) = the composer auto-places (bounds-aware); False = a persisted drag-to-place position the composer honors verbatim. Survives reload — the compose/export path threads it into `SheetViewPlacement.auto_place`.
             * @default true
             */
            auto_place: boolean;
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
             * Auto Place
             * @description Placement mode (mirrors :class:`SheetViewPlacement`): set False to PERSIST a dragged position so the composer honors `position` verbatim (the drag-to-place seam — typically sent alongside `position`); set True to return the view to bounds-aware auto-layout. Null (default) leaves the mode unchanged. At least one of the update fields must be provided.
             */
            auto_place?: boolean | null;
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
                    "application/json": components["schemas"]["AssemblyListResponse"];
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
    create_assembly_api_v1_assemblies_post: {
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
    get_assembly_evaluation_request_api_v1_assemblies__assembly_id__evaluation_request_get: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
                    "application/json": components["schemas"]["EvaluateAssemblyRequest"];
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
                /** @description Optimistic-concurrency guard (design §1.2) */
                expected_version: number;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
                /** @description Optimistic-concurrency guard (design §1.2) */
                expected_version: number;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
    redo_api_v1_assemblies__assembly_id__redo_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
    undo_api_v1_assemblies__assembly_id__undo_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
    list_drawings_api_v1_drawings_get: {
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
                    "application/json": components["schemas"]["DrawingListResponse"];
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
    create_drawing_api_v1_drawings_post: {
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
                /** @description Optimistic-concurrency guard (design §2.1) */
                expected_version: number;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
    get_drawing_bom_api_v1_drawings__drawing_id__bom_get: {
        parameters: {
            query?: {
                /** @description Which sheet to bill (a sheet id from the drawing tree); omit to bill the FIRST sheet, the same default the compose/export routes take. An unknown/foreign id is a `sheet_not_found` 404. */
                sheet?: string | null;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
                    "application/json": components["schemas"]["DrawingBomResponse"];
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
                /** @description Optimistic-concurrency guard (design §2.1) */
                expected_version: number;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
    create_sheet_api_v1_drawings__drawing_id__sheets_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
                /** @description Optimistic-concurrency guard (design §2.1) */
                expected_version: number;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
                /** @description Optimistic-concurrency guard (design §2.1) */
                expected_version: number;
            };
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
            header?: {
                /** @description Authenticated user id, forwarded by the gateway (documents is internal and trusts this header). */
                "X-Loft-User"?: string | null;
            };
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
    update_part_api_v1_parts__part_id__patch: {
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
    suppress_feature_api_v1_parts__part_id__features__feature_id__suppress_patch: {
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
                "application/json": components["schemas"]["FeatureSuppressRequest"];
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
    record_last_evaluation_api_v1_parts__part_id__last_evaluation_put: {
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
                "application/json": components["schemas"]["PartEvaluationRecord"];
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
    redo_api_v1_parts__part_id__redo_post: {
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
    undo_api_v1_parts__part_id__undo_post: {
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
    create_from_step_import_api_v1_step_import_post: {
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
                "application/json": components["schemas"]["ImportAssemblyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssemblyImportResult"] | components["schemas"]["SingleBodyImportResult"];
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
