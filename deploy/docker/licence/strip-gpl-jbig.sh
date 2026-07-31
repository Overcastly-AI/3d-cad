#!/bin/sh
# strip-gpl-jbig.sh — replace the GPL-2.0 jbigkit vendored inside the OCP wheel
# with the GPL-free stub in this directory. LIC-1; docs/LICENSING.md §4.
#
#   strip-gpl-jbig.sh <search-root> [--require]
#
# <search-root> is anything containing the installed environment (a venv, a
# site-packages tree, or a bare `*.libs` directory). `--require` makes "no
# libjbig found" a FAILURE instead of a no-op — pass it for the geometry image,
# where the library is known to be present, so a silently-skipped strip can
# never masquerade as a clean build.
#
# Deleting libjbig does not work (the vendored libraries use eager binding:
# `undefined symbol: jbg_enc_out`), so we overwrite it in place with a library
# of the same file name and SONAME that exports exactly the ten symbols libtiff
# imports. See jbig-stub.c for the full reasoning.
#
# POSIX sh on purpose: this runs inside the Docker builder stage.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
STUB_SRC="${HERE}/jbig-stub.c"
MARKER="LOFT-GPL-FREE-JBIG-STUB v1"

ROOT=${1:-}
REQUIRE=${2:-}
if [ -z "$ROOT" ]; then
	echo "usage: strip-gpl-jbig.sh <search-root> [--require]" >&2
	exit 64
fi
[ -f "$STUB_SRC" ] || {
	echo "strip-gpl-jbig: missing $STUB_SRC" >&2
	exit 64
}

# The ten symbols libtiff-*.so.5.5.0 imports from jbigkit. Kept here as well as
# in the C source so the assertion below is independent of the file it checks.
JBG_SYMBOLS="jbg_dec_free jbg_dec_getimage jbg_dec_getsize jbg_dec_in \
jbg_dec_init jbg_enc_free jbg_enc_init jbg_enc_out jbg_newlen jbg_strerror"

# Debian's `cc` alternative comes from the gcc package; fall back rather than
# fail with a bare "cc: not found" three layers into an image build.
CC=${CC:-}
if [ -z "$CC" ]; then
	if command -v cc >/dev/null 2>&1; then
		CC=cc
	elif command -v gcc >/dev/null 2>&1; then
		CC=gcc
	else
		echo "strip-gpl-jbig: no C compiler (need cc or gcc)" >&2
		exit 1
	fi
fi

found=0
for lib in $(find "$ROOT" -name 'libjbig*.so*' -type f | sort); do
	found=$((found + 1))
	base=$(basename "$lib")
	echo "strip-gpl-jbig: found $lib"

	if grep -aq "$MARKER" "$lib"; then
		echo "strip-gpl-jbig: already stubbed, nothing to do"
		continue
	fi
	if ! grep -aq 'JBIG-KIT' "$lib"; then
		echo "strip-gpl-jbig: $base is neither jbigkit nor our stub — refusing" >&2
		echo "  (classify it in scripts/check-licences.py before proceeding)" >&2
		exit 1
	fi

	# Same file name AND same SONAME, so libtiff's DT_NEEDED still resolves.
	"$CC" -shared -fPIC -O2 -Wl,-soname,"$base" -o "${lib}.stub" "$STUB_SRC"
	# Overwrite in place rather than rm+mv: keeps the original mode/ownership,
	# which the runtime stage copies verbatim.
	cat "${lib}.stub" >"$lib"
	rm -f "${lib}.stub"

	# --- assertions: the replacement is ours, is GPL-free, and links ---------
	grep -aq "$MARKER" "$lib" || {
		echo "strip-gpl-jbig: FAILED — $base does not carry the stub marker" >&2
		exit 1
	}
	if grep -aqE 'JBIG-KIT|Licence: GPL|License: GPL' "$lib"; then
		echo "strip-gpl-jbig: FAILED — GPL strings survive in $base" >&2
		exit 1
	fi
	for sym in $JBG_SYMBOLS; do
		nm -D --defined-only "$lib" | grep -q " T ${sym}\$" || {
			echo "strip-gpl-jbig: FAILED — stub does not export ${sym}" >&2
			exit 1
		}
	done
	echo "strip-gpl-jbig: replaced $base with the GPL-free stub ($(wc -c <"$lib") bytes, 10 symbols)"
done

if [ "$found" -eq 0 ]; then
	if [ "$REQUIRE" = "--require" ]; then
		echo "strip-gpl-jbig: FAILED — --require given but no libjbig found under $ROOT" >&2
		echo "  Either the OCP wheel stopped vendoring it (good: drop --require and" >&2
		echo "  the inventory entry) or this build did not install the kernel (bad)." >&2
		exit 1
	fi
	echo "strip-gpl-jbig: no libjbig under $ROOT (nothing to strip)"
fi
