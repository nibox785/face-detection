import argparse
import itertools
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from face_engine.facenet.detect import detect_faces
from face_engine.facenet.embedding import get_embedding

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return -1.0
    return float(np.dot(a, b) / denom)


def iter_images(dataset_dir: Path):
    for student_dir in dataset_dir.iterdir():
        if not student_dir.is_dir():
            continue
        for image_path in student_dir.iterdir():
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                yield student_dir.name, image_path


def build_embeddings(dataset_dir: Path) -> Dict[str, List[np.ndarray]]:
    by_student: Dict[str, List[np.ndarray]] = {}

    for student_name, image_path in iter_images(dataset_dir):
        image = cv2.imread(str(image_path))
        if image is None:
            continue

        faces = detect_faces(image)
        if not faces:
            continue

        face_image, _bbox = faces[0]
        emb = get_embedding(face_image)
        by_student.setdefault(student_name, []).append(emb)

    return by_student


def build_pairs(by_student: Dict[str, List[np.ndarray]]) -> Tuple[List[float], List[float]]:
    positive_scores: List[float] = []
    negative_scores: List[float] = []

    # Positive pairs: cùng student
    for student_name, embs in by_student.items():
        if len(embs) < 2:
            continue
        for i, j in itertools.combinations(range(len(embs)), 2):
            positive_scores.append(cosine_similarity(embs[i], embs[j]))

    # Negative pairs: khác student
    students = list(by_student.keys())
    for i in range(len(students)):
        for j in range(i + 1, len(students)):
            for emb_a in by_student[students[i]]:
                for emb_b in by_student[students[j]]:
                    negative_scores.append(cosine_similarity(emb_a, emb_b))

    return positive_scores, negative_scores


def evaluate_threshold(threshold: float, positives: List[float], negatives: List[float]):
    tp = sum(score >= threshold for score in positives)
    fn = sum(score < threshold for score in positives)
    fp = sum(score >= threshold for score in negatives)
    tn = sum(score < threshold for score in negatives)

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    return {
        "threshold": threshold,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark threshold cho nhận diện khuôn mặt")
    parser.add_argument("--dataset", default="dataset", help="Đường dẫn dataset root")
    parser.add_argument("--start", type=float, default=0.30, help="Threshold bắt đầu")
    parser.add_argument("--end", type=float, default=0.90, help="Threshold kết thúc")
    parser.add_argument("--step", type=float, default=0.01, help="Bước threshold")
    parser.add_argument("--output", default="benchmarks/threshold_report.json", help="File JSON kết quả benchmark")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    if not dataset_dir.exists():
        raise SystemExit(f"Dataset không tồn tại: {dataset_dir}")

    by_student = build_embeddings(dataset_dir)
    if len(by_student) < 2:
        raise SystemExit("Cần ít nhất 2 sinh viên trong dataset để benchmark")

    positives, negatives = build_pairs(by_student)
    if not positives or not negatives:
        raise SystemExit("Không đủ cặp positive/negative để benchmark")

    print(f"Students: {len(by_student)}")
    print(f"Positive pairs: {len(positives)}")
    print(f"Negative pairs: {len(negatives)}")

    results = []
    threshold = args.start
    while threshold <= args.end + 1e-9:
        results.append(evaluate_threshold(round(threshold, 4), positives, negatives))
        threshold += args.step

    best = max(results, key=lambda x: (x["f1"], x["accuracy"]))
    top5 = sorted(results, key=lambda x: (x["f1"], x["accuracy"]), reverse=True)[:5]

    print("\n=== BEST THRESHOLD ===")
    print(f"Threshold: {best['threshold']:.4f}")
    print(f"Accuracy : {best['accuracy']:.4f}")
    print(f"Precision: {best['precision']:.4f}")
    print(f"Recall   : {best['recall']:.4f}")
    print(f"F1       : {best['f1']:.4f}")
    print(f"Confusion: TP={best['tp']} FP={best['fp']} TN={best['tn']} FN={best['fn']}")

    print("\n=== TOP 5 THRESHOLDS (F1, Accuracy) ===")
    for row in top5:
        print(
            f"t={row['threshold']:.4f} | F1={row['f1']:.4f} | "
            f"Acc={row['accuracy']:.4f} | P={row['precision']:.4f} | R={row['recall']:.4f}"
        )

    report = {
        "dataset": str(dataset_dir),
        "students": len(by_student),
        "positive_pairs": len(positives),
        "negative_pairs": len(negatives),
        "best": best,
        "top5": top5,
        "range": {"start": args.start, "end": args.end, "step": args.step},
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved report: {out_path}")


if __name__ == "__main__":
    main()
