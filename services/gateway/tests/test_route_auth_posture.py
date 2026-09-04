"""K2 — every route is authenticated, or exempt for a written reason.

WHAT THIS GATE IS FOR. The gateway's unauthenticated surface is 89 operations
and until this file nothing asserted anything about it. The posture was
correct — four consecutive engineering-audit passes (J7 -> K2 -> L3 -> M3) said
so and this file confirms it — but correct-by-habit is one refactor away from
being wrong silently, and auth is the one place where "nobody noticed" is the
whole attack. Adding a route without ``CurrentUser`` should be impossible to
do quietly; that is the only thing this file buys.

WHY ONE FILE FOR THREE SERVICES. It is one invariant about the system's
identity surface, and splitting it would mean three floors, three exempt lists
and three verdicts to keep in step. The gateway owns identity (RESEARCH §3),
so the whole-system posture is legitimately its test; cross-service in-process
tests already live here (``test_assembly_import_chain.py``), which is what the
``integration`` marker is for.

WHY IT IS A TEST AND NOT A ``scripts/`` GATE. Both ``just lint`` and
``just test`` are in the definition of done and CI runs both, so catching is a
wash; three things break the tie. (1) The subject is the BUILT app, and
``gateway.build_app()`` deliberately refuses to boot without ``LOFT_ENV=dev``
— a lint script would have to begin by setting a security-posture variable to
its most permissive value, in its own process, to check security. pytest
already has that posture, declared once in ``conftest.py``. (2) Zero wiring:
``testpaths`` already covers ``services/``, so this rides the existing
``uv run pytest`` in CI's ``python`` job with no justfile edit, no ci.yml step
and no ``.dockerignore`` negation to drift out of date. (3) The negative
controls read better as tests than as a ``--self-test`` flag, and they run
every time rather than when someone remembers the flag. The controls
themselves live next to the code they exercise, in
``packages/py-kit/tests/test_routes.py``.

THE TWO OBLIGATIONS, both of which must be asserted. A gate satisfying only
the first is the one already known not to work:

1. **every operation is authenticated or exempt** — the posture; and
2. **the walk actually found the routes** — the floor plus ``unwalked``.

``all([])`` over an empty walk is vacuously true and this repo has shipped
that shape five times. It is not hypothetical here: the audit that filed K2
mis-measured the gateway as "3 routes, nothing to check" while auditing for
exactly this, because FastAPI does not flatten included routers into
``app.routes``. Three probes passing a posture check IS a green gate over 3%
of the app.
"""

import pytest
from documents.main import build_app as build_documents_app
from documents.parts import get_principal
from fastapi import FastAPI
from gateway.auth import get_current_user
from gateway.main import build_app as build_gateway_app
from geometry.main import build_app as build_geometry_app
from py_kit.routes import Operation, sweep_routes

pytestmark = pytest.mark.integration

# --------------------------------------------------------------------------
# The exempt lists.
#
# An allow-list is the right mechanism for "this route is deliberately open"
# and also the obvious place for a future route to hide, so three things
# constrain it. Each entry states a REASON (enforced non-empty, and read in
# review — an exemption whose defence is not written down is the next
# person's bypass). Each list is asserted against its own COUNT, held in a
# separate constant, so widening the unauthenticated surface is a two-place
# edit whose diff says "5 -> 6" out loud instead of one more line in a
# 60-line literal. And every entry is asserted to still EXIST: a stale
# exemption for a deleted route is a pre-authorised hole that silently covers
# whatever is added at that path later.
# --------------------------------------------------------------------------

#: py-kit's own probes, on every service by construction. Defined once
#: (CLAUDE.md DRY) rather than repeated in three literals that could drift.
PROBE_EXEMPTIONS: dict[Operation, str] = {
    ("GET", "/healthz"): "liveness probe — must answer before anything works",
    ("GET", "/readyz"): "readiness probe — same, and read by compose/k8s",
    ("GET", "/metrics"): (
        "Prometheus scrape — network-scoped, not user-scoped; see docs/OBSERVABILITY.md"
    ),
}

