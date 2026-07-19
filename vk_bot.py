import os
import vk_api
import time
import re
import threading
import base64
import requests
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
from flask import Flask, request

USER_TOKEN = os.environ.get("USER_TOKEN", "")
CHAT_READ = int(os.environ.get("CHAT_READ", "2000000020"))
CHAT_WRITE = int(os.environ.get("CHAT_WRITE", "2000000206"))
ROLE_CHECKER_ID = int(os.environ.get("ROLE_CHECKER_ID", "-218136766"))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "30"))

app = Flask(__name__)


@app.route("/")
def index():
    return """
    <h2>Получение VK токена с IP Render</h2>
    <form method="post" action="/auth">
        <input name="phone" placeholder="Телефон (+7...)"><br><br>
        <input name="password" placeholder="Пароль" type="password"><br><br>
        <button type="submit">Получить токен</button>
    </form>
    """


VK_APP_ID = 2274003
VK_API_V = "5.199"


def vk_auth(phone, password, captcha_sid=None, captcha_key=None):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    resp = s.get("https://oauth.vk.com/authorize", params={
        "client_id": VK_APP_ID,
        "display": "page",
        "redirect_uri": "https://oauth.vk.com/blank.html",
        "scope": "messages",
        "response_type": "token",
        "v": VK_API_V,
    })

    login_page = resp.text
    act_match = re.search(r' action="([^"]+)"', login_page)
    if not act_match:
        raise Exception("Не удалось найти форму входа VK")
    action_url = act_match.group(1).replace("&amp;", "&")

    data = {"email": phone, "pass": password}
    if captcha_sid and captcha_key:
        data["captcha_sid"] = captcha_sid
        data["captcha_key"] = captcha_key

    resp = s.post(action_url, data=data, allow_redirects=False)

    if resp.status_code == 302:
        location = resp.headers.get("Location", "")
        if "access_token" in location:
            token = re.search(r'access_token=([^&]+)', location)
            if token:
                return token.group(1), None, None
        return s.get(location).text, None, None

    html = resp.text

    if "captcha" in html.lower() or "cap_code" in html:
        cap_match = re.search(r'captcha_sid["\s:=]+(\d+)', html)
        cap_img = re.search(r'(https?://[^"\']+captcha[^"\']+)', html)
        if cap_match and cap_img:
            return None, cap_match.group(1), cap_img.group(1)

    if "redirect" in html.lower() or "blank.html" in html:
        redir = re.search(r'location\.href\s*=\s*["\']([^"\']+)', html)
        if redir:
            loc = redir.group(1)
            token = re.search(r'access_token=([^&]+)', loc)
            if token:
                return token.group(1), None, None

    raise Exception(f"Ошибка авторизации. Возможно, нужен код из SMS.")


@app.route("/auth", methods=["POST"])
def auth():
    phone = request.form.get("phone", "")
    password = request.form.get("password", "")
    captcha_sid = request.form.get("captcha_sid", "")
    captcha_answer = request.form.get("captcha_answer", "")
    if not phone or not password:
        return "Заполни все поля"
    try:
        token, new_sid, captcha_url = vk_auth(phone, password)
        if captcha_url:
            r = requests.get(captcha_url, headers={"User-Agent": "Mozilla/5.0"})
            img_data = base64.b64encode(r.content).decode()
            return f"""<h2>CAPTCHA</h2>
            <img src="data:image/jpeg;base64,{img_data}" style="max-width:300px"><br>
            <form method='post' action='/auth'>
                <input name='phone' value='{phone}' type='hidden'>
                <input name='password' value='{password}' type='hidden'>
                <input name='captcha_sid' value='{new_sid}' type='hidden'>
                <input name='captcha_answer' placeholder='Текст с картинки'><br><br>
                <button type='submit'>Отправить</button>
            </form>"""
        if token:
            return f"<h1>ТОКЕН:</h1><textarea rows='3' cols='60'>{token}</textarea>"
        return "Ошибка авторизации"
    except Exception as e:
        return f"Ошибка: {e}"


@app.route("/ping")
def ping():
    return "pong"


def run_bot():
    if not USER_TOKEN:
        print("USER_TOKEN не задан, бот не запускается", flush=True)
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
