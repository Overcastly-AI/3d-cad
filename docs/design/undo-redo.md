# Design — Undo / redo v1 (part feature tree)

Status: **accepted** (2026-07-17). Scope: full undo/redo of the **part feature
tree** — every modeling edit in an editing session (feature create / update /
delete / reorder) is reversible, with `Ctrl/⌘+Z` / `Ctrl/⌘+Shift+Z` and toolbar
controls. Assembly undo (instances/mates) is the immediate fast-follow (UR3),
same mechanism. Sketch-internal constraint undo is a later, finer-grained layer.

## The load-bearing decision: server-side state snapshots, not client command-inversion

A parametric feature tree cross-references by **entity ID** (`feature_dependencies`:
a fillet references an extrude's edge by the extrude's feature id; a
sketch-on-face references its base feature). The naive client-side approach —
record each mutation as an inverse command and replay it — **breaks referential
integrity on redo**: re-creating a deleted feature mints a *new* server id, so
every downstream reference that pointed at the old id is orphaned. Command
inversion also can't see server-side cascade effects (dependent-feature
invalidation, order re-normalization).

**Therefore undo/redo is server-side and snapshot-based.** The document keeps a
bounded, ordered history of **full feature-tree states**; undo/redo restores an
adjacent snapshot *verbatim, preserving every entity id*. This is:
- **Correct on references** — ids come from the snapshot, never regenerated, so
  `feature_dependencies` stays valid across any undo/redo distance.
- **Uniform** — one snapshot/restore path covers create/update/delete/reorder
  identically; no per-op inverse logic to get wrong (the DRY win).
- **Durable + reload-safe** — history lives with the document, not in volatile
  client memory; a refresh doesn't lose the stack (and it's collaboration-ready
  later — a shared document has one authoritative history).

The cost is snapshot storage; a parametric tree is small JSON and the ring is
bounded (below), so this is cheap and bounded by design.

## Model

Per part, a linear history of tree states with a cursor:

- `snapshots[0]` = the tree state **before the first edit of the session's chain**
  (the baseline you can undo back to). Seeded lazily on the first mutation.
- Each mutating op, in the **same transaction** as the tree write, appends the
  **resulting** post-op state and advances `cursor` to it.
- **Undo** = restore `snapshots[cursor-1]`, `cursor -= 1` (no-op at 0).
- **Redo** = restore `snapshots[cursor+1]`, `cursor += 1` (no-op at the top).
- A **fresh edit while `cursor` is not at the top truncates the redo tail**
  (`snapshots[cursor+1:]` dropped) before appending — the standard linear-history
  rule; branching history is out of scope.
- **Bounded ring:** cap at `HISTORY_MAX` (start 50). Appending past the cap drops
  the oldest (and its baseline role shifts forward — you can undo within the
  window, not before it). Log/telemetry the drop; never silently imply infinite.

A "snapshot" is the document's full mutable child state: the ordered `features`
(id, order_index, type, param_version, params, name) + `feature_dependencies` +
the `rollback_feature_id` pointer. Restore = replace the part's features/deps with
the snapshot's (ids verbatim) inside one transaction.

## Version / OCC interaction

Undo and redo **are document edits**: each bumps `tree_version` exactly like a
feature mutation, and each takes the client's `expected_tree_version` (stale →
422, same guard as every other write). The response returns the restored tree +
the new `tree_version` so the client re-renders authoritatively (re-evaluate for
geometry, as any tree change does). Undo/redo never mutate stored geometry
directly — they restore the tree and the normal evaluate path recomputes.

## Endpoints (documents, proxied by gateway — reuse the existing auth hop)

- `POST /api/v1/parts/{id}/undo` → `{expected_tree_version}` → restored tree +
  new version, or `409/422`.
- `POST /api/v1/parts/{id}/redo` → same shape.
- The tree GET response gains `can_undo: bool` / `can_redo: bool` (cursor at
  bounds) so the toolbar reflects availability without a second call.

No new gateway auth surface — mirror the existing `parts` proxy (principal via
`X-Loft-User`, envelopes re-surfaced).

## Slice sequence

- **UR1 (backend + contract):** the snapshot store (recommend a `part_snapshots`
  table keyed `(part_id, seq)` + a `history_cursor` on `parts`, bounded prune —
  scales better than a fat JSON column on the row) + snapshot-on-mutation hooked
  into all four feature ops + undo/redo endpoints + `can_undo/can_redo` on the
  tree response; alembic migration; gateway proxy; `just gen`. **Correctness is
  the deliverable** — tests: undo/redo restores a **byte-identical** tree
  (ids + order + params) at any distance; a fillet-on-extrude survives
  delete-extrude → undo (dependency intact, ids preserved); fresh-edit truncates
  redo; ring drop at the cap; OCC stale → 422; undo at baseline / redo at top are
  clean no-ops (not errors).
- **UR2 (frontend):** toolbar undo/redo buttons (design-system, disabled via
  `can_undo/can_redo`) + `Ctrl/⌘+Z` / `Ctrl/⌘+Shift+Z` (and `Ctrl+Y`) guarded by
  `isTypingTarget` (never hijack a text field); issue the endpoint, refresh the
  tree + viewport, surface the stale-version 409 as a soft reload. e2e: extrude →
  fillet → undo twice → both gone → redo twice → both back with the fillet still
  bound to the extrude; keyboard + button parity.

## Out of v1 (filed)

Assembly undo/redo (UR3 — same snapshot mechanism over instances+mates);
sketch-internal (per-constraint) undo; cross-document / global undo; persistent
redo across a full page reload beyond the server ring; collaborative
per-user undo scoping.
