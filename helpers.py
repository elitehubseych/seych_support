import json
from datetime import datetime, timezone, timedelta


MSK = timezone(timedelta(hours=3))


def get_msk_now() -> datetime:
    return datetime.now(MSK)


def get_greeting() -> str:
    return "Доброго времени суток"


def is_night() -> bool:
    return 0 <= get_msk_now().hour < 6


def format_datetime(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=MSK)
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def format_ban_duration(seconds: float) -> str:
    if seconds is None:
        return "∞ навсегда"
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    parts = []
    if days > 0:
        parts.append(f"{days} дн.")
    if hours > 0:
        parts.append(f"{hours} ч.")
    if minutes > 0:
        parts.append(f"{minutes} мин.")
    return " ".join(parts) if parts else "< 1 мин."


def parse_duration(text: str) -> int | None:
    text = text.lower().strip()
    parts = text.split()
    if len(parts) < 2:
        return None
    try:
        num = int(parts[0])
    except ValueError:
        return None
    unit = parts[1]
    if unit in ("мин", "минута", "минуты", "минут", "минуту", "minutes", "min"):
        return num * 60
    elif unit in ("ч", "час", "часа", "часов", "часу", "hours", "hour", "h"):
        return num * 3600
    elif unit in ("д", "день", "дня", "дней", "дню", "days", "day", "d"):
        return num * 86400
    elif unit in ("год", "года", "лет", "году", "years", "year", "y"):
        return num * 31536000
    return None


# --- VK Keyboards ---

def _btn(label: str, color: str, payload: dict) -> dict:
    return {
        "action": {
            "type": "callback",
            "label": label,
            "payload": json.dumps(payload),
        },
        "color": color,
    }


def _text_btn(label: str, color: str, payload: dict) -> dict:
    return {
        "action": {
            "type": "text",
            "label": label,
            "payload": json.dumps(payload),
        },
        "color": color,
    }


def cancel_keyboard(ticket_id: int) -> str:
    kb = {
        "one_time": True,
        "buttons": [[
            _btn("❌ Отменить обращение", "negative", {"cmd": "cancel_ticket", "ticket_id": ticket_id})
        ]],
    }
    return json.dumps(kb)


def admin_ticket_inline(ticket_id: int) -> str:
    kb = {
        "inline": True,
        "buttons": [[
            _btn("✅ Взять в работу", "positive", {"cmd": "take_ticket", "ticket_id": ticket_id}),
            _btn("⏭️ Пропустить", "secondary", {"cmd": "skip_ticket", "ticket_id": ticket_id}),
            _btn("🚫 Закрыть", "negative", {"cmd": "close_ticket", "ticket_id": ticket_id}),
        ]],
    }
    return json.dumps(kb)


def finish_keyboard() -> str:
    kb = {
        "one_time": False,
        "buttons": [[
            _btn("🔚 Завершить обращение", "negative", {"cmd": "finish_ticket"})
        ]],
    }
    return json.dumps(kb)


def rating_keyboard(ticket_id: int) -> str:
    kb = {
        "one_time": True,
        "buttons": [[
            _btn("😡", "negative", {"cmd": "rate", "ticket_id": ticket_id, "rating": 1}),
            _btn("😟", "negative", {"cmd": "rate", "ticket_id": ticket_id, "rating": 2}),
            _btn("😐", "secondary", {"cmd": "rate", "ticket_id": ticket_id, "rating": 3}),
            _btn("🙂", "positive", {"cmd": "rate", "ticket_id": ticket_id, "rating": 4}),
            _btn("😍", "positive", {"cmd": "rate", "ticket_id": ticket_id, "rating": 5}),
        ]],
    }
    return json.dumps(kb)


def empty_keyboard() -> str:
    return json.dumps({"buttons": []})
