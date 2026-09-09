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

## Local commands

From the CW repository root:

```bash
python -m tools.CIC validate-tools
python -m tools.CIC selftest
python -m tools.CIC import <source-folder> <cw-folder>
python -m tools.CIC import <source-folder> <cw-folder> --force
```

The default validation context is the locked `spec_sets/CW_CORE_v1.1.0.json` bundle (CCF 2.4.3 / NodeTypes 1.18.0 / Rulesets 3.14.0). An explicit `--spec-set` may be supplied when intentionally evaluating another immutable bundle.

## SSOT rule

**One truth. Many topologies. No duplicate truth.**

For CIC itself, the one truth is this directory in the CW repository.
