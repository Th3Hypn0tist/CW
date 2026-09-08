from __future__ import annotations

from typing import Any, Mapping, Optional

SPEC_IDS = {
    "ccf": "CANONICAL_CONTRACT_FORMAT",
    "nodetypes": "CW_NODETYPES",
    "rulesets": "CW_RULESETS",
}


def classify_spec(data: Mapping[str, Any] | Any) -> Optional[str]:
    """Classify one CW core specification artifact from content only.

    Filenames and paths are intentionally excluded from classification authority.
    """
    if not isinstance(data, Mapping):
        return None
    if data.get("type") == "canonical_contract_format" or data.get("id") == SPEC_IDS["ccf"]:
        return "ccf"
    if data.get("id") == SPEC_IDS["nodetypes"] or (
        isinstance(data.get("nodetypes"), list) and isinstance(data.get("nodetype_schema"), dict)
    ):
        return "nodetypes"
    if data.get("id") == SPEC_IDS["rulesets"] or (
        isinstance(data.get("property_rulesets"), list) and isinstance(data.get("link_rulesets"), list)
    ):
        return "rulesets"
    return None
