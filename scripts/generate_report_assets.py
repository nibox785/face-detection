import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Dict

plt = importlib.import_module("matplotlib.pyplot")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Khong tim thay file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def percent_change(new_value: float, old_value: float) -> float:
    if old_value == 0:
        return 0.0
    return (new_value - old_value) / old_value * 100.0


def build_threshold_map(report: Dict[str, Any]) -> Dict[float, Dict[str, Any]]:
    threshold_map: Dict[float, Dict[str, Any]] = {}
    for row in report.get("top5", []):
        threshold = round(safe_float(row.get("threshold")), 2)
        threshold_map[threshold] = row
    best = report.get("best", {})
    if best:
        threshold = round(safe_float(best.get("threshold")), 2)
        threshold_map[threshold] = best
    return threshold_map


def write_summary_markdown(output_path: Path, threshold_report: Dict[str, Any], latency_report: Dict[str, Any]) -> None:
    best = threshold_report["best"]
    threshold_map = build_threshold_map(threshold_report)
    t61 = threshold_map.get(0.61, best)
    t66 = threshold_map.get(0.66, best)

    fp_reduction = percent_change(safe_float(t66.get("fp")), safe_float(t61.get("fp")))
    accuracy_delta = safe_float(t66.get("accuracy")) - safe_float(t61.get("accuracy"))
    precision_delta = safe_float(t66.get("precision")) - safe_float(t61.get("precision"))
    recall_delta = safe_float(t66.get("recall")) - safe_float(t61.get("recall"))

    lines = [
        "# So lieu benchmark phuc vu bao cao",
        "",
        "## 1. Threshold can bang an toan hon",
        "",
        f"- Threshold = {safe_float(t66.get('threshold')):.2f}",
        f"- F1 = {safe_float(t66.get('f1')):.4f}",
        f"- Accuracy = {safe_float(t66.get('accuracy')):.4f}",
        f"- Precision = {safe_float(t66.get('precision')):.4f}",
        f"- Recall = {safe_float(t66.get('recall')):.4f}",
        f"- False Accept (FP) = {int(safe_float(t66.get('fp')))}",
        "",
        "### So sanh 0.61 va 0.66",
        "",
        "| Chi so | 0.61 | 0.66 | Chenh lech |",
        "|---|---:|---:|---:|",
        f"| Accuracy | {safe_float(t61.get('accuracy')):.4f} | {safe_float(t66.get('accuracy')):.4f} | {accuracy_delta:+.4f} |",
        f"| Precision | {safe_float(t61.get('precision')):.4f} | {safe_float(t66.get('precision')):.4f} | {precision_delta:+.4f} |",
        f"| Recall | {safe_float(t61.get('recall')):.4f} | {safe_float(t66.get('recall')):.4f} | {recall_delta:+.4f} |",
        f"| F1 | {safe_float(t61.get('f1')):.4f} | {safe_float(t66.get('f1')):.4f} | {safe_float(t66.get('f1')) - safe_float(t61.get('f1')):+.4f} |",
        f"| FP | {int(safe_float(t61.get('fp')))} | {int(safe_float(t66.get('fp')))} | {int(safe_float(t66.get('fp'))) - int(safe_float(t61.get('fp'))):+d} |",
        "",
        f"- FP giam {abs(fp_reduction):.2f}% khi chuyen tu 0.61 sang 0.66.",
        "",
        "## 2. Latency so khop",
        "",
        f"- Loop per query = {safe_float(latency_report.get('loop_per_query_ms')):.6f} ms",
        f"- FAISS single per query = {safe_float(latency_report.get('faiss_single_per_query_ms')):.6f} ms",
        f"- FAISS batch per query = {safe_float(latency_report.get('faiss_batch_per_query_ms')):.6f} ms",
        f"- Speedup single vs loop = {safe_float(latency_report.get('speedup_single_vs_loop')):.3f}x",
        f"- Speedup batch vs loop = {safe_float(latency_report.get('speedup_batch_vs_loop')):.3f}x",
        "",
        "## 3. Log ngan de dua vao bao cao",
        "",
        f"- Chon threshold = {safe_float(t66.get('threshold')):.2f} vi can bang giua an toan va do nhay.",
        f"- FAISS giup rut ngan thoi gian tim kiem tu {safe_float(latency_report.get('loop_per_query_ms')):.6f} ms/xu ly xuong {safe_float(latency_report.get('faiss_single_per_query_ms')):.6f} ms/xu ly.",
        "- He thong luu ket qua qua API backend de tach loi AI khoi nghiep vu, de bao tri va mo rong.",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def plot_threshold_comparison(output_path: Path, threshold_report: Dict[str, Any]) -> None:
    threshold_map = build_threshold_map(threshold_report)
    left = threshold_map.get(0.61) or threshold_report["best"]
    right = threshold_map.get(0.66) or threshold_report["best"]

    labels = ["Accuracy", "Precision", "Recall", "F1"]
    left_values = [safe_float(left.get("accuracy")), safe_float(left.get("precision")), safe_float(left.get("recall")), safe_float(left.get("f1"))]
    right_values = [safe_float(right.get("accuracy")), safe_float(right.get("precision")), safe_float(right.get("recall")), safe_float(right.get("f1"))]

    x = list(range(len(labels)))
    width = 0.35

    plt.figure(figsize=(10, 5.5))
    plt.bar([i - width / 2 for i in x], left_values, width=width, label="Threshold 0.61")
    plt.bar([i + width / 2 for i in x], right_values, width=width, label="Threshold 0.66")
    plt.xticks(x, labels)
    plt.ylim(0, 1.0)
    plt.ylabel("Score")
    plt.title("So sanh chi so hieu nang theo threshold")
    plt.grid(axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_top5_curve(output_path: Path, threshold_report: Dict[str, Any]) -> None:
    rows = sorted(threshold_report.get("top5", []), key=lambda item: safe_float(item.get("threshold")))
    if not rows:
        return

    thresholds = [safe_float(row.get("threshold")) for row in rows]
    accuracy = [safe_float(row.get("accuracy")) for row in rows]
    precision = [safe_float(row.get("precision")) for row in rows]
    recall = [safe_float(row.get("recall")) for row in rows]
    f1 = [safe_float(row.get("f1")) for row in rows]

    plt.figure(figsize=(10, 5.5))
    plt.plot(thresholds, accuracy, marker="o", label="Accuracy")
    plt.plot(thresholds, precision, marker="o", label="Precision")
    plt.plot(thresholds, recall, marker="o", label="Recall")
    plt.plot(thresholds, f1, marker="o", label="F1")
    plt.xlabel("Threshold")
    plt.ylabel("Score")
    plt.title("Top 5 threshold tot nhat")
    plt.ylim(0, 1.0)
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_latency_comparison(output_path: Path, latency_report: Dict[str, Any]) -> None:
    labels = ["Loop", "FAISS single", "FAISS batch"]
    values = [
        safe_float(latency_report.get("loop_per_query_ms")),
        safe_float(latency_report.get("faiss_single_per_query_ms")),
        safe_float(latency_report.get("faiss_batch_per_query_ms")),
    ]

    plt.figure(figsize=(9, 5.5))
    bars = plt.bar(labels, values, color=["#6c757d", "#198754", "#0d6efd"])
    plt.ylabel("Milliseconds per query")
    plt.title("So sanh latency nhan dien")
    plt.yscale("log")
    plt.grid(axis="y", alpha=0.25, which="both")

    for bar, value in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.6f} ms", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Word-ready charts and summary files from benchmark JSON")
    parser.add_argument("--threshold-report", default="benchmarks/threshold_report.json")
    parser.add_argument("--latency-report", default="benchmarks/p2_latency.json")
    parser.add_argument("--output-dir", default="reports/word_assets")
    args = parser.parse_args()

    threshold_path = Path(args.threshold_report)
    latency_path = Path(args.latency_report)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    threshold_report = load_json(threshold_path)
    latency_report = load_json(latency_path)

    plot_threshold_comparison(output_dir / "threshold_061_vs_066.png", threshold_report)
    plot_top5_curve(output_dir / "threshold_top5_curve.png", threshold_report)
    plot_latency_comparison(output_dir / "latency_comparison.png", latency_report)
    write_summary_markdown(output_dir / "summary_for_word.md", threshold_report, latency_report)

    print(f"Da tao tai lieu bieu do tai: {output_dir}")
    print(f"- {output_dir / 'threshold_061_vs_066.png'}")
    print(f"- {output_dir / 'threshold_top5_curve.png'}")
    print(f"- {output_dir / 'latency_comparison.png'}")
    print(f"- {output_dir / 'summary_for_word.md'}")


if __name__ == "__main__":
    main()