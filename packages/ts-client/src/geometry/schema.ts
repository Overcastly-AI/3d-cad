// GENERATED — do not edit; run `just gen`.
// Types for the geometry service (source contract: packages/contracts/geometry.openapi.json).
export interface paths {
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
            params: components["schemas"]["BoxParams"];
            /**
             * Shape
             * @description Shape kind (parametric box only, today)
             * @constant
             */
            shape: "box";
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
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
            params: components["schemas"]["BoxParams"];
            /**
             * Shape
             * @description Shape kind (parametric box only, today)
             * @constant
             */
            shape: "box";
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
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
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
