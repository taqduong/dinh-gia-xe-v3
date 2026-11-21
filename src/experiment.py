"""Đánh giá bốn phương pháp trên cùng tập test đã giữ lại."""

from dataclasses import asdict
from platform import python_version
from time import perf_counter_ns

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from .cbr import CaseBase
from .inference import infer
from .models import Case
from .pricing import combine

METHODS = {"rules": "Chỉ luật", "cbr": "Chỉ CBR", "random_forest": "Random Forest", "hybrid": "Hệ lai"}
CATEGORICAL = ["frame_id", "region", "condition", "segment"]
RF_PARAMS = {"n_estimators": 180, "min_samples_leaf": 3, "max_features": .85, "n_jobs": 1}


def features(cases: tuple[Case, ...], kb):
    return pd.DataFrame([
        {**asdict(case.vehicle), "age": kb.year - case.vehicle.year,
         "segment": kb.frames[case.vehicle.frame_id].segment, "new_price": kb.frames[case.vehicle.frame_id].new_price}
        for case in cases
    ]).drop(columns="year")


def build_forest(seed):
    return make_pipeline(
        ColumnTransformer([("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL)], remainder="passthrough"),
        RandomForestRegressor(random_state=seed, **RF_PARAMS),
    )


def measures(data, method, scope, elapsed_ns, count, missing):
    actual, estimate = data["actual"], data[method]
    return {
        "method": method, "label": METHODS[method], "scope": scope, "n": len(data),
        "test_n": count, "cbr_missing": missing, "mae_million": float(mean_absolute_error(actual, estimate)) if len(data) else None,
        "mape_percent": float(mean_absolute_percentage_error(actual, estimate) * 100) if len(data) else None,
        "r2": float(r2_score(actual, estimate)) if len(data) >= 2 else None,
        "total_ms": elapsed_ns / 1e6, "ms_per_vehicle": elapsed_ns / 1e6 / count,
    }


def evaluate(kb, train: tuple[Case, ...], test: tuple[Case, ...], seed: int):
    if not train or not test:
        raise ValueError("Cần dữ liệu train và test.")
    if {case.case_id for case in train} & {case.case_id for case in test}:
        raise ValueError("Train và test có mã tình huống giao nhau.")
    if {case.vehicle for case in train} & {case.vehicle for case in test}:
        raise ValueError("Train và test có đầu vào trùng nhau.")

    cases = CaseBase(kb, train)
    forest = build_forest(seed)
    start = perf_counter_ns()
    forest.fit(features(train, kb), [case.price for case in train])
    training_ms = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns()
    rf_predictions = forest.predict(features(test, kb))
    elapsed = dict.fromkeys(METHODS, 0)
    elapsed["random_forest"] = perf_counter_ns() - start

    rows = []
    for case, forest_prediction in zip(test, rf_predictions):
        start = perf_counter_ns()
        rules = infer(case.vehicle, kb)
        after_rules = perf_counter_ns()
        cbr = cases.estimate(case.vehicle)
        after_cbr = perf_counter_ns()
        hybrid = combine(case.vehicle, rules, cbr, kb)
        after_hybrid = perf_counter_ns()
        elapsed["rules"] += after_rules - start
        elapsed["cbr"] += after_cbr - after_rules
        elapsed["hybrid"] += after_hybrid - start
        rows.append({
            "case_id": case.case_id, **asdict(case.vehicle), "actual": case.price,
            "rules": rules.price, "cbr": cbr.price, "random_forest": forest_prediction, "hybrid": hybrid.price,
            "cbr_neighbors": len(cbr.neighbors), "cbr_mean_similarity": cbr.mean_similarity,
            "cbr_neighbor_ids": "|".join(item.case.case_id for item in cbr.neighbors),
            "cbr_weight": hybrid.cbr_weight, "confidence": hybrid.confidence,
            "lower": hybrid.lower, "upper": hybrid.upper, "covered": hybrid.lower <= case.price <= hybrid.upper,
        })

    predictions = pd.DataFrame(rows)
    common = predictions.dropna(subset="cbr")
    missing, count = len(predictions) - len(common), len(predictions)
    metrics = [measures(common, method, "common_cbr", elapsed[method], count, missing) for method in METHODS]
    metrics += [measures(predictions, method, "full_test", elapsed[method], count, missing)
                for method in METHODS if method != "cbr"]
    metadata = {
        "seed": seed, "reference_year": kb.year, "train_n": len(train), "test_n": count,
        "common_n": len(common), "cbr_missing": missing, "metrics": metrics,
        "interval": {"n": count, "covered_n": int(predictions["covered"].sum()),
                     "coverage_percent": float(predictions["covered"].mean() * 100),
                     "mean_width_million": float((predictions["upper"] - predictions["lower"]).mean())},
        "timing": {"rf_fit_ms": training_ms, "timed_queries_per_method": count, "unit": "ms",
                   "scope": "Đo trên toàn bộ test. RF dự đoán theo lô và có biến đổi đặc trưng. "
                            "Thời gian hệ lai gồm suy diễn, truy hồi và tổng hợp."},
        "rf_params": {"random_state": seed, **RF_PARAMS},
        "versions": {"python": python_version(), "scikit_learn": sklearn.__version__,
                     "numpy": np.__version__, "pandas": pd.__version__},
    }
    return predictions, metadata
