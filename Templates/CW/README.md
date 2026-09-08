# CW sharded Node templates

This directory mirrors the canonical StructureTree roots and contains one starter Node shard for every NodeType in `CanonicalWireframe_NodeTypes_v1.17.0.json`.

```text
CW/
├── FILE/
│   ├── code.cw
│   └── NODETYPES/
│       └── ...all non-family NodeType templates...
├── ABS/
│   └── abs.cw
├── DOC/
│   └── doc.cw
└── CTRCT/
    └── contract.cw
```

Canonical identity families:

```text
#FILE  -> code
#ABS   -> abs
#DOC   -> doc
#CTRCT -> contract
```

The files under `FILE/NODETYPES/` are collected there only so every currently declared NodeType has a copyable starter. Directory placement does not infer semantic identity or NodeType; the explicit `id` and `entity_type_ref` remain authoritative.

`topology_entity.abstract.cw` represents the abstract `topology_entity` NodeType and is not intended as a normal concrete Node.

Each `.cw` file in this directory is a Node shard, not a standalone CCF contract. Copy the Node into a canonical CW model or use it as the starting point for a sharded CW workspace once the selected loader defines shard composition.

NodeTypes define what is available to present. Rulesets define how it is read. StructureTree provides hierarchical navigation. Links provide relational navigation.
