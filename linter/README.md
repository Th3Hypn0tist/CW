# CW Linters and Validators

CW has two separate validation tools:

```text
cw_spec_lint.py
    Is the selected specification set internally coherent?

cw_validate.py
    Does this CW canonical artifact conform to the selected specification set?
```

Both tools are local-first and use only the Python standard library.

The key boundary is:

> **Importers produce CW only. NodeTypes and Rulesets are selected after import.**

The validator does not contain a fixed code, UML, business, or other domain vocabulary. A compatible NodeTypes/Rulesets pair can be added or replaced without changing the CW import format or the validator implementation.

## Specification sets

A specification set binds exactly these roles:

```text
CCF
NodeTypes
Rulesets
```

The repository default is pinned by:

```text
spec_sets/CW_CORE.json
```

The manifest may pin each file with its Git blob SHA. This makes the selected interpretation content explicit and immutable.

### Default

```bash
python linter/cw_spec_lint.py --coverage
python linter/cw_validate.py artifact.json
```

Both commands search upward from the tool location and prefer `spec_sets/CW_CORE.json`.

### Explicit specification-set manifest

```bash
python linter/cw_spec_lint.py --spec-set /path/to/UML_SPEC_SET.json --coverage
python linter/cw_validate.py artifact.json --spec-set /path/to/UML_SPEC_SET.json
```

### Explicit three-file selection

```bash
python linter/cw_spec_lint.py \
  --ccf Canonical_Contract_Format.json \
  --nodetypes UML_NodeTypes.json \
  --rulesets UML_Rulesets.json

python linter/cw_validate.py artifact.json \
  --ccf Canonical_Contract_Format.json \
  --nodetypes UML_NodeTypes.json \
  --rulesets UML_Rulesets.json
```

### Legacy directory selection

A directory containing exactly one CCF, one NodeTypes artifact and one Rulesets artifact is still supported:

```bash
python linter/cw_spec_lint.py --dir /path/to/specs
python linter/cw_validate.py artifact.json --spec-dir /path/to/specs
```

Directory discovery is compatibility behavior, not semantic authority. Ambiguous directories fail rather than using a latest-version rule.

## `RULESET_NODE`

`RULESET_NODE` governs the Node root itself.

```text
NodeType
    defines what semantic sections the Node has available to present

RULESET_NODE.section_readers
    defines how those sections are read from canonical CW data
```

The linter checks this contract generically. It does not hardcode the concrete section vocabulary.

For the CW Core set, a code Node exposes sections such as Functions, Events and Required Links. ABS, DOC and Contract Nodes do not inherit those code-only sections.

## Links

Links are the universal relational navigation mechanism.

The selected Rulesets may provide one open generic Link Ruleset. With that rule selected by `Property.ruleset_ref`, an explicit relation value can be read and preserved without requiring a dedicated Ruleset for every possible relation label.

Specialized Link Rulesets remain valid when additional semantics are required, for example Event causality or Function calls.

This means:

```text
StructureTree = hierarchical navigation
Links         = relational navigation
```

Both navigate the same canonical identities.

## UML or another domain

A UML specification is not a different import format. A producer still emits CW canonical data.

A UML test therefore becomes:

```text
source
  -> importer
  -> CW canonical model
  -> UML specification set
  -> cw_spec_lint / cw_validate
```

A UML NodeTypes registry may declare UML NodeTypes and available sections, while its Rulesets define how those sections are read. The same validation executable is used unchanged.

## Specification-linter result

```text
0  PASS
1  specification integrity failure
2  operational failure
```

`--json` emits machine-readable output. `--coverage` reports the generic validation surface and confirms that concrete NodeType/domain Link vocabularies are not hardcoded.

## Artifact-validator results

```text
INVALID_SPECIFICATION
INVALID_MODEL
UNREADY
READY
IMPLEMENTATION_FAILURE
```

CLI exit codes:

```text
0  READY or UNREADY
1  INVALID_MODEL or INVALID_SPECIFICATION
2  IMPLEMENTATION_FAILURE
```

`UNREADY != INVALID_MODEL`.

The validator first self-lints the selected specification set unless `--skip-spec-lint` is supplied for isolated debugging.

## Canonical boundaries

The tools do not infer semantics from filenames, paths, directory placement, renderer geometry, colors, names, source-code proximity, or a “latest” registry.

The authority chain is:

```text
CW canonical data
  + explicitly selected specification set
    -> NodeTypes: what exists to present
    -> Rulesets: how it is read
  -> derived StructureTree / Links / renderer projections
```

No projection becomes a second source of truth.
