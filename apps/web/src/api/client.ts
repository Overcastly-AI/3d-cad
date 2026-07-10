/**
 * The one gateway client instance for the app — typed by the generated
 * `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule).
 * Same-origin in dev (Vite proxies /api to the gateway) and in prod.
 */
import { createGatewayClient } from "@loft/ts-client/gateway";

export const gatewayClient = createGatewayClient({ baseUrl: "/" });

/**
 * Mesh quality used for BOTH the viewport tessellation and STL export, so
 * the exported facets are exactly what the screen shows (mm / rad).
 */
export const MESH_LINEAR_DEFLECTION_MM = 0.1;
export const MESH_ANGULAR_DEFLECTION_RAD = 0.1;
