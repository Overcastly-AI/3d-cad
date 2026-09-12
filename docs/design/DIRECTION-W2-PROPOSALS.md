# Design direction — Redesign Wave 2: proposals

**Date:** 2026-09-12 · **Author:** frontend-qa (design direction, pre-build)
**Status:** DECIDED. Three builders implement against this; it is not a menu.
**Audited against the running app** (native stack :8060/:8061/:8062, Vite :5260,
real Chromium at 1600×1000 and 1280×800), not against imagination. Reference
frames: `docs/design/screenshots/w2-direction/`.

**The sentence a user says if this wave works:** *"It tells me what to do next —
everywhere, in the same voice."*

---

## 0. The one-paragraph version

**The proposal idiom already exists and it is good.** It is the drafting
**leader note** in `viewport/SketchProposal.tsx`: an anchor dot on the exact
point the note is about, a two-tone hairline stub, and a stamped chip at the
end of it carrying a verb and its key. Wave 2 invents nothing. It **generalises
that one object** so a second, higher-value moment — a sketch solving — can
write one, gives the five most-used verbs the letters the chip will print, and
adds *one* much quieter mark in the tool band for the case a chip cannot
honestly serve. Every decision below exists to stop three agents shipping three
dialects of the same idea.

---

## 1. The proposal idiom — what is already there, and the law that governs it

I inventoried every "the app tells you something about what you could do next"
surface in the running app. There are three, and they are already distinct on
purpose. **This is the voice. Nothing in W2 may add a fourth.**

| # | Idiom | Where it lives | What it means | Visual vocabulary |
|---|---|---|---|---|
| **A** | **Leader note** (the proposal) | `viewport/SketchProposal.tsx` | *"Here is a verb you can take right now, on this thing."* | anchor dot + two-tone leader stub + chip: `border-hairline bg-anvil/90 shadow-float backdrop-blur-sm`, `text-brass`, `font-display text-2xs uppercase tracking-[0.16em]`, verb glyph left, `Kbd` right |
| **B** | **Cursor mark** (the identification) | `viewport/SketchScene.tsx` → `CursorMark` | *"This is the name of the thing under your pointer."* | same stamped card, but `text-mist`, **no leader, no `Kbd`, pointer-inert**, follows the cursor |
| **C** | **Band state cell** (the scope) | `design/BandStateCell` → `CreateStrip` SCOPE | *"A selection is held and it is renaming these verbs."* | eyebrow + value + `×` retract, inside the command band |

**The law, in three lines. Put it in the code comment of whatever you build:**

- **brass + leader + `Kbd` = an offer you can take right now.** (A)
- **mist + no leader + no `Kbd` = a name for what is under the pointer.** (B)
- **band cell + eyebrow + `×` = a held state that renames verbs.** (C)

Never mix them. A mist chip with a `Kbd` is a lie; a brass chip that only names
a thing is the "decorative chrome" defect mandate 3c calls out by name.

### 1.1 W2 extends idiom A. Here is exactly how.

Evidence that A is good and must be reused rather than re-invented:
`docs/design/screenshots/w2-direction/face-hover-offer-1600.png` — measured
live this pass: chip box **112 × 24 px**, text `"Sketch↵"`, dot on the face,
stub up-and-right, brass on anvil at **7.85 : 1** contrast (computed; AA and
AAA for normal text). The component's own docstring already argues the three
decisions that make it work (the face's hover tint carries the proposal; it is
written on REST not on hover; it proposes and does not select). Those arguments
carry over unchanged.

