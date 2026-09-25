#!/usr/bin/env python3
"""Air-gap gate — nothing the RUNNING product needs may live on the internet.

``docs/VISION.md`` names "free & unlimited" and "your data, your files, your
compute" as two of Loft's four structural advantages, and ``README.md`` states
the operative consequence outright: **"The whole stack can run air-gapped."**
That is a testable claim about a regulated shop's network, and until this file
existed nothing in the repo graded it — which is exactly how it came to be
false. Measured 2026-09-15 (AIRGAP-1): every service boots through
``py_kit.app.create_app``, whose ``FastAPI(...)`` left ``docs_url``/``redoc_url``
at their defaults, so ``/docs`` on the ONE port a self-hoster publishes served
HTML sourcing ``cdn.jsdelivr.net`` and ``fastapi.tiangolo.com``, and ``/redoc``
added ``fonts.googleapis.com``. Blank page, day one, for the only customer the
claim was written for.

A one-time audit decays; this does not. Seven checks, each of which walks a
surface and asserts BOTH a property and a census:

1. ``python`` — no non-docstring string literal in any shipped backend tree
   (``BACKEND_ROOTS``: the services, py-kit, loft-wire and the loft-script
   CLIENT) names an external host. AST-based, so a URL in a comment or a
   docstring (which is documentation, and allowed) cannot trip it and a URL in
   code cannot hide. Each declared root must contribute at least one file —
   see ``Check.empty_roots``, which is what a total floor cannot do.
2. ``fastapi-docs`` — every ``FastAPI(...)`` construction passes
   ``docs_url=None`` and ``redoc_url=None``. This is a STRUCTURAL check on the
   defect above: the offending URLs are inside the fastapi package, never in
   our source, so no amount of grepping our own strings could ever have found
   them. ``/openapi.json`` is untouched — it is generated in-process and is
   what a local explorer points at.
3. ``web`` — no external ``src``/``href``/``url()``/``@import`` in the HTML
   entry, and no external URL in non-comment TS/TSX/CSS under ``apps/web/src``
   or ``packages/design/src`` (``WEB_ROOTS``). Per-root census, same as check 1
   and for the same measured reason: with the roots inlined at the call site,
   emptying ``packages/design/src`` took the walk 315 -> 277 against a floor of
   200 and the gate still said ``ok``.
4. ``fonts`` — POSITIVE control: ``packages/design/src/fonts.ts`` must import
   every face from ``@fontsource`` (a self-hosted npm package whose files are
   emitted into the bundle). "No Google Fonts link found" is vacuously true of
   a repo with no fonts at all; this asserts the faces are there AND local.
5. ``compose`` — no external host in any ``docker-compose*.yml`` outside an
   ``image:`` reference, so nothing a container RUNS reaches off-box. The
   images themselves are pull-time, not run-time; they are printed as the
   mirror list an air-gapped operator must side-load.
6. ``dockerfile`` — ``CMD``/``ENTRYPOINT``/``HEALTHCHECK`` (the only lines that
   execute when a container RUNS, as opposed to when it builds) reference
   loopback only. ``FROM`` images join the mirror list (stage names do not —
   ``FROM deps AS build`` names an earlier stage, and telling an air-gapped
   operator to go and find an image called "deps" wastes a real person's time).
7. ``static-server`` — the nginx config the web edge RUNS: every ``proxy_pass``
   and ``resolver`` target, with nginx ``set`` variables RESOLVED first. That
   substitution is the whole check: the upstream is written
   ``proxy_pass http://$loft_gateway$request_uri`` so nginx re-resolves it per
   request, which means ``//`` is never followed by a hostname anywhere in the
   file and the plain URL scan matches nothing at all. Measured — neuter the
   substitution and an upstream pointed at ``telemetry.example`` goes
   undetected.

**Vacuity is the failure mode this gate class actually has here.** A sibling
gate once printed ``0 COPY source(s) reach the build context`` and exited 0,
and ``check-tailwind-scale.py`` was one ``default=0`` away from the same. So
every check declares how many things it expects to walk and REFUSES (exit 2)
when it walks fewer — and ``--self-test`` proves that refusal fires by running
the real floors against an empty tree.

Stdlib only, no network, no docker daemon, ~0.2 s. Wired into ``just lint`` and
CI's ``compose`` job. Prove it can fail::

    python3 scripts/check-air-gap.py --self-test
    python3 scripts/check-air-gap.py
    python3 scripts/check-air-gap.py --dist apps/web/dist   # after a real build
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: This gate reads the tree with ``ast``, and the tree is Python 3.12 (PEP 695
#: generics: ``class DocumentHistory[DocT: HistoryDocument]``). This container's
#: ``python3`` is **3.11**, and a GitHub runner's is 3.12 — so the naive
#: invocation every sibling gate uses would have reported five services files as
#: "unparseable" locally and zero in CI, i.e. a gate that disagrees with itself
#: depending on where it runs. Re-exec under a new-enough interpreter instead,
#: and REFUSE if there is none: degrading to a text scan would keep the exit
#: code green while checking something weaker than advertised, which is the
#: failure mode this whole file exists to prevent.
_MIN_PYTHON = (3, 12)
_REEXEC_GUARD = "LOFT_AIRGAP_REEXEC"


def _ensure_modern_python() -> None:
    if sys.version_info >= _MIN_PYTHON:
        return
    if os.environ.get(_REEXEC_GUARD):
        print(
            f"air-gap: need Python >= {'.'.join(map(str, _MIN_PYTHON))} to parse this "
            f"tree; re-exec already attempted and landed on {sys.version.split()[0]}.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    for candidate in ("python3.13", "python3.12"):
        path = shutil.which(candidate)
        if path:
            os.environ[_REEXEC_GUARD] = "1"
            os.execv(path, [path, str(Path(__file__).resolve()), *sys.argv[1:]])
    print(
        f"air-gap: REFUSED — this gate parses Python "
        f"{'.'.join(map(str, _MIN_PYTHON))}+ source and found no such "
        f"interpreter (running "
        f"{sys.version.split()[0]}). Install python3.12 or run via `uv run python`.",
        file=sys.stderr,
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------
# What counts as "on this machine".
#
# Keys are hostnames; values are the REASON, because an allowlist without one
# rots into a list of things somebody once wanted to pass. Everything here is
# either a loopback address, a compose-internal service name (resolvable only
# inside the stack's own network), or a string that is never fetched at all.
# --------------------------------------------------------------------------
LOCAL_HOSTS: dict[str, str] = {
    "localhost": "loopback",
    "127.0.0.1": "loopback",
    "0.0.0.0": "wildcard bind, not a fetch target",
    "::1": "loopback",
    "db": "compose service (postgres)",
    "redis": "compose service",
    "minio": "compose service (object store)",
    "gateway": "compose service",
    "documents": "compose service",
    "geometry": "compose service",
    "web": "compose service (nginx serving the SPA)",
    "127.0.0.11": "Docker's embedded DNS, on the stack's own network",
    "geometry-1": "docker-compose.scale.yml named replica",
    "geometry-2": "docker-compose.scale.yml named replica",
    "geometry-3": "docker-compose.scale.yml named replica",
    "geometry-4": "docker-compose.scale.yml named replica",
}

#: Hosts that appear in code but are NEVER fetched. Each needs a reason that
#: explains why a reader should not treat it as egress.
NEVER_FETCHED: dict[str, str] = {
    "www.w3.org": "XML/SVG namespace identifier — an opaque id, not a URL "
    "anything resolves (SVG_NS, drawings compose)",
}

#: Registries whose images must be MIRRORED for an air-gapped install. Not a
#: violation — an image is pulled once at install time, not per request — but
#: the operator has to be told, so the gate prints them.
REGISTRY_HOSTS = ("docker.io", "quay.io", "ghcr.io", "registry.k8s.io")

#: The hosts FastAPI's built-in explorer pages pull from when docs_url /
#: redoc_url are left at their defaults (measured on fastapi 0.139.0). Recorded
#: so the next reader knows precisely what check 2 is standing in for — these
#: strings live in the fastapi package, never in our tree, which is why only a
#: structural check can see them.
FASTAPI_DOC_CDNS = (
    "cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
    "cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    "cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js",
    "fastapi.tiangolo.com/img/favicon.png",
    "fonts.googleapis.com/css?family=Montserrat",
)

URL = re.compile(
    r"(?P<scheme>https?:)?//(?P<host>[A-Za-z0-9._-]+)(?P<rest>[^\s\"'`)>]*)"
)
HTML_REF = re.compile(
    r"""(?:src|href)\s*=\s*["']\s*((?:https?:)?//[^"'\s]+)""", re.IGNORECASE
)
CSS_REF = re.compile(
    r"""(?:url\(\s*["']?|@import\s+["'])((?:https?:)?//[^"'\s)]+)""", re.IGNORECASE
)


