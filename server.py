import os
import logging
import threading
import time
import urllib.request
from aiohttp import web
from dotenv import load_dotenv
import vk_api
from vk_api.utils import get_random_id

import db
from bot_logic import (
    on_new_message,
    on_callback_button,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("support-bot")

TOKEN = os.getenv("VK_GROUP_TOKEN")
GROUP_ID = int(os.getenv("VK_GROUP_ID", 0))
CONFIRMATION = os.getenv("VK_CONFIRMATION_TOKEN")
SECRET = os.getenv("VK_SECRET_KEY", "")

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()

processing = set()


def send(user_id: int, text: str, keyboard: str = None):
    kwargs = {
        "user_id": user_id,
        "message": text,
        "random_id": get_random_id(),
    }
    if keyboard:
        kwargs["keyboard"] = keyboard
    try:
        vk.messages.send(**kwargs)
    except Exception as e:
        log.error(f"Send error to {user_id}: {e}")


def get_user_name(user_id: int) -> str:
    try:
        resp = vk.users.get(user_ids=user_id)
        if resp:
            u = resp[0]
            return f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
    except Exception:
        pass
    return f"Пользователь {user_id}"


db.init_db()
from bot_logic import init as bot_init
bot_init(vk, send, get_user_name)


RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")


def keep_alive():
    if not RENDER_URL:
        return
    while True:
        time.sleep(300)
        try:
            req = urllib.request.Request(f"{RENDER_URL}/ping", method="GET")
            urllib.request.urlopen(req, timeout=30)
            log.info("💓 Keep-alive ping OK")
        except Exception as e:
            log.warning(f"Keep-alive ping failed: {e}")


threading.Thread(target=keep_alive, daemon=True).start()


async def handle_event(request):
    data = await request.json()
    log.info(f"⬇️ EVENT: type={data.get('type')}")

    if SECRET and data.get("secret") != SECRET:
        log.warning(f"❌ Bad secret!")
        return web.Response(status=1, text="bad secret")

    event_type = data.get("type")

    if event_type == "confirmation":
        log.info(f"✅ Confirmation: {CONFIRMATION}")
        return web.Response(text=CONFIRMATION)

    if event_type == "message_new":
        msg = data["object"]["message"]
        peer_id = msg.get("peer_id", 0)
        from_id = msg.get("from_id", 0)
        text = msg.get("text", "").strip()

        log.info(f"📩 MSG from={from_id} text={text!r}")

        if from_id <= 0:
            return web.Response(text="ok")

        is_dm = (peer_id == from_id)

        try:
            on_new_message(from_id, peer_id, text, is_dm)
        except Exception as e:
            log.exception(f"❌ message_new error: {e}")

        return web.Response(text="ok")

    if event_type == "message_event":
        obj = data["object"]
        user_id = obj.get("user_id", 0)
        peer_id = obj.get("peer_id", 0)
        event_id = obj.get("event_id", "")
        payload_raw = obj.get("payload", "{}")

        log.info(f"🔘 CALLBACK from={user_id} payload={payload_raw!r}")

        try:
            if isinstance(payload_raw, str):
                payload = json.loads(payload_raw)
            else:
                payload = payload_raw
        except (json.JSONDecodeError, TypeError):
            return web.Response(text="ok")

        try:
            vk.messages.sendEvent(
                user_id=user_id,
                peer_id=peer_id,
                event_id=event_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "⏳ Обработка..."}),
            )
        except Exception as e:
            log.error(f"sendEvent error: {e}")

        try:
            on_callback_button(user_id, peer_id, payload)
            log.info(f"✅ Processed callback from={user_id}")
        except Exception as e:
            log.exception(f"❌ message_event error: {e}")

        return web.Response(text="ok")

    return web.Response(text="ok")


app = web.Application()
app.router.add_post("/", handle_event)
app.router.add_get("/ping", lambda r: web.Response(text="pong"))

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("SERVER_PORT", 8080)))
    log.info(f"🚀 Server on {host}:{port}")
    web.run_app(app, host=host, port=port)