**Decision — one component, one note on screen at a time.**
`SketchProposal.tsx` becomes a general `ProposalNote` that renders **at most one
note**. Two independently-mounted chips would be the "three dialects" failure
literally drawn on screen, and it is reachable today (a sketch solves while the
pointer rests on an existing body's face).

**Priority when two proposals are live: the pointer wins.**
A pointer-addressed note (the face-hover sketch offer) is the user actively
pointing at something; a state-triggered note (the solve offer) is ambient. The
ambient one **withdraws the instant a pointer-addressed note is written, and
does not come back** (it is one-shot — see §4). Never stack, never queue, never
shrink one to fit both.

### 1.2 Shape, anchor, copy — exact

| Property | Decision |
|---|---|
| Shape | Unchanged: `h-proposal` × `w-proposal`, `border-hairline`, `bg-anvil/90`, `shadow-float`, `backdrop-blur-sm`, verb glyph (13 px) · verb word · `Kbd` right-aligned via `ml-auto` |
| Chip width token | **`proposal.chipWidth: 112 → 120`** in `packages/design/src/tokens.ts`. Measured in the live app at the chip's exact type spec: `SKETCH` = 45.61 px, `EXTRUDE`/`REVOLVE`/`CHAMFER` = 53.2 px, and the non-text budget leaves 51 px at 112. 120 gives 59 px and fits every verb. This is the **only** token change in the wave. |
| Placement | Unchanged — `placeProposal()` derives everything from the token, including the edge flip and clamp. Do not hand-place anything. |
| Copy — visible | **The verb alone, in caps: `SKETCH` · `EXTRUDE`.** Not `Extrude Sketch1`. Measured: `EXTRUDE SKETCH1` is 114 px of text and needs a ~181 px chip — 60 % wider, a card sitting on the model. The **leader already names the noun spatially**, which is the whole point of a leader note; saying it again in words is the one-element-one-job rule broken. |
| Copy — accessible name | **The noun is carried in words here, always.** `aria-label="Extrude Sketch1"`; the existing `aria-label="Sketch on <faceLabel>"` is unchanged. |
| `Kbd` glyph | **The verb's own letter, read from the registry** (§3): `E`, `K`. Not `↵`. |
| Motion | **None.** No fade, no slide, no pulse. The existing chip has no entry animation and says why. `prefers-reduced-motion` therefore needs no new code — which is the best available outcome, so state it in the commit rather than omitting it. |
| Focus | The chip must **not** take focus when it appears. It stays a real `<button>` with the existing `focus-visible:outline-2 outline-brass`. |
| Announcement | The **state-triggered** note gets `role="status"` so a keyboard/SR user learns it exists. The **pointer-addressed** note stays silent — that user is already looking at it, and announcing every dwell would be chatter. One `announce` prop, two call sites. |

### 1.3 Test hooks that must survive

`data-testid="sketch-proposal"` and `data-testid="sketch-proposal-layer"` are
driven by `apps/web/e2e/hover-sketch.spec.ts` and **must keep those exact
names**. Add, do not rename:

- the solve note: `data-testid="extrude-proposal"`
- both notes: `data-proposal-verb="sketch"|"extrude"` and
  `data-proposal-subject="<Sketch1 | face label>"`

so one assertion can ask "what is the app proposing right now?" without knowing
which note answered.

---

## 2. What "proposed" means mechanically

**A proposal is a pre-filled noun for a verb you can already fire.**

That one sentence is the wave's contract, and it produces the rest:

1. **Accepting must deliver everything the chip's words promise, and nothing
   more.** `EXTRUDE` anchored to Sketch1 promises the Extrude command on
   Sketch1. So accepting opens the Extrude editor **with `extrude-profile`
   already naming that sketch, `extrude-distance` autofocused and selected, and
   the existing drag handle live on that profile.** All three of those already
   happen when the toolbar opens Extrude on a solved sketch — this item is the
   chip and the binding, not new editor behaviour. Do not touch the editor.
2. **The user must not have to re-do:** picking the profile, clicking into the
   distance field, or finding the sketch in the tree. If a builder finds
   themselves adding a pick step after accept, the proposal was wrong to offer.
3. **Accepting does NOT commit a feature.** It opens the editor. One more
   `Enter` commits. Both are "accept the thing in front of you", so the
   vocabulary holds across the two.
4. **Hard gate — no chip without a noun.** If the proposal's noun cannot fill
   the command's required picks, **there is no chip.** Fillet needs edges and we
   have none (selection does not survive the pointer — `AUDIT-CRAFT` P0-2), so
   **Fillet never gets a chip in this wave.** A chip that opens an empty form is
   the templated-affordance defect, and it would poison the idiom for the two
   places it is honest.
5. **The key does the same thing as the chip.** Pressing the printed letter
   while the note shows **consumes the note's noun**. Pressing the same letter
   with no note showing starts that verb's ordinary picking flow. One rule, five
   letters — and it is what makes the chip a *teacher* rather than a button.

---

## 3. The keyboard story

### 3.1 The letters

`E` Extrude · `R` Revolve · `F` Fillet · `C` Chamfer · `K` Sketch.

**Verified free by reading the code, not by assuming.** The part workspace's
"modelling" vocabulary (live only when `mode === "off" && editor === null`,
`PartPage.tsx:4473`) currently claims: `P S L H D O I` (create/modify), `M`
(measure), `V` / `Shift+V` (isolate), `?`, `Enter`, the digits `0–5` and `Home`
(views), `Alt+↑/↓` (reorder). **None of E, R, F, C, K is taken.**

**`R`, `C`, `F`, `K`, `E` are also sketch-mode letters (rect, circle, offset,
extend, equal) and that is NOT a collision — do not "fix" it.** The two
vocabularies never coexist: the create-shortcut handler bails unless
`mode === "off"`, and `resolveSketchKey` is only consulted inside a sketch.
Mode is the disambiguator and it is already deterministic. A builder who
re-keys one of these to avoid an imagined clash has broken muscle memory for
nothing.

**`S` stays Sweep.** Sketch takes `K`. A moved shortcut is worse than a missing
one; this is the rule for any future collision too — **if a letter is taken in
the same mode, the new verb ships without a letter and gets filed.** Never
re-key an existing binding to make room.

### 3.2 One source for the letters

Add to `apps/web/src/shortcuts/registry.ts` (B2's file) an id-keyed lookup that
the handler, the chip, the tooltip and the shortcut sheet all read:

```ts
/** The id half of the band's `new-<id>` testids — one vocabulary, not two. */
export type PartVerbId = "sketch" | "extrude" | "revolve" | "fillet" | "chamfer"
  | "pattern" | "sweep" | "loft" | "shell" | "draft" | "hole" | "mirror";

/** The letter a part-workspace verb answers to, or undefined where it has none. */
export function partVerbKey(id: PartVerbId): string | undefined;
```

`PART_CREATE_SHORTCUTS` gains an `id` field and the five new rows; `partVerbKey`
is derived from that one table. **No builder may hardcode a letter anywhere.**
The chip renders `partVerbKey("extrude")?.toUpperCase() ?? "↵"` — so at every
commit, including one where B2 has not landed yet, the chip prints a key that
actually works. That is deliberate: it makes the wave order-independent and
every commit green on its own.

### 3.3 How a user learns them — three channels, ranked

1. **The chip prints the key.** This is the teacher, and it is the whole reason
   the chip is worth building. A mouse user rests on a face, sees `SKETCH ⟨K⟩`,
   and has learned a durable accelerator without opening anything.
2. **The band tooltip prints it** — `ToolButton`'s `shortcut` prop already
   renders a `Kbd`. It is **hover-only**, so it is reinforcement, not teaching;
   `CreateStrip.tsx`'s own docstring already argues that a hover-only channel
   fails the flow mandate. B3 passes `shortcut={partVerbKey(...)}` to the five
   ToolButtons that lack one.
3. **The shortcut sheet** (`?`) picks the rows up for free because it is derived
   from the same table. **Do not hand-type a sheet row.**

### 3.4 Why `Enter` is not re-specified

`KEY_ACCEPT_PROPOSAL = "Enter"` has a written rationale in `registry.ts` and it
still holds: accept means accept everywhere in this product. **Enter stays bound
to "accept the showing note" on every note, and stays unprinted.** The chip
prints the *letter* because the letter is what the user can carry away — it
keeps working after the chip is gone, and `Enter` does not.

Consequence, and it is a real edit: `hover-sketch.spec.ts:256` asserts
`toContainText("↵")`. **B1 rewrites that assertion to read the registry**
(`toContainText(partVerbKey("sketch")!.toUpperCase())`) so the glyph and the
binding cannot drift — which is the property the spec's own comment asks for.

### 3.5 The cross-agent contract — read this twice

Two window keydown listeners will want the same letter: the note's (accept the
proposal) and `PartPage`'s existing opener table (start the verb's own flow).
If the opener wins, Extrude opens **without the profile** — which looks almost
right and is exactly the silent-wrong-result class this repo keeps paying for.

