# CW shard composition contract

Status: implementation contract for the human-editable sharded CW representation.

This contract defines representation assembly only. It does not add canonical semantics and it does not make paths, filenames, extensions, or StructureTree placement semantic authority.

## Principle

One canonical model may be serialized monolithically or as shards without changing canonical meaning.

```text
monolithic CW <-> normalized canonical model <-> sharded CW
```

A lossless composition of a sharded CW representation MUST produce the same normalized canonical model as its semantically equivalent monolithic representation.

## Serialization extensions

A monolithic CW model MAY be serialized as either:

```text
model.cw
model.json
```

The `.json` form exists for interoperability with tools and AI services that only permit JSON file extensions. It does not define different semantics and MUST contain the same monolithic Canonical Contract content that could be stored in `.cw`.

The `.json` extension is monolithic-only. A `.json` CW artifact MUST NOT declare external `shards`.

A sharded CW representation uses `.cw` exclusively for both the composition root and Node shards. This keeps the native multi-artifact representation unambiguous while preserving `.json` as a compatibility envelope for single-file exchange.

## Directory form

A sharded CW directory has one root artifact and zero or more Node shards.

```text
model.cw
FILE/
  ... .cw
ABS/
  ... .cw
DOC/
  ... .cw
CTRCT/
  ... .cw
```

The root artifact carries model-level Canonical Contract fields. Node shards carry canonical Entity/Node objects directly.

The directory names above are topology/navigation conventions only. A loader MUST NOT infer Entity identity, NodeType, Property semantics, relation semantics, or ownership from those names.

## Root artifact

`model.cw` is the composition root for sharded CW.

Before composition, its `entities` collection represents the monolithic Entity slot and MUST be empty when external Node shards are used. The root MAY carry representation-only shard metadata used to locate shards.

After composition, the loader materializes the normalized model by replacing the root `entities` collection with the loaded canonical Entity objects. Representation-only shard metadata is not canonical semantic authority.

A root artifact MUST NOT duplicate a canonical Entity definition that is also supplied by a shard.

A monolithic `.json` artifact is not a composition root and MUST NOT reference external shards.

## Node shard

A Node shard is a JSON-serialized canonical Entity object stored in a `.cw` artifact, for example:

```json
{
  "id": "#FILE:app",
  "name": "app",
  "entity_type_ref": "code",
  "status": "unlocked",
  "properties": [],
  "required_links": []
}
```

A shard MUST NOT wrap that Entity in a second Canonical Contract root merely because it is stored separately.

The Entity `id` is canonical identity. The shard path is not identity authority.

The Entity `entity_type_ref` is NodeType authority. The shard directory is not NodeType authority.

## Discovery

Input discovery may consider `.cw` and `.json` serialization files deterministically, but their permitted representation roles differ:

- `.json` MAY contain one complete monolithic Canonical Contract model;
- `.json` MUST NOT be used as a sharded composition root or Node shard;
- `.cw` MAY contain a monolithic Canonical Contract model;
- `model.cw` MAY be a sharded composition root;
- declared Node shards MUST use `.cw`.

The loader classifies canonical content by explicit structure, not by using the extension as semantic authority. Extension constrains only the permitted serialization topology.

If classification is ambiguous, composition fails. The loader MUST NOT guess identity, NodeType, relation meaning, ownership, or specification from filename, directory, extension, or naming convention.

## Deterministic composition

For one sharded model, composition MUST:

1. resolve exactly one `.cw` composition root;
2. discover the `.cw` Node shards declared by the representation;
3. parse every selected shard as one canonical Entity object;
4. reject duplicate canonical Entity ids;
5. preserve each Entity object without semantic rewriting;
6. materialize the root `entities` array deterministically;
7. resolve canonical Entity/Property references only after the complete model identity namespace has been assembled;
8. run specification selection and semantic validation against the assembled canonical model.

Ordering used for deterministic serialization or loading MUST NOT become semantic Entity ordering unless an owning canonical field explicitly declares ordered semantics.

## Specification boundary

Import and representation assembly do not select semantic meaning by path or importer implementation.

Importers emit CW canonical data. Specification selection is a separate step. The selected immutable specification set determines CCF, NodeTypes, Rulesets, and validation semantics for the assembled canonical model.

A loader MAY require a caller-provided specification selection before final semantic validation. It MUST NOT silently inject `latest`, `current`, a mutable branch, or an importer-hardcoded specification as semantic authority.

## Invalid composition

Composition fails before semantic readiness evaluation when any of the following occurs:

- no unique root can be resolved where a root is required;
- a `.json` artifact declares external shards;
- a sharded root does not use `.cw`;
- a declared shard does not use `.cw`;
- a declared shard is missing;
- a selected shard is not an Entity object;
- a shard contains more than one Entity definition;
- two shards define the same canonical Entity id;
- the root and a shard duplicate the same canonical Entity definition;
- a shard wrapper creates a second independent canonical contract identity for the same Node;
- composition requires guessing identity, NodeType, relation meaning, or specification from path/filename/extension.

## Round-trip requirement

Given canonical model `M`:

```text
M -> monolithic .cw serialization -> normalize = M
M -> monolithic .json serialization -> normalize = M
M -> sharded .cw serialization -> compose -> normalize = M
```

All paths MUST preserve the same active canonical identities, Properties, Links, Required Links, Function logic, references, gaps, and model-level contract semantics.

Whitespace, JSON key order, shard file order, and physical shard placement may differ when they are not explicitly canonical semantics.
