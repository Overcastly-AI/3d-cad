/**
 * The part workspace's right-click menus (UI-REVIEW 2026-07-24 #10): the
 * viewport menu (view snaps, tools, selection) and the feature-tree row menu
 * (edit / suppress / rename / delete, and the Repeat verbs). Built on open
 * (cheap), so every item reads the freshest state; each row is a WIRED
 * action. Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */
import {
  CloseIcon,
  ConstructionIcon,
  type ContextMenuSection,
  DatumIcon,
  MeasureIcon,
  SketchIcon,
  SuppressIcon,
  ViewFitIcon,
  ViewFrontIcon,
  ViewHomeIcon,
  ViewIsoIcon,
  ViewRightIcon,
  ViewTopIcon,
  VerbGlyph,
} from "@loft/design";

import type { FeatureResponse } from "../../api/parts";
import { scopeFeature } from "../../features/patternScope";
import { useViewCommandStore } from "../../viewport/viewCommands";
import { selectionTouchesProjected } from "../../sketch/project";
import { useSketchStore } from "../../sketch/store";

/**
 * The SKETCHER's right-click menu (SKETCH-PROJECT-EDGES): what can be done to
 * the selected sketch geometry. Break link is Fusion's verb for projected
 * geometry — the entity stays where it is and stops following the body — and
 * it is offered only when the selection holds some; the other two are the
 * strip's own verbs (N, Delete), here because the pointer is.
 */
export function sketchMenuSections(): ContextMenuSection[] {
  const sketch = useSketchStore.getState();
  const projected = selectionTouchesProjected(
    sketch.selection,
    sketch.entities,
  );
  const empty = sketch.selection.length === 0;
  return [
    {
      key: "sketch",
      label: "Sketch",
      items: [
        {
          key: "break-link",
          label: "Break link",
          icon: <CloseIcon />,
          disabled: !projected,
          onSelect: () => useSketchStore.getState().breakLink(),
          "data-testid": "ctx-sketch-break-link",
        },
        {
          key: "construction",
          label: "Toggle construction",
          icon: <ConstructionIcon />,
          shortcut: "N",
          disabled: empty,
          onSelect: () => useSketchStore.getState().toggleConstruction(),
          "data-testid": "ctx-sketch-construction",
        },
        {
          key: "delete",
          label: "Delete",
          icon: <CloseIcon />,
          shortcut: "Del",
          danger: true,
          disabled: empty,
          onSelect: () => useSketchStore.getState().deleteSelection(),
          "data-testid": "ctx-sketch-delete",
        },
      ],
    },
  ];
}

const requestView = (
  kind: "fit" | "home" | "front" | "top" | "right" | "iso",
) => useViewCommandStore.getState().request(kind);

export function viewportMenuSections({
  selectedFeatureId,
  features,
  hasBody,
  measureActive,
  deletingId,
  startSketch,
  startSketchOnFace,
  toggleMeasure,
  toggleSuppress,
  requestDeleteFeature,
}: {
  selectedFeatureId: string | null;
  features: FeatureResponse[];
  hasBody: boolean;
  measureActive: boolean;
  deletingId: string | null;
  startSketch: () => void;
  startSketchOnFace: () => void;
  toggleMeasure: () => void;
  toggleSuppress: (feature: FeatureResponse) => void;
  requestDeleteFeature: (feature: FeatureResponse) => void;
}): ContextMenuSection[] {
  const selected =
    selectedFeatureId === null
      ? undefined
      : features.find((f) => f.id === selectedFeatureId);
  const sections: ContextMenuSection[] = [
    {
      key: "view",
      label: "View",
      items: [
        {
          key: "fit",
          label: "Fit to view",
          icon: <ViewFitIcon />,
          shortcut: "0",
          onSelect: () => requestView("fit"),
          "data-testid": "ctx-view-fit",
        },
        {
          key: "home",
          label: "Home",
          icon: <ViewHomeIcon />,
          shortcut: "Home",
          onSelect: () => requestView("home"),
          "data-testid": "ctx-view-home",
        },
        {
          key: "front",
          label: "Front",
          icon: <ViewFrontIcon />,
          shortcut: "1",
          onSelect: () => requestView("front"),
          "data-testid": "ctx-view-front",
        },
        {
          key: "top",
          label: "Top",
          icon: <ViewTopIcon />,
          shortcut: "2",
          onSelect: () => requestView("top"),
          "data-testid": "ctx-view-top",
        },
        {
          key: "right",
          label: "Right",
          icon: <ViewRightIcon />,
          shortcut: "3",
          onSelect: () => requestView("right"),
          "data-testid": "ctx-view-right",
        },
        {
          key: "iso",
          label: "Isometric",
          icon: <ViewIsoIcon />,
          shortcut: "4",
          onSelect: () => requestView("iso"),
          "data-testid": "ctx-view-iso",
        },
      ],
    },
    {
      key: "tools",
      label: "Tools",
      items: [
        {
          key: "new-sketch",
          label: "New sketch",
          icon: <SketchIcon />,
          onSelect: startSketch,
          "data-testid": "ctx-new-sketch",
        },
        {
          key: "sketch-on-face",
          label: "Sketch on face",
          icon: <DatumIcon />,
          disabled: !hasBody,
          onSelect: startSketchOnFace,
          "data-testid": "ctx-sketch-on-face",
        },
        {
          key: "measure",
          label: measureActive ? "Stop measuring" : "Measure",
          icon: <MeasureIcon />,
          shortcut: "M",
          disabled: !hasBody,
          onSelect: toggleMeasure,
          "data-testid": "ctx-measure",
        },
      ],
    },
  ];
  if (selected !== undefined) {
    const suppressed = selected.feature.suppressed ?? false;
    sections.push({
      key: "selected",
      label: selected.name,
      items: [
        {
          key: "suppress",
          label: suppressed ? "Unsuppress" : "Suppress",
          icon: <SuppressIcon />,
          onSelect: () => toggleSuppress(selected),
          "data-testid": "ctx-selected-suppress",
        },
        {
          key: "delete",
          label: "Delete",
          icon: <CloseIcon />,
          danger: true,
          disabled: deletingId === selected.id,
          onSelect: () => requestDeleteFeature(selected),
          "data-testid": "ctx-selected-delete",
        },
      ],
    });
  }
  return sections;
}

