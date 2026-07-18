/**
 * Client-side part-name validation — the same policy the gateway enforces
 * (`PartCreate.name`: whitespace-trimmed, 1–200 chars), applied before the
 * request so a keyboard-first create gives an instant, legible answer instead
 * of a round-trip. The server stays the source of truth (uniqueness lives
 * there — a 409 `part_name_taken` can only be known by asking).
 */

/** The gateway's `PartCreate.name` bound. */
export const MAX_PART_NAME_LENGTH = 200;

/**
 * A field error for `name`, or `null` when it is submittable. Trims first —
 * a name of only spaces is empty, matching the server's whitespace trim.
 */
export function validatePartName(name: string): string | null {
  const trimmed = name.trim();
  if (trimmed.length === 0) return "Name the part to create it.";
  if (trimmed.length > MAX_PART_NAME_LENGTH) {
    return `Keep the name under ${MAX_PART_NAME_LENGTH} characters.`;
  }
  return null;
}
