#!/usr/bin/env bash
# smoke-healthz.sh — probe /healthz + /readyz on gateway/documents/geometry.
#
# Usage:   scripts/smoke-healthz.sh [BASE_PORT]
#          BASE_PORT defaults to 8000; services are probed at BASE_PORT,
#          BASE_PORT+1, BASE_PORT+2 (gateway, documents, geometry).
# Env:     SMOKE_HOST     host to probe (default 127.0.0.1)
#          SMOKE_RETRIES  attempts per probe, 1s apart (default 5 — covers
#                         services still booting under compose)
#          SMOKE_SERVICES space-separated subset to probe, e.g. "gateway".
#                         The BASE compose stack publishes ONLY the gateway
#                         (audit G3: documents/geometry are internal), so a
#                         probe of the real self-host stack is
#                         SMOKE_SERVICES=gateway. Ports still come from each
#                         service's canonical offset, not the list order.
#
# Works against both the compose stack (host-mapped ports) and bare uvicorn
# processes. Prints a table; exits non-zero if any probe fails.

set -euo pipefail

BASE_PORT="${1:-8000}"
HOST="${SMOKE_HOST:-127.0.0.1}"
RETRIES="${SMOKE_RETRIES:-5}"
CANONICAL=(gateway documents geometry) # index == port offset from BASE_PORT

if [[ -n "${SMOKE_SERVICES:-}" ]]; then
  read -r -a SERVICES <<<"$SMOKE_SERVICES"
else
  SERVICES=("${CANONICAL[@]}")
fi

# offset_of NAME -> canonical port offset; exits non-zero on an unknown name.
offset_of() {
  local name="$1" i
  for i in "${!CANONICAL[@]}"; do
    [[ "${CANONICAL[$i]}" == "$name" ]] && {
      echo "$i"
      return 0
    }
  done
  echo "smoke: unknown service '${name}' (expected one of: ${CANONICAL[*]})" >&2
  return 1
}

# probe URL -> echoes final HTTP code ("000" = no connection), never fails.
probe() {
  local url="$1" code="000" attempt
  for ((attempt = 1; attempt <= RETRIES; attempt++)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || true)"
    [[ "$code" == "200" ]] && break
    ((attempt < RETRIES)) && sleep 1
  done
  echo "${code:-000}"
}

fail=0
printf '%-10s %-6s %-14s %-14s %s\n' SERVICE PORT HEALTHZ READYZ RESULT
printf '%-10s %-6s %-14s %-14s %s\n' ------- ---- ------- ------ ------

for svc in "${SERVICES[@]}"; do
  # Separate assignment on purpose: `set -e` aborts here on an unknown name,
  # rather than feeding an empty string into the arithmetic below.
  offset="$(offset_of "$svc")"
  port=$((BASE_PORT + offset))
  hz="$(probe "http://${HOST}:${port}/healthz")"
  rz="$(probe "http://${HOST}:${port}/readyz")"
  if [[ "$hz" == "200" && "$rz" == "200" ]]; then
    result=ok
  else
    result=FAIL
    fail=1
  fi
  printf '%-10s %-6s %-14s %-14s %s\n' "$svc" "$port" "$hz" "$rz" "$result"
done

if ((fail)); then
  echo
  echo "smoke: FAILED — at least one probe did not return 200 (000 = no connection)" >&2
fi
exit "$fail"
