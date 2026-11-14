import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import server


ROOT = Path(__file__).resolve().parent


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
APP_URL = os.environ.get("APP_URL", "").strip().rstrip("/")
API_ROOT = f"https://api.telegram.org/bot{TOKEN}"


def telegram(method, payload, timeout=35):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_ROOT}/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {result.get('description', 'unknown error')}")
    return result["result"]


def send_welcome(chat_id, first_name, referred=False):
    keyboard = {
        "inline_keyboard": [[
            {"text": "🚘 Открыть игру", "web_app": {"url": APP_URL}},
        ]],
    }
    name = first_name.strip()[:80] or "друг"
    text = (
        f"Привет, {name}! 👋\n\n"
        "Добро пожаловать в Знакобум! Генерируй автомобильные номера, "
        "собирай редкие комбинации и развивай свою коллекцию.\n\n"
        "Игровые рубли — только очки внутри игры."
    )
    if referred:
        text += "\n\nТы пришёл по приглашению: после первого входа в игру вы оба получите по 50 000 игровых рублей."
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": keyboard,
        "disable_web_page_preview": True,
    })


def main():
    if not TOKEN:
        raise SystemExit("Set BOT_TOKEN in .env before starting the bot.")
    if not APP_URL.startswith("https://"):
        raise SystemExit("APP_URL must be a public HTTPS URL to open the Mini App.")

    info = telegram("getMe", {})
    print(f"Бот @{info['username']} запускается. Остановка: Ctrl+C", flush=True)
    telegram("setChatMenuButton", {
        "menu_button": {
            "type": "web_app",
            "text": "Открыть игру",
            "web_app": {"url": APP_URL},
        },
    })
    offset = None
    while True:
        try:
            params = {"timeout": 25, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            for update in telegram("getUpdates", params):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "").strip()
                if text.split(" ", 1)[0].split("@", 1)[0] == "/start":
                    sender = message.get("from", {})
                    referral = re.fullmatch(r"/start(?:@\w+)?\s+ref_([A-Za-z0-9_-]{8,32})", text)
                    referred = False
                    if referral:
                        try:
                            referred = server.register_referral(referral.group(1), str(sender.get("id", "")))
                        except (OSError, sqlite3.Error, ValueError) as exc:
                            print(f"Referral registration failed: {exc}", file=sys.stderr, flush=True)
                    send_welcome(message["chat"]["id"], sender.get("first_name", "друг"), referred)
        except KeyboardInterrupt:
            print("\nБот остановлен.", flush=True)
            return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError, KeyError) as exc:
            print(f"Ошибка Telegram API: {exc}", file=sys.stderr, flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
