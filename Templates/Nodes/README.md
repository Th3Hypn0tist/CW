# CW Node templates

This directory contains copyable starter Node shards for the NodeTypes declared by the current CW Core NodeTypes specification.

The catalog is independent of StructureTree placement. Directory placement under `Templates/Nodes/` does not assign canonical identity, identity family, topology or NodeType. The explicit Node content remains authoritative.

```text
Templates/Nodes/
├── code/
│   ├── code.cw
│   ├── generic.cw
│   ├── system.cw
│   ├── component.cw
│   ├── input.cw
│   ├── output.cw
│   ├── binding.cw
│   ├── api.cw
│   ├── database.cw
│   └── ...other implementation/code-context Node templates...
├── abs.cw
├── doc.cw
├── contract.cw
└── topology_entity.abstract.cw
```

Identity-family examples:

```text
code/code.cw -> NodeType `code`      / #FILE family
abs.cw       -> NodeType `abs`       / #ABS family
doc.cw       -> NodeType `doc`       / #DOC family
contract.cw  -> NodeType `contract`  / #CTRCT family
```

`topology_entity.abstract.cw` represents the abstract `topology_entity` NodeType and is not intended as a normal concrete Node instance.

Each `.cw` file here is an individual Node shard, not a standalone CCF contract. Copy the appropriate template into a canonical CW model or sharded workspace and replace the placeholder identity and content.

NodeTypes define what is available to present. Rulesets define how it is read. StructureTree provides hierarchical navigation. Links provide relational navigation.
