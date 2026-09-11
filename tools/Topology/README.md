# Topology

Interactive and shell views over canonical CW.

The implementation is split into reusable library code and View hosts. Canonical relation semantics are read only from explicit CW content. Names, paths, filenames, geometry and rendering do not become semantic authority.

## Interactive View

Launch with or without an initial CW source:

```bash
python3 -m tools.Topology
python3 -m tools.Topology Examples/Ultralight_CMS_CW_Open_Page_v1.4.json
```

Keymap:

```text
Up / Down   scroll
O           open existing CW folder or monolith
C           import a code folder through canonical CIC
T           select explicit canonical link_type_ref topology
H           select hierarchy / topology / Mermaid view
E           export current view to Markdown
Q Q Q       quit
```

## One StructureTree hierarchy

`hierarchy` renders one StructureTree over all discovered canonical Entity Nodes.
Identity-family branches such as `#FILE`, `#DOC`, `#CTRCT` and `#ABS` are siblings below one common `ROOT`; they are not separate hierarchy projections.

```text
ROOT
|-- #FILE
|   `-- ...
|-- #DOC
|   `-- ...
|-- #CTRCT
|   `-- ...
`-- #ABS
    `-- ...
```

StructureTree directory nodes and `directory_child` edges are derived navigation/projection data only. They do not create canonical Entities or Link Properties. Canonical Entity identity remains the leaf authority.

Selecting a topology with `T` does not filter the StructureTree hierarchy. The selection is used by relational `topology` and `mermaid` projections only.

## Relational topology views

`T` exposes the explicit `value.link_type_ref` values found in the loaded CW source. These are canonical relational topologies over the same canonical Nodes.

```text
hierarchy   complete StructureTree navigation hierarchy
topology    selected relation-labelled canonical topology
mermaid     selected canonical topology as Mermaid source
```

## Shell tools

The deterministic shell relation projections remain available directly:

```bash
python3 tools/Topology/cw_topology.py Examples/Ultralight_CMS_CW_Open_Page_v1.4.json --list
python3 tools/Topology/cw_topology.py Examples/Ultralight_CMS_CW_Open_Page_v1.4.json -t dependency
python3 tools/Topology/hierarchy.py Examples/Ultralight_CMS_CW_Open_Page_v1.4.json dependency
```

These legacy shell projections operate on selected canonical Link topology. The TUI `hierarchy` view is the complete StructureTree hierarchy described above.

## Library boundary

```text
tools/Topology/
├── lib/
│   ├── graph.py          CW loading, canonical graph + derived StructureTree graph
│   ├── ascii_walk.py     deterministic ASCII traversal/rendering
│   ├── projection.py     representation-neutral projection result
│   ├── projector.py      host-neutral projection service
│   └── curses_view.py    reusable curses host for line-oriented View modules
├── projections/
│   ├── hierarchy.py      complete StructureTree hierarchy
│   ├── topology.py       selected canonical relation topology
│   └── mermaid.py        selected canonical relation as Mermaid source
├── tui.py                Topology View adapter + CIC workflow
├── cw_topology.py        labelled shell relation projection
├── hierarchy.py          plain shell relation projection
├── __main__.py           curses View entry point
└── README.md
```

`lib/curses_view.py` owns terminal mechanics only: scrolling, key dispatch, modal input/list dialogs, filesystem browsing, status rendering and quit sequencing. It does not know CW or topology semantics.

`TopologyProjector` owns projection state. CIC remains the sole code importer authority; Topology consumes canonical CW only.
