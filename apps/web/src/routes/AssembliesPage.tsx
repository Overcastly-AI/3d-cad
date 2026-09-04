import { Button, Chip, ImportStepIcon, Kbd, ProgressTrack } from "@loft/design";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  type DragEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  type AssemblyResponse,
  createAssembly,
  deleteAssembly,
  duplicateAssembly,
  fetchAssemblies,
  moveAssembly,
  renameAssembly,
} from "../api/assemblies";
import {
  importStepAsNewDocument,
  isImportAborted,
  type StepImportResult,
} from "../api/assemblyImport";
import {
  DocumentRegister,
  type RegisterCopy,
  REGISTER_GUTTER,
} from "../components/DocumentRegister";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { useRegisterFiling } from "../components/useRegisterFiling";
import { WorkspaceNav } from "../components/WorkspaceNav";
import { precheckStepFile, stepFeatureName } from "../features/import";
import { usePreferencesStore } from "../settings/preferences";
import { KEY_IMPORT } from "../shortcuts/registry";

/**
 * The assemblies register — the same drawer as parts (`DocumentRegister`) with
 * the assembly vocabulary and the route into the instances/mates workspace.
 * Filing an assembly does NOT open it: unlike a part, a new assembly has
 * nothing to work on until parts are added to it, so the register keeps focus
 * on the scribe line for the next one.
 */
const COPY: RegisterCopy = {
  title: "Assembly register",
  caption:
    "Your assemblies, most recently worked first. Open one to compose it, or delete it. Last worked reads the time since its most recent edit.",
  noun: "assembly",
  nounPlural: "assemblies",
  loading: "Loading assemblies…",
  loadError: "Your assemblies could not be loaded.",
  deleteError: "The assembly could not be deleted.",
  renameError: "The assembly could not be renamed.",
  duplicateError: "The assembly could not be duplicated.",
  createError: "The assembly could not be created.",
  emptyHeadline: "No assemblies filed yet.",
  // FLOW (CLAUDE.md design mandate). REACH-2 got the INSTINCT right — an empty
  // register is where a migrating engineer lands holding a supplier file — and
  // paid for it in prose: the sentence had to say "from the slot below",
  // because the slot was 422 px below at 1280x800 and 622 px below at
  // 1600x1000 (UI-REVIEW 2026-08-27 P1-A; the gap GREW with the screen, which
  // is the tell that it was a layout problem wearing a copy problem's clothes).
  //
  // The layout is a fork now, so the copy can stop giving directions. It names
  // both ways once, in the order the columns run, and never points: if this
  // sentence ever needs a "below" again, the layout has regressed.
  emptyBody:
    "An assembly holds parts at their places, and the mates that keep them there. Start one from scratch, or bring in a STEP you already have — its parts, names and placements come across.",
  fieldLabel: "Assembly name",
  placeholder: "e.g. Bolted plates",
  createLabel: "New assembly",
  createFirstLabel: "Create first assembly",
};

/**
 * Would this element SWALLOW a printable keystroke? Page accelerators stand
 * down for those and only those.
 *
 * `tagName === "INPUT"` was the old test and it is too broad by exactly one
 * case that matters here: the hidden `<input type="file">` this page owns. It
 * takes focus when the picker closes, so `Escape` — the key that withdraws an
 * import in flight — was landing on it and being dropped, which made the
 * cancel path work by mouse and silently not by keyboard. A file input cannot
 * consume a character; nothing is protected by ignoring keys over it.
 */
function isTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable || target.tagName === "TEXTAREA") return true;
  return target instanceof HTMLInputElement && target.type !== "file";
}

