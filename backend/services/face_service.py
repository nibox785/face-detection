import numpy as np

from face_engine.facenet.embedding import get_embedding
from face_engine.facenet.detect import detect_faces


class FaceService:
    def __init__(self, threshold=0.7):
        self.threshold = threshold

    def detect(self, frame):
        return detect_faces(frame)

    def extract_embedding(self, face_image):
        return get_embedding(face_image)

    def cosine_similarity(self, emb1, emb2):
        return np.dot(emb1, emb2) / (
            np.linalg.norm(emb1) * np.linalg.norm(emb2)
        )

    def recognize(self, embedding, db_embeddings):
        best_score = -1
        best_match = None

        for student_id, db_emb in db_embeddings:
            score = self.cosine_similarity(embedding, db_emb)

            if score > best_score:
                best_score = score
                best_match = student_id

        if best_score >= self.threshold:
            return best_match, best_score

        return None, best_score