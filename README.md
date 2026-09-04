# AIGM-CW

AIGM Canonical Wireframe (CW) defines a machine-readable canonical architecture model built around the Canonical Contract Format (CCF), CW NodeTypes, and CW Rulesets.

## Validation tools

CW ships with two deliberately separate validation tools under [`linter/`](linter/):

### `cw_spec_lint.py` — validate the standard itself

`cw_spec_lint.py` checks the internal integrity of the active CW specification set:

- Canonical Contract Format (CCF)
- CW NodeTypes
- CW Dependency Rules / Rulesets

It answers:

> Does the CW standard set remain internally coherent with its own declared integrity requirements?

Run locally from the repository root:

```bash
python linter/cw_spec_lint.py --coverage
```

Machine-readable output:

```bash
python linter/cw_spec_lint.py --json
```

### `cw_validate.py` — validate any CW artifact

`cw_validate.py` validates an arbitrary CW artifact against the active locked CW standard.

Input may be either **one JSON file**:

```bash
python linter/cw_validate.py artifact.json
```

or **one directory**:

```bash
python linter/cw_validate.py ./artifact-directory/
```

When a directory is supplied, all `*.json` files below that directory are loaded recursively as one validation set. Canonical references may resolve across those files.

**Filenames, extensions beyond JSON discovery, directory names, paths, and directory structure do not provide semantic meaning.** Canonical identity and semantics are resolved from the JSON content itself.

By default the validator resolves the active standard from the repository root relative to the validator:

```text
Canonical_Contract_Format_v*.json
CanonicalWireframe_NodeTypes_v*.json
CanonicalWireframe_Dependency_Rules_v*.json
```

To validate explicitly against another specification directory:

```bash
python linter/cw_validate.py artifact.json --spec-dir /path/to/specs
```

The validator checks the selected standard with `cw_spec_lint.py` before artifact validation unless that behavior is explicitly disabled by the validator options.

The canonical result classes are:

```text
INVALID_SPECIFICATION
INVALID_MODEL
UNREADY
READY
IMPLEMENTATION_FAILURE
```

Exit codes:

```text
0  READY or UNREADY — canonical model is valid
1  INVALID_MODEL or INVALID_SPECIFICATION
2  IMPLEMENTATION_FAILURE
```

The distinction is intentional:

```text
cw_spec_lint.py   CW standard -> specification integrity
cw_validate.py    CW artifact -> conformance against CW standard
```

See [`linter/README.md`](linter/README.md) for detailed local usage.

---

## Licensing

AIGM-CW follows an **Open Standard, Not Open Use** model.

The canonical specifications may be read and tested freely, but use beyond the free
read/test scope requires an appropriate license.

For the full license terms, see [`LICENSE.md`](LICENSE.md).

### 1. Open Core — Read / Test

**Free**

Includes:

- CCF reading
- CW NodeTypes reading
- CW Rulesets reading
- Editor sandbox mode
- Validator dry-run mode

Does **not** permit:

- Production automation using the CW model
- CI/CD production enforcement using CW validation
- External system integration using CW / Structure capabilities
- Abstraction publication
- Abstraction mounting
- Specification-closure execution in production
- Metamodule Ruleset execution in production automation

> This is an open standard, not open use.

---

### 2. Commercial Use License

**From €50,000 / year / organization**

Required when CW / Structure becomes part of a production system, automation path,
integration layer, runtime, or enforcement mechanism.

Permits, within the licensed organizational and deployment scope:

- CW / Structure use as part of production automation
- CI/CD validation or enforcement
- Integration with external systems
- Automated or unattended validator execution
- Specification-closure execution in production
- Abstraction publication and mounting
- Execution of separately licensed metamodule Rulesets in production systems
- Domain extensions
- Full-feature editor and validator use within the licensed Commercial scope

Does **not** include:

- OEM / white-label rights
- Third-party redistribution or resale rights
- Automatic entitlement to Premium Rulesets not separately licensed

Pricing starts at **€50,000 / year / organization** and has **no fixed upper limit**.
Final pricing depends on deployment scope, organizational scope, licensing requirements,
support requirements, and separately licensed capabilities.

A separate Structure Developer License is **not required in addition to a Commercial Use License**
for users operating within the licensed Commercial scope, unless separately agreed.

---

### 3. Structure Developer License

**€1,200–€3,500 / user / year**

For developers and architects using **Structure** as a development, modeling,
validation, architecture, and code-production tool.

Includes:

- Full-feature Structure editor access
- Full-feature validator access for interactive development use
- Local code refactoring tools
- Spatial 3D canvas write access
- Canonical modeling and architecture work
- Code generation and code-oriented development workflows
- Use of code and other implementation outputs created with Structure in production

**Code created with Structure may be deployed and used in production.**

The licensing boundary is the **CW / Structure model and tooling itself**, not the
code produced with it.

The Structure Developer License does **not** permit the CW / Structure model,
validator, specification closure, or Ruleset execution to become part of production
automation, CI/CD enforcement, a production runtime, an external system integration,
or an unattended production service.

Those uses require a Commercial Use License or OEM License as applicable.

The Structure Developer License also does not grant OEM, white-label,
redistribution, sublicensing, or resale rights.

---

### 4. Premium Rulesets

**€10,000–€150,000 / Ruleset — one-time license fee**

Domain-specific and metamodule Rulesets, for example:

- FinTech
- MedTech
- Cloud Infrastructure
- Industry-specific compliance validation
- Advanced causal traceability

Premium Rulesets are licensed separately unless explicitly included in a written
commercial agreement.

The Premium Ruleset fee is a **one-time license fee**, not an annual subscription.

A Premium Ruleset may be used only within the scope permitted by the holder's
underlying CW / Structure license. Purchasing a Premium Ruleset does not by itself
grant Commercial production-automation, OEM, redistribution, or resale rights.

---

### 5. OEM License

**From €100,000 / year**

For software vendors, platform providers, and tooling vendors that embed,
redistribute, white-label, sublicense, or expose CW / Structure capabilities as part
of a third-party commercial product or service.

An OEM License includes the Commercial Use capabilities required within the
**licensed OEM product scope**, plus the OEM rights expressly granted in the agreement.

May include:

- CW / Structure production use within the licensed OEM product
- Full-feature editor and validator use required for the licensed OEM product
- Specification-closure execution required for the licensed OEM product
- White-label integration
- Embedding CW / Structure capabilities into third-party products
- Product redistribution rights
- Validator-engine sublicensing
- Other negotiated third-party distribution rights

An OEM License does **not** automatically grant unrestricted organization-wide
Commercial Use outside the licensed OEM product or distribution scope.

Unrelated internal organizational use may require a separate Commercial Use scope.

OEM terms are negotiated separately.

---

### 6. Certification

**€15,000–€80,000 / certification**

AIGM-CW Certification is a separate AIGM-CW product and audit service.

It may include:

- Official AIGM-CW compliance certification
- Deterministic architecture audit report
- Workspace readiness verification
- Official AIGM-CW conformance statement or certification mark, where granted

AIGM-CW Certification does **not** include, replace, or imply any separate
AIGMos certification.

A technical `READY` result alone does not constitute official AIGM-CW Certification.

Intended for enterprise, regulated-industry, and public-sector use cases.
