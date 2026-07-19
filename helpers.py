import json
import datetime
import re


def get_greeting() -> str:
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "Доброе утро"
    elif 12 <= hour < 18:
        return "Добрый день"
    elif 18 <= hour < 23:
        return "Добрый вечер"
    return "Доброй ночи"


def is_night() -> bool:
    hour = datetime.datetime.now().hour
    return hour < 6 or hour >= 23


def format_datetime(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


def format_ban_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} сек."
    if seconds < 3600:
        return f"{seconds // 60} мин."
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h} ч. {m} мин."
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d} дн. {h} ч."


def parse_duration(text: str):
    match = re.match(r"(\d+)\s*(м|min|ч|h|д|d|с|s)", text.lower())
    if not match:
        return None
    val = int(match.group(1))
    unit = match.group(2)
    if unit in ("м", "min"):
        return val * 60
    if unit in ("ч", "h"):
        return val * 3600
    if unit in ("д", "d"):
        return val * 86400
    if unit in ("с", "s"):
        return val
    return None


def _btn(label, color="secondary", payload=None):
    b = {"action": {"type": "text", "label": label, "color": color}}
    if payload:
        b["action"]["payload"] = json.dumps(payload)
    return b


def _kb(rows, one_time=False, inline=False):
    return json.dumps({"one_time": one_time, "inline": inline, "buttons": rows})


def cancel_keyboard(ticket_id):
    return _kb([[_btn("❌ Отменить", "negative", {"cmd": "cancel_ticket", "ticket_id": ticket_id})]])


def admin_ticket_inline(ticket_id):
    return _kb([
        [
            _btn("✅ Взять", "positive", {"cmd": "take_ticket", "ticket_id": ticket_id}),
            _btn("⏭ Пропустить", "secondary", {"cmd": "skip_ticket", "ticket_id": ticket_id}),
        ]
    ], inline=True)


def finish_keyboard():
    return _kb([[_btn("🔚 Завершить", "primary", {"cmd": "finish_ticket"})]])


def rating_inline(ticket_id):
    buttons = []
    for i in range(1, 6):
        buttons.append(_btn(f"{'⭐' * i}", "secondary", {"cmd": "rate", "ticket_id": ticket_id, "rating": i}))
    return _kb([buttons], inline=True)


def empty_keyboard():
    return _kb([[]])
