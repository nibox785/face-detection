import sqlite3
<<<<<<< HEAD
import pickle
from datetime import datetime, timedelta
=======
from datetime import datetime
>>>>>>> 9b321e4968c99f488f7cef3ad04a52b68b0efbf2
from typing import List, Optional, Dict, Any

import numpy as np

DB_PATH = "attendance.db"
EMBEDDING_MAGIC = b"EMB1"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

# ===============================
# INIT & BASIC
# ===============================
def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        mssv TEXT UNIQUE,                 
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Migration cho database cũ chưa có cột mssv / created_at
    if not _column_exists(cursor, "students", "mssv"):
        cursor.execute("ALTER TABLE students ADD COLUMN mssv TEXT")
    if not _column_exists(cursor, "students", "created_at"):
        cursor.execute("ALTER TABLE students ADD COLUMN created_at DATETIME")

    # Tạo unique index cho MSSV để tránh trùng dữ liệu học viên
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_mssv_unique ON students(mssv)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        embedding BLOB,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    """)

    # Tạo index để tối ưu query
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_student_id ON embeddings(student_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(DATE(timestamp, 'localtime'))")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS revoked_tokens (
        jti TEXT PRIMARY KEY,
        exp_ts INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_revoked_tokens_exp ON revoked_tokens(exp_ts)")

    conn.commit()
    conn.close()

# ===============================
# EMBEDDINGS
# ===============================

def get_all_embeddings():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT student_id, embedding FROM embeddings")

    rows = cursor.fetchall()
    conn.close()

    result = []
    for student_id, blob in rows:
        emb = _deserialize_embedding(blob)
        result.append((student_id, emb))

    return result


def _serialize_embedding(embedding) -> bytes:
    array = np.asarray(embedding, dtype=np.float32)
    return EMBEDDING_MAGIC + array.tobytes()


def _deserialize_embedding(blob: bytes):
    if blob.startswith(EMBEDDING_MAGIC):
        array = np.frombuffer(blob[len(EMBEDDING_MAGIC):], dtype=np.float32)
        return array.copy()

    # Legacy fallback cho dữ liệu cũ lưu bằng pickle.
    import pickle

    return pickle.loads(blob)


def save_embedding(student_id, embedding):
    conn = get_connection()
    cursor = conn.cursor()

    blob = _serialize_embedding(embedding)

    cursor.execute(
        "INSERT INTO embeddings (student_id, embedding) VALUES (?, ?)",
        (student_id, blob)
    )

    conn.commit()
    conn.close()


# ===============================
# ATTENDANCE
# ===============================

def insert_attendance(student_id):
    conn = get_connection()
    cursor = conn.cursor()
    # lấy ngày giờ Việt Nam 
    vn_time = datetime.utcnow() + timedelta(hours=7)

    cursor.execute(
        "INSERT INTO attendance (student_id, timestamp) VALUES (?, ?)",
        (student_id, vn_time.strftime("%Y-%m-%d %H:%M:%S"))
    )


    conn.commit()
    conn.close()


def check_attendance_today(student_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) FROM attendance 
        WHERE student_id = ? 
        AND DATE(timestamp, 'localtime') = DATE('now', '+7 hours')
        """,
        (student_id,)
    )

    count = cursor.fetchone()[0]
    conn.close()

    return count > 0

# ===============================
# STUDENTS
# ===============================
def get_all_students():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, mssv FROM students ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row[0], "name": row[1], "mssv": row[2]} for row in rows]


def get_student_by_id(student_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, mssv FROM students WHERE id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    return {"id": row[0], "name": row[1], "mssv": row[2]} if row else None


def delete_student_and_embedding(student_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
    
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_student_by_name(name: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, mssv FROM students WHERE name = ?", (name.strip(),))
    row = cursor.fetchone()
    conn.close()
    return {"id": row[0], "name": row[1], "mssv": row[2]} if row else None


def get_student_by_mssv(mssv: str) -> Optional[Dict[str, Any]]:
    """Lấy sinh viên theo MSSV"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, mssv FROM students WHERE mssv = ?", (mssv.strip(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "mssv": row[2]}
    return None


def create_student(name: str, mssv: Optional[str] = None) -> int:
    """Tạo sinh viên mới với validation MSSV"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Validate MSSV nếu có
    if mssv and mssv.strip():
        mssv = mssv.strip()
        # Check MSSV duplicate
        cursor.execute("SELECT id FROM students WHERE mssv = ?", (mssv,))
        if cursor.fetchone():
            conn.close()
            raise ValueError(f"MSSV '{mssv}' đã tồn tại trong hệ thống")
    else:
        mssv = None
    
    cursor.execute(
        "INSERT INTO students (name, mssv) VALUES (?, ?)",
        (name.strip(), mssv)
    )
    student_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return student_id


def update_student_mssv(student_id: int, mssv: Optional[str]) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE students SET mssv = ? WHERE id = ?",
        (mssv.strip() if mssv and mssv.strip() else None, student_id)
    )
    conn.commit()
    conn.close()


def update_student_name(student_id: int, name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE students SET name = ? WHERE id = ?",
        (name.strip(), student_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def revoke_token(jti: str, exp_ts: int) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO revoked_tokens (jti, exp_ts) VALUES (?, ?)",
        (str(jti), int(exp_ts))
    )
    conn.commit()
    conn.close()


def cleanup_revoked_tokens(now_ts: int) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM revoked_tokens WHERE exp_ts <= ?", (int(now_ts),))
    conn.commit()
    conn.close()


def is_token_revoked(jti: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM revoked_tokens WHERE jti = ? LIMIT 1", (str(jti),))
    found = cursor.fetchone() is not None
    conn.close()
    return found


# ===============================
# ATTENDANCE - NÂNG CAO
# ===============================
def get_attendance_by_student(student_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, s.name, a.timestamp 
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.student_id = ?
        ORDER BY a.timestamp DESC
    """, (student_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "timestamp": r[2]} for r in rows]


def get_attendance_range(start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT a.id, s.name, a.student_id, a.timestamp 
        FROM attendance a
        JOIN students s ON a.student_id = s.id
    """
    params = []
    
    if start_date and end_date:
        query += " WHERE DATE(a.timestamp, 'localtime') BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE DATE(a.timestamp, 'localtime') >= ?"
        params = [start_date]
    
    query += " ORDER BY a.timestamp DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {"id": r[0], "name": r[1], "student_id": r[2], "timestamp": r[3]}
        for r in rows
    ]