export function treeMenuSections(
  feature: FeatureResponse,
  {
    hasBody,
    deletingId,
    selectFeature,
    setSelectedFeatureId,
    setRenamingId,
    toggleSuppress,
    requestDeleteFeature,
    openScopedVerb,
  }: {
    hasBody: boolean;
    deletingId: string | null;
    selectFeature: (feature: FeatureResponse) => void;
    setSelectedFeatureId: (id: string | null) => void;
    setRenamingId: (id: string | null) => void;
    toggleSuppress: (feature: FeatureResponse) => void;
    requestDeleteFeature: (feature: FeatureResponse) => void;
    openScopedVerb: (
      verb: "pattern" | "mirror",
      feature: FeatureResponse,
    ) => void;
  },
): ContextMenuSection[] {
  const suppressed = feature.feature.suppressed ?? false;
  // Only offered where the kernel can actually repeat this row on its own —
  // a fillet/shell/boolean has a result and no rigid tool, so naming one is a
  // rebuild error, and pattern-scope §7 rule 4 says a refused kind is not
  // OFFERED rather than refused after the fact.
  const seedable = hasBody && scopeFeature(feature) !== null;
  const sections: ContextMenuSection[] = [
    {
      key: "feature",
      label: feature.name,
      items: [
        {
          key: "edit",
          label: "Edit",
          onSelect: () => selectFeature(feature),
          "data-testid": "tree-ctx-edit",
        },
        {
          key: "rename",
          label: "Rename",
          icon: <SketchIcon />,
          onSelect: () => {
            setSelectedFeatureId(feature.id);
            setRenamingId(feature.id);
          },
          "data-testid": "tree-ctx-rename",
        },
        {
          key: "suppress",
          label: suppressed ? "Unsuppress" : "Suppress",
          icon: <SuppressIcon />,
          onSelect: () => toggleSuppress(feature),
          "data-testid": "tree-ctx-suppress",
        },
        {
          key: "delete",
          label: "Delete",
          icon: <CloseIcon />,
          danger: true,
          disabled: deletingId === feature.id,
          onSelect: () => requestDeleteFeature(feature),
          "data-testid": "tree-ctx-delete",
        },
      ],
    },
  ];
  // A SECOND SECTION, not four more items in the first: Edit/Rename/Suppress/
  // Delete are things you do TO the row, these make a NEW feature out of it.
  // The verbs read as sentences ("Repeat Hole1") for the same reason the band
  // renames itself — the menu proposes the next step by name.
  if (seedable) {
    sections.push({
      key: "scope",
      label: "Repeat",
      items: [
        {
          key: "pattern",
          label: `Repeat ${feature.name}`,
          icon: <VerbGlyph verb="pattern" />,
          shortcut: "P",
          onSelect: () => openScopedVerb("pattern", feature),
          "data-testid": "tree-ctx-pattern",
        },
        {
          key: "mirror",
          label: `Mirror ${feature.name}`,
          icon: <VerbGlyph verb="mirror" />,
          shortcut: "I",
          onSelect: () => openScopedVerb("mirror", feature),
          "data-testid": "tree-ctx-mirror",
        },
      ],
    });
  }
  return sections;
}
