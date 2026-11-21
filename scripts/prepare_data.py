"""Chuẩn hóa và chia train/test, ghi lại số lượng ở từng bước."""

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from scripts.generate_data import SEED
from src.datasets import BOOL_VALUES, VEHICLE_FIELDS, read_raw
from src.knowledge import DATA_DIR, load_knowledge
from src.models import FLAGS

TEST_SHARE = .20


def prepare(raw: pd.DataFrame, kb):
    log = []

    def record(step, before, after):
        log.append({"step": step, "before": before, "after": after, "removed": before - after})

    cleaned = raw.apply(lambda column: column.str.strip())
    for field in ("year", "mileage", "price"):
        cleaned[field] = pd.to_numeric(cleaned[field], errors="coerce")
    for field in FLAGS:
        cleaned[field] = cleaned[field].str.lower().map(BOOL_VALUES)
    record("Chuẩn hóa khoảng trắng, số và cờ Có/Không", len(raw), len(cleaned))

    year, mileage, price = cleaned["year"], cleaned["mileage"], cleaned["price"]
    checks = {
        "Lọc giá thiếu, không hữu hạn hoặc không dương": np.isfinite(price) & price.gt(0),
        "Lọc năm sản xuất sai miền": year.between(kb.settings["min_year"], kb.year) & year.mod(1).eq(0),
        "Lọc số km thiếu hoặc sai miền": mileage.between(0, kb.settings["max_mileage"]) & mileage.mod(1).eq(0),
        "Lọc mã khung, khu vực, tình trạng, mã và lịch sử không hợp lệ": (
            cleaned["frame_id"].isin(kb.frames) & cleaned["region"].isin(kb.settings["region_offsets"]) &
            cleaned["condition"].isin(kb.settings["conditions"]) & cleaned["case_id"].ne("") &
            cleaned[list(FLAGS)].notna().all(axis=1)
        ),
    }
    for name, valid in checks.items():
        before = len(cleaned)
        cleaned = cleaned.loc[valid.reindex(cleaned.index)].copy()
        record(name, before, len(cleaned))
    for name, keys in [("Bỏ mã tình huống trùng", ["case_id"]),
                       ("Bỏ bản ghi có đầu vào trùng", list(VEHICLE_FIELDS))]:
        before = len(cleaned)
        cleaned = cleaned.drop_duplicates(subset=keys).copy()
        record(name, before, len(cleaned))
    cleaned = cleaned.astype({"year": "int64", "mileage": "int64", **dict.fromkeys(FLAGS, "bool")})
    train, test = train_test_split(cleaned, test_size=TEST_SHARE, random_state=SEED)
    train = train.sort_values("case_id").reset_index(drop=True)
    test = test.sort_values("case_id").reset_index(drop=True)
    return train, test, {"seed": SEED, "reference_year": kb.year, "test_share": TEST_SHARE,
                         "steps": log, "raw": len(raw), "clean": len(cleaned), "train": len(train), "test": len(test)}


def main():
    kb = load_knowledge()
    kb.require_valid()
    train, test, log = prepare(read_raw(DATA_DIR / "raw.csv"), kb)
    for name, split in [("train", train), ("test", test)]:
        split.to_csv(DATA_DIR / f"{name}.csv", index=False, float_format="%.2f")
    (DATA_DIR / "preparation.json").write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{log['raw']} → {log['clean']} bản ghi hợp lệ · train {len(train)} · test {len(test)}.")


if __name__ == "__main__":
    main()