export function AssembliesPage() {
  const queryClient = useQueryClient();
  // The user's "units for new documents" preference (#58), stamped at creation.
  const newDocumentUnit = usePreferencesStore((state) => state.newDocumentUnit);
  const assemblies = useQuery({
    queryKey: ["assemblies"],
    queryFn: () => fetchAssemblies(),
    staleTime: 30_000,
  });
  // Filing (#WS2) — see PartsPage; the wiring is shared, not repeated.
  const filing = useRegisterFiling<AssemblyResponse>(
    "assembly",
    "assemblies",
    moveAssembly,
  );

  const fileInputRef = useRef<HTMLInputElement>(null);
  /** The file currently being read + uploaded, by name; null when idle. */
  const [importing, setImporting] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [imported, setImported] = useState<StepImportResult | null>(null);
  /** True while a file drag is over the page — see `dragDepth`. */
  const [armed, setArmed] = useState(false);
  /**
   * `dragenter`/`dragleave` fire for every DESCENDANT the pointer crosses, so a
   * boolean toggled by them flickers off the moment the cursor passes over a
   * register row. Counting enters minus leaves is the standard fix and it is
   * the reason this is a ref, not state: it must not drive a render itself.
   */
  const dragDepth = useRef(0);
  /**
   * The in-flight import's abort handle, so `Stop` and `Escape` can withdraw
   * it. A ref rather than state: nothing renders FROM it (the `importing` name
   * already says a request is live), and putting it in state would re-render
   * the register on every start.
   */
  const abortRef = useRef<AbortController | null>(null);

  /** Withdraw the import in flight, if any. Idle otherwise — safe to spam. */
  const cancelImport = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // Nothing should keep running against a page the user has left.
  useEffect(() => () => abortRef.current?.abort(), []);

  /**
   * Read the chosen/dropped file and post its bytes at the import route.
   *
   * The client-side pre-check (`precheckStepFile`, shared with the part-level
   * import) only buys instant feedback; the SERVER is the source of truth and
   * its typed envelope — `import_not_step`, `import_too_large`,
   * `import_too_many_products` — is surfaced verbatim. On success the register
   * query is invalidated so the new row appears without a reload, and the
   * result line names what the server actually made: a STEP with product
   * structure becomes an assembly, a flat one becomes a part.
   *
   * A WITHDRAWN import lands nowhere: not on the error line (the user did it
   * deliberately; an "Import failed" they caused themselves is noise dressed as
   * a fault), and not on the result line. The slot simply returns to its
   * invitation, which is the state it was in before they started.
   */
  const importFile = useCallback(
    (file: File) => {
      setImportError(null);
      setImported(null);
      const preError = precheckStepFile(file);
      if (preError !== null) {
        setImportError(preError);
        return;
      }
      // A second file chosen while one is in flight replaces it rather than
      // racing it — two results would arrive into one line.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setImporting(file.name);
      void (async () => {
        try {
          const bytes = await file.arrayBuffer();
          const result = await importStepAsNewDocument(
            bytes,
            stepFeatureName(file.name),
            undefined,
            controller.signal,
          );
          await queryClient.invalidateQueries({
            queryKey: [result.kind === "assembly" ? "assemblies" : "parts"],
          });
          setImported(result);
        } catch (error) {
          if (!isImportAborted(error)) {
            setImportError(
              error instanceof Error
                ? error.message
                : "The STEP file could not be imported.",
            );
          }
        } finally {
          // Only the CURRENT request may clear the busy line: a superseded one
          // resolving late would otherwise blank the line its replacement owns.
          if (abortRef.current === controller) {
            abortRef.current = null;
            setImporting(null);
          }
        }
      })();
    },
    [queryClient],
  );

  // `I` opens the picker from anywhere on the page, the way `N` jumps to the
  // scribe line; `Escape` withdraws an import in flight, which is the same key
  // that backs out of every other command in the app. Both are ignored inside a
  // text field so they cannot eat a keystroke while an assembly is being named
  // or the drawer filtered.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTextEntry(event.target)) return;
      if (event.key === "Escape") {
        // Only claim the key while there is something to withdraw — otherwise
        // Escape still belongs to whatever else is listening for it.
        if (abortRef.current !== null) {
          event.preventDefault();
          cancelImport();
        }
        return;
      }
      if (event.key.toLowerCase() === KEY_IMPORT) {
        event.preventDefault();
        fileInputRef.current?.click();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [cancelImport]);

  /** Only a drag CARRYING FILES arms the page; text/element drags pass through. */
  const carriesFiles = (event: DragEvent): boolean =>
    event.dataTransfer.types.includes("Files");

  const onDragEnter = (event: DragEvent) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setArmed(true);
  };
  const onDragOver = (event: DragEvent) => {
    if (!carriesFiles(event)) return;
    // Without this the browser's default is to REFUSE the drop and navigate to
    // the file instead — the page would be replaced by raw STEP text.
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };
  const onDragLeave = (event: DragEvent) => {
    if (!carriesFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setArmed(false);
  };
  const onDrop = (event: DragEvent) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setArmed(false);
    const file = event.dataTransfer.files[0];
    if (file !== undefined) importFile(file);
  };

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Chip data-testid="status-chip">Assemblies</Chip>
      </TopBar>
      {/*
        THE WHOLE REGISTER IS THE DROP TARGET (REACH-2). A postage-stamp drop
        rectangle would be one more thing to aim at; the file the user is
        already holding should propose the action wherever they let go of it.
        The frame below is the outline — an element already on screen doing a
        second real job rather than new chrome appearing (mandate 3a).
      */}
      <main
        data-testid="assemblies-drop-target"
        data-drop-armed={armed ? "true" : "false"}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className="relative min-h-0 grow overflow-y-auto bg-carbide"
      >
        <SheetGrid />
        <div
          className={`pointer-events-none absolute inset-3 border transition-colors duration-fast ${
            armed ? "border-brass" : "border-hairline"
          }`}
          aria-hidden="true"
        />
        <div className="relative mx-auto flex h-full w-full max-w-5xl flex-col px-4 py-6 sm:px-8">
          <WorkspaceNav active="assemblies" />
          <DocumentRegister
            idPlural="assemblies"
            idSingular="assembly"
            copy={COPY}
            documents={assemblies.data ?? []}
            isLoading={assemblies.isLoading}
            isError={assemblies.isError}
            error={assemblies.error}
            openLink={(assembly, props) => (
              <Link
                to="/assemblies/$assemblyId"
                params={{ assemblyId: assembly.id }}
                {...props}
              >
                {assembly.name}
              </Link>
            )}
            filing={filing}
            onCreate={async (name, folderId) => {
              await createAssembly(name, newDocumentUnit, folderId);
              await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
            }}
            onRename={async (assembly, name) => {
              await renameAssembly(assembly.id, name, assembly.doc_version);
              await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
            }}
            onDuplicate={async (assembly) => {
              // Instances and mates are copied; the PARTS they name are not —
              // both assemblies reference the same parts afterwards.
              await duplicateAssembly(assembly.id);
              await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
            }}
            onDelete={async (assembly) => {
              await deleteAssembly(assembly.id);
              await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
            }}
            // THE SECOND WAY IN. The register decides where this lands — beside
            // the scribe form when the drawer is empty, as the drawer's last
            // line once it is not — because only the register knows which of
            // those it is. See `RegisterOffer`.
            offer={{
              label: "Start from a STEP file",
              render: (placement) => (
                <ImportSlot
                  placement={placement}
                  fileInputRef={fileInputRef}
                  armed={armed}
                  importing={importing}
                  error={importError}
                  imported={imported}
                  onFile={importFile}
                  onCancel={cancelImport}
                  onDismiss={() => {
                    setImportError(null);
                    setImported(null);
                  }}
                />
              ),
            }}
          />
        </div>
      </main>
    </div>
  );
}

