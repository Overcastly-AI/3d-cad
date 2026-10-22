"""Which feature types make or change a body (split out of
:mod:`loft_wire.features`, FILE-SIZE-RATCHET; re-exported there unchanged)."""

#: Feature types that produce/mutate the body chain — the acceptable targets of
#: a :class:`SubshapeRef` face reference (topo-naming §4: a face is named on a
#: body-affecting feature's result). ``datum``/``sketch`` are NOT body-affecting.
BODY_AFFECTING_FEATURE_TYPES = frozenset(
    {
        "extrude",
        "revolve",
        "sweep",
        "pipe",
        "loft",
        "fillet",
        "chamfer",
        "shell",
        "draft",
        # `hole` drills a cylinder into the body (a body-affecting modifier like
        # fillet/shell/draft), so its result faces/edges are nameable by a later
        # SubshapeRef (a datum on the new bore face, a hole near an earlier hole).
        "hole",
        "pattern",
        # `mirror` reflects the current body about a plane and unions the
        # reflection in (a body-affecting modifier like pattern), so its result
        # faces/edges are nameable by a later SubshapeRef (a hole on a mirrored
        # boss, a sketch on the reflected face).
        "mirror",
        # `import` produces the base body (step-import.md §1), so its faces/edges
        # are nameable by a later SubshapeRef — "sketch on an imported part's face".
        "import",
        # `sheet_metal_base_flange` produces the sheet body (sheet-metal.md §4.1),
        # so its faces/edges are nameable by a later SubshapeRef — a sketch/hole on
        # a flange face (§7), or (slice #3) the edge-flange bend attaches to a base
        # edge. A base flange IS a body-affecting result like any extrude.
        "sheet_metal_base_flange",
        # `sheet_metal_edge_flange` folds a flange onto the sheet body (sheet-metal
        # §4.2), so its result faces/edges are nameable by a later SubshapeRef — a
        # hole on a formed flange face, or a second edge flange off a NEW edge the
        # first created (still a depth-1 star off the base, §4.3).
        "sheet_metal_edge_flange",
        # `sheet_metal_hem` folds a ~180 deg return onto the sheet body (parity §2,
        # closed hem) — the SAME body-affecting result as an edge flange (it reuses
        # `build_edge_flange`), so its faces/edges are nameable by a later
        # SubshapeRef (a hole on the hemmed return, a bend off a new edge).
        "sheet_metal_hem",
        # `sheet_metal_corner_relief` cuts a notch into the sheet body (sheet-metal
        # §4.4) — a body-affecting modifier like fillet/shell — so its result
        # faces/edges are nameable by a later SubshapeRef (a hole near a relieved
        # corner). It never keys a standalone body (no `merge`).
        "sheet_metal_corner_relief",
        # `boolean` produces a combined body (multi-body §Decisions-3), so its
        # result faces/edges are nameable by a later SubshapeRef (a fillet on a
        # boolean seam — MB-3, the honest stage-1-degrade-under-edit case).
        "boolean",
    }
)


#: The body-CREATING (base) feature types — the acceptable target/tool of a
#: `boolean` operand ref (multi-body §Decisions-3: a boolean combines two bodies
#: named by their BASE features). A body's identity is its base-feature id
#: (§MB-0 Decision 1), and only these features CREATE a body (extrude/revolve/
#: sweep/loft build a primitive, import brings one in). The MODIFIERS (fillet/
#: chamfer/shell/draft/pattern) mutate the active body in place and never key a
#: body, so they are NOT valid boolean operands; `boolean` itself is excluded too
#: (it takes over its target's base id, not its own — boolean-on-boolean is MB-4).
BASE_BODY_AFFECTING_FEATURE_TYPES = frozenset(
    {"extrude", "revolve", "sweep", "pipe", "loft", "import", "sheet_metal_base_flange"}
)
