# Ultralight CMS — CW Golden Reference

This directory is the normative target fixture for the next CanonicalWireframe toolchain generation.

- `Format/` is the self-contained interpretation environment.
- `Model/` is the canonical mechanism/model-data root.
- `Assets/` contains opaque physical payloads owned by Nodes.
- NodeType declarations use `.cwn`; canonical model artifacts use `.cw`.
- CCF is the unchanged Canonical Contract Format 2.4.3.
- `Model/model.cw.format.format_version` is therefore `2.4.3`; CW package, DR, and model release versions are separate version dimensions.
- The package remains `unlocked` until the new linter and CIC pipeline validate the complete closure.
- Property identifiers are package-global inside the active `Model/` closure; bare Property references resolve by exact `Property.id` and never by locality or naming convention.
- A Link Property's storage owner is independent from its semantic endpoints. `event_cause.parent_ref` identifies the causing Function even when the Link Property is stored on another Entity.
- `dependency` direction is explicit: `parent_ref` is the provider/dependency and `child_ref` is the dependent/consumer.
- DOC assets are presentation payloads only. DOC semantic scope is canonical `members[]`, not information inferred from SVG/image/PDF contents.

## Golden mechanism-only invariant

The golden `Model/` is a machine-readable mechanism, not one populated CMS run. Runtime/example request and content values are therefore not canonical Model truth.

- `DATA_PAGE_REQUEST`, `DATA_CONTENT_COLLECTION`, and `DATA_STYLE_STYLESHEET` are typed runtime slots with `value: null`.
- Derived Data slots also start `null`; readiness flags may use mechanism-defined initial `false` state.
- Schemas, Event/Function/Effect topology, Required Links, lookup/branching behavior, and state-transition constants remain canonical mechanism.
- Concrete page records (`home`, `about`), CSS, HTML presentation literals, and similar fixture payload belong only to opaque `Assets/`.
- Asset payloads are not parsed by the CW validator. It validates only existence, ownership path, registered `file_type_ref`, extension, and asset cardinality.

The fixture demonstrates Entity + Property canonical atoms; every Node as an abstraction; overlapping `members` abstractions; `FILE` as primary implementation family; reusable Schema/Data; Event-mediated Function boundaries; no `function_call` and no logic `call`; Required Links as Properties; one Asset maximum per Entity; deterministic identity-based asset naming; and validation limited to asset existence and registered file type/extension, never payload semantics.

The CMS behavior is intentionally small but not single-path: runtime `DATA_PAGE_REQUEST.page_id` selects from a runtime-populated content collection, successful content/style readiness composes an explicit structured draft and final publish document, and a missing page follows an explicit content-error branch. The actual HTML serialization remains implementation payload in `Assets/FILE/%23FILE%3Arenderer.js`, not duplicated as canonical Model content.
