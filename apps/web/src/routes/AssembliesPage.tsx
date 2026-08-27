import { Button, Chip, ImportStepIcon, Kbd } from "@loft/design";
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
  type StepImportResult,
} from "../api/assemblyImport";
import {
  DocumentRegister,
  type RegisterCopy,
} from "../components/DocumentRegister";
import { SheetGrid } from "../components/SheetGrid";
import { TopBar } from "../components/TopBar";
import { useRegisterFiling } from "../components/useRegisterFiling";
import { WorkspaceNav } from "../components/WorkspaceNav";
import { precheckStepFile, stepFeatureName } from "../features/import";
import { usePreferencesStore } from "../settings/preferences";

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
  // FLOW (CLAUDE.md design mandate): an empty register is where a migrating
  // engineer lands HOLDING A SUPPLIER FILE, so "name your first assembly" —
  // what this said before REACH-2 — proposed the wrong next step to the one
  // user most likely to be here. The import slot below the drawer is named
  // first, and the scribe line stays the answer for work that starts here.
  emptyBody:
    "Already have geometry? Import a STEP from the slot below and its parts, names and placements come with it. Otherwise name your first assembly, then add parts to it, ground one, and bolt the rest together with mates.",
  fieldLabel: "Assembly name",
  placeholder: "e.g. Bolted plates",
  createLabel: "New assembly",
  createFirstLabel: "Create first assembly",
};

/**
 * The chord that opens the file picker, sitting beside the register's own `N`.
 *
 * Deliberately NOT in `shortcuts/registry.ts` yet: importing INTO a register is
 * a one-register verb today (a drawing cannot be imported, and a part imports
 * from inside its own workspace), and the repo's DRY rule is to extract on the
 * second real use rather than the first imagined one. It moves to the registry
 * — and into the shortcut sheet — the day a second register grows an import.
 */
const KEY_IMPORT = "i";

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
   * Read the chosen/dropped file and post its bytes at the import route.
   *
   * The client-side pre-check (`precheckStepFile`, shared with the part-level
   * import) only buys instant feedback; the SERVER is the source of truth and
   * its typed envelope — `import_not_step`, `import_too_large`,
   * `import_too_many_products` — is surfaced verbatim. On success the register
   * query is invalidated so the new row appears without a reload, and the
   * result line names what the server actually made: a STEP with product
   * structure becomes an assembly, a flat one becomes a part.
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
      setImporting(file.name);
      void (async () => {
        try {
          const bytes = await file.arrayBuffer();
          const result = await importStepAsNewDocument(
            bytes,
            stepFeatureName(file.name),
          );
          await queryClient.invalidateQueries({
            queryKey: [result.kind === "assembly" ? "assemblies" : "parts"],
          });
          setImported(result);
        } catch (error) {
          setImportError(
            error instanceof Error
              ? error.message
              : "The STEP file could not be imported.",
          );
        } finally {
          setImporting(null);
        }
      })();
    },
    [queryClient],
  );

  // `I` opens the picker from anywhere on the page, the way `N` jumps to the
  // scribe line. Ignored inside a text field so it cannot eat a keystroke while
  // an assembly is being named or the drawer filtered.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.key.toLowerCase() === KEY_IMPORT) {
        event.preventDefault();
        fileInputRef.current?.click();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

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
          />
          <ImportSlot
            fileInputRef={fileInputRef}
            armed={armed}
            importing={importing}
            error={importError}
            imported={imported}
            onFile={importFile}
            onDismissError={() => setImportError(null)}
          />
        </div>
      </main>
    </div>
  );
}

/**
 * THE IMPORT SLOT — the drawer's lip.
 *
 * The register is a log book: the scribe line at its foot opens a NEW entry,
 * and this strip, attached to the same bottom rule with no gap, takes a sheet
 * that already exists. That is why it is a line and not a card, why it sits on
 * the carbide gutter ground rather than the drawer's anvil, and why its verb is
 * `ghost` — the drawer already spends its one solid brass action on "New
 * assembly", and boldness goes in one place.
 *
 * One line, one state at a time: the invitation, the armed drop, the read, the
 * refusal, or what was made. Every one of them is real state — nothing here
 * decorates.
 *
 * It carries the drawer's scribed left margin so the log's left rule stays one
 * straight line from the header to the frame's bottom edge — measured at 1280,
 * an un-indented strip broke it by 56 px and the strip read as a toolbar bolted
 * under the drawer instead of the drawer's own last line. The margin is BLANK
 * rather than numbered: the scribe line can print the next ordinal because it
 * files exactly one assembly, and an import cannot — the server decides whether
 * the file becomes an assembly or a part, and how many parts come with it.
 */
function ImportSlot({
  fileInputRef,
  armed,
  importing,
  error,
  imported,
  onFile,
  onDismissError,
}: {
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  armed: boolean;
  importing: string | null;
  error: string | null;
  imported: StepImportResult | null;
  onFile: (file: File) => void;
  onDismissError: () => void;
}) {
  return (
    <div
      data-testid="assembly-import-slot"
      className={`flex shrink-0 items-stretch border border-t-0 bg-carbide transition-colors duration-fast ${
        armed ? "border-brass" : "border-hairline"
      }`}
    >
      {/* The scribed margin, at the register's own gutter width. */}
      <div className="w-[3.5rem] shrink-0" aria-hidden="true" />
      <div className="flex min-w-0 grow flex-wrap items-center gap-x-4 gap-y-2 py-2.5 pr-3">
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
          <p
            role="status"
            data-testid="assembly-import-busy"
            className="min-w-0 grow font-body text-xs text-mist"
          >
            Reading <span className="font-data text-mist">{importing}</span> —
            its products become parts and its occurrences become instances.
          </p>
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
              onClick={onDismissError}
              data-testid="assembly-import-dismiss"
              className="shrink-0 rounded-sm font-display text-2xs uppercase tracking-[0.14em] text-brass outline-none transition-colors duration-fast hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
            >
              Dismiss
            </button>
          </p>
        ) : imported !== null ? (
          <ImportedLine result={imported} />
        ) : (
          <p
            data-testid="assembly-import-hint"
            className="min-w-0 grow font-body text-xs text-gauge"
          >
            {armed
              ? "Drop it anywhere on this page — its parts and placements come with it."
              : "Have one already? Choose a .step or .stp file, or drop it anywhere on this page."}
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
 */
function ImportedLine({ result }: { result: StepImportResult }) {
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
          className="shrink-0 rounded-sm font-display text-2xs uppercase tracking-[0.14em] text-brass outline-none transition-colors duration-fast hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
        >
          Open part
        </Link>
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
        className="shrink-0 rounded-sm font-display text-2xs uppercase tracking-[0.14em] text-brass outline-none transition-colors duration-fast hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
      >
        Open assembly
      </Link>
    </p>
  );
}
