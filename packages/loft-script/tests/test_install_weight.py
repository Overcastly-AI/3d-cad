"""What `pip install loft-script` puts in somebody's venv.

This library is installed next to numpy in a modelling script's environment, and
for its first commit it dragged a web server (uvicorn), an async ORM
(SQLAlchemy + alembic), a task queue (arq) and a Redis client in with it —
**33** resolved distributions — because it depended on ``loft-py-kit`` for the
wire DTOs and a dependency is a property of the DISTRIBUTION, not of the module.
Every module it imported was pydantic-clean the whole time. No import-based
check could see it; that is why this one reads METADATA.

Two checks, at the two layers the defect can live in:

1. the declared first-party closure (this file), and
2. what the wire package itself may import
   (``packages/loft-wire/tests/test_wire_dependency_closure.py``).

Both carry count floors. A closure walk that terminates immediately would make
"none of them declare a server" vacuously true, which is the failure shape this
repo has paid for repeatedly.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Distributions that make this a heavyweight install rather than an HTTP
#: caller. Not exhaustive and not meant to be — it is the specific set that was
#: actually present, so a regression names the thing that came back.
SERVER_DISTRIBUTIONS = frozenset(
    {
        "alembic",
        "arq",
        "asyncpg",
        "fastapi",
        "prometheus-client",
        "pydantic-settings",
        "redis",
        "sqlalchemy",
        "starlette",
        "structlog",
        "uvicorn",
    }
)

#: Workspace member directories, by distribution name.
FIRST_PARTY = {
    "loft-wire": REPO_ROOT / "packages/loft-wire",
    "loft-py-kit": REPO_ROOT / "packages/py-kit",
    "loft-script": REPO_ROOT / "packages/loft-script",
    "loft-gateway": REPO_ROOT / "services/gateway",
    "loft-documents": REPO_ROOT / "services/documents",
    "loft-geometry": REPO_ROOT / "services/geometry",
}


def _requirements(dist: str) -> list[str]:
    raw = (FIRST_PARTY[dist] / "pyproject.toml").read_bytes()
    declared = tomllib.loads(raw.decode())["project"]["dependencies"]
    return [spec.split(">")[0].split("=")[0].split("[")[0].strip() for spec in declared]


def _closure(root: str) -> dict[str, list[str]]:
    """Every distribution reachable from ``root``, mapped to what declared it.

    First-party members are followed transitively; third-party names are
    recorded and not followed (their own metadata is upstream's business, and
    the resolved-set measurement in the commit message covers it).
    """
    reached: dict[str, list[str]] = {}
    pending = [root]
    visited = {root}
    while pending:
        dist = pending.pop()
        for requirement in _requirements(dist):
            reached.setdefault(requirement, []).append(dist)
            if requirement in FIRST_PARTY and requirement not in visited:
                visited.add(requirement)
                pending.append(requirement)
    return reached


def test_loft_script_declares_no_server_distribution_anywhere_in_its_closure() -> None:
    closure = _closure("loft-script")

    assert len(closure) >= 3, (
        f"closure walk reached only {sorted(closure)} — too few to have walked "
        "anything. A closure that terminates immediately makes the assertion "
        "below vacuously true."
    )

    offences = sorted(
        f"{dist} (declared by {', '.join(sorted(set(by)))})"
        for dist, by in closure.items()
        if dist in SERVER_DISTRIBUTIONS
    )
    assert not offences, (
        "`pip install loft-script` would install server infrastructure. The "
        "library is an HTTP caller; these belong to the services:\n  "
        + "\n  ".join(offences)
    )


def test_loft_script_has_exactly_one_first_party_dependency() -> None:
    """Named rather than merely counted, because WHICH one is the whole design.

    The wire types belong to neither the server nor the client, so they are
    their own distribution and both sides depend on it. A second first-party
    entry here means a boundary moved — most likely somebody reached for
    ``loft-py-kit`` again for something that should have been in the wire.
    """
    first_party = [d for d in _requirements("loft-script") if d in FIRST_PARTY]
    assert first_party == ["loft-wire"], first_party


def test_py_kit_depends_on_the_wire_and_not_the_other_way_round() -> None:
    """The arrow's direction, asserted at the metadata layer.

    ``loft-wire`` importing nothing from ``py_kit`` is checked in that package's
    own suite; this is the complementary half — the wire must not *declare*
    py-kit either, which is how the coupling would reappear without any import
    changing (a transitive dependency is invisible to an AST walk).
    """
    assert "loft-wire" in _requirements("loft-py-kit")
    assert "loft-py-kit" not in _requirements("loft-wire")
