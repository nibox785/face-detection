import argparse
import glob
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List

import importlib

plt = importlib.import_module("matplotlib.pyplot")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def safe_std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(statistics.stdev(values))


def safe_p95(values: List[float]) -> float:
    if not values:
        return 0.0
    seq = sorted(values)
    idx = int(round(0.95 * (len(seq) - 1)))
    return float(seq[idx])


def extract_session_metrics(payload: Dict[str, Any]) -> Dict[str, float]:
    telemetry = payload.get("telemetryTimeline", [])
    latency_samples = [float(v) for v in payload.get("latencySamplesMs", []) if v is not None]
    decision_totals = payload.get("decisionTotals", {})
    events = payload.get("recognitionEvents", [])

    fps = [float(row.get("fps", 0.0)) for row in telemetry]
    api_pm = [float(row.get("apiCallsPerMin", 0.0)) for row in telemetry]

    total_decisions = max(1, sum(int(v) for v in decision_totals.values()))
    auto_ratio = float(decision_totals.get("AUTO_MARK", 0)) / total_decisions
    manual_ratio = float(decision_totals.get("MANUAL_REVIEW", 0)) / total_decisions
    reject_ratio = float(decision_totals.get("REJECT", 0)) / total_decisions

    face_counts = [float(row.get("faceCount", 0)) for row in events]
    recognized_counts = [float(row.get("recognizedCount", 0)) for row in events]

    return {
        "fps_mean": safe_mean(fps),
        "api_calls_pm_mean": safe_mean(api_pm),
        "latency_mean_ms": safe_mean(latency_samples),
        "latency_p95_ms": safe_p95(latency_samples),
        "auto_mark_ratio": auto_ratio,
        "manual_review_ratio": manual_ratio,
        "reject_ratio": reject_ratio,
        "face_count_mean": safe_mean(face_counts),
        "recognized_count_mean": safe_mean(recognized_counts),
    }


def aggregate_metrics(session_metrics: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    keys = list(session_metrics[0].keys()) if session_metrics else []
    result = {}
    for key in keys:
        values = []
        for row in session_metrics:
            try:
                values.append(float(row.get(key, 0.0)))
            except Exception:
                continue

        if not values:
            continue

        result[key] = {
            "mean": round(safe_mean(values), 6),
            "std": round(safe_std(values), 6),
            "min": round(min(values), 6) if values else 0.0,
            "max": round(max(values), 6) if values else 0.0,
        }
    return result


def write_summary_markdown(output_path: Path, aggregate: Dict[str, Dict[str, float]], n_sessions: int):
    lines = [
        "# Session stability summary",
        "",
        f"- Number of sessions: {n_sessions}",
        "",
        "## Aggregated metrics (mean +- std)",
        "",
        f"- FPS mean: {aggregate.get('fps_mean', {}).get('mean', 0):.3f} +- {aggregate.get('fps_mean', {}).get('std', 0):.3f}",
        f"- API calls/min mean: {aggregate.get('api_calls_pm_mean', {}).get('mean', 0):.3f} +- {aggregate.get('api_calls_pm_mean', {}).get('std', 0):.3f}",
        f"- Latency mean (ms): {aggregate.get('latency_mean_ms', {}).get('mean', 0):.3f} +- {aggregate.get('latency_mean_ms', {}).get('std', 0):.3f}",
        f"- Latency p95 (ms): {aggregate.get('latency_p95_ms', {}).get('mean', 0):.3f} +- {aggregate.get('latency_p95_ms', {}).get('std', 0):.3f}",
        f"- AUTO_MARK ratio: {aggregate.get('auto_mark_ratio', {}).get('mean', 0) * 100.0:.2f}% +- {aggregate.get('auto_mark_ratio', {}).get('std', 0) * 100.0:.2f}%",
        f"- MANUAL_REVIEW ratio: {aggregate.get('manual_review_ratio', {}).get('mean', 0) * 100.0:.2f}% +- {aggregate.get('manual_review_ratio', {}).get('std', 0) * 100.0:.2f}%",
        f"- REJECT ratio: {aggregate.get('reject_ratio', {}).get('mean', 0) * 100.0:.2f}% +- {aggregate.get('reject_ratio', {}).get('std', 0) * 100.0:.2f}%",
        "",
        "## Quick interpretation",
        "",
        "- STD nho hon cho thay he thong on dinh hon qua cac phien.",
        "- Theo doi dac biet latency_p95_ms va reject_ratio khi doi threshold.",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def plot_errorbars(output_path: Path, aggregate: Dict[str, Dict[str, float]]):
    labels = ["Latency mean", "Latency p95", "FPS", "API calls/min"]
    means = [
        aggregate.get("latency_mean_ms", {}).get("mean", 0.0),
        aggregate.get("latency_p95_ms", {}).get("mean", 0.0),
        aggregate.get("fps_mean", {}).get("mean", 0.0),
        aggregate.get("api_calls_pm_mean", {}).get("mean", 0.0),
    ]
    stds = [
        aggregate.get("latency_mean_ms", {}).get("std", 0.0),
        aggregate.get("latency_p95_ms", {}).get("std", 0.0),
        aggregate.get("fps_mean", {}).get("std", 0.0),
        aggregate.get("api_calls_pm_mean", {}).get("std", 0.0),
    ]

    plt.figure(figsize=(9.5, 5.5))
    x = list(range(len(labels)))
    plt.bar(x, means, yerr=stds, capsize=6, color=["#0d6efd", "#198754", "#f59f00", "#6f42c1"])
    plt.xticks(x, labels)
    plt.title("Session stability (mean +- std)")
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Aggregate multiple session telemetry JSON files and report std")
    parser.add_argument("--input-glob", default="reports/word_assets/session/session_metrics_*.json")
    parser.add_argument("--output", default="benchmarks/session_stability_report.json")
    parser.add_argument("--summary", default="reports/word_assets/session/session_stability_summary.md")
    parser.add_argument("--chart", default="reports/word_assets/session/session_stability_errorbars.png")
    args = parser.parse_args()

    files = sorted(glob.glob(args.input_glob))
    if not files:
        raise SystemExit(f"No files found for glob: {args.input_glob}")

    session_rows = []
    for fp in files:
        payload = load_json(Path(fp))
        metrics = extract_session_metrics(payload)
        metrics["file"] = fp
        session_rows.append(metrics)

    aggregate = aggregate_metrics(session_rows)

    out_payload = {
        "num_sessions": len(session_rows),
        "sessions": session_rows,
        "aggregate": aggregate,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_summary_markdown(summary_path, aggregate, len(session_rows))

    chart_path = Path(args.chart)
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    plot_errorbars(chart_path, aggregate)

    print("=== SESSION STABILITY BENCHMARK ===")
    print(f"Sessions: {len(session_rows)}")
    print(f"Saved: {output_path}")
    print(f"Saved summary: {summary_path}")
    print(f"Saved chart: {chart_path}")


if __name__ == "__main__":
    main()
