import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def read_text_if_exists(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_markdown(
    threshold_report: Dict[str, Any],
    latency_report: Dict[str, Any],
    session_payload: Optional[Dict[str, Any]],
    session_summary: str,
    liveness_report: Optional[Dict[str, Any]],
    stability_report: Optional[Dict[str, Any]],
) -> str:
    best = threshold_report.get("best", {})
    top5 = threshold_report.get("top5", [])
    students = int(threshold_report.get("students", 0))
    positive_pairs = int(threshold_report.get("positive_pairs", 0))
    negative_pairs = int(threshold_report.get("negative_pairs", 0))

    loop_ms = safe_float(latency_report.get("loop_per_query_ms"))
    faiss_single_ms = safe_float(latency_report.get("faiss_single_per_query_ms"))
    faiss_batch_ms = safe_float(latency_report.get("faiss_batch_per_query_ms"))
    speedup_single = safe_float(latency_report.get("speedup_single_vs_loop"))
    speedup_batch = safe_float(latency_report.get("speedup_batch_vs_loop"))

    lines = [
        "# Chuong 4 - Ket qua thuc nghiem",
        "",
        "## 4.1 Cau hinh va du lieu",
        "",
        f"- So luong danh tinh benchmark threshold: {students}",
        f"- So cap positive: {positive_pairs}",
        f"- So cap negative: {negative_pairs}",
        f"- Kich thuoc embedding: {latency_report.get('dimension', 'N/A')}",
        "",
        "## 4.2 Ket qua toi uu nguong nhan dien",
        "",
        f"- Best threshold: {safe_float(best.get('threshold')):.2f}",
        f"- Accuracy: {safe_float(best.get('accuracy')):.4f}",
        f"- Precision: {safe_float(best.get('precision')):.4f}",
        f"- Recall: {safe_float(best.get('recall')):.4f}",
        f"- F1-score: {safe_float(best.get('f1')):.4f}",
        f"- Confusion: TP={int(safe_float(best.get('tp')))}, FP={int(safe_float(best.get('fp')))}, TN={int(safe_float(best.get('tn')))}, FN={int(safe_float(best.get('fn')))}",
        "",
        "Bang top-5 threshold co the trinh bay trong phu luc:",
    ]

    for row in top5:
        lines.append(
            f"- t={safe_float(row.get('threshold')):.2f} | Acc={safe_float(row.get('accuracy')):.4f} | P={safe_float(row.get('precision')):.4f} | R={safe_float(row.get('recall')):.4f} | F1={safe_float(row.get('f1')):.4f}"
        )

    lines.extend([
        "",
        "Hinh de chen:",
        "- reports/word_assets/threshold_061_vs_066.png",
        "- reports/word_assets/threshold_top5_curve.png",
        "",
        "## 4.3 Ket qua toc do nhan dien (latency)",
        "",
        f"- Loop baseline: {loop_ms:.6f} ms/query",
        f"- FAISS single: {faiss_single_ms:.6f} ms/query",
        f"- FAISS batch: {faiss_batch_ms:.6f} ms/query",
        f"- Speedup single vs loop: {speedup_single:.3f}x",
        f"- Speedup batch vs loop: {speedup_batch:.3f}x",
        "",
        "Hinh de chen:",
        "- reports/word_assets/latency_comparison.png",
        "",
        "## 4.4 Ket qua telemetry theo phien",
        "",
    ])

    if session_payload:
        meta = session_payload.get("meta", {})
        decision_totals = session_payload.get("decisionTotals", {})
        latencies = [safe_float(v) for v in session_payload.get("latencySamplesMs", [])]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p95_idx = int(round(0.95 * (len(latencies) - 1))) if latencies else 0
        p95_latency = sorted(latencies)[p95_idx] if latencies else 0.0
        total_decisions = max(1, sum(int(v) for v in decision_totals.values()))

        lines.extend([
            f"- Session started at: {meta.get('startedAt', 'N/A')}",
            f"- Recognition interval: {meta.get('recognitionIntervalMs', 'N/A')} ms",
            f"- So mau latency: {len(latencies)}",
            f"- Latency trung binh phien: {avg_latency:.2f} ms",
            f"- Latency p95 phien: {p95_latency:.2f} ms",
            f"- AUTO_MARK: {int(decision_totals.get('AUTO_MARK', 0))} ({int(decision_totals.get('AUTO_MARK', 0)) / total_decisions * 100.0:.2f}%)",
            f"- MANUAL_REVIEW: {int(decision_totals.get('MANUAL_REVIEW', 0))} ({int(decision_totals.get('MANUAL_REVIEW', 0)) / total_decisions * 100.0:.2f}%)",
            f"- REJECT: {int(decision_totals.get('REJECT', 0))} ({int(decision_totals.get('REJECT', 0)) / total_decisions * 100.0:.2f}%)",
            "",
            "Hinh de chen:",
            "- reports/word_assets/session/session_latency_timeline.png",
            "- reports/word_assets/session/session_fps_api_timeline.png",
            "- reports/word_assets/session/session_decision_ratio.png",
            "",
        ])
    else:
        lines.extend([
            "- Chua co du lieu session telemetry. Hay xuat JSON phien tu Attendance panel va chay generate_session_report_assets.py.",
            "",
        ])

    lines.extend([
        "## 4.5 Chi so anti-spoofing (APCER, BPCER, ACER)",
        "",
    ])

    if liveness_report:
        m = liveness_report.get("metrics", {})
        lines.extend([
            f"- So mau liveness: {int(safe_float(m.get('num_samples')))} (bona_fide={int(safe_float(m.get('num_bona_fide')))}, attack={int(safe_float(m.get('num_attack')))} )",
            f"- APCER: {safe_float(m.get('APCER')):.4f}%",
            f"- BPCER: {safe_float(m.get('BPCER')):.4f}%",
            f"- ACER: {safe_float(m.get('ACER')):.4f}%",
            f"- Liveness accuracy: {safe_float(m.get('accuracy')):.4f}%",
            "- File tham chieu: benchmarks/liveness_report.json",
            "",
        ])
    else:
        lines.extend([
            "- Chua co liveness_report.json. Hay chay benchmark_liveness_metrics.py de bo sung APCER/BPCER/ACER.",
            "",
        ])

    lines.extend([
        "## 4.6 Do on dinh qua nhieu phien (mean +- std)",
        "",
    ])

    if stability_report:
        agg = stability_report.get("aggregate", {})
        num_sessions = int(safe_float(stability_report.get("num_sessions", 0)))
        lines.extend([
            f"- So phien duoc benchmark: {num_sessions}",
            f"- FPS mean +- std: {safe_float(agg.get('fps_mean', {}).get('mean')):.3f} +- {safe_float(agg.get('fps_mean', {}).get('std')):.3f}",
            f"- API calls/min mean +- std: {safe_float(agg.get('api_calls_pm_mean', {}).get('mean')):.3f} +- {safe_float(agg.get('api_calls_pm_mean', {}).get('std')):.3f}",
            f"- Latency mean (ms) mean +- std: {safe_float(agg.get('latency_mean_ms', {}).get('mean')):.3f} +- {safe_float(agg.get('latency_mean_ms', {}).get('std')):.3f}",
            f"- Latency p95 (ms) mean +- std: {safe_float(agg.get('latency_p95_ms', {}).get('mean')):.3f} +- {safe_float(agg.get('latency_p95_ms', {}).get('std')):.3f}",
            f"- AUTO_MARK ratio mean +- std: {safe_float(agg.get('auto_mark_ratio', {}).get('mean')) * 100.0:.2f}% +- {safe_float(agg.get('auto_mark_ratio', {}).get('std')) * 100.0:.2f}%",
            f"- MANUAL_REVIEW ratio mean +- std: {safe_float(agg.get('manual_review_ratio', {}).get('mean')) * 100.0:.2f}% +- {safe_float(agg.get('manual_review_ratio', {}).get('std')) * 100.0:.2f}%",
            f"- REJECT ratio mean +- std: {safe_float(agg.get('reject_ratio', {}).get('mean')) * 100.0:.2f}% +- {safe_float(agg.get('reject_ratio', {}).get('std')) * 100.0:.2f}%",
            "",
            "Hinh de chen:",
            "- reports/word_assets/session/session_stability_errorbars.png",
            "",
        ])
    else:
        lines.extend([
            "- Chua co session_stability_report.json. Hay chay benchmark_session_stability.py tren nhieu session JSON.",
            "",
        ])

    lines.extend([
        "## 4.7 Tong hop dong gop ky thuat",
        "",
        "- He thong ket hop detect + embedding + liveness gate trong mot luong suy dien thong nhat.",
        "- Co che tim kiem FAISS giup cai thien ro rang ve latency so voi loop baseline.",
        "- Giao dien telemetry va top-3 confidence tang kha nang giai thich quyet dinh nhan dien.",
        "- Quy trinh sinh report duoc tu dong hoa de su dung lai cho cac lan benchmark tiep theo.",
        "",
        "## 4.8 Ban luan va han che",
        "",
        "- Du lieu threshold hien tai con nho, can mo rong danh tinh va dieu kien moi truong.",
        "- Can benchmark nhieu phien va bao cao do lech chuan de ket luan on dinh hon.",
        "",
    ])

    if session_summary:
        lines.extend([
            "## 4.9 Trich doan session summary",
            "",
            "Noi dung duoi day duoc trich tu file session summary:",
            "",
            session_summary,
            "",
        ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate chapter-4 markdown for thesis Word report")
    parser.add_argument("--threshold-report", default="benchmarks/threshold_report.json")
    parser.add_argument("--latency-report", default="benchmarks/p2_latency.json")
    parser.add_argument("--session-json", default="", help="Optional: exported session_metrics_*.json")
    parser.add_argument("--session-summary", default="reports/word_assets/session/session_summary_for_word.md")
    parser.add_argument("--liveness-report", default="benchmarks/liveness_report.json")
    parser.add_argument("--stability-report", default="benchmarks/session_stability_report.json")
    parser.add_argument("--output", default="reports/word_assets/chapter4_results.md")
    args = parser.parse_args()

    threshold_report = load_json(Path(args.threshold_report))
    latency_report = load_json(Path(args.latency_report))

    session_payload = None
    if args.session_json:
        session_path = Path(args.session_json)
        if session_path.exists():
            session_payload = load_json(session_path)

    liveness_report = None
    liveness_path = Path(args.liveness_report)
    if liveness_path.exists():
        liveness_report = load_json(liveness_path)

    stability_report = None
    stability_path = Path(args.stability_report)
    if stability_path.exists():
        stability_report = load_json(stability_path)

    session_summary_text = read_text_if_exists(Path(args.session_summary))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = build_markdown(
        threshold_report,
        latency_report,
        session_payload,
        session_summary_text,
        liveness_report,
        stability_report,
    )
    output_path.write_text(markdown, encoding="utf-8")

    print(f"Generated thesis markdown: {output_path}")


if __name__ == "__main__":
    main()
