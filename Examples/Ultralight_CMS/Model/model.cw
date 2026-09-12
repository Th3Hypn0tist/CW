{
  "format":{"contract_format":"CANONICAL_CONTRACT","format_version":"2.4.3"},
  "identity":{"id":"ULTRALIGHT_CMS_GOLDEN","name":"Ultralight CMS Golden Reference","type":"system_architecture","version":"2.0.2-reference"},
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
    {"id":"GOLDEN_MECHANISM_ONLY","rule":"The golden Model describes mechanism, contracts, ports, state slots and causal structure only. Runtime/example input and content payload values MUST NOT be canonical Model truth. Runtime Data slots start null unless a mechanism-defined initial state is required. Example payload values may exist only in opaque Assets/."},
    {"id":"GOLDEN_NO_FUNCTION_CALL","rule":"No function_call Link or logic call primitive exists."},
    {"id":"GOLDEN_ASSET_CARDINALITY","rule":"Every Entity owns zero or one Asset Property."},
    {"id":"GOLDEN_ABSTRACTION","rule":"Every Node is an abstraction; ABS is the least opinionated standard family."},
    {"id":"GOLDEN_OVERLAP","rule":"The same canonical Entity may be a member of multiple abstraction Nodes without duplication."},
    {"id":"GOLDEN_DEPENDENCY_DIRECTION","rule":"dependency parent_ref is the provider/dependency and child_ref is the dependent/consumer."},
    {"id":"GOLDEN_SUCCESS_AND_FAILURE","rule":"The mechanism contains explicit success and content-not-found failure branches without requiring pre-populated fixture requests or content in Model/."}
  ]},
  "references":[],
  "gaps":[],
  "prose":{"summary":"Normative mechanism-only target fixture for the next CW toolchain generation."}
}
