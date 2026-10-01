/**
 * PER-FEATURE EDIT LOGIC: the editor a tree row opens in, seeded from the
 * feature's stored params. Every type but a sketch opens a form; a sketch's
 * editor IS the sketcher, which `PartPage`'s `selectFeature` hydrates itself.
 * `null` means "no editor" (an import, a boolean). Split out of `PartPage.tsx`
 * (SPLIT-PARTPAGE); behaviour unchanged.
 */
import { type FeatureResponse, type LengthUnit } from "../../api/parts";
import { formFromDatumParams } from "../../features/datum";
import { formFromParams } from "../../features/extrude";
import { formFromRevolveParams } from "../../features/revolve";
import { formFromPatternParams } from "../../features/pattern";
import { formFromSweepParams } from "../../features/sweep";
import { formFromLoftParams } from "../../features/loft";
import {
  formFromBaseFlangeParams,
  formFromCornerReliefParams,
  formFromEdgeFlangeParams,
  formFromHemParams,
  pickedFromEdgeFlangeParams,
  pickedFromHemParams,
} from "../../features/sheetMetal";
import { formFromMirrorParams } from "../../features/mirror";
import {
  formFromChamferParams,
  formFromFilletParams,
  pickedFromChamferParams,
  pickedFromFilletParams,
} from "../../features/modify";
import {
  formFromShellParams,
  pickedFacesFromShellParams,
} from "../../features/shell";
import {
  formFromDraftParams,
  pickedFacesFromDraftParams,
} from "../../features/draft";
import { formFromHoleParams } from "../../features/hole";
import type { OpenEditor } from "./openEditor";

export function editorForFeature(
  feature: FeatureResponse,
  lengthUnit: LengthUnit,
  // A pattern/mirror's persisted scope is shown by feature NAME, which only
  // the tree can supply.
  features: FeatureResponse[],
): OpenEditor | null {
  if (feature.feature.type === "extrude") {
    return {
      kind: "extrude",
      mode: "edit",
      featureId: feature.id,
      initial: formFromParams(feature.feature.params, lengthUnit),
    };
  }
  if (feature.feature.type === "revolve") {
    return {
      kind: "revolve",
      mode: "edit",
      featureId: feature.id,
      initial: formFromRevolveParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "sweep") {
    return {
      kind: "sweep",
      mode: "edit",
      featureId: feature.id,
      initial: formFromSweepParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "loft") {
    return {
      kind: "loft",
      mode: "edit",
      featureId: feature.id,
      initial: formFromLoftParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "pattern") {
    return {
      kind: "pattern",
      mode: "edit",
      featureId: feature.id,
      initial: formFromPatternParams(
        feature.feature.params,
        lengthUnit,
        features,
      ),
    };
  }
  if (feature.feature.type === "fillet") {
    return {
      kind: "fillet",
      mode: "edit",
      featureId: feature.id,
      initial: formFromFilletParams(feature.feature.params, lengthUnit),
      initialPicked: pickedFromFilletParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "chamfer") {
    return {
      kind: "chamfer",
      mode: "edit",
      featureId: feature.id,
      initial: formFromChamferParams(feature.feature.params, lengthUnit),
      initialPicked: pickedFromChamferParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "shell") {
    return {
      kind: "shell",
      mode: "edit",
      featureId: feature.id,
      initial: formFromShellParams(feature.feature.params, lengthUnit),
      initialPickedFaces: pickedFacesFromShellParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "draft") {
    return {
      kind: "draft",
      mode: "edit",
      featureId: feature.id,
      initial: formFromDraftParams(feature.feature.params, lengthUnit),
      initialPickedFaces: pickedFacesFromDraftParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "hole") {
    return {
      kind: "hole",
      mode: "edit",
      featureId: feature.id,
      initial: formFromHoleParams(feature.feature.params, lengthUnit),
    };
  }
  if (feature.feature.type === "mirror") {
    return {
      kind: "mirror",
      mode: "edit",
      featureId: feature.id,
      initial: formFromMirrorParams(feature.feature.params, features),
    };
  }
  if (feature.feature.type === "sheet_metal_base_flange") {
    return {
      kind: "baseFlange",
      mode: "edit",
      featureId: feature.id,
      initial: formFromBaseFlangeParams(feature.feature.params, lengthUnit),
    };
  }
  if (feature.feature.type === "sheet_metal_edge_flange") {
    return {
      kind: "edgeFlange",
      mode: "edit",
      featureId: feature.id,
      initial: formFromEdgeFlangeParams(feature.feature.params, lengthUnit),
      initialPicked: pickedFromEdgeFlangeParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "sheet_metal_hem") {
    return {
      kind: "hem",
      mode: "edit",
      featureId: feature.id,
      initial: formFromHemParams(feature.feature.params, lengthUnit),
      initialPicked: pickedFromHemParams(feature.feature.params),
    };
  }
  if (feature.feature.type === "sheet_metal_corner_relief") {
    return {
      kind: "cornerRelief",
      mode: "edit",
      featureId: feature.id,
      initial: formFromCornerReliefParams(feature.feature.params, lengthUnit),
    };
  }
  if (feature.feature.type === "datum") {
    // Every datum kind is editable here — offset / offset-from / midplane /
    // on_face. A face-referencing datum (on_face or a midplane FACE-side)
    // seeds its picked face(s) from the stored signature; the editor arms a
    // re-pick through the same FacePickOverlay it authored them with.
    return {
      kind: "datum",
      mode: "edit",
      featureId: feature.id,
      initial: formFromDatumParams(feature.feature.params, lengthUnit),
    };
  }
  return null;
}
