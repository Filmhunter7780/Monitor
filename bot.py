"""
Бот слежения за посылками anytrack.kz -> Telegram.
Для Render (Web Service, Docker) + UptimeRobot.
"""
import json
import os
import re
import time
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright

TG_TOKEN = os.environ["TG_TOKEN"]  # токен бота — в Environment на Render
LOGIN = os.environ.get("TRACK_LOGIN", "1324")
PASSWORD = os.environ.get("TRACK_PASSWORD", "Savage21")
URL = "https://7999.anytrack.kz/public/#/my-tracks"
INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600"))  # секунд
STATE_FILE = "state.json"
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
JS_PARCELS = """() => {
  const cnt = t => (t.match(/Статус:/g) || []).length;
  const out = new Set();
  document.querySelectorAll('*').forEach(el => {
    if (el.children.length === 0 && /^Статус:/.test(el.textContent.trim())) {
      let node = el;
      while (node.parentElement &&
             cnt(node.parentElement.innerText) === 1 &&
             !node.parentElement.innerText.includes('Мои посылки')) {
        node = node.parentElement;
      }
      out.add(node.innerText.trim().replace(/\\s+/g, ' '));
    }
  });
  return [...out];
}"""


def fetch_rows():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            page = browser.new_page()
            page.goto(URL, wait_until="networkidle")

            if page.locator("input[type=password]").count():
                pwd = page.locator("input[type=password]").first
                usr = page.locator(
                    "input:not([type=password]):not([type=hidden]):not([type=checkbox])"
                ).first
                usr.fill(LOGIN)
                pwd.fill(PASSWORD)
                pwd.press("Enter")
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                if "my-tracks" not in page.url:
                    page.goto(URL, wait_until="networkidle")
                time.sleep(2)

            rows = page.evaluate(JS_PARCELS)
            if not rows:
                rows = [page.inner_text("body").strip()]
            return rows
        finally:
            browser.close()


# ---------- Состояние ----------
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return None


def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), ensure_ascii=False)


def key(row):
    m = re.search(r"\b\d{9,}\b", row)  # трек-номер
    if m:
        return m.group(0)
    m = re.search(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}", row)  # дата
    return m.group(0) if m else row[:30]


# ---------- Основной цикл ----------
def main():
    threading.Thread(target=run_server, daemon=True).start()
    chat_id = get_chat_id()
    notify(chat_id, "✅ Бот слежения за посылками запущен")
    while True:
        try:
            rows = fetch_rows()
            current = {key(r): r for r in rows}
            old = load_state()
            if old is None:
                save_state(current)
                notify(chat_id, f"Сохранил текущее состояние: {len(current)} записей.")
            else:
                for k, r in current.items():
                    if k not in old:
                        notify(chat_id, f"🆕 Новая посылка:\n{r}")
                    elif old[k] != r:
                        notify(chat_id, f"📦 Изменение:\n{r}\n\nБыло:\n{old[k]}")
                save_state(current)
        except Exception as e:
            print("Ошибка:", e, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