**Binding, non-negotiable, and each half is one line:**

- **B1:** the note binds its keys on the **window in the capture phase**
  (`{ capture: true }`) and calls `event.preventDefault()`. Capture on `window`
  runs before any bubble-phase `window` listener, so the order is deterministic
  rather than registration-order luck.
- **B2:** the existing create-shortcut handler (`PartPage.tsx:4474`, bubble)
  gains one guard as its first statement: `if (event.defaultPrevented) return;`

Neither half works alone, and neither half fails loudly. Land both.

---

## 4. When a proposal is wrong

**A proposal that cannot be ignored cheaply is worse than none.** Three
mechanisms, and only three.

1. **Dismiss by doing anything else.** Any `pointerdown` or `wheel` in the
   viewport withdraws the note — the existing chip already does this, for the
   good reason that a camera gesture invalidates a screen-anchored note. So the
   cheapest possible dismissal ("I just start orbiting") costs nothing and needs
   no learning. Opening any command also withdraws it.
2. **`Esc` withdraws it explicitly.** While a note is showing and no command is
   open, `Esc` withdraws the note **and stops there.** This does not change what
   `Esc` means — it is still "back out one step", and the note is now the
   frontmost step. It **displaces nothing**: the flow audit measured `Esc` at
   model idle with nothing armed as *"nothing at all, any number of times"*, so
   the key was free at exactly the moment the note is live. Every other `Esc`
   behaviour is untouched (§5).
