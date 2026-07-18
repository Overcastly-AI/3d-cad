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

The project is pre-release (Phase 0 — see
[`docs/ROADMAP.md`](./docs/ROADMAP.md)). There are no tagged releases yet;
only the latest state of the default branch is supported.

| Version         | Supported |
| --------------- | --------- |
| `main` (latest) | Yes       |
| Anything else   | No        |

## Scope notes (honest)

- There is **no authentication yet** (Phase 1 roadmap item) — do not expose
  a dev deployment of this stack to untrusted networks.
- The compose file ships dev-only default credentials for Postgres/MinIO,
  clearly marked as such; override them for any real deployment.
- Vulnerability reports about the absence of not-yet-built features (auth,
  rate limiting, multi-tenancy) are appreciated as roadmap validation but
  will generally be tracked as roadmap items, not advisories.
