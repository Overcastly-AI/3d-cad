# UX Flow Audit — the novice lens ("could my grandpa follow the flow?")

**Date:** 2026-07-24 · **Auditor:** frontend-qa (founder-directed special pass)
**Method:** live walkthrough of the real stack (native boot, isolated ports
:8040-8042, Playwright-driven Chromium at 1440×900), role-playing a
computer-literate, CAD-illiterate first-timer. Every claim below was
reproduced against the running app; evidence in `docs/screenshots/audit-ux/`.
**Scope note:** this is NOT the design-system audit (that's `UI-REVIEW.md`).
It asks one question at every step: *would a smart person with zero CAD
background know what to do next, and why?*

The task: sign up cold and produce a 100 × 50 × 20 mm box. The run completed
it end-to-end (`24-box-done.png` — extents readout `100 × 50 × 20`, volume
100,000 mm³), then probed the feature editors, error states, and recovery
paths.

---

## What already works for a novice (credit where due)

These are real strengths — the fixes below should not regress them.

- **Empty states teach.** The parts register says *"Name your first part to
  open a fresh sheet — sketch it, extrude it, and it will be filed here"*
  (`03b-after-register-retry.png`); an empty part says *"Start with a Sketch
  — pick a plane, then draw"* (`05-modeler-empty-part.png`). There is a
  guidance chain from signup to the first feature.
- **Disabled tools explain themselves** — to mouse, keyboard, and screen
  readers. Extrude before a sketch exists is `aria-disabled` (still
  focusable), hover/focus shows "Solve a sketch first"
  (`20-extrude-disabled-hover.png`, `20b-extrude-disabled-focus.png`).
- **The ghost planes are genuinely clickable** in the viewport during plane
  pick — the novice's instinct (click the big square) works. Verified.
- **Mode is always legible.** Breadcrumb changes (SKETCH / PICK A PLANE /
  EXTRUDE), and an open command swaps the toolbar for an "IN COMMAND ▸ Mirror
  · CANCEL ESC · OK ENTER" band (`26b-…png`).
- **The Extrude editor is novice-grade already**: Profile / Distance (default
  10 mm, autofocused) / Add–Cut / Merge result with a plain subtitle, CANCEL
  Esc / CREATE Enter (`23-extrude-editor.png`). Enter-to-create works.
- **Errors never silently ship a wrong model.** The over-deep hole shows
  `ERR` + SOLVE `Failed` in the tree with genuinely good copy: *"This hole
  would break through the far side of the body. Reduce the depth or recess,
  or switch to Through all."* (`30-hole-too-deep-error.png`).
- **Destructive actions confirm**: *"Delete Grandpa Box? This cannot be
  undone."* inline in the row (`34-delete-part-confirm.png`).
- **Undo works and is honest** — Ctrl+Z cleanly removed the errored hole
  (`31-after-ctrl-z.png`); redo shows disabled when empty.

---

## Findings (severity-ranked)

Severity scale: **P0** hard-stuck · **P1** novice likely gives up · **P2**
confusion, recoverable · **P3** wording/polish.

No P0s were found: every state reached in the walkthrough had a *visible*
exit (worst case, an on-screen CANCEL button).

### P1 — the app breaks its own Escape promise when focus is outside an editor

The in-command band advertises **"CANCEL — ESC"**, but editor Escape handlers
live on the editor panel's DOM subtree (`onKeyDown` on the wrapper div,
`MirrorEditor.tsx:88`, same pattern in every editor). Click **Mirror** from
the toolbar → focus stays on the toolbar/body → press Esc (exactly what the
band says) → **nothing happens**, and the entire toolbar is locked ("Finish
mirror first"). Verified live: two Escapes, editor still open
(`26b-mirror-escape-ignored-in-command-band.png`). Extrude/Revolve only
escape correctly because their distance field autofocuses (focus lands
inside); Mirror autofocuses nothing, so its advertised Esc is dead by
default. Esc never *destroys* work (good) — it just doesn't work.
**Fix (backlog-sized):** while `activeCommand` is set, a document-level
keydown listener routes Escape to the active editor's cancel (CreateStrip
already owns `activeCommand`); editors keep their local handlers.

### P1 — exact dimensions are the give-up point of the golden path

