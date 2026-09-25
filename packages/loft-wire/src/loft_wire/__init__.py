"""Loft's WIRE TYPES — the pydantic models that cross a Loft service boundary.

This is a distribution with exactly one runtime dependency tree: ``pydantic``
(plus ``email-validator`` for the one ``EmailStr`` on the auth DTOs). That is
the whole point of it existing separately from ``loft-py-kit``.

WHY IT IS ITS OWN DISTRIBUTION
------------------------------
These models used to live at ``py_kit.schemas.*``. Every module under there
imported nothing but ``pydantic`` and the standard library — but the
DISTRIBUTION that shipped them, ``loft-py-kit``, declares FastAPI, uvicorn,
SQLAlchemy, alembic, arq and redis, because the rest of ``py_kit`` is a service
kit and genuinely needs them. A dependency is a property of the distribution,
not of the module, so ``pip install loft-script`` — a modelling library whose
entire premise is that it is just another HTTP caller — installed a web server,
an async ORM, a task queue and a Redis client into somebody's venv next to
numpy. The models are the WIRE, and the wire belongs to neither the server nor
the client, so it gets its own package and both depend on it.

The rule this package enforces, and it is enforced rather than asserted
(``tests/test_wire_dependency_closure.py``, with a count floor): **nothing
under ``loft_wire`` may import anything outside the standard library and this
distribution's declared dependencies.** In particular no kernel (OCP /
build123d), no FastAPI, no SQLAlchemy, and no ``py_kit``. The dependency arrow
points ``py_kit -> loft_wire``, never back — see :mod:`loft_wire.instrument`
for the one place that arrow was inverted and how.
"""
