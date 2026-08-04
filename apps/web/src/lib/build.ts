/**
 * Which build am I looking at?
 *
 * `vite.config.ts` injects these at build time (FB-11). They exist because the
 * founder tests from a Codespace: without them a report cannot be tied to a
 * commit, so "already fixed or still broken?" is unanswerable from either side
 * and both sides waste a round trip finding out.
 *
 * `sha` is short, and carries a `-dirty` suffix when the tree it was built from
 * had uncommitted changes — a dirty build is a different artifact from the
 * commit it sits on, and reporting it as that clean commit would be a lie of
 * exactly the kind this module exists to prevent. `unknown` when there is no
 * git (a tarball or image build), which is honest rather than absent.
 */
declare const __BUILD_SHA__: string;
declare const __BUILD_TIME__: string;

export const BUILD_SHA: string =
  typeof __BUILD_SHA__ === "string" ? __BUILD_SHA__ : "unknown";

export const BUILD_TIME: string =
  typeof __BUILD_TIME__ === "string" ? __BUILD_TIME__ : "";

/** One line a human can read out or paste into a bug report. */
export function buildLabel(): string {
  if (BUILD_TIME === "") return BUILD_SHA;
  const when = new Date(BUILD_TIME);
  return Number.isNaN(when.getTime())
    ? BUILD_SHA
    : `${BUILD_SHA} · ${when.toISOString().slice(0, 16).replace("T", " ")}Z`;
}
