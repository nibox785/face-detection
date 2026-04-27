import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple
import sys

import cv2
import numpy as np

# Ensure project root is importable when running as `python scripts/...py`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from face_engine.facenet.detect import detect_faces
from face_engine.facenet.embedding import get_embedding_with_liveness

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_SPOOF_REJECT_THRESHOLD = 0.65


def read_image(path: Path):
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
        if raw.size > 0:
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if image is not None:
                return image
    except Exception:
        pass

    return cv2.imread(str(path))


def iter_images(folder: Path):
    if not folder.exists():
        return
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def select_best_face(faces_with_bbox: List[Tuple[np.ndarray, dict]]):
    if not faces_with_bbox:
        return None

    def score(item):
        _face, bbox = item
        conf = float(bbox.get("confidence", 0.0))
        w = float(max(0, bbox.get("w", 0)))
        h = float(max(0, bbox.get("h", 0)))
        return conf * (w * h)

    return max(faces_with_bbox, key=score)


def evaluate_folder(folder: Path, ground_truth: str, spoof_reject_threshold: float):
    rows = []
    for image_path in iter_images(folder):
        row = {
            "image": str(image_path),
            "ground_truth": ground_truth,
            "predicted": "attack",
            "is_real": False,
            "spoof_score": 1.0,
            "face_detected": False,
            "error": None,
        }

        try:
            frame = read_image(image_path)
            if frame is None:
                row["error"] = "cannot_read_image"
                rows.append(row)
                continue

            faces = detect_faces(frame)
            if not faces:
                row["error"] = "no_face_detected"
                rows.append(row)
                continue

            row["face_detected"] = True
            best = select_best_face(faces)
            if best is None:
                row["error"] = "best_face_not_found"
                rows.append(row)
                continue

            face_image, _bbox = best
            _embedding, is_real, spoof_score = get_embedding_with_liveness(face_image)
            row["is_real"] = bool(is_real)
            row["spoof_score"] = float(spoof_score)
            row["predicted"] = (
                "bona_fide"
                if (bool(is_real) and float(spoof_score) < float(spoof_reject_threshold))
                else "attack"
            )

        except Exception as e:
            row["error"] = str(e)

        rows.append(row)

    return rows


def safe_div(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def compute_metrics(rows: List[Dict]):
    bona = [r for r in rows if r["ground_truth"] == "bona_fide"]
    attack = [r for r in rows if r["ground_truth"] == "attack"]

    attack_as_real = sum(1 for r in attack if r["predicted"] == "bona_fide")
    bona_as_attack = sum(1 for r in bona if r["predicted"] == "attack")

    apcer = safe_div(attack_as_real, len(attack)) * 100.0
    bpcer = safe_div(bona_as_attack, len(bona)) * 100.0
    acer = (apcer + bpcer) / 2.0

    tp = sum(1 for r in bona if r["predicted"] == "bona_fide")
    tn = sum(1 for r in attack if r["predicted"] == "attack")
    fp = attack_as_real
    fn = bona_as_attack

    accuracy = safe_div(tp + tn, len(rows)) * 100.0

    return {
        "num_samples": len(rows),
        "num_bona_fide": len(bona),
        "num_attack": len(attack),
        "attack_as_real": attack_as_real,
        "bona_as_attack": bona_as_attack,
        "APCER": round(apcer, 4),
        "BPCER": round(bpcer, 4),
        "ACER": round(acer, 4),
        "accuracy": round(accuracy, 4),
        "confusion": {
            "TP_bona_fide": tp,
            "TN_attack": tn,
            "FP_attack_as_real": fp,
            "FN_bona_as_attack": fn,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark liveness metrics: APCER, BPCER, ACER")
    parser.add_argument("--dataset", default="dataset/liveness_eval", help="Dataset root containing bona_fide/ and attack/")
    parser.add_argument("--output", default="benchmarks/liveness_report.json", help="Output JSON report")
    parser.add_argument("--details", default="benchmarks/liveness_samples.json", help="Per-sample output JSON")
    parser.add_argument(
        "--spoof-threshold",
        type=float,
        default=DEFAULT_SPOOF_REJECT_THRESHOLD,
        help="Reject as attack if spoof_score >= threshold (used with is_real gate)",
    )
    args = parser.parse_args()

    dataset_root = Path(args.dataset)
    bona_dir = dataset_root / "bona_fide"
    attack_dir = dataset_root / "attack"

    if not bona_dir.exists() or not attack_dir.exists():
        raise SystemExit(
            "Dataset format required: <dataset>/bona_fide and <dataset>/attack directories"
        )

    rows = []
    rows.extend(evaluate_folder(bona_dir, "bona_fide", args.spoof_threshold))
    rows.extend(evaluate_folder(attack_dir, "attack", args.spoof_threshold))

    metrics = compute_metrics(rows)

    payload = {
        "dataset": str(dataset_root),
        "policy": {
            "predicted_bona_fide_if": "is_real == True and spoof_score < spoof_threshold",
            "spoof_threshold": args.spoof_threshold,
        },
        "metrics": metrics,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    details_path = Path(args.details)
    details_path.parent.mkdir(parents=True, exist_ok=True)
    details_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print("=== LIVENESS BENCHMARK ===")
    print(f"Samples: {metrics['num_samples']} | bona_fide: {metrics['num_bona_fide']} | attack: {metrics['num_attack']}")
    print(f"APCER: {metrics['APCER']:.4f}%")
    print(f"BPCER: {metrics['BPCER']:.4f}%")
    print(f"ACER : {metrics['ACER']:.4f}%")
    print(f"Accuracy: {metrics['accuracy']:.4f}%")
    print(f"Saved: {output_path}")
    print(f"Saved details: {details_path}")


if __name__ == "__main__":
    main()
