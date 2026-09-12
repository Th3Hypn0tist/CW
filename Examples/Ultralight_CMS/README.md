# Ultralight CMS — CW Golden Reference

This directory is the normative target fixture for the next CanonicalWireframe toolchain generation.

- `Format/` is the self-contained interpretation environment.
- `Model/` is the canonical mechanism/model-data root.
- `Assets/` contains opaque physical payloads owned by Nodes.
- NodeType declarations use `.cwn`; canonical model artifacts use `.cw`.
- CCF is the unchanged Canonical Contract Format 2.4.3.
- CCF, CW package format, Dependency Rules and modeled-system release versions are independent dimensions. `CW.json.version_dimensions` points to their authoritative sources and does not duplicate their current values.
- The package remains `unlocked` until the new linter and CIC pipeline validate the complete closure.
- `Model/model.cw.shards[]` is the authoritative Model closure. Every non-root `.cw` shard is listed exactly once and unlisted `.cw` files invalidate the package.
- Property identifiers are package-global inside the active `Model/` closure; bare Property references resolve by exact `Property.id` and never by locality or naming convention.
- A Link Property's owner is its declarer. Storage ownership is independent from semantic endpoints; `event_cause.parent_ref` identifies the causing Function.
- `dependency` direction is explicit: `parent_ref` is the provider/dependency and `child_ref` is the dependent/consumer.
- DOC assets are presentation payloads only. DOC semantic scope is canonical `members[]`, not information inferred from SVG/image/PDF contents.

## Data lifecycle

A Data Property defines a runtime slot contract. Runtime values live in an execution context and do not mutate the canonical `.cw` model.

- `value: null` means `UNBOUND`, not schema-invalid.
- `READY` means non-null and schema-valid when a `schema_ref` exists.
- Invalid non-null bindings never satisfy a `ready` condition.
- Event occurrences retain their execution context through Function/Event/Effect causality.
- `event_condition` with `condition_mode: ready` waits on the actual Data slot. No parallel `*_READY` Data Properties exist.
- One `emit` creates one Event occurrence. If its conditions are not ready, that occurrence waits and dispatches exactly once when they become ready.

## CMS routing mechanism

The opaque content asset is a list of records shaped as:

```json
{"id":"index","title":"Home","body":"..."}
```

`SCHEMA_PAGE_CONTENT` defines required `id`, `title` and `body`. `SCHEMA_CONTENT_COLLECTION` requires unique `id` values and requires an item whose `id` is `index`.

Routing therefore has deterministic semantics:

```text
requested page_id
  -> lookup content by id
  -> found: use it
  -> missing: lookup id="index"
```

`index` is a mechanism constant; its human-facing title is unrelated to routing identity and may be `Home`, `Etusivu`, or anything else. Because a content collection becomes `READY` only after schema validation, a READY collection is guaranteed to contain exactly one `index` item. Missing `index` is therefore a runtime binding/schema failure, not a normal page-not-found branch.

The style asset is raw CSS, so `SCHEMA_STYLE_SHEET` is a string rather than an artificial `{css: ...}` wrapper. Compose reads the actual ready style slot directly.

## Mechanism-only invariant

The golden `Model/` describes schemas, slots, routing, topology and causality. Concrete page records, CSS, HTML serialization and similar implementation/example payloads live only in opaque `Assets/`. The CW package validator never parses those payloads; an adapter/runtime validates any payload-derived Data binding before that Data becomes READY.

Filesystem semantics are also deterministic: canonical paths use `/`, UTF-8 + NFC, exact RFC3986-style uppercase percent encoding, reject case-fold collisions and path traversal, and do not admit symlinks as canonical package members.
