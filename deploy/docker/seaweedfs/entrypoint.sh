#!/bin/sh
# ---------------------------------------------------------------------------
# Loft's bundled S3 object store: SeaweedFS (Apache-2.0) in one container.
#
# Used by the `seaweedfs` compose service (docker-compose.yml), which mounts
# this file read-only and runs it with /bin/sh. The SAME script boots a native
# `weed` binary for local proofs (SEAWEEDFS_EXEC=weed), so the boot sequence the
# sandbox exercises is the one compose runs.
#
# What it does, in order:
#   1. writes the S3 identity file (s3.json) from S3_ACCESS_KEY_ID /
#      S3_SECRET_ACCESS_KEY: one identity, full rights, and NO anonymous access;
#   2. starts `weed server -s3` (master + volume + filer + S3 gateway, one
#      process) in the background, with the Iceberg catalog and Lance
#      namespace listeners that 4.x starts by default turned off: Loft uses
#      neither, and an unused listener is surface;
#   3. waits for the S3 gateway, then creates the bucket ${S3_BUCKET} if it
#      does not exist — HEAD first, PUT only on 404, so a restart on an
#      existing volume is a no-op. The request is SigV4-signed with the
#      configured credentials, so a credential the server rejects fails the
#      boot instead of the first mesh upload;
#   4. touches the ready marker the compose healthcheck requires, and waits on
#      the server, forwarding SIGTERM/SIGINT so `docker compose stop` is clean.
#
# Any failure exits non-zero, so the container stops and every service that
# depends on it with `condition: service_healthy` refuses to start.
#
# Environment (defaults are the container's):
#   S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY   required
#   S3_BUCKET            bucket to ensure                    (loft)
#   S3_REGION            SigV4 signing region                (us-east-1)
#   SEAWEEDFS_DATA_DIR   data directory                      (/data)
#   SEAWEEDFS_CONF_DIR   s3.json + ready marker              (/tmp/loft-s3)
#   SEAWEEDFS_S3_PORT    S3 gateway port                     (8333)
#   SEAWEEDFS_IP         address the components advertise    (127.0.0.1)
#   SEAWEEDFS_BIND       address the S3 gateway binds        (0.0.0.0)
#                        Master, volume and filer (HTTP and gRPC) always bind
#                        127.0.0.1: they have no auth, so only S3 is reachable
#                        from the compose network.
#   SEAWEEDFS_MASTER_PORT / _VOLUME_PORT / _FILER_PORT       (9333/8080/8888;
#                        each gRPC port is +10000)
#   SEAWEEDFS_EXEC       launcher: the image's /entrypoint.sh (drops root to
#                        the `seaweed` user and fixes /data ownership), else
#                        `weed` on PATH
# ---------------------------------------------------------------------------
set -eu

log() { echo "loft-s3: $*" >&2; }

: "${S3_ACCESS_KEY_ID:?loft-s3: S3_ACCESS_KEY_ID is required}"
: "${S3_SECRET_ACCESS_KEY:?loft-s3: S3_SECRET_ACCESS_KEY is required}"
bucket="${S3_BUCKET:-loft}"
region="${S3_REGION:-us-east-1}"
data_dir="${SEAWEEDFS_DATA_DIR:-/data}"
conf_dir="${SEAWEEDFS_CONF_DIR:-/tmp/loft-s3}"
s3_port="${SEAWEEDFS_S3_PORT:-8333}"
ip="${SEAWEEDFS_IP:-127.0.0.1}"
bind="${SEAWEEDFS_BIND:-0.0.0.0}"
master_port="${SEAWEEDFS_MASTER_PORT:-9333}"
volume_port="${SEAWEEDFS_VOLUME_PORT:-8080}"
filer_port="${SEAWEEDFS_FILER_PORT:-8888}"
if [ -z "${SEAWEEDFS_EXEC:-}" ]; then
  if [ -x /entrypoint.sh ]; then SEAWEEDFS_EXEC=/entrypoint.sh; else SEAWEEDFS_EXEC=weed; fi
fi

case "$S3_ACCESS_KEY_ID" in
  *:*) log "S3_ACCESS_KEY_ID must not contain ':'"; exit 2 ;;
esac

