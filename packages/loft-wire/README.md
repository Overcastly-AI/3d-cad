# `loft-wire` — Loft's wire types

The pydantic models that cross a Loft service boundary. `pydantic` and
`email-validator` are its entire dependency tree, and keeping it that way is the
package's only job.

```python
from loft_wire.parts import PartCreate
from loft_wire.features import ExtrudeFeature
```

## Why it is a package and not a subdirectory of `py-kit`

These models used to be `py_kit.schemas.*`. Every module under there imported
nothing but pydantic and the standard library — but `loft-py-kit` the
**distribution** declares FastAPI, uvicorn, SQLAlchemy, alembic, arq, redis and
prometheus-client, because the rest of `py_kit` is a service kit and genuinely
needs them.

A dependency is a property of the distribution, not of the module. So
`pip install loft-script` — a modelling library whose entire premise is that it
is just another HTTP caller — resolved **33** distributions and put a web
server, an async ORM, a task queue and a Redis client into somebody's venv next
to numpy. It resolves **15** now.

The models are the WIRE, and the wire belongs to neither the server nor the
client. Both depend on this; it depends on neither.

```
loft-script  ->  loft-wire  <-  loft-py-kit  <-  gateway / documents / geometry
```

## The rule, and where it is enforced

**Nothing under `loft_wire` may import anything outside the standard library and
this distribution's declared dependencies** — in particular no `py_kit`, no
FastAPI, no SQLAlchemy, and no kernel (`OCP` / `build123d`).

- `tests/test_wire_dependency_closure.py` AST-walks every module and fails on
  any import outside that set, naming the forbidden distributions individually
  so a failure says *which* boundary broke.
- `packages/loft-script/tests/test_install_weight.py` walks the declared
  first-party closure, which is the layer the original defect lived in and is
  invisible to an import check — a transitive dependency changes no import line.

Both carry count floors: a walk that finds nothing would make every "all of them
are fine" assertion vacuously true.

## The one inverted edge

`FeatureError.model_post_init` counts every feature failure, and the counter is
a Prometheus metric that lives in `py_kit.metrics`. Rather than import it,
`loft_wire.instrument` publishes an observer registry that `py_kit.metrics`
registers into at import time. Read that module's docstring before touching it:
the indirection has a real hazard (an unregistered observer is a flat line,
which reads as "nothing is failing") and the docstring names what holds it down.

See `docs/RESEARCH.md` §3b for the decision record.
