# CW Linters and Validators

CW has two primary semantic validation entry points:

```text
cw_spec_lint.py
    Is the selected specification set internally coherent?

cw_validate.py
    Does this CW canonical artifact conform to the selected specification set?
```

Both primary tools are local-first and use only the Python standard library. The same package also contains composition, specification binding, package validation, version-stamp validation, and specialized Event/Effect/dispatch validators.

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
spec_sets/CW_CORE_v1.2.0.json
```

Current default bundle:

```text
CCF        2.5.0
NodeTypes  1.18.0
Rulesets   4.0.0
```

The previous immutable `spec_sets/CW_CORE_v1.1.0.json` bundle remains preserved for historical interpretation and regression testing. Older preserved specification material remains under `History/`. Immutable historical bundles are not rewritten in place.

The manifest may pin each file with its Git blob SHA. This makes the selected interpretation content explicit and immutable.

### Default

```bash
python linter/cw_spec_lint.py --coverage
python linter/cw_validate.py artifact.json
```

Both commands search upward from the tool location and prefer `spec_sets/CW_CORE_v1.2.0.json`.

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

For CW Core 1.2:

```text
code     -> inherited links + functions + events + required_links + data + effects + representation
abs      -> inherited links
DOC      -> inherited links + representation
contract -> inherited links + members
```

`contract.members` is an Entity-root field interpreted by `RULESET_NODE`. It declares explicit normative Contract scope. Implementation-side Contract affiliation is a separate Link claim.

## Links

Links are the universal relational navigation mechanism.

The selected Rulesets may provide one open generic Link Ruleset. With that rule selected by `Property.ruleset_ref`, an explicit relation selector can be read and preserved without requiring a dedicated Ruleset for every possible relation label.

The generic Link selector model distinguishes two explicit forms:

```text
#ABS:Runtime
```

A leading `#` means the selector is a canonical topology identity reference. The referenced topology Entity must resolve, and `parent_ref -> child_ref` expresses hierarchy only inside that topology.

```text
ABS:Runtime:dependency
```

Without a leading `#`, the selector is an open literal relation name. It is preserved exactly and no canonical identity is inferred from its prefix.

Topology hierarchy does not imply dependency, causality, ownership, authority, containment or implementation semantics. Those remain independent specialized Links when required.

The same canonical Node may participate in multiple overlapping topology hierarchies without duplication.

Specialized Link Rulesets remain valid when additional semantics are required, for example Event causality, Function calls or implementation-side Contract affiliation.

`contract_affiliation` is directed:

```text
#FILE implementation -> #CTRCT contract
```

It states that an implementation FILE affiliates itself with the Contract as a whole. It does not silently add that FILE to `CTRCT.members`.

This distinction is intentional:

```text
CTRCT.members        = declared normative Contract scope
contract_affiliation = implementation-side affiliation
```

Both claims can be queried independently without duplicate truth.

This means:

```text
StructureTree = hierarchical navigation
Links         = relational navigation + explicit topology hierarchy
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

The current artifact validator additionally validates:

- `contract.members` is an array of unique canonical refs.
- unresolved member refs remain `UNREADY` rather than being guessed.
- a generic `RULESET_LINK` selector beginning with `#` resolves a canonical topology Entity.
- a resolved topology selector must be compatible with the `topology_entity` NodeType family.
- literal relation selectors without `#` are not identity-resolved.

## CW Core 1.2 identity and reference model

The current default specification set explicitly uses:

```text
model-global Entity identity
owner-local Property identity
explicit cross-Entity Property addresses
Event-mediated cross-Entity Function boundaries
```

Entity ids therefore remain model-global, while Property ids are local to their owning Entity. A cross-Entity Property reference must identify both owner and Property explicitly:

```json
{
  "entity_ref": "#FILE:example",
  "property_ref": "FUNCTION::render"
}
```

A consumer must not recover Property ownership from filenames, paths, naming conventions, geometry, source proximity, or another heuristic.

Cross-Entity Function behavior is likewise not represented as an implicit direct Function-to-Function shortcut across Node ownership. The selected Rulesets keep that boundary Event-mediated and explicit.

## Composition, binding and package validation

The linter package also contains these supporting modules:

```text
cw_compose.py             compose explicitly sharded CW for validation
cw_bind.py                bind one imported candidate to an immutable specification_ref
cw_version.py             validate optional Node timestamp/hash version stamps
cw_condition_validate.py  validate structured Event condition semantics
cw_effect_validate.py     validate Effect semantics
cw_dispatch_validate.py   validate and resolve explicit Event dispatch semantics
cw_package_validate.py    validate the self-contained CW package form
```

`cw_compose.py` changes storage representation only. It does not create new canonical identity or semantic authority.

`cw_bind.py` changes only the root `specification_ref`. It refuses silent rebinding to a different evaluation context.

The package validator is run separately:

```bash
python linter/cw_package_validate.py /path/to/package
python linter/cw_package_validate.py /path/to/package --json
```

It validates the package-local format/model closure, including `Format/`, `Model/`, NodeType family files, shards, owner-local Property references, Event/Effect semantics, Required Links, and Assets. Package validation is a separate package contract; it does not replace the generic `cw_spec_lint.py` + `cw_validate.py` model.

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
