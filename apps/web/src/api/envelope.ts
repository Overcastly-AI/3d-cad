/**
 * Reader for the py-kit error envelope:
 *   {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}
 *
 * The generated client only *types* the documented error statuses (422), but
 * every non-2xx body a Loft service returns has this shape at runtime — this
 * module narrows `unknown` bodies safely, it does NOT redeclare API types.
 */

export interface ErrorEnvelope {
  code: string;
  message: string;
}

/** Narrow an unknown response body to the error envelope, or null. */
export function parseErrorEnvelope(body: unknown): ErrorEnvelope | null {
  if (typeof body !== "object" || body === null) return null;
  const error = (body as Record<string, unknown>).error;
  if (typeof error !== "object" || error === null) return null;
  const o = error as Record<string, unknown>;
  if (typeof o.code !== "string" || typeof o.message !== "string") return null;
  return { code: o.code, message: o.message };
}

/** The envelope's machine-readable code (e.g. "invalid_token"), or null. */
export function envelopeCode(body: unknown): string | null {
  return parseErrorEnvelope(body)?.code ?? null;
}

/** The envelope's human message, or *fallback* when the body isn't one. */
export function envelopeMessage(body: unknown, fallback: string): string {
  return parseErrorEnvelope(body)?.message ?? fallback;
}

/** The envelope's `details` object, narrowed; `{}` when there is none. */
export function envelopeDetails(body: unknown): Record<string, unknown> {
  if (typeof body !== "object" || body === null) return {};
  const error = (body as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return {};
  const details = (error as { details?: unknown }).details;
  return typeof details === "object" && details !== null
    ? (details as Record<string, unknown>)
    : {};
}

/**
 * A refused feature write. `pointer` is the params field the server blames
 * (`/distance_mm`) when a formula did not resolve (PART-PARAMETERS), so the
 * editor can put the message on that field.
 */
export class FeatureWriteError extends Error {
  constructor(
    message: string,
    readonly code: string | null,
    readonly pointer: string | null,
  ) {
    super(message);
    this.name = "FeatureWriteError";
  }
}

/** A refused feature create/update body as a {@link FeatureWriteError}. */
export function featureWriteError(
  body: unknown,
  fallback: string,
): FeatureWriteError {
  const pointer = envelopeDetails(body).pointer;
  return new FeatureWriteError(
    envelopeMessage(body, fallback),
    envelopeCode(body),
    typeof pointer === "string" ? pointer : null,
  );
}
