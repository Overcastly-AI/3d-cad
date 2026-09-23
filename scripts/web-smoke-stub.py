#!/usr/bin/env python3
"""Stub servers that let `scripts/web-smoke.sh --self-test` watch itself fail.

WHY THIS EXISTS. `web-smoke.sh` guards the compose stack's web service, and the
only place the real thing can run is CI's `deploy-path` workflow — the Docker
registry is policy-denied in the dev container, so no local command can boot
that stack. An assertion in it that can never fire would therefore be invisible
until a self-hoster hit the defect it was supposed to catch, and a bash typo in
it costs a twenty-minute round trip to discover.

So this reproduces the SERVING RULES (nginx's `try_files` for the SPA, `=404`
under /assets/, a reverse proxy at /api, the gateway's missing explorer) in
about a hundred lines of stdlib, runs the checker against a healthy stub — and
then against one stub per defect, demanding a failure each time. Each defect is
one somebody could plausibly ship:

  greedy-fallback   /assets/* falls through to index.html, so a missing bundle
                    answers 200 with HTML (the zero-byte-200 shape)
  html-bundle       the NAMED bundle answers 200 with HTML — a separate case
                    because greedy-fallback trips the missing-asset check
                    first and so can never exercise this one
  tiny-bundle       the bundle is 200 and real JS and 13 bytes
  no-asset-ref      a valid-looking entry document naming no bundle at all,
                    which is what an image with no dist/ directory serves
  no-fallback       a client-side route 404s, so /parts/<id> breaks on reload
  no-proxy          /api is not proxied, so the SPA loads and has no data
  broken-proxy      /api answers 502 — the upstream name never resolved
  stock-index       the server root is a directory listing, not the app
  explorer-live     /docs serves the CDN-loading FastAPI explorer again
  dead-gateway      everything 404s — the control that stops "no explorer"
                    from passing on a broken stack

Serve one scenario by hand:

    python3 scripts/web-smoke-stub.py --scenario healthy --serve
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INDEX = (
    b'<!doctype html>\n<html lang="en"><head><title>Loft</title>'
    b'<script type="module" crossorigin src="/assets/index-DEADBEEF.js"></script>'
    b'</head><body><div id="root"></div></body></html>\n'
)
#: Must exceed web-smoke.sh's 100 000-byte floor, and must not start with "<".
BUNDLE = b"const app=1;//" + b"x" * 200_000
OPENAPI = json.dumps({"openapi": "3.1.0", "paths": {}}).encode()
ERROR_ENVELOPE = json.dumps(
    {"error": {"code": "not_authenticated", "message": "Not authenticated"}}
).encode()


class Gateway(BaseHTTPRequestHandler):
    scenario = "healthy"

    def log_message(self, format: str, *args: object) -> None:
        """Silence the per-request access log — the checker's output is the
        signal here, and 99 request lines would bury it.

        The shadowing `format` parameter name is the base class's, and pyright
        enforces the match: it is keyword-capable there, so `*args`-only would
        be an incompatible override.
        """

    def do_GET(self) -> None:
        if self.scenario == "dead-gateway":
            return self.send(404, b"not found", "text/plain")
        if self.path == "/openapi.json":
            return self.send(200, OPENAPI, "application/json")
        if self.path in ("/docs", "/redoc"):
            if self.scenario == "explorer-live":
                return self.send(200, b"<html>swagger-ui</html>", "text/html")
            return self.send(404, b"not found", "text/plain")
        if self.path.startswith("/api/"):
            return self.send(401, ERROR_ENVELOPE, "application/json")
        self.send(404, b"not found", "text/plain")

    def send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


#: What nginx's server block adds, and what every location that re-adds ANY
#: header must therefore re-add in full. Modelled here because the discard rule
#: is a RUNTIME property of nginx that no static read of the config can see.
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
)

# The Content-Security-Policy, as deploy/docker/web/nginx.conf serves it. Held
# separately from SECURITY_HEADERS because it is the one header with a long
# exact VALUE, so it gets its own scenarios: a location can drop it (the
# add_header discard rule) or serve a WEAKENED one, and those are different
# defects with different fixes. `scripts/render-web-nginx.py --check-only`
# refuses unless this string is byte-identical to the three other copies.
# ONE literal, not a wrapped one: the consistency gate matches a complete
# double-quoted policy string, and a string split across lines is not one.
# The line-length suppression is there for that reason and not for tidiness.
CSP = "default-src 'self' data: blob:; script-src 'self' 'wasm-unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"  # noqa: E501

# A policy that looks right and is not: script-src gains 'unsafe-inline', which
# is the single change that makes a CSP stop being a defence. A value check
# that only asserted "a policy is present" would pass this happily, and that is
# precisely the check people write.
WEAK_CSP = CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")


class Web(Gateway):
    gateway_port = 0

    def send(self, status: int, body: bytes, content_type: str) -> None:
        """Every response the web edge emits carries the server-level headers.

        The `drop-*` scenarios reproduce the real defect: a `location` that
        re-adds only `nosniff` and so discards the inherited `X-Frame-Options`
        and `Referrer-Policy`. That is what `/assets/` and `/api/` did, and it
        is invisible to `nginx -t` and to any config parse — only a response
        can show it, which is why this stub is the only place a contributor can
        watch the assertion fail.
        """
        dropped = (
            self.scenario == "drop-asset-headers" and self.path.startswith("/assets/")
        ) or (self.scenario == "drop-api-headers" and self.path.startswith("/api/"))
        # The CSP has its OWN drop scenarios, one per location, for the same
        # reason the header drops do: a single combined scenario stops at
        # whichever assertion fires first and proves only that one of them
        # works. `no-csp` is the server-level case — the whole policy missing,
        # which is what this file looked like before the browser leg existed.
        csp_dropped = (
            self.scenario == "no-csp"
            or (self.scenario == "drop-asset-csp" and self.path.startswith("/assets/"))
            or (self.scenario == "drop-api-csp" and self.path.startswith("/api/"))
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if not csp_dropped:
            self.send_header(
                "Content-Security-Policy",
                WEAK_CSP if self.scenario == "weak-csp" else CSP,
            )
        for name, value in SECURITY_HEADERS:
            if dropped and name != "X-Content-Type-Options":
                continue
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            if self.scenario == "no-proxy":
                return self.send(404, b"not found", "text/plain")
            if self.scenario == "broken-proxy":
                return self.send(502, b"bad gateway", "text/html")
            # A transparent proxy: forward and mirror the answer verbatim.
            import urllib.error
            import urllib.request

            url = f"http://127.0.0.1:{self.gateway_port}{self.path}"
            try:
                with urllib.request.urlopen(url) as response:
                    body = response.read()
                    return self.send(response.status, body, "application/json")
            except urllib.error.HTTPError as exc:
                return self.send(exc.code, exc.read(), "application/json")

        if self.path == "/assets/index-DEADBEEF.js":
            # The named bundle itself. `html-bundle` and `tiny-bundle` are the
            # two ways it can answer 200 and still not be the app — they are
            # separate scenarios because `greedy-fallback` trips the
            # missing-asset check FIRST, so it can never exercise these.
            if self.scenario == "html-bundle":
                return self.send(200, INDEX, "text/html")
            if self.scenario == "tiny-bundle":
                return self.send(200, b"const app=1;\n", "application/javascript")
            return self.send(200, BUNDLE, "application/javascript")
        if self.path.startswith("/assets/"):
            # nginx `try_files $uri =404` vs. a config that lets /assets/ fall
            # through to the SPA — the whole point of that rule.
            if self.scenario == "greedy-fallback":
                return self.send(200, INDEX, "text/html")
            return self.send(404, b"not found", "text/plain")
        if self.path == "/":
            if self.scenario == "stock-index":
                return self.send(200, b"<html><h1>Index of /</h1></html>", "text/html")
            if self.scenario == "no-asset-ref":
                # A correct-looking entry document that references no bundle —
                # what a build emits when the output directory was never
                # copied into the image.
                stripped = INDEX.replace(b"/assets/index-DEADBEEF.js", b"")
                return self.send(200, stripped, "text/html")
            return self.send(200, INDEX, "text/html")
        # Any other path is a client-side route.
        if self.scenario == "no-fallback":
            return self.send(404, b"not found", "text/plain")
        self.send(200, INDEX, "text/html")


SCENARIOS = {
    "healthy": True,
    "greedy-fallback": False,
    "html-bundle": False,
    "tiny-bundle": False,
    "no-asset-ref": False,
    "no-fallback": False,
    "no-proxy": False,
    "broken-proxy": False,
    "stock-index": False,
    "explorer-live": False,
    "dead-gateway": False,
    # The nginx add_header discard rule, one scenario per location that had it
    # wrong. Separate because each is reached by a different assertion, and a
    # single combined scenario would stop at whichever fires first — proving
    # only that ONE of the two checks works.
    "drop-asset-headers": False,
    "drop-api-headers": False,
    # The CSP: absent at the server, absent in one location, or present and
    # weakened. The last one is the reason the check compares the whole string
    # rather than asserting the header exists.
    "no-csp": False,
    "drop-asset-csp": False,
    "drop-api-csp": False,
    "weak-csp": False,
}


def serve(scenario: str) -> tuple[ThreadingHTTPServer, ThreadingHTTPServer]:
    gateway_type = type("G", (Gateway,), {"scenario": scenario})
    gateway = ThreadingHTTPServer(("127.0.0.1", 0), gateway_type)
    web_type = type(
        "W", (Web,), {"scenario": scenario, "gateway_port": gateway.server_port}
    )
    web = ThreadingHTTPServer(("127.0.0.1", 0), web_type)
    for server in (gateway, web):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return web, gateway


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checker", help="path to web-smoke.sh")
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()

    if args.serve:
        web, gateway = serve(args.scenario or "healthy")
        print(f"WEB_PORT={web.server_port} GATEWAY_PORT={gateway.server_port}")
        threading.Event().wait()
        return 0

    if not args.checker:
        parser.error("--checker is required unless --serve")

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = {args.scenario: SCENARIOS[args.scenario]}
    failures: list[str] = []
    for scenario, should_pass in scenarios.items():
        web, gateway = serve(scenario)
        completed = subprocess.run(
            ["bash", args.checker],
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "WEB_PORT": str(web.server_port),
                "GATEWAY_PORT": str(gateway.server_port),
            },
            capture_output=True,
            text=True,
        )
        for server in (web, gateway):
            server.shutdown()
        passed = completed.returncode == 0
        verdict = "ok  " if passed == should_pass else "FAIL"
        detail = "" if passed else (completed.stderr.strip().splitlines() or [""])[-1]
        print(
            f"  {verdict} {scenario:<16} exit={completed.returncode} "
            f"(expected {'pass' if should_pass else 'a failure'})"
        )
        if detail and not should_pass:
            print(f"         -> {detail[:150]}")
        if passed != should_pass:
            failures.append(scenario)
            if should_pass:
                print(completed.stdout, completed.stderr, file=sys.stderr)

    if failures:
        print(f"\nweb-smoke self-test FAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(
        f"\nweb-smoke: self-test passed ({len(scenarios) - 1} defects reproduced, "
        "1 positive control) — every assertion has been seen to fail."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
