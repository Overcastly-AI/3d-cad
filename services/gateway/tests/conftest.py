"""Suite-wide ambient env for the gateway tests, plus the auth-posture verdict.

``gateway.main`` builds a module-level ``app`` at import time, and the
fail-closed secret posture (no ``LOFT_ENV`` default) refuses to construct it
without either an explicit ``LOFT_ENV=dev`` or a real ``JWT_SECRET`` — by
design (see :mod:`gateway.auth.security`). Tests import that module, so the
suite opts into dev explicitly here, exactly like a developer shell would.
Fail-fast tests are unaffected: they pass ``loft_env=`` kwargs, which take
priority over the environment in pydantic-settings.

The rest of this file is the reporting channel for
``test_route_auth_posture.py``. A passing test's stdout is captured, so the
counts that gate the whole unauthenticated surface would never reach a CI log
— and "something passed" is not the question a human reading that log has.
See :func:`pytest_unconfigure` for why the verdict is emitted from there.
"""

import os

import pytest
from _pytest.terminal import TerminalReporter

os.environ.setdefault("LOFT_ENV", "dev")

#: Every service the route-auth sweep covers. Named here rather than counted
#: at runtime so a sweep that silently stops covering one is legible in the
#: verdict instead of just producing a shorter block nobody compares.
SWEPT_SERVICES = ("gateway", "documents", "geometry")

_posture_lines: dict[str, str] = {}


@pytest.fixture(scope="session")
def route_posture_report() -> dict[str, str]:
    """Where ``test_route_auth_posture.py`` records one line per service.

    A fixture rather than a shared module constant because a test module
    cannot import its own conftest (pytest imports it under a name that is
    not on ``sys.path`` — measured), and a fixture is the channel pytest
    already provides for conftest-to-test state.
    """
    return _posture_lines


def pytest_unconfigure(config: pytest.Config) -> None:
    """Emit the route-auth verdict AFTER everything else pytest prints.

    Not ``pytest_terminal_summary``: that hook runs before the short test
    summary, so on a red run the verdict lands in the middle of the log where
    a fixed ``tail_lines`` read cannot reach it (the trap CLAUDE.md records
    for e2e shards and the postgres verdict). ``pytest_unconfigure`` runs
    after the reporter's final stats line.

    Silent when nothing was swept — most pytest invocations select a handful
    of files and do not run this test, and a block claiming "0 services
    checked" on every one of them is how a verdict gets tuned out. But a
    PARTIAL sweep is reported loudly: it looks exactly like a complete one.
    """
    if not _posture_lines:
        return
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if not isinstance(reporter, TerminalReporter):  # pragma: no cover - guard
        return
    lines = ["== route auth posture =="]
    lines += [_posture_lines[name] for name in SWEPT_SERVICES if name in _posture_lines]
    missing = [name for name in SWEPT_SERVICES if name not in _posture_lines]
    if missing:
        lines.append(
            f"PARTIAL: {len(_posture_lines)} of {len(SWEPT_SERVICES)} services "
            f"swept — no reading at all for {', '.join(missing)}. Expected for "
            f"a narrow selection; a full run sweeps all three."
        )
    print("\n" + "\n".join(lines))
