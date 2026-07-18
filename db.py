import json
import os
import threading
import time
from typing import Optional


DB_PATH = os.getenv("DB_PATH", "database.json")

_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(DB_PATH):
        return _default_db()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return _default_db()


def _save(data: dict):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _default_db() -> dict:
    return {
        "admins": [],
        "tickets": [],
        "bans": [],
        "next_ticket_id": 1,
    }


def init_db():
    with _lock:
        data = _load()
        if "next_ticket_id" not in data:
            data["next_ticket_id"] = 1
        if "bans" not in data:
            data["bans"] = []
        _save(data)


# --- Admins ---

def add_admin(user_id: int) -> bool:
    with _lock:
        data = _load()
        if user_id in data["admins"]:
            return False
        data["admins"].append(user_id)
        _save(data)
        return True


def remove_admin(user_id: int) -> bool:
    with _lock:
        data = _load()
        if user_id not in data["admins"]:
            return False
        data["admins"].remove(user_id)
        _save(data)
        return True


def is_admin(user_id: int) -> bool:
    data = _load()
    return user_id in data["admins"]


def is_developer(user_id: int) -> bool:
    return user_id == int(os.getenv("DEVELOPER_ID", 0))


def is_admin_or_dev(user_id: int) -> bool:
    return is_admin(user_id) or is_developer(user_id)


def get_all_admins() -> list:
    data = _load()
    return list(data["admins"])


# --- Bans ---

def ban_user(user_id: int, reason: str, duration: Optional[int] = None) -> dict:
    with _lock:
        data = _load()
        ban_entry = {
            "user_id": user_id,
            "reason": reason,
            "duration": duration,
            "banned_at": time.time(),
        }
        data["bans"].append(ban_entry)
        _save(data)
        return ban_entry


def unban_user(user_id: int) -> bool:
    with _lock:
        data = _load()
        before = len(data["bans"])
        data["bans"] = [b for b in data["bans"] if b["user_id"] != user_id]
        _save(data)
        return len(data["bans"]) < before


def is_banned(user_id: int) -> Optional[dict]:
    data = _load()
    for b in data["bans"]:
        if b["user_id"] == user_id:
            if b["duration"] is None:
                return b
            elapsed = time.time() - b["banned_at"]
            if elapsed < b["duration"]:
                return b
            else:
                unban_user(user_id)
                return None
    return None


def get_all_bans() -> list:
    data = _load()
    return list(data["bans"])


# --- Tickets ---

def create_ticket(user_id: int, user_name: str, text: str) -> dict:
    with _lock:
        data = _load()
        ticket_id = data["next_ticket_id"]
        data["next_ticket_id"] += 1
        ticket = {
            "id": ticket_id,
            "user_id": user_id,
            "user_name": user_name,
            "text": text,
            "status": "open",
            "admin_id": None,
            "admin_name": None,
            "created_at": time.time(),
            "messages": [{"from": "user", "user_id": user_id, "name": user_name, "text": text, "time": time.time()}],
        }
        data["tickets"].append(ticket)
        _save(data)
        return ticket


def get_ticket(ticket_id: int) -> Optional[dict]:
    data = _load()
    for t in data["tickets"]:
        if t["id"] == ticket_id:
            return t
    return None


def get_open_tickets() -> list:
    data = _load()
    return [t for t in data["tickets"] if t["status"] == "open"]


def get_active_tickets() -> list:
    data = _load()
    return [t for t in data["tickets"] if t["status"] in ("open", "in_progress")]


def get_user_active_ticket(user_id: int) -> Optional[dict]:
    data = _load()
    for t in data["tickets"]:
        if t["user_id"] == user_id and t["status"] in ("open", "in_progress"):
            return t
    return None


def take_ticket(ticket_id: int, admin_id: int, admin_name: str) -> Optional[dict]:
    with _lock:
        data = _load()
        for t in data["tickets"]:
            if t["id"] == ticket_id:
                if t["status"] != "open":
                    return None
                t["status"] = "in_progress"
                t["admin_id"] = admin_id
                t["admin_name"] = admin_name
                _save(data)
                return t
        return None


def skip_ticket(ticket_id: int) -> Optional[dict]:
    with _lock:
        data = _load()
        for t in data["tickets"]:
            if t["id"] == ticket_id:
                if t["status"] != "open":
                    return None
                t["admin_id"] = None
                t["admin_name"] = None
                _save(data)
                return t
        return None


def close_ticket(ticket_id: int) -> Optional[dict]:
    with _lock:
        data = _load()
        for t in data["tickets"]:
            if t["id"] == ticket_id:
                t["status"] = "closed"
                _save(data)
                return t
        return None


def add_message_to_ticket(ticket_id: int, sender: str, user_id: int, name: str, text: str) -> Optional[dict]:
    with _lock:
        data = _load()
        for t in data["tickets"]:
            if t["id"] == ticket_id:
                t["messages"].append({
                    "from": sender,
                    "user_id": user_id,
                    "name": name,
                    "text": text,
                    "time": time.time(),
                })
                _save(data)
                return t
        return None


def rate_ticket(ticket_id: int, rating: int) -> Optional[dict]:
    with _lock:
        data = _load()
        for t in data["tickets"]:
            if t["id"] == ticket_id:
                t["rating"] = rating
                _save(data)
                return t
        return None


def close_all_user_tickets(user_id: int):
    with _lock:
        data = _load()
        for t in data["tickets"]:
            if t["user_id"] == user_id and t["status"] in ("open", "in_progress"):
                t["status"] = "closed"
        _save(data)
