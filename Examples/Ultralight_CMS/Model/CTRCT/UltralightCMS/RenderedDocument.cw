{
  "id":"#CTRCT:UltralightCMS:RenderedDocument",
  "name":"Ultralight CMS Rendered Document Contract",
  "entity_type_ref":"CTRCT/schema",
  "status":"unlocked",
  "properties":[
    {"id":"MEMBERS::#CTRCT:UltralightCMS:RenderedDocument","property_type_ref":"members","ruleset_ref":"RULESET_MEMBERS","status":"unlocked","value":{"member_refs":["#FILE:index","#FILE:renderer"],"properties":{}}},
    {"id":"SCHEMA_RENDERED_DOCUMENT","property_type_ref":"schema","ruleset_ref":"RULESET_SCHEMA","status":"unlocked","value":{"schema_type_ref":"record","definition":{"fields":{"content":{"schema_ref":"SCHEMA_PAGE_CONTENT","required":true},"style":{"schema_ref":"SCHEMA_STYLE_SHEET","required":true},"status":{"type":"string","required":true,"allowed_values":["draft","published"]}}},"properties":{}}}
  ]
}
