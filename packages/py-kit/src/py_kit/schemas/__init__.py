"""Boundary DTO schemas shared across Loft services.

Single source of truth (CLAUDE.md DRY rule) for the pydantic models that
cross service boundaries — e.g. the gateway proxies the geometry API with
exactly the models the geometry service serves. Pure pydantic only: kernel
(OCP/build123d) or infrastructure imports must never appear under this
package, so py-kit stays lean and importable everywhere.
"""