/** The quiet brass verb shared by Dismiss, Stop and Open — one face, one rank. */
const SLOT_VERB =
  "shrink-0 rounded-sm font-display text-2xs uppercase tracking-[0.14em] text-brass outline-none transition-colors duration-fast hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass";

/**
 * THE IMPORT SLOT — one control, drawn for the two places the register puts it.
 *
 * `line` (a drawer with sheets in it) is the strip REACH-2 shipped and the
 * review praised: the register is a log book, the scribe line at its foot opens
 * a NEW entry, and this takes a sheet that already exists. That is why it is a
 * line and not a card, why it sits on the carbide gutter ground rather than the
 * drawer's anvil, and why its verb is `ghost` — the drawer spends its one solid
 * brass action on "New assembly", and boldness goes in one place. It carries
 * the drawer's scribed left margin (`REGISTER_GUTTER`, imported now rather than
 * transcribed) so the log's left rule stays one straight line; measured at
 * 1280, an un-indented strip broke it by 56 px and read as a toolbar bolted
 * underneath. The margin is BLANK rather than numbered: the scribe line can
 * print the next ordinal because it files exactly one assembly, and an import
 * cannot — the server decides whether the file becomes an assembly or a part.
 *
 * `fork` (an EMPTY drawer) is the same control with its chrome removed, because
 * there it is already inside the register's margin and beside the create form
 * as its equal. Nothing is duplicated between the two: one component, one set
 * of hooks, one state machine — the placement only decides whether the strip
 * draws a rule and a gutter of its own.
 *
 * One line, one state at a time: the invitation, the armed drop, the read, the
 * refusal, or what was made. Every one of them is real state — nothing here
 * decorates.
 */
