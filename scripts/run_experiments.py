"""Lưu số liệu, vết demo và biểu đồ từ lần chạy thực nghiệm."""

import json
from dataclasses import asdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.generate_data import SEED
from src.cbr import CaseBase
from src.datasets import load_cases
from src.experiment import evaluate
from src.knowledge import DATA_DIR, OUTPUTS, load_knowledge
from src.pricing import valuate


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def plot_results(predictions, results, folder):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.labelcolor": "#152941",
                         "text.color": "#152941", "xtick.color": "#354e6b", "ytick.color": "#354e6b"})
    colors = ["#224972", "#557694", "#248378", "#DC6B27"]
    rows = [row for row in results["metrics"] if row["scope"] == "common_cbr"]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.2), sharey=True, layout="constrained")
    for axis, measure, label in zip(axes, ("mae_million", "mape_percent"), ("MAE (triệu đồng)", "MAPE (%)")):
        values = [row[measure] for row in rows]
        bars = axis.barh([row["label"] for row in rows], values, color=colors, height=.58)
        axis.bar_label(bars, fmt="%.2f", padding=4)
        axis.set_xlim(0, max(values) * 1.25)
        axis.set_xlabel(label)
        axis.grid(axis="x", alpha=.14)
    axes[0].invert_yaxis()
    fig.suptitle(f"Sai số trên {results['common_n']} xe có kết quả CBR · Dữ liệu mô phỏng", fontweight="bold")
    fig.savefig(folder / "errors.png", dpi=180)
    plt.close(fig)

    ordered = predictions.sort_values("actual")
    sample = ordered.iloc[np.linspace(0, len(ordered) - 1, 32, dtype=int)]
    x = np.arange(1, len(sample) + 1)
    fig, axis = plt.subplots(figsize=(9.6, 3.2), layout="constrained")
    axis.fill_between(x, sample["lower"], sample["upper"], color=colors[1], alpha=.20, label="Khoảng đề xuất")
    axis.plot(x, sample["hybrid"], color=colors[3], linewidth=1.65, label="Giá đề xuất")
    axis.scatter(x, sample["actual"], color=colors[0], s=14, label="Giá mô phỏng")
    axis.set(xlabel="32 xe lấy đều theo thứ tự giá trên tập test", ylabel="Triệu đồng")
    axis.legend(loc="upper left", frameon=False)
    axis.grid(axis="y", alpha=.16)
    fig.savefig(folder / "intervals.png", dpi=180)
    plt.close(fig)


def main():
    kb = load_knowledge()
    kb.require_valid()
    train, train_issues = load_cases(DATA_DIR / "train.csv", kb)
    test, test_issues = load_cases(DATA_DIR / "test.csv", kb)
    if train_issues or test_issues:
        raise ValueError(train_issues + test_issues)
    predictions, results = evaluate(kb, train, test, SEED)
    folder = OUTPUTS / "experiments"
    folder.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(folder / "predictions.csv", index=False, float_format="%.8f")
    pd.DataFrame(results["metrics"]).to_csv(folder / "metrics.csv", index=False, float_format="%.8f")
    write_json(folder / "metrics.json", results)

    library = CaseBase(kb, train)
    demos = {demo.id: {"label": demo.label, "frame": asdict(kb.frames[demo.vehicle.frame_id]),
                      "valuation": asdict(valuate(demo.vehicle, kb, library))}
             for demo in kb.demos}
    write_json(folder / "demo_results.json", demos)
    if results["common_n"]:
        plot_results(predictions, results, folder)
    print(pd.DataFrame(results["metrics"])[["label", "scope", "n", "mae_million", "mape_percent", "r2"]].to_string(index=False))
    print(f"CBR thiếu {results['cbr_missing']}/{results['test_n']} ca. Khoảng hệ lai: {results['interval']}.")


if __name__ == "__main__":
    main()