3. **One offer per subject, per session.** This is what "dismissing teaches the
   app something" means here — not a preference model (unfalsifiable, too
   clever), but a one-shot: **a note is written at most once for a given
   subject.** Withdraw the extrude offer for `Sketch1` and `Sketch1` never
   offers again this session. Keep the seen-set local to the proposal module
   keyed on the subject's id; it needs no store slice.

**Explicitly rejected: a timeout auto-dismiss.** A chip that vanishes on a timer
while you are reading it is the nag's evil twin. The note persists until it is
acted on, dismissed, or invalidated by a camera move.

**The nag test a reviewer should run:** finish a sketch, press `Esc`, finish
another sketch — the second offers (different subject), the first never does
again. Orbit once at any point — the note is gone and nothing brings it back.

---

## 5. What must not change

### 5.1 Muscle memory this wave is forbidden to break

- **Every existing letter keeps its meaning.** `P S L H D O I` (pattern, sweep,
  loft, shell, draft, hole, mirror), `M` measure, `V`/`Shift+V` isolate, `?`
  sheet, `N` / `/` on the registers, `0–5` + `Home` views, `Alt+↑/↓` reorder.
  **And every sketch-mode letter**: `L R C A S J K F I U B` tools, the fifteen
  constraint verbs, `N` construction, `G` snap. Not one moves.
- **`Enter` keeps meaning accept** — of a showing note, of an editor's value, of
  the register's name field. W2 adds no second accept vocabulary.
- **`Esc` keeps meaning "back out one step"**, and keeps all four behaviours the
  flow audit certified: drops an in-progress entity while leaving the tool
  armed; dismisses the draw-time size cells **while keeping the drawn shape**;
  closes an open editor without creating the feature, **whether or not focus is
  inside it**. W2 only adds a new frontmost step.
- **A viewport click never destroys an open command.** Unchanged.
- **Positions.** The tool band's group order, eyebrows and x-positions; the
  sketch strip; the timeline; the ViewCube bottom-right; the view rail; the
  inspector on the right. A hand that goes somewhere without looking keeps
  going there.
- **The band may not grow.** Measured this pass at the 1280×800 floor: the band
  is **1241 px of 1280**, every tool is **32 px** (the icon tier), 39 px of
  slack. **No new band cell** (the SCOPE cell costs 104 px and already forces
  EXPORT and INSPECT to shed their words), no change to `labelPriority`, no
  wider label.

### 5.2 Surfaces that are already good — do not redesign in passing

Both audits list these. Touching one is out of scope and will be reverted:

- **The extrude drag handle** (`extrude-depth-handle` / `-readout` / `-steps`).
- **The revolve editor** — one keystroke from a solved profile to a correct
  feature, with inferred axes. Copy its thinking; do not edit its code.