GATEWAY_EXEMPTIONS: dict[Operation, str] = {
    **PROBE_EXEMPTIONS,
    ("POST", "/api/v1/auth/register"): (
        "creates the identity — cannot require one. Rate-limited and "
        "password-policy guarded in gateway.auth.routes"
    ),
    ("POST", "/api/v1/auth/login"): (
        "exchanges credentials for the token every other route needs. Uniform "
        "401 and constant-cost argon2 on the miss path (anti-enumeration)"
    ),
}
EXPECTED_GATEWAY_EXEMPTIONS = 5

DOCUMENTS_EXEMPTIONS: dict[Operation, str] = {
    **PROBE_EXEMPTIONS,
    ("GET", "/api/v1/materials"): (
        "read-only shared material library — identical for every user, owns "
        "no user data, and the gateway's own /api/v1/materials proxy in front "
        "of it IS authenticated"
    ),
}
EXPECTED_DOCUMENTS_EXEMPTIONS = 4

# Count floors. The number each service had when the sweep was written,
# cross-checked against `docs/AUDIT-ENGINEERING.md` "Pass 7" M3. A floor, not
# an equality: routes get added constantly and an equality would fail every
# feature commit, which is how a gate gets deleted. It exists solely so a walk
# that collapses to the three probes cannot report success -- `unwalked`
# catches a walk that shrinks relative to the schema, but both readings shrink
# together if a whole router stops being included, and only this notices that.
GATEWAY_ROUTE_FLOOR = 88
DOCUMENTS_ROUTE_FLOOR = 64
GEOMETRY_ROUTE_FLOOR = 28

#: Every identity dependency in the system. Geometry is checked against the
#: full set: its invariant is that NONE of them reach it.
ALL_IDENTITY_MARKERS = (get_current_user, get_principal)


def assert_walk_is_real(
    sweep_operations: frozenset[Operation],
    unwalked: frozenset[Operation],
    floor: int,
    service: str,
) -> None:
    """Obligation 2: the posture verdict describes the whole app.

    Both halves are needed and neither implies the other. ``unwalked`` names
    operations the app's OpenAPI schema describes that the walk did not reach;
    the floor catches the case where both readings shrink together.
    """
    assert unwalked == frozenset(), (
        f"{service}: the route walk missed {len(unwalked)} documented "
        f"operation(s) — {sorted(unwalked)}. Every posture claim below is "
        f"about a FRACTION of this app until that is zero."
    )
    assert len(sweep_operations) >= floor, (
        f"{service}: the walk found {len(sweep_operations)} operations, below "
        f"the floor of {floor}. Either routes were deleted (lower the floor "
        f"deliberately, in a commit that says so) or the walk is broken — and "
        f"a broken walk reports a clean posture over whatever it did reach."
    )


def assert_exemptions_are_honest(
    exemptions: dict[Operation, str],
    expected: int,
    live: frozenset[Operation],
    service: str,
) -> None:
    """The allow-list's own hygiene — see the block comment above."""
    assert len(exemptions) == expected, (
        f"{service}: the exempt list has {len(exemptions)} entries, not "
        f"{expected}. Changing the unauthenticated surface is deliberate: "
        f"update the count constant in the same commit and say why."
    )
    for operation, reason in exemptions.items():
        assert len(reason.strip()) >= 20, (
            f"{service}: exemption {operation} needs a real reason, not "
            f"{reason!r} — an exemption whose defence is not written down is "
            f"the next person's bypass."
        )
    stale = set(exemptions) - set(live)
    assert not stale, (
        f"{service}: {sorted(stale)} are exempt but no longer exist. A stale "
        f"exemption pre-authorises whatever is added at that path next."
    )


def record(report: dict[str, str], service: str, line: str) -> None:
    """Hand the verdict block its line (see ``conftest.pytest_unconfigure``)."""
    report[service] = line


