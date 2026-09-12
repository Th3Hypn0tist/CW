{
  "format":{"contract_format":"CANONICAL_CONTRACT","format_version":"2.4.3"},
  "identity":{"id":"ULTRALIGHT_CMS_GOLDEN","name":"Ultralight CMS Golden Reference","type":"system_architecture","version":"2.0.3-reference"},
  "specification_ref":"LOCAL_FORMAT:../Format",
  "status":"unlocked",
  "purpose":"Golden-reference mechanism-only CW package for the self-contained package, NodeType, Event-boundary, Asset and abstraction model.",
  "entities":[],
  "shards":[
    {"entity_ref":"#ABS:UltralightCMS","artifact_ref":"ABS/UltralightCMS.cw"},
    {"entity_ref":"#ABS:UltralightCMS:RenderPipeline","artifact_ref":"ABS/RenderPipeline.cw"},
    {"entity_ref":"#FILE:index","artifact_ref":"FILE/index.cw"},
    {"entity_ref":"#FILE:renderer","artifact_ref":"FILE/renderer.cw"},
    {"entity_ref":"#FILE:content","artifact_ref":"FILE/content.cw"},
    {"entity_ref":"#FILE:style","artifact_ref":"FILE/style.cw"},
    {"entity_ref":"#DOC:UltralightCMS:Flow","artifact_ref":"DOC/UltralightCMS/Flow.cw"}
  ],
  "constraints":{"invariants":[
    {"id":"GOLDEN_ENTITY_PROPERTY_ONLY","rule":"Canonical semantic truth is represented as Entities and Properties."},
    {"id":"GOLDEN_PROPERTY_ID_GLOBAL","rule":"Every active Property.id is unique across the complete Model closure and every bare Property reference resolves by exact package-global Property.id."},
    {"id":"GOLDEN_MECHANISM_ONLY","rule":"The golden Model describes mechanism, contracts, runtime slot definitions and causal structure only. Runtime/example payload values MUST NOT be canonical Model truth."},
    {"id":"GOLDEN_DERIVED_READINESS","rule":"Readiness is derived from Data slot state and schema conformance. No parallel *_READY Data truth is permitted."},
    {"id":"GOLDEN_FALLBACK_INDEX","rule":"Page resolution looks up the requested page by PageContent.id and falls back to id=index. A READY content collection is schema-guaranteed to contain exactly one index item."},
    {"id":"GOLDEN_NO_FUNCTION_CALL","rule":"No function_call Link or logic call primitive exists."},
    {"id":"GOLDEN_ASSET_CARDINALITY","rule":"Every Entity owns zero or one Asset Property."},
    {"id":"GOLDEN_ABSTRACTION","rule":"Every Node is an abstraction; ABS is the least opinionated standard family."},
    {"id":"GOLDEN_OVERLAP","rule":"The same canonical Entity may be a member of multiple abstraction Nodes without duplication."},
    {"id":"GOLDEN_DEPENDENCY_DIRECTION","rule":"dependency parent_ref is the provider/dependency and child_ref is the dependent/consumer."},
    {"id":"GOLDEN_SHARD_CLOSURE","rule":"Model/model.cw.shards[] is the authoritative canonical Model closure; every non-root .cw shard is listed exactly once and no listed shard may be missing."}
  ]},
  "references":[],
  "gaps":[],
  "prose":{"summary":"Normative mechanism-only target fixture for the next CW toolchain generation."}
}