- **The rebuild-failure state** — named cause, named parameter, last good body
  still on screen, `role="alert"`, dismissible. This is the product's standard.
- **Feature delete + its dependents confirm.**
- **The draw-time dimension cells** as a concept (FLOW-A1 owns their one bug).
- **The cursor-mark / snap-marker vocabulary** (idiom B). It is deliberately
  quieter than a proposal. Do not "upgrade" it.
- **The SCOPE cell and its `×`** (idiom C).
- **The shortcut sheet's derivation** — extend the tables, never hand-type a row.

---

## 6. The signature — where boldness is spent, and where it is not

**Spent:** the **drafting leader note**. One object — dot, two-tone hairline
stub, stamped brass chip — extended to the moment that costs the most
(8 of 15 measured hunts). The boldness is that a CAD app annotates its own model
the way the drawings it produces are annotated, and that this is the *only* way
it ever speaks about what comes next.

**Deliberately not spent — every one of these is a defect if it appears:**

- No new colour. **Brass is the only accent this product has**; the palette is
  `carbide / anvil / hairline / etch / mist / gauge / brass / brassHover /
  aluminum / flag` and W2 introduces nothing. (The repo has 7 hex literals
  total and zero duplicated between DOM and WebGL. Keep it.)
- No new token except `proposal.chipWidth: 112 → 120`.
- No motion. No fade-in, no slide, no pulse, no attention-getting loop.
- No new panel, no new band cell, no toast, no badge, no pill, no coachmark,
  no numbered "step 1 of 3", no onboarding tour.
- No second signature in the band. The band's contribution is a **6 px dot**
  (§7, FLOW-B3) and that is intentionally the quietest thing in the wave.

Chanel's mirror: the thing removed from the first draft was the noun in the chip
(`EXTRUDE SKETCH1`). The leader already says it, in space.

---

## 7. Per-item direction

### FLOW-B1 — the solve writes the offer · `apps/web/src/viewport/**`

**Trigger:** the sketch's solve completing — the state transition itself, not a
hover, not a dwell, not a menu. `eval-status` turns `Solved` after
FINISH SKETCH. **No dwell delay**: the dwell exists to stop a pointer sweep
proposing things, and there is no pointer in this path.

**Anchor:** the screen projection of the solved profile loop's **area centroid**.
**Skip the note entirely** if that point falls outside the frame's safe margin
(`proposal.margin`) or the loop's screen bbox is shorter than `proposal.chipHeight`
— a leader pointing at a speck or off-screen is a lie, and the `E` key still
works, which is the honest fallback.

**Copy:** visible `EXTRUDE`; `Kbd` = `partVerbKey("extrude")`;
`aria-label` = `Extrude Sketch1`; `role="status"` on this note only.

**Accept:** call the same path the toolbar's Extrude button calls
(`onNewExtrude`), so the two cannot drift — the existing `acceptSketchProposal`
is the pattern to copy verbatim.

**Also yours:** generalising `SketchProposal` → one `ProposalNote` with at most
one note and the pointer-wins priority (§1.1); the capture-phase key binding
(§3.5); the `chipWidth` token bump — **exactly two lines of
`packages/design/src/tokens.ts`, nothing else in that file**; and the
`hover-sketch.spec.ts:256` glyph assertion (§3.4).

> **Trap, and it will cost you an hour if you skip it.** `tokens.ts` feeds the
> Tailwind preset, which Vite reads **once at boot**. After changing
> `chipWidth`, **restart Vite** — otherwise `w-proposal` keeps the old value,
> the chip mis-measures, and it reads as a half-finished component. See
> `CLAUDE.md` ("a Tailwind preset change is a build-config change").

**PartPage footprint:** one import, one `<ProposalNote>` beside the existing one
inside the same `hud={…}` block (`PartPage.tsx:4989`), one `onAccept` callback
beside `acceptSketchProposal` (`:4096`). Nothing else.

**Assertion:** finish a sketch; **without moving the mouse**, assert a visible
element whose accessible name contains "Extrude"; press `e`; assert
`extrude-editor` is visible and `extrude-profile` names that sketch. Negative
controls: the note is gone after any viewport `pointerdown`; and after `Esc` it
does not return for the same sketch.

