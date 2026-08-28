"""PGTEST-GATE — the guard on the guard.

``conftest.pg_required`` decides whether a missing PostgreSQL is a skip or a
red build. It is therefore the one place in this suite where getting the
answer wrong is invisible: too lax and 37% of the documents tests go back to
vanishing with exit 0, too strict and every contributor without a server
hits a wall.

Two things these tests are deliberately careful about.

1. **Nothing is inherited.** pytest imports every conftest before it runs any
   test, so a whole-repo run already carries other services' ``os.environ``
   edits (``services/gateway/tests/conftest.py`` seeds ``LOFT_ENV=dev``) by
   the time this file is read — and this module's subject IS an environment
   variable. Every case therefore states the whole environment explicitly,
   either as a literal dict or via ``monkeypatch``. A case that passed
   because the ambient ``CI`` happened to be set would be testing the runner,
   not the gate.
2. **The injected path and the ambient path are checked against each other.**
   Testing only the convenient ``env=`` overload would leave the code that
   actually runs — the one reading ``os.environ`` — unmeasured. That is the
   "a gate is only as honest as its input" trap in miniature.
"""

from collections.abc import Callable

import pytest

RequiredFn = Callable[[dict[str, str] | None], tuple[bool, str]]


def test_absent_signals_mean_not_required(pg_required_fn: RequiredFn) -> None:
    """A contributor's laptop: skip, not a wall."""
    required, why = pg_required_fn({})
    assert required is False
    assert "not CI" in why


def test_ci_alone_requires_postgres(pg_required_fn: RequiredFn) -> None:
    """The automatic half: a new workflow inherits the requirement."""
    required, why = pg_required_fn({"CI": "true"})
    assert required is True
    assert "CI=" in why


@pytest.mark.parametrize("falsey", ["0", "false", "False", "no", "off"])
def test_a_falsey_ci_is_not_ci(pg_required_fn: RequiredFn, falsey: str) -> None:
    """Some environments export ``CI=false``, which means NOT CI.

    Treating any non-empty value as truthy would wall those users on a
    variable they never chose to set.
    """
    required, _ = pg_required_fn({"CI": falsey})
    assert required is False


def test_explicit_opt_in_beats_absent_ci(pg_required_fn: RequiredFn) -> None:
    """The honest half: demand a real server locally when you mean to."""
    required, why = pg_required_fn({"LOFT_REQUIRE_PG": "1"})
    assert required is True
    assert "LOFT_REQUIRE_PG" in why


def test_explicit_opt_out_beats_ci(pg_required_fn: RequiredFn) -> None:
    """The escape hatch, and the reason it must be honoured.

    A downstream CI that genuinely cannot provide PostgreSQL needs a way to
    accept the coverage loss knowingly. Without it the gate's only options
    are "pass silently" and "unusable", and the historical evidence is that
    an unusable gate gets deleted rather than fixed.
    """
    required, why = pg_required_fn({"CI": "true", "LOFT_REQUIRE_PG": "0"})
    assert required is False
    assert "LOFT_REQUIRE_PG" in why


def test_blank_values_fall_through_rather_than_deciding(
    pg_required_fn: RequiredFn,
) -> None:
    """``LOFT_REQUIRE_PG=`` is "unset", not "off".

    Shell interpolation of an undefined variable produces an empty string,
    so an empty override must not silently disable the CI default.
    """
    required, why = pg_required_fn({"CI": "1", "LOFT_REQUIRE_PG": "   "})
    assert required is True
    assert "CI=" in why


def test_the_ambient_path_agrees_with_the_injected_one(
    pg_required_fn: RequiredFn, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The overload under test must be the code that actually runs.

    ``env=None`` reads ``os.environ``; every other case here passes a dict.
    If those two ever diverge, all the coverage above would be measuring a
    function CI never calls -- so state the environment explicitly (never
    inherit it) and assert the two paths give the same answer.
    """
    for state in ({}, {"CI": "1"}, {"CI": "1", "LOFT_REQUIRE_PG": "0"}):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("LOFT_REQUIRE_PG", raising=False)
        for key, value in state.items():
            monkeypatch.setenv(key, value)
        assert pg_required_fn(None) == pg_required_fn(state), state
