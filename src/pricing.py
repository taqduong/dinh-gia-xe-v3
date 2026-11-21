"""Tổng hợp giá và tính dải tham khảo theo tri thức khai báo."""

from dataclasses import dataclass

from .cbr import CaseBase, CaseEstimate
from .inference import Inference, infer
from .knowledge import KnowledgeBase
from .models import Vehicle


@dataclass(frozen=True)
class Valuation:
    vehicle: Vehicle
    inference: Inference
    cbr: CaseEstimate
    rule_weight: float
    cbr_weight: float
    price: float
    lower: float
    upper: float
    confidence: str
    confidence_reason: str
    interval_rate: float
    disagreement_addition: float
    spread_addition: float


def combine(vehicle: Vehicle, rules: Inference, cbr: CaseEstimate, kb: KnowledgeBase) -> Valuation:
    config = kb.settings["hybrid"]
    n = len(cbr.neighbors)
    cap = kb.settings["cbr"]["limit"]
    wcbr, gap = 0.0, 0.0
    interval_rate = config["rules_only_interval"]
    confidence, reason = "Thấp", cbr.reason
    if cbr.price is not None:
        wcbr = config["base_cbr_weight"] + config["quality_cbr_weight"] * cbr.mean_similarity * n / cap
        if vehicle.severe:
            wcbr *= config["severe_weight_factor"]
        gap = abs(rules.price - cbr.price)
        interval_rate = config["base_interval"]
        if n < cap:
            interval_rate += config["sparse_interval"]

    price = (1 - wcbr) * rules.price + wcbr * (cbr.price or 0.0)
    if cbr.price is not None:
        if vehicle.severe:
            reason = "Có lịch sử ngập nước hoặc tai nạn nặng."
        elif (not vehicle.commercial and n == cap and cbr.mean_similarity >= config["high_similarity"]
              and gap / price <= config["high_disagreement"]):
            confidence, reason = "Cao", "Đủ 5 xe, độ tương tự cao và chênh lệch giữa hai giá thấp."
        elif cbr.mean_similarity >= config["medium_similarity"] and gap / price <= config["medium_disagreement"]:
            confidence, reason = "Trung bình", "Độ tương tự và chênh lệch giá đạt ngưỡng trung bình."
        else:
            reason = "Độ tương tự thấp hoặc hai phương pháp cho giá chênh lệch lớn."
    if vehicle.severe:
        interval_rate += config["severe_interval"]
    if vehicle.commercial:
        interval_rate += config["commercial_interval"]
    disagreement = config["disagreement_factor"] * gap
    spread = config["spread_factor"] * cbr.spread if cbr.price is not None else 0.0
    half = price * interval_rate + disagreement + spread
    return Valuation(vehicle, rules, cbr, 1 - wcbr, wcbr, price, max(1.0, price - half), price + half,
                     confidence, reason or "", interval_rate, disagreement, spread)


def valuate(vehicle: Vehicle, kb: KnowledgeBase, cases: CaseBase) -> Valuation:
    return combine(vehicle, infer(vehicle, kb), cases.estimate(vehicle), kb)