### FLOW-B2 — the five verbs get their keys · `apps/web/src/shortcuts/**`

**This is the wave's first commit** — B1 and B3 both read `partVerbKey` from it.
It is also the smallest.

Ship: the `id` field + five rows on `PART_CREATE_SHORTCUTS`; `PartVerbId` and
`partVerbKey` (§3.2); the five opener rows in `PartPage.tsx:4481`'s table with
their existing gate grammar (`e`/`r` gated on the same condition `new-extrude` /
`new-revolve` use, `f`/`c` on `hasBody`, `k` always); and the
`if (event.defaultPrevented) return;` guard (§3.5).

**Assertions:** with a solved sketch and nothing focused, `press("e")` opens
`extrude-editor`. A registry unit test that **no two commands claim one key
within one mode**, asserting the expected row COUNT as well as the property —
a uniqueness check over an empty list passes vacuously, which is this repo's
most-repeated defect. And one test that the shortcut sheet prints all five.

### FLOW-B3 — one accented next verb after a build · `apps/web/src/components/**`

**Scope boundary with B1, stated so neither fires on the other's transition:**
**B1 owns the sketch→extrude transition. B3 owns every transition that produces
a BODY.** `sketch` is never in B3's table.

**The mark: a 6 px brass dot at the tool's top-right corner.** The same anchor
dot the viewport leader uses — one mark, two densities, because a 32 px band
cell has no room for a leader. It costs **zero width**, which §5.1 requires.

- It must **not** be the active scribe (`bottom-0.5 h-px bg-brass`,
  `aria-pressed`) and must not make the glyph brass — both already mean
  "this tool is on".
- Draw it as raw SVG (`<svg width={6} height={6}><circle cx={3} cy={3} r={2.5}
  fill={color.brass} />`), **not Tailwind sizing**. This theme's spacing scale
  is closed at 12 and an unknown utility silently emits nothing, producing a
  zero-area element that looks perfect in the DOM — three separate defects this
  year. `scripts/check-tailwind-scale.py` gates it.
- Carries `data-next-step="true"` — the attribute the flow audit's acceptance
  test already names. **Exactly one tool in the band, or none.**

**What it proposes — a small explicit table, in one file, one reason per row.
A row exists only where we can name why.**

| Feature just built | Accent | Why |
|---|---|---|
| the **first body** in the part (any verb) | `new-fillet` | this is the instant the whole MODIFY group stops being disabled; a band that quietly unlocks eight tools and says nothing is the flow test failing in its purest form |
| `extrude` | `new-extrude` | boss-then-cut is the common pair |
| `revolve` | `new-revolve` | as above |
| `hole` | `new-hole` | measured: two holes is the median case, and today the second shares nothing with the first (audit F-6) |
| `fillet` | `new-fillet` | edges are broken in passes, not all at once |
| `chamfer` | `new-chamfer` | as above |
| `edge_flange` | `new-edge-flange` | a sheet part folds several legs |
| everything else | **nothing** | we cannot name why, so we do not guess |

The first-body row wins when both apply. **Do not add rows for divination**
("after an extrude you probably want a shell"). Fortune-telling in a tool band
is the templated result this wave exists to avoid.

**Copy — the accented tool's `caption` (the existing tooltip second line):**

- repeat rows: `Another ${label.toLowerCase()} on this body` → *"Another hole on
  this body"*
- first-body row: `Round the new body's edges`

