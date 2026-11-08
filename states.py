import json

import database as db


def set_state(user_id: str, state: dict) -> None:
    db.save_state(user_id, json.dumps(state, ensure_ascii=False))


def get_state(user_id: str) -> dict | None:
    raw = db.load_state(user_id)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def clear_state(user_id: str) -> None:
    db.delete_state(user_id)