# Ultralight CMS — CW Golden Reference

This directory is the normative target fixture for the next CanonicalWireframe toolchain generation.

- `Format/` is the self-contained interpretation environment.
- `Model/` is the canonical model-data root.
- `Assets/` contains opaque physical payloads owned by Nodes.
- NodeType declarations use `.cwn`; canonical model artifacts use `.cw`.
- CCF is the unchanged Canonical Contract Format 2.4.3.
- The package remains `unlocked` until the new linter and CIC pipeline validate the complete closure.

The fixture demonstrates Entity + Property canonical atoms; every Node as an abstraction; overlapping `members` abstractions; `FILE` as primary implementation family; reusable Schema/Data; Event-mediated Function boundaries; no `function_call` and no logic `call`; Required Links as Properties; one Asset maximum per Entity; deterministic identity-based asset naming; and validation limited to asset existence and registered file type/extension, never payload semantics.
