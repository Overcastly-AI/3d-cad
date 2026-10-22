#!/usr/bin/env bash
# seaweedfs-native.sh — a native SeaweedFS for sandboxes without Docker.
#
#   scripts/seaweedfs-native.sh build          # print the path of a pinned `weed`
#   scripts/seaweedfs-native.sh start <dir>    # boot it on <dir>, foreground
#
# `start` runs deploy/docker/seaweedfs/entrypoint.sh, the same boot sequence
# (identity file, bucket creation, ready marker) the compose service runs, with
# every listener on 127.0.0.1. Ports come from SEAWEEDFS_S3_PORT (8333),
# SEAWEEDFS_MASTER_PORT (9333), SEAWEEDFS_VOLUME_PORT (8080) and
# SEAWEEDFS_FILER_PORT (8888); each gRPC port is +10000, so pick private ones
# when other stacks share the machine. S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY /
# S3_BUCKET as for compose. Ready when <dir>/conf/ready exists. Then e.g.:
#
#   LOFT_S3_SMOKE=1 S3_URL=http://127.0.0.1:$SEAWEEDFS_S3_PORT S3_BUCKET=loft \
#     S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... \
#     uv run pytest services/geometry/tests/test_s3_store.py
#
# WHY IT BUILDS. GitHub release assets and the Docker registry's blobs are
# blocked here (docs/ENVIRONMENT.md), but the Go module proxy is not. The
# module zip is checked against the pinned h1 sum (and by `go` against
# sum.golang.org) before anything compiles. ~8 min cold, then cached.
#
# The pin is the commit SeaweedFS tagged 4.48, the version of the image in
# docker-compose.yml (scripts/check-compose.py asserts the two agree). Its
# go.mod has a `replace`, so `go install mod@version` refuses it; the build
# runs inside the downloaded module instead. Needs Go; the go.mod asks for
# 1.26.6, which `go` fetches through the same proxy (GOTOOLCHAIN).

set -euo pipefail

SEAWEEDFS_VERSION=4.48
MODULE=github.com/seaweedfs/seaweedfs
MODULE_VERSION=v0.0.0-20260928155340-530be3e37337
MODULE_SUM="h1:bxdS//0RTj8mWGFgfW2bbShKM9XDRwas85/+BHQ0tS4="
GO_TOOLCHAIN=go1.26.6

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/loft/seaweedfs-${SEAWEEDFS_VERSION}"
WEED="$CACHE/weed"

build() {
  if [[ -x "$WEED" ]]; then
    echo "$WEED"
    return
  fi
  command -v go >/dev/null || {
    echo "seaweedfs-native: Go is required to build weed" >&2
    exit 2
  }
  mkdir -p "$CACHE"
  local scratch json got dir
  scratch="$(mktemp -d)"
  export GOTOOLCHAIN="$GO_TOOLCHAIN" CGO_ENABLED=0 GOFLAGS=-trimpath
  json="$(cd "$scratch" && go mod download -json "$MODULE@$MODULE_VERSION")"
  got="$(sed -n 's/.*"Sum": "\(.*\)".*/\1/p' <<<"$json")"
  if [[ "$got" != "$MODULE_SUM" ]]; then
    echo "seaweedfs-native: $MODULE@$MODULE_VERSION has sum '$got', pinned '$MODULE_SUM' - REFUSING" >&2
    exit 1
  fi
  dir="$(sed -n 's/.*"Dir": "\(.*\)".*/\1/p' <<<"$json")"
  echo "seaweedfs-native: building weed $SEAWEEDFS_VERSION (several minutes, once)" >&2
  (cd "$dir" && go build -mod=mod -ldflags "-s -w" -o "$WEED.tmp" ./weed)
  mv "$WEED.tmp" "$WEED"
  rmdir "$scratch" 2>/dev/null || true
  "$WEED" version >&2
  echo "$WEED"
}

case "${1:-}" in
  build)
    build
    ;;
  start)
    [[ -n "${2:-}" ]] || {
      echo "usage: $0 start <dir>" >&2
      exit 2
    }
    weed="$(build)"
    mkdir -p "$2/data" "$2/conf"
    SEAWEEDFS_EXEC="$weed" \
      SEAWEEDFS_DATA_DIR="$2/data" \
      SEAWEEDFS_CONF_DIR="$2/conf" \
      SEAWEEDFS_BIND="${SEAWEEDFS_BIND:-127.0.0.1}" \
      exec sh "$REPO_ROOT/deploy/docker/seaweedfs/entrypoint.sh"
    ;;
  *)
    echo "usage: $0 build | start <dir>" >&2
    exit 2
    ;;
esac