function ImportSlot({
  placement,
  fileInputRef,
  armed,
  importing,
  error,
  imported,
  onFile,
  onCancel,
  onDismiss,
}: {
  placement: "fork" | "line";
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  armed: boolean;
  importing: string | null;
  error: string | null;
  imported: StepImportResult | null;
  onFile: (file: File) => void;
  onCancel: () => void;
  onDismiss: () => void;
}) {
  const line = placement === "line";
  return (
    <div
      data-testid="assembly-import-slot"
      data-placement={placement}
      className={
        line
          ? `flex shrink-0 items-stretch border-t bg-carbide transition-colors duration-fast ${
              armed ? "border-brass" : "border-hairline"
            }`
          : "flex items-stretch"
      }
    >
      {/* The scribed margin, at the register's own gutter width — only in the
          `line` placement; in the fork the register has already indented us. */}
      {line ? (
        <div className={`${REGISTER_GUTTER} shrink-0`} aria-hidden="true" />
      ) : null}
      <div
        className={`flex min-w-0 grow flex-wrap items-center gap-x-4 gap-y-2 ${
          line ? "py-2.5 pr-3" : ""
        }`}
      >
        {/* The native picker, kept in the DOM (hidden, non-tabbable) and opened
          by the verb or by `I`. Clearing the value lets the same file be
          re-chosen after a refusal. */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".step,.stp"
          data-testid="assembly-import-input"
          className="hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file !== undefined) onFile(file);
          }}
        />

        <div className="flex shrink-0 items-center gap-2">
          <Button
            data-testid="assembly-import-button"
            aria-label="Import STEP — file an existing assembly into this register"
            disabled={importing !== null}
            onClick={() => fileInputRef.current?.click()}
          >
            <ImportStepIcon size={14} aria-hidden />
            {importing === null ? "Import STEP" : "Importing…"}
          </Button>
          <span className="sr-only">Press I to import a STEP file.</span>
          <Kbd aria-hidden="true">{KEY_IMPORT.toUpperCase()}</Kbd>
        </div>

        {importing !== null ? (
          /*
            THE READ (UI-REVIEW 2026-08-27 P1-B).
            Three things the old busy line did not have, in the order they
            answer "is this thing alive?": a moving carriage, a number that only
            advances while the app is running, and a way out.

            `role="status"` announces the sentence ONCE. The elapsed seconds sit
            outside it deliberately — inside a live region they would be read
            aloud every second, which is how a progress indicator becomes the
            thing you turn off.
          */
          <div className="flex min-w-0 grow flex-wrap items-center gap-x-4 gap-y-1">
            <p
              role="status"
              data-testid="assembly-import-busy"
              className="min-w-0 grow font-body text-xs text-mist"
            >
              Reading <span className="font-data text-mist">{importing}</span> —
              what is inside decides whether it files as an assembly or a part.
            </p>
            {/* No width from here: the bed carries its own floor
                (`progress.bedWidth`), so a caller cannot collapse it. */}
            <ProgressTrack
              label={`Importing ${importing}`}
              data-testid="assembly-import-progress"
              className="shrink-0"
            />
            <button
              type="button"
              onClick={onCancel}
              data-testid="assembly-import-cancel"
              className={SLOT_VERB}
            >
              Stop
            </button>
          </div>
        ) : error !== null ? (
          <p
            role="alert"
            data-testid="assembly-import-error"
            className="flex min-w-0 grow flex-wrap items-baseline gap-x-3 gap-y-1 font-body text-xs text-flag"
          >
            <span className="font-display text-2xs uppercase tracking-[0.16em] text-flag">
              Import failed
            </span>
            <span className="min-w-0 text-mist">{error}</span>
            <button
              type="button"
              onClick={onDismiss}
              data-testid="assembly-import-dismiss"
              className={SLOT_VERB}
            >
              Dismiss
            </button>
          </p>
        ) : imported !== null ? (
          <ImportedLine result={imported} onDismiss={onDismiss} />
        ) : (
          <p
            data-testid="assembly-import-hint"
            className="min-w-0 grow font-body text-xs text-gauge"
          >
            {armed
              ? "Drop it anywhere on this page — its parts and placements come with it."
              : "Choose a .step or .stp file, or drop it anywhere on this page."}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * WHAT THE SERVER MADE, and the way into it.
 *
 * The result is discriminated (`kind`), and the two cases are genuinely
 * different documents, so this reads the server's own answer rather than
 * guessing from the file. The single-body case is the one worth stating out
 * loud: a flat STEP is not a failed assembly import, it is a part, and saying
 * so — with a link to it — is the difference between a result and a dead end.
 *
 * IT HAS THE SAME `Dismiss` THE REFUSAL HAS (UI-REVIEW 2026-08-27 P2-A). It
 * shipped without one, and because a result evicts `assembly-import-hint`, one
 * import removed the slot's own instruction for the rest of the session: the
 * strip stopped reading as an affordance and started reading as a log of the
 * last thing that happened, permanently. A success is not more permanent than a
 * failure, and the vocabulary of an interface should not depend on whether
 * things went well.
 */
function ImportedLine({
  result,
  onDismiss,
}: {
  result: StepImportResult;
  onDismiss: () => void;
}) {
  const dismiss = (
    <button
      type="button"
      onClick={onDismiss}
      data-testid="assembly-import-dismiss"
      className={SLOT_VERB}
    >
      Dismiss
    </button>
  );
  if (result.kind === "part") {
    return (
      <p
        role="status"
        data-testid="assembly-import-result"
        data-import-kind="part"
        className="flex min-w-0 grow flex-wrap items-baseline gap-x-3 gap-y-1 font-body text-xs text-mist"
      >
        <span>
          <span className="font-data">{result.part.name}</span> carried one body
          and no product structure, so it is filed as a part.
        </span>
        <Link
          to="/parts/$partId"
          params={{ partId: result.part.id }}
          data-testid="assembly-import-open"
          className={SLOT_VERB}
        >
          Open part
        </Link>
        {dismiss}
      </p>
    );
  }

  const instances = result.assembly.instances.length;
  const parts = result.part_ids.length;
  return (
    <p
      role="status"
      data-testid="assembly-import-result"
      data-import-kind="assembly"
      className="flex min-w-0 grow flex-wrap items-baseline gap-x-3 gap-y-1 font-body text-xs text-mist"
    >
      <span>
        Imported{" "}
        <span className="font-data">{result.assembly.assembly.name}</span> —{" "}
        {instances} {instances === 1 ? "instance" : "instances"} from {parts}{" "}
        {parts === 1 ? "part" : "parts"}.
      </span>
      <Link
        to="/assemblies/$assemblyId"
        params={{ assemblyId: result.assembly.assembly.id }}
        data-testid="assembly-import-open"
        className={SLOT_VERB}
      >
        Open assembly
      </Link>
      {dismiss}
    </p>
  );
}
