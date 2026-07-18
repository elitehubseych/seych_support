import os
import json
import time
import logging

import db
from helpers import (
    get_greeting, is_night, format_datetime, format_ban_duration,
    parse_duration, cancel_keyboard, admin_ticket_inline,
    finish_keyboard, rating_inline, empty_keyboard,
)

log = logging.getLogger("support-bot")

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", 0))
BOT_NAME = "Сейч"

_vk = None
_send = None
_get_user_name = None


def init(vk, send_fn, get_name_fn):
    global _vk, _send, _get_user_name
    _vk = vk
    _send = send_fn
    _get_user_name = get_name_fn


def send(user_id: int, text: str, keyboard: str = None):
    _send(user_id, text, keyboard)


def get_user_name(user_id: int) -> str:
    return _get_user_name(user_id)


def mention_user(user_id: int) -> str:
    return f"[id{user_id}|{get_user_name(user_id)}]"


def send_to_all_admins(text: str, keyboard: str = None):
    for admin_id in db.get_all_admins():
        send(admin_id, text, keyboard=keyboard)
    if DEVELOPER_ID not in db.get_all_admins():
        send(DEVELOPER_ID, text, keyboard=keyboard)


def send_to_other_admins(exclude_id: int, text: str):
    for admin_id in db.get_all_admins():
        if admin_id != exclude_id:
            send(admin_id, text)
    if DEVELOPER_ID != exclude_id:
        send(DEVELOPER_ID, text)


def extract_user_id(text: str) -> int | None:
    text = text.strip()
    if text.startswith("[id") and "|" in text:
        try:
            return int(text.split("[id")[1].split("|")[0])
        except (ValueError, IndexError):
            pass
    if text.startswith("@"):
        text = text[1:]
    if text.isdigit():
        return int(text)
    return None


# ========================
# Callback buttons
# ========================

def on_callback_button(user_id: int, peer_id: int, payload: dict):
    cmd = payload.get("cmd")
    ticket_id = payload.get("ticket_id")

    if cmd == "cancel_ticket" and ticket_id:
        handle_cancel(user_id, ticket_id)

    elif cmd == "take_ticket" and ticket_id:
        handle_take(user_id, ticket_id)

    elif cmd == "skip_ticket" and ticket_id:
        handle_skip(user_id, ticket_id)

    elif cmd == "close_ticket" and ticket_id:
        handle_close(user_id, ticket_id)

    elif cmd == "rate" and ticket_id:
        handle_rate(user_id, ticket_id, payload.get("rating", 0))

    elif cmd == "finish_ticket":
        handle_finish(user_id)


def handle_cancel(user_id: int, ticket_id: int):
    ticket = db.get_ticket(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        return
    if ticket["status"] != "open":
        send(user_id, "⚠️ Это обращение уже обрабатывается, отменить невозможно.")
        return
    db.close_ticket(ticket_id)
    send(user_id, f"❌ Обращение #{ticket_id} отменено.\n\nС уважением, {BOT_NAME}!", keyboard=empty_keyboard())
    send_to_other_admins(user_id,
        f"❌ Пользователь {mention_user(user_id)} отменил обращение #{ticket_id}.")


def handle_take(user_id: int, ticket_id: int):
    if not db.is_admin_or_dev(user_id):
        return
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        return
    if ticket["status"] == "in_progress":
        send(user_id, f"⚠️ Обращение #{ticket_id} уже занято администратором {mention_user(ticket['admin_id'])}.")
        return
    if ticket["status"] != "open":
        send(user_id, "⚠️ Это обращение уже закрыто.")
        return
    admin_name = get_user_name(user_id)
    db.take_ticket(ticket_id, user_id, admin_name)
    send(user_id,
        f"✅ Вы успешно взяли в работу обращение #{ticket_id} пользователя {mention_user(ticket['user_id'])}\n"
        f"💬 Пишите ответ прямо сюда.",
        keyboard=finish_keyboard())
    send(ticket["user_id"],
        f"📋 Администратор взял Ваш вопрос на рассмотрение, ожидайте, Вам сейчас ответят.",
        keyboard=finish_keyboard())


def handle_skip(user_id: int, ticket_id: int):
    if not db.is_admin_or_dev(user_id):
        return
    ticket = db.get_ticket(ticket_id)
    if not ticket or ticket["status"] != "open":
        return
    db.skip_ticket(ticket_id)
    send_to_other_admins(user_id,
        f"⏭️ Администратор {mention_user(user_id)} пропустил обращение #{ticket_id}, его может забрать другой администратор.")


def handle_close(user_id: int, ticket_id: int):
    if not db.is_admin_or_dev(user_id):
        return
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        return
    if ticket["status"] == "closed":
        return
    db.close_ticket(ticket_id)
    send(user_id,
        f"✅ Вы успешно закрыли обращение #{ticket_id} пользователя {mention_user(ticket['user_id'])}.", keyboard=empty_keyboard())
    send_to_other_admins(user_id,
        f"🚫 Администратор {mention_user(user_id)} закрыл обращение #{ticket_id} пользователя {mention_user(ticket['user_id'])}.")
    send(ticket["user_id"],
        f"🚫 Ваше обращение #{ticket_id} было закрыто администрацией.", keyboard=empty_keyboard())
    send(ticket["user_id"],
        f"⭐ Оцените работу администратора:",
        keyboard=rating_inline(ticket_id))


def handle_rate(user_id: int, ticket_id: int, rating: int):
    ticket = db.get_ticket(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        return
    if rating < 1 or rating > 5:
        return
    db.rate_ticket(ticket_id, rating)
    stars = "⭐" * rating
    send(user_id, f"✅ Спасибо за оценку! Ваша оценка: {stars}\n\nС уважением, {BOT_NAME}!")
    if ticket.get("admin_id"):
        rating_labels = {1: "😡 Плохо", 2: "😟 Удовлетворительно", 3: "😐 Нормально", 4: "🙂 Хорошо", 5: "😍 Отлично"}
        send(ticket["admin_id"],
            f"📊 Пользователь {mention_user(user_id)} оценил Вашу работу\n"
            f"Оценка: {rating_labels.get(rating, str(rating))} ({stars})")


def handle_finish(user_id: int):
    if db.is_admin_or_dev(user_id):
        ticket = None
        for t in db.get_active_tickets():
            if t.get("admin_id") == user_id and t["status"] == "in_progress":
                ticket = t
                break
        if not ticket:
            send(user_id, "⚠️ У вас нет активных обращений.")
            return
        db.close_ticket(ticket["id"])
        send(user_id,
            f"✅ Вы завершили обращение #{ticket['id']} пользователя {mention_user(ticket['user_id'])}.", keyboard=empty_keyboard())
        send(ticket["user_id"],
            f"🚫 Ваше обращение #{ticket['id']} было закрыто администрацией.", keyboard=empty_keyboard())
        send(ticket["user_id"],
            f"⭐ Оцените работу администратора:",
            keyboard=rating_inline(ticket["id"]))
        return

    ticket = db.get_user_active_ticket(user_id)
    if not ticket:
        send(user_id, "⚠️ У вас нет активных обращений.")
        return

    if ticket["user_id"] == user_id:
        db.close_ticket(ticket["id"])
        send(user_id, f"✅ Вы завершили обращение #{ticket['id']}.", keyboard=empty_keyboard())
        if ticket.get("admin_id"):
            send(ticket["admin_id"],
                f"🔚 Пользователь {mention_user(user_id)} завершил обращение #{ticket['id']}.", keyboard=empty_keyboard())


# ========================
# Message handlers
# ========================

def on_new_message(user_id: int, peer_id: int, text: str, is_dm: bool):
    if not is_dm:
        return

    if db.is_admin_or_dev(user_id) and peer_id == user_id:
        handle_admin_dm(user_id, text)
        return

    handle_user_dm(user_id, text)


def handle_user_dm(user_id: int, text: str):
    if text.startswith("/"):
        handle_user_command(user_id, text)
        return

    ban = db.is_banned(user_id)
    if ban:
        if ban["duration"] is None:
            send(user_id, f"🚫 Вы заблокированы в системе поддержки.\n📝 Причина: {ban.get('reason', 'не указана')}")
        else:
            remaining = ban["duration"] - (time.time() - ban["banned_at"])
            send(user_id,
                f"🚫 Вы заблокированы в системе поддержки.\n"
                f"📝 Причина: {ban.get('reason', 'не указана')}\n"
                f"⏳ Осталось: {format_ban_duration(remaining)}")
        return

    active = db.get_user_active_ticket(user_id)
    if active:
        send_user_in_ticket(user_id, text, active)
        return

    create_new_ticket(user_id, text)


def create_new_ticket(user_id: int, text: str):
    user_name = get_user_name(user_id)
    ticket = db.create_ticket(user_id, user_name, text)
    ticket_id = ticket["id"]

    greeting = get_greeting()
    night_text = ""
    if is_night():
        night_text = (
            "\n\n🌙 Вы обратились в ночное время суток, администраторы могут быть не в сети. "
            "Время ответа на вопрос увеличивается. Но Вам обязательно ответят, без ответа никто не останется."
            "\n\n⚠️ Если Вы обратились по ошибке, пожалуйста, отмените своё обращение в поддержку. "
            "За сообщения не по делу может последовать наказание."
        )

    send(user_id,
        f"{greeting}, {user_name}!\n\n"
        f"📋 Ваше обращение №{ticket_id} успешно зарегистрировано.\n"
        f"Пожалуйста, ожидайте ответ от администрации, они ответят, как только освободятся."
        f"{night_text}\n\n"
        f"С уважением, {BOT_NAME}!",
        keyboard=cancel_keyboard(ticket_id))

    mention = mention_user(user_id)
    admin_msg = (
        f"📩 Новое обращение от {mention}\n"
        f"📋 №{ticket_id}\n"
        f"📝 Суть обращения: {text}\n"
        f"🕐 Дата и время: {format_datetime(ticket['created_at'])}"
    )
    for admin_id in db.get_all_admins():
        send(admin_id, admin_msg, keyboard=admin_ticket_inline(ticket_id))
    if DEVELOPER_ID not in db.get_all_admins():
        send(DEVELOPER_ID, admin_msg, keyboard=admin_ticket_inline(ticket_id))


def send_user_in_ticket(user_id: int, text: str, ticket: dict):
    db.add_message_to_ticket(ticket["id"], "user", user_id, ticket["user_name"], text)

    if ticket["status"] == "open":
        send(user_id,
            "⏳ Ваше обращение находится в очереди ожидания.\n"
            "Пожалуйста, ожидайте ответа от администратора.",
            keyboard=finish_keyboard())
    elif ticket["status"] == "in_progress" and ticket.get("admin_id"):
        send(ticket["admin_id"],
            f"📨 Сообщение от {mention_user(user_id)}\n"
            f"📋 Обращение #{ticket['id']}\n\n"
            f"💬 {text}",
            keyboard=finish_keyboard())
        send(user_id,
            "✉️ Ваше сообщение отправлено администратору. Ожидайте ответа.",
            keyboard=finish_keyboard())


def handle_admin_dm(user_id: int, text: str):
    if not db.is_admin_or_dev(user_id):
        return

    if text.startswith("/"):
        handle_admin_command(user_id, text)
        return

    ticket = None
    for t in db.get_active_tickets():
        if t.get("admin_id") == user_id and t["status"] == "in_progress":
            ticket = t
            break

    if ticket:
        db.add_message_to_ticket(ticket["id"], "admin", user_id, get_user_name(user_id), text)
        send(ticket["user_id"],
            f"💬 Ответ от администратора:\n{text}",
            keyboard=finish_keyboard())
        send(user_id,
            f"✅ Ответ отправлен пользователю.",
            keyboard=finish_keyboard())
    else:
        send(user_id, "⚠️ У вас нет активных обращений.")


# ========================
# User commands
# ========================

def handle_user_command(user_id: int, text: str):
    parts = text.split()
    cmd = parts[0].lower()

    if cmd in ("/start", "/help"):
        ban = db.is_banned(user_id)
        if ban:
            send(user_id, "🚫 Вы заблокированы в системе поддержки.")
            return
        send(user_id,
            f"👋 Добро пожаловать в систему поддержки {BOT_NAME}!\n\n"
            f"📝 Чтобы создать обращение, просто напишите сообщение с описанием проблемы.\n"
            f"🔚 Чтобы завершить обращение, нажмите кнопку «Завершить» или /close\n\n"
            f"С уважением, {BOT_NAME}!")

    elif cmd == "/close":
        ticket = db.get_user_active_ticket(user_id)
        if not ticket:
            send(user_id, "⚠️ У вас нет активных обращений.")
            return
        db.close_ticket(ticket["id"])
        send(user_id, f"✅ Обращение #{ticket['id']} завершено.", keyboard=empty_keyboard())
        if ticket.get("admin_id"):
            send(ticket["admin_id"],
                f"🔚 Пользователь {mention_user(user_id)} завершил обращение #{ticket['id']}.", keyboard=empty_keyboard())


# ========================
# Admin commands
# ========================

def handle_admin_command(user_id: int, text: str):
    if not db.is_admin_or_dev(user_id):
        return

    parts = text.split()
    cmd = parts[0].lower()

    if cmd == "/ask":
        tickets = db.get_active_tickets()
        if not tickets:
            send(user_id, "📭 Нет активных обращений.")
            return
        lines = ["📋 Список обращений:\n"]
        for t in tickets:
            user_mention = mention_user(t["user_id"])
            if t["status"] == "in_progress" and t.get("admin_id"):
                admin_mention = mention_user(t["admin_id"])
                status_str = f"🔹 {user_mention} #{t['id']} — {admin_mention}"
            else:
                status_str = f"🔹 {user_mention} #{t['id']} — ⏳ в ожидании"
            lines.append(status_str)
        send(user_id, "\n".join(lines))

    elif cmd == "/job":
        if len(parts) < 2 or not parts[1].isdigit():
            send(user_id, "⚠️ Использование: /job <номер обращения>")
            return
        ticket_id = int(parts[1])
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            send(user_id, f"⚠️ Обращение #{ticket_id} не существует.")
            return
        if ticket["status"] == "in_progress":
            send(user_id, f"⚠️ Обращение #{ticket_id} занято администратором {mention_user(ticket['admin_id'])}.")
            return
        if ticket["status"] == "closed":
            send(user_id, f"⚠️ Обращение #{ticket_id} уже закрыто.")
            return
        admin_name = get_user_name(user_id)
        db.take_ticket(ticket_id, user_id, admin_name)
        send(user_id,
            f"✅ Вы успешно взяли в работу обращение #{ticket_id} пользователя {mention_user(ticket['user_id'])}\n"
            f"💬 Пишите ответ прямо сюда.",
            keyboard=finish_keyboard())
        send(ticket["user_id"],
            f"📋 Администратор взял Ваш вопрос на рассмотрение, ожидайте, Вам сейчас ответят.",
            keyboard=finish_keyboard())

    elif cmd == "/getadmin":
        if len(parts) < 2:
            send(user_id, "⚠️ Использование: /getadmin @user")
            return
        target = extract_user_id(parts[1])
        if not target:
            send(user_id, "⚠️ Не удалось определить пользователя. Используйте @user или ID.")
            return
        if db.add_admin(target):
            name = get_user_name(target)
            send(user_id, f"✅ Пользователь {name} (ID: {target}) назначен администратором.")
            send(target, "🎉 Вы были назначены администратором поддержки!")
        else:
            send(user_id, "ℹ️ Этот пользователь уже является администратором.")

    elif cmd == "/unadmin":
        if len(parts) < 2:
            send(user_id, "⚠️ Использование: /unadmin @user")
            return
        target = extract_user_id(parts[1])
        if not target:
            send(user_id, "⚠️ Не удалось определить пользователя.")
            return
        if target == DEVELOPER_ID:
            send(user_id, "⚠️ Нельзя снять разработчика.")
            return
        if db.remove_admin(target):
            name = get_user_name(target)
            send(user_id, f"✅ Пользователь {name} (ID: {target}) снят с роли администратора.")
            send(target, "ℹ️ Вы были сняты с роли администратора поддержки.")
        else:
            send(user_id, "ℹ️ Этот пользователь не является администратором.")

    elif cmd == "/admins":
        admins = db.get_all_admins()
        all_ids = list(set(admins + [DEVELOPER_ID]))
        if not all_ids:
            send(user_id, "📭 Список администраторов пуст.")
            return
        lines = ["👥 Список администраторации:\n"]
        for aid in all_ids:
            role = "🔧 Разработчик" if aid == DEVELOPER_ID else "🛡️ Администратор"
            lines.append(f"{role}: {mention_user(aid)}")
        send(user_id, "\n".join(lines))

    elif cmd == "/ban":
        handle_ban_command(user_id, parts)

    elif cmd == "/banlist":
        bans = db.get_all_bans()
        if not bans:
            send(user_id, "📭 Список банов пуст.")
            return
        lines = ["🚫 Список заблокированных пользователей:\n"]
        for b in bans:
            name = get_user_name(b["user_id"])
            dur = "навсегда" if b["duration"] is None else format_ban_duration(b["duration"])
            lines.append(f"🔹 {name} (ID: {b['user_id']}) — {dur}\n📝 Причина: {b.get('reason', 'не указана')}")
        send(user_id, "\n\n".join(lines))

    elif cmd == "/unban":
        if len(parts) < 2:
            send(user_id, "⚠️ Использование: /unban @user или /unban ID")
            return
        target = extract_user_id(parts[1])
        if not target:
            send(user_id, "⚠️ Не удалось определить пользователя.")
            return
        if db.unban_user(target):
            name = get_user_name(target)
            send(user_id, f"✅ Пользователь {name} (ID: {target}) разблокирован.")
            send(target, "🎉 Вы были разблокированы в системе поддержки.")
        else:
            send(user_id, "ℹ️ Этот пользователь не заблокирован.")


def handle_ban_command(admin_id: int, parts: list):
    if len(parts) < 2:
        send(admin_id,
            "⚠️ Использование:\n"
            "/ban @user [срок] [причина]\n"
            "/ban @user — перманентная блокировка")
        return

    target = extract_user_id(parts[1])
    if not target:
        send(admin_id, "⚠️ Не удалось определить пользователя.")
        return

    if target == DEVELOPER_ID:
        send(admin_id, "⚠️ Нельзя заблокировать разработчика.")
        return

    remaining = parts[2:]
    duration = None
    reason = "не указана"

    if remaining:
        parsed = parse_duration(" ".join(remaining[:2]))
        if parsed is not None:
            duration = parsed
            reason = " ".join(remaining[2:]) if len(remaining) > 2 else "не указана"
        else:
            reason = " ".join(remaining)

    db.ban_user(target, reason, duration)
    db.close_all_user_tickets(target)

    target_name = get_user_name(target)

    if duration is None:
        dur_str = "Навсегда"
    else:
        dur_str = format_ban_duration(duration)

    send(admin_id,
        f"✅ Вы успешно заблокировали пользователя {target_name}\n"
        f"📅 Срок: {dur_str}\n"
        f"📝 Причина: {reason}")

    send(target,
        f"🚫 Вы были заблокированы администрацией за нарушения правил.\n"
        f"📅 Срок: {dur_str}\n"
        f"📝 Причина: {reason}")

    send_to_other_admins(admin_id,
        f"🚫 Администратор {mention_user(admin_id)} заблокировал пользователя {mention_user(target)}\n"
        f"📅 Срок: {dur_str}\n"
        f"📝 Причина: {reason}")
