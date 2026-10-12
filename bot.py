"""
Бот слежения за посылками anytrack.kz -> Telegram.
Для Render (Web Service) + UptimeRobot, чтобы не засыпал.

Переменные окружения (Render -> Environment):
  TG_TOKEN        - токен бота (обязательно)
  TRACK_LOGIN     - логин на сайте (обязательно)
  TRACK_PASSWORD  - пароль на сайте (обязательно)
  TG_CHAT_ID      - ваш chat id (желательно)
  CHECK_INTERVAL  - интервал проверки в секундах (по умолчанию 600)
"""
import json
import os
import time
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright

TG_TOKEN = os.environ["TG_TOKEN"]
LOGIN = os.environ["TRACK_LOGIN"]
PASSWORD = os.environ["TRACK_PASSWORD"]
URL = "https://7999.anytrack.kz/public/#/my-tracks"
INTERVAL = int(os.environ.get("CHECK_INTERVAL", "180"))  # секунд
STATE_FILE = "state_v2.json"
CHAT_FILE = "chat_id.txt"


# ---------- Веб-сервер для UptimeRobot ----------
class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def run_server():
    port = int(os.environ.get("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), Ping).serve_forever()


# ---------- Telegram ----------
def tg(method, **params):
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}",
                      json=params, timeout=30)
    return r.json()


def get_chat_id():
    if os.environ.get("TG_CHAT_ID"):
        return os.environ["TG_CHAT_ID"]
    if os.path.exists(CHAT_FILE):
        return open(CHAT_FILE).read().strip()
    for upd in reversed(tg("getUpdates").get("result", [])):
        msg = upd.get("message")
        if msg:
            cid = str(msg["chat"]["id"])
            open(CHAT_FILE, "w").write(cid)
            return cid
    raise SystemExit("Напишите боту /start и задайте TG_CHAT_ID.")


def notify(chat_id, text):
    tg("sendMessage", chat_id=chat_id, text=text[:4000])


# ---------- Парсинг сайта ----------
JS_PARSE = """
() => [...document.querySelectorAll('app-tracks-list .p-dataview-content .col-12')].map(card => {
  const t = s => (card.querySelector(s)?.innerText || '').trim();
  const number = t('.text-2xl');
  const name = t('.font-bold.text-500');
  const status = t('.status-value');
  const dateEl = [...card.querySelectorAll('div')].find(
    d => /^\\d{2}\\.\\d{2}\\.\\d{4}/.test(d.innerText.trim()) && d.children.length === 0
  );
  const date = dateEl ? dateEl.innerText.trim() : '';
  return {number, name, date, status};
}).filter(x => x.number)
"""


def fetch_rows():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(URL, wait_until="networkidle")
            time.sleep(3)

            if page.locator("input[type=password]").count():
                pwd = page.locator("input[type=password]").first
                usr = page.locator(
                    "input:not([type=password]):not([type=hidden]):not([type=checkbox])"
                ).first
                usr.fill(LOGIN)
                pwd.fill(PASSWORD)
                btn = page.locator("button, input[type=submit]").first
                if btn.count():
                    btn.click()
                else:
                    pwd.press("Enter")
                time.sleep(5)
                page.goto(URL, wait_until="networkidle")

            # ждём, пока Angular отрисует список
            page.wait_for_selector("app-tracks-list .p-dataview-content", timeout=30000)
            time.sleep(1)

            items = page.evaluate(JS_PARSE)
            return {i["number"]: i for i in items}
        finally:
            browser.close()


# ---------- Состояние ----------
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return None


def save_state(s):
    json.dump(s, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False)


def fmt(i):
    return f"{i['number']}\n{i['name']}\n{i['date']}\nСтатус: {i['status']}"


# ---------- Основной цикл ----------
def main():
    threading.Thread(target=run_server, daemon=True).start()
    chat_id = get_chat_id()
    notify(chat_id, "✅ Бот слежения за посылками запущен")
    while True:
        try:
            current = fetch_rows()
            old = load_state()
            if old is None:
                save_state(current)
                notify(chat_id, f"Сохранил текущее состояние: {len(current)} посылок.")
            else:
                for k, i in current.items():
                    if k not in old:
                        notify(chat_id, f"🆕 Новая посылка:\n{fmt(i)}")
                    elif old[k]["status"] != i["status"]:
                        notify(chat_id,
                               f"📦 Статус изменился:\n{fmt(i)}\n\nБыл: {old[k]['status']}")
                save_state(current)
        except Exception as e:
            print("Ошибка:", e, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
