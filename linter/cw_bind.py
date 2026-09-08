from __future__ import annotations

import copy
from typing import Any


class CWBindingError(ValueError):
    pass


def bind_specification(document: dict[str, Any], specification_ref: str) -> dict[str, Any]:
    """Bind one imported CW candidate to an immutable specification reference.

    Binding is intentionally separate from import and semantic validation. It
    changes only the root specification_ref and never rewrites canonical Entity,
    Property, Link, Function, Event, Required Link, or other modeled content.
    """
    if not isinstance(document, dict):
        raise CWBindingError("CW document must be an object")
    if not isinstance(specification_ref, str) or not specification_ref.strip():
        raise CWBindingError("specification_ref must be a non-empty immutable reference")

    existing = document.get("specification_ref")
    if existing is not None:
        if not isinstance(existing, str) or not existing.strip():
            raise CWBindingError("existing specification_ref is malformed")
        if existing != specification_ref:
            raise CWBindingError(
                f"CW document is already bound to {existing!r}; rebinding would change evaluation context"
            )
        return copy.deepcopy(document)

    bound = copy.deepcopy(document)
    bound["specification_ref"] = specification_ref
    return bound


def is_specification_bound(document: Any) -> bool:
    return (
        isinstance(document, dict)
        and isinstance(document.get("specification_ref"), str)
        and bool(document["specification_ref"].strip())
    )