def is_local(host: str) -> bool:
    return host in LOCAL_HOSTS or host in NEVER_FETCHED or host.startswith("127.")


@dataclass
class Finding:
    where: str
    detail: str


@dataclass
class Check:
    """One surface, its verdict, and — non-negotiably — its census."""

    name: str
    walked: int = 0
    floor: int = 0
    findings: list[Finding] = field(default_factory=list[Finding])
    notes: list[str] = field(default_factory=list[str])
    #: Name of the constant declaring this check's roots, so the REFUSED
    #: message tells the reader which list to go and fix. A message that names
    #: the wrong constant sends the next person to the wrong file.
    roots_const: str = ""
    #: Declared source roots this check found NOTHING in. A total floor cannot
    #: detect a check that quietly stops covering a subtree, because the total
    #: stays comfortably above it: measured 2026-09-15, fifteen wire modules
    #: moved out of packages/py-kit into a new distribution, `python` went
    #: 147 -> 132 against a floor of 100, and the gate reported `ok` while the
    #: new package was scanned by nothing at all. A floor catches a COLLAPSE;
    #: only a per-root census catches a SHRINK, and a shrink is what a
    #: refactor produces.
    empty_roots: list[str] = field(default_factory=list[str])

    @property
    def vacuous(self) -> bool:
        return self.walked < self.floor or bool(self.empty_roots)


# --------------------------------------------------------------------------
# File collection
# --------------------------------------------------------------------------
_SKIP_DIR = ("node_modules", ".venv", "dist", ".git", "__pycache__")


def _walk(root: Path, rel: str, suffixes: tuple[str, ...]) -> list[Path]:
    base = root / rel
    if not base.exists():
        return []
    out: list[Path] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        parts = path.relative_to(root).parts
        if any(d in parts for d in _SKIP_DIR):
            continue
        out.append(path)
    return out


