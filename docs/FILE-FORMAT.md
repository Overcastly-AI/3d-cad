# The `.loft` file format

A `.loft` file is one Loft part as a file you own: the whole parametric feature
tree, which any Loft can import back into an editable part, plus a cached STEP
body that any CAD tool can open, and the part's named versions. Format version
**1.2** (1.0: parts; 1.1: named versions; 1.2: parameters and formulas; see
Versioning). Assemblies come later.

Code: `packages/loft-wire/src/loft_wire/loft_file.py` (the format),
`packages/loft-wire/src/loft_wire/versions.py` (the version API types),
`services/documents/src/documents/loft_file.py` (tree read and import),
`services/documents/src/documents/versions.py` (versions: save, list, restore),
`services/gateway/src/gateway/loft_file.py` (the two file routes),
`services/gateway/src/gateway/versions.py` (the version routes),
`packages/loft-wire/src/loft_wire/loft_formulas.py` (sketch formulas in a tree).

## Routes and clients

| Where       | Export                                    | Import                                      |
| ----------- | ----------------------------------------- | ------------------------------------------- |
| Gateway     | `GET /api/v1/parts/{id}/export.loft`      | `POST /api/v1/parts/import` (raw body)      |
| Web         | Export strip, `Save .loft` link           | Parts register top bar, `Open .loft`        |
| loft-script | `part.save("bracket.loft")`               | `session.open("bracket.loft")`              |
| Offline     |                                           | `loft.open("bracket.loft")` (read only)     |

An import always creates a **new** part, and returns `201 {part, warnings}`.

## Named versions

A version is a named, kept copy of a part's tree ("Rev B, sent to the shop").
They live in the `part_versions` table (migration 0017) and are **never
pruned**: unlike the 50-step undo ring, a version lasts as long as its part.

| Action  | Gateway                                          | loft-script                  |
| ------- | ------------------------------------------------ | ---------------------------- |
| Save    | `POST /api/v1/parts/{id}/versions` (201)         | `part.save_version("Rev B")` |
| List    | `GET /api/v1/parts/{id}/versions`, newest first  | `part.versions()`            |
| Restore | `POST /api/v1/parts/{id}/versions/{seq}/restore` | `part.restore_version(2)`    |

A save sends `{name, message?, author?, expected_tree_version?}`; a restore
sends `{expected_tree_version}` and answers with the restored tree.

- `seq` is per part, starts at 1 and only grows; an import keeps the file's.
- A version stores the tree exactly as `tree.json` holds it, and its
  `tree_sha256` is the sha256 of those canonical bytes.
- The **author** is a display name the caller gives, or null. No account id or
  email is stored with a version or written to a file.
- **Saving** is not an edit: `tree_version` and the undo ring do not move.
- **Restoring** is one edit through the history ring: undo walks back to the
  tree before it, and no version is deleted. It writes back the features (with
  their ids), their order and suppression, and the rollback bar, which is the
  state undo covers. The part's name, display unit and materials are left as
  they are. The tree is validated with the import's `POST /features` rules first
  (params are upcast), and a restore that would remove a drawing section view's
  cutting plane is refused like an undo (`409 part_restore_conflict`).
- Caps: 100 versions a part and 128 MiB of version trees (canonical JSON, STEP
  inline) a part. Past either, a save is refused with `409 part_version_limit`;
  nothing is ever dropped to make room. One version tree is capped at 8 MiB
  (`422 part_version_too_large`).
- Every route is authenticated and owner-scoped: another owner's part is `404`.

## Container

A zip holding only data. Members, in this order:

| Member                     | What                                                                       |
| -------------------------- | -------------------------------------------------------------------------- |
| `manifest.json`            | what the file is, and the sha256 of every other member                     |
| `tree.json`                | the feature tree: the only thing an import builds from                     |
| `versions/index.json`      | the named versions, ascending `seq` (1.1; absent when the part has none)   |
| `versions/<seq>.tree.json` | one version's tree, same shape and rules as `tree.json` (1.1)              |
| `blobs/sha256-<hex>.step`  | an `import` feature's STEP text, moved out of every tree that names it     |
| `cache/body.step`          | the exported body, for tools that do not run Loft (absent with no body)    |

`manifest.json`: `format` `"loft"`, `format_version` `"1.2"`, `loft_version`,
`kind` `"part"`, `document_id`, `units` `{storage: "mm"}`, `tree_sha256`,
`members` `{path: sha256}`, `cache` `{step_sha256, built_from_tree_sha256,
properties {volume_mm3, area_mm2, bbox}}` or null, and `references` `[]`. There
is no export time.

`tree.json`: `name`, `length_unit`, `materials` (per-body entries sorted by
`base_feature_id`), `rollback_feature_id`, `parameters` (1.2, left out when the
table is empty), and `features` in tree order, each `{id, name, type,
param_version, suppressed, params}` plus, in 1.2, `expressions` and
`dimension_expressions` when the feature has formulas. Params are written at
the current `param_version`, through the feature registry, and always hold
numbers: every formula's resolved value is in place. There is no
`order_index`, no dependency edges, no timestamps and no undo history. An
import feature's `params.data` reads `"loft-blob:sha256:<hex>"`; the reader puts
the STEP text back.

`versions/index.json`: `{versions: [{seq, name, message, author, created_at,
tree_sha256}]}` in strictly ascending `seq`. `created_at` is UTC ISO 8601 (`Z`);
`author` is a display name or null; `tree_sha256` is the sha256 of
`versions/<seq>.tree.json`. Each version tree is written exactly like
`tree.json` (canonical JSON, blobs moved out), so a version identical to the
current tree has identical bytes, and the trees share one copy of each blob.

## Parameters and formulas (1.2)

The part's parameter table and every formula travel in each tree (`tree.json`
and every `versions/<seq>.tree.json`), as Loft stores them (RESEARCH §20):

- `parameters`: the table in its order, each `{id, name, expression, unit,
  comment, value}`; `value` is the resolved number (mm, degrees or plain).
- A feature's `expressions`: a JSON pointer into `params` to the formula that
  drives that number, `{"/distance_mm": "D * 2"}`. The number at the pointer
  is the formula's value.
- A sketch dimension's formula over the sketch's own dimensions
  (`width / 2`) stays in the dimension's `expression`, as every Loft reads it.
- A sketch dimension's formula that names anything outside its sketch (a
  parameter) is written beside the feature in `dimension_expressions`, a
  pointer to the dimension's `expression` to the formula
  (`{"/constraints/9/expression": "W"}`), and the dimension's `expression` is
  null, its `value_mm`/`value_deg` the resolved number. The reader puts it
  back. The pointer addresses the constraint by position, which a file can
  do because it is one snapshot. An entry that is not a formula of at most
  256 characters for a formula-less dimension of that sketch is
  `loft_tree_invalid`.

So `params` alone always builds the part, and an older Loft that ignores the
three keys imports the numbers (Versioning). An import keeps the table and the
formulas; documents resolves them again on write, so the part re-drives: change
a parameter and the body follows.

## Canonical bytes

The same part on the same Loft build writes the same bytes:

- JSON: `sort_keys`, `indent=2`, `ensure_ascii=False`, UTF-8 with LF and a
  trailing newline, `allow_nan=False`. Floats are the shortest round-trip repr;
  `-0.0` is written `0.0`.
- Zip: fixed member order, every date 1980-01-01, mode 0644, no extra fields;
  JSON STORED, STEP DEFLATE level 6.

Three frozen fixtures in `packages/loft-wire/tests/fixtures/`, never
regenerated (a format change adds a new one):

- `golden-v1.2.loft`: a parametric part (parameters `W` and `D`, a sketch
  width `= W` and height `= width / 2`, an extrude `= D * 2`, and version
  "Rev A") written by the real export. Read-then-repacked to the same bytes;
  over the real services, import, export, import into a fresh install and
  export again gives identical bytes, and the imported part re-drives
  (`services/gateway/tests/test_loft_parametric_chain.py`).
- `golden-v1.1.loft` (two versions, container-only params): still reads, and
  this build writes its inputs to the same members, `format_version` aside.
- `golden-v1.loft`: format 1.0; still reads.

### Diffing `.loft` files in git

A `.loft` diffs as its `tree.json`. Add to `.gitattributes`:

```
*.loft diff=loft
```

and to your git config:

```
git config diff.loft.textconv "unzip -p"
```

`unzip -p` prints `manifest.json`, `tree.json` and then the versions (the STEP
members are printed too; use `"sh -c 'unzip -p \"$0\" manifest.json tree.json'"`
to skip them).

## Versioning

- `format_version` is `major.minor`. A newer **major** is refused with
  `422 loft_format_too_new` ("This .loft was written by a newer Loft ...
  Upgrade Loft to open it.", `details.format_version` and
  `details.supported_major`), before anything else is read. A newer **minor**
  is read: every model ignores keys it does not know, and members it adds are
  skipped unread if their path is safe. Nothing warns about what was skipped.

| Version | Adds                                                              | What the previous minor's reader does with it               |
| ------- | ----------------------------------------------------------------- | ----------------------------------------------------------- |
| 1.0     | parts: `manifest.json`, `tree.json`, `blobs/`, `cache/body.step`  |                                                             |
| 1.1     | `versions/index.json`, `versions/<seq>.tree.json`                 | 1.0: imports the part without its versions                  |
| 1.2     | `parameters`, feature `expressions`, `dimension_expressions`      | 1.1: imports the numbers, without the table or any formula  |

- **A 1.1 Loft opening a 1.2 file** takes the newer-minor path: the manifest
  reads, there are no new members, and `tree.json` and the version trees
  validate with `parameters`, `expressions` and `dimension_expressions`
  ignored. `params` holds every resolved number, and the only formulas left
  are over a sketch's own dimensions, which 1.1 evaluates, so the part
  rebuilds to the exported volume with no warning; it is no longer
  parametric. Had a parameter formula stayed in a dimension's `expression`,
  1.1 would have read it as a sketch formula and failed the sketch (`unknown
  dimension name 'W'`); that is why 1.2 moves it out.
