/**
 * The authoring seat's editor union and the constants the part workspace
 * shares. Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import {
  type EdgeSignature,
  type EvaluateTreeResult,
  type PlanarFaceSignature,
} from "../../api/parts";
import { type DatumForm } from "../../features/datum";
import { type ExtrudeForm } from "../../features/extrude";
import { type RevolveForm } from "../../features/revolve";
import { type PatternForm } from "../../features/pattern";
import { type SweepForm } from "../../features/sweep";
import { type LoftForm } from "../../features/loft";
import {
  type BaseFlangeForm,
  type CornerReliefForm,
  type EdgeFlangeForm,
  type HemForm,
} from "../../features/sheetMetal";
import { type CombineForm } from "../../features/boolean";
import { type MirrorForm } from "../../features/mirror";
import { type ChamferForm, type FilletForm } from "../../features/modify";
import { type ShellForm } from "../../features/shell";
import { type DraftForm } from "../../features/draft";
import { type HoleForm } from "../../features/hole";

/** Constraint/dimension edits persist after this quiet gap (the live loop). */
export const SYNC_DEBOUNCE_MS = 400;

/**
 * The one open feature editor (the authoring seat holds a single editor at a
 * time). Hoisted to a named union so `COMMAND_LABEL` can be keyed on
 * `OpenEditor["kind"]` — a future editor kind missing from the map is a
 * COMPILE error, never a silently unlocked band with unregistered keys.
 */
export type OpenEditor =
  | {
      kind: "extrude";
      mode: "create" | "edit";
      initial: ExtrudeForm;
      featureId?: string;
    }
  | {
      kind: "revolve";
      mode: "create" | "edit";
      initial: RevolveForm;
      featureId?: string;
    }
  | {
      kind: "sweep";
      mode: "create" | "edit";
      initial: SweepForm;
      featureId?: string;
    }
  | {
      kind: "loft";
      mode: "create" | "edit";
      initial: LoftForm;
      featureId?: string;
    }
  | {
      kind: "pattern";
      mode: "create" | "edit";
      initial: PatternForm;
      featureId?: string;
    }
  | {
      kind: "fillet";
      mode: "create" | "edit";
      initial: FilletForm;
      initialPicked: EdgeSignature[];
      featureId?: string;
    }
  | {
      kind: "chamfer";
      mode: "create" | "edit";
      initial: ChamferForm;
      initialPicked: EdgeSignature[];
      featureId?: string;
    }
  | {
      kind: "shell";
      mode: "create" | "edit";
      initial: ShellForm;
      initialPickedFaces: PlanarFaceSignature[];
      featureId?: string;
    }
  | {
      kind: "draft";
      mode: "create" | "edit";
      initial: DraftForm;
      initialPickedFaces: PlanarFaceSignature[];
      featureId?: string;
    }
  | {
      kind: "hole";
      mode: "create" | "edit";
      initial: HoleForm;
      featureId?: string;
    }
  | {
      kind: "mirror";
      mode: "create" | "edit";
      initial: MirrorForm;
      featureId?: string;
    }
  | {
      kind: "datum";
      mode: "create" | "edit";
      initial: DatumForm;
      featureId?: string;
    }
  | {
      kind: "baseFlange";
      mode: "create" | "edit";
      initial: BaseFlangeForm;
      featureId?: string;
    }
  | {
      kind: "edgeFlange";
      mode: "create" | "edit";
      initial: EdgeFlangeForm;
      initialPicked: EdgeSignature[];
      featureId?: string;
    }
  | {
      kind: "hem";
      mode: "create" | "edit";
      initial: HemForm;
      initialPicked: EdgeSignature[];
      featureId?: string;
    }
  | {
      kind: "cornerRelief";
      mode: "create" | "edit";
      initial: CornerReliefForm;
      featureId?: string;
    }
  | {
      kind: "combine";
      mode: "create";
      initial: CombineForm;
      featureId?: string;
    };

/** Editor kind → the command name shown in the breadcrumb + band lock reason. */
export const COMMAND_LABEL: Record<OpenEditor["kind"], string> = {
  extrude: "Extrude",
  revolve: "Revolve",
  sweep: "Sweep",
  loft: "Loft",
  pattern: "Pattern",
  fillet: "Fillet",
  chamfer: "Chamfer",
  shell: "Shell",
  draft: "Draft",
  hole: "Hole",
  mirror: "Mirror",
  datum: "Datum plane",
  baseFlange: "Base flange",
  edgeFlange: "Edge flange",
  hem: "Hem",
  cornerRelief: "Corner relief",
  combine: "Combine",
};

/** An evaluate result with no `bodies` list: one stable empty list. */
export const NO_BODIES: NonNullable<EvaluateTreeResult["bodies"]> = [];
