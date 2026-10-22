/**
 * Mirror components in the assembly workspace (ASM-MIRROR-COMPONENT), pure.
 *
 * The mirror dialog's form, how it becomes a wire mirror, how a stored mirror
 * reads back into the form, and how a mirror is named in the tree. As in
 * SolidWorks' Mirror Components: each chosen component gets a mirrored COPY
 * (the same part, for a symmetric one) or an OPPOSITE HAND (a derived part
 * whose geometry is the source reflected, and which follows its edits).
 */
import type { InstanceResponse } from "../api/assemblies";
import type {
  ComponentMirror,
  MirrorResponse,
  MirrorState,
} from "../api/mirrors";
import {
  coerceToField,
  ExprError,
  evaluateExpression,
  lengthEntryExpression,
} from "../features/expr";
import type { PickedFace } from "./patternStore";

/** An origin plane of the assembly, or the face picked in the viewport. */
export type PlaneChoice = "yz" | "zx" | "xy" | "face";

export const PLANE_LABEL: Record<PlaneChoice, string> = {
  yz: "YZ plane",
  zx: "XZ plane",
  xy: "XY plane",
  face: "Picked face",
};

export interface MirrorForm {
  /** The components to mirror, in order. */
  seeds: string[];
  /** The seeds that get an opposite hand rather than a copy. */
  opposite: string[];
  plane: PlaneChoice;
  /** An origin plane's offset along its normal, as typed. */
  offset: string;
  face: PickedFace | null;
}

export function newMirrorForm(seeds: string[]): MirrorForm {
  return { seeds, opposite: [], plane: "yz", offset: "0 mm", face: null };
}

/** A stored mirror, back in the form. */
export function formFromMirror(mirror: ComponentMirror): MirrorForm {
  const form = newMirrorForm([...mirror.seed_instance_ids]);
  form.opposite = [...(mirror.opposite_hand_instance_ids ?? [])];
  if (mirror.plane.kind === "face") {
    form.plane = "face";
    form.face = {
      instanceId: mirror.plane.instance_id,
      signature: mirror.plane.signature,
    };
  } else {
    form.plane = mirror.plane.plane;
    form.offset = `${mirror.plane.offset_mm ?? 0} mm`;
  }
  return form;
}

/** Whether *instance* can get an opposite hand (parts only). */
export function canBeOppositeHand(
  instance: Pick<InstanceResponse, "ref_document_kind">,
): boolean {
  return instance.ref_document_kind === "part";
}

/** The wire mirror for `form`, or the reason it is not one yet. */
export function buildMirror(
  form: MirrorForm,
): { mirror: ComponentMirror } | { error: string } {
  if (form.seeds.length === 0) return { error: "Choose a component to mirror" };
  const opposite = form.opposite.filter((id) => form.seeds.includes(id));
  if (form.plane === "face") {
    if (form.face === null) return { error: "Pick the face to mirror about" };
    return {
      mirror: {
        seed_instance_ids: form.seeds,
        plane: {
          kind: "face",
          instance_id: form.face.instanceId,
          signature: form.face.signature,
        },
        opposite_hand_instance_ids: opposite,
      },
    };
  }
  let offset: number;
  try {
    offset = coerceToField(
      evaluateExpression(lengthEntryExpression(form.offset, "mm"), new Map()),
      "length",
    );
  } catch (error) {
    const reason = error instanceof ExprError ? error.message : String(error);
    return { error: `Offset: ${reason}` };
  }
  return {
    mirror: {
      seed_instance_ids: form.seeds,
      plane: { kind: "origin_plane", plane: form.plane, offset_mm: offset },
      opposite_hand_instance_ids: opposite,
    },
  };
}

/** "Mirror 2": its ordinal among the assembly's mirrors. */
export function mirrorTitle(
  mirrors: readonly MirrorResponse[],
  mirror: MirrorResponse,
): string {
  return `Mirror ${mirrors.findIndex((m) => m.id === mirror.id) + 1}`;
}

/** What a mirror reflects: its seeds' names, an opposite hand marked. */
export function mirrorSeedNames(
  instances: readonly Pick<InstanceResponse, "id" | "name">[],
  mirror: ComponentMirror,
): string {
  const opposite = new Set(mirror.opposite_hand_instance_ids ?? []);
  return mirror.seed_instance_ids
    .map((id) => {
      const name = instances.find((i) => i.id === id)?.name ?? "Missing";
      return opposite.has(id) ? `${name} (opposite hand)` : name;
    })
    .join(", ");
}

/** The tree's warning for a mirror's state, or null when it placed cleanly. */
export function mirrorWarning(
  instances: readonly Pick<InstanceResponse, "id" | "name">[],
  state: MirrorState | undefined,
): string | null {
  if (state === undefined) return null;
  if (state.error_code !== null && state.error_code !== undefined) {
    return state.error_message ?? "not placed";
  }
  const asymmetric = state.asymmetric ?? [];
  if (asymmetric.length === 0) return null;
  const names = asymmetric
    .map((id) => instances.find((i) => i.id === id)?.name ?? "a part")
    .join(", ");
  return `${names}: not symmetric, so its copy is not a mirror image; make it an opposite hand`;
}
