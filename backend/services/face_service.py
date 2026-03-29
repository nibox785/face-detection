import numpy as np
import logging

from face_engine.facenet.embedding import get_embedding
from face_engine.facenet.detect import detect_faces

logger = logging.getLogger("face-attendance.face_service")


class FaceService:
    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        logger.info(f"FaceService được khởi tạo với threshold = {threshold}")

    def detect(self, frame):
        """Phát hiện khuôn mặt trong ảnh"""
        try:
            faces = detect_faces(frame)
            logger.debug(f"Detect faces: tìm thấy {len(faces)} khuôn mặt")
            return faces
        except Exception as e:
            logger.error(f"Lỗi khi detect faces: {str(e)}", exc_info=True)
            return []

    def extract_embedding(self, face_image):
        """Trích xuất embedding từ khuôn mặt"""
        try:
            embedding = get_embedding(face_image)
            logger.debug(f"Extract embedding thành công, shape: {embedding.shape}")
            return embedding
        except Exception as e:
            logger.error(f"Lỗi khi extract embedding: {str(e)}", exc_info=True)
            raise

    def cosine_similarity(self, emb1, emb2):
        """Tính cosine similarity giữa 2 embedding"""
        try:
            return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        except Exception as e:
            logger.error(f"Lỗi cosine_similarity: {str(e)}")
            return -1.0

    def recognize(self, embedding, db_embeddings):
        """
        Nhận diện sinh viên từ embedding
        Trả về (student_id, score) hoặc (None, best_score)
        """
        if not db_embeddings:
            logger.warning("Database embeddings trống!")
            return None, 0.0

        try:
            best_score = -1.0
            best_match = None

            for student_id, db_emb in db_embeddings:
                score = self.cosine_similarity(embedding, db_emb)

                if score > best_score:
                    best_score = score
                    best_match = student_id

            if best_score >= self.threshold:
                logger.info(f"✅ Nhận diện thành công - Student ID: {best_match} | Score: {best_score:.4f}")
                return best_match, best_score
            else:
                logger.info(f"❌ Không khớp đủ ngưỡng - Best score: {best_score:.4f}")
                return None, best_score

        except Exception as e:
            logger.error(f"Lỗi trong quá trình recognize: {str(e)}", exc_info=True)
            return None, 0.0