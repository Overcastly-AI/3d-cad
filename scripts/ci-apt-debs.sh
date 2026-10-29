#!/usr/bin/env bash
# System packages for a CI job WITHOUT the apt mirror on the hot path.
#
#   scripts/ci-apt-debs.sh key <pkg>...             # cache-key part for these packages
#   scripts/ci-apt-debs.sh install <dir> <pkg>...   # make every <pkg> installed
#   scripts/ci-apt-debs.sh --self-test              # stubbed dpkg/apt, no root needed
#
# `install` installs what `dpkg-query` reports missing, from the first
# source that works:
#   1. the .deb files in <dir>, which the calling action restores from
#      actions/cache: `dpkg -i`, no network, no mirror;
#   2. bounded apt (3 attempts, 3 min per command), the cold-cache fallback.
#      It downloads into <dir> and keeps the files, so the action can save
#      them, and the next job on this runner image takes path 1.
# With $GITHUB_OUTPUT set it writes `seeded=true` when path 2 filled an
# empty <dir>: that is the action's cue to save the cache.
#
# Why (2026-10-23): the apt mirror, not the work, set these steps' times. In
# run 39980520437 at 27c44a5, planegcs-build-deps took 7m07s on pytest shard
# 5/6 (which then hit its 25-min timeout) and 6m08s on e2e smoke, whose
# Chromium step took 7m23s more; it was 2-6 min on several other jobs that
# day, against ~15 s normally. Retries bound a stall but still wait on the
# mirror; a .deb cache does not ask it.
#
# `key` hashes each package's candidate version as the image's own apt lists
# record it (no `apt-get update`), so a different image or package set gets a
# different cache. The action adds ImageOS/ImageVersion on top.
set -euo pipefail

# A cached .deb is installed when its package is missing OR older on this
# runner than in the cache: the seeding job's `apt-get update` may have
# pulled a newer dependency (nginx-light 7.19 needs nginx >= 7.19 while the
# image ships nginx 7.18), and skipping it leaves the set unconfigurable.
needs_deb() { # <deb>
  local p v iv
  p=$(dpkg-deb -f "$1" Package)
  [ -z "$(missing_of "$p")" ] || return 0
  v=$(dpkg-deb -f "$1" Version)
  iv=$(dpkg-query -W -f='${Version}' "$p" 2>/dev/null || true)
  [ -n "$iv" ] && dpkg --compare-versions "$iv" lt "$v"
}

missing_of() {
  local p
  for p in "$@"; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' || echo "$p"
  done
}

cmd_key() {
  local p cand lines=""
  for p in "$@"; do
    cand=$(apt-cache policy "$p" 2>/dev/null | sed -n 's/^ *Candidate: *//p')
    lines+="$p=${cand:-unknown}"$'\n'
  done
  printf '%s' "$lines" | sha256sum | cut -c1-16
}

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1" >>"$GITHUB_OUTPUT"; fi
}

