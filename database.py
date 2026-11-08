import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from config import DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, role TEXT NOT NULL, name TEXT NOT NULL,
    school_id TEXT, class_id TEXT, points INTEGER DEFAULT 0,
    ovz INTEGER DEFAULT 0, child_id TEXT
);
CREATE TABLE IF NOT EXISTS schools (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, director_id TEXT
);
CREATE TABLE IF NOT EXISTS classes (
    id TEXT PRIMARY KEY, school_id TEXT, name TEXT NOT NULL, invite_code TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    class_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL,
    PRIMARY KEY (class_id, user_id)
);
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY, class_id TEXT NOT NULL, user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'wait'
);
CREATE TABLE IF NOT EXISTS schedule (
    id TEXT PRIMARY KEY, class_id TEXT NOT NULL, day_of_week INTEGER NOT NULL,
    time TEXT NOT NULL, subject TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
    subject TEXT, steps TEXT, is_done INTEGER DEFAULT 0,
    deadline TEXT, task_type TEXT DEFAULT 'task', priority INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS states (
    user_id TEXT PRIMARY KEY, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_starts (
    user_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
"""

ALLOWED_USER_FIELDS = {"role", "name", "school_id", "class_id", "ovz", "child_id"}


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO members (class_id, user_id, role) "
            "SELECT class_id, id, 'teacher' FROM users "
            "WHERE role = 'teacher' AND class_id IS NOT NULL"
        )


def get_user(uid: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row else None


def create_user(uid: str, name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, role, name) VALUES (?, 'student', ?)",
            (uid, name),
        )


def update_user(uid: str, field: str, value: Any) -> None:
    if field not in ALLOWED_USER_FIELDS:
        raise ValueError(f"Недопустимое поле: {field}")
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, uid))


def get_all_students() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE role = 'student'").fetchall()


def get_progress(user_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(is_done), 0) AS done "
            "FROM tasks WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return {"total": row["total"] or 0, "done": row["done"] or 0}


def get_parents_of(child_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE role = 'parent' AND child_id = ?",
            (child_id,),
        ).fetchall()


def create_school(school_id: str, name: str, director_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO schools (id, name, director_id) VALUES (?, ?, ?)",
            (school_id, name, director_id),
        )


def get_school_name(school_id: str | None) -> str | None:
    if not school_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM schools WHERE id = ?", (school_id,)
        ).fetchone()
    return row["name"] if row else None


def create_class(class_id: str, school_id: str, name: str, invite_code: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO classes (id, school_id, name, invite_code) VALUES (?, ?, ?, ?)",
            (class_id, school_id, name, invite_code),
        )


def get_class_name(class_id: str | None) -> str | None:
    if not class_id:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT name FROM classes WHERE id = ?", (class_id,)).fetchone()
    return row["name"] if row else None


def get_class_by_code(code: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM classes WHERE invite_code = ?", (code,)
        ).fetchone()
    return dict(row) if row else None


def get_class_by_id(class_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM classes WHERE id = ?", (class_id,)
        ).fetchone()
    return dict(row) if row else None


def get_class_by_name_and_school(name: str, school_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM classes WHERE name = ? AND school_id = ?", (name, school_id)
        ).fetchone()
    return dict(row) if row else None


def get_classes_of_school(school_id: str | None) -> list[sqlite3.Row]:
    if not school_id:
        return []
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM classes WHERE school_id = ?", (school_id,)
        ).fetchall()


def get_classes_of_teacher(teacher_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT c.* FROM classes c "
            "JOIN members m ON m.class_id = c.id "
            "WHERE m.user_id = ? AND m.role = 'teacher' "
            "ORDER BY c.name",
            (teacher_id,),
        ).fetchall()


def add_member(class_id: str, user_id: str, role: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO members (class_id, user_id, role) VALUES (?, ?, ?)",
            (class_id, user_id, role),
        )


def remove_teacher_memberships(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM members WHERE user_id = ?", (user_id,))


def get_class_students(class_id: str | None) -> list[sqlite3.Row]:
    if not class_id:
        return []
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM members WHERE class_id = ? AND role = 'student'",
            (class_id,),
        ).fetchall()


def get_teacher_of_class(class_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id FROM members WHERE class_id = ? AND role = 'teacher' LIMIT 1",
            (class_id,),
        ).fetchone()
    return row["user_id"] if row else None


def kick_student(user_id: str, class_id: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM members WHERE user_id = ? AND class_id = ?",
            (user_id, class_id),
        )
        conn.execute("UPDATE users SET class_id = NULL WHERE id = ?", (user_id,))


def create_request(req_id: str, class_id: str, user_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO requests (id, class_id, user_id, status) VALUES (?, ?, ?, 'wait')",
            (req_id, class_id, user_id),
        )


def get_user_request(user_id: str, class_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM requests WHERE user_id = ? AND class_id = ? "
            "ORDER BY rowid DESC LIMIT 1",
            (user_id, class_id),
        ).fetchone()


def get_pending_requests(class_id: str | None) -> list[sqlite3.Row]:
    if not class_id:
        return []
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM requests WHERE class_id = ? AND status = 'wait'",
            (class_id,),
        ).fetchall()


def get_request(req_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()


def approve_request(req_id: str) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()
        if not row:
            return
        conn.execute("UPDATE requests SET status = 'ok' WHERE id = ?", (req_id,))
        conn.execute(
            "INSERT OR IGNORE INTO members (class_id, user_id, role) VALUES (?, ?, 'student')",
            (row["class_id"], row["user_id"]),
        )
        conn.execute(
            "UPDATE users SET class_id = ? WHERE id = ? AND class_id IS NULL",
            (row["class_id"], row["user_id"]),
        )


def reject_request(req_id: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE requests SET status = 'no' WHERE id = ?", (req_id,))


def get_schedule(class_id: str | None) -> list[sqlite3.Row]:
    if not class_id:
        return []
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM schedule WHERE class_id = ? ORDER BY day_of_week, time",
            (class_id,),
        ).fetchall()


def clear_schedule(class_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM schedule WHERE class_id = ?", (class_id,))


def add_lesson(class_id: str, day: int, time: str, subject: str, lesson_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO schedule (id, class_id, day_of_week, time, subject) "
            "VALUES (?, ?, ?, ?, ?)",
            (lesson_id, class_id, day, time, subject),
        )


def delete_lesson(lesson_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM schedule WHERE id = ?", (lesson_id,))


def add_task(task_id: str, user_id: str, title: str, subject: str, steps: str, deadline: str = None, task_type: str = 'task', priority: int = 1) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, title, subject, steps, deadline, task_type, priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, user_id, title, subject, steps, deadline, task_type, priority)
        )


def add_homework_to_class(class_id: str, subject: str, title: str, deadline: str = None) -> int:
    students = get_class_students(class_id)
    if not students:
        return 0
    with get_conn() as conn:
        for s in students:
            conn.execute(
                "INSERT INTO tasks (id, user_id, title, subject, steps, deadline, task_type, priority) "
                "VALUES (?, ?, ?, ?, ?, ?, 'homework', 2)",
                (str(uuid.uuid4())[:6], s["user_id"], title, subject, None, deadline)
            )
    return len(students)


def get_tasks(user_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? "
            "ORDER BY is_done, CASE WHEN deadline IS NULL THEN 1 ELSE 0 END, deadline, priority DESC",
            (user_id,)
        ).fetchall()


def get_first_pending_task(user_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND is_done = 0 "
            "ORDER BY priority DESC, deadline ASC LIMIT 1",
            (user_id,)
        ).fetchone()


def get_task(task_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def complete_task(task_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, is_done FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row or row["is_done"] == 1:
            return None
        conn.execute("UPDATE tasks SET is_done = 1 WHERE id = ?", (task_id,))
        conn.execute(
            "UPDATE users SET points = points + 5 WHERE id = ?", (row["user_id"],)
        )
    return row["user_id"]


def save_state(user_id: str, data: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO states (user_id, data) VALUES (?, ?)",
            (user_id, data),
        )


def load_state(user_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM states WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["data"] if row else None


def delete_state(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM states WHERE user_id = ?", (user_id,))


def save_pending_start(user_id: str, payload: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pending_starts (user_id, payload) VALUES (?, ?)",
            (user_id, payload),
        )


def pop_pending_start(user_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload FROM pending_starts WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM pending_starts WHERE user_id = ?", (user_id,))
    return row["payload"]