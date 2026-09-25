#!/usr/bin/env python3
"""Render deploy/docker/web/nginx.conf so it can run OUTSIDE the container.

WHY THIS EXISTS. `apps/web`'s entire e2e suite drives the Vite DEV server, so
nothing had ever loaded the PRODUCTION bundle, and nothing had ever loaded it
through the production server. Those are two different gaps and only one of
them is about the bundle: the deployed app is served by nginx with a
Content-Security-Policy that the dev server does not emit, and a CSP that
blocks a worker, a blob: URL or an inlined font is a total failure that ships
green — the page still renders, so every status-code probe agrees it is fine.

The container that serves it cannot be built in the dev container (the Docker
registry is policy-denied, CONNECT 403), and CI's browser workflow has no
daemon either. But nginx is just a binary, and the config is just a file. So
this script takes the REAL config and rewrites the four directives that are
about the CONTAINER rather than about the app — where it listens, where the
bundle is, and how it finds the gateway — and refuses if it had to touch
anything else.

THAT REFUSAL IS THE WHOLE POINT, and it is what makes the leg evidence rather
than theatre. A leg that ran against a hand-written "production-like" config
would prove nothing about what we ship: the failure it exists to catch is a
mistake IN THAT FILE. So the rendering is line-addressed and fully asserted —
every substitution must match exactly once, and every `add_header` line (the
security headers and the CSP among them) must come through BYTE-IDENTICAL.
If the config is reshaped so that a pattern stops matching, this exits non-zero
and names the pattern instead of silently serving a config that has quietly
lost a header.

Run `--self-test` for the negative controls: each one breaks one guarantee and
demands a refusal.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CONF = REPO_ROOT / "deploy" / "docker" / "web" / "nginx.conf"

# Where mime.types might live. The alpine image and Debian/Ubuntu agree on the
# path; the list exists so a missing file is a named failure rather than a
# mystery `text/plain` on every .js the browser then refuses to execute as a
# module — which would look exactly like a CSP violation and is not one.
MIME_TYPES_CANDIDATES = (
    Path("/etc/nginx/mime.types"),
    Path("/usr/local/nginx/conf/mime.types"),
    Path("/opt/homebrew/etc/nginx/mime.types"),
)


@dataclass(frozen=True)
class Rewrite:
    """One directive that is about the CONTAINER, not about the app."""

    name: str
    pattern: re.Pattern[str]
    why: str


# Exactly these four, and the `why` is not decoration: it is the argument that
# the rewrite cannot change what the leg measures.
REWRITES: tuple[Rewrite, ...] = (
    Rewrite(
        "listen",
        re.compile(r"^(\s*)listen\s+8080;\s*$"),
        "8080 is the container port; a native run needs a free one and must "
        "bind the LITERAL loopback address (this container has no IPv6 "
        "loopback and every CI runner is dual-stack).",
    ),
    Rewrite(
        "root",
        re.compile(r"^(\s*)root\s+/usr/share/nginx/html;\s*$"),
        "the bundle is COPYed to that path in the image; natively it is apps/web/dist.",
    ),
    Rewrite(
        "resolver",
        re.compile(r"^(\s*)resolver\s+127\.0\.0\.11\b.*;\s*$"),
        "127.0.0.11 is Docker's embedded DNS and exists only on a "
        "user-defined network. The upstream below becomes a literal address, "
        "so no name is ever resolved and no resolver is needed.",
    ),
    Rewrite(
        "gateway",
        re.compile(r"^(\s*)set\s+\$loft_gateway\s+\"gateway:8000\";\s*$"),
        "`gateway` is the compose service name; natively the gateway is a "
        "uvicorn on the loopback.",
    ),
)


class RenderError(RuntimeError):
    """The config could not be rendered without changing what it means."""


def render(source: str, *, port: int, root: Path, gateway: str) -> str:
    """Rewrite the four container directives. Refuse on anything else.

    Every rewrite must match EXACTLY ONCE. Zero means the config was reshaped
    and this script is now rendering something it does not understand; more
    than one means a second copy of the directive would be left behind or
    clobbered. Both are refusals, because the alternative is a leg that
    silently tests a config nobody wrote.
    """
    lines = source.splitlines(keepends=True)
    out = list(lines)
    hits: dict[str, list[int]] = {rw.name: [] for rw in REWRITES}

    for index, line in enumerate(lines):
        for rewrite in REWRITES:
            match = rewrite.pattern.match(line)
            if match is None:
                continue
            hits[rewrite.name].append(index)
            indent = match.group(1)
            if rewrite.name == "listen":
                out[index] = f"{indent}listen 127.0.0.1:{port};\n"
            elif rewrite.name == "root":
                out[index] = f"{indent}root {root};\n"
            elif rewrite.name == "resolver":
                out[index] = (
                    f"{indent}# resolver: dropped by scripts/render-web-nginx.py "
                    f"(no Docker DNS off-container; the upstream below is a literal)\n"
                )
            elif rewrite.name == "gateway":
                out[index] = f'{indent}set $loft_gateway "{gateway}";\n'

    problems: list[str] = []
    for rewrite in REWRITES:
        count = len(hits[rewrite.name])
        if count != 1:
            problems.append(
                f"  {rewrite.name}: matched {count} line(s), expected exactly 1\n"
                f"      pattern: {rewrite.pattern.pattern}\n"
                f"      why it is rewritten: {rewrite.why}"
            )
    if problems:
        raise RenderError(
            "REFUSED: deploy/docker/web/nginx.conf no longer has the shape this "
            "renderer understands, so a rendered config would not be the config "
            "we ship.\n" + "\n".join(problems)
        )

    rendered = "".join(out)
    _assert_only_expected_lines_changed(lines, out, hits)
    _assert_headers_are_byte_identical(source, rendered)
    return rendered


def _assert_only_expected_lines_changed(
    before: list[str], after: list[str], hits: dict[str, list[int]]
) -> None:
    """No line outside the four rewrites may differ. Line counts must match."""
    if len(before) != len(after):
        raise RenderError(
            f"REFUSED: the render changed the line count "
            f"({len(before)} -> {len(after)})"
        )
    expected = {index for indices in hits.values() for index in indices}
    changed = {i for i in range(len(before)) if before[i] != after[i]}
    # SUBSET, not equality. The first version demanded `changed == expected`
    # and was wrong in one direction: `--check-only` renders with the
    # container's own root, so that rewrite legitimately produces a byte-
    # identical line and the gate refused a perfectly good config. A rewrite
    # that writes back the same value is not a defect — the match-count check
    # above is what proves the directive was FOUND. What must never happen is a
    # line changing that nobody asked to change, and that is `changed -
    # expected`.
    stray = sorted(changed - expected)
    if stray:
        raise RenderError(
            "REFUSED: the render touched lines it was not supposed to: "
            f"{stray}\n"
            + "\n".join(
                f"  {i}: {before[i].rstrip()} -> {after[i].rstrip()}" for i in stray
            )
        )


# The security headers are the SUBJECT of the leg, so they are the one thing a
# renderer must not be able to influence. Compared by full line, in order, so a
# reordering, a dropped repetition or a changed value all fail — and the COUNT
# is asserted against a floor, because "all zero of them match" is the vacuous
# pass this repo has shipped four times.
HEADER_FLOOR = 4  # >= one server-level trio plus the CSP; see nginx.conf

# One per location that emits a document AND carries any add_header of its own,
# plus the server block: today that is the server, `/assets/`,
# `= /index.html` and `/api/`. nginx's add_header is NOT additive across
# levels, so a location that re-adds a SUBSET silently serves without the rest
# — which has already happened once in this file, to two of the three security
# headers. The renderer is the cheapest place that can count them: it runs in
# `just lint` via --check-only, with no browser and no daemon.
CSP_HEADER_FLOOR = 4


def _assert_headers_are_byte_identical(source: str, rendered: str) -> None:
    before = [ln for ln in source.splitlines() if "add_header" in ln]
    after = [ln for ln in rendered.splitlines() if "add_header" in ln]
    if len(before) < HEADER_FLOOR:
        raise RenderError(
            f"REFUSED: only {len(before)} add_header line(s) in "
            f"{SOURCE_CONF.name}, expected at least {HEADER_FLOOR}. Either the "
            "config lost its headers or this check is reading the wrong file; "
            "a header census that walks nothing cannot fail for the reason it "
            "exists."
        )
    csp = [
        ln
        for ln in rendered.splitlines()
        if ln.lstrip().startswith("add_header Content-Security-Policy")
    ]
    if len(csp) < CSP_HEADER_FLOOR:
        raise RenderError(
            f"REFUSED: {len(csp)} `add_header Content-Security-Policy` line(s), "
            f"expected at least {CSP_HEADER_FLOOR} — the server block plus every "
            "location that carries any add_header of its own. nginx's add_header "
            "is not additive across levels, so a location that omits it serves "
            "the app with NO policy while every other location looks correct, "
            "and no status code anywhere says so."
        )
    if before != after:
        diff = "\n".join(
            difflib.unified_diff(before, after, "shipped", "rendered", lineterm="")
        )
        raise RenderError(
            "REFUSED: the render altered an add_header line. Those headers are "
            "exactly what the browser leg measures, so a rendered config that "
            "changes them proves nothing about what we ship.\n" + diff
        )


# ---------------------------------------------------------------------------
# THE POLICY, TRANSCRIBED FOUR TIMES ON PURPOSE — and held identical by this.
#
# The Content-Security-Policy is written out in four places, each beside a
# different oracle: the nginx config that SERVES it, `web-smoke.sh` (the real
# container, in deploy-path), `web-smoke-stub.py` (the stub that makes those
# assertions falsifiable in seconds), and the browser leg's `EXPECTED_CSP` (a
# real Chromium, against the real bundle). That duplication is deliberate: a
# check that reads the value out of the thing it is checking can only ever
# prove it equals itself, so the browser must be told INDEPENDENTLY what it
# should see.
#
# What duplication cannot survive is drift, so the four are compared here —
# cheaply, statically, in `just lint`, with no browser and no daemon. Note the
# vacuity guard: each extraction must match EXACTLY ONCE, because four copies
# that all read empty agree perfectly.
# ---------------------------------------------------------------------------
# ONE pattern for all four files, deliberately not anchored to each file's own
# syntax. The first version used a per-file anchor and broke twice in ten
# minutes — once when `ruff format` collapsed a parenthesised string onto its
# assignment line, once when a line-length suppression was appended to it. Both
# times the gate REFUSED rather than skipping the file, which is the behaviour
# it was built for, but a pattern that tracks formatting is a pattern that will
# keep costing that. What is actually invariant is the POLICY LITERAL: a
# double-quoted string beginning `default-src` and ending `frame-ancestors`.
# The exactly-one count guard below is what keeps the loose pattern honest.
POLICY_PATTERN = r'"(default-src[^"]*frame-ancestors[^"]*)"'

POLICY_SOURCES: tuple[tuple[str, str], ...] = (
    (
        "deploy/docker/web/nginx.conf",
        "the `set $loft_csp` definition the add_header lines reference",
    ),
    (
        "scripts/web-smoke.sh",
        "what the real container is asserted to serve",
    ),
    (
        "scripts/web-smoke-stub.py",
        "what the stub serves, so the assertion above can be watched failing",
    ),
    (
        "apps/web/e2e-dist/distSupport.ts",
        "what a real browser is told to expect",
    ),
)


def check_policy_consistency() -> None:
    found: dict[str, str] = {}
    problems: list[str] = []
    for path, why in POLICY_SOURCES:
        file = REPO_ROOT / path
        if not file.is_file():
            problems.append(f"  {path}: missing ({why})")
            continue
        matches = re.findall(POLICY_PATTERN, file.read_text())
        if len(matches) != 1:
            problems.append(
                f"  {path}: {len(matches)} match(es) for the policy, expected 1 "
                f"({why})\n      pattern: {POLICY_PATTERN}"
            )
            continue
        found[path] = matches[0]
    if problems:
        raise RenderError(
            "REFUSED: the Content-Security-Policy could not be read from every "
            "place it is written down. Four copies that all read empty would "
            "agree perfectly, so this refuses rather than comparing what it "
            "managed to find.\n" + "\n".join(problems)
        )

    distinct = set(found.values())
    if len(distinct) != 1:
        lines = "\n".join(f"  {path}:\n    {value}" for path, value in found.items())
        raise RenderError(
            "REFUSED: the Content-Security-Policy has drifted between the places "
            "it is written down. They are transcribed separately on purpose — "
            "each sits beside a different oracle — but they must say the same "
            "thing, or one of the gates is blessing a policy nobody ships.\n" + lines
        )

    # And the config must SERVE it through the variable, not through a second
    # literal somebody pasted into one location. A literal would be invisible
    # to the comparison above and would drift silently.
    conf = (REPO_ROOT / "deploy/docker/web/nginx.conf").read_text()
    literal_headers = [
        line
        for line in conf.splitlines()
        if line.lstrip().startswith("add_header Content-Security-Policy")
        and "$loft_csp" not in line
    ]
    if literal_headers:
        raise RenderError(
            "REFUSED: an `add_header Content-Security-Policy` line carries a "
            "literal policy instead of $loft_csp, so it is outside the "
            "consistency check above and will drift:\n"
            + "\n".join(f"  {line.strip()}" for line in literal_headers)
        )
    print(
        f"render-web-nginx: the CSP agrees across "
        f"{len(found)} independently-written copies"
    )


def mime_types_path() -> Path:
    for candidate in MIME_TYPES_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise RenderError(
        "REFUSED: no mime.types found in "
        + ", ".join(str(c) for c in MIME_TYPES_CANDIDATES)
        + ". Without it nginx serves every asset as the default type and the "
        "browser refuses the ES module — which reads like a CSP failure and is "
        "not one."
    )


MAIN_TEMPLATE = """\
# GENERATED by scripts/render-web-nginx.py — do not edit.
#
# The stock image supplies this outer shell; deploy/docker/web/nginx.conf is
# included from http{{}} in the container exactly as it is below. Everything
# here is about running as an unprivileged user outside a container: writable
# pid/temp/log paths, one worker, and the foreground.
worker_processes 1;
daemon off;
pid {run}/nginx.pid;
error_log {run}/error.log info;

