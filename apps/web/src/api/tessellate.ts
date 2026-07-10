/**
 * Gateway data layer — all types come from the generated `@loft/ts-client`
 * (pydantic → OpenAPI → TS; CLAUDE.md DRY rule). No hand-written API types.
 */
import { createGatewayClient } from "@loft/ts-client/gateway";
import type { components } from "@loft/ts-client/gateway";

export type BoxParams = components["schemas"]["BoxParams"];
export type TessellationMetadata =
  components["schemas"]["TessellationMetadata"];
export type ShapeProperties = components["schemas"]["ShapeProperties"];
export type Vec3 = components["schemas"]["Vec3"];

/**
 * Deliberate cross-language duplicate (HTTP header names don't flow through
 * the OpenAPI-generated types). Source of truth: `PROPERTIES_HEADER` in
 * `packages/py-kit/src/py_kit/schemas/geometry.py` — change both together.
 * Drift is loud, not silent: `parsePropertiesHeader` throws when the header
 * is absent, so a renamed server header fails the first tessellation (and
 * the e2e happy path) instead of quietly dropping mass properties.
 */
export const PROPERTIES_HEADER = "X-Loft-Properties";

/** Same-origin in dev (Vite proxies /api to the gateway) and in prod. */
const client = createGatewayClient({ baseUrl: "/" });

export interface TessellationResult {
  /** Binary glTF payload, ready for GLTFLoader.parseAsync. */
  glb: ArrayBuffer;
  /** Mass properties + mesh stats from the X-Loft-Properties header. */
  meta: TessellationMetadata;
}

const isFinite_ = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);

const isVec3 = (v: unknown): v is Vec3 => {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return isFinite_(o.x) && isFinite_(o.y) && isFinite_(o.z);
};

/**
 * Runtime guard for the generated TessellationMetadata type — validation
 * only; the shape itself is defined once, in the generated client.
 */
function isTessellationMetadata(v: unknown): v is TessellationMetadata {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  const props = o.properties as Record<string, unknown> | undefined;
  const mesh = o.mesh as Record<string, unknown> | undefined;
  if (typeof props !== "object" || props === null) return false;
  if (typeof mesh !== "object" || mesh === null) return false;
  const bbox = props.bounding_box as Record<string, unknown> | undefined;
  const topo = props.topology as Record<string, unknown> | undefined;
  return (
    isFinite_(props.volume) &&
    isFinite_(props.surface_area) &&
    isVec3(props.centroid) &&
    typeof bbox === "object" &&
    bbox !== null &&
    isVec3(bbox.min) &&
    isVec3(bbox.max) &&
    typeof topo === "object" &&
    topo !== null &&
    isFinite_(topo.faces) &&
    isFinite_(topo.edges) &&
    isFinite_(topo.shells) &&
    isFinite_(mesh.triangles) &&
    isFinite_(mesh.vertices) &&
    isFinite_(mesh.glb_bytes)
  );
}

/** Parse the X-Loft-Properties response header into typed metadata. */
export function parsePropertiesHeader(
  raw: string | null,
): TessellationMetadata {
  if (raw === null || raw.trim() === "") {
    throw new Error(
      `Tessellation response is missing the ${PROPERTIES_HEADER} header`,
    );
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(`${PROPERTIES_HEADER} header is not valid JSON`);
  }
  if (!isTessellationMetadata(parsed)) {
    throw new Error(
      `${PROPERTIES_HEADER} header does not match TessellationMetadata`,
    );
  }
  return parsed;
}

/** Request a server-side tessellation of a parametric box via the gateway. */
export async function tessellateBox(
  params: BoxParams,
): Promise<TessellationResult> {
  const { data, error, response } = await client.POST(
    "/api/v1/geometry/tessellate",
    {
      body: { shape: "box", params, linear_deflection: 0.1 },
      parseAs: "arrayBuffer",
    },
  );
  if (error !== undefined) {
    throw new Error(
      "The geometry service rejected the request — check the dimensions",
    );
  }
  if (data === undefined) {
    throw new Error("Tessellation returned no mesh payload");
  }
  // The OpenAPI schema types binary content as string; parseAs:"arrayBuffer"
  // makes the runtime payload an ArrayBuffer (openapi-fetch pass-through).
  const glb = data as unknown as ArrayBuffer;
  const meta = parsePropertiesHeader(response.headers.get(PROPERTIES_HEADER));
  return { glb, meta };
}
