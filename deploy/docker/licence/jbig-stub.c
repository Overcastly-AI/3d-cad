/*
 * jbig-stub.c — a GPL-free replacement for jbigkit's libjbig.
 *
 * WHY THIS FILE EXISTS (docs/LICENSING.md §4)
 * -------------------------------------------
 * The `cadquery-ocp-novtk` wheel declares `License: Apache-2.0` and vendors
 * jbigkit (`libjbig`, GPL-2.0-or-later) as a build-machine artifact of
 * auditwheel. It is hard-linked, not incidental:
 *
 *     OCP.cpython-312-*.so -> libTKService -> libfreeimage -> libtiff -> libjbig
 *
 * every hop a DT_NEEDED, so the GPL library is mapped into any process that
 * imports the kernel. Redistributing that inside our image would violate this
 * project's absolute "no GPL/AGPL dependencies" rule and would make the
 * published geometry image effectively GPL-2.0 — over a TIFF codec we never
 * call. Loft does no TIFF I/O at all.
 *
 * Deleting the library is not an option: the vendored libraries are built with
 * eager binding, so a missing libjbig fails at import with
 *
 *     ImportError: libtiff-*.so.5.5.0: undefined symbol: jbg_enc_out
 *
 * `libtiff` imports exactly ten `jbg_*` symbols. This file defines those ten
 * and nothing else. None is reachable in Loft: they are only ever called from
 * libtiff's JBIG codec, which only runs when a JBIG-compressed TIFF is opened,
 * which nothing in this project does. If one is somehow called we abort loudly
 * with the symbol name rather than return a plausible-looking lie.
 *
 * This file is original work by the Loft project, MIT-licensed like the rest of
 * the repository. It contains no jbigkit code, no jbigkit headers, and no
 * knowledge of the JBIG algorithm — only the ten names libtiff's linker demands.
 *
 * Alternatives, for whoever revisits this: rebuilding libtiff with
 * --disable-jbig, or building OCCT with -DUSE_FREEIMAGE=OFF (which removes the
 * whole libfreeimage -> libtiff -> libjbig subtree), are both cleaner and both
 * cost us a maintained upstream build. docs/LICENSING.md §4 records the
 * trade-off and recommends asking the OCP maintainers to drop the codec.
 */

#include <stdlib.h>
#include <stdio.h>

/*
 * Build-time assertions grep for this string to prove the shipped .so is OUR
 * stub and not the GPL original. Do not change it without changing
 * deploy/docker/licence/strip-gpl-jbig.sh and scripts/check-licences.py.
 */
const char loft_jbig_stub_marker[] =
    "LOFT-GPL-FREE-JBIG-STUB v1 (MIT) - jbigkit removed, see docs/LICENSING.md";

static void loft_jbig_unreachable(const char *symbol) {
  fprintf(stderr,
          "loft: %s was called, but JBIG support was removed from this image "
          "for licensing reasons (docs/LICENSING.md #4). Loft performs no TIFF "
          "I/O; reaching this point means something changed. Aborting rather "
          "than returning a fabricated result.\n",
          symbol);
  fflush(stderr);
  abort();
}

#define LOFT_JBIG_STUB(name)                                                   \
  void name(void);                                                             \
  void name(void) { loft_jbig_unreachable(#name); }

/* The exact ten symbols libtiff-*.so.5.5.0 imports:
 *   nm -D --undefined-only libtiff-*.so.5.5.0 | grep jbg   */
LOFT_JBIG_STUB(jbg_dec_free)
LOFT_JBIG_STUB(jbg_dec_getimage)
LOFT_JBIG_STUB(jbg_dec_getsize)
LOFT_JBIG_STUB(jbg_dec_in)
LOFT_JBIG_STUB(jbg_dec_init)
LOFT_JBIG_STUB(jbg_enc_free)
LOFT_JBIG_STUB(jbg_enc_init)
LOFT_JBIG_STUB(jbg_enc_out)
LOFT_JBIG_STUB(jbg_newlen)
LOFT_JBIG_STUB(jbg_strerror)
