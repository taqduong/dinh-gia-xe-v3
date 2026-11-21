"""Nạp và kiểm tra khung, luật và mẫu định giá từ JSON."""

import json
from dataclasses import dataclass
from math import isclose, isfinite
from operator import eq, ge, gt, le, lt, ne
from pathlib import Path

from .models import FLAGS, Frame, Vehicle

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "kb"
DATA_DIR = ROOT / "data"
OUTPUTS = ROOT / "outputs"

COMPARISONS = {"==": eq, "!=": ne, ">": gt, ">=": ge, "<": lt, "<=": le, "in": lambda x, y: x in y}
NUMERIC_FACTS = {"age", "year", "mileage", "risk_count", "risk_multiplier", "price"}
ACTION_TYPES = ("adjust_percent", "apply_risk", "floor_risk_multiplier")


@dataclass(frozen=True)
class Issue:
    source: str
    location: str
    message: str


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: object

    def matches(self, facts: dict) -> bool:
        return COMPARISONS[self.op](facts[self.field], self.value)


@dataclass(frozen=True)
class Action:
    type: str
    value: float
    warning: str | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    conditions: tuple[Condition, ...]
    action: Action
    priority: int
    explanation: str


@dataclass(frozen=True)
class Demo:
    id: str
    label: str
    vehicle: Vehicle


@dataclass
class KnowledgeBase:
    settings: dict
    frames: dict[str, Frame]
    rules: tuple[Rule, ...]
    demos: tuple[Demo, ...]
    issues: tuple[Issue, ...]

    @property
    def year(self) -> int:
        return self.settings["reference_year"]

    def vehicle_errors(self, vehicle: Vehicle) -> list[str]:
        errors = []
        if not isinstance(vehicle.frame_id, str) or vehicle.frame_id not in self.frames:
            errors.append("Phiên bản xe không tồn tại trong cơ sở tri thức.")
        if type(vehicle.year) is not int or not self.settings["min_year"] <= vehicle.year <= self.year:
            errors.append(f"Năm sản xuất phải là số nguyên từ {self.settings['min_year']} đến {self.year}.")
        if type(vehicle.mileage) is not int or not 0 <= vehicle.mileage <= self.settings["max_mileage"]:
            errors.append(f"Số km phải là số nguyên từ 0 đến {self.settings['max_mileage']:,}.".replace(",", "."))
        if not isinstance(vehicle.region, str) or vehicle.region not in self.settings["region_offsets"]:
            errors.append("Khu vực không hợp lệ.")
        if vehicle.condition not in self.settings["conditions"]:
            errors.append("Tình trạng không hợp lệ.")
        if any(type(getattr(vehicle, field)) is not bool for field in FLAGS):
            errors.append("Các mục lịch sử xe phải có giá trị Có hoặc Không.")
        return errors

    def require_valid(self) -> None:
        if self.issues:
            detail = " ".join(f"{i.source} · {i.location} · {i.message}" for i in self.issues)
            raise ValueError(detail)


def is_number(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value)


def is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _read(path: Path, expected: type, issues: list[Issue]):
    try:
        with path.open(encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, expected):
            raise ValueError(f"Cần kiểu {expected.__name__} ở cấp ngoài cùng.")
        return payload
    except (OSError, ValueError) as error:
        issues.append(Issue(path.name, "Tệp", str(error)))
        return expected()


def _frames(payload: dict, issues: list[Issue]) -> dict[str, Frame]:
    frames = {}

    def read_group(brand, model, trims):
        if not is_text(model) or not isinstance(trims, list) or not trims:
            issues.append(Issue("frames.json", f"{brand}/{model}", "Dòng xe phải chứa danh sách phiên bản."))
            return
        for index, trim in enumerate(trims, 1):
            location = f"{brand}/{model} #{index}"
            if not isinstance(trim, dict) or not all(is_text(trim.get(key)) for key in ("id", "name", "segment")):
                issues.append(Issue("frames.json", location, "Thiếu mã, tên phiên bản hoặc phân khúc."))
                continue
            code, price = trim["id"], trim.get("new_price")
            if code in frames:
                issues.append(Issue("frames.json", location, f"Mã khung trùng ({code})."))
            elif not is_number(price) or price <= 0:
                issues.append(Issue("frames.json", code, "Giá tham chiếu phải là số dương."))
            else:
                frames[code] = Frame(code, brand, model, trim["name"], trim["segment"], price)

    for brand, models in payload.items():
        if not is_text(brand) or not isinstance(models, dict) or not models:
            issues.append(Issue("frames.json", str(brand), "Hãng xe phải chứa ít nhất một dòng xe."))
            continue
        for model, trims in models.items():
            read_group(brand, model, trims)
    if not frames:
        issues.append(Issue("frames.json", "Tệp", "Cần ít nhất một khung hợp lệ."))
    return frames


def _condition(raw: object, domains: dict) -> Condition:
    if not isinstance(raw, dict):
        raise ValueError("Điều kiện cần có trường, toán tử và giá trị.")
    field, op, value = raw.get("field"), raw.get("op"), raw.get("value")
    if not isinstance(field, str) or not isinstance(op, str) or op not in COMPARISONS:
        raise ValueError(f"Điều kiện có trường hoặc toán tử không hợp lệ ({field}, {op}).")
    if field in NUMERIC_FACTS and op != "in" and is_number(value):
        return Condition(field, op, value)
    if field in FLAGS and op in ("==", "!=") and type(value) is bool:
        return Condition(field, op, value)
    if field in domains and op in ("==", "!=", "in"):
        values = value if op == "in" else [value]
        if isinstance(values, list) and values and all(is_text(item) and item in domains[field] for item in values):
            return Condition(field, op, value)
        if field == "frame_id":
            raise ValueError(f"Điều kiện tham chiếu mã khung không tồn tại ({value}).")
    raise ValueError(f"Điều kiện không hợp lệ ({field} {op} {value}).")


def _action(raw: object) -> Action:
    if not isinstance(raw, dict):
        raise ValueError("Hành động cần có kiểu và hệ số.")
    kind, value, warning = raw.get("type"), raw.get("value"), raw.get("warning")
    if kind not in ACTION_TYPES or not is_number(value) or (warning is not None and not is_text(warning)):
        raise ValueError(f"Hành động không hợp lệ ({kind}, {value}).")
    lower, upper = {"adjust_percent": (-1, 1.01), "apply_risk": (-1, 0), "floor_risk_multiplier": (0, 1)}[kind]
    if not lower < value < upper:
        raise ValueError(f"Hệ số hành động ngoài miền cho phép ({kind}, {value}).")
    return Action(kind, value, warning)


def _rules(payload: list, domains: dict, issues: list[Issue]) -> tuple[Rule, ...]:
    result, codes = [], set()
    for index, raw in enumerate(payload, 1):
        code = raw.get("id") if isinstance(raw, dict) else None
        location = code if is_text(code) else f"Luật #{index}"
        try:
            if not is_text(code):
                raise ValueError("Thiếu mã luật hợp lệ.")
            if code in codes:
                raise ValueError(f"Mã luật trùng ({code}).")
            codes.add(code)
            priority = raw.get("priority")
            if type(priority) is not int or priority <= 0:
                raise ValueError("Độ ưu tiên phải là số nguyên dương.")
            if not is_text(raw.get("explanation")):
                raise ValueError("Thiếu giải thích của luật.")
            if not isinstance(raw.get("conditions"), list) or not raw["conditions"]:
                raise ValueError("Luật cần ít nhất một điều kiện.")
            conditions = tuple(_condition(item, domains) for item in raw["conditions"])
            result.append(Rule(code, conditions, _action(raw.get("action")), priority, raw["explanation"]))
        except ValueError as error:
            issues.append(Issue("rules.json", location, str(error)))
    if not result:
        issues.append(Issue("rules.json", "Tệp", "Cần ít nhất một luật hợp lệ."))

    for first, second in zip(ACTION_TYPES, ACTION_TYPES[1:]):
        before = [rule.priority for rule in result if rule.action.type == first]
        after = [rule.priority for rule in result if rule.action.type == second]
        if before and after and min(before) <= max(after):
            issues.append(Issue("rules.json", "Độ ưu tiên", f"{first} phải đứng trước {second}."))
    return tuple(sorted(result, key=lambda rule: (-rule.priority, rule.id)))


def load_knowledge(path: Path = KB_DIR) -> KnowledgeBase:
    issues: list[Issue] = []
    settings = _read(path / "settings.json", dict, issues)
    required = {"reference_year", "min_year", "max_mileage", "conditions", "region_offsets", "cbr", "hybrid"}
    if missing := required - settings.keys():
        issues.append(Issue("settings.json", "Cấu hình", f"Thiếu khóa {', '.join(sorted(missing))}."))
        return KnowledgeBase(settings, {}, (), (), tuple(issues))
    weights = settings["cbr"]["weights"]
    if not all(is_number(value) and value > 0 for value in weights.values()) or not isclose(sum(weights.values()), 1):
        issues.append(Issue("settings.json", "CBR", "Trọng số độ tương tự phải dương và có tổng bằng 1."))
    frames = _frames(_read(path / "frames.json", dict, issues), issues)
    domains = {
        "frame_id": frames, "condition": settings["conditions"], "region": settings["region_offsets"],
        "segment": {frame.segment for frame in frames.values()},
    }
    rules = _rules(_read(path / "rules.json", list, issues), domains, issues)
    kb = KnowledgeBase(settings, frames, rules, (), ())
    demos = []
    for index, item in enumerate(_read(path / "demos.json", list, issues), 1):
        try:
            if not isinstance(item, dict) or not all(is_text(item.get(key)) for key in ("id", "label")):
                raise ValueError("Thiếu mã hoặc tên mẫu.")
            if any(demo.id == item["id"] for demo in demos):
                raise ValueError(f"Mã mẫu trùng ({item['id']}).")
            vehicle = Vehicle(**item["vehicle"])
            if errors := kb.vehicle_errors(vehicle):
                raise ValueError(" ".join(errors))
            demos.append(Demo(item["id"], item["label"], vehicle))
        except (KeyError, TypeError, ValueError) as error:
            issues.append(Issue("demos.json", f"Mẫu #{index}", str(error)))
    if not demos:
        issues.append(Issue("demos.json", "Tệp", "Cần ít nhất một mẫu hợp lệ."))
    kb.demos, kb.issues = tuple(demos), tuple(issues)
    return kb
