from __future__ import annotations

from dataclasses import dataclass, field

from .event_logic import EventTriggerRule


class EventRuleRegistryError(ValueError):
    pass


@dataclass
class EventRuleRegistry:
    _rules: dict[str, EventTriggerRule] = field(default_factory=dict)

    def register(self, rule: EventTriggerRule, *, replace: bool = False) -> None:
        if not isinstance(rule, EventTriggerRule):
            raise EventRuleRegistryError("event rule registry accepts EventTriggerRule only")
        if rule.rule_id in self._rules and not replace:
            raise EventRuleRegistryError(f"event trigger rule already registered: {rule.rule_id}")
        self._rules[rule.rule_id] = rule

    def rules(self) -> tuple[EventTriggerRule, ...]:
        return tuple(self._rules[key] for key in sorted(self._rules))

    def rules_for_language(self, language_id: str) -> tuple[EventTriggerRule, ...]:
        return tuple(rule for rule in self.rules() if rule.language_id == language_id)

    def clear(self) -> None:
        self._rules.clear()

    def __len__(self) -> int:
        return len(self._rules)


DEFAULT_EVENT_RULES = EventRuleRegistry()
