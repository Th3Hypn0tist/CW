# Topology

Deterministic shell projection of explicit canonical CW Link topologies.

The tool reads canonical Link Properties and filters only by explicit `value.link_type_ref` values. It does not infer topology or relation semantics from names, paths, filenames, geometry, or rendering.

```bash
python3 -m tools.Topology Examples/Ultralight_CMS_CW_Open_Page_v1.4.json --list
python3 -m tools.Topology Examples/Ultralight_CMS_CW_Open_Page_v1.4.json -t dependency
python3 -m tools.Topology Examples/Ultralight_CMS_CW_Open_Page_v1.4.json -t event_input,event_read,event_effect,effect_target
python3 -m tools.Topology Examples/Ultralight_CMS_CW_Open_Page_v1.4.json --all
```

Options:

- `--list` lists explicit relation selectors and counts.
- `-t`, `--topology`, `-r`, `--relation` selects one or more explicit relation selectors.
- `--all` prints each explicit relation selector as a separate ASCII topology.
- `--link-ids` includes canonical Link Property ids.
- `--names` appends explicit Node names while keeping canonical ids primary.
