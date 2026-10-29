import type { SkippedPluginUpdate } from "../api/plugins";

/**
 * What the last Update all left out of date, and why (PLUGIN-UPDATE-ALL): a
 * feature whose update re-lays what it built (it updates on its own), or one
 * whose update was refused while the rest updated. Never silent: it stays
 * under the tree's update strip until dismissed or the next update.
 */
export function UpdateSkippedNote({
  skipped,
  onDismiss,
}: {
  skipped: readonly SkippedPluginUpdate[];
  onDismiss?: (() => void) | undefined;
}) {
  if (skipped.length === 0) return null;
  return (
    <div
      role="status"
      className="border-l-2 border-flag py-1 pr-2 pl-[10px]"
      data-testid="feature-update-skipped"
    >
      <span className="block font-display text-2xs uppercase tracking-[0.14em] text-flag">
        Left out of date
      </span>
      <ul>
        {skipped.map((skip) => (
          <li
            key={skip.feature_id}
            className="font-body text-xs text-mist"
            data-testid="feature-update-skipped-row"
          >
            <span className="text-brass">{skip.name}</span>
            {`: ${skip.message}`}
          </li>
        ))}
      </ul>
      {onDismiss !== undefined ? (
        <button
          type="button"
          onClick={onDismiss}
          data-testid="feature-update-skipped-dismiss"
          className="font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Dismiss
        </button>
      ) : null}
    </div>
  );
}
