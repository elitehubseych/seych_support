import os
import vk_api
import time
import re
import json
from flask import Flask, request
from vk_api.utils import get_random_id
from config import GROUP_TOKEN, CHAT_READ, CHAT_WRITE, CONFIRM_CODE, ROLE_CHECKER_ID, DEVELOPER_ID

app = Flask(__name__)

if not GROUP_TOKEN:
    print("ОШИБКА: GROUP_TOKEN не задан!", flush=True)
    exit(1)
print(f"GROUP_TOKEN: {GROUP_TOKEN[:10]}...", flush=True)

vk = vk_api.VkApi(token=GROUP_TOKEN)
api = vk.get_api()

pending = {}
state = {"stickers_disabled": True}

STICKER_FILE = "stickers_state.json"

def load_sticker_state():
    try:
        with open(STICKER_FILE, "r") as f:
            state["stickers_disabled"] = json.load(f).get("disabled", True)
    except:
        state["stickers_disabled"] = True

def save_sticker_state():
    with open(STICKER_FILE, "w") as f:
        json.dump({"disabled": state["stickers_disabled"]}, f)

load_sticker_state()


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def send_msg(peer_id, message):
    try:
        api.messages.send(peer_id=peer_id, message=message, random_id=get_random_id())
        log(f"-> [{peer_id}] {message}")
    except Exception as e:
        log(f"Ошибка отправки в {peer_id}: {e}")


def get_chat_title(peer_id):
    try:
        chats = api.messages.getConversationsById(peer_ids=peer_id)
        for item in chats.get("items", []):
            if "chat_settings" in item:
                return item["chat_settings"].get("title", "Беседа")
    except:
        pass
    return "Беседа"


def is_sticker(msg):
    attachments = msg.get("attachments", [])
    for a in attachments:
        if a.get("type") == "sticker":
            return True
    return False


me = api.groups.getById()
group_id = me[0]["id"]
log(f"Группа: {me[0]['name']} (ID: {group_id})")
log(f"Stickers disabled: {state['stickers_disabled']}")

chat_title = get_chat_title(CHAT_READ)
log(f"Основной чат: {chat_title} ({CHAT_READ})")


@app.route("/vk", methods=["POST"])
def vk_callback():
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        data = dict(request.form)

    if data.get("type") == "confirmation":
        return CONFIRM_CODE

    if data.get("type") == "message_new":
        msg = data["object"]["message"]
        text = msg.get("text", "").strip()
        from_id = msg.get("from_id", 0)
        chat_id = msg.get("peer_id", 0)
        msg_id = msg.get("conversation_message_id", 0)

        log(f"Чат {chat_id} | Из {from_id}: {text}")

        if from_id < 0:
            log(f"Сообщение от группы {from_id}: {text}")

        if chat_id == CHAT_WRITE and from_id != DEVELOPER_ID:
            if is_sticker(msg) and state["stickers_disabled"]:
                cm_id = msg.get("conversation_message_id", 0)
                try:
                    api.messages.delete(conversation_message_ids=str(cm_id), peer_id=chat_id)
                    log(f"Удалён стикер от {from_id} в архивном чате, cm_id={cm_id}")
                except Exception as e:
                    log(f"Ошибка удаления стикера (cm_id={cm_id}): {e}")
                return "ok"
            attachments = msg.get("attachments", [])
            if attachments:
                log(f"Вложения от {from_id}: {json.dumps(attachments, ensure_ascii=False)[:300]}")

        if chat_id == CHAT_WRITE and text.lower() == "/stick":
            if from_id != DEVELOPER_ID:
                send_msg(CHAT_WRITE, "Только разработчик может управлять стикерами.")
                return "ok"
            state["stickers_disabled"] = not state["stickers_disabled"]
            save_sticker_state()
            title = get_chat_title(CHAT_READ)
            if state["stickers_disabled"]:
                send_msg(CHAT_WRITE, f"Стиcker запрещены в «{title}»")
            else:
                send_msg(CHAT_WRITE, f"Стиcker разрешены в «{title}»")
            return "ok"

        if text.lower().startswith("code ") and chat_id == CHAT_READ:
            parts = text.split(None, 1)
            if len(parts) < 2:
                return "ok"
            target = parts[1]
            mention = re.search(r'\[id(\d+)\|@?([^\]]+)\]', target)
            if mention:
                target_name = mention.group(2)
                target_id = mention.group(1)
            else:
                return "ok"

            pending[str(from_id)] = {"target_name": target_name, "target_id": target_id, "from_id": from_id}
            send_msg(CHAT_WRITE, f"Роль [id{from_id}|@]")
            log(f"code от {from_id} -> проверяю роль [id{from_id}|@] в архивном чате")

        if text.lower().startswith("/pir"):
            send_msg(chat_id, f"Бот работает! Группа: {me[0]['name']} (ID: {group_id})")

        if from_id == ROLE_CHECKER_ID:
            log(f"Ответ от роль-чекера: {text}")
            match = re.search(r'Роль\s+\[id(\d+)\|?([^\]]*)\]\s*[—–\-]\s*\[([^\]]+)\]', text, re.IGNORECASE)
            if match:
                role_user_id = match.group(1)
                role_name = match.group(3)
                log(f"Роль для id{role_user_id}: {role_name}")

                for writer_id, d in list(pending.items()):
                    if str(d["from_id"]) == str(role_user_id):
                        if role_name.upper() == "LUXE":
                            send_msg(CHAT_WRITE, f"Капча @{d['target_name']} 5 минут !mute %user% 1 минута")
                            log(f"LUXE -> Капча для {d['target_name']}")
                        else:
                            log(f"Роль {role_name} != LUXE")
                        del pending[writer_id]
                        break

    return "ok"


@app.route("/")
def index():
    return "Seych 2.0 running"


@app.route("/ping")
def ping():
    return "pong"


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    log(f"PORT={port}")
    log(f"CHAT_WRITE={CHAT_WRITE}")
    app.run(host="0.0.0.0", port=port)