def test_gateway_routes_are_authenticated_or_exempt(
    route_posture_report: dict[str, str],
) -> None:
    """Every gateway operation requires a bearer identity, or is listed."""
    app: FastAPI = build_gateway_app()
    sweep = sweep_routes(app, markers=(get_current_user,))
    record(route_posture_report, "gateway", sweep.describe("gateway"))

    assert_walk_is_real(
        sweep.operations, sweep.unwalked, GATEWAY_ROUTE_FLOOR, "gateway"
    )
    assert_exemptions_are_honest(
        GATEWAY_EXEMPTIONS, EXPECTED_GATEWAY_EXEMPTIONS, sweep.operations, "gateway"
    )
    assert sweep.unprotected == frozenset(GATEWAY_EXEMPTIONS), (
        "gateway: routes reachable without authenticating that are not on the "
        f"exempt list: {sorted(sweep.unprotected - set(GATEWAY_EXEMPTIONS))}. "
        "Add `user: CurrentUser` to the handler, or — if it is genuinely "
        "public — add it to GATEWAY_EXEMPTIONS with a reason and bump "
        "EXPECTED_GATEWAY_EXEMPTIONS."
    )


def test_documents_routes_require_a_forwarded_principal(
    route_posture_report: dict[str, str],
) -> None:
    """Documents is internal: its identity is the gateway-forwarded principal.

    Not a credential check — ``get_principal`` trusts the ``X-Loft-User``
    header because ``apps/web`` talks only to the gateway (CLAUDE.md service
    boundaries) and real enforcement lives there. It is still the right marker
    to sweep for: it is what makes a row owner-scoped, so a route without it
    reads or writes documents belonging to nobody in particular.
    """
    app: FastAPI = build_documents_app()
    sweep = sweep_routes(app, markers=(get_principal,))
    record(route_posture_report, "documents", sweep.describe("documents"))

    assert_walk_is_real(
        sweep.operations, sweep.unwalked, DOCUMENTS_ROUTE_FLOOR, "documents"
    )
    assert_exemptions_are_honest(
        DOCUMENTS_EXEMPTIONS,
        EXPECTED_DOCUMENTS_EXEMPTIONS,
        sweep.operations,
        "documents",
    )
    assert sweep.unprotected == frozenset(DOCUMENTS_EXEMPTIONS), (
        "documents: routes served without an owner principal that are not on "
        f"the exempt list: {sorted(sweep.unprotected - set(DOCUMENTS_EXEMPTIONS))}"
    )


def test_geometry_stays_identity_free(
    route_posture_report: dict[str, str],
) -> None:
    """Geometry's invariant is the INVERSE, and asserting the other would be
    asserting the wrong thing loudly.

    The kernel is stateless, never touches Postgres and never sees a user
    (CLAUDE.md service boundaries); it is reached only via the gateway, which
    has already authenticated. So the property worth gating is that no
    identity dependency has LEAKED across that boundary — a
    ``get_current_user`` appearing here would mean the kernel had grown a
    notion of who is asking, which is a boundary violation whether or not it
    is spelled securely.

    This is exactly why the count floor is not optional. "No route is
    authenticated" is trivially true of a walk that found no routes, so the
    posture assertion below carries no information at all without the floor
    beside it.
    """
    app: FastAPI = build_geometry_app()
    sweep = sweep_routes(app, markers=ALL_IDENTITY_MARKERS)
    record(route_posture_report, "geometry", sweep.describe("geometry"))

    assert_walk_is_real(
        sweep.operations, sweep.unwalked, GEOMETRY_ROUTE_FLOOR, "geometry"
    )
    assert sweep.protected == frozenset(), (
        "geometry: identity dependencies have crossed into the kernel — "
        f"{sorted(sweep.protected)}. Geometry is reached through the gateway, "
        "which authenticates; it must not learn who is asking."
    )
    assert sweep.unprotected == sweep.operations
