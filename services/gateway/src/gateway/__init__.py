"""Loft gateway service — auth, REST aggregation, geometry/document proxy.

The single public entry point to the platform: the web app (and any other
client) talks only to this service (CLAUDE.md service boundaries).

NB this line used to end "…, WebSocket fan-out", and no WebSocket route has
ever existed here. That aspiration propagated as fact into CLAUDE.md,
docs/ARCHITECTURE.md and the README, where a release audit found it being
advertised to strangers as shipped (2026-07-31). Describe what the module
DOES; a roadmap belongs in docs/ROADMAP.md, where it is marked as unbuilt.
"""
