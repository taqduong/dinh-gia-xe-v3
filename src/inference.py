"""Máy suy diễn tiến với tập sự kiện, tập xung đột và vết thực thi."""

from dataclasses import asdict, dataclass

from .knowledge import KnowledgeBase
from .models import Vehicle


@dataclass(frozen=True)
class Step:
    rule_id: str
    priority: int
    explanation: str
    before: float
    delta: float
    after: float
    warning: str | None


@dataclass(frozen=True)
class Inference:
    reference_price: float
    price: float
    steps: tuple[Step, ...]
    risk_count: int
    risk_multiplier: float

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(step.warning for step in self.steps if step.warning)


def infer(vehicle: Vehicle, kb: KnowledgeBase) -> Inference:
    kb.require_valid()
    if errors := kb.vehicle_errors(vehicle):
        raise ValueError(" ".join(errors))
    frame = kb.frames[vehicle.frame_id]
    facts = {
        **asdict(vehicle), "age": kb.year - vehicle.year, "segment": frame.segment,
        "price": frame.new_price, "risk_count": 0, "risk_multiplier": 1.0,
    }
    fired: set[str] = set()
    steps: list[Step] = []

    while True:
        # Tập luật đã sắp theo độ ưu tiên giảm dần, sau đó theo mã tăng dần.
        rule = next(
            (item for item in kb.rules if item.id not in fired and all(c.matches(facts) for c in item.conditions)),
            None,
        )
        if rule is None:
            break
        before = facts["price"]
        action = rule.action
        factor = 1 + action.value
        if action.type == "apply_risk":
            facts["risk_multiplier"] *= factor
            facts["risk_count"] += 1
        elif action.type == "floor_risk_multiplier":
            factor = max(1.0, action.value / facts["risk_multiplier"])
            facts["risk_multiplier"] *= factor
        facts["price"] *= factor
        fired.add(rule.id)
        steps.append(Step(rule.id, rule.priority, rule.explanation, before, facts["price"] - before,
                          facts["price"], action.warning))
    return Inference(frame.new_price, facts["price"], tuple(steps), facts["risk_count"], facts["risk_multiplier"])
