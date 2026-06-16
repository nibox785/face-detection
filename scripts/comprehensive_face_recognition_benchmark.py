"""
Comprehensive Face Recognition Benchmark with Liveness Detection
=================================================================

Script này thực hiện benchmark toàn diện cho hệ thống nhận diện khuôn mặt với anti-spoofing.

Logic xử lý:
1. Load dataset: Đọc ảnh từ folder dataset, group theo student.
2. Build embeddings: Trích xuất embedding cho mỗi ảnh, lưu theo student.
3. Build FAISS index: Tạo index FAISS để tìm kiếm nhanh.
4. Test recognition: Với mỗi test image, detect face, extract embedding+liveness, search FAISS, decision.
5. Calculate metrics: Tính accuracy, FAR, FRR, APCER, BPCER, ACER.

Giải thích số liệu:
- Accuracy: Tỷ lệ dự đoán đúng (TP + TN) / total.
- FAR (False Acceptance Rate): Tỷ lệ attack được chấp nhận sai (FP / (FP + TN)).
- FRR (False Rejection Rate): Tỷ lệ bona fide bị reject sai (FN / (FN + TP)).
- APCER (Attack Presentation Classification Error Rate): FAR cho attack samples.
- BPCER (Bona Fide Presentation Classification Error Rate): FRR cho bona fide samples.
- ACER (Average Classification Error Rate): (APCER + BPCER) / 2.

Ngưỡng:
- Recognition threshold: Cosine similarity > threshold để match.
- Liveness threshold: Spoof score < threshold để accept (real nếu score thấp).

Usage: python scripts/comprehensive_face_recognition_benchmark.py --dataset dataset/ --threshold 0.7 --liveness_threshold 0.65
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from face_engine.facenet.detect import detect_faces
from face_engine.facenet.embedding import get_embedding_with_liveness
from backend.services.faiss_search import FAISSEmbeddingIndex

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def read_image(path: Path) -> Optional[np.ndarray]:
    """Đọc ảnh robust với Unicode paths."""
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
        if raw.size > 0:
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if image is not None:
                return image
    except Exception:
        pass
    return cv2.imread(str(path))


def iter_images(dataset_dir: Path):
    """Iterate qua tất cả ảnh trong dataset, yield (student_name, image_path)."""
    for student_dir in dataset_dir.iterdir():
        if not student_dir.is_dir():
            continue
        for image_path in student_dir.iterdir():
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                yield student_dir.name, image_path


def build_student_embeddings(dataset_dir: Path) -> Dict[str, List[np.ndarray]]:
    """
    Xây dựng embeddings cho mỗi student từ dataset.

    Logic:
    - Với mỗi student folder, đọc tất cả ảnh.
    - Detect face, extract embedding (không liveness, vì đây là DB).
    - Lưu list embeddings per student.
    """
    by_student: Dict[str, List[np.ndarray]] = {}

    for student_name, image_path in iter_images(dataset_dir):
        if student_name not in by_student:
            by_student[student_name] = []

        frame = read_image(image_path)
        if frame is None:
            continue

        # Detect faces
        faces = detect_faces(frame)
        if not faces:
            continue

        # Chọn face tốt nhất (confidence cao nhất)
        best_face = max(faces, key=lambda x: x[1].get("confidence", 0.0))
        face_image, _ = best_face

        # Extract embedding (không liveness cho DB)
        try:
            embedding = get_embedding_with_liveness(face_image)[0]  # Chỉ lấy embedding
            by_student[student_name].append(embedding)
        except Exception as e:
            logger.warning(f"Skip {image_path}: {e}")

    # Filter students có ít nhất 1 embedding
    by_student = {k: v for k, v in by_student.items() if v}
    logger.info(f"Built embeddings for {len(by_student)} students")
    return by_student


def build_faiss_index(student_embeddings: Dict[str, List[np.ndarray]]) -> FAISSEmbeddingIndex:
    """
    Xây dựng FAISS index từ embeddings.

    Logic:
    - Gán student_id cho mỗi student.
    - Flatten tất cả embeddings, lưu mapping student_id -> embeddings.
    """
    index = FAISSEmbeddingIndex(dim=512)
    db_embeddings = []

    for student_id, (student_name, embeddings) in enumerate(student_embeddings.items()):
        for emb in embeddings:
            db_embeddings.append((student_id, emb))

    index.build(db_embeddings)
    logger.info(f"Built FAISS index with {len(db_embeddings)} embeddings")
    return index


def test_recognition(
    test_dir: Path,
    faiss_index: FAISSEmbeddingIndex,
    student_embeddings: Dict[str, List[np.ndarray]],
    recognition_threshold: float,
    liveness_threshold: float
) -> List[Dict]:
    """
    Test recognition trên test set.

    Logic per image:
    - Detect face.
    - Extract embedding + liveness.
    - Nếu liveness fail (is_real=False hoặc spoof_score >= threshold), reject.
    - Search FAISS top-k.
    - Match nếu cosine > recognition_threshold với đúng student.

    Return list results cho metrics calculation.
    """
    results = []
    student_names = list(student_embeddings.keys())

    for true_student, image_path in iter_images(test_dir):
        result = {
            "image": str(image_path),
            "true_student": true_student,
            "predicted_student": None,
            "confidence": 0.0,
            "face_detected": False,
            "liveness_pass": False,
            "is_real": False,
            "spoof_score": 1.0,
            "error": None,
        }

        try:
            frame = read_image(image_path)
            if frame is None:
                result["error"] = "cannot_read_image"
                results.append(result)
                continue

            # Detect faces
            faces = detect_faces(frame)
            if not faces:
                result["error"] = "no_face_detected"
                results.append(result)
                continue

            result["face_detected"] = True
            best_face = max(faces, key=lambda x: x[1].get("confidence", 0.0))
            face_image, _ = best_face

            # Extract embedding + liveness
            embedding, is_real, spoof_score = get_embedding_with_liveness(face_image)
            result["is_real"] = is_real
            result["spoof_score"] = spoof_score

            # Liveness check
            if not is_real or spoof_score >= liveness_threshold:
                result["error"] = "liveness_fail"
                results.append(result)
                continue

            result["liveness_pass"] = True

            # Search FAISS
            distances, indices = faiss_index.search(embedding.reshape(1, -1), k=5)
            if indices[0][0] == -1:  # No match
                result["error"] = "no_match"
                results.append(result)
                continue

            # Get best match
            best_idx = indices[0][0]
            best_distance = distances[0][0]
            predicted_student_id = faiss_index.student_ids[best_idx]
            predicted_student = student_names[predicted_student_id]
            confidence = 1.0 - best_distance  # Cosine similarity

            result["predicted_student"] = predicted_student
            result["confidence"] = confidence

            # Decision
            if confidence >= recognition_threshold and predicted_student == true_student:
                result["correct"] = True
            else:
                result["correct"] = False

        except Exception as e:
            result["error"] = str(e)

        results.append(result)

    return results


def calculate_metrics(results: List[Dict]) -> Dict:
    """
    Tính toán metrics từ results.

    Logic:
    - Bona fide: liveness_pass and predicted đúng.
    - Attack: Không phải bona fide (giả sử test set có attack images, nhưng ở đây chỉ bona fide).
    - FAR: Attack accepted (không áp dụng ở đây).
    - FRR: Bona fide rejected.
    """
    total = len(results)
    bona_fide_correct = sum(1 for r in results if r.get("liveness_pass") and r.get("correct"))
    bona_fide_total = sum(1 for r in results if r.get("face_detected") and r.get("liveness_pass") is not False)
    rejected = sum(1 for r in results if not r.get("liveness_pass"))

    accuracy = bona_fide_correct / total if total > 0 else 0
    frr = (bona_fide_total - bona_fide_correct) / bona_fide_total if bona_fide_total > 0 else 0

    # APCER/BPCER giả sử không có attack samples
    apcer = 0.0  # FAR
    bpcer = frr  # FRR
    acer = (apcer + bpcer) / 2

    return {
        "total_samples": total,
        "bona_fide_correct": bona_fide_correct,
        "bona_fide_total": bona_fide_total,
        "rejected": rejected,
        "accuracy": round(accuracy * 100, 2),
        "FRR": round(frr * 100, 2),
        "APCER": round(apcer * 100, 2),
        "BPCER": round(bpcer * 100, 2),
        "ACER": round(acer * 100, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Comprehensive Face Recognition Benchmark")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to dataset directory")
    parser.add_argument("--test_dir", type=Path, help="Path to test directory (default: same as dataset)")
    parser.add_argument("--recognition_threshold", type=float, default=0.7, help="Cosine similarity threshold for recognition")
    parser.add_argument("--liveness_threshold", type=float, default=0.65, help="Spoof score threshold for liveness")
    parser.add_argument("--output", type=Path, default="comprehensive_benchmark_report.json", help="Output JSON file")

    args = parser.parse_args()

    if not args.test_dir:
        args.test_dir = args.dataset

    # Build embeddings
    logger.info("Building student embeddings...")
    student_embeddings = build_student_embeddings(args.dataset)

    # Build FAISS index
    logger.info("Building FAISS index...")
    faiss_index = build_faiss_index(student_embeddings)

    # Test recognition
    logger.info("Testing recognition...")
    results = test_recognition(args.test_dir, faiss_index, student_embeddings, args.recognition_threshold, args.liveness_threshold)

    # Calculate metrics
    metrics = calculate_metrics(results)

    # Save report
    report = {
        "config": {
            "dataset": str(args.dataset),
            "test_dir": str(args.test_dir),
            "recognition_threshold": args.recognition_threshold,
            "liveness_threshold": args.liveness_threshold,
        },
        "metrics": metrics,
        "results": results[:10],  # Sample first 10 results
    }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Report saved to {args.output}")
    logger.info(f"Metrics: Accuracy={metrics['accuracy']}%, FRR={metrics['FRR']}%, ACER={metrics['ACER']}%")


if __name__ == "__main__":
    main()