# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub
issues.**

Report privately via GitHub Security Advisories:
[https://github.com/Overcastly-AI/3d-cad/security/advisories/new](https://github.com/Overcastly-AI/3d-cad/security/advisories/new)
("Report a vulnerability" on the repo's Security tab).

Include what you can: affected component (service, package, or the web
app), reproduction steps, impact assessment, and any suggested fix. You'll
get a response on a best-effort basis — this is a pre-release open-source
project without a dedicated security team, and there is currently **no bug
bounty program**. Credit in the advisory is gladly given if you want it.

## Supported versions

The project is pre-release — see [`docs/ROADMAP.md`](./docs/ROADMAP.md) for
the current phase. There are no tagged releases and no published container
images yet; only the latest state of the default branch is supported.

| Version         | Supported |
| --------------- | --------- |
| `main` (latest) | Yes       |
| Anything else   | No        |

## Scope notes (honest)

- **Authentication exists** (registration, login, JWT-bearer sessions), and
  the compose topology publishes only the gateway — `documents` and
  `geometry` are not reachable from the host. None of it has had a security
  audit.
- **Dev-only defaults are published in this repo.** The compose file's
  Postgres/MinIO passwords and the gateway's JWT fallback secret are all
  readable by anyone. Since 2026-07-30 they fail closed: unless `LOFT_ENV` is
  exactly `dev`, a service whose datastore URL embeds a known default
  password — or which has no `JWT_SECRET` — refuses to boot and names the
  variable to fix. **Leaving `LOFT_ENV=dev` is what opts you back into the
  insecure defaults**, so it is the one setting that matters when exposing a
  deployment.
- **Multi-tenancy is shallow.** Parts are owned by their creator, but the
  project has not been designed or reviewed for hostile co-tenants.
- Vulnerability reports about the absence of not-yet-built features are
  appreciated as roadmap validation but will generally be tracked as roadmap
  items, not advisories. The README's "What does NOT exist yet" section and
  [`docs/ROADMAP.md`](./docs/ROADMAP.md) are the current list.
