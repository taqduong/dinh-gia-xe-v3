"""Sinh 3.000 tình huống và thêm lỗi có chủ đích để minh họa làm sạch."""

from dataclasses import asdict

import numpy as np
import pandas as pd

from src.datasets import COLUMNS
from src.knowledge import DATA_DIR, KnowledgeBase, load_knowledge
from src.models import Vehicle

SEED = 4126
SAMPLE_COUNT = 3000
# Mốc đời xe và trọng số lấy mẫu do nhóm mô phỏng quy định.
MODELS = {
    "Vios": (2009, 18), "Corolla Cross": (2020, 6), "Fortuner": (2010, 6),
    "Accent": (2012, 12), "Grand i10": (2014, 9), "Tucson": (2013, 5),
    "Morning": (2012, 8), "Seltos": (2020, 5), "K3": (2014, 5),
    "City": (2013, 9), "Civic": (2016, 4), "CR-V": (2012, 5),
    "Mazda3": (2014, 6), "CX-5": (2014, 7), "Xpander": (2018, 8),
    "Ranger": (2013, 7),
}
REGION_MARKET = {"Hà Nội": 1.018, "TP. Hồ Chí Minh": 1.026, "Đà Nẵng": .985,
                 "Tỉnh miền Bắc": .970, "Tỉnh miền Nam": .979}
CONDITION_MARKET = {"Tốt": 1.04, "Khá": 0.986, "Trung bình": 0.91, "Kém": 0.79}


def generate(kb: KnowledgeBase, size: int = SAMPLE_COUNT) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    frames = [frame for frame in kb.frames.values() if frame.model in MODELS]
    popularity = np.array([MODELS[frame.model][1] for frame in frames], dtype=float)
    sample = rng.choice(len(frames), size, p=popularity / popularity.sum())
    rows = []
    for index, frame_index in enumerate(sample, 1):
        frame = frames[frame_index]
        max_age = kb.year - MODELS[frame.model][0]
        age = int(rng.triangular(0, min(6, max_age - 1), max_age + 1))
        commercial = bool(rng.random() < (.20 if frame.segment in {"Sedan hạng B", "MPV"} else .09))
        flood = bool(rng.random() < .048)
        accident = bool(rng.random() < (.066 if commercial else .035))
        dealer = bool(rng.random() < max(.20, .65 - .024 * age))
        annual_km = 12300 + 9700 * commercial
        km = int(np.clip(rng.normal(6000 + annual_km * age, 6500 + 1600 * age), 300, 470000))
        wear = age / 12 + .38 * commercial + .60 * flood + .49 * accident + rng.normal(0, .38) - .19 * dealer
        condition = ("Tốt" if wear < .20 else "Khá" if wear < .84 else
                     "Trung bình" if wear < 1.36 else "Kém")
        region = str(rng.choice(list(REGION_MARKET), p=[.29, .30, .09, .16, .16]))
        vehicle = Vehicle(frame.id, kb.year - age, km, region, condition, dealer, commercial, flood, accident)

        # Đường khấu hao liên tục, hiệu ứng thị trường giả định và nhiễu log-normal.
        age_factor = .955 * np.exp(-(.064 + .003 * (frame.brand not in {"Toyota", "Honda"})) * age ** .92)
        mileage_factor = np.exp(-.0000022 * (km - 12900 * age))
        risk_factor = (.91 if commercial else 1) * (.74 if flood else 1) * (.80 if accident else 1)
        risk_factor *= .91 if flood and accident else 1
        price = (frame.new_price * age_factor * mileage_factor * CONDITION_MARKET[condition] *
                 REGION_MARKET[region] * (1.024 if dealer else .995) * risk_factor *
                 np.exp(rng.normal(0, .065 + .012 * (flood or accident))))
        price = round(float(np.clip(price, 10, frame.new_price * 1.15)), 2)
        rows.append({"case_id": f"VN{index:04d}", **asdict(vehicle), "price": price})

    # Cùng bản ghi với cùng mã, rồi cùng đặc trưng nhưng khác mã.
    for offset, row in enumerate(rows[:24]):
        duplicate = dict(row)
        if offset >= 12:
            duplicate["case_id"] = f"DUP{offset:02d}"
        rows.append(duplicate)
    defects = [("price", -1)] * 5 + [("year", kb.year + 3)] * 4 + [("mileage", "")] * 4 + [("frame_id", "unknown")] * 3
    for offset, (column, value) in enumerate(defects):
        rows.append({**rows[30 + offset], "case_id": f"ERR{offset:02d}", column: value})
    return pd.DataFrame(rows, columns=COLUMNS)


def main():
    kb = load_knowledge()
    kb.require_valid()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dataset = generate(kb)
    dataset.to_csv(DATA_DIR / "raw.csv", index=False, float_format="%.2f")
    print(f"Đã tạo {len(dataset)} bản ghi · seed {SEED} · năm tham chiếu {kb.year}.")


if __name__ == "__main__":
    main()
