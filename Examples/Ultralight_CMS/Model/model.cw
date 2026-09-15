{
  "format": {
    "contract_format": "CANONICAL_CONTRACT",
    "format_version": "2.5.0"
  },
  "identity": {
    "id": "ULTRALIGHT_CMS_GOLDEN",
    "name": "Ultralight CMS Golden Reference",
    "type": "system_architecture",
    "version": "2.1.0-reference"
  },
  "specification_ref": "LOCAL_FORMAT:Format",
  "status": "unlocked",
  "purpose": "Golden-reference mechanism-only CW package for the self-contained package, NodeType, Event-boundary, Asset, abstraction, documentation and contract model.",
  "entities": [],
  "shards": [
    {
      "entity_ref": "#ABS:UltralightCMS",
      "artifact_ref": "ABS/UltralightCMS.cw"
    },
    {
      "entity_ref": "#ABS:UltralightCMS:RenderPipeline",
      "artifact_ref": "ABS/RenderPipeline.cw"
    },
    {
      "entity_ref": "#CTRCT:UltralightCMS",
      "artifact_ref": "CTRCT/UltralightCMS.cw"
    },
    {
      "entity_ref": "#CTRCT:UltralightCMS:Content",
      "artifact_ref": "CTRCT/UltralightCMS/Content.cw"
    },
    {
      "entity_ref": "#CTRCT:UltralightCMS:PageRequest",
      "artifact_ref": "CTRCT/UltralightCMS/PageRequest.cw"
    },
    {
      "entity_ref": "#CTRCT:UltralightCMS:Style",
      "artifact_ref": "CTRCT/UltralightCMS/Style.cw"
    },
    {
      "entity_ref": "#CTRCT:UltralightCMS:RenderedDocument",
      "artifact_ref": "CTRCT/UltralightCMS/RenderedDocument.cw"
    },
    {
      "entity_ref": "#FILE:index",
      "artifact_ref": "FILE/index.cw"
    },
    {
      "entity_ref": "#FILE:renderer",
      "artifact_ref": "FILE/renderer.cw"
    },
    {
      "entity_ref": "#FILE:content",
      "artifact_ref": "FILE/content.cw"
    },
    {
      "entity_ref": "#FILE:style",
      "artifact_ref": "FILE/style.cw"
    },
    {
      "entity_ref": "#DOC:UltralightCMS:Architecture",
      "artifact_ref": "DOC/UltralightCMS/Architecture.cw"
    },
    {
      "entity_ref": "#DOC:UltralightCMS:Runtime",
      "artifact_ref": "DOC/UltralightCMS/Runtime.cw"
    },
    {
      "entity_ref": "#DOC:UltralightCMS:Package",
      "artifact_ref": "DOC/UltralightCMS/Package.cw"
    },
    {
      "entity_ref": "#DOC:UltralightCMS:Flow",
      "artifact_ref": "DOC/UltralightCMS/Flow.cw"
    }
  ],
  "constraints": {
    "invariants": [
      {
        "id": "GOLDEN_ENTITY_PROPERTY_ONLY",
        "rule": "Canonical semantic truth is represented as Entities and Properties."
      },
      {
        "id": "GOLDEN_PROPERTY_ID_OWNER_LOCAL",
        "rule": "Entity.id is model-global. Property.id is unique only inside its owning Entity; Property canonical address is owner Entity.id plus local Property.id."
      },
      {
        "id": "GOLDEN_MECHANISM_ONLY",
        "rule": "The golden Model describes mechanism, contracts, runtime slot definitions and causal structure only. Runtime/example payload values MUST NOT be canonical Model truth."
      },
      {
        "id": "GOLDEN_DERIVED_READINESS",
        "rule": "Readiness is derived from Data slot state and schema conformance. No parallel *_READY Data truth is permitted."
      },
      {
        "id": "GOLDEN_FALLBACK_INDEX",
        "rule": "Page resolution looks up the requested page by PageContent.id and falls back to id=index. A READY content collection is schema-guaranteed to contain exactly one index item. If that invariant is nevertheless violated at execution time, resolution fails with INVALID_CONTENT_SOURCE rather than writing null forward."
      },
      {
        "id": "GOLDEN_LOOKUP_READY_ONLY",
        "rule": "lookup executes only against READY collections. UNBOUND or INVALID lookup sources are INVALID execution, not a null lookup result."
      },
      {
        "id": "GOLDEN_FUNCTION_INTERFACE_EXACT",
        "rule": "Function input_refs and output_refs describe canonical Properties actually read and written by modeled Function logic. Pure causal relay Functions may declare empty interfaces."
      },
      {
        "id": "GOLDEN_FUNCTION_BOUNDARY",
        "rule": "function_call is permitted only between Functions owned by the same Entity. Cross-Entity behavioral invocation is Event-mediated."
      },
      {
        "id": "GOLDEN_ASSET_CARDINALITY",
        "rule": "Every Entity owns zero or one Asset Property."
      },
      {
        "id": "GOLDEN_ABSTRACTION",
        "rule": "Every Node is an abstraction; ABS is the least opinionated standard family."
      },
      {
        "id": "GOLDEN_OVERLAP",
        "rule": "The same canonical Entity may be a member of multiple abstraction Nodes without duplication."
      },
      {
        "id": "GOLDEN_DEPENDENCY_DIRECTION",
        "rule": "dependency parent_ref is the provider/dependency and child_ref is the dependent/consumer."
      },
      {
        "id": "GOLDEN_SHARD_CLOSURE",
        "rule": "Model/model.cw.shards[] is the authoritative canonical Model closure; every non-root .cw shard is listed exactly once and no listed shard may be missing."
      },
      {
        "id": "GOLDEN_CTRCT_CONTRACTS",
        "rule": "Reusable CMS Schema Properties are owned by CTRCT/schema Entities. Cross-Entity Schema references use explicit {entity_ref, property_ref} addresses; same-owner Schema references may remain bare local ids."
      },
      {
        "id": "GOLDEN_DOC_SCOPE",
        "rule": "DOC semantic scope is defined by members Properties. DOC Assets contain explanatory or presentation payload only and MUST NOT become a second source of canonical model truth."
      }
    ]
  },
  "references": [],
  "gaps": [],
  "prose": {
    "summary": "Normative mechanism-only target fixture for the next CW toolchain generation, including canonical CMS contracts and conversation-derived explanatory DOC Nodes."
  }
}
