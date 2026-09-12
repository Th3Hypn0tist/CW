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
- This fixture does not demonstrate the registered `CTRCT` family. Registered families are open-ended, and an unused family does not require a fixture Entity.

## Package-relative references

Canonical path-bearing values never need `..` traversal. Their resolution base is part of the Format contract:

- `ccf_ref`, `dr_ref` and `nodetypes_ref` resolve relative to `Format/`.
- `model_root`, `assets_root` and the model manifest resolve relative to the package root.
- `shards[].artifact_ref` resolves relative to `Model/`.
- Asset `asset_ref` resolves relative to the package root.
- The model points to its local Format as `LOCAL_FORMAT:Format`.

Path values themselves remain canonical relative paths: no absolute paths, backslashes, empty segments, `.` segments or `..` segments.

## Data lifecycle

A Data Property defines a runtime slot contract. Runtime values live in an execution context and do not mutate the canonical `.cw` model.

- `value: null` means `UNBOUND`, not schema-invalid.
- `READY` means non-null and schema-valid when a `schema_ref` exists.
- Invalid non-null bindings never satisfy a `ready` condition.
- Event occurrences retain their execution context through Function/Event/Effect causality.
- `event_condition` with `condition_mode: ready` waits on the actual Data slot. No parallel `*_READY` Data Properties exist.
- One `emit` creates one Event occurrence. If its conditions are not ready, that occurrence waits and dispatches exactly once when they become ready.

Package validity and runtime readiness are different dimensions. A package may validly declare `DATA_CONTENT_COLLECTION` with `value: null`; this proves the slot contract is valid, not that a runtime execution context has already bound the collection or made it READY.

`lookup` has an explicit boundary: its source collection MUST already be `READY`. Calling `lookup` against an `UNBOUND` or `INVALID` source is INVALID execution, not a `null` result. Against a READY collection, zero matches returns `null`; more than one match is INVALID.

## Function interfaces and control relays

`Function.input_refs` and `Function.output_refs` describe canonical Properties the modeled Function logic actually reads and writes. They do not describe all Data visible in the surrounding execution context.

`FUNCTION_OPEN_PAGE` therefore has empty `input_refs` and `output_refs`: it is intentionally a pure causal relay. `DATA_PAGE_REQUEST` belongs to `EVENT_OPEN_PAGE` and remains available in the preserved execution context, but `FUNCTION_OPEN_PAGE` itself does not read or rewrite that Data.

This distinction keeps control flow and Data flow separate:

```text
control: Event -> Function -> Event
state:   execution context -> canonical Data slots
```

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
  -> impossible invariant violation: fail INVALID_CONTENT_SOURCE
```

`index` is a mechanism constant; its human-facing title is unrelated to routing identity and may be `Home`, `Etusivu`, or anything else. Because a content collection becomes `READY` only after schema validation, a READY collection is guaranteed to contain exactly one `index` item. The explicit `INVALID_CONTENT_SOURCE` failure still closes the control path so a broken runtime cannot silently write `null` forward.

The style asset is raw CSS, so `SCHEMA_STYLE_SHEET` is a string rather than an artificial `{css: ...}` wrapper. Compose reads the actual ready style slot directly.

## Mechanism-only invariant

The golden `Model/` describes schemas, slots, routing, topology and causality. Concrete page records, CSS, HTML serialization and similar implementation/example payloads live only in opaque `Assets/`. The CW package validator never parses those payloads; an adapter/runtime validates any payload-derived Data binding before that Data becomes READY.

The fact that the example `content.json` visibly happens to be a list is not package-validator truth. The validator checks the Asset reference, path, registered type, extension and cardinality only. Runtime binding is where the decoded payload is checked against `SCHEMA_CONTENT_COLLECTION`.

Filesystem semantics are deterministic: canonical paths use `/`, UTF-8 + NFC, exact RFC3986-style uppercase percent encoding, reject case-fold collisions and path traversal, and do not admit symlinks as canonical package members.
