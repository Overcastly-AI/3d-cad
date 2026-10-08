# The `.loft` file format

A `.loft` file is one Loft part as a file you own: the whole parametric feature
tree, which any Loft can import back into an editable part, plus a cached STEP
body that any CAD tool can open. Format version **1.0** (step 1: parts).
Named versions (step 2) and assemblies (step 3) come later.

Code: `packages/loft-wire/src/loft_wire/loft_file.py` (the format),
`services/documents/src/documents/loft_file.py` (tree read and import),
`services/gateway/src/gateway/loft_file.py` (the two routes).

## Routes and clients

| Where       | Export                                    | Import                                      |
| ----------- | ----------------------------------------- | ------------------------------------------- |
| Gateway     | `GET /api/v1/parts/{id}/export.loft`      | `POST /api/v1/parts/import` (raw body)      |
| Web         | Export strip, `Save .loft` link           | Parts register top bar, `Open .loft`        |
| loft-script | `part.save("bracket.loft")`               | `session.open("bracket.loft")`              |
| Offline     |                                           | `loft.open("bracket.loft")` (read only)     |

An import always creates a **new** part, and returns `201 {part, warnings}`.

## Container

A zip holding only data. Members, in this order:

| Member                     | What                                                                       |
| -------------------------- | -------------------------------------------------------------------------- |
| `manifest.json`            | what the file is, and the sha256 of every other member                     |
| `tree.json`                | the feature tree: the only thing an import builds from                     |
| `blobs/sha256-<hex>.step`  | an `import` feature's STEP text, moved out of the tree                     |
| `cache/body.step`          | the exported body, for tools that do not run Loft (absent with no body)    |

`manifest.json`: `format` `"loft"`, `format_version` `"1.0"`, `loft_version`,
`kind` `"part"`, `document_id`, `units` `{storage: "mm"}`, `tree_sha256`,
`members` `{path: sha256}`, `cache` `{step_sha256, built_from_tree_sha256,
properties {volume_mm3, area_mm2, bbox}}` or null, and `references` `[]`. There
is no export time.

`tree.json`: `name`, `length_unit`, `materials` (per-body entries sorted by
`base_feature_id`), `rollback_feature_id`, and `features` in tree order, each
`{id, name, type, param_version, suppressed, params}`. Params are written at
the current `param_version`, through the feature registry. There is no
`order_index`, no dependency edges, no timestamps and no undo history. An
import feature's `params.data` reads `"loft-blob:sha256:<hex>"`; the reader puts
the STEP text back.

## Canonical bytes

The same part on the same Loft build writes the same bytes:

- JSON: `sort_keys`, `indent=2`, `ensure_ascii=False`, UTF-8 with LF and a
  trailing newline, `allow_nan=False`. Floats are the shortest round-trip repr;
  `-0.0` is written `0.0`.
- Zip: fixed member order, every date 1980-01-01, mode 0644, no extra fields;
  JSON STORED, STEP DEFLATE level 6.

`packages/loft-wire/tests/fixtures/golden-v1.loft` is checked byte for byte.

### Diffing `.loft` files in git

A `.loft` diffs as its `tree.json`. Add to `.gitattributes`:

```
*.loft diff=loft
```

and to your git config:

```
git config diff.loft.textconv "unzip -p"
```

`unzip -p` prints `manifest.json` then `tree.json` (the STEP members are
printed too; use `"sh -c 'unzip -p \"$0\" manifest.json tree.json'"` to skip
them).

## Versioning

- `format_version` is `major.minor`. A newer **major** is refused with
  `422 loft_format_too_new` ("Upgrade Loft"). A newer **minor** is read; keys
  it adds are ignored, and members it adds are skipped unread if their path is
  safe.
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
5. Writes the part, its features and edges in one transaction.
6. Rebuilds the part from `tree.json`. The cached body is never sent to the
   kernel. The rebuilt volume is compared with the manifest at the kernel's
   1e-7 relative tolerance.

Warnings (`201`, never refusals): `loft_tree_edited` (tree.json does not match
its sha256; the cache is ignored), `loft_cache_corrupt` (cached body does not
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

The central directory the end record declares is capped at 128 KiB (512 bytes an entry), so a lying entry count cannot make the parse expensive (`loft_too_many_members`). ZIP64 end records are refused outright
(`loft_zip_invalid`): zipfile would trust their counts over the capped classic
record, and a legal `.loft` never needs ZIP64. Each blob may be named by one `import` feature only (`loft_blob_reused`), blobs are inlined only into an `import` feature's `params.data`, and the inlined text counts against the 256 MiB total. `tree.json` with a non-finite number or pathological nesting is `loft_tree_invalid`. Each member is read with `read(cap + 1)`, so a header that understates a size
cannot make the reader allocate past the cap. Also refused: `..`, absolute or
drive paths, backslashes, duplicate names, directory entries, encrypted
members, compression other than STORED or DEFLATE (`loft_member_unsafe`,
`loft_member_duplicate`, `loft_member_encrypted`, `loft_member_compression`),
and members the format does not define (`loft_member_unknown`) unless the file
is a newer minor version. Both routes are authenticated and rate-limited
(`COMPUTE_RATE_LIMIT`).

## Not a backup

A `.loft` holds one part. It has no undo history, no drawings or assemblies
that reference the part, and no account data. Back up the stack with
`just backup` ([OPERATIONS.md](./OPERATIONS.md)).