def _is_backend_test(path: Path) -> bool:
    parts = path.parts
    return "tests" in parts or path.name.startswith("test_") or "alembic" in parts


def _is_frontend_test(path: Path) -> bool:
    return ".test." in path.name or "/test/" in path.as_posix() or "e2e" in path.parts


# --------------------------------------------------------------------------
# 1. Python string literals (AST — comments and docstrings are documentation)
# --------------------------------------------------------------------------
#: EVERY Python tree that ships as part of the running product, in ONE place.
#: It used to be an inline tuple repeated in the two AST checks below, which is
#: precisely how a new distribution gets added to neither: `packages/loft-wire`
#: and `packages/loft-script` were split out on 2026-09-15 and were scanned by
#: nothing until this was hoisted. `loft-script` is here because it is a CLIENT
#: users run — a phone-home in a client library is egress from the same
#: air-gapped network, and the fact that it is not a server does not change
#: whose firewall it crosses.
BACKEND_ROOTS = (
    "services",
    "packages/py-kit",
    "packages/loft-wire",
    "packages/loft-script",
)


def _backend_sources(root: Path) -> tuple[list[Path], list[str]]:
    """Every shipped backend .py file, plus any declared root that had none."""
    files: list[Path] = []
    empty: list[str] = []
    for rel in BACKEND_ROOTS:
        found = [p for p in _walk(root, rel, (".py",)) if not _is_backend_test(p)]
        if not found:
            empty.append(rel)
        files.extend(found)
    return files, empty


def check_python(root: Path, floor: int) -> Check:
    check = Check("python", floor=floor, roots_const="BACKEND_ROOTS")
    files, check.empty_roots = _backend_sources(root)
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:  # a file we cannot parse is not a file we checked
            check.findings.append(Finding(str(path), f"unparseable: {exc}"))
            continue
        check.walked += 1
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            for match in URL.finditer(node.value):
                if not match.group("scheme"):
                    continue  # bare `//x` inside a string is a path, not a URL
                host = match.group("host")
                if is_local(host):
                    continue
                check.findings.append(
                    Finding(
                        f"{path.relative_to(root)}:{node.lineno}",
                        f"string literal names external host {host!r}",
                    )
                )
    return check


# --------------------------------------------------------------------------
# 2. FastAPI's built-in explorer pages (structural — the URLs are upstream's)
# --------------------------------------------------------------------------
def check_fastapi_docs(root: Path, floor: int) -> Check:
    check = Check("fastapi-docs", floor=floor)
    files, _ = _backend_sources(root)
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name != "FastAPI":
                continue
            check.walked += 1
            where = f"{path.relative_to(root)}:{node.lineno}"
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
            for arg in ("docs_url", "redoc_url"):
                value = kwargs.get(arg)
                disabled = isinstance(value, ast.Constant) and value.value is None
                if not disabled:
                    check.findings.append(
                        Finding(
                            where,
                            f"FastAPI(...) does not pass {arg}=None; the page it "
                            f"serves loads assets from {FASTAPI_DOC_CDNS[0]} et al.",
                        )
                    )
    check.notes.append(
        f"{check.walked} FastAPI(...) construction site(s); "
        f"{len(FASTAPI_DOC_CDNS)} upstream CDN refs prevented"
    )
    return check


# --------------------------------------------------------------------------
# 3. Web source + markup
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class WebRoot:
    """One declared frontend root: where to look, at what, and how to read it.

    The suffixes and the scan mode travel WITH the root because the two
    surfaces fail differently: in markup a ``src``/``href``/``url()`` IS a
    fetch, whereas in code only an absolute URL outside a comment is.
    """

    rel: str
    suffixes: tuple[str, ...]
    #: "markup" -> src/href/url()/@import refs, relative ones included.
    #: "code"   -> absolute URLs only, comments stripped first.
    surface: str


#: EVERY frontend tree that ships in the bundle, in ONE place — the sibling of
#: ``BACKEND_ROOTS`` above, and hoisted for the same reason. These roots used to
#: be an inline literal tuple inside a comprehension in ``check_web``, with no
#: per-root census at all, so this check had exactly the blindness `977f492`
#: fixed for the backend: measured, stubbing ``packages/design/src`` to empty
#: took the walk from 315 to 277 against a floor of 200 and the gate printed
#: ``ok`` — the entire design system (tokens, primitives, CSS) scanned by
#: nothing while the air-gap verdict stayed green. Renaming or moving a package
#: is not hypothetical here; it is what happened to ``py_kit.schemas``.
WEB_ROOTS = (
    WebRoot("apps/web", (".html",), "markup"),
    WebRoot("apps/web/src", (".ts", ".tsx", ".css"), "code"),
    WebRoot("packages/design/src", (".ts", ".tsx", ".css"), "code"),
)


