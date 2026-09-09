from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class LinkCompletenessError(ValueError):
    pass


@dataclass(frozen=True)
class ObligationVerdict:
    obligation_id: str
    required: bool
    state: str
    matched_link_ids: tuple[str, ...]
    candidate_link_ids: tuple[str, ...]
    min_count: int
    max_count: int | None
    actual_count: int
    reason: str | None = None


@dataclass(frozen=True)
class LinkCompletenessResult:
    state: str
    obligations: tuple[ObligationVerdict, ...]

    @property
    def solved(self) -> bool:
        return self.state == "SOLVED"


_VALID_RESOLUTION = {"RESOLVED", "UNRESOLVED", "INVALID"}


def _text(record: dict[str, Any], key: str, *, required: bool = True) -> str | None:
    value = record.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise LinkCompletenessError(f"{key} must be a non-empty string")
    return value


def _obligation(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LinkCompletenessError("link obligation must be an object")
    min_count = record.get("min_count", 1 if record.get("required", True) else 0)
    max_count = record.get("max_count")
    if not isinstance(min_count, int) or min_count < 0:
        raise LinkCompletenessError("min_count must be a non-negative integer")
    if max_count is not None and (not isinstance(max_count, int) or max_count < min_count):
        raise LinkCompletenessError("max_count must be null or an integer >= min_count")
    required = record.get("required", True)
    if not isinstance(required, bool):
        raise LinkCompletenessError("required must be boolean")
    return {
        "obligation_id": _text(record, "obligation_id"),
        "required": required,
        "link_type_ref": _text(record, "link_type_ref"),
        "parent_ref": _text(record, "parent_ref"),
        "child_ref": _text(record, "child_ref", required=False),
        "min_count": min_count,
        "max_count": max_count,
    }


def _link(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LinkCompletenessError("link evidence must be an object")
    status = record.get("resolution_status", "RESOLVED")
    if status not in _VALID_RESOLUTION:
        raise LinkCompletenessError(f"invalid resolution_status: {status!r}")
    obligation_refs = record.get("obligation_refs", [])
    if not isinstance(obligation_refs, list) or any(not isinstance(item, str) or not item for item in obligation_refs):
        raise LinkCompletenessError("obligation_refs must be an array of non-empty strings")
    return {
        "link_id": _text(record, "link_id"),
        "link_type_ref": _text(record, "link_type_ref"),
        "parent_ref": _text(record, "parent_ref", required=False),
        "child_ref": _text(record, "child_ref", required=False),
        "resolution_status": status,
        "obligation_refs": tuple(obligation_refs),
    }


def _shape_matches(obligation: dict[str, Any], link: dict[str, Any]) -> bool:
    if link["link_type_ref"] != obligation["link_type_ref"]:
        return False
    if link["parent_ref"] != obligation["parent_ref"]:
        return False
    expected_child = obligation["child_ref"]
    if expected_child is not None and link["child_ref"] != expected_child:
        return False
    return link["child_ref"] is not None


def _semantic_key(link: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return (link["link_type_ref"], link["parent_ref"], link["child_ref"])


def evaluate_required_links(
    obligations: Iterable[dict[str, Any]],
    links: Iterable[dict[str, Any]],
) -> LinkCompletenessResult:
    """Evaluate explicit link obligations against explicit implementation evidence.

    This evaluator does not discover obligations and does not infer candidate
    intent from name similarity. A malformed/unresolved candidate is attributed
    to an obligation only through an explicit `obligation_refs` evidence field.
    Exact resolved links may satisfy an obligation without that attribution.

    Duplicate semantically identical links count once. Optional obligations never
    make the aggregate result UNSOLVED. One unmet required obligation does.
    """
    normalized_obligations = [_obligation(item) for item in obligations]
    normalized_links = [_link(item) for item in links]

    ids = [item["obligation_id"] for item in normalized_obligations]
    if len(ids) != len(set(ids)):
        raise LinkCompletenessError("duplicate obligation_id")
    known_ids = set(ids)
    for link in normalized_links:
        unknown = set(link["obligation_refs"]) - known_ids
        if unknown:
            raise LinkCompletenessError(
                f"link {link['link_id']} references unknown obligations: {sorted(unknown)}"
            )

    verdicts: list[ObligationVerdict] = []
    for obligation in normalized_obligations:
        obligation_id = obligation["obligation_id"]
        attributed = [link for link in normalized_links if obligation_id in link["obligation_refs"]]
        exact_resolved = [
            link for link in normalized_links
            if link["resolution_status"] == "RESOLVED" and _shape_matches(obligation, link)
        ]

        unique: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
        for link in exact_resolved:
            unique.setdefault(_semantic_key(link), link)
        matched = list(unique.values())
        actual_count = len(matched)

        invalid_candidates = [
            link for link in attributed
            if link["resolution_status"] == "INVALID"
            or (link["resolution_status"] == "RESOLVED" and not _shape_matches(obligation, link))
        ]
        unresolved_candidates = [link for link in attributed if link["resolution_status"] == "UNRESOLVED"]

        min_count = obligation["min_count"]
        max_count = obligation["max_count"]
        below_minimum = actual_count < min_count
        above_maximum = max_count is not None and actual_count > max_count

        if not below_minimum and not above_maximum:
            state = "SATISFIED"
            reason = None
        elif above_maximum:
            state = "INVALID"
            reason = "resolved semantic link cardinality exceeds max_count"
        elif invalid_candidates:
            state = "INVALID"
            reason = "explicit candidate has invalid type, direction, target, or resolution"
        elif unresolved_candidates:
            state = "UNRESOLVED"
            reason = "explicit candidate target is unresolved"
        else:
            state = "MISSING"
            reason = "required minimum cardinality is not satisfied by resolved semantic links"

        verdicts.append(ObligationVerdict(
            obligation_id=obligation_id,
            required=obligation["required"],
            state=state,
            matched_link_ids=tuple(sorted(link["link_id"] for link in matched)),
            candidate_link_ids=tuple(sorted(link["link_id"] for link in attributed)),
            min_count=min_count,
            max_count=max_count,
            actual_count=actual_count,
            reason=reason,
        ))

    aggregate = "SOLVED" if all(
        (not verdict.required) or verdict.state == "SATISFIED"
        for verdict in verdicts
    ) else "UNSOLVED"
    return LinkCompletenessResult(state=aggregate, obligations=tuple(verdicts))
