# CW Linters and Validators

CW intentionally contains two different validation tools.

They answer different questions:

```text
cw_spec_lint.py
    Does the CW standard set itself remain internally coherent?

cw_validate.py
    Does this CW artifact conform to the local locked CW standard?
```

Both tools are local-first, use only the Python standard library, and resolve the CW specification directory relative to their own location by default.

## Expected layout

```text
CW/
├── Canonical_Contract_Format_v*.json
├── CanonicalWireframe_NodeTypes_v*.json
├── CanonicalWireframe_Dependency_Rules_v*.json
└── linter/
    ├── cw_spec_lint.py
    ├── cw_validate.py
    └── README.md
```

---

## 1. CW specification integrity linter

`cw_spec_lint.py` validates the **CW specification set itself**: CCF, NodeTypes, and Dependency Rules / Rulesets.

From the repository root:

```bash
python linter/cw_spec_lint.py --coverage
```

Machine-readable output:

```bash
python linter/cw_spec_lint.py --json
```

The default specification directory is always the parent of the `linter` directory:

```text
../
```

The caller's current working directory does not determine which specification files are validated.

To test another specification set explicitly:

```bash
python linter/cw_spec_lint.py --dir /path/to/specs --coverage
```

### Specification-linter exit codes

```text
0  PASS — no specification lint errors
1  FAIL — specification integrity errors found
2  operational failure
```

This tool deliberately does **not** claim to be the complete canonical model/runtime validator described by `CCF.validator.required_operations`.

---

## 2. CW artifact validator

`cw_validate.py` validates arbitrary CW artifacts against the local locked CW standard.

The input may be either **one JSON file** or **one directory**.

### Validate one JSON artifact

```bash
python linter/cw_validate.py ./artifact.json
```

### Validate a directory artifact set

```bash
python linter/cw_validate.py ./artifact-directory/
```

Directory input is treated as one validation set. All `*.json` files below the directory are loaded recursively, and canonical references may resolve across those files.

**Filenames, directory names, file extensions beyond JSON discovery, and directory structure never provide canonical semantics.** Identity and semantic resolution come from explicit structured CW data.

Machine-readable output:

```bash
python linter/cw_validate.py ./artifact-directory/ --json
```

To validate against another explicitly supplied CW specification directory:

```bash
python linter/cw_validate.py ./artifact.json --spec-dir /path/to/specs
```

By default `cw_validate.py` first runs `cw_spec_lint.py` against the selected CW standard. An invalid standard therefore cannot silently be used as validation authority.

For isolated debugging only, that pre-check may be skipped explicitly:

```bash
python linter/cw_validate.py ./artifact.json --skip-spec-lint
```

### Artifact-validator result classes

The validator reports canonical result classes rather than a generic boolean:

```text
INVALID_SPECIFICATION
INVALID_MODEL
UNREADY
READY
IMPLEMENTATION_FAILURE
```

At the command-line level:

```text
0  READY or UNREADY — canonical model is structurally valid
1  INVALID_MODEL or INVALID_SPECIFICATION
2  IMPLEMENTATION_FAILURE
```

`UNREADY` is not treated as invalid. It means the model is valid but one or more explicitly modeled requirements or references remain unresolved.

### Current validation surface

The artifact validator currently checks, among other things:

- CCF contract shape and required top-level fields;
- contract format and format version against the selected local CCF contract;
- canonical Entity and Property identity uniqueness across a multi-file input set;
- Entity required fields;
- NodeType resolution and inherited NodeType requirements;
- required Property types and Property cardinalities;
- Property type to Ruleset resolution;
- `ruleset_ref` agreement with the governing Property/Link Ruleset;
- Property `value_schema` required fields and basic declared value types;
- Link type resolution;
- Link endpoint resolution and explicit endpoint constraints;
- Ruleset reference-compatibility constraints;
- explicit Required Link satisfaction through `required_link_ref`;
- top-level reference resolution against the artifact set or local CW standard;
- unresolved canonical references as `UNREADY` rather than guessed semantics.

The validator does not infer semantics from names, paths, geometry, source-code proximity, visual placement, or other non-canonical signals.

---

## Local-first rule

Both executables work without GitHub Actions and without third-party Python packages.

CI may invoke the same executables, but CI is only an execution environment. It is not part of CW validation semantics.
