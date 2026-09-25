# Claude Code tooling for Loft

Loft is built by a small team of Claude Code agents. `CLAUDE.md` holds the
rules every agent follows, and `ORCHESTRATOR.md` is the main session's loop.

| Agent              | Owns                                                            |
| ------------------ | --------------------------------------------------------------- |
| `kernel-architect` | `services/geometry` (OCCT kernel, solver, tessellation, export) |
| `backend-builder`  | gateway, documents, `py-kit`, `loft-wire`, `loft-script`        |
| `frontend-builder` | `apps/web`, `packages/design`                                   |
| `platform-builder` | CI, Docker/compose, `justfile`, `scripts/`                      |
| `code-reviewer`    | one independent review per change; subsystem audits on request  |
| `geometry-qa`      | goldens, STEP round-trip, determinism: is the geometry right?   |
| `qa-tester`        | the real app in a real browser; reference parts end to end      |
| `product-manager`  | `docs/VISION.md`, `docs/ROADMAP.md`, `docs/BACKLOG.md`          |
| `tech-writer`      | README, CONTRIBUTING, QUICKSTART, ARCHITECTURE, OPERATIONS      |

The skills (`skills/`) are `run-stack` (boot and verify a stack),
`geometry-gates` (goldens and round-trips), `frontend-design` (visual design
direction) and `add-microservice`.
