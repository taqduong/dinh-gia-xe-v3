"""Truy hồi và hiệu chỉnh tình huống bằng các hệ số CBR độc lập."""

from collections import defaultdict
from dataclasses import dataclass
from math import fsum

from .knowledge import KnowledgeBase
from .models import Case, Vehicle


@dataclass(frozen=True)
class Neighbor:
    case: Case
    similarity: float
    components: dict[str, float]
    reference_ratio: float
    adjustment_terms: dict[str, float]
    raw_ratio: float
    ratio: float
    adjusted_price: float


@dataclass(frozen=True)
class CaseEstimate:
    neighbors: tuple[Neighbor, ...]
    price: float | None
    mean_similarity: float
    spread: float
    reason: str | None


def similarity(target: Vehicle, case: Vehicle, kb: KnowledgeBase) -> tuple[float, dict[str, float]]:
    config = kb.settings["cbr"]
    levels = kb.settings["conditions"]
    components = {
        "trim": 1.0 if target.frame_id == case.frame_id else config["other_trim_similarity"],
        "year": max(0.0, 1 - abs(target.year - case.year) / config["year_scale"]),
        "mileage": max(0.0, 1 - abs(target.mileage - case.mileage) / config["mileage_scale"]),
        "region": float(target.region == case.region),
        "condition": 1 - abs(levels.index(target.condition) - levels.index(case.condition)) / (len(levels) - 1),
        "dealer_service": float(target.dealer_service == case.dealer_service),
        "commercial": float(target.commercial == case.commercial),
    }
    return fsum(config["weights"][field] * score for field, score in components.items()), components


def adapt(target: Vehicle, case: Case, score: float, components: dict[str, float], kb: KnowledgeBase) -> Neighbor:
    other = case.vehicle
    config = kb.settings["cbr"]
    levels, regions = kb.settings["conditions"], kb.settings["region_offsets"]
    reference_ratio = kb.frames[target.frame_id].new_price / kb.frames[other.frame_id].new_price
    terms = {
        "year": (target.year - other.year) * config["age_adjustment_per_year"],
        "mileage": (other.mileage - target.mileage) / 20000 * config["mileage_adjustment_per_20000"],
        "condition": (levels.index(target.condition) - levels.index(other.condition)) * config["condition_adjustment_per_level"],
        "dealer_service": (int(target.dealer_service) - int(other.dealer_service)) * config["dealer_adjustment"],
        "commercial": (int(other.commercial) - int(target.commercial)) * config["commercial_adjustment"],
        "region": regions[target.region] - regions[other.region],
    }
    raw_ratio = reference_ratio * (1 + fsum(terms.values()))
    ratio = min(config["max_ratio"], max(config["min_ratio"], raw_ratio))
    return Neighbor(case, score, components, reference_ratio, terms, raw_ratio, ratio, case.price * ratio)


class CaseBase:
    def __init__(self, kb: KnowledgeBase, cases: tuple[Case, ...]):
        self.kb = kb
        self.cases = cases
        self.groups: dict[tuple, list[Case]] = defaultdict(list)
        for case in cases:
            self.groups[self.key(case.vehicle)].append(case)

    def key(self, vehicle: Vehicle) -> tuple:
        return (*self.kb.frames[vehicle.frame_id].model_key, vehicle.flood, vehicle.major_accident)

    def estimate(self, target: Vehicle, exclude_id: str | None = None) -> CaseEstimate:
        config = self.kb.settings["cbr"]
        candidates = []
        for case in self.groups.get(self.key(target), ()):
            if case.case_id == exclude_id or abs(target.year - case.vehicle.year) > config["year_window"]:
                continue
            score, components = similarity(target, case.vehicle, self.kb)
            if score >= config["threshold"]:
                candidates.append((score, case, components))
        candidates.sort(key=lambda pair: (-pair[0], pair[1].case_id))
        neighbors = tuple(
            adapt(target, case, score, components, self.kb)
            for score, case, components in candidates[:config["limit"]]
        )
        total = fsum(item.similarity for item in neighbors)
        count = len(neighbors)
        mean = total / count if count else 0.0
        if count < config["minimum"]:
            reason = (f"Chỉ có {count} xe đạt ngưỡng tương tự {config['threshold']:.0%}. "
                      f"Cần ít nhất {config['minimum']} xe cùng dòng và cùng hồ sơ ngập nước, tai nạn nặng.")
            return CaseEstimate(neighbors, None, mean, 0.0, reason)
        price = fsum(item.similarity * item.adjusted_price for item in neighbors) / total
        spread = fsum(item.similarity * abs(item.adjusted_price - price) for item in neighbors) / total
        return CaseEstimate(neighbors, price, mean, spread, None)
