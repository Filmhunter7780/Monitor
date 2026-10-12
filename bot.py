"""
Бот: следит за посылками на anytrack.kz и шлёт изменения в Telegram.

Установка:
    pip install playwright requests
    playwright install chromium

Запуск (значения берутся из переменных окружения):
    export TG_TOKEN="токен_бота"
    export TRACK_LOGIN="логин"
    export TRACK_PASSWORD="пароль"
    export TG_CHAT_ID="ваш_chat_id"   # необязательно, определится сам
    python track_bot.py
"""
import json
import os
import time
import hashlib
import requests
from playwright.sync_api import sync_playwright

TG_TOKEN = os.environ["8755313794:AAEq9SVhCe_My_nkRNUdu3ekboMZQZ-AqUY"]
LOGIN = os.environ["1324"]
PASSWORD = os.environ["Savage21"]
URL = "https://7999.anytrack.kz/public/#/my-tracks"
INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600"))  # секунд
STATE_FILE = "state.json"
CHAT_FILE = "chat_id.txt"


# ---------- Telegram ----------
def tg(method, **params):
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}",
                      json=params, timeout=30)
    return r.json()

