{
  "id": "#LOGIC:content",
  "name": "content",
  "entity_type_ref": "LOGIC",
  "status": "unlocked",
  "properties": [
    {
      "id": "ASSET",
      "property_type_ref": "asset",
      "ruleset_ref": "RULESET_ASSET",
      "status": "unlocked",
      "value": {
        "asset_ref": "Assets/LOGIC/%23LOGIC%3Acontent.json",
        "file_type_ref": "json",
        "properties": {}
      }
    },
    {
      "id": "DATA_CONTENT_COLLECTION",
      "property_type_ref": "data",
      "ruleset_ref": "RULESET_DATA",
      "status": "unlocked",
      "value": {
        "data_type_ref": "content_collection",
        "value": null,
        "schema_ref": {
          "entity_ref": "#CTRCT:UltralightCMS:Content",
          "property_ref": "SCHEMA_CONTENT_COLLECTION"
        },
        "properties": {}
      }
    }
  ]
}
