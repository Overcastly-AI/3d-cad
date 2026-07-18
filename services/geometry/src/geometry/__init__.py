"""Loft geometry service — OCCT feature evaluation, tessellation, export.

The ONLY service allowed to import OCP/build123d (CLAUDE.md boundaries).
Stateless and CPU-bound: fed by the arq queue, results go to object storage
and are referenced by ID. Never touches Postgres.
"""
