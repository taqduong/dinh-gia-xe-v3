import json
from dataclasses import replace
from shutil import copytree

import pytest

from src.cbr import CaseBase, adapt, similarity
from src.datasets import load_cases
from src.inference import infer
from src.knowledge import DATA_DIR, KB_DIR, load_knowledge
from src.models import Case
from src.pricing import valuate


@pytest.fixture(scope="module")
def kb():
    return load_knowledge()


@pytest.fixture(scope="module")
def primary(kb):
    return next(demo.vehicle for demo in kb.demos if demo.id == "normal")


@pytest.fixture(scope="module")
def library(kb):
    cases, issues = load_cases(DATA_DIR / "train.csv", kb)
    assert not issues
    return CaseBase(kb, cases)


def test_knowledge_and_main_demo(kb, primary):
    assert not kb.issues
    assert len(kb.rules) == 25
    assert len(kb.demos) == 5
    assert kb.frames[primary.frame_id].title == "Toyota Vios 1.5G CVT"
    assert (primary.year, primary.mileage) == (2019, 95000)


@pytest.mark.parametrize("change,fragment", [
    ({"year": 2027}, "Năm sản xuất"),
    ({"year": 1999}, "Năm sản xuất"),
    ({"mileage": -1}, "Số km"),
    ({"mileage": 1.5}, "Số km"),
    ({"region": "Không rõ"}, "Khu vực"),
    ({"frame_id": "khung-sai"}, "Phiên bản"),
    ({"flood": "false"}, "lịch sử"),
])
def test_invalid_request(kb, primary, change, fragment):
    with pytest.raises(ValueError, match=fragment):
        infer(replace(primary, **change), kb)


def test_forward_chain_and_trace(kb, primary):
    result = infer(primary, kb)
    assert [step.rule_id for step in result.steps] == ["TUOI-04", "KM-03", "TT-02", "BD-02", "KV-01"]
    assert result.price == pytest.approx(548 * .65 * .94 * .98 * .98 * 1.02)
    for before, step in zip([result.reference_price, *(s.after for s in result.steps)], result.steps):
        assert step.before == pytest.approx(before)
        assert step.before + step.delta == pytest.approx(step.after)
    assert not result.warnings


def test_dealer_adjustment(kb, primary):
    baseline = infer(primary, kb).price
    dealer = infer(replace(primary, dealer_service=True), kb)
    assert dealer.price == pytest.approx(baseline * 1.04 / .98)
    assert "BD-01" in [step.rule_id for step in dealer.steps]


def test_multiple_risks_and_priority(kb, primary):
    vehicle = replace(primary, commercial=True, flood=True, major_accident=True)
    result = infer(vehicle, kb)
    assert [step.rule_id for step in result.steps[-4:]] == ["RR-01", "RR-02", "RR-03", "RR-04"]
    assert result.risk_count == len(result.warnings) == 3
    assert result.risk_multiplier == pytest.approx(.58)
    assert result.price == pytest.approx(infer(primary, kb).price * .58)
    assert result.steps[-1].delta > 0


def test_cbr_filters_weights_and_adjusts(kb, primary, library):
    estimate = library.estimate(primary)
    scores = [neighbor.similarity for neighbor in estimate.neighbors]
    assert len(scores) == 5
    assert scores == sorted(scores, reverse=True)
    assert min(scores) >= kb.settings["cbr"]["threshold"]
    for neighbor in estimate.neighbors:
        assert library.key(neighbor.case.vehicle) == library.key(primary)
        assert neighbor.adjusted_price == pytest.approx(neighbor.case.price * neighbor.ratio)
    assert estimate.price == pytest.approx(
        sum(neighbor.similarity * neighbor.adjusted_price for neighbor in estimate.neighbors) / sum(scores)
    )
    score, parts = similarity(primary, replace(primary, mileage=115000), kb)
    neighbor = adapt(primary, Case("X", replace(primary, mileage=115000), 300), score, parts, kb)
    assert score == pytest.approx(1 - .18 * 20000 / 120000)
    assert neighbor.adjusted_price == pytest.approx(300 * 1.035)
    assert all(candidate.case.case_id != "X" for candidate in
               CaseBase(kb, (neighbor.case,)).estimate(primary, exclude_id="X").neighbors)


def test_cbr_risk_and_year_filters(kb, primary):
    candidates = (Case("A", replace(primary, flood=True), 350), Case("B", replace(primary, year=2014), 350),
                  Case("C", primary, 320))
    result = CaseBase(kb, candidates).estimate(primary)
    assert [neighbor.case.case_id for neighbor in result.neighbors] == ["C"]
    assert result.price is None
    assert "1 xe" in result.reason


def test_hybrid_and_interval(kb, primary, library):
    result = valuate(primary, kb, library)
    expected_weight = .25 + .5 * result.cbr.mean_similarity * len(result.cbr.neighbors) / 5
    assert result.cbr_weight == pytest.approx(expected_weight)
    assert result.cbr_weight + result.rule_weight == pytest.approx(1)
    assert result.price == pytest.approx(result.rule_weight * result.inference.price + result.cbr_weight * result.cbr.price)
    half = .10 * result.price + .35 * abs(result.cbr.price - result.inference.price) + .30 * result.cbr.spread
    assert (result.lower, result.upper) == pytest.approx((max(1, result.price - half), result.price + half))
    assert result.confidence == "Cao"


def test_missing_cases_fallback(kb, library):
    sparse = next(demo.vehicle for demo in kb.demos if demo.id == "sparse")
    result = valuate(sparse, kb, library)
    assert result.cbr.price is None
    assert "0 xe" in result.cbr.reason
    assert result.cbr_weight == 0
    assert result.price == result.inference.price
    assert result.confidence == "Thấp"


def test_severe_case(kb, library):
    vehicle = next(demo.vehicle for demo in kb.demos if demo.id == "flood")
    result = valuate(vehicle, kb, library)
    assert result.confidence == "Thấp"
    assert "ngập nước" in result.inference.warnings[0]
    assert result.price < result.inference.reference_price
    assert result.cbr_weight < .60


def test_knowledge_validation_reports_bad_entries(tmp_path):
    store = tmp_path / "kb"
    copytree(KB_DIR, store)
    rules_path = store / "rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rules += [
        rules[0],
        {**rules[1], "id": "INVALID-OP", "conditions": [{"field": "age", "op": "???", "value": 4}]},
        {**rules[1], "id": "INVALID-ACTION", "action": {"type": "replace_price", "value": 10}},
        {**rules[1], "id": "MISSING-FRAME", "conditions": [{"field": "frame_id", "op": "==", "value": "missing"}]},
    ]
    rules_path.write_text(json.dumps(rules), encoding="utf-8")
    messages = [issue.message for issue in load_knowledge(store).issues]
    for fragment in ("Mã luật trùng", "toán tử không hợp lệ", "Hành động không hợp lệ", "mã khung không tồn tại"):
        assert any(fragment in message for message in messages)
