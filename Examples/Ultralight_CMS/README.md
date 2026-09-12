# Ultralight CMS — CW Golden Reference

This directory is the normative target fixture for the next CanonicalWireframe toolchain generation.

- `Format/` is the self-contained interpretation environment.
- `Model/` is the canonical model-data root.
- `Assets/` contains opaque physical payloads owned by Nodes.
- NodeType declarations use `.cwn`; canonical model artifacts use `.cw`.
- CCF is the unchanged Canonical Contract Format 2.4.3.
- `Model/model.cw.format.format_version` is therefore `2.4.3`; CW package, DR, and model release versions are separate version dimensions.
- The package remains `unlocked` until the new linter and CIC pipeline validate the complete closure.
- Property identifiers are package-global inside the active `Model/` closure; bare Property references resolve by exact `Property.id` and never by locality or naming convention.
- `dependency` direction is explicit: `parent_ref` is the provider/dependency and `child_ref` is the dependent/consumer.
- DOC assets are presentation payloads only. DOC semantic scope is canonical `members[]`, not information inferred from SVG/image/PDF contents.

The fixture demonstrates Entity + Property canonical atoms; every Node as an abstraction; overlapping `members` abstractions; `FILE` as primary implementation family; reusable Schema/Data; Event-mediated Function boundaries; no `function_call` and no logic `call`; Required Links as Properties; one Asset maximum per Entity; deterministic identity-based asset naming; and validation limited to asset existence and registered file type/extension, never payload semantics.

The CMS behavior is intentionally small but no longer single-path: page selection is driven by `DATA_PAGE_REQUEST.page_id`, content is a multi-entry collection, successful content/style readiness composes an explicit draft and final publish document, and a missing page follows an explicit content-error branch to an error document.
