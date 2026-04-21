import cv2
import numpy as np

from backend.database import db
from backend.api import routes


def _make_test_image_bytes() -> bytes:
    image = np.full((64, 64, 3), 180, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def _auth_header(client) -> dict:
    response = client.post(
        "/api/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_auth_login_verify_logout_flow(client):
    headers = _auth_header(client)

    verify_response = client.get("/api/auth/verify", headers=headers)
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "success"

    logout_response = client.post("/api/logout", headers=headers)
    assert logout_response.status_code == 200

    verify_after_logout = client.get("/api/auth/verify", headers=headers)
    assert verify_after_logout.status_code == 401


def test_login_invalid_credentials_returns_401(client):
    response = client.post(
        "/api/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_auth_verify_requires_bearer_token(client):
    response = client.get("/api/auth/verify")
    assert response.status_code == 401


def test_register_endpoint_success_with_stub(client, monkeypatch):
    headers = _auth_header(client)

    monkeypatch.setattr(
        routes.register_service,
        "register_student",
        lambda name, file=None, mssv=None: (True, "Đăng ký sinh viên thành công", 101),
    )
    monkeypatch.setattr(routes, "update_embeddings_cache", lambda: None)

    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/api/register",
        data={"name": "Student Test"},
        files={"file": ("student.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["student_id"] == 101


def test_recognize_endpoint_success_with_stub(client, monkeypatch):
    headers = _auth_header(client)

    student_id = db.create_student("Recognized Student", "SV-RECOG-01")

    dummy_face = np.full((32, 32, 3), 100, dtype=np.uint8)
    dummy_bbox = {"x": 10, "y": 12, "w": 20, "h": 20, "confidence": 0.95}
    dummy_embedding = np.ones(512, dtype=np.float32)

    monkeypatch.setattr(routes.face_service, "detect", lambda frame: [(dummy_face, dummy_bbox)])
    monkeypatch.setattr(
        routes.face_service,
        "get_embedding_with_liveness",
        lambda face_image: (dummy_embedding, True, 0.02),
    )
    monkeypatch.setattr(
        routes.face_service,
        "recognize",
        lambda embedding, db_embeddings, use_faiss=False, faiss_index=None: (student_id, 0.88),
    )
    monkeypatch.setattr(routes.attendance_service, "mark_attendance", lambda _student_id: True)

    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/api/recognize",
        files={"file": ("frame.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert len(payload["data"]) == 1
    assert payload["data"][0]["student_id"] == student_id
    assert payload["data"][0]["score"] == 0.88


def test_recognize_requires_authorization_header(client):
    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/api/recognize",
        files={"file": ("frame.jpg", image_bytes, "image/jpeg")},
    )
    assert response.status_code == 401


def test_recognize_rejects_non_bearer_header(client):
    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/api/recognize",
        files={"file": ("frame.jpg", image_bytes, "image/jpeg")},
        headers={"Authorization": "DeviceKey demo-key"},
    )
    assert response.status_code == 401


def test_update_and_delete_student_management(client):
    headers = _auth_header(client)

    student_id = db.create_student("Old Name", "SV-MGMT-01")
    embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    db.save_embedding(student_id, embedding)
    db.insert_attendance(student_id)

    update_response = client.put(
        f"/api/students/{student_id}",
        data={"name": "New Name"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["name"] == "New Name"

    delete_response = client.delete(f"/api/students/{student_id}", headers=headers)
    assert delete_response.status_code == 200

    assert db.get_student_by_id(student_id) is None
    assert not any(sid == student_id for sid, _ in db.get_all_embeddings())
    assert db.get_attendance_by_student(student_id) == []


def test_register_rejects_non_image_file(client, monkeypatch):
    headers = _auth_header(client)

    # Không cần gọi AI logic nếu validation file fail sớm.
    monkeypatch.setattr(routes, "update_embeddings_cache", lambda: None)

    response = client.post(
        "/api/register",
        data={"name": "Student Invalid File"},
        files={"file": ("note.txt", b"not-an-image", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 400


def test_dataset_register_rejects_duplicate_mssv(client):
    headers = _auth_header(client)

    db.create_student("Existing Student", "SV-DUP-01")
    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/api/dataset/register",
        data={"name": "New Student", "mssv": "SV-DUP-01"},
        files={"file": ("student.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 400


def test_dataset_register_multiple_rejects_insufficient_images(client):
    headers = _auth_header(client)
    image_bytes = _make_test_image_bytes()

    files = [("files", (f"img_{i}.jpg", image_bytes, "image/jpeg")) for i in range(3)]
    response = client.post(
        "/api/dataset/register-multiple",
        data={"name": "Multi Student", "mssv": "SV-MULTI-01"},
        files=files,
        headers=headers,
    )

    assert response.status_code == 400


def test_dataset_register_multiple_success_with_stubs(client, monkeypatch):
    headers = _auth_header(client)

    dummy_face = np.full((32, 32, 3), 120, dtype=np.uint8)
    dummy_bbox = {"x": 6, "y": 8, "w": 24, "h": 24, "confidence": 0.96}
    dummy_embedding = np.ones(512, dtype=np.float32)

    monkeypatch.setattr(routes.face_service, "detect", lambda frame: [(dummy_face, dummy_bbox)])
    monkeypatch.setattr(routes.face_service, "extract_embedding", lambda face: dummy_embedding)
    monkeypatch.setattr(routes, "select_best_face_for_registration", lambda faces, shape: (dummy_face, dummy_bbox))
    monkeypatch.setattr(routes, "score_registration_frame", lambda frame, face, bbox: 0.9)
    monkeypatch.setattr(routes, "save_dataset_image", lambda student_name, filename, contents: "dataset/mock.jpg")
    monkeypatch.setattr(routes, "update_embeddings_cache", lambda: None)

    image_bytes = _make_test_image_bytes()
    files = [("files", (f"img_{i}.jpg", image_bytes, "image/jpeg")) for i in range(10)]
    response = client.post(
        "/api/dataset/register-multiple",
        data={"name": "Multi Student", "mssv": "SV-MULTI-OK"},
        files=files,
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["mssv"] == "SV-MULTI-OK"


def test_liveness_check_success_with_stub(client, monkeypatch):
    dummy_face = np.full((32, 32, 3), 130, dtype=np.uint8)
    dummy_bbox = {"x": 4, "y": 5, "w": 26, "h": 26, "confidence": 0.93}

    monkeypatch.setattr(routes.face_service, "detect", lambda frame: [(dummy_face, dummy_bbox)])
    monkeypatch.setattr(routes, "select_best_face_for_registration", lambda faces, shape: (dummy_face, dummy_bbox))
    monkeypatch.setattr(
        routes.face_service,
        "get_embedding_with_liveness",
        lambda face: (np.ones(512, dtype=np.float32), True, 0.04),
    )

    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/api/face/liveness-check",
        files={"file": ("frame.jpg", image_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["is_real"] is True


def test_liveness_check_returns_error_when_no_face(client, monkeypatch):
    monkeypatch.setattr(routes.face_service, "detect", lambda frame: [])

    image_bytes = _make_test_image_bytes()
    response = client.post(
        "/api/face/liveness-check",
        files={"file": ("frame.jpg", image_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
