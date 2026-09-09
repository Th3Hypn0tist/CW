# CIC

`CW/tools/CIC/` is the authoritative CIC source.

All other CIC copies are synchronized consumers. Their synchronization mechanism is owned elsewhere and does not change CIC authority.

## Boundary

CIC owns deterministic source acquisition, parser/evidence extraction, unbound CW candidate generation, transactional create/update, and Node version stamping.

CIC does **not** own canonical specification semantics. The CW specification set and CW linter remain independent authorities in this repository.

The public import gate therefore runs this exact order:

```text
validate CIC + CW tooling
  -> validate selected immutable CW specification set
  -> import source to staged unbound CW
  -> compose / representation-validate CW
  -> bind specification only in a temporary validation projection
  -> semantic CW validation
  -> timestamp changed/new Nodes
  -> calculate MD5 with hash field present as ""
  -> write shards
  -> read back and reverse-verify hashes
  -> semantic CW validation again
  -> atomically expose target CW
```

`READY` and `UNREADY` are both valid model states for the version gate. `INVALID_MODEL`, invalid specification/tooling, representation failure, or hash failure aborts the transaction and creates no new authoritative version.

The written CIC output remains specification-unbound. Temporary validation binding is evaluation context only and is never silently persisted by CIC.

Source and output trees must be disjoint. CIC rejects the same directory, an output that contains the source, and an output located anywhere inside the source tree. This prevents a subsequent import from ingesting an earlier generated CW snapshot as source input.

## Node version

```text
id        = persistent canonical Node identity
timestamp = YYYYMMDDhhmmss chronological version order
hash      = lowercase MD5 version checksum
```

Hash generation:

```text
validate first
timestamp = current UTC time formatted YYYYMMDDhhmmss
hash = ""
MD5(deterministic direct Entity shard serialization)
hash = calculated digest
write
read back
hash = ""
recalculate MD5
compare
```

An unchanged Node preserves its previous timestamp/hash during `--force` update. Only changed or new Nodes receive a new version.

MD5 is a fast version checksum. It is not security, authenticity, trust, or semantic identity authority.

## Local release gate

From the CW repository root:

```bash
python -m tools.CIC release-check
```

This is the authoritative local pre-sync gate. It:

1. compiles the CIC and CW validation tools,
2. validates the selected immutable specification closure,
3. runs the complete import -> semantic validation -> stamp -> reverse-verify selftest,
4. runs the CIC regression suite,
5. rejects `api_legacy.py`, `structuretree.py`, and imports of their old package paths.

The lower-level commands remain available:

```bash
python -m tools.CIC validate-tools
python -m tools.CIC selftest
python -m tools.CIC import <source-folder> <cw-folder>
python -m tools.CIC import <source-folder> <cw-folder> --force
```

The default validation context is the locked `spec_sets/CW_CORE_v1.1.0.json` bundle (CCF 2.4.3 / NodeTypes 1.18.0 / Rulesets 3.14.0). An explicit `--spec-set` may be supplied when intentionally evaluating another immutable bundle.

## Synchronization contract

`CW/tools/CIC/` is the source copied to consumer repositories. A synchronized consumer may expose it as top-level `CIC/`; the package bootstrap deliberately supports both locations without maintaining two implementations.

The public importer still requires access to the CW specification/linter authority. Inside the CW repository this is discovered automatically. When a synchronized CIC copy is executed from another repository, set `CW_ROOT` to a local CW checkout containing `spec_sets/` and `linter/`, or pass `cw_root` explicitly. A consumer copy must not carry or invent a parallel specification authority merely to make CIC self-contained.

The synchronization mechanism itself is outside CIC and outside this contract. A consumer copy does not become an authority merely because it is locally modified.

## SSOT rule

**One truth. Many topologies. No duplicate truth.**

For CIC itself, the one truth is this directory in the CW repository.
