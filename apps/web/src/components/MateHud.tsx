/**
 * The mate-authoring HUD — the in-viewport prompt while a mate tool is armed
 * (the DRO/solve-diagnostic drawing-stamp language). It reads the mate store
 * for the active tool + how many picks are collected and tells the user the
 * next click; the store's rejection (same instance twice) and the submit error
 * surface here too. Nothing renders when no tool is armed.
 *
 * A parametric mate (distance / angle) collects two faces, then holds here to
 * let the user set its value (a design-system `NumberField`, mm / degrees) and
 * commit — keyboard-first: the field autofocuses, Enter commits, Escape cancels.
 */
import { Button, NumberField, parseLength } from "@loft/design";
import { type KeyboardEvent, useEffect, useState } from "react";

import { isParametricMate, useMateAuthoringStore } from "../assembly/mateStore";
import { mateToolLabel, parseMateValue } from "../assembly/mates";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { lengthInputValue } from "../units/length";

const FIRST: Record<string, string> = {
  coincident: "Pick a flat face on the first part.",
  concentric: "Pick a hole edge on the first part.",
  lock: "Pick the first part to anchor to.",
  distance: "Pick a flat face on the first part.",
  angle: "Pick a flat face on the first part.",
};
const SECOND: Record<string, string> = {
  coincident: "Now pick the mating face on the OTHER part — they snap flush.",
  concentric: "Now pick the mating hole edge on the OTHER part — axes align.",
  lock: "Now pick the OTHER part to lock it rigidly.",
  distance: "Now pick the offset face on the OTHER part — set the gap next.",
  angle: "Now pick the angled face on the OTHER part — set the angle next.",
};

export interface MateHudProps {
  /** A POST/re-solve failure, surfaced verbatim. */
  submitError: string | null;
  /** The mate is being added + re-solved (the snap). */
  submitting: boolean;
  /** Commit the pending parametric mate (distance / angle) at its set value. */
  onCommit: () => void;
}

export function MateHud({ submitError, submitting, onCommit }: MateHudProps) {
  const docUnit = useDocumentLengthUnit();
  const tool = useMateAuthoringStore((s) => s.tool);
  const picks = useMateAuthoringStore((s) => s.picks);
  const value = useMateAuthoringStore((s) => s.value);
  const error = useMateAuthoringStore((s) => s.error);
  const setValue = useMateAuthoringStore((s) => s.setValue);
  const setTool = useMateAuthoringStore((s) => s.setTool);

  // A distance mate carries a canonical-mm gap; an angle mate carries degrees.
  // The distance field converts through the document unit at its boundary; the
  // angle field never touches length conversion (angles are always degrees).
  const isDistance = tool === "distance";

  // A local editing buffer so decimals/signs type smoothly; the parsed number
  // flows to the store (the commit's source of truth).
  const [draft, setDraft] = useState("");
  const needsValue =
    tool !== null && isParametricMate(tool) && picks.length === 2;
  // Seed the buffer from the store's default when the value phase opens. Keyed
  // on `needsValue` only so a keystroke (which updates `value`) never clobbers
  // what the user is typing — the seed is a one-shot on entering the phase. A
  // distance seed formats the canonical mm into the document unit.
  useEffect(() => {
    if (needsValue) {
      const seed = useMateAuthoringStore.getState().value;
      setDraft(
        seed === null
          ? ""
          : isDistance
            ? lengthInputValue(seed, docUnit)
            : seed.toString(),
      );
    }
  }, [needsValue, isDistance, docUnit]);

  if (tool === null) return null;

  const onDraftChange = (next: string) => {
    setDraft(next);
    // Distance parses through the document unit → canonical mm; angle stays a
    // plain signed number of degrees.
    setValue(isDistance ? parseLength(next, docUnit) : parseMateValue(next));
  };
  const onFieldKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (value !== null && !submitting) onCommit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      setTool(null);
    }
  };

  const prompt = picks.length === 0 ? FIRST[tool] : SECOND[tool];
  const unit = isDistance ? docUnit : "°";

  return (
    <div
      role="status"
      data-testid="mate-hud"
      data-mate-tool={tool}
      className="absolute left-editor top-3 max-w-sm border border-brass bg-anvil px-3 py-2"
    >
      <span className="block font-display text-2xs uppercase tracking-[0.18em] text-brass">
        {`${mateToolLabel(tool)} mate`}
      </span>
      {needsValue && !submitting ? (
        <div className="mt-2 flex items-end gap-2">
          <NumberField
            label={mateToolLabel(tool)}
            unit={unit}
            className="w-[7rem]"
            data-testid="mate-value"
            autoFocus
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            onFocus={(event) => event.currentTarget.select()}
            onKeyDown={onFieldKeyDown}
          />
          <Button
            variant="solid"
            data-testid="mate-commit"
            disabled={value === null}
            onClick={onCommit}
          >
            Add mate
          </Button>
        </div>
      ) : (
        <span className="mt-1 block font-body text-xs text-mist">
          {submitting ? "Solving the assembly…" : prompt}
        </span>
      )}
      {error ? (
        <span
          role="alert"
          className="mt-1 block font-body text-xs text-flag"
          data-testid="mate-hud-error"
        >
          {error}
        </span>
      ) : null}
      {submitError ? (
        <span
          role="alert"
          className="mt-1 block font-body text-xs text-flag"
          data-testid="mate-submit-error"
        >
          {submitError}
        </span>
      ) : null}
    </div>
  );
}
