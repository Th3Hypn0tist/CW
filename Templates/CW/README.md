# CW sharded structure template

This directory is the minimal sharded CW template.

```text
CW/
├── FILE/
│   └── code.cw
├── ABS/
│   └── abs.cw
├── DOC/
│   └── doc.cw
└── CTRCT/
    └── contract.cw
```

Every current canonical StructureTree root has one minimal Node template.

```text
#FILE  -> FILE/
#ABS   -> ABS/
#DOC   -> DOC/
#CTRCT -> CTRCT/
```

This directory demonstrates shard placement and hierarchy. It is not the reusable Node template catalog; those templates live under `Templates/Nodes/`.

Directory placement is navigation/topology, not semantic inference authority. Canonical identity and NodeType remain explicit in Node content.

The monolithic starter remains at `Templates/CanonicalWireframe_Template.cw`.
