#!/usr/bin/env bash
# web-smoke.sh — what a BROWSER sees on the two published ports.
#
#   scripts/web-smoke.sh                 # web :8080, gateway :8000
#   WEB_PORT=8180 GATEWAY_PORT=8100 scripts/web-smoke.sh
#
# Called by scripts/compose-smoke.sh as its last two steps, and runnable on its
# own against any live stack — including a `just dev` one, where the web service
# is Vite rather than nginx and every assertion below still has to hold.
#
# WHY IT IS A SEPARATE FILE. Its parent needs a Docker daemon, and the Docker
# registry is policy-denied in the dev container, so compose-smoke.sh can only
# ever be exercised on a CI runner — the slowest signal we have. These
# assertions are just HTTP and bash, and bash is where the typos live. Split
# out, they can be rehearsed in seconds against a stub server that reproduces
# the serving rules (`--self-test`), so a mistake in THEM does not cost a
# twenty-minute round trip on the one workflow that can run the real thing.
#
# WHAT IT REFUSES, and why each one is not implied by a status code:
#   * the root is the SPA entry document        (a directory listing is 200 too)
#   * the hashed bundle it NAMES is real JS     (the SPA fallback returns
#                                                index.html with a 200 for a
#                                                missing asset — same shape as
#                                                the zero-byte-200 trap)
#   * a missing asset 404s                      (or the check above is
#                                                unfalsifiable)
#   * a client-side route falls back            (reload/bookmark must survive)
#   * /api is TRANSPARENT to the gateway        (the app's client is baseUrl
#                                                "/" — same-origin relative)
#   * /docs and /redoc are gone                 (their HTML loads swagger-ui
#                                                from cdn.jsdelivr.net, on the
#                                                one port a self-hoster
#                                                publishes — AIRGAP-1)
#   * /openapi.json is 200                      (POSITIVE CONTROL: a gateway
#                                                that 404s everything would
#                                                satisfy the line above)

set -euo pipefail

WEB_PORT="${WEB_PORT:-8080}"
GATEWAY_PORT="${GATEWAY_PORT:-8000}"
HOST="${SMOKE_HOST:-127.0.0.1}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fetch() { curl -sS -o "$2" -w '%{http_code}' "$1"; }

fail() {
  echo "web-smoke: $*" >&2
  exit 1
}

run_checks() {
  local web="http://${HOST}:${WEB_PORT}"
  local gw="http://${HOST}:${GATEWAY_PORT}"
  local code asset bytes direct proxied path

  code=$(fetch "$web/" "$tmp/index.html")
  [[ "$code" == "200" ]] || fail "the web root answered $code, not 200"
  grep -q '<div id="root"' "$tmp/index.html" ||
    fail "the web root is not the SPA entry document (no #root mount point) — a directory listing or a stock server page answers 200 too"
  grep -q "<title>Loft</title>" "$tmp/index.html" ||
    fail "the entry document is not Loft's"
  echo "  ok  / -> 200, $(wc -c <"$tmp/index.html") bytes, carries #root"

  # The bundle is named BY THE DOCUMENT rather than guessed: a build whose
  # asset never reached the image would still serve a perfectly good
  # index.html, and this reference is the only thing tying the two together.
  # `|| true` is load-bearing, and the self-test is what found that out. This
  # script runs under `set -o pipefail`, so a grep that matches NOTHING fails
  # the whole pipeline, which fails the assignment, which makes `set -e` abort
  # THE SCRIPT — silently, before the diagnostic below can say why. The
  # `no-asset-ref` scenario exited 1 with an empty stderr until this was added:
  # a real defect would have ended the CI log mid-sentence, which is the worst
  # possible shape for the one signal we get from that workflow.
  asset=$(grep -o '/assets/[A-Za-z0-9._-]*\.js' "$tmp/index.html" | head -1 || true)
  [[ -n "$asset" ]] ||
    fail "the entry document references no /assets/*.js bundle — the build output never reached the image"
  code=$(fetch "$web$asset" "$tmp/bundle.js")
  [[ "$code" == "200" ]] || fail "the bundle $asset answered $code"
  if head -c1 "$tmp/bundle.js" | grep -q '<'; then
    fail "$asset served HTML — the SPA fallback is masking a missing asset"
  fi
  bytes=$(wc -c <"$tmp/bundle.js")
  ((bytes > 100000)) || fail "$asset is only $bytes bytes — that is not the app bundle"
  echo "  ok  $asset -> 200, $bytes bytes, not HTML"

  code=$(fetch "$web/assets/this-file-does-not-exist.js" "$tmp/missing")
  [[ "$code" == "404" ]] ||
    fail "a missing asset answered $code, not 404 — the SPA fallback is too greedy, which makes the not-HTML check above unfalsifiable"
  echo "  ok  a missing asset -> 404 (the fallback does not swallow /assets/)"

  code=$(fetch "$web/parts/reload-me" "$tmp/route.html")
  [[ "$code" == "200" ]] || fail "a client-side route answered $code, not 200 (no SPA fallback)"
  grep -q '<div id="root"' "$tmp/route.html" ||
    fail "a client-side route did not fall back to the SPA — a reload or a bookmark of /parts/<id> would 404"
  echo "  ok  /parts/reload-me -> 200 SPA fallback (reload/bookmark survives)"

  # Compared against the SAME request on the gateway's own port rather than
  # against a hardcoded status: that proves the proxy is transparent without
  # this script having to know what the gateway says about an unauthenticated
  # read, so it cannot go stale when that answer changes.
  direct=$(fetch "$gw/api/v1/parts" "$tmp/direct.json")
  proxied=$(fetch "$web/api/v1/parts" "$tmp/proxied.json")
  [[ "$proxied" == "$direct" ]] ||
    fail "/api/v1/parts is $proxied through the web service but $direct on the gateway — the proxy is not transparent (404 = never forwarded; 502 = could not reach the gateway)"
  grep -q '"error"' "$tmp/proxied.json" ||
    fail "the proxied response carries no error envelope — it did not come from the gateway"
  echo "  ok  /api/v1/parts -> $proxied through web, identical to the gateway direct"

  for path in /docs /redoc; do
    code=$(fetch "$gw$path" "$tmp/explorer")
    [[ "$code" == "404" ]] ||
      fail "$path answered $code, not 404 — the FastAPI explorer is live on the published port and its HTML loads JavaScript from cdn.jsdelivr.net"
    echo "  ok  $path -> 404"
  done
  code=$(fetch "$gw/openapi.json" "$tmp/openapi.json")
  [[ "$code" == "200" ]] ||
    fail "/openapi.json answered $code — without it the two 404s above prove nothing, since a gateway that 404s everything would pass them"
  grep -q '"openapi"' "$tmp/openapi.json" || fail "/openapi.json is not an OpenAPI document"
  echo "  ok  /openapi.json -> 200 (generated in-process; the 404s above are real)"
}

# ---------------------------------------------------------------------------
# --self-test: a stub server that reproduces the serving rules, plus one that
# breaks each rule, so every assertion above is watched failing at least once.
#
# A gate nobody has seen fail is not a gate. Here that is not a slogan: these
# assertions guard a compose service whose only real exercise is a CI workflow
# neither a contributor nor this container can run, so "it passed on the runner"
# is the ONLY other evidence available, and it takes twenty minutes to get.
# ---------------------------------------------------------------------------
self_test() {
  python3 "$(dirname "$0")/web-smoke-stub.py" --checker "$0"
}

if [[ "${1:-}" == "--self-test" ]]; then
  self_test
  exit $?
fi

run_checks
echo
echo "web-smoke: the stack ends at the app."
