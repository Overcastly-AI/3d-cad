# `loft-script` — Loft's public Python scripting API

Model parts from code, through the same gateway the web app uses.

```python
import loft

with loft.connect("http://localhost:8000", token=TOKEN) as session:
    part = session.new_part("Bracket")

    sk = part.sketch(on="XY")
    sk.rect(40, 25)
    sk.solve()

    part.extrude(sk, 10)

    print(part.mass_properties().volume)   # 10000.0
    part.export("bracket.step")
```

## The one design constraint

**This library is another client of the gateway, exactly like `apps/web`.**

It imports no kernel, touches no database, and reaches nothing the browser
cannot reach. The alternative — a scripting API that drives the geometry
service directly, or writes feature rows into Postgres — is a *second product*:
it drifts, it develops its own bugs, and every feature we ship afterwards has to
be built twice. The constraint is enforced, not just documented:

- every call names an operation from the generated table
  (`loft/_operations.py`), which is derived from
  `packages/contracts/gateway.openapi.json`;
- the transport **refuses** to send a request body whose model is not the one
  the contract declares for that route (`ContractMismatch`) — so the library
  cannot grow a private payload shape the browser never sends;
- the library refuses what the UI refuses: an unsolved sketch (the workspace
  leaves extrude disabled), an export with no body (the export button reads
  "No body"), a non-positive extrude distance (the server's own validator).

## Where the types come from

The wire DTOs are `py_kit.schemas.*` — the *same pydantic classes the services
serve*. They are imported, never regenerated.

That is a deliberate asymmetry with `packages/ts-client`, which **is**
generated. TypeScript cannot read a pydantic model, so it has no choice.
Python can. Deriving a second set of Python classes from an OpenAPI document
that was itself derived from those classes is a round trip that only loses
things — validators, cross-field model validators, shared derivations like
`is_stale_for_tree` — while creating a drift surface where there was none.
Hand-written *or generated* duplicates of API types are the defect the DRY rule
names.

What a Python client genuinely cannot import is the **routing**: the method,
the URL template, and which component schema the gateway declares for each
operation's body. Those live in FastAPI decorators. So exactly that is
generated, by `scripts/gen-py-operations.py`, wired into `just gen` and diffed
by `just gen-check`. A renamed route becomes a pyright error at the call site
rather than a 404 in somebody's script.

## Covered verbs

| Area | In |
| --- | --- |
| Auth | `register`, `connect` (token or email/password), `session.user`, `session.token` |
| Parts | create, list, get, rename, set display unit, delete |
| Sketch entities | line, rectangle (dimensioned + grounded), circle (by radius **or** diameter), arc, point, construction geometry |
| Sketch constraints | coincident, horizontal, vertical, fixed, parallel, perpendicular, tangent, equal, concentric |
| Sketch dimensions | distance, radius, diameter — each with `name=` and `expression=` (the parametric half) |
| Solve | `sketch.save()` / `sketch.solve()`, with `SketchNotSolved` carrying the conflicting/redundant constraint indices |
| Features | extrude (add/cut, direction, merge), re-parametrize an extrude, read the tree, delete a feature |
| Query | `part.evaluate()`, `part.mass_properties()` (volume, area, centroid, bbox, face/edge/shell counts) |
| Export | STEP, STL, 3MF, GLB — to bytes or to a file with format inferred from the suffix |

**Deliberately not yet**, each because it is a coherent slice of its own and
half of one would be worse than none: revolve / sweep / loft / fillet / chamfer
/ shell / draft / hole / pattern / mirror / boolean / sheet-metal features;
assemblies, mates and BOM; drawings and their views/dimensions/annotations;
folders; STEP import; undo/redo and the rollback bar; measure and overlay;
materials. Every one of them is an existing gateway route already present in
`loft/_operations.py`, so adding a verb is a typed method over a constant that
is already generated — not new plumbing.

## Designed for the MCP server that comes next

- **Machine-readable failures.** Every error is a `LoftError` with a stable
  `.code` (the gateway envelope's own code, or the geometry service's feature
  error code) and an `.as_dict()` fit to return from a tool. No stack traces.
- **Individually addressable operations.** Parts, features and sketches all
  have ids, and every handle can be rebuilt from an id alone —
  `session.part(id)`, `part.sketch_by_id(id)`, `part.feature(id)`.
- **No hidden session state.** The only cached value is `tree_version`, and it
  is an optimisation: a write that loses the optimistic-concurrency race
  refetches and retries once, so an agent that reconstructs a handle per tool
  call is never wrong, only one request slower.

## Testing

`tests/test_contract_parity.py` asserts that every model the library sends is
the class `packages/contracts` names for that route, and that every operation
it calls exists. `tests/test_modelling.py` drives a **real** gateway +
documents + geometry stack in-process (ASGI transports, real OCCT) and asserts
on the *geometry* — 10 000 mm³, 6 faces, 40 x 25 x 10 mm — never on a status
code, because a 2xx proves a request parsed, not that it meant anything.