def _web_sources(root: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    """Every shipped frontend file with its surface, plus any root that had none."""
    files: list[tuple[Path, str]] = []
    empty: list[str] = []
    for web_root in WEB_ROOTS:
        found = [
            p
            for p in _walk(root, web_root.rel, web_root.suffixes)
            if not _is_frontend_test(p)
        ]
        if not found:
            empty.append(web_root.rel)
        files.extend((p, web_root.surface) for p in found)
    return files, empty


def _strip_ts_comments(text: str) -> str:
    """Blank out // and /* */ comments so a documented URL is not a finding.

    Written as a scanner rather than a regex because ``"https://x"`` contains
    the very token that opens a line comment — the naive version reports every
    URL in the tree as commented out, which is a gate that cannot fail.
    """
    out: list[str] = []
    i, n = 0, len(text)
    state = None  # None | "line" | "block" | '"' | "'" | "`"
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state is None:
            if ch == "/" and nxt == "/":
                state, i = "line", i + 2
                out.append("  ")
                continue
            if ch == "/" and nxt == "*":
                state, i = "block", i + 2
                out.append("  ")
                continue
            if ch in "\"'`":
                state = ch
            out.append(ch)
        elif state == "line":
            if ch == "\n":
                state = None
                out.append(ch)
            else:
                out.append(" ")
        elif state == "block":
            if ch == "*" and nxt == "/":
                state, i = None, i + 2
                out.append("  ")
                continue
            out.append(" " if ch != "\n" else ch)
        else:  # inside a string literal
            if ch == "\\":
                out.append(ch)
                if i + 1 < n:
                    out.append(nxt)
                i += 2
                continue
            if ch == state:
                state = None
            out.append(ch)
        i += 1
    return "".join(out)


def check_web(root: Path, floor: int) -> Check:
    check = Check("web", floor=floor, roots_const="WEB_ROOTS")
    files, check.empty_roots = _web_sources(root)

    for path, surface in files:
        check.walked += 1
        raw = path.read_text(encoding="utf-8", errors="replace")

        if surface == "markup":
            for pattern in (HTML_REF, CSS_REF):
                for ref in pattern.findall(raw):
                    match = URL.match(ref if "//" in ref[:8] else f"//{ref}")
                    host = match.group("host") if match else ref
                    if not is_local(host):
                        check.findings.append(
                            Finding(
                                str(path.relative_to(root)),
                                f"external asset {ref}",
                            )
                        )
            continue

        text = raw if path.suffix == ".css" else _strip_ts_comments(raw)
        for match in URL.finditer(text):
            if not match.group("scheme") and path.suffix != ".css":
                continue
            host = match.group("host")
            if is_local(host) or host.endswith(".test"):
                continue
            line = text[: match.start()].count("\n") + 1
            check.findings.append(
                Finding(
                    f"{path.relative_to(root)}:{line}",
                    f"code references external host {host!r}",
                )
            )
    return check


def check_dist(dist: Path, floor: int) -> Check:
    """Built-bundle cross-check: HTML/CSS only, where a ref IS a fetch.

    Deliberately NOT the JS chunks. A production bundle inlines every
    dependency's error-message URLs (measured on this repo's 2.1 MB chunk:
    docs.pmnd.rs, github.com, jcgt.org — all `throw new Error` text and one
    GLSL citation), so scanning them yields a list nobody can act on. The
    source scan above owns our own code; this owns what the build EMITTED.
    """
    check = Check("dist", floor=floor)
    for path in sorted(dist.rglob("*")):
        if not path.is_file() or path.suffix not in (".html", ".css"):
            continue
        check.walked += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in (HTML_REF, CSS_REF):
            for ref in pattern.findall(text):
                match = URL.match(ref if ref.startswith(("http", "//")) else f"//{ref}")
                host = match.group("host") if match else ref
                if not is_local(host):
                    check.findings.append(
                        Finding(str(path.name), f"built asset fetches {ref}")
                    )
    return check


# --------------------------------------------------------------------------
# 4. Fonts — a POSITIVE control, not an absence
# --------------------------------------------------------------------------
def check_fonts(root: Path, floor: int) -> Check:
    check = Check("fonts", floor=floor)
    path = root / "packages/design/src/fonts.ts"
    if not path.exists():
        return check  # walked == 0 -> the vacuity guard reports it
    tree = ast_imports(path.read_text(encoding="utf-8", errors="replace"))
    for spec in tree:
        check.walked += 1
        if not spec.startswith("@fontsource"):
            check.findings.append(
                Finding(
                    "packages/design/src/fonts.ts",
                    f"font import {spec!r} is not a self-hosted @fontsource package",
                )
            )
    check.notes.append(f"{check.walked} self-hosted font face(s)")
    return check


def ast_imports(text: str) -> list[str]:
    """Every module specifier in a TS file's bare/side-effect imports."""
    return re.findall(r"""^\s*import\s+["']([^"']+)["']""", text, re.MULTILINE)


# --------------------------------------------------------------------------
# 5/6. Compose + Dockerfile — run time, as distinct from build time
# --------------------------------------------------------------------------
RUNTIME_DIRECTIVES = ("CMD", "ENTRYPOINT", "HEALTHCHECK")


def check_compose(root: Path, floor: int) -> Check:
    check = Check("compose", floor=floor)
    images: list[str] = []
    for path in sorted(root.glob("docker-compose*.yml")):
        check.walked += 1
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # a comment is documentation
            if stripped.startswith("image:"):
                images.append(stripped.split(":", 1)[1].strip())
                continue
            for match in URL.finditer(line.split(" #", 1)[0]):
                if not match.group("scheme"):
                    continue
                host = match.group("host")
                if is_local(host):
                    continue
                check.findings.append(
                    Finding(
                        f"{path.name}:{lineno}",
                        f"a running container would reach external host {host!r}",
                    )
                )
    check.notes.append(
        "images to MIRROR for an air-gapped install: " + ", ".join(sorted(set(images)))
    )
    return check


#: Directives that make the SERVER open a connection of its own. A hostname
#: anywhere else in an nginx config is a name it serves, not a name it fetches.
_NGINX_EGRESS = re.compile(
    r"^\s*(proxy_pass|fastcgi_pass|uwsgi_pass|scgi_pass|grpc_pass|resolver|"
    r"proxy_ssl_trusted_certificate|auth_jwt_key_request)\s+(?P<rest>.+?);?\s*$"
)
#: `set $name "value";` — nginx's only assignment, and the thing that makes an
#: upstream invisible to a naive URL scan (see the docstring below).
_NGINX_SET = re.compile(
    r"""^\s*set\s+(?P<name>\$[A-Za-z0-9_]+)\s+["']?(?P<value>[^"';]+)"""
)
#: host[:port] left after variable substitution.
_HOSTPORT = re.compile(r"^(?P<host>[A-Za-z0-9._-]+)(?::\d+)?$")


def check_static_server(root: Path, floor: int) -> Check:
    """The web edge's own config — what the RUNNING nginx connects to.

    A NEW SURFACE, added with the web service (2026-09-15). The five checks
    above grade application source, compose and Dockerfiles; none of them can
    see a reverse-proxy config, and this one is a process that makes outbound
    connections on behalf of every user of the product. A `proxy_pass` at an
    analytics host, or a `resolver 8.8.8.8`, would be egress from the one
    container a self-hoster publishes, and every other check in this file would
    pass.

    It does NOT reuse the plain URL scan, and that is the whole reason it is a
    function rather than three lines added to `check_dockerfile`. The upstream
    is written `proxy_pass http://$loft_gateway$request_uri;` — deliberately,
    so nginx re-resolves it per request instead of caching a dead container's
    IP forever. `URL`'s host class is `[A-Za-z0-9._-]+`, which `$` is not in,
    so the scan matches NOTHING there: the single most important line in the
    file is invisible to it, and a check that reported `ok` on that basis would
    be measuring its own blind spot. So variables are RESOLVED from the `set`
    directives in the same file before the host is read.
    """
    check = Check("static-server", floor=floor)
    base = root / "deploy/docker/web"
    if not base.is_dir():
        return check  # walked == 0 -> the vacuity guard reports it

    for path in sorted(base.rglob("*.conf")):
        text = path.read_text(encoding="utf-8", errors="replace")
        variables: dict[str, str] = {}
        for line in text.splitlines():
            assignment = _NGINX_SET.match(line.split("#", 1)[0])
            if assignment:
                variables[assignment.group("name")] = assignment.group("value").strip()

        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            check.walked += 1
            where = f"{path.relative_to(root)}:{lineno}"

            # (a) any absolute URL, wherever it appears
            for match in URL.finditer(line):
                host = match.group("host")
                if not is_local(host):
                    check.findings.append(
                        Finding(
                            where,
                            f"nginx config references external host {host!r}",
                        )
                    )

            # (b) the egress directives, with variables substituted
            egress = _NGINX_EGRESS.match(line)
            if not egress:
                continue
            for token in egress.group("rest").split():
                resolved = token
                for name, value in variables.items():
                    resolved = resolved.replace(name, value)
                # Strip a scheme and anything after the authority; drop the
                # leftovers of unresolved nginx variables ($request_uri etc.).
                resolved = resolved.split("://", 1)[-1].split("/", 1)[0]
                resolved = resolved.split("$", 1)[0].rstrip(";")
                hostport = _HOSTPORT.match(resolved)
                if not hostport or not resolved:
                    continue  # a flag like `valid=10s`, or `ipv6=off`
                host = hostport.group("host")
                if host in ("valid", "ipv6", "on", "off"):
                    continue
                if not is_local(host):
                    check.findings.append(
                        Finding(
                            where,
                            f"{egress.group(1)} would connect to external host "
                            f"{host!r} at request time",
                        )
                    )
    check.notes.append(f"{check.walked} nginx directive line(s) graded")
    return check


def check_dockerfile(root: Path, floor: int) -> Check:
    check = Check("dockerfile", floor=floor)
    froms: list[str] = []
    base = root / "deploy"
    files = [
        p for p in sorted(base.rglob("*")) if p.is_file() and "Dockerfile" in p.name
    ]
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        # `FROM deps AS build` names an EARLIER STAGE, not an image. Collect the
        # stage names first so the mirror list below does not tell an air-gapped
        # operator to go and find an image called "deps" (it did, the day the
        # multi-stage web image landed). The note is advice somebody acts on, so
        # a wrong entry in it costs a real person real time.
        stages = {
            parts[3].lower()
            for parts in (line.strip().split() for line in lines)
            if len(parts) >= 4
            and parts[0].upper() == "FROM"
            and parts[2].upper() == "AS"
        }
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            head = stripped.split(" ", 1)[0].upper()
            if head == "FROM":
                reference = stripped.split(" ")[1]
                if reference.lower() not in stages:
                    froms.append(reference)
            if head not in RUNTIME_DIRECTIVES:
                continue
            check.walked += 1
            for match in URL.finditer(stripped):
                if not match.group("scheme"):
                    continue
                host = match.group("host")
                if is_local(host):
                    continue
                check.findings.append(
                    Finding(
                        f"{path.name}:{lineno}",
                        f"{head} reaches external host {host!r} at container RUN time",
                    )
                )
    check.notes.append("base images to MIRROR: " + ", ".join(sorted(set(froms))))
    return check


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
#: Floors re-measured against the tree at the commit this landed on
#: (2026-09-15, after the loft-wire/loft-script split): 156 backend source
#: files, 1 FastAPI site, 1 html + 319 ts/tsx/css, 4 font faces, 3 compose
#: files, 3 Dockerfile runtime directives, 58 nginx directive lines. Set well
#: below the real numbers so ordinary churn never trips them, and well above
#: zero so a walk that collapses does.
#:
#: A FLOOR IS A COLLAPSE DETECTOR AND NOTHING MORE. `python` was 147 against a
#: floor of 100; fifteen modules moved into a new distribution, the count fell
#: to 132, the gate said `ok`, and the new package was scanned by nothing. No
#: floor low enough to survive churn can catch that, so the real guard for
#: shrinkage is `Check.empty_roots` — a per-root census that refuses when any
#: DECLARED root contributes zero files. Raise these when the tree grows; do
#: not rely on them to notice coverage leaving.
#:
#: THE DIVISION OF LABOUR, written here because the next reader will otherwise
#: re-derive a floor and believe they have fixed this:
#:
#:   * the FLOOR catches TOTAL COLLAPSE — a walk that finds (almost) nothing,
#:     e.g. the gate pointed at the wrong root, or run from the wrong cwd. It
#:     is a single number over the whole check and it is all it can be.
#:   * the PER-ROOT CENSUS (`Check.empty_roots`) catches a SHRINK — one
#:     declared subtree going to zero while the total stays healthy. This is
#:     what a refactor produces, and it is invisible to any floor.
#:
#: Both root-declaring checks now carry both: `python` over `BACKEND_ROOTS`
#: and `web` over `WEB_ROOTS`. Measured on the real tree before the census
#: existed — stub `packages/design/src` to empty and `web` goes 315 -> 277
#: against this floor of 200 and prints `ok`. A check that adds a root list
#: without a census inherits exactly that hole, so add the root to the named
#: constant rather than inlining it at the call site.
REAL_FLOORS = {
    "python": 120,
    "fastapi-docs": 1,
    "web": 200,
    "fonts": 3,
    "compose": 3,
    "dockerfile": 2,
    "static-server": 25,
    "dist": 2,
}


def run_checks(
    root: Path, floors: dict[str, int], dist: Path | None = None
) -> list[Check]:
    checks = [
        check_python(root, floors["python"]),
        check_fastapi_docs(root, floors["fastapi-docs"]),
        check_web(root, floors["web"]),
        check_fonts(root, floors["fonts"]),
        check_compose(root, floors["compose"]),
        check_dockerfile(root, floors["dockerfile"]),
        check_static_server(root, floors["static-server"]),
    ]
    if dist is not None:
        checks.append(check_dist(dist, floors["dist"]))
    return checks


def report(checks: list[Check], quiet: bool = False) -> int:
    failed = 0
    for check in checks:
        if check.vacuous:
            failed = max(failed, 2)
            if check.empty_roots:
                print(
                    f"REFUSED  {check.name}: found NO files under "
                    f"{', '.join(check.empty_roots)} — a declared source root "
                    "is scanned by nothing, so this check's `ok` would be an "
                    "`ok` about a smaller product than the one we ship. Either "
                    f"the tree moved (update {check.roots_const or 'the root list'}"
                    ") or it is gone.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"REFUSED  {check.name}: walked {check.walked} of an expected "
                    f"{check.floor}+ — this check examined (almost) nothing, so its "
                    f"verdict is not evidence.",
                    file=sys.stderr,
                )
            continue
        if check.findings:
            failed = max(failed, 1)
            print(f"FAIL     {check.name}: {len(check.findings)} finding(s)")
            for finding in check.findings:
                print(f"           {finding.where}: {finding.detail}")
        elif not quiet:
            print(f"ok       {check.name}: {check.walked} walked")
        for note in check.notes:
            if not quiet:
                print(f"           note: {note}")
    if failed == 1:
        print(
            "\nair-gap: the running product reaches the public internet. "
            "README.md claims it does not.",
            file=sys.stderr,
        )
    return failed


# --------------------------------------------------------------------------
# Self-test: build the defects and DEMAND a failure for each.
# --------------------------------------------------------------------------
_CLEAN_PY = '''"""Docs may cite https://example.com/spec freely."""

# A comment may also cite https://example.com — documentation, not egress.
GEOMETRY = "http://localhost:8002"
SVG_NS = "http://www.w3.org/2000/svg"
'''

_CLEAN_APP = """from fastapi import FastAPI

app = FastAPI(title="t", version="1", docs_url=None, redoc_url=None)
"""

_CLEAN_HTML = """<!doctype html>
<html><head><title>Loft</title></head>
<body><script type="module" src="/src/main.tsx"></script></body></html>
"""

_CLEAN_TSX = """// see https://example.com/why for the rationale
const SVG_NS = "http://www.w3.org/2000/svg";
export const base = "/api/v1";
"""

_CLEAN_FONTS = """import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/fragment-mono/400.css";
"""

_CLEAN_COMPOSE = """name: loft
services:
  minio:
    image: quay.io/minio/minio:RELEASE.2024-12-18T13-15-44Z
  geometry:
    image: loft/geometry
    environment:
      S3_URL: http://minio:9000
"""

_CLEAN_DOCKERFILE = """FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y curl
HEALTHCHECK CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/healthz" || exit 1
CMD exec uvicorn "${SERVICE_NAME}.main:app" --host 0.0.0.0
"""


_CLEAN_NGINX = """map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 8080;
    root /usr/share/nginx/html;
    location /assets/ {
        try_files $uri =404;
    }
    location /api/ {
        resolver 127.0.0.11 valid=10s ipv6=off;
        set $loft_gateway "gateway:8000";
        proxy_pass http://$loft_gateway$request_uri;
        proxy_set_header Host $host;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""


def _fixture(root: Path) -> None:
    (root / "services/gateway/src/gateway").mkdir(parents=True)
    (root / "packages/py-kit/src/py_kit").mkdir(parents=True)
    (root / "packages/loft-wire/src/loft_wire").mkdir(parents=True)
    (root / "packages/loft-script/src/loft").mkdir(parents=True)
    (root / "packages/loft-wire/src/loft_wire/auth.py").write_text(_CLEAN_PY)
    (root / "packages/loft-script/src/loft/transport.py").write_text(_CLEAN_PY)
    (root / "apps/web/src").mkdir(parents=True)
    (root / "packages/design/src").mkdir(parents=True)
    (root / "deploy/docker/web").mkdir(parents=True)
    (root / "deploy/docker/web/nginx.conf").write_text(_CLEAN_NGINX)
    (root / "services/gateway/src/gateway/main.py").write_text(_CLEAN_PY)
    (root / "packages/py-kit/src/py_kit/app.py").write_text(_CLEAN_APP)
    (root / "apps/web/index.html").write_text(_CLEAN_HTML)
    (root / "apps/web/src/App.tsx").write_text(_CLEAN_TSX)
    (root / "packages/design/src/fonts.ts").write_text(_CLEAN_FONTS)
    (root / "docker-compose.yml").write_text(_CLEAN_COMPOSE)
    (root / "deploy/docker/service.Dockerfile").write_text(_CLEAN_DOCKERFILE)


#: Floors for the fixture tree, which is deliberately tiny. The REAL floors get
#: their own negative control below (an empty tree must be REFUSED, not passed).
_FIXTURE_FLOORS = {k: 1 for k in REAL_FLOORS}

_MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "cdn-link-in-html",
        "apps/web/index.html",
        "<body>",
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/x.css" /><body>',
    ),
    (
        "google-font-link",
        "apps/web/index.html",
        "<body>",
        '<link href="https://fonts.googleapis.com/css?family=Inter" '
        'rel="stylesheet"><body>',
    ),
    (
        "fetch-in-web-code",
        "apps/web/src/App.tsx",
        'export const base = "/api/v1";',
        'export const base = "https://telemetry.loft.example/v1";',
    ),
    (
        "url-in-python-code",
        "services/gateway/src/gateway/main.py",
        'GEOMETRY = "http://localhost:8002"',
        'GEOMETRY = "https://updates.loft.example/check"',
    ),
    (
        "fastapi-docs-default",
        "packages/py-kit/src/py_kit/app.py",
        'app = FastAPI(title="t", version="1", docs_url=None, redoc_url=None)',
        'app = FastAPI(title="t", version="1")',
    ),
    (
        "fastapi-redoc-only",
        "packages/py-kit/src/py_kit/app.py",
        "docs_url=None, redoc_url=None",
        "docs_url=None",
    ),
    (
        "cdn-font-not-fontsource",
        "packages/design/src/fonts.ts",
        "@fontsource/fragment-mono/400.css",
        "https://fonts.googleapis.com/css?family=Fragment+Mono",
    ),
    (
        "compose-runtime-download",
        "docker-compose.yml",
        "S3_URL: http://minio:9000",
        "S3_URL: http://minio:9000\n"
        "    command: sh -c 'curl https://get.example.com/x | sh'",
    ),
    (
        "healthcheck-phones-home",
        "deploy/docker/service.Dockerfile",
        'HEALTHCHECK CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/healthz" || exit 1',
        'HEALTHCHECK CMD curl -fsS "https://status.loft.example/ping" || exit 1',
    ),
    # THE ONE THE PLAIN URL SCAN CANNOT SEE. The upstream is reached through an
    # nginx variable, so `//` is never followed by a hostname anywhere in the
    # file; only the substitution in check_static_server finds it. Reverting
    # that substitution is the negative control for the whole check.
    (
        "nginx-proxies-offbox",
        "deploy/docker/web/nginx.conf",
        'set $loft_gateway "gateway:8000";',
        'set $loft_gateway "telemetry.loft.example:443";',
    ),
    (
        "nginx-public-resolver",
        "deploy/docker/web/nginx.conf",
        "resolver 127.0.0.11 valid=10s ipv6=off;",
        "resolver 8.8.8.8 valid=10s ipv6=off;",
    ),
    # A static server can also serve egress by INJECTING it into the document
    # it returns, which no amount of auditing the bundle would catch.
    (
        "nginx-injects-cdn",
        "deploy/docker/web/nginx.conf",
        "    listen 8080;",
        "    listen 8080;\n"
        '    sub_filter "</head>" '
        '"<script src=\\"https://cdn.jsdelivr.net/npm/x.js\\"></script></head>";',
    ),
]


def self_test() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "clean"
        root.mkdir()
        _fixture(root)
        checks = run_checks(root, _FIXTURE_FLOORS)
        bad = [f"{c.name}:{f.where} {f.detail}" for c in checks for f in c.findings]
        vac = [c.name for c in checks if c.vacuous]
        if bad or vac:
            failures.append(
                f"POSITIVE CONTROL: a clean tree must pass, got findings={bad} "
                f"vacuous={vac}"
            )
        else:
            print("ok  positive control: the clean fixture passes")

    # The vacuity guard, against the REAL floors — this is the check that a
    # sibling gate ("0 COPY source(s) reach the build context", exit 0) did not
    # have. An empty tree must be REFUSED, never quietly blessed.
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "empty"
        empty.mkdir()
        checks = run_checks(empty, REAL_FLOORS)
        refused = [c.name for c in checks if c.vacuous]
        expected = {
            "python",
            "fastapi-docs",
            "web",
            "fonts",
            "compose",
            "dockerfile",
            "static-server",
        }
        if set(refused) != expected:
            failures.append(
                f"VACUITY GUARD: an empty tree must refuse every check; "
                f"refused={sorted(refused)} expected={sorted(expected)}"
            )
        else:
            print(f"ok  vacuity guard: an empty tree refuses all {len(refused)} checks")

    # THE SHRINK CONTROLS, and the reason Check.empty_roots exists. Reproduces
    # the 2026-09-15 defect exactly: a declared root that the check walks
    # NOTHING in, while the total stays far above the floor. Without the
    # per-root census these cases report `ok`.
    #
    # EVERY declared root is emptied IN TURN, for both root-declaring checks.
    # A control that only empties one root cannot see a census that forgot a
    # DIFFERENT root — which is the whole defect being fixed here, since
    # `check_web` had a census for none of its three.
    #
    # Each case asserts the FLOOR IS STILL SATISFIED (`walked >= floor`) before
    # asserting the refusal. That is what isolates the guard under test: if the
    # shrink also dropped the total below the floor, the refusal would be the
    # floor firing and the control would pass while proving nothing about the
    # census. So the two assertions together ARE the "floor says ok, census
    # says REFUSED" negative control, checked on every run.
    shrink_cases = [
        *((check_python, rel, (".py",)) for rel in BACKEND_ROOTS),
        *((check_web, r.rel, r.suffixes) for r in WEB_ROOTS),
    ]
    for factory, rel, suffixes in shrink_cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shrunk"
            root.mkdir()
            _fixture(root)
            for orphan in (root / rel).rglob("*"):
                if orphan.is_file() and orphan.suffix in suffixes:
                    orphan.unlink()
            shrunk = factory(root, 1)
            floor_only_ok = shrunk.walked >= shrunk.floor
            if not floor_only_ok:
                failures.append(
                    f"SHRINK CONTROL [{shrunk.name}/{rel}]: the fixture fell BELOW "
                    f"the floor (walked {shrunk.walked} < {shrunk.floor}), so this "
                    "case tests the floor, not the per-root census. Give the "
                    "fixture more files outside this root."
                )
            elif not shrunk.vacuous or rel not in shrunk.empty_roots:
                failures.append(
                    f"SHRINK CONTROL [{shrunk.name}/{rel}]: a declared root with no "
                    f"files must REFUSE; vacuous={shrunk.vacuous} "
                    f"empty_roots={shrunk.empty_roots} walked={shrunk.walked}"
                )
            else:
                print(
                    f"ok  shrink control [{shrunk.name}/{rel}]: floor satisfied "
                    f"(walked {shrunk.walked} >= {shrunk.floor}) yet the census "
                    "REFUSES"
                )

    # The MIRROR of the shrink control: the census must not fire on a healthy
    # tree. A guard written against one failure encodes that failure's
    # direction, and an over-eager census that names a populated root would be
    # a gate that cries wolf — which is how a gate gets muted.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "healthy"
        root.mkdir()
        _fixture(root)
        noisy = [
            (c.name, c.empty_roots)
            for c in (check_python(root, 1), check_web(root, 1))
            if c.empty_roots
        ]
        if noisy:
            failures.append(
                f"CENSUS FALSE-POSITIVE CONTROL: every declared root is populated "
                f"in the fixture, yet the census named {noisy}"
            )
        else:
            print(
                "ok  census false-positive control: a populated tree names no "
                "empty root"
            )

    for name, rel, old, new in _MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mutated"
            root.mkdir()
            _fixture(root)
            target = root / rel
            text = target.read_text()
            if old not in text:
                failures.append(f"{name}: fixture anchor {old!r} not found in {rel}")
                continue
            target.write_text(text.replace(old, new, 1))
            checks = run_checks(root, _FIXTURE_FLOORS)
            hits = sum(len(c.findings) for c in checks)
            if hits == 0:
                failures.append(
                    f"{name}: the gate did NOT fail on an injected defect in {rel}"
                )
            else:
                print(f"ok  {name}: {hits} finding(s)")

    if failures:
        print("\nSELF-TEST FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    controls = 3 + len(shrink_cases)  # positive, vacuity, census false-positive
    print(
        f"\nself-test passed ({len(_MUTATIONS)} defects reproduced, "
        f"{controls} controls)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_modern_python()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--dist",
        type=Path,
        default=None,
        help="also scan a built web bundle's HTML/CSS (e.g. apps/web/dist)",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    dist = args.dist
    if dist is not None and not dist.is_absolute():
        dist = args.root / dist
    if dist is not None and not dist.exists():
        print(f"air-gap: --dist {dist} does not exist (build first)", file=sys.stderr)
        return 2
    return report(run_checks(args.root, REAL_FLOORS, dist), quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
