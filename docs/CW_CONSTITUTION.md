# CW Constitution

> **One truth. Many topologies. No duplicate truth.**

This document defines the architectural invariants of Canonical Wireframe (CW). Machine-enforced realization remains expressed through the active locked Canonical Contract Format, NodeTypes, Rulesets, and their pinned immutable specification closure.

If an implementation, projection, importer, renderer, editor, serializer, or future specification change conflicts with these invariants, the conflict must be made explicit and resolved by formalization. No component may silently create a second semantic authority.

## Article I — One Truth, Many Topologies

### 1. Canonical truth

CW SHALL maintain exactly one canonical semantic model.

Canonical Entities, Properties, Links, identities, and their resolved semantics constitute that model.

No projection, renderer, topology, directory structure, serialization layout, adapter, importer, editor state, cache, or derived representation may establish a parallel semantic authority.

### 2. Many topologies

The same canonical model MAY be exposed through any number of topologies.

A topology may organize, navigate, filter, group, abstract, document, contract, or visualize canonical model objects, but it SHALL NOT duplicate or redefine their canonical meaning.

Different topologies SHALL reuse the same canonical identities and canonical Properties.

### 3. Universal Entity / Node / Property principle

A rendered Node is a projection of a canonical Entity.

All core Entity families use the same canonical Entity and Property model and the same universal Node projection principle.

The core Entity identity families are:

- `#FILE` — master implementation topology
- `#ABS` — abstraction topology
- `#DOC` — documentation topology
- `#CTRCT` — contract topology

These families SHALL NOT define parallel Node object models or parallel Property systems.

Their specialization is selected through the canonical Entity type reference and resolved NodeType. Actual semantic state remains in canonical Entity Properties and canonical Link Properties.

A NodeType may define structural projection expectations, member structure, interfaces, Property presentation expectations, and Required Link declarations. A NodeType SHALL NOT redefine Property value semantics or Link semantics owned by Rulesets.

### 4. Master implementation topology

`#FILE` SHALL provide the master implementation topology.

One accepted implementation source file maps to one canonical `#FILE` Entity identity.

Source-language suffix, filename extension, rendering choice, or serialization location SHALL NOT create a second canonical identity.

`#ABS`, `#DOC`, and `#CTRCT` may refer to canonical `#FILE` or `#ABS` identities where they concern implementation or abstraction structure.

They SHALL NOT reproduce a referenced `#FILE` or `#ABS` semantic object as a second authoritative definition.

### 5. Abstraction topology

`#ABS` represents a canonical abstraction Entity.

An abstraction may organize or expose existing canonical model objects, but membership or abstraction SHALL NOT duplicate those objects or their identities.

An abstraction member references an already canonical model object.

Any machine-significant abstraction relation SHALL be represented through canonical structured semantics governed by the active specification closure.

### 6. Documentation topology

`#DOC` represents a canonical document Entity.

A `#DOC` Entity may document, explain, justify, specify, or otherwise relate to canonical `#FILE`, `#ABS`, `#DOC`, or `#CTRCT` identities through canonical Links permitted by the governing Rulesets.

A document is not required to use the `.cw` extension.

Its physical representation MAY be any supported readable format, including but not limited to Markdown, plain text, HTML, JSON, or PDF.

Examples:

```text
DOC/architecture/rationale.md
DOC/architecture/specification.pdf
DOC/notes/context.txt
```

The representation format, filename, extension, and physical path do not define the canonical identity or semantic meaning of the `#DOC` Entity.

Representation-specific parsing, extraction, previewing, or rendering belongs to adapter/tooling behavior and SHALL NOT become canonical semantic authority.

### 7. Contract topology

`#CTRCT` represents a canonical contract Entity.

A contract may define machine-significant constraints, obligations, interfaces, or agreements concerning canonical `#FILE` or `#ABS` targets, subject to the governing canonical Properties and Rulesets.

A contract SHALL NOT become an alternate definition of the referenced target.

### 8. Universal Link model

Every machine-significant directed semantic relation SHALL be representable as a canonical Link Property.

The Link type vocabulary is open-ended.

Structure Core, renderers, editors, importers, and other consumers SHALL NOT contain a closed semantic list of Link types as an independent authority.

The governing Link Ruleset defines:

- Link value semantics
- semantic endpoint roles
- endpoint compatibility
- Link Property ownership and placement
- flow and causality semantics where applicable
- Required Link satisfaction semantics where applicable

A Link SHALL NOT derive semantic meaning from visual direction, geometry, filename, path, serialization order, or renderer behavior.

A document such as `rationale.md` may therefore be canonically connected to code, an abstraction, another document, or a contract. Either endpoint may occupy the semantic role permitted by the governing Link Ruleset. The canonical Link owner/placement is determined by that Ruleset, not by display direction.

### 9. Reference, never copy

When one canonical topology concerns another canonical object, it SHALL reference that object's canonical identity rather than duplicate its semantic definition.

This applies across `#FILE`, `#ABS`, `#DOC`, and `#CTRCT`.

A reference may create another topology, navigation path, view, abstraction, document relation, or contract relation. It SHALL NOT create another truth.

### 10. Representation independence

Canonical identity is representation-independent.

Physical representation belongs to the adapter boundary.

Paths and directory structures MAY mirror canonical identities for deterministic storage, discovery, and navigation, but they SHALL NOT create, infer, replace, or override canonical semantic identity.

### 11. Monolithic and sharded forms

CW MAY be represented as one monolithic canonical artifact or as a deterministic sharded representation.

Both forms SHALL resolve to the same canonical semantic model.

Sharded root families MAY include:

```text
FILE/
ABS/
DOC/
CTRCT/
```

For CW-native shards, identity may be mirrored structurally, for example:

```text
#ABS:boo:far:doo
ABS/boo/far/doo.cw

#CTRCT:foo:bar:doo
CTRCT/foo/bar/doo.cw
```

For `#DOC`, the physical representation retains its readable document format and is not forced to `.cw`:

```text
#DOC:architecture:rationale
DOC/architecture/rationale.md
```

The path is a representation/storage projection. Canonical identity remains authoritative in the canonical model.

### 12. Derived state

StructureTree and equivalent indexes, projection graphs, navigation trees, spatial layouts, visual surfaces, caches, and runtime convenience structures SHALL remain derived and rebuildable.

Derived state SHALL NOT become a second source of truth.

User editing through Structure or another canonical authoring tool SHALL modify candidate canonical CW state, validate it against the applicable pinned specification closure, and rebuild projections from accepted canonical state.

### 13. Tooling boundary

Tools may extract, import, serialize, validate, project, render, or edit CW, but tools SHALL NOT redefine CW semantics locally.

Source importers such as CIC may know how to extract implementation evidence and map it into CW. Canonical semantic authority remains in CW and its pinned specification closure.

Consumers shall depend on valid CW, not on importer internals.

## Constitutional invariant

**One truth. Many topologies. No duplicate truth.**
