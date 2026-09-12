from __future__ import annotations

from typing import Any


class CICProfileError(ValueError):
    pass


_PROFILES: dict[str, dict[str, Any]] = {
    "aigmos": {
        "event_rules": [
            {
                "rule_id": "AIGMOS_COMMANDDEF_HANDLER",
                "language_id": "python",
                "evidence_kind": "registration_handler",
                "evidence_value": "CommandDef",
                "event_type_ref": "command",
            }
        ]
    }
}


def list_profiles() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES))


def profile_options(name: str | None) -> dict[str, Any]:
    if name is None:
        return {}
    clean = str(name).strip().lower()
    if not clean:
        return {}
    profile = _PROFILES.get(clean)
    if profile is None:
        raise CICProfileError(f"unknown CIC profile: {name!r}; available: {', '.join(list_profiles())}")
    return {
        "event_rules": [dict(item) for item in profile.get("event_rules", [])],
    }