cmd_install() {
  local dir=$1
  shift
  local start=$SECONDS fresh=1 d p
  local -a missing debs
  output seeded=false
  mapfile -t missing < <(missing_of "$@")
  if [ ${#missing[@]} -eq 0 ]; then
    echo "all $# packages already installed"
    return 0
  fi
  echo "missing ${#missing[@]} of $#: ${missing[*]}"
  mkdir -p "$dir"
  if compgen -G "$dir/*.deb" >/dev/null; then
    fresh=0
    debs=()
    for d in "$dir"/*.deb; do
      if needs_deb "$d"; then debs+=("$d"); fi
    done
    echo "deb cache: $(compgen -G "$dir/*.deb" | wc -l) files, ${#debs[@]} missing or newer than installed"
    if [ ${#debs[@]} -gt 0 ] && sudo DEBIAN_FRONTEND=noninteractive timeout 180 dpkg -i "${debs[@]}" >/dev/null &&
      [ -z "$(missing_of "$@")" ]; then
      echo "installed from the deb cache in $((SECONDS - start)) s (no apt)"
      return 0
    fi
    # Same image key, yet the set does not install: a dependency the seeding
    # runner already had, or a damaged file. Apt still makes the job green.
    echo "::warning::deb cache did not install cleanly after $((SECONDS - start)) s; falling back to apt"
    sudo timeout 180 dpkg --configure -a || true
  fi
  mapfile -t missing < <(missing_of "$@")
  mkdir -p "$dir/partial"
  local attempt
  for attempt in 1 2 3; do
    # A timeout can kill dpkg mid-install; finish that first or the retry
    # fails with "dpkg was interrupted". `-f` lets apt repair a set a failed
    # `dpkg -i` left unconfigured instead of refusing "Unmet dependencies".
    [ "$attempt" = 1 ] || sudo timeout 180 dpkg --configure -a || true
    if sudo timeout 180 apt-get update -qq &&
      sudo DEBIAN_FRONTEND=noninteractive timeout 180 apt-get install -f -y -qq --no-install-recommends \
        -o Dir::Cache::archives="$dir" -o APT::Keep-Downloaded-Packages=true \
        -o APT::Sandbox::User=root "${missing[@]}"; then
      sudo chown -R "$(id -u):$(id -g)" "$dir"
      rm -rf "$dir/partial" "$dir/lock"
      echo "installed with apt in $((SECONDS - start)) s (attempt $attempt)"
      if [ $fresh = 1 ] && compgen -G "$dir/*.deb" >/dev/null; then
        echo "seeded the deb cache: $(compgen -G "$dir/*.deb" | wc -l) files"
        output seeded=true
      fi
      return 0
    fi
    echo "::warning::apt: attempt $attempt stalled or failed after $((SECONDS - start)) s; retrying"
  done
  return 1
}

self_test() {
  local t fails=0
  t=$(mktemp -d)
  trap 'rm -rf "$t"' RETURN
  mkdir -p "$t/bin"
  # State: $t/installed lists installed packages; $t/log records calls.
  cat >"$t/bin/sudo" <<'EOF'
#!/usr/bin/env bash
while [[ "$1" == *=* ]]; do export "$1"; shift; done
exec "$@"
EOF
  cat >"$t/bin/dpkg-query" <<'EOF'
#!/usr/bin/env bash
grep -qx "${!#}" "$STUB/installed" || exit 1
case "$2" in
  *Version*) cat "$STUB/versions/${!#}" 2>/dev/null || echo 1.0 ;;
  *) printf 'install ok installed' ;;
esac
EOF
  cat >"$t/bin/dpkg-deb" <<'EOF'
#!/usr/bin/env bash
# dpkg-deb -f <deb> <Field>
basename "$2" | cut -d_ -f"$([ "$3" = Version ] && echo 2 || echo 1)"
EOF
  cat >"$t/bin/dpkg" <<'EOF'
#!/usr/bin/env bash
echo "dpkg $*" >>"$STUB/log"
if [ "$1" = --compare-versions ]; then # <a> lt <b>
  [ "$2" != "$4" ] && [ "$(printf '%s\n%s\n' "$2" "$4" | sort -V | head -1)" = "$2" ]
  exit
fi
[ "$1" = -i ] || exit 0
[ -e "$STUB/dpkg-fails" ] && exit 1
shift
for d in "$@"; do basename "$d" | cut -d_ -f1 >>"$STUB/installed"; done
EOF
  cat >"$t/bin/apt-get" <<'EOF'
#!/usr/bin/env bash
echo "apt-get $*" >>"$STUB/log"
[ "$1" = update ] && exit 0
[ -e "$STUB/apt-fails" ] && exit 100
dir=""; pkgs=()
while [ $# -gt 0 ]; do
  case "$1" in
    -o) [[ "$2" == Dir::Cache::archives=* ]] && dir=${2#*=}; shift 2 ;;
    -*) shift ;;
    install) shift ;;
    *) pkgs+=("$1"); shift ;;
  esac
done
for p in "${pkgs[@]}"; do echo "$p" >>"$STUB/installed"; touch "$dir/${p}_1.0_amd64.deb"; done
EOF
  chmod +x "$t/bin/"*
  run_case() { # name, expect rc, expect seeded, expect-in-log, forbid-in-log
    local name=$1 want_rc=$2 want_seeded=$3 want=$4 forbid=$5 rc=0 seeded
    : >"$t/log"
    : >"$t/out"
    PATH="$t/bin:$PATH" STUB=$t GITHUB_OUTPUT=$t/out "$0" install "$t/debs" a b c >"$t/stdout" 2>&1 || rc=$?
    seeded=$(sed -n 's/^seeded=//p' "$t/out" | tail -1)
    if [ "$rc" != "$want_rc" ] || [ "$seeded" != "$want_seeded" ] ||
      { [ -n "$want" ] && ! grep -q -- "$want" "$t/log"; } ||
      { [ -n "$forbid" ] && grep -q -- "$forbid" "$t/log"; }; then
      echo "FAIL $name: rc=$rc seeded=$seeded"
      sed 's/^/  log: /' "$t/log"
      sed 's/^/  out: /' "$t/stdout"
      fails=$((fails + 1))
    else
      echo "ok   $name"
    fi
  }
  # 1. Nothing missing: neither dpkg nor apt runs.
  printf 'a\nb\nc\n' >"$t/installed"
  run_case "all present: no dpkg, no apt" 0 false "" "-i"
  # 2. Cold cache: apt installs only what is missing, into the cache dir.
  printf 'a\n' >"$t/installed"
  run_case "cold cache: apt seeds the dir" 0 true "Dir::Cache::archives=$t/debs" "dpkg -i"
  [ -e "$t/debs/b_1.0_amd64.deb" ] && [ ! -e "$t/debs/a_1.0_amd64.deb" ] ||
    { echo "FAIL cold cache: seeded files wrong: $(ls "$t/debs")"; fails=$((fails + 1)); }
  # 3. Warm cache: dpkg -i the debs, apt never asked (the point of this file).
  printf 'a\n' >"$t/installed"
  run_case "warm cache: dpkg -i, no apt" 0 false "dpkg -i" "apt-get"
  # 4. Warm cache that will not install: falls back to apt, does not re-seed.
  printf 'a\n' >"$t/installed"
  touch "$t/dpkg-fails"
  run_case "broken cache: apt fallback, no re-seed" 0 false "apt-get install" ""
  rm "$t/dpkg-fails"
  # 6. A cached dependency newer than the image's (nginx 7.19 vs 7.18) is
  #    installed with the missing packages, not skipped (run 40800450240).
  rm -rf "$t/debs"
  mkdir -p "$t/debs" "$t/versions"
  printf 'a\n' >"$t/installed"
  echo 1.0 >"$t/versions/a"
  touch "$t/debs/a_2.0_amd64.deb" "$t/debs/b_1.0_amd64.deb" "$t/debs/c_1.0_amd64.deb"
  run_case "newer cached dependency is installed too" 0 false "a_2.0_amd64.deb" "apt-get"
  # 7. ...and one the image has at the same version is not.
  printf 'a\n' >"$t/installed"
  echo 2.0 >"$t/versions/a"
  run_case "same-version dependency is skipped" 0 false "dpkg -i" "a_2.0_amd64.deb"
  rm -rf "$t/versions"
  # 5. Cache gone and apt down: red, after three attempts (bounded, not hung).
  rm -rf "$t/debs"
  printf 'a\n' >"$t/installed"
  touch "$t/apt-fails"
  run_case "apt down: fails after retries" 1 false "configure -a" ""
  [ "$(grep -c 'apt-get install' "$t/log")" = 3 ] ||
    { echo "FAIL apt down: expected 3 install attempts"; fails=$((fails + 1)); }
  rm "$t/apt-fails"
  if [ $fails -ne 0 ]; then
    echo "ci-apt-debs self-test: $fails failure(s)"
    return 1
  fi
  echo "ci-apt-debs self-test: all cases behaved"
}

case "${1:-}" in
  key) shift; cmd_key "$@" ;;
  install) shift; cmd_install "$@" ;;
  --self-test) self_test ;;
  *)
    echo "usage: $0 key <pkg>... | install <dir> <pkg>... | --self-test" >&2
    exit 2
    ;;
esac