- **1.0 and 1.1 files** import unchanged: they have no parameters and no
  formulas, and their trees are written by 1.2 to the same bytes.
- `param_version`: an older version is upcast through the registry chain. A
  newer version (`loft_feature_too_new`) or an unknown type
  (`loft_feature_unknown_type`) is a 422 naming the feature.

## What an import does

1. Reads the upload in memory only (never to disk), with the checks under
   Limits.
2. Validates every feature exactly as `POST /features` does: `FeatureCreate`,
   import-with-prior-body, and same-part / strictly-earlier / type-compatible
   references, in tree order. Dependency edges are derived again.
3. **Ids.** The file's part and feature ids are kept, unless any of them already
   exists in this install; then all are re-minted. A re-mint rewrites the
   feature uuids inside each picked subshape's `topo_name` and drops hashed
   names (their digest covers the old ids), and remaps per-body materials.
4. **Name.** A taken name becomes "<name> copy" ("copy 2", ...), so importing
   the same file twice gives a copy.
5. Writes the part, its features and edges, and its versions (each `seq`
   kept) in one transaction. Every version tree is validated like the current
   one first, so any version can be restored; a version that fails is a 422
   naming it (`details.version_seq`). The id check and a re-mint cover the
   feature ids of every version as well as the current tree's.
6. Rebuilds the part from `tree.json`. The cached body is never sent to the
   kernel. The rebuilt volume is compared with the manifest at the kernel's
   1e-7 relative tolerance.

Warnings (`201`, never refusals): `loft_tree_edited` (tree.json does not match
its sha256; the cache is ignored), `loft_version_edited` (a version tree does not
match its index sha256; it is imported as it reads), `loft_cache_corrupt` (cached body does not
match; ignored), `loft_volume_mismatch`, `loft_rebuild_errors` (the part is
imported with its errors), `loft_verify_unavailable`.

A blob whose sha256 does not match is refused (`loft_blob_corrupt`).

## Limits

| Limit                                  | Value                          | Code                    |
| -------------------------------------- | ------------------------------ | ----------------------- |
| Upload (compressed, checked streaming) | 64 MiB                         | `loft_too_large`        |
| Zip entries (read from the EOCD first) | 256                            | `loft_too_many_members` |
| `manifest.json`                        | 1 MiB                          | `loft_member_too_large` |
| `tree.json`                            | 8 MiB                          | `loft_member_too_large` |
| One blob                               | 16 MiB (`MAX_INLINE_STEP_CHARS`) | `loft_member_too_large` |
| `cache/body.step`                      | 64 MiB                         | `loft_member_too_large` |
| All members, uncompressed              | 256 MiB                        | `loft_member_too_large` |
| Compression ratio (members ≥ 1 MiB)    | 100:1                          | `loft_zip_bomb`         |
| Features                               | 1000 (`MAX_TREE_FEATURES`)     | `loft_tree_invalid`     |
| Versions                               | 100 (`MAX_PART_VERSIONS`)      | `loft_too_many_versions` |
| `versions/index.json`                  | 1 MiB                          | `loft_member_too_large` |
| One `versions/<seq>.tree.json`         | 8 MiB                          | `loft_member_too_large` |

The central directory the end record declares is capped at 128 KiB (512 bytes an entry), so a lying entry count cannot make the parse expensive (`loft_too_many_members`). ZIP64 end records are refused outright
(`loft_zip_invalid`): zipfile would trust their counts over the capped classic
record, and a legal `.loft` never needs ZIP64. A blob may be named by any number of `import` features (the writer stores identical STEP text once), blobs are inlined only into an `import` feature's `params.data`, and every reference's inlined text counts against the 256 MiB total, checked before any text is decoded, so one blob fanned out past the total is refused (`loft_member_too_large`). `tree.json` with a non-finite number or pathological nesting is `loft_tree_invalid`. Each member is read with `read(cap + 1)`, so a header that understates a size
cannot make the reader allocate past the cap. Also refused: `..`, absolute or
drive paths, backslashes, duplicate names, directory entries, encrypted
members, compression other than STORED or DEFLATE (`loft_member_unsafe`,
`loft_member_duplicate`, `loft_member_encrypted`, `loft_member_compression`),
and members the format does not define (`loft_member_unknown`) unless the file
is a newer minor version. Version members must match `versions/index.json`
exactly: a tree it does not list, version trees with no index, or an index not in
ascending `seq` is `loft_versions_invalid`, and an entry without its tree is
`loft_member_missing`. Each version may name the blobs the current tree does;
every copy any tree inlines counts against the 256 MiB total. The export applies the same caps rather than write a file no Loft
could open. When the cached body is what takes a part over a cap, the file is
written without `cache/body.step` (the cache is untrusted and an import rebuilds
from the tree anyway), so a part never becomes unexportable; only trees over a
cap are refused (`422`, same codes). Both routes are
authenticated and rate-limited (`COMPUTE_RATE_LIMIT`).

## Not a backup

A `.loft` holds one part and its named versions. It has no undo history, no
drawings or assemblies that reference the part, and no account data. Back up the stack with
`just backup` ([OPERATIONS.md](./OPERATIONS.md)).
