/** Tiny class-name joiner — avoids a dependency for one-liner needs. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