events {{
    worker_connections 64;
}}

http {{
    include {mime_types};
    default_type application/octet-stream;

    access_log {run}/access.log;
    client_body_temp_path {run}/client_body;
    proxy_temp_path {run}/proxy_temp;
    fastcgi_temp_path {run}/fastcgi_temp;
    uwsgi_temp_path {run}/uwsgi_temp;
    scgi_temp_path {run}/scgi_temp;

    include {server_conf};
}}
"""


def write_run_dir(
    run_dir: Path, *, port: int, root: Path, gateway: str, source: Path = SOURCE_CONF
) -> Path:
    """Render both files into `run_dir` and hand back the MAIN config path."""
    run_dir.mkdir(parents=True, exist_ok=True)
    server_conf = run_dir / "loft-web.conf"
    server_conf.write_text(
        render(source.read_text(), port=port, root=root, gateway=gateway)
    )
    main_conf = run_dir / "nginx.conf"
    main_conf.write_text(
        MAIN_TEMPLATE.format(
            run=run_dir,
            mime_types=mime_types_path(),
            server_conf=server_conf,
        )
    )
    return main_conf


# ---------------------------------------------------------------------------
# --self-test: one negative control per guarantee.
#
# A gate nobody has watched fail is not a gate, and asserting the exit code
# alone would have passed all along here — the interesting failures are the
# ones that produce a PLAUSIBLE config. So each scenario mutates the shipped
# config in a way a real edit could, and demands a refusal naming the reason.
# ---------------------------------------------------------------------------
SELF_TESTS: tuple[tuple[str, str, str], ...] = (
    (
        "header-dropped",
        "a location loses its Content-Security-Policy",
        "drop",
    ),
    (
        "listen-reshaped",
        "the listen directive is reshaped so the rewrite misses it",
        "listen",
    ),
    (
        "listen-duplicated",
        "a second listen 8080 appears",
        "dup",
    ),
    (
        "no-headers-at-all",
        "the config has no add_header lines (the vacuity case)",
        "empty",
    ),
)


def _mutate(source: str, kind: str) -> str:
    lines = source.splitlines(keepends=True)
    if kind == "drop":
        for index, line in enumerate(lines):
            if "Content-Security-Policy" in line and "add_header" in line:
                del lines[index]
                break
        else:  # pragma: no cover - guarded by the fixture assertion below
            raise AssertionError("fixture has no CSP add_header to drop")
        return "".join(lines)
    if kind == "weaken":
        # Target the add_header/`set` LINE, not the first textual match: the
        # file discusses the policy in prose above it, and a mutation that
        # edits a COMMENT is correctly not refused — which would make this
        # control pass for the wrong reason. Found exactly that way.
        for index, line in enumerate(lines):
            if line.lstrip().startswith(
                ("set $loft_csp", "add_header Content-Security-Policy")
            ):
                lines[index] = line.replace("'wasm-unsafe-eval'", "'unsafe-eval'")
                if lines[index] == line:
                    lines[index] = line.replace("object-src 'none'", "object-src *")
                break
        else:  # pragma: no cover - guarded by the fixture assertion
            raise AssertionError("fixture has no CSP definition line to weaken")
        return "".join(lines)
    if kind == "listen":
        return source.replace("listen 8080;", "listen 8080 default_server;", 1)
    if kind == "dup":
        return source.replace("listen 8080;", "listen 8080;\n    listen 8080;", 1)
    if kind == "empty":
        return "".join(ln for ln in lines if "add_header" not in ln)
    raise AssertionError(f"unknown mutation {kind}")


def self_test() -> int:
    source = SOURCE_CONF.read_text()
    failures: list[str] = []
    checks = 0

    checks += 1
    try:
        check_policy_consistency()
    except RenderError as exc:
        failures.append(str(exc))

    # POSITIVE CONTROL first. Without it every refusal below could be produced
    # by a renderer that refuses everything, which is a gate that cannot pass.
    checks += 1
    try:
        rendered = render(
            source, port=5290, root=Path("/tmp/dist"), gateway="127.0.0.1:8000"
        )
    except RenderError as exc:
        failures.append(f"positive control: the SHIPPED config was refused:\n{exc}")
        rendered = ""
    else:
        for needle in ("listen 127.0.0.1:5290;", "root /tmp/dist;", '"127.0.0.1:8000"'):
            checks += 1
            if needle not in rendered:
                failures.append(f"positive control: rendered config lacks {needle!r}")
        checks += 1
        if not any(
            line.lstrip().startswith("add_header Content-Security-Policy")
            for line in rendered.splitlines()
        ):
            failures.append(
                "positive control: the rendered config carries no CSP — the leg "
                "would then measure zero violations against no policy, which is "
                "the vacuous pass this whole file exists to prevent"
            )

    # The fixture must actually contain what the mutations remove, or the
    # negative controls are testing a property of an empty set.
    checks += 1
    csp_lines = [
        ln
        for ln in source.splitlines()
        if ln.lstrip().startswith("add_header Content-Security-Policy")
    ]
    if len(csp_lines) < 4:
        failures.append(
            f"fixture: the shipped nginx.conf carries {len(csp_lines)} "
            "`add_header Content-Security-Policy` line(s); nginx's add_header "
            "is not additive across levels, so the server block plus each "
            "location that has any add_header of its own needs one (4 today). "
            "Fewer means either a location is serving without a policy or "
            "these negative controls have nothing to mutate."
        )

    for name, description, kind in SELF_TESTS:
        checks += 1
        try:
            mutated = _mutate(source, kind)
        except AssertionError as exc:
            failures.append(f"{name}: could not build the fixture ({exc})")
            continue
        if mutated == source:
            failures.append(f"{name}: the mutation changed nothing — {description}")
            continue
        try:
            render(mutated, port=5290, root=Path("/tmp/dist"), gateway="127.0.0.1:8000")
        except RenderError:
            print(f"  ok   {name}: refused ({description})")
        else:
            failures.append(
                f"{name}: NOT refused — {description}. The renderer would have "
                "handed the leg a config that is not the one we ship."
            )

    # THE BLIND SPOT, ASSERTED RATHER THAN LEFT IMPLICIT.
    #
    # This renderer compares the SOURCE against the RENDER, so it can catch a
    # renderer that alters a header and cannot catch a config whose header is
    # WRONG — a faithfully-reproduced mistake reproduces faithfully. That is the
    # correct division of labour (a config renderer is not the policy's judge),
    # but a blind spot nobody has written down is indistinguishable from
    # coverage. So it is pinned here: weakening the policy must NOT be refused,
    # and the two gates that DO refuse it are named.
    checks += 1
    weakened = _mutate(source, "weaken")
    if weakened == source:
        failures.append("blind-spot: the weaken mutation changed nothing")
    else:
        try:
            render(
                weakened, port=5290, root=Path("/tmp/dist"), gateway="127.0.0.1:8000"
            )
        except RenderError as exc:
            failures.append(
                "blind-spot: a weakened policy was refused by the RENDERER. That "
                "is not this tool's job and the comment beside this check is now "
                f"wrong — re-derive it:\n{exc}"
            )
        else:
            print(
                "  ok   blind-spot: a WEAKENED policy is not refused here, by "
                "design.\n"
                "       The served VALUE is judged by scripts/web-smoke.sh "
                "(real container,\n"
                "       deploy-path) and by apps/web/e2e-dist/dist-csp.spec.ts "
                "(real browser,\n"
                "       against EXPECTED_CSP in e2e-dist/distSupport.ts)."
            )

    print()
    if failures:
        print(
            f"render-web-nginx --self-test: {len(failures)} of {checks} checks FAILED"
        )
        for failure in failures:
            print(f"  FAIL {failure}")
        return 1
    print(f"render-web-nginx --self-test: {checks} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--out", type=Path, help="run directory to render into")
    parser.add_argument("--port", type=int, default=5290)
    parser.add_argument("--root", type=Path, help="the built bundle (apps/web/dist)")
    parser.add_argument("--gateway", default="127.0.0.1:8000")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="render to a throwaway directory and discard it — the cheap gate "
        "that proves the shipped config is still renderable",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.check_only:
        check_policy_consistency()
        with tempfile.TemporaryDirectory() as tmp:
            write_run_dir(
                Path(tmp),
                port=args.port,
                root=args.root or Path("/usr/share/nginx/html"),
                gateway=args.gateway,
            )
        print("render-web-nginx: deploy/docker/web/nginx.conf renders cleanly")
        return 0

    if args.out is None or args.root is None:
        parser.error("--out and --root are required (or pass --check-only/--self-test)")

    main_conf = write_run_dir(
        args.out, port=args.port, root=args.root.resolve(), gateway=args.gateway
    )
    print(main_conf)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RenderError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
