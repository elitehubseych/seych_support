import vk_api
import time
import re
import threading
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import os

USER_TOKEN = os.environ["USER_TOKEN"]
CHAT_READ = int(os.environ.get("CHAT_READ", "2000000020"))
CHAT_WRITE = int(os.environ.get("CHAT_WRITE", "2000000206"))
ROLE_CHECKER_ID = int(os.environ.get("ROLE_CHECKER_ID", "-218136766"))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "30"))

vk = vk_api.VkApi(token=USER_TOKEN)
api = vk.get_api()

pending = {}
timers = {}


def send_msg(peer_id, message):
    try:
        api.messages.send(peer_id=peer_id, message=message, random_id=get_random_id())
        print(f"[{time.strftime('%H:%M:%S')}] -> [{peer_id}] {message}")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Ошибка: {e}")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def on_timeout(writer_id):
    pending.pop(writer_id, None)
    timers.pop(writer_id, None)
    log(f"Таймаут для user {writer_id}")


def on_code(writer_id, target_name, target_id):
    pending[writer_id] = {"target_name": target_name, "target_id": target_id}
    log(f"code @{target_name} (id{target_id}) от user {writer_id}")
    send_msg(CHAT_WRITE, f"роль [id{writer_id}|@]")
    timer = threading.Timer(TIMEOUT_SECONDS, on_timeout, [writer_id])
    timers[writer_id] = timer
    timer.start()


def on_role(from_id, text):
    match = re.search(r'Роль\s+\[id(\d+)\|?([^\]]*)\]\s*[—–\-]\s*\[LUXE\]', text, re.IGNORECASE)
    if not match:
        return

    role_user_id = match.group(1)
    role_user_name = match.group(2)
    log(f"LUXE подтверждён для {role_user_name} (id{role_user_id})")

    if int(role_user_id) in pending:
        data = pending[int(role_user_id)]
        send_msg(CHAT_WRITE, f"Капча @{data['target_name']} 5 минут !mute %user% 1 минута")
        timers.pop(int(role_user_id), None)
        del pending[int(role_user_id)]


me = api.users.get()
log(f"Бот: {me[0]['first_name']} {me[0]['last_name']} (ID: {me[0]['id']})")
log(f"Чтение: {CHAT_READ} | Запись: {CHAT_WRITE} | Роль-чекер: {ROLE_CHECKER_ID}")

lp = VkLongPoll(vk)
log("Ожидание сообщений...")

for event in lp.listen():
    if event.type != VkEventType.MESSAGE_NEW:
        continue

    uid = event.user_id
    pid = event.peer_id
    text = event.text.strip()

    log(f"Чат {pid} | Юзер {uid}: {text}")

    if pid == CHAT_READ and text.lower().startswith('code '):
        mention = re.search(r'\[id(\d+)\|@?([^\]]+)\]', text)
        if mention:
            target_id = mention.group(1)
            target_name = mention.group(2)
            on_code(uid, target_name, target_id)

    if uid == ROLE_CHECKER_ID:
        on_role(uid, text)
