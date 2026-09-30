/**
 * EDIT FEATURE ROLLS THE TIMELINE BACK (FILLET-EDIT-REPICK), as Fusion 360's
 * Edit Feature does: while a fillet, chamfer, shell or draft is being edited,
 * the travel stop sits just before it, so the viewport shows the body the
 * feature is BUILT ON. That is the body its picks live on. At the tip the
 * edges a fillet rounded are gone, so its picks had nothing to be drawn on and
 * a click could not reach them.
 *
 * The stop is the documents rollback bar (`PUT /rollback`), which is view
 * state: moving it is not an undo step. The edit remembers where the bar was
 * and puts it back on Save, Cancel, or on switching to an editor that does not
 * roll back. On Save the bar goes back BEFORE the write, so the undo snapshot
 * the write records has the bar where the user left it, not rolled back.
 *
 * Moves are serialised: each reads the tree version the previous one produced,
 * and a Cancel followed at once by another Edit restores the bar the FIRST
 * edit found, not the one it left.
 */
import type { FeatureResponse } from "../api/parts";

/** The editors whose Edit rolls the timeline back to the feature. */
export const ROLLBACK_EDIT_KINDS: ReadonlySet<string> = new Set([
  "fillet",
  "chamfer",
  "shell",
  "draft",
]);

/**
 * Where the bar sits while `featureId` is edited: the feature right before
 * it (the bar names the LAST INCLUDED feature). Undefined when the feature is
 * unknown or first, which cannot be rolled back to.
 */
export function editRollbackBarId(
  features: readonly FeatureResponse[],
  featureId: string,
): string | undefined {
  const at = features.findIndex((feature) => feature.id === featureId);
  if (at <= 0) return undefined;
  return features[at - 1]?.id;
}

/** The bar and the tree version that reported it. */
export interface BarState {
  /** The last included feature, or null at the tip. */
  bar: string | null;
  version: number;
}

export interface EditRollbackDeps {
  /** The bar as the cached tree reports it, or null before the tree loads. */
  cachedBar: () => BarState | null;
  /**
   * Move the persisted bar, writing against `expectedVersion`. `quiet` skips
   * the body refetch: the caller writes next and refreshes after that.
   * Resolves with the tree version the move produced.
   */
  moveBar: (
    bar: string | null,
    expectedVersion: number | null,
    quiet: boolean,
  ) => Promise<number>;
}

export class EditRollback {
  /** Where the bar was when the edit took it, or null when no edit holds it. */
  private restoreTo: { bar: string | null } | null = null;
  /** The bar the held edit wants, so a failed save can take it back. */
  private target: string | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  /** The bar the queue will leave in place, while moves are queued. */
  private queuedBar: { bar: string | null } | null = null;
  private pending = 0;
  /**
   * What this controller's last move produced. A quiet move does not refresh
   * the cached tree, so until the cache catches up this is the fresher fact.
   */
  private known: BarState | null = null;

  constructor(private readonly deps: EditRollbackDeps) {}

  /** True while an edit holds the bar back. */
  get held(): boolean {
    return this.restoreTo !== null;
  }

  /** Roll the bar back to `target` for an edit. */
  hold(target: string): Promise<number | null> {
    if (this.restoreTo === null) this.restoreTo = { bar: this.barNow() };
    this.target = target;
    return this.enqueue(target, false);
  }

  /**
   * Put the bar back where the edit found it. Resolves with the version the
   * move produced, or null when there was nothing to move.
   */
  release(quiet = false): Promise<number | null> {
    if (this.restoreTo === null) return Promise.resolve(null);
    const { bar } = this.restoreTo;
    this.restoreTo = null;
    return this.enqueue(bar, quiet);
  }

  /** Take the bar back after a failed save (the editor is still open). */
  reacquire(): Promise<number | null> {
    return this.target === null
      ? Promise.resolve(null)
      : this.hold(this.target);
  }

  /** The user moved the bar: that position is theirs, so do not restore. */
  forget(): void {
    this.restoreTo = null;
  }

  /** The server's bar: the cached tree, or this controller's newer move. */
  private server(): BarState | null {
    const cached = this.deps.cachedBar();
    if (
      this.known !== null &&
      (cached === null || this.known.version > cached.version)
    ) {
      return this.known;
    }
    return cached;
  }

  private barNow(): string | null {
    return this.queuedBar !== null
      ? this.queuedBar.bar
      : (this.server()?.bar ?? null);
  }

  private enqueue(bar: string | null, quiet: boolean): Promise<number | null> {
    this.queuedBar = { bar };
    this.pending += 1;
    const run = this.queue.then(async () => {
      const server = this.server();
      if (server !== null && server.bar === bar) return null;
      const version = await this.deps.moveBar(
        bar,
        server?.version ?? null,
        quiet,
      );
      this.known = { bar, version };
      return version;
    });
    const settle = () => {
      this.pending -= 1;
      if (this.pending === 0) this.queuedBar = null;
    };
    // The chain itself never rejects, so one failed move does not strand the
    // moves queued after it; the caller still sees this move's failure.
    this.queue = run.then(settle, settle);
    return run;
  }
}
