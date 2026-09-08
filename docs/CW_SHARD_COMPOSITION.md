# CW shard composition contract

Status: implementation contract for the human-editable sharded CW representation.

This contract defines representation assembly only. It does not add canonical semantics and it does not make paths, filenames, extensions, or StructureTree placement semantic authority.

## Principle

One canonical model may be serialized monolithically or as shards without changing canonical meaning.

```text
monolithic CW <-> normalized canonical model <-> sharded CW
```

A lossless composition of a sharded CW representation MUST produce the same normalized canonical model as its semantically equivalent monolithic representation.

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

`model.cw` is the composition root.

Before composition, its `entities` collection represents the monolithic Entity slot and MUST be empty when external Node shards are used. The root MAY carry representation-only shard metadata used to locate shards.

After composition, the loader materializes the normalized model by replacing the root `entities` collection with the loaded canonical Entity objects. Representation-only shard metadata is not canonical semantic authority.

A root artifact MUST NOT duplicate a canonical Entity definition that is also supplied by a shard.

## Node shard

A Node shard is a JSON-serialized canonical Entity object, for example:

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

Directory discovery considers `.cw` and `.json` serialization files deterministically.

The loader classifies content by explicit structure, not extension or path:

- a composition root is an object with a Canonical Contract `format` block and model-level contract fields;
- a Node shard is an object with canonical Entity fields such as `id`, `name`, `entity_type_ref`, `status`, and `properties` and without a Canonical Contract root `format` block;
- other JSON/CW files are not silently interpreted as model members.

If classification is ambiguous, composition fails. The loader MUST NOT guess from filename, directory, extension, or naming convention.

## Deterministic composition

For one sharded model, composition MUST:

1. resolve exactly one composition root;
2. discover the Node shards declared by the representation or, when declaration is intentionally omitted, only by an explicitly defined deterministic loader policy;
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
M -> monolithic serialization -> normalize = M
M -> sharded serialization -> compose -> normalize = M
```

Both paths MUST preserve the same active canonical identities, Properties, Links, Required Links, Function logic, references, gaps, and model-level contract semantics.

Whitespace, JSON key order, shard file order, and physical shard placement may differ when they are not explicitly canonical semantics.