# JSON string escaping for the two values we interpolate: backslash and quote.
# Control characters in a credential are refused rather than escaped. `tr`, not
# grep: grep is line-based and never sees a newline.
json_escape() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }
for name in S3_ACCESS_KEY_ID S3_SECRET_ACCESS_KEY; do
  eval "value=\$$name"
  stripped="$(printf '%s' "$value" | tr -d '[:cntrl:]'; printf x)"
  if [ "${stripped%x}" != "$value" ]; then
    log "$name contains a newline, carriage return or other control character."
    log "  Usually a trailing newline from \$(cat file) or a CRLF .env; remove it."
    exit 2
  fi
done

mkdir -p "$conf_dir" "$data_dir"
rm -f "$conf_dir/ready"
umask 077
cat >"$conf_dir/s3.json" <<EOF
{
  "identities": [
    {
      "name": "loft",
      "credentials": [
        {
          "accessKey": "$(json_escape "$S3_ACCESS_KEY_ID")",
          "secretKey": "$(json_escape "$S3_SECRET_ACCESS_KEY")"
        }
      ],
      "actions": ["Admin", "Read", "List", "Tagging", "Write"]
    }
  ]
}
EOF
# The image's launcher drops to the unprivileged `seaweed` user, which must be
# able to read the identity file it is handed.
if [ "$(id -u)" = "0" ] && id seaweed >/dev/null 2>&1; then
  chown -R seaweed:seaweed "$conf_dir"
fi

# `-logtostderr` first: the image's launcher passes an unrecognised first
# argument straight to `weed`, after its chown + privilege drop.
"$SEAWEEDFS_EXEC" -logtostderr=true server \
  -dir="$data_dir" \
  -ip="$ip" \
  -ip.bind=127.0.0.1 \
  -master.port="$master_port" \
  -master.volumeSizeLimitMB=1024 \
  -volume.port="$volume_port" \
  -volume.max=0 \
  -filer.port="$filer_port" \
  -s3 \
  -s3.port="$s3_port" \
  -s3.ip.bind="$bind" \
  -s3.config="$conf_dir/s3.json" \
  -s3.port.iceberg=0 \
  -s3.port.lance=0 &
pid=$!

stop() {
  log "stopping (pid $pid)"
  kill -TERM "$pid" 2>/dev/null || true
}
trap stop TERM INT

s3="http://127.0.0.1:${s3_port}"
signed() {
  curl -sS -o /dev/null -w '%{http_code}' \
    --aws-sigv4 "aws:amz:${region}:s3" \
    --user "${S3_ACCESS_KEY_ID}:${S3_SECRET_ACCESS_KEY}" "$@"
}

# The S3 gateway comes up after master, volume and filer; 120 s is generous for
# a cold volume, and the loop also notices a server that died on the way.
tries=0
until curl -fsS -o /dev/null "$s3/healthz" 2>/dev/null; do
  if ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" || true
    log "weed server exited before the S3 gateway came up"
    exit 1
  fi
  tries=$((tries + 1))
  if [ "$tries" -ge 240 ]; then
    log "S3 gateway not up on $s3 after 120 s"
    kill -TERM "$pid" 2>/dev/null || true
    exit 1
  fi
  sleep 0.5
done

# Bucket: HEAD, then PUT only when absent. 200 = present, 404 = create, anything
# else (403 = the server rejected our own credentials) is fatal. The filer can
# take a moment after /healthz to accept bucket writes, so a 5xx is retried.
tries=0
while :; do
  code=$(signed -I "$s3/$bucket") || code=000
  case "$code" in
    200)
      log "bucket '$bucket' present"
      break
      ;;
    404)
      code=$(signed -X PUT "$s3/$bucket") || code=000
      case "$code" in
        200 | 409)
          log "bucket '$bucket' created"
          break
          ;;
      esac
      ;;
    403 | 401)
      log "the S3 gateway rejected the configured credentials (HTTP $code)"
      kill -TERM "$pid" 2>/dev/null || true
      exit 1
      ;;
  esac
  tries=$((tries + 1))
  if [ "$tries" -ge 60 ]; then
    log "could not ensure bucket '$bucket' (last HTTP $code)"
    kill -TERM "$pid" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

touch "$conf_dir/ready"
log "ready: $s3 bucket '$bucket'"

# `wait` returns early when a trapped signal arrives; keep waiting until the
# server has actually exited, and exit with its status.
status=0
wait "$pid" || status=$?
while kill -0 "$pid" 2>/dev/null; do
  wait "$pid" || status=$?
done
exit "$status"
