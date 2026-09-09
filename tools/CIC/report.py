from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .cw import file_refs, filetree, links, load_cw, validate_cw

REPORT_VERSION="1.2"


def build_cw_report(document: dict[str, Any], *, source: str | None = None) -> dict[str, Any]:
    validate_cw(document)
    entities=[e for e in document.get("entities",[]) if isinstance(e,dict)]; properties=[(e.get("id"),p) for e in entities for p in e.get("properties",[]) if isinstance(p,dict)]
    entity_types=Counter(str(e.get("entity_type_ref") or "<missing>") for e in entities); property_types=Counter(str(p.get("property_type_ref") or "<missing>") for _,p in properties); rulesets=Counter(str(p.get("ruleset_ref") or "<missing>") for _,p in properties)
    refs=file_refs(document); filetree(document) if refs else None; link_records=links(document); link_types=Counter(str(item.get("link_type_ref") or "<missing>") for item in link_records)
    gaps=list(document.get("gaps",[])) if isinstance(document.get("gaps"),list) else []; unresolved=[]
    for entity in entities:
        if str(entity.get("status","")).lower() in {"unresolved","unsolved","invalid"}: unresolved.append(entity.get("id"))
        for prop in entity.get("properties",[]):
            if isinstance(prop,dict) and str(prop.get("status","")).lower() in {"unresolved","unsolved","invalid"}: unresolved.append(prop.get("id"))
    verdict="UNSOLVED" if gaps or unresolved else "PASS"
    return {"report_version":REPORT_VERSION,"source":source,"verdict":verdict,"document":{"identity_id":document.get("identity",{}).get("id") if isinstance(document.get("identity"),dict) else None,"status":document.get("status"),"specification_ref":document.get("specification_ref")},"integrity":{"status":"PASS","validator":"CIC.validate_cw"},"entities":{"total":len(entities),"by_type":dict(sorted(entity_types.items())),"file_entities":len(refs)},"properties":{"total":len(properties),"by_type":dict(sorted(property_types.items())),"by_ruleset":dict(sorted(rulesets.items()))},"links":{"total":len(link_records),"by_type":dict(sorted(link_types.items()))},"unresolved":{"explicit_gap_count":len(gaps),"explicit_gaps":gaps,"status_refs":sorted(str(ref) for ref in unresolved)},"issues":[] if verdict=="PASS" else [{"kind":"UNRESOLVED","severity":"UNSOLVED"}]}


def report_cw(path: str | Path) -> dict[str, Any]:
    candidate=Path(path); return build_cw_report(load_cw(candidate),source=str(candidate))


def format_cw_report(report: dict[str, Any]) -> str:
    return "\n".join(["CW REPORT","=========",f"Source: {report.get('source') or '<memory>'}",f"VERDICT: {report['verdict']}","",f"Entities: {report['entities']['total']}",f"Properties: {report['properties']['total']}",f"Links: {report['links']['total']}",f"#FILE: {report['entities']['file_entities']}","",f"VERDICT: {report['verdict']}"])
