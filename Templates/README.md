# CW templates

CW templates are separated by purpose:

```text
Templates/
├── CanonicalWireframe_Template.cw  # monolithic canonical model starter
├── CW/                             # minimal sharded StructureTree template
│   ├── FILE/
│   │   └── code.cw
│   ├── ABS/
│   │   └── abs.cw
│   ├── DOC/
│   │   └── doc.cw
│   └── CTRCT/
│       └── contract.cw
└── Nodes/                          # copyable individual Node templates
    ├── code/                       # code / implementation Node examples
    ├── abs.cw
    ├── doc.cw
    ├── contract.cw
    └── topology_entity.abstract.cw
```

`Templates/CanonicalWireframe_Template.cw` is the monolithic starter.

`Templates/CW/` demonstrates the minimal sharded CW hierarchy. Every canonical StructureTree root contains a minimal Node template.

`Templates/Nodes/` is the reusable Node template catalog. Its directory layout is template organization only and is not semantic authority.
