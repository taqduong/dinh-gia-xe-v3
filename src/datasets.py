"""Đọc dữ liệu mô phỏng và dựng kho tình huống từ dữ liệu đã kiểm tra."""

from dataclasses import fields
from math import isfinite
from pathlib import Path

import pandas as pd

from .knowledge import Issue, KnowledgeBase
from .models import FLAGS, Case, Vehicle

VEHICLE_FIELDS = tuple(field.name for field in fields(Vehicle))
COLUMNS = ("case_id", *VEHICLE_FIELDS, "price")
BOOL_VALUES = {"true": True, "false": False, "1": True, "0": False}


def read_raw(path: Path) -> pd.DataFrame:
    dataset = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = set(COLUMNS) - set(dataset.columns)
    if missing:
        raise ValueError(f"Thiếu cột: {', '.join(sorted(missing))}.")
    return dataset.loc[:, list(COLUMNS)]


def row_case(row: dict, kb: KnowledgeBase) -> Case:
    values = {key: row[key] for key in ("frame_id", "region", "condition")}
    try:
        values.update({key: int(row[key]) for key in ("year", "mileage")})
        values.update({key: BOOL_VALUES[str(row[key]).lower()] for key in FLAGS})
        price = float(row["price"])
    except (TypeError, ValueError, KeyError) as error:
        raise ValueError("Sai kiểu năm, số km, giá hoặc cờ lịch sử.") from error
    vehicle = Vehicle(**values)
    if errors := kb.vehicle_errors(vehicle):
        raise ValueError(" ".join(errors))
    if not isfinite(price) or price <= 0:
        raise ValueError("Giá tình huống phải là số dương.")
    if not row["case_id"].strip():
        raise ValueError("Thiếu mã tình huống.")
    return Case(row["case_id"], vehicle, price)


def load_cases(path: Path, kb: KnowledgeBase) -> tuple[tuple[Case, ...], tuple[Issue, ...]]:
    try:
        dataset = read_raw(path)
    except (OSError, ValueError) as error:
        return (), (Issue(path.name, "Tệp", str(error)),)

    cases, issues, seen = [], [], set()
    for idx, row in enumerate(dataset.to_dict("records"), 2):
        try:
            case = row_case(row, kb)
            if case.case_id in seen:
                raise ValueError("Mã tình huống trùng.")
            seen.add(case.case_id)
            cases.append(case)
        except ValueError as error:
            issues.append(Issue(path.name, f"Dòng {idx} ({row['case_id']})", str(error)))
    return tuple(cases), tuple(issues)


def case_dataframe(cases: tuple[Case, ...], kb: KnowledgeBase) -> pd.DataFrame:
    rows = []
    for case in cases:
        frame = kb.frames[case.vehicle.frame_id]
        rows.append({"Mã": case.case_id, "Hãng": frame.brand, "Dòng": frame.model, "Phiên bản": frame.name,
                     "Phân khúc": frame.segment, "Đời xe": case.vehicle.year, "Số km": case.vehicle.mileage,
                     "Khu vực": case.vehicle.region, "Tình trạng": case.vehicle.condition,
                     "Bảo dưỡng hãng": case.vehicle.dealer_service, "Xe dịch vụ": case.vehicle.commercial,
                     "Ngập nước": case.vehicle.flood, "Tai nạn nặng": case.vehicle.major_accident,
                     "Tuổi xe": kb.year - case.vehicle.year, "Giá (triệu ₫)": case.price})
    return pd.DataFrame(rows)
