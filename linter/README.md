# CW Specification Linter

`cw_spec_lint.py` is the local and CI specification-integrity linter for the CanonicalWireframe specification set.

It has no third-party Python dependencies.

## Expected layout

```text
CW/
├── Canonical_Contract_Format_v*.json
├── CanonicalWireframe_NodeTypes_v*.json
├── CanonicalWireframe_Dependency_Rules_v*.json
└── linter/
    ├── cw_spec_lint.py
    └── README.md
```

The linter resolves the specification directory relative to its own file location.

In other words, the default specification directory is always:

```text
../
```

from `linter/cw_spec_lint.py`.

The current working directory does not determine which specification files are validated.
Artifact discovery is content-based and version-independent.

## Local use

From the repository root:

```bash
python linter/cw_spec_lint.py
```

With integrity coverage:

```bash
python linter/cw_spec_lint.py --coverage
```

Machine-readable output:

```bash
python linter/cw_spec_lint.py --json
```

You can also run it while your shell is inside the `linter` directory:

```bash
python cw_spec_lint.py --coverage
```

Or from an unrelated current working directory by using the script path:

```bash
python /path/to/CW/linter/cw_spec_lint.py --coverage
```

All three forms validate the same parent specification directory.

## Explicit specification directory

For testing another specification set, override the default directory explicitly:

```bash
python linter/cw_spec_lint.py --dir /path/to/specs --coverage
```

`--dir` is an explicit override. Without it, the linter always uses the parent of the `linter` directory.

## Exit codes

```text
0  PASS — no specification lint errors
1  FAIL — specification integrity errors found
2  operational failure
```

This makes the same executable suitable for:

- manual local validation;
- editor/tool integration;
- pre-commit or other local hooks;
- CI/CD gates;
- scripted validation pipelines.

## Scope

This linter validates the **CW specification set itself**: CCF, NodeTypes, and Dependency Rules / Rulesets.

It is deliberately separate from the complete canonical model/runtime validator described by `CCF.validator.required_operations`.

A linter PASS means the scanned specification set satisfies the integrity checks implemented by this linter, including coverage of the mandatory `specification_integrity_checks` declared by the active Rulesets artifact.
