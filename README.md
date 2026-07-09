# Loft (working name)

**An open-source, cloud-native parametric 3D CAD platform — early
foundation stage.**

Python microservices around the OCCT geometry kernel, a React +
react-three-fiber frontend, MIT licensed, built to self-host. The goal:
a daily driver a working engineer would model a real part in — see
[`docs/VISION.md`](./docs/VISION.md) for the thesis and the honest scorecard
against the incumbents.

> **Status: Phase 0 (foundation).** Nothing runs yet. This README makes no
> claims beyond what's in the repo — it grows only as verified capability
> ships (see [`docs/ROADMAP.md`](./docs/ROADMAP.md) for what's next, and
> [`docs/BACKLOG.md`](./docs/BACKLOG.md) for what's being built right now).

## What's decided (and why)

Architecture decisions live in [`docs/RESEARCH.md`](./docs/RESEARCH.md):

- **Kernel:** OCCT via OCP + build123d, isolated in a stateless geometry
  service.
- **Backend:** Python 3.12 FastAPI microservices (gateway, documents,
  geometry) — Postgres 16, Redis + arq, S3/MinIO.
- **Frontend:** React 19 + Vite + TypeScript, react-three-fiber viewport.
- **Monorepo:** uv + pnpm workspaces, contract-first (pydantic → OpenAPI →
  generated TS client), Docker Compose for dev, Kubernetes later.

## Built by an AI agent team

This project is developed by a team of specialized Claude Code agents
(builders, independent reviewers/QA including geometry-correctness QA, and
direction roles) working off the repo's own roadmap and backlog — the
workflow inherited from [Next-Lane](https://github.com/Overcastly-AI/Next-Lane).
See [`.claude/README.md`](./.claude/README.md) and
[`docs/AUTONOMOUS-LOOP.md`](./docs/AUTONOMOUS-LOOP.md).

## License

[MIT](./LICENSE) © Overcastly AI.

Built by [Overcastly AI](https://overcastly.com). Not affiliated with,
endorsed by, or sponsored by any commercial CAD vendor; product names
mentioned in docs are their owners' trademarks, used for identification only.
