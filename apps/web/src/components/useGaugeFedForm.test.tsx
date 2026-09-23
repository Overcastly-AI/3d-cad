/**
 * `useGaugeFedForm` — a gauge-written field commits WITH the override that
 * carries its value, in every editor that has a gauge.
 *
 * WHAT IS UNDER TEST is not "the field ends up right": an effect gets there
 * too, one commit late. It is "no commit ever shows the field behind the
 * override it was handed" — the one-commit lag that put two disagreeing
 * numbers on screen while you dragged (the rod on the new step, the field on
 * the previous one). So each editor is mounted under a `<Profiler>` whose
 * `onRender` reads the field straight off the DOM at every commit, and the
 * assertion is on that list of commits.
 *
 * WHY A TABLE OF ALL EIGHT. The defect was fixed in one editor (`3b7f9ad`) and
 * left in seven, each a copy of the same two effects. A spot-check on one or
 * two editors is exactly the evidence that let the other seven lag, so every
 * gauge-fed field appears below, the count is asserted, and an editor that
 * stops routing its gauge through the hook fails HERE.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Profiler, type ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { LengthUnit } from "@loft/design";
import { defaultDatumForm, type DatumForm } from "../features/datum";
import { defaultDraftForm, type DraftForm } from "../features/draft";
import { defaultExtrudeForm, type ExtrudeForm } from "../features/extrude";
import {
  defaultChamferForm,
  defaultFilletForm,
  type ChamferForm,
  type FilletForm,
} from "../features/modify";
import { defaultPatternForm, type PatternForm } from "../features/pattern";
import { defaultRevolveForm, type RevolveForm } from "../features/revolve";
import { defaultShellForm, type ShellForm } from "../features/shell";
import { DocumentUnitProvider } from "../units/documentUnit";
import { ChamferEditor } from "./ChamferEditor";
import { DatumEditor } from "./DatumEditor";
import { DraftEditor } from "./DraftEditor";
import { ExtrudeEditor } from "./ExtrudeEditor";
import { FilletEditor } from "./FilletEditor";
import { PatternEditor } from "./PatternEditor";
import { RevolveEditor } from "./RevolveEditor";
import { ShellEditor } from "./ShellEditor";
import { gaugeWrite, useGaugeFedForm } from "./useGaugeFedForm";

afterEach(cleanup);

const noop = (): void => undefined;

const SKETCHES = [{ id: "sk-1", name: "Sketch1", provenance: "base" as const }];

const X_AXIS = {
  id: "origin:X",
  label: "X axis · through the origin",
  construction: false,
  kind: "origin_axis" as const,
  ref: { kind: "origin_axis" as const, axis: "X" as const },
  reason: null,
};

/** One gauge-fed field of one editor, with its own form and override types. */
interface FieldSpec<F, O extends object> {
  /** The field's test id — the identity of the case. */
  field: string;
  /** A fresh seed form; a new identity is a retarget. */
  initial: () => F;
  /** The field's text in a fresh seed. */
  seeded: string;
  /** A fresh override box (a new identity is a new gauge write). */
  override: () => O;
  /** The field's text once `override()` is written (unit: mm). */
  wrote: string;
  render: (initial: F, override: O | null) => ReactElement;
}

/** The erased case: everything the table needs, types closed over. */
interface Case {
  field: string;
  seeded: string;
  wrote: string;
  mount: () => Harness;
}

interface Harness {
  /** The field's text at every commit since the last `rerender`. */
  commits: string[];
  /** Re-render with a new override box, a retarget, or both. */
  rerender: (next: { drag?: boolean; retarget?: boolean }) => void;
  /** Re-render with the SAME props (the standing override kept). */
  again: () => void;
}

function editorCase<F, O extends object>(spec: FieldSpec<F, O>): Case {
  return {
    field: spec.field,
    seeded: spec.seeded,
    wrote: spec.wrote,
    mount: () => {
      const commits: string[] = [];
      const readField = () =>
        screen.queryByTestId<HTMLInputElement>(spec.field)?.value ?? "<none>";
      let initial = spec.initial();
      let override: O | null = null;
      const tree = () => (
        <Profiler id={spec.field} onRender={() => commits.push(readField())}>
          <DocumentUnitProvider unit="mm">
            {spec.render(initial, override)}
          </DocumentUnitProvider>
        </Profiler>
      );
      const view = render(tree());
      return {
        commits,
        rerender: ({ drag = false, retarget = false }) => {
          if (retarget) initial = spec.initial();
          if (drag) override = spec.override();
          commits.length = 0;
          view.rerender(tree());
        },
        again: () => {
          commits.length = 0;
          view.rerender(tree());
        },
      };
    },
  };
}

const CASES: Case[] = [
  editorCase<ExtrudeForm, { mm: number }>({
    field: "extrude-distance",
    initial: () => defaultExtrudeForm("sk-1"),
    seeded: "10",
    override: () => ({ mm: 26 }),
    wrote: "26",
    render: (initial, override) => (
      <ExtrudeEditor
        mode="create"
        profiles={SKETCHES}
        initial={initial}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        depthOverride={override}
      />
    ),
  }),
  editorCase<FilletForm, { mm: number }>({
    field: "fillet-radius",
    initial: defaultFilletForm,
    seeded: "2",
    override: () => ({ mm: 7 }),
    wrote: "7",
    render: (initial, override) => (
      <FilletEditor
        mode="create"
        initial={initial}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        radiusOverride={override}
      />
    ),
  }),
  editorCase<ChamferForm, { mm: number }>({
    field: "chamfer-distance",
    initial: defaultChamferForm,
    seeded: "1",
    override: () => ({ mm: 3.5 }),
    wrote: "3.5",
    render: (initial, override) => (
      <ChamferEditor
        mode="create"
        initial={initial}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        distanceOverride={override}
      />
    ),
  }),
  editorCase<ShellForm, { mm: number }>({
    field: "shell-thickness",
    initial: defaultShellForm,
    seeded: "2",
    override: () => ({ mm: 4 }),
    wrote: "4",
    render: (initial, override) => (
      <ShellEditor
        mode="create"
        initial={initial}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        thicknessOverride={override}
      />
    ),
  }),
  editorCase<DatumForm, { mm: number }>({
    field: "datum-offset",
    initial: () => defaultDatumForm(),
    seeded: "30",
    override: () => ({ mm: 12 }),
    wrote: "12",
    render: (initial, override) => (
      <DatumEditor
        mode="create"
        initial={initial}
        datumRefs={[]}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        canPickFace={false}
        activeFacePickSlot={null}
        onToggleFacePick={noop}
        facePick={null}
        facePickError={null}
        offsetOverride={override}
      />
    ),
  }),
  editorCase<DraftForm, { deg: number }>({
    field: "draft-angle",
    initial: defaultDraftForm,
    seeded: "3",
    override: () => ({ deg: 7 }),
    wrote: "7",
    render: (initial, override) => (
      <DraftEditor
        mode="create"
        initial={initial}
        bodyFeatureId="body-1"
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        angleOverride={override}
      />
    ),
  }),
  editorCase<PatternForm, { n: number }>({
    field: "pattern-count",
    initial: () => defaultPatternForm(),
    seeded: "3",
    override: () => ({ n: 5 }),
    wrote: "5",
    render: (initial, override) => (
      <PatternEditor
        mode="create"
        initial={initial}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        countOverride={override}
      />
    ),
  }),
  editorCase<PatternForm, { mm: number }>({
    field: "pattern-spacing",
    initial: () => defaultPatternForm(),
    seeded: "10",
    override: () => ({ mm: 25 }),
    wrote: "25",
    render: (initial, override) => (
      <PatternEditor
        mode="create"
        initial={initial}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        spacingOverride={override}
      />
    ),
  }),
  editorCase<RevolveForm, { deg: number }>({
    field: "revolve-angle",
    initial: () => defaultRevolveForm("sk-1", "origin:X"),
    seeded: "360",
    override: () => ({ deg: 90 }),
    wrote: "90",
    render: (initial, override) => (
      <RevolveEditor
        mode="create"
        profiles={SKETCHES}
        axesByProfile={{ "sk-1": [X_AXIS] }}
        initial={initial}
        onSubmit={noop}
        onCancel={noop}
        saving={false}
        error={null}
        angleOverride={override}
      />
    ),
  }),
];

/** Eight editors, nine gauge-fed fields (a pattern has two gauges). */
const GAUGE_FED_FIELDS = 9;

