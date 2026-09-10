# Topology

Interactive and shell views over explicit canonical CW Link topologies.

The implementation is split into reusable library code and View hosts. Canonical topology semantics are read only from explicit CW content. Names, paths, filenames, geometry and rendering do not become semantic authority.

## Interactive View

Launch the curses View with a CW artifact or folder:

```bash
python3 -m tools.Topology Examples/Ultralight_CMS_CW_Open_Page_v1.4.json
```

Keymap:

```text
Up / Down   scroll
O           open CW source dialog
T           topology / view selection
E           export current view to .md
Q Q Q       quit
```

`T` exposes the explicit `value.link_type_ref` values found in the loaded CW source and the available presentation modes:

```text
hierarchy   plain parent/child hierarchy
topology    relation-labelled topology
```

## Shell tools

The original deterministic shell projections remain available directly:

```bash
python3 tools/Topology/cw_topology.py Examples/Ultralight_CMS_CW_Open_Page_v1.4.json --list
python3 tools/Topology/cw_topology.py Examples/Ultralight_CMS_CW_Open_Page_v1.4.json -t dependency
python3 tools/Topology/hierarchy.py Examples/Ultralight_CMS_CW_Open_Page_v1.4.json dependency
```

## Library boundary

```text
tools/Topology/
├── lib/
│   ├── graph.py          CW loading + Node/Edge graph collection
│   ├── ascii_walk.py     deterministic ASCII traversal/rendering
│   └── curses_view.py    reusable curses host for line-oriented View modules
├── tui.py                Topology View adapter
├── cw_topology.py        labelled shell projection
├── hierarchy.py          plain shell projection
├── __main__.py           curses View entry point
└── README.md
```

`lib/curses_view.py` owns terminal mechanics only: scrolling, key dispatch, modal input/list dialogs, status rendering and quit sequencing. It does not know CW or topology semantics.

`TopologyView` in `tui.py` owns the CW-specific View state and adapts canonical topology data to the generic curses host. This separation is intentional so the curses host can later be reused by AIGMos View modules without making curses or Topology semantic authority.