Active voice, specific, ≤33 chars (the precedent is *"Repeats Hole1, not the
whole body"*). The caption already reaches screen readers via
`aria-describedby` — that wiring is `ToolButton`'s and needs no change.

**Also yours:** `shortcut={partVerbKey(id)}` on the five ToolButtons that lack
one (`new-sketch`, `new-extrude`, `new-revolve`, `new-fillet`, `new-chamfer`).

**Dismissal:** the accent has no dismiss control **by design** — it occupies no
space and blocks nothing. It clears when any command opens, on `Esc`, and it is
written once per build (never re-armed for the same feature).

**PartPage footprint:** one `nextStep={…}` prop on `<CreateStrip>`. The table
itself is a pure module in your own subtree (`components/nextStep.ts`) with unit
tests, so it is testable without a browser.

**Assertion:** create an extrude; assert exactly one tool carries
`data-next-step="true"`, that it is enabled, and that its dot measures **non-zero
in both axes** (not merely that the element exists — a zero-area mark is this
repo's signature failure). Open any command; assert the count drops to 0.

---

## 8. The one thing I cannot decide without seeing it built

**Whether the band's 6 px proposal dot is legible enough at 1280×800 to count as
"visible from the current state."** Everything else in this brief is decided
from measurement; this one is a judgement about a small mark on a 32 px icon at
the top of a frame while the user's eyes are on the body in the middle of it,
and I do not trust my own guess about it more than a screenshot.

**B3 ships the dot first**, captures before/after at 1280×800 and 1600×1000, and
I re-audit. **The escalation, pre-specified so nobody invents a third thing:** if
the dot does not read, the accented tool *additionally* takes `text-brass` on its
glyph (dot + brass glyph together, which is then distinguishable from `active`
by the absence of the bottom scribe). **Not** a wider label, **not** a band
cell, **not** motion, **not** a second colour. If both together still do not
read, the finding is that the band is the wrong surface for this and it moves to
the viewport in a later wave — which is a direction decision, not a builder's.

---

## 9. Territory, order, and the shared file

`apps/web/src/routes/PartPage.tsx` (5 690 lines) is the integration point for
**all three** items and is in none of the three subtrees. Unallocated, it is the
wave's collision. Allocated, each builder's footprint is a few lines:

| Builder | Owns outright | `PartPage.tsx` — the only hunks you may touch |
|---|---|---|
| **B1** | `apps/web/src/viewport/**`, `hover-sketch.spec.ts`, **2 lines** of `packages/design/src/tokens.ts` (`chipWidth` + its comment) | one import; one `<ProposalNote>` inside the existing `hud={…}` block at **:4989**; one `onAccept` callback beside `acceptSketchProposal` at **:4096** |
| **B2** | `apps/web/src/shortcuts/**` | the `openers` record at **:4481** (five rows + deps) and the `defaultPrevented` guard as the first statement of `onKeyDown` at **:4474** |
| **B3** | `apps/web/src/components/**` (incl. `CreateStrip.tsx`, new `nextStep.ts`) | one `nextStep={…}` prop on `<CreateStrip>` |

**Order:** B2 commits first (smallest, and both others import `partVerbKey` from
it). B1 and B3 are then fully parallel. B1's registry-derived fallback
(`?? "↵"`) means no commit is ever broken by the ordering, which is the point.

**Standing rules that apply here with unusual force:**

- Worktrees, and `git rev-list --count HEAD..origin/<branch>` as your **first**
  command — the container's clone is seeded at the last merge into `main` and
  has arrived stale nine times running.
- Read `git diff --cached` **in full** before committing. Three of you will have
  `PartPage.tsx` dirty at overlapping moments and `git add <file>` takes all of
  it.
- Restart Vite after the `tokens.ts` change (B1) — see the trap in §7.
- `just lint` in full, not `ruff check`; `uv run ruff`, never a PATH `ruff`.

---

## 10. What I will re-audit, and against what

Before/after at **1280×800 and 1600×1000** for each item, plus:

1. **The voice test.** Screenshot the face-hover offer and the solve offer side
   by side. They must read as the same object saying two things — same chip,
   same leader, same type, different verb. If they read as two components, the
   wave failed its own goal regardless of the tests.
2. **The hunt test.** Re-run the flow ledger's Part 1 (`AUDIT-FLOW-2026-09` §
   Part 1). **8 of 15 hunts were the solved-sketch transition; the target is
   0 for that row**, and no new hunts introduced elsewhere.
3. **The nag test** (§4) and the **two-live-proposals test** (§1.1).
4. **Keyboard-only pass.** Sketch → solve → `E` → type → `Enter`, with no
   pointer events in the whole run.
5. **Zero-area sweep.** Every new mark measured in both axes with
   `getBoundingClientRect`, and every new pick target checked with
   `elementFromPoint` at its centre. No `force: true`.
6. **Contrast + focus.** New brass-on-anvil text ≥ 4.5:1 (the chip measures
   7.85:1 today — keep it), visible focus ring on the chip, `role="status"` on
   the solve note only.
