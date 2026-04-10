import sqlite3
import pickle
from datetime import datetime
from typing import List, Optional, Dict, Any

DB_PATH = "attendance.db"


def get_connection():
    return sqlite3.connect(DB_PATH)

# ===============================
# INIT & BASIC
# ===============================
def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        mssv TEXT UNIQUE,                 
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(DATE(timestamp))")

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
        emb = pickle.loads(blob)
        result.append((student_id, emb))

    return result


def save_embedding(student_id, embedding):
    conn = get_connection()
    cursor = conn.cursor()

    blob = pickle.dumps(embedding)

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

    cursor.execute(
        "INSERT INTO attendance (student_id) VALUES (?)",
        (student_id,)
    )

    conn.commit()
    conn.close()


def check_attendance_today(student_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM attendance WHERE student_id = ? AND DATE(timestamp) = DATE('now')",
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
    cursor.execute("SELECT id, name FROM students ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row[0], "name": row[1]} for row in rows]


def get_student_by_id(student_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM students WHERE id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    return {"id": row[0], "name": row[1]} if row else None


def delete_student_and_embedding(student_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Xóa embedding trước
    cursor.execute("DELETE FROM embeddings WHERE student_id = ?", (student_id,))
    # Xóa attendance
    cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
    # Xóa student
    cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
    
    conn.commit()
    conn.close()
    return True


def get_student_by_name(name: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM students WHERE name = ?", (name.strip(),))
    row = cursor.fetchone()
    conn.close()
    return {"id": row[0], "name": row[1]} if row else None


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
        query += " WHERE DATE(a.timestamp) BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE DATE(a.timestamp) >= ?"
        params = [start_date]
    
    query += " ORDER BY a.timestamp DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {"id": r[0], "name": r[1], "student_id": r[2], "timestamp": r[3]}
        for r in rows
    ]