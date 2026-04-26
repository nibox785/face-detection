import numpy as np
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger("face-attendance.face_service")


class FaceService:
    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        logger.info(f"FaceService được khởi tạo với threshold = {threshold}")

    def detect(self, frame):
        """Phát hiện khuôn mặt trong ảnh"""
        try:
            # Lazy import để tránh circular import
            from face_engine.facenet.detect import detect_faces
            faces = detect_faces(frame)
            logger.debug(f"Detect faces: tìm thấy {len(faces)} khuôn mặt")
            return faces
        except Exception as e:
            logger.error(f"Lỗi khi detect faces: {str(e)}", exc_info=True)
            return []

    def extract_embedding(self, face_image):
        """Trích xuất embedding từ khuôn mặt (không liveness)"""
        try:
            from face_engine.facenet.embedding import get_embedding
            embedding = get_embedding(face_image)
            logger.debug(f"Extract embedding thành công, shape: {embedding.shape}")
            return embedding
        except Exception as e:
            logger.error(f"Lỗi khi extract embedding: {str(e)}", exc_info=True)
            raise

    def get_embedding_with_liveness(self, face_image):
        """
        Trích xuất embedding + kiểm tra Liveness (Anti-Spoofing)
        Trả về: (embedding, is_real, spoof_score)
        """
        try:
            from face_engine.facenet.embedding import get_embedding_with_liveness
            embedding, is_real, spoof_score = get_embedding_with_liveness(face_image)
            logger.debug(f"Liveness check - is_real: {is_real}, spoof_score: {spoof_score:.4f}")
            return embedding, is_real, spoof_score
        except Exception as e:
            logger.error(f"Lỗi khi extract embedding with liveness: {str(e)}", exc_info=True)
            # FAIL-CLOSED: Reject frame khi liveness check lỗi
            logger.warning("⚠️ Liveness check failed in FaceService - rejecting for safety")
            embedding = self.extract_embedding(face_image)
            return embedding, False, 1.0  # is_real=False để bắt buộc reject

    def cosine_similarity(self, emb1, emb2):
        """Tính cosine similarity giữa 2 embedding"""
        try:
            return float(np.dot(emb1, emb2))
        except Exception as e:
            logger.error(f"Lỗi cosine_similarity: {str(e)}")
            return -1.0

    def recognize_topk(self, embedding, db_embeddings, top_k: int = 3):
        """Trả về top-k ứng viên theo cosine similarity để phục vụ explainability."""
        if not db_embeddings:
            return []

        try:
            scored = []
            for student_id, db_emb in db_embeddings:
                score = self.cosine_similarity(embedding, db_emb)
                if score < 0:
                    continue
                scored.append((student_id, float(score)))

            scored.sort(key=lambda item: item[1], reverse=True)
            return scored[:max(1, int(top_k))]
        except Exception as e:
            logger.error(f"Lỗi recognize_topk: {str(e)}", exc_info=True)
            return []

    def recognize(self, embedding, db_embeddings, use_faiss=False, faiss_index=None):
        """
        Nhận diện sinh viên từ embedding.
        
        Args:
            embedding: Query embedding (shape: (512,))
            db_embeddings: List of (student_id, embedding) tuples
            use_faiss: If True, use FAISS for faster search (optional)
        
        Returns:
            (student_id, score) hoặc (None, best_score)
        """
        if not db_embeddings:
            logger.warning("Database embeddings trống!")
            return None, 0.0

        try:
            # Try FAISS if enabled and available
            if use_faiss and faiss_index is not None:
                try:
                    student_id, score = faiss_index.search(
                        embedding,
                        top_k=1,
                        threshold=self.threshold,
                    )

                    if student_id:
                        logger.info(
                            f"✅ Nhận diện thành công (FAISS) - "
                            f"Student ID: {student_id} | Score: {score:.4f}"
                        )
                        return student_id, score

                    logger.info(f"❌ Không khớp đủ ngưỡng - Best score: {score:.4f}")
                    return None, score

                except Exception as e:
                    logger.warning(f"FAISS search failed, fallback to loop: {str(e)}")
            
            # Fallback: Loop cosine similarity (original method)
            best_score = -1.0
            best_match = None

            for student_id, db_emb in db_embeddings:
                score = self.cosine_similarity(embedding, db_emb)
                if score > best_score:
                    best_score = score
                    best_match = student_id

            if best_score >= self.threshold:
                logger.info(
                    f"✅ Nhận diện thành công - "
                    f"Student ID: {best_match} | Score: {best_score:.4f}"
                )
                return best_match, best_score
            else:
                logger.info(f"❌ Không khớp đủ ngưỡng - Best score: {best_score:.4f}")
                return None, best_score

        except Exception as e:
            logger.error(f"Lỗi trong quá trình recognize: {str(e)}", exc_info=True)
            return None, 0.0