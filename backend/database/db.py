import sqlite3
import pickle

DB_PATH = "attendance.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


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

