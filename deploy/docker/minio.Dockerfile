# ---------------------------------------------------------------------------
# MinIO server + mc client, built FROM SOURCE at pinned, checksummed module
# versions. Used by the `minio` and `minio-init` compose services.
#
#   docker build -f deploy/docker/minio.Dockerfile -t loft-minio .
#
# WHY WE BUILD IT. MinIO Inc. has withdrawn its prebuilt community images
# TWICE in two weeks, and each time every CI job that boots the stack went
# red on commits that had not touched it:
#   * 2026-09-12: minio/minio and minio/mc were removed from Docker Hub
#     (hub.docker.com/v2/repositories/minio/{minio,mc}/ -> "object not found");
#     we repinned to quay.io in bd58416.
#   * 2026-09-24: quay.io/minio/{minio,mc} started answering anonymous pulls
#     with "unauthorized: access to the requested resource is not authorized"
#     (cd6baed, fc5e840), ten minutes after the same pins pulled green on
#     639f21c. Upstream had already moved community publishing to its own
#     registry.min.dev in Oct 2025 (minio/minio 05e5699) and declared the
#     project source-only ("THIS REPOSITORY IS NO LONGER MAINTAINED").
# Pinning a tag cannot survive an upstream that stops publishing, and a third
# vendor registry is the same bet a third time. See docs/LESSONS.md
# #ci-minio-withdrawn.
#
# WHY THIS SOURCE IS DURABLE. The binaries are built with `go install
# <module>@<version>`, which fetches from the Go module proxy
# (proxy.golang.org), not from MinIO and not from GitHub. The proxy keeps
# every module version it has served, and each zip is recorded in the public,
# append-only checksum log (sum.golang.org), which `go` verifies on download.
# The versions below are the Go pseudo-versions of the EXACT commits the
# RELEASE tags we pinned before point at: 16f8cf1c52f0 is
# RELEASE.2024-12-18T13-15-44Z and 1681e4497c09 is mc
# RELEASE.2024-11-21T17-21-54Z (proxy .info Origin.Hash, verified 2026-09-24).
# The same source, byte for byte, as the images we used to pull. The
# `h1:` sums are pinned here too and asserted before the build, so a moved
# pseudo-version or a private GOPROXY mirror serving different bytes fails the
# build rather than shipping something else.
#
# The remaining registry dependency is the two Docker Official (`library/`)
# base images below, the same class as postgres:16 and redis:7, which the
# stack already pulls.
#
# COST: roughly 4-5 minutes of compile on a 4-core host the FIRST time (measured
# 274 s for both binaries, cold module cache, including downloads). After that
# the layer cache makes it free until this file changes.
#
# AIR-GAP: build time reaches the Go module proxy, as the service image
# reaches PyPI. An air-gapped builder points GOPROXY at its own mirror
# (`--build-arg GOPROXY=https://athens.internal`); the pinned h1 sums still
# hold it to the same bytes. The RUNNING container reaches nothing.
#
# LICENCE: MinIO and mc are AGPL-3.0-or-later. They run UNMODIFIED as a
# separate network service, exactly as the pulled images did; nothing of ours
# links them. The image carries both LICENSE files and names the exact source
# (module@version) in its labels. See docs/LICENSING.md §5.
# ---------------------------------------------------------------------------

# --- build: both binaries from the module proxy -----------------------------
# Go 1.23 meets both go.mod floors (minio `go 1.23`, mc `go 1.22`) and is
# contemporary with both releases; GOTOOLCHAIN=local forbids a silent
# toolchain download.
FROM golang:1.23.4-alpine3.21 AS build

ARG GOPROXY=https://proxy.golang.org
ENV GOPROXY=${GOPROXY} \
    GOTOOLCHAIN=local \
    CGO_ENABLED=0 \
    GOFLAGS="-trimpath -tags=kqueue"

ARG MINIO_RELEASE=RELEASE.2024-12-18T13-15-44Z
ARG MINIO_VERSION=v0.0.0-20241218131544-16f8cf1c52f0
ARG MINIO_COMMIT=16f8cf1c52f0a77eeb8f7565aaf7f7df12454583
ARG MINIO_SUM=h1:VkIkrCKtbftWOcvIN45eXM5Y+BHo6kLrH3bRf2TBrvg=
ARG MC_RELEASE=RELEASE.2024-11-21T17-21-54Z
ARG MC_VERSION=v0.0.0-20241121172154-1681e4497c09
ARG MC_COMMIT=1681e4497c09d7438a34e846f76dbde972ab7daf
ARG MC_SUM=h1:Yl/q8sHsBQwidLtZFN8UShYDiLeWvk6CXNsj9JjlOHM=

# Refuse to build anything but the pinned bytes. `go mod download -json`
# reports the h1 sum of the zip it verified; compare it to the pin.
RUN set -eu; \
    check() { \
      got=$(go mod download -json "$1@$2" | sed -n 's/.*"Sum": "\(.*\)".*/\1/p'); \
      if [ "$got" != "$3" ]; then \
        echo "minio.Dockerfile: $1@$2 has sum '$got', pinned '$3' - REFUSING" >&2; \
        exit 1; \
      fi; \
      echo "ok $1@$2 $got"; \
    }; \
    check github.com/minio/minio "$MINIO_VERSION" "$MINIO_SUM"; \
    check github.com/minio/mc "$MC_VERSION" "$MC_SUM"

# The -X flags reproduce what upstream's buildscripts/gen-ldflags.go stamps,
# so `minio --version` and the server's own version reporting name the real
# release instead of DEVELOPMENT.GOGET.
RUN set -eu; \
    ts() { echo "$1" | sed -E 's/^RELEASE\.([0-9-]+)T([0-9]+)-([0-9]+)-([0-9]+)Z$/\1T\2:\3:\4Z/'; }; \
    go install -ldflags "-s -w \
      -X github.com/minio/minio/cmd.Version=$(ts "$MINIO_RELEASE") \
      -X github.com/minio/minio/cmd.CopyrightYear=2024 \
      -X github.com/minio/minio/cmd.ReleaseTag=$MINIO_RELEASE \
      -X github.com/minio/minio/cmd.CommitID=$MINIO_COMMIT \
      -X github.com/minio/minio/cmd.ShortCommitID=$(echo "$MINIO_COMMIT" | cut -c1-12)" \
      "github.com/minio/minio@$MINIO_VERSION"; \
    go install -ldflags "-s -w \
      -X github.com/minio/mc/cmd.Version=$(ts "$MC_RELEASE") \
      -X github.com/minio/mc/cmd.CopyrightYear=2024 \
      -X github.com/minio/mc/cmd.ReleaseTag=$MC_RELEASE \
      -X github.com/minio/mc/cmd.CommitID=$MC_COMMIT \
      -X github.com/minio/mc/cmd.ShortCommitID=$(echo "$MC_COMMIT" | cut -c1-12)" \
      "github.com/minio/mc@$MC_VERSION"; \
    mkdir -p /out/licenses/minio /out/licenses/mc; \
    cp "$(go env GOMODCACHE)/github.com/minio/minio@$MINIO_VERSION/LICENSE" /out/licenses/minio/; \
    cp "$(go env GOMODCACHE)/github.com/minio/mc@$MC_VERSION/LICENSE" /out/licenses/mc/; \
    cp /go/bin/minio /go/bin/mc /out/

# --- runtime ----------------------------------------------------------------
# Alpine, not scratch: the `minio-init` one-shot runs `/bin/sh -c "mc ..."`
# and the healthcheck runs `mc ready local`. Runs as root, like the upstream
# image it replaces, so an existing `minio-data` volume (root-owned, written
# by that image) keeps working without a chown migration.
FROM alpine:3.21 AS runtime

ARG MINIO_RELEASE=RELEASE.2024-12-18T13-15-44Z
ARG MINIO_VERSION=v0.0.0-20241218131544-16f8cf1c52f0
ARG MC_RELEASE=RELEASE.2024-11-21T17-21-54Z
ARG MC_VERSION=v0.0.0-20241121172154-1681e4497c09

COPY --from=build /out/minio /out/mc /usr/bin/
COPY --from=build /out/licenses /licenses

# mc writes its config on first use; upstream's image points it at /tmp too.
ENV MC_CONFIG_DIR=/tmp/.mc

# Build-time proof the binaries run on this base, naming the release.
RUN minio --version | grep -F "$MINIO_RELEASE" \
    && mc --version | grep -F "$MC_RELEASE"

LABEL org.opencontainers.image.title="loft-minio" \
      org.opencontainers.image.description="MinIO $MINIO_RELEASE + mc $MC_RELEASE, built unmodified from source for the Loft compose stack" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.version="$MINIO_RELEASE" \
      dev.loft.minio.source="github.com/minio/minio@$MINIO_VERSION" \
      dev.loft.mc.source="github.com/minio/mc@$MC_VERSION"

EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["minio"]
CMD ["server", "/data"]
