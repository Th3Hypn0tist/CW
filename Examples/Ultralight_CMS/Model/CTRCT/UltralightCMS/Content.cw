{
  "id":"#CTRCT:UltralightCMS:Content",
  "name":"Ultralight CMS Content Contract",
  "entity_type_ref":"CTRCT/schema",
  "status":"unlocked",
  "properties":[
    {"id":"MEMBERS::#CTRCT:UltralightCMS:Content","property_type_ref":"members","ruleset_ref":"RULESET_MEMBERS","status":"unlocked","value":{"member_refs":["#FILE:content","#FILE:renderer","#FILE:index"],"properties":{}}},
    {"id":"SCHEMA_PAGE_CONTENT","property_type_ref":"schema","ruleset_ref":"RULESET_SCHEMA","status":"unlocked","value":{"schema_type_ref":"record","definition":{"fields":{"id":{"type":"string","required":true},"title":{"type":"string","required":true},"body":{"type":"string","required":true}}},"properties":{}}},
    {"id":"SCHEMA_CONTENT_COLLECTION","property_type_ref":"schema","ruleset_ref":"RULESET_SCHEMA","status":"unlocked","value":{"schema_type_ref":"list","definition":{"item_schema_ref":"SCHEMA_PAGE_CONTENT","unique_by":"id","required_items":[{"field":"id","value":"index"}]},"properties":{}}}
  ]
}
