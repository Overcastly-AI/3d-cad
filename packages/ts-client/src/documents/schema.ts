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
         *     Once features exist this gains the design doc's 409-with-dependents
         *     pre-check (docs/design/feature-tree.md §2.3); today a part has no
         *     dependents, so deletion is unconditional.
         */
        delete: operations["delete_part_api_v1_parts__part_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
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
}
