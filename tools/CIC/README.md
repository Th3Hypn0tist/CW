# CIC

`CW/tools/CIC/` is the authoritative CIC source.

CIC is the code-to-CW ingress pipeline. It extracts implementation evidence, projects canonical `#FILE` Entities and Properties, materializes a self-contained CW package, validates that package against its own local `Format/` closure, versions changed Nodes, and publishes the result transactionally.

## Authority boundary

CIC owns:

- deterministic source acquisition,
- parser/evidence extraction,
- canonical `#FILE` identity projection,
- source Asset materialization,
- exact local import dependency projection,
- Event materialization only from validated trigger evidence,
- package construction,
- transactional create/update,
- Node version stamping.

CIC does **not** own CW semantics. The generated package carries its semantic authority under `Format/`.

The current package shape is:

```text
<CW package>/
├── Format/
│   ├── CW.json
│   ├── CCF.json
│   ├── DR.json
│   └── NodeTypes/**/*.cwn
├── Model/
│   ├── model.cw
│   └── FILE/**/*.cw
├── Assets/
│   └── FILE/<percent-encoded-Entity.id>.<source-extension>
└── Diagnostics/
    └── import.ir.json
```

`Diagnostics/` is non-canonical parser/evidence material. It is not part of the Model closure.

## Public import gate

The public importer runs this order:

```text
validate CIC + package tooling
  -> validate the current golden package
  -> parse source into non-canonical evidence IR
  -> serialize parser-stage FILE shards
  -> copy the selected package-local Format closure
  -> move canonical shards under Model/
  -> copy each imported source file as its owning #FILE Entity Asset
  -> promote exactly resolved internal imports to dependency Links
  -> validate the self-contained package
  -> timestamp/hash changed or new Nodes
  -> reverse-verify Node hashes
  -> validate the package again
  -> atomically expose the target package
```

A failure at any validation, version, or publish step leaves the previous target untouched.

## Canonical source mapping

One imported source file maps to one language-agnostic `#FILE` Entity.

Examples:

```text
foo/bar.py       -> #FILE:foo:bar
web/app.js       -> #FILE:web:app
schema.v1.json   -> #FILE:schema.v1
```

Only the final source-format suffix is removed from canonical identity. The original physical source file is retained as the Node's one opaque Asset.

The canonical shard path remains language-independent:

```text
Model/FILE/foo/bar.cw
```

while the Asset preserves the source payload format:

```text
Assets/FILE/%23FILE%3Afoo%3Abar.py
```

If two source files collapse to the same canonical `#FILE` identity, import fails. CIC does not invent a disambiguation rule.

## Structural dependencies

Exactly resolved internal implementation imports project to canonical `dependency` Links:

```text
provider/dependency -> dependent/consumer
```

Therefore:

```text
parent_ref = imported provider
child_ref  = importing consumer
```

The consumer Entity owns the Link Property because it declares the dependency. Import dependency does not imply execution causality.

Unresolved or external imports remain evidence in `Diagnostics/import.ir.json`; CIC does not fabricate canonical external Entities.

## Functions and Events

Functions and methods remain Properties of their owning `#FILE` Entity. CIC does not create Function Entities.

Source-level call evidence remains parser evidence unless a separate canonical mapping is explicitly justified. CIC never emits `function_call` Links or a `call` logic primitive.

Events are materialized only from validated trigger evidence. An external trigger may produce:

```text
Event -> event_handler -> Function
```

A Function-to-Function canonical boundary must remain Event-mediated according to the package-local DR semantics.

## Assets

Each imported `#FILE` Entity owns exactly one Asset containing the original source bytes.

CIC may extend the copied, still-unlocked package-local `DR.json.asset_file_types` registry when the source tree contains an extension not already registered. It does not modify CCF and it does not inspect Asset payload semantics during package validation.

Asset byte changes count as Node version changes even when the parsed canonical Property structure remains otherwise identical.

## Package-local Format

The current default Format template is:

```text
Examples/Ultralight_CMS/Format/
```

It is copied into every generated package. An alternate template may be supplied explicitly with `--format-template` or the Python `format_template=` argument.

`spec_set` remains accepted temporarily as a compatibility argument, but it is not semantic authority for the new pipeline. Generated packages bind:

```text
specification_ref = LOCAL_FORMAT:Format
```

## Node version

```text
id        = persistent canonical Node identity
timestamp = YYYYMMDDhhmmss UTC chronological version order
hash      = lowercase MD5 version checksum
```

Hash generation is over deterministic direct Entity shard serialization with `hash` temporarily set to `""`.

MD5 here is a fast version checksum, not security or identity authority.

An unchanged Node preserves its previous timestamp/hash during `--force`. A change in either canonical Entity payload or owned Asset bytes produces a new Node version.

## Local release gate

From repository root:

```bash
python -m tools.CIC release-check
```

The gate:

1. compiles CIC and the package validator,
2. validates `Examples/Ultralight_CMS` as the current golden package,
3. runs a full source -> package -> validate -> version -> reverse-verify selftest,
4. runs the CIC regression suite,
5. rejects old duplicate CIC implementations/imports.

Useful lower-level commands:

```bash
python -m tools.CIC validate-tools
python -m tools.CIC selftest
python -m tools.CIC import <source-folder> <package-folder>
python -m tools.CIC import <source-folder> <package-folder> --force
python linter/cw_package_validate.py <package-folder> --json
```

## SSOT

**One truth. Many topologies. No duplicate truth.**

The parser IR is evidence. The generated `Model/` is canonical semantic structure. `Assets/` hold opaque physical payloads. `Format/` defines how the package is interpreted.