A novice reaches "a 3D slab" plausibly, but the *100 × 50* part requires the
select-an-edge → press **D** (or CONSTRAIN ▸ DIMENSION ▸ Distance) idiom, and
nothing in sketch mode ever suggests it. The status readout says "nothing
selected · 5 applied" but never *"select a line, then Dimension to set its
length."* The DIMENSION menu (once found) is good — items with D/R/E
shortcuts (`13b-dim-menu-open.png`) — but the bridge to it is tribal
knowledge. This is where the exact-box task most likely dies.
**Fix:** selection-contextual verb hints in the sketch status bar — when one
line is selected, show "Line · D set length · H horizontal · V vertical"; when
nothing is selected and DOF > 0, show "Click a line to dimension it."
(`22-sketch-100x50-dimensioned.png` for the current silent state.)

### P1 — extrude on an open profile fails with *revolve* instructions

Draw an open L of two lines, save the sketch (allowed, no warning), extrude
it (the profile dropdown happily lists it, CREATE enabled) → tree shows
`PROFILE_NOT_CLOSED`: *"…for a revolve, snap a construction centerline's two
ends onto the profile's open corners on the axis…"*
(`33b-open-profile-extrude-error.png`). The one friendly string in
`featureErrors.ts` is revolve-specific but shared by every feature — for an
extrude it is actively misleading; a novice will hunt for an "axis" that has
nothing to do with their problem.
**Fix:** key friendly copy on `(code, feature.type)`; extrude's variant is
one sentence ("Close the gap between the lines so the outline is a complete
loop, then extrude"). Bonus P2: mark open sketches in the profile dropdown
("Sketch2 — not closed") instead of letting the pick fail downstream.

### P2 — "Solve a sketch first" gates the whole flow in solver jargon

The single most-seen gate reason on the golden path uses "solve" — homework,
not modeling, to a novice. Same family: the sketch status bar's
`SOLVE — DOF 10 · UNDER-CONSTRAINED` (`15-after-100-entered.png`) reads as a
warning with no explanation and no hover to decode it.
**Fix:** "Finish a sketch first" for the gate; give the DOF chip a tooltip in
words ("The shape isn't fully pinned down — add dimensions. Fine to continue.")
— keep the DOF number for experts.

### P2 — the disabled-tool tooltip is clipped by the feature-tree panel

The extrude gate tooltip renders *under* the floating FEATURE TREE panel —
at default layout the reason reads "…olve a sketch first"
(`20-extrude-disabled-hover.png`). The one place we explain ourselves, half
covered. **Fix:** raise the tooltip layer above floating panels (z-token in
`packages/design` ToolButton tooltip), or flip it to the free side.

### P2 — the Hole editor covers its own "click a point" target

Picking the front face seeds a centre point node that renders *behind* the
editor panel; in point-pick mode the visible dot is unclickable — the panel
swallows the click (`29-hole-point-under-editor.png`; Playwright: "subtree
intercepts pointer events", had to dispatch programmatically). A novice in
"PICKING… (CLICK A POINT)" clicks the dot the UI just drew and nothing
happens. **Fix:** while a pick session is armed, make the editor panel
click-transparent-when-overlapping (or auto-dodge the panel away from the
picked face's screen bounds).

### P2 — every first dimension asks "Role: DRIVING / DRIVEN"

The dimension popover (`14-distance-dim-prompt.png`) is otherwise great
(value autofocused, unit shown) but confronts a first-timer with a
driving/driven toggle and an optional Name field — expert concepts, zero
explanation. **Fix:** default DRIVING, collapse Name/Role behind a "More"
disclosure; one-line tooltips ("Driving sets the size; driven just reads it").

### P2 — features can't be deleted, and the alternative is hover-only "SUPP"

The tree has no per-feature delete; an errored experiment (Hole2 ERR) can
only be removed by an immediate Ctrl+Z, or silenced via a hover-revealed
suppress control whose state label is "SUPP" (`32-feature-row-hover.png`,
`30b-tree-after-hole-attempt.png`). A novice with a red row and no visible
"remove" will conclude they've broken the file. **Fix:** per-feature delete
in the row's hover/context actions with a downstream-consequence confirm
("Extrude1 uses this sketch — it will fail"), which is also the missing
depended-on-delete story; spell "Suppressed".

### P2 — undo/redo are 32 × 16 px targets

Undo is visible (good — not chord-only) but the buttons are 16 px tall
(`24-box-done.png`, top-left HISTORY group) — under WCAG 2.5.8 minimum target
size and hopeless on the tablet-class viewports the QA mandate names.
**Fix:** pad the History group targets to ≥ 24 px; keep the visual weight via
the icon, not the hit area.

### P2 — feature errors land where the novice isn't looking

Submitting a doomed hole/extrude closes the editor immediately; the error
appears in the small left tree while the eye is on the (vanished) panel or
the unchanged model. First impression is "it worked" until the red row is
noticed. **Fix:** on submit-then-error, keep focus continuity — a transient
callout anchored where the editor was ("Hole2 failed — see feature tree"),
or scroll/flash the errored row.

### P3 — wording list (golden path first)

| Where | Today | Novice-safe alternative |
| --- | --- | --- |
| Plane pick chips | `XY · XZ · YZ` | subtitle with the ViewCube's own words: "Top · Front · Side" (`06-sketch-plane-pick.png`) |
| First-run copy | "sketch it, extrude it" | "draw a shape, pull it into 3D" |
| Sketch save strip | "4 entities" | "4 lines" |
| Finish group | unlabeled ✓ / ✗ icons | keep icons, add SAVE / DISCARD text labels (`07-sketch-mode-entered.png`) |
| Tree marker | `ROLLBACK` | "◂ history stops here" tooltip |
| Hole types | `C'BORE / C'SINK` | expand on tooltip: "Counterbore — flat recess", "Countersink — cone recess" (`28-hole-editor.png`) |
| Export captions | `B-rep / Mesh` | keep, add "exact CAD file / 3D-print file" |
| Toolbar tooltips | label + shortcut only | render the existing plain aria-label line ("Extrude — add or cut a sketch profile") in the visible tooltip — the copy is already written, sighted users just never see it |
| Sign-in card | "Parametric CAD" | one sentence: "Design real 3D parts in your browser" (`01-cold-landing.png`) |

---

## Flow-logic verdict (walkthrough script answers)

1. **Cold start:** guidance exists and chains (register → named part → "Start
   with a Sketch"). Jargon density is the only friction; no dead ends.
2. **The box, knowing nothing:** four walls, none fatal — (1) "pick a plane"
   is unexplained but any click succeeds; (2) draw tools are unlabeled icons,
   though the rectangle glyph is guessable; (3) **exact sizing** — the P1
   above, the probable give-up point; (4) finish = ✓ icon. Extrude itself is
   well-guided (enabled + highlighted + sensible default).
3. **Language:** table above; the pattern is that prompts say WHAT ("Pick a
   plane") but rarely WHY/WHAT-NEXT ("…to choose the flat surface you'll draw
   on").
4. **Mistake recovery:** undo visible and true; part delete confirms; the Esc
   promise is broken out-of-focus (P1); feature removal is undiscoverable (P2).
5. **Errors:** hole_too_deep is exemplary; profile_not_closed is
   wrong-context (P1); placement misses the eye (P2).
6. **Flow order** matches the novice mental model (draw → make 3D → refine);
   nothing demands CAD-brain sequencing. The system's real gap is vocabulary
   and idiom discovery, not flow architecture.

**Could grandpa get from signup to a 3D box, unaided?** A box of *some* size:
yes, plausibly in 15–25 minutes — the guidance chain and the clickable planes
carry him. The *exact* 100 × 50 × 20 box: roughly even odds he gives up at
the dimensioning step; if he finds the DIMENSION menu he finishes in ~5 more
minutes.

## Top 5 changes for novice success (without dumbing down the expert tool)

1. **Honor the advertised Esc globally** while a command is open (P1) — a
   keyboard contract fix, invisible to experts except that it now works.
2. **Selection-contextual verb hints in the sketch status bar** (P1) — the
   status bar already exists; experts read DOF, novices read "D set length".
3. **Context-correct error copy** — key `featureErrors.ts` on feature type,
   and flag open profiles in the extrude/revolve dropdown before submit (P1).
4. **Plain-words pass on the golden path** — "Finish a sketch first",
   Top/Front/Side plane subtitles, DOF tooltip, DRIVING/DRIVEN behind a
   disclosure (P2s) — pure copy/markup, no behavior change.
5. **Show the "what it does" line in every tool tooltip** (it already exists
   as the aria-label) + unclip the tooltip layer (P2) — turns the wall of
   fifteen jargon verbs into a self-teaching palette for the price of
   rendering a string.

## Evidence index (docs/screenshots/audit-ux/)

Predecessor pass (kept, verified): `01`–`16` cold start → register → empty
states → plane pick → sketch → rectangle → dimension menu/popover →
under-constrained status → reopened part.
This pass: `20`/`20b` disabled-extrude tooltip (mouse/keyboard) ·
`22` dimensioned 100×50 · `23` extrude editor · `24` finished box ·
`25` fillet editor · `26`/`26b` mirror editor + dead-Esc lock ·
`27` revolve editor · `28`/`28b`/`29` hole editor, face pick, covered point ·
`30`/`30b` hole_too_deep · `31` undo · `32` feature-row hover ·
`33`–`33c` open-profile extrude error · `34` part-delete confirm.
