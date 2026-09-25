"""THE GATE THIS PACKAGE EXISTS FOR: loft_wire imports pydantic and nothing else.

``loft-script`` used to depend on ``loft-py-kit`` for its DTOs, which put
FastAPI, uvicorn, SQLAlchemy, alembic, arq and redis into every environment that
ran ``pip install loft-script`` — 33 resolved distributions for a library that is
an HTTP caller. Every module involved was clean; the DISTRIBUTION was not, and no
gate could see the difference because a dependency is metadata, not an import.

So the split is only worth what it is enforced to be worth. Two checks, and a
count floor on each, because a walk that finds nothing passes vacuously (the
lesson ``check-build-context.py`` printing "0 COPY source(s)" and exiting 0
taught this repo).

The checks read the SOURCE with ``ast``, deliberately, rather than importing the
modules and inspecting ``sys.modules``: an import-based check sees only what the
test process happened to load, and the whole failure mode here is a dependency
that is present for a reason having nothing to do with the module under test.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PACKAGE_ROOT / "src" / "loft_wire"

#: Every distribution ``packages/loft-wire/pyproject.toml`` declares, as the
#: TOP-LEVEL MODULE each one provides. The keys are checked against the file
#: rather than trusted, so adding a dependency without thinking about this gate
#: fails here instead of silently widening it.
_DIST_TO_MODULES = {
    "pydantic": {"pydantic"},
    "email-validator": {"email_validator"},
}

#: Floors. A refactor may legitimately move these UP; a change that drops either
#: below its floor has stopped examining the thing it claims to examine.
MIN_MODULES_WALKED = 14
MIN_IMPORTS_SEEN = 40


def _declared_third_party_modules() -> set[str]:
    raw = (PACKAGE_ROOT / "pyproject.toml").read_bytes()
    declared = tomllib.loads(raw.decode())["project"]["dependencies"]
    names = {
        spec.split(">")[0].split("=")[0].split("[")[0].strip() for spec in declared
    }
    unknown = names - _DIST_TO_MODULES.keys()
    assert not unknown, (
        f"loft-wire declares {sorted(unknown)}, which this gate does not know how "
        "to map to an import name. Add it to _DIST_TO_MODULES *and* satisfy "
        "yourself it is non-copyleft (RESEARCH §8) — do not widen this blindly."
    )
    allowed: set[str] = set()
    for name in names:
        allowed |= _DIST_TO_MODULES[name]
    return allowed


def _top_level_imports(tree: ast.Module) -> set[str]:
    """Top-level module name of every import in ``tree``, absolute imports only.

    Relative imports (``from . import x``) resolve inside this package by
    construction and cannot reach a foreign distribution, so they are not the
    subject here.
    """
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            seen.add(node.module.split(".")[0])
    return seen


def _walk_sources() -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
    ]


def test_loft_wire_imports_only_stdlib_and_its_declared_dependencies() -> None:
    allowed = _declared_third_party_modules() | sys.stdlib_module_names | {"loft_wire"}

    modules = _walk_sources()
    assert len(modules) >= MIN_MODULES_WALKED, (
        f"walked {len(modules)} module(s) under {SOURCE_ROOT}; expected at least "
        f"{MIN_MODULES_WALKED}. A gate that examines nothing passes vacuously."
    )

    total_imports = 0
    offences: list[str] = []
    for path, tree in modules:
        imports = _top_level_imports(tree)
        total_imports += len(imports)
        offences.extend(
            f"{path.relative_to(PACKAGE_ROOT)}: imports {name!r}"
            for name in sorted(imports - allowed)
        )

    assert total_imports >= MIN_IMPORTS_SEEN, (
        f"saw {total_imports} import(s); expected at least {MIN_IMPORTS_SEEN}. "
        "Either the parse stopped working or the package emptied out."
    )
    assert not offences, (
        "loft_wire must import nothing but the standard library and its own "
        "declared dependencies — that property IS this distribution's reason to "
        "exist, and every one of these lands in the venv of anyone who runs "
        "`pip install loft-script`:\n  " + "\n  ".join(offences)
    )


def test_loft_wire_never_imports_py_kit_or_the_kernel() -> None:
    """The same property stated as the names it must never be, so the failure
    message says WHICH boundary broke rather than "unexpected import".

    ``py_kit`` is the one that has actually happened: ``features`` imported
    ``py_kit.metrics`` to count feature errors, which is why
    :mod:`loft_wire.instrument` exists. ``OCP`` / ``build123d`` is the kernel
    boundary CLAUDE.md enforces in review — only ``services/geometry`` may
    import it, and a DTO package is the most tempting place to violate that.
    """
    forbidden = {"py_kit", "OCP", "build123d", "fastapi", "sqlalchemy", "starlette"}

    modules = _walk_sources()
    assert len(modules) >= MIN_MODULES_WALKED, "see the floor above"

    offences = [
        f"{path.relative_to(PACKAGE_ROOT)}: imports {name!r}"
        for path, tree in modules
        for name in sorted(_top_level_imports(tree) & forbidden)
    ]
    assert not offences, "\n  ".join(["wire -> server import(s):", *offences])
