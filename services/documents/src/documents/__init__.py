"""Loft documents service — parts/assemblies, feature trees, versioning.

Owns the Postgres document model (alembic migrations only). Never imports
the geometry kernel; geometry results are referenced by object-storage ID
(CLAUDE.md service boundaries).
"""
