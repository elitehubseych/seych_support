import os
import json
import vk_api
import time
import re
import threading
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
from flask import Flask, request

USER_TOKEN = os.environ.get("USER_TOKEN", "")
CHAT_READ = int(os.environ.get("CHAT_READ", "2000000020"))
CHAT_WRITE = int(os.environ.get("CHAT_WRITE", "2000000206"))
ROLE_CHECKER_ID = int(os.environ.get("ROLE_CHECKER_ID", "-218136766"))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "30"))

app = Flask(__name__)
token_result = {}


@app.route("/")
def index():
    if token_result.get("token"):
        return f"<h1>ГОТОВО!</h1><textarea rows='3' cols='60'>{token_result['token']}</textarea><p>Добавь в USER_TOKEN</p>"
    return """
    <h2>Получение VK токена с IP Render</h2>
    <form method="post" action="/auth">
        <input name="phone" placeholder="Телефон (+7...)"><br>
        <input name="password" placeholder="Пароль" type="password"><br>
        <button type="submit">Получить токен</button>
    </form>
    """


captcha_sid = None
captcha_img = None


def make_captcha_handler():
    def handler(captcha):
        global captcha_sid, captcha_img
        captcha_sid = captcha.sid
        captcha_img = captcha.get_url()
        return captcha
    return handler


@app.route("/auth", methods=["POST"])
def auth():
    global captcha_sid, captcha_img
    phone = request.form.get("phone", "")
    password = request.form.get("password", "")
    captcha_answer = request.form.get("captcha_answer", "")
    if not phone or not password:
        return "Заполни все поля"
    try:
        kw = dict(login=phone, password=password, app_id=2274003, scope="messages", captcha_handler=make_captcha_handler())
        if captcha_sid and captcha_answer:
            kw["captcha_sid"] = captcha_sid
            kw["captcha_answer"] = captcha_answer
        vk = vk_api.VkApi(**kw)
        vk.auth()
        token = vk.token["access_token"]
        token_result["token"] = token
        captcha_sid = None
        captcha_img = None
        return f"<h1>ТОКЕН:</h1><textarea rows='3' cols='60'>{token}</textarea>"
    except vk_api.exceptions.Captcha as e:
        return f"<h2>Нужна CAPTCHA</h2><img src='{e.get_url()}'><form method='post' action='/auth'><input name='phone' value='{phone}' type='hidden'><input name='password' value='{password}' type='hidden'><input name='captcha_sid' value='{e.sid}' type='hidden'><input name='captcha_answer' placeholder='Введите текст'><button type='submit'>Отправить</button></form>"
    except Exception as e:
        return f"Ошибка: {e}"


@app.route("/ping")
def ping():
    return "pong"


def run_bot():
    if not USER_TOKEN:
        print("USER_TOKEN не задан, бот не запускается")
        return

    vk = vk_api.VkApi(token=USER_TOKEN)
    api = vk.get_api()

    pending = {}
    timers = {}

    def send_msg(peer_id, message):
        try:
            api.messages.send(peer_id=peer_id, message=message, random_id=get_random_id())
            print(f"[{time.strftime('%H:%M:%S')}] -> [{peer_id}] {message}", flush=True)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Ошибка: {e}", flush=True)

    def log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

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

    try:
        me = api.users.get()
        log(f"Бот: {me[0]['first_name']} {me[0]['last_name']} (ID: {me[0]['id']})")
    except Exception as e:
        log(f"Ошибка токена: {e}")
        return

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
                on_code(uid, mention.group(2), mention.group(1))

        if uid == ROLE_CHECKER_ID:
            on_role(uid, text)


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.getenv("PORT", 10000))
    print(f"Сервер на порту {port}", flush=True)
    app.run(host="0.0.0.0", port=port)
