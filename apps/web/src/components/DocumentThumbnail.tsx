/**
 * A document's picture in a register row or the Add panel (LIBRARY-THUMBNAILS),
 * as Fusion's Data Panel and Onshape's document list show one: the part or
 * assembly from the isometric view, or a drawing's first sheet, rendered by
 * the server from the current tree.
 *
 * Three honest states, never a stale picture:
 *
 * - **loading** — the placeholder glyph, softly pulsing, while the server
 *   renders. A new `version` is a new query, so an edit shows the placeholder
 *   and then the new picture; it never keeps showing the old one as current;
 * - **ready** — the picture;
 * - **failed / empty** — the placeholder, still. A document that does not
 *   build has no picture (the server refuses rather than drawing its last good
 *   body); its glyph takes the flag ink and the tile says why on hover.
 */
import { cx } from "@loft/design";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchThumbnail, type ThumbnailKind } from "../api/thumbnails";

export type ThumbnailState = "loading" | "ready" | "failed" | "empty" | "error";

export interface DocumentThumbnailProps {
  kind: ThumbnailKind;
  id: string;
  /**
   * Anything that changes when the document does (a part's `tree_version`, a
   * document's `updated_at`). Part of the query key, so an edit refetches; the
   * browser's ETag revalidation makes an unchanged refetch a 304.
   */
  version: string | number;
  /** The document's name, for the image's alternative text. */
  name: string;
  size?: "md" | "sm";
  className?: string;
}

const TITLES: Record<Exclude<ThumbnailState, "ready">, string> = {
  loading: "Rendering preview…",
  failed: "No preview: this document does not rebuild.",
  empty: "No preview yet: nothing to draw.",
  error: "The preview could not be loaded.",
};

export function DocumentThumbnail({
  kind,
  id,
  version,
  name,
  size = "md",
  className,
}: DocumentThumbnailProps) {
  const query = useQuery({
    queryKey: ["thumbnail", kind, id, version],
    queryFn: () => fetchThumbnail(kind, id),
    staleTime: 30_000,
    // A 503 (the geometry queue is full) is worth one more try; a 422 is an
    // answer, not an error, and never reaches here as one.
    retry: 1,
  });
  const blob = query.data?.kind === "image" ? query.data.blob : null;
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (blob === null) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  const state: ThumbnailState = query.isError
    ? "error"
    : query.data?.kind === "unavailable"
      ? query.data.reason
      : url !== null
        ? "ready"
        : "loading";

  return (
    <span
      data-testid="document-thumbnail"
      data-thumbnail-state={state}
      data-thumbnail-kind={kind}
      data-document-id={id}
      title={state === "ready" ? undefined : TITLES[state]}
      className={cx(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-sm border border-hairline bg-carbide",
        size === "md" ? "h-12 w-12" : "h-10 w-10",
        className,
      )}
    >
      {state === "ready" && url !== null ? (
        <img
          src={url}
          alt={`Preview of ${name}`}
          className="h-full w-full object-contain"
          draggable={false}
        />
      ) : (
        <PlaceholderGlyph
          failed={state === "failed"}
          pulsing={state === "loading"}
        />
      )}
    </span>
  );
}

/** An outlined isometric block: the "a picture goes here" mark. */
function PlaceholderGlyph({
  failed,
  pulsing,
}: {
  failed: boolean;
  pulsing: boolean;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={cx(
        "h-1/2 w-1/2",
        failed ? "text-flag" : "text-etch",
        pulsing && "animate-pulse",
      )}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinejoin="round"
    >
      <path d="M12 3 20 7.5v9L12 21l-8-4.5v-9L12 3Z" />
      <path d="M4 7.5 12 12l8-4.5M12 12v9" />
      {failed ? <path d="M7 17 17 7" /> : null}
    </svg>
  );
}