describe("every gauge-fed field commits WITH its override", () => {
  it(`covers all ${GAUGE_FED_FIELDS} gauge-fed fields exactly once`, () => {
    expect(CASES).toHaveLength(GAUGE_FED_FIELDS);
    expect(new Set(CASES.map((c) => c.field)).size).toBe(GAUGE_FED_FIELDS);
  });

  describe.each(CASES)("$field", (c) => {
    it("the dragged value is in the field on the commit that carries it", () => {
      const t = c.mount();
      t.rerender({ drag: true });
      // One commit, already reading the dragged value. The effect this
      // replaced produced [seeded, wrote]: a commit a drag step behind.
      expect(t.commits).toEqual([c.wrote]);
    });

    it("a typed edit is not overwritten while the same override stands", () => {
      const t = c.mount();
      t.rerender({ drag: true });
      fireEvent.change(screen.getByTestId(c.field), {
        target: { value: "17" },
      });
      t.again();
      expect(screen.getByTestId(c.field)).toHaveValue("17");
    });

    it("a retarget and a drag in the same render: the drag lands on top", () => {
      const t = c.mount();
      t.rerender({ drag: true });
      t.rerender({ retarget: true });
      expect(t.commits.at(-1)).toBe(c.seeded);
      t.rerender({ retarget: true, drag: true });
      expect(t.commits).toEqual([c.wrote]);
    });
  });
});

describe("useGaugeFedForm", () => {
  interface Form {
    a: string;
    b: string;
  }

  function Probe(props: {
    initial: Form;
    a: { v: number } | null;
    b: { v: number } | null;
    unit: LengthUnit;
  }) {
    const [form, setForm] = useGaugeFedForm(
      props.initial,
      gaugeWrite(props.a, (f: Form, o) => ({ ...f, a: String(o.v) })),
      gaugeWrite(
        props.b,
        (f: Form, o) => ({ ...f, b: `${o.v} ${props.unit}` }),
        props.unit,
      ),
    );
    return (
      <>
        <input
          data-testid="a"
          value={form.a}
          onChange={(e) => setForm((f) => ({ ...f, a: e.target.value }))}
        />
        <output data-testid="b">{form.b}</output>
      </>
    );
  }

  const SEED: Form = { a: "0", b: "0" };

  it("a repeated number in a NEW box still lands after a typed edit", () => {
    const view = render(
      <Probe initial={SEED} a={{ v: 4 }} b={null} unit="mm" />,
    );
    fireEvent.change(screen.getByTestId("a"), { target: { value: "9" } });
    view.rerender(<Probe initial={SEED} a={{ v: 4 }} b={null} unit="mm" />);
    expect(screen.getByTestId("a")).toHaveValue("4");
  });

  it("a formatting change re-writes a standing override; the other is untouched", () => {
    const a = { v: 4 };
    const b = { v: 2 };
    const view = render(<Probe initial={SEED} a={a} b={b} unit="mm" />);
    fireEvent.change(screen.getByTestId("a"), { target: { value: "9" } });
    view.rerender(<Probe initial={SEED} a={a} b={b} unit="in" />);
    expect(screen.getByTestId("b")).toHaveTextContent("2 in");
    // `a` is not formatted by the unit, so its typed edit survives.
    expect(screen.getByTestId("a")).toHaveValue("9");
  });

  it("writes apply in the order passed, both on top of a same-render re-seed", () => {
    const view = render(<Probe initial={SEED} a={null} b={null} unit="mm" />);
    view.rerender(
      <Probe
        initial={{ a: "s", b: "s" }}
        a={{ v: 1 }}
        b={{ v: 2 }}
        unit="mm"
      />,
    );
    expect(screen.getByTestId("a")).toHaveValue("1");
    expect(screen.getByTestId("b")).toHaveTextContent("2 mm");
  });

  it("an override present at mount is written before the first commit", () => {
    const commits: string[] = [];
    render(
      <Profiler
        id="probe"
        onRender={() =>
          commits.push(
            (screen.queryByTestId("a") as HTMLInputElement | null)?.value ??
              "<none>",
          )
        }
      >
        <Probe initial={SEED} a={{ v: 6 }} b={null} unit="mm" />
      </Profiler>,
    );
    expect(commits).toEqual(["6"]);
  });
});
