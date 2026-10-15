/**
 * EDIT IN PLACE, the chrome (ASM-A3-IN-CONTEXT): which assembly the part is
 * being edited in, the way back to it, and every in-context reference of this
 * part that did not resolve, each named by its sketch and said in plain words
 * (the typed reason geometry reported). A reference that resolved is quiet.
 */
import { useNavigate } from "@tanstack/react-router";

import type { FeatureResponse } from "../../api/parts";
import { IN_CONTEXT_REASON_TEXT } from "../../assembly/inContext";
import type { InContextSession } from "./useInContext";

export function InContextBanner({
  session,
  features,
}: {
  session: InContextSession | null;
  features: readonly FeatureResponse[];
}) {
  const navigate = useNavigate();
  if (session === null) return null;
  const errors = session.statuses.filter((status) => status.state === "error");
  const sketchName = (id: string) =>
    features.find((feature) => feature.id === id)?.name ?? "A sketch";
  return (
    <div
      role="region"
      aria-label="Editing in place"
      data-testid="in-context-banner"
      data-loading={session.loading ? "true" : "false"}
      data-links={session.statuses.length}
      className="pointer-events-auto absolute bottom-3 left-1/2 z-10 flex max-w-[min(36rem,calc(100%-2rem))] -translate-x-1/2 flex-col gap-1 rounded-sm border border-brass/60 bg-anvil/95 px-3 py-2"
    >
      <div className="flex items-center gap-3">
        <span className="font-display text-2xs uppercase tracking-[0.18em] text-brass">
          Editing in place
        </span>
        <span className="truncate font-body text-xs text-mist">
          in {session.assemblyName ?? "the assembly"}
        </span>
        <button
          type="button"
          data-testid="in-context-return"
          className="ml-auto rounded-sm border border-hairline px-2 py-0.5 font-body text-xs text-mist hover:border-brass hover:text-brass"
          onClick={() =>
            void navigate({
              to: "/assemblies/$assemblyId",
              params: { assemblyId: session.assemblyId },
            })
          }
        >
          Return to assembly
        </button>
      </div>
      {session.problem !== null ? (
        <p role="alert" className="font-body text-xs text-flag">
          {session.problem}
        </p>
      ) : null}
      {errors.map((status) => (
        <p
          key={`${status.feature_id}/${status.entity_id}`}
          role="alert"
          data-testid={`in-context-error-${status.entity_id}`}
          data-reason={status.reason ?? ""}
          className="font-body text-xs text-flag"
        >
          <span className="font-medium">{sketchName(status.feature_id)}:</span>{" "}
          {status.reason
            ? IN_CONTEXT_REASON_TEXT[status.reason]
            : (status.message ?? "")}
        </p>
      ))}
      {session.statuses.map((status) => {
        const curve = status.resolved;
        const centre =
          curve?.kind === "circle"
            ? `${curve.center.x},${curve.center.y},${curve.center.z}`
            : "";
        return (
          // A raster-independent stamp of each link, for QA.
          <span
            key={`stamp-${status.feature_id}/${status.entity_id}`}
            hidden
            data-testid={`in-context-link-${status.entity_id}`}
            data-state={status.state}
            data-centre={centre}
          />
        );
      })}
    </div>
  );
}
