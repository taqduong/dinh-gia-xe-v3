import json

import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error

from scripts.generate_data import generate
from scripts.prepare_data import prepare
from src.datasets import VEHICLE_FIELDS, read_raw
from src.knowledge import DATA_DIR, OUTPUTS, load_knowledge


def test_generator_is_deterministic():
    kb = load_knowledge()
    pd.testing.assert_frame_equal(generate(kb, 80), generate(kb, 80))


def test_prepare_steps_and_split():
    kb = load_knowledge()
    raw = read_raw(DATA_DIR / "raw.csv")
    train, test, log = prepare(raw, kb)
    assert len(raw) == 3040 and len(train) == 2400 and len(test) == 600
    assert sum(step["removed"] for step in log["steps"]) == 40
    assert not set(train.case_id) & set(test.case_id)
    assert not pd.concat([train, test]).duplicated(subset=list(VEHICLE_FIELDS)).any()
    assert list(train.case_id) == sorted(train.case_id)


def test_outputs_share_test_and_report_missing():
    root = OUTPUTS / "experiments"
    predictions = pd.read_csv(root / "predictions.csv")
    train_ids = set(pd.read_csv(DATA_DIR / "train.csv").case_id)
    test_ids = set(pd.read_csv(DATA_DIR / "test.csv").case_id)
    results = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    assert set(predictions.case_id) == test_ids
    assert len(predictions) == results["test_n"]
    retrieved = {code for row in predictions.cbr_neighbor_ids.dropna() for code in row.split("|")}
    assert retrieved <= train_ids and not retrieved & test_ids
    common = predictions[predictions.cbr.notna()]
    assert len(common) == results["common_n"] == results["test_n"] - results["cbr_missing"]
    assert (predictions.loc[predictions.cbr.isna(), "cbr_weight"] == 0).all()
    for row in results["metrics"]:
        dataset = common if row["scope"] == "common_cbr" else predictions
        assert row["mae_million"] == pytest.approx(mean_absolute_error(dataset.actual, dataset[row["method"]]))
        assert len(dataset) == row["n"]
    assert results["interval"]["covered_n"] == int(predictions.covered.sum())
    assert results["interval"]["mean_width_million"] == pytest.approx((predictions.upper - predictions.lower).mean())
