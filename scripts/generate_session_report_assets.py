import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List

import importlib

plt = importlib.import_module("matplotlib.pyplot")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Khong tim thay file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_mean(values: List[float]) -> float:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return 0.0
    return float(sum(clean) / len(clean))


def safe_p95(values: List[float]) -> float:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return 0.0
    idx = int(round(0.95 * (len(clean) - 1)))
    return clean[idx]


def plot_latency_timeline(output_path: Path, telemetry_rows: List[Dict[str, Any]]):
    if not telemetry_rows:
        return

    x = list(range(len(telemetry_rows)))
    last_latency = [float(row.get("lastLatencyMs", 0.0)) for row in telemetry_rows]
    avg_latency = [float(row.get("avgLatencyMs", 0.0)) for row in telemetry_rows]

    plt.figure(figsize=(10, 5.2))
    plt.plot(x, last_latency, label="Latency gan nhat (ms)", linewidth=1.8)
    plt.plot(x, avg_latency, label="Latency trung binh dong (ms)", linewidth=1.8)
    plt.xlabel("Moc thoi gian (giay)")
    plt.ylabel("Latency (ms)")
    plt.title("Dien bien latency trong phien diem danh")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_fps_api_timeline(output_path: Path, telemetry_rows: List[Dict[str, Any]]):
    if not telemetry_rows:
        return

    x = list(range(len(telemetry_rows)))
    fps = [float(row.get("fps", 0.0)) for row in telemetry_rows]
    api_pm = [float(row.get("apiCallsPerMin", 0.0)) for row in telemetry_rows]

    fig, ax1 = plt.subplots(figsize=(10, 5.2))
    ax1.plot(x, fps, color="#0d6efd", label="FPS overlay", linewidth=1.8)
    ax1.set_xlabel("Moc thoi gian (giay)")
    ax1.set_ylabel("FPS", color="#0d6efd")
    ax1.tick_params(axis="y", labelcolor="#0d6efd")
    ax1.grid(True, alpha=0.25)

    ax2 = ax1.twinx()
    ax2.plot(x, api_pm, color="#198754", label="API calls/phut", linewidth=1.8)
    ax2.set_ylabel("API calls/phut", color="#198754")
    ax2.tick_params(axis="y", labelcolor="#198754")

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc="upper right")

    plt.title("On dinh render va toc do goi API theo thoi gian")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_decision_ratio(output_path: Path, decision_totals: Dict[str, Any]):
    labels = ["AUTO_MARK", "MANUAL_REVIEW", "REJECT"]
    values = [
        int(decision_totals.get("AUTO_MARK", 0)),
        int(decision_totals.get("MANUAL_REVIEW", 0)),
        int(decision_totals.get("REJECT", 0)),
    ]

    plt.figure(figsize=(8.5, 5.0))
    colors = ["#198754", "#f59f00", "#dc3545"]
    bars = plt.bar(labels, values, color=colors)
    plt.ylabel("So lan")
    plt.title("Phan bo quyet dinh trong phien nhan dien")
    plt.grid(axis="y", alpha=0.2)

    for bar, value in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(value), ha="center", va="bottom")

    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()


def write_summary(output_path: Path, payload: Dict[str, Any]):
    telemetry_rows = payload.get("telemetryTimeline", [])
    latencies = payload.get("latencySamplesMs", [])
    decisions = payload.get("decisionTotals", {})
    events = payload.get("recognitionEvents", [])

    face_counts = [int(row.get("faceCount", 0)) for row in events]
    recognized_counts = [int(row.get("recognizedCount", 0)) for row in events]

    total_decisions = sum(int(v) for v in decisions.values())
    auto_ratio = (int(decisions.get("AUTO_MARK", 0)) / total_decisions * 100.0) if total_decisions else 0.0
    manual_ratio = (int(decisions.get("MANUAL_REVIEW", 0)) / total_decisions * 100.0) if total_decisions else 0.0
    reject_ratio = (int(decisions.get("REJECT", 0)) / total_decisions * 100.0) if total_decisions else 0.0

    fps_values = [float(row.get("fps", 0)) for row in telemetry_rows]
    api_values = [float(row.get("apiCallsPerMin", 0)) for row in telemetry_rows]

    lines = [
        "# Tong hop phien telemetry cho bao cao",
        "",
        "## 1. Thong tin phien",
        "",
        f"- Started at: {payload.get('meta', {}).get('startedAt', 'N/A')}",
        f"- Exported at: {payload.get('meta', {}).get('exportedAt', 'N/A')}",
        f"- Recognition interval (ms): {payload.get('meta', {}).get('recognitionIntervalMs', 'N/A')}",
        f"- So moc telemetry: {len(telemetry_rows)}",
        f"- So su kien recognize: {len(events)}",
        "",
        "## 2. Chi so hieu nang",
        "",
        f"- FPS trung binh: {safe_mean(fps_values):.2f}",
        f"- API calls/phut trung binh: {safe_mean(api_values):.2f}",
        f"- Latency trung binh: {safe_mean(latencies):.2f} ms",
        f"- Latency p95: {safe_p95(latencies):.2f} ms",
        f"- Face count trung binh/event: {safe_mean(face_counts):.2f}",
        f"- Recognized count trung binh/event: {safe_mean(recognized_counts):.2f}",
        "",
        "## 3. Phan bo quyet dinh",
        "",
        f"- AUTO_MARK: {int(decisions.get('AUTO_MARK', 0))} ({auto_ratio:.2f}%)",
        f"- MANUAL_REVIEW: {int(decisions.get('MANUAL_REVIEW', 0))} ({manual_ratio:.2f}%)",
        f"- REJECT: {int(decisions.get('REJECT', 0))} ({reject_ratio:.2f}%)",
        "",
        "## 4. Nhan xet nhanh",
        "",
        "- Neu MANUAL_REVIEW cao: can canh chinh threshold hoac cai thien chat luong anh dau vao.",
        "- Neu REJECT cao: kiem tra liveness threshold va dieu kien camera/anh sang.",
        "- So sanh latency p95 giua cac phien de theo doi on dinh he thong.",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Generate Word assets from exported session telemetry JSON")
    parser.add_argument("--input", required=True, help="Path to session_metrics_*.json exported from frontend")
    parser.add_argument("--output-dir", default="reports/word_assets/session", help="Output directory")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = load_json(input_path)
    telemetry_rows = payload.get("telemetryTimeline", [])
    decision_totals = payload.get("decisionTotals", {})

    plot_latency_timeline(output_dir / "session_latency_timeline.png", telemetry_rows)
    plot_fps_api_timeline(output_dir / "session_fps_api_timeline.png", telemetry_rows)
    plot_decision_ratio(output_dir / "session_decision_ratio.png", decision_totals)
    write_summary(output_dir / "session_summary_for_word.md", payload)

    print("Da tao xong word assets cho session:")
    print(f"- {output_dir / 'session_latency_timeline.png'}")
    print(f"- {output_dir / 'session_fps_api_timeline.png'}")
    print(f"- {output_dir / 'session_decision_ratio.png'}")
    print(f"- {output_dir / 'session_summary_for_word.md'}")


if __name__ == "__main__":
    main()
