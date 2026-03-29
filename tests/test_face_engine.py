import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cv2
import numpy as np
from face_engine.facenet.detect import detect_faces
from face_engine.facenet.embedding import get_embedding
from backend.services.face_service import FaceService
import logging

logging.basicConfig(level=logging.INFO)

def test_face_engine():
    print("=== TEST PHASE 1: AI Core ===")
    
    # Tạo ảnh test giả lập (ảnh màu xám đơn giản với hình vuông giả lập face)
    # Thay thế bằng ảnh thật nếu có
    img = np.zeros((480, 640, 3), dtype=np.uint8)  # Ảnh 640x480, đen
    # Vẽ hình vuông giả lập face
    cv2.rectangle(img, (200, 150), (400, 350), (255, 255, 255), -1)  # Hình vuông trắng
    
    # Lưu ảnh test tạm thời
    cv2.imwrite("tests/test_image.jpg", img)
    print("✅ Đã tạo ảnh test giả lập: tests/test_image.jpg")
    
    faces = detect_faces(img)
    print(f"✅ Detect faces: tìm thấy {len(faces)} khuôn mặt")
    
    if faces:
        emb = get_embedding(faces[0])
        print(f"✅ Extract embedding thành công - Shape: {emb.shape}")
        
        # Test similarity (so sánh 2 lần cùng khuôn mặt)
        emb2 = get_embedding(faces[0])
        service = FaceService()
        score = service.cosine_similarity(emb, emb2)
        print(f"✅ Cosine similarity (cùng người): {score:.4f} (nên gần 1.0)")
        
        # Test với embedding khác (không cùng)
        img2 = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(img2, (250, 200), (450, 400), (200, 200, 200), -1)  # Hình khác
        faces2 = detect_faces(img2)
        if faces2:
            emb_diff = get_embedding(faces2[0])
            score_diff = service.cosine_similarity(emb, emb_diff)
            print(f"✅ Cosine similarity (khác người): {score_diff:.4f} (nên thấp)")
    else:
        print("❌ Không detect được face - có thể do ảnh giả lập quá đơn giản")
    
    print("\nPhase 1 test hoàn tất!")

if __name__ == "__main__":
    test_face_engine()