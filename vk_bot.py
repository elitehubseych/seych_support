import os
import vk_api
import time
import re
from flask import Flask, request
from vk_api.utils import get_random_id
from config import GROUP_TOKEN, CHAT_READ, CHAT_WRITE, CONFIRM_CODE, ROLE_CHECKER_ID

app = Flask(__name__)

if not GROUP_TOKEN:
    print("ОШИБКА: GROUP_TOKEN не задан!", flush=True)
    exit(1)
print(f"GROUP_TOKEN: {GROUP_TOKEN[:10]}...", flush=True)

vk = vk_api.VkApi(token=GROUP_TOKEN)
api = vk.get_api()

pending = {}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def send_msg(peer_id, message):
    try:
        api.messages.send(peer_id=peer_id, message=message, random_id=get_random_id())
        log(f"-> [{peer_id}] {message}")
    except Exception as e:
        log(f"Ошибка отправки в {peer_id}: {e}")


me = api.groups.getById()
group_id = me[0]["id"]
log(f"Группа: {me[0]['name']} (ID: {group_id})")


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

        log(f"Чат {chat_id} | Из {from_id}: {text}")

        if from_id < 0:
            log(f"Сообщение от группы {from_id}: {text}")

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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    log(f"PORT={port}")
    log(f"CHAT_WRITE={CHAT_WRITE}")
    app.run(host="0.0.0.0", port=port)
