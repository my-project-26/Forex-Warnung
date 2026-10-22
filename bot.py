#!/usr/bin/env python3
"""Forex Factory: Vorabendübersicht für alle Ereignisse des Folgetags."""
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "seen_events.json"
BASE = "https://nfs.faireconomy.media/"
BERLIN = ZoneInfo("Europe/Berlin")
IMPACT = {"low": "🟡", "medium": "🟠", "high": "🔴"}
MAX_MESSAGE = 3500

def get_json(url, data=None):
    payload = urlencode(data).encode() if data is not None else None
    req = Request(url, data=payload, headers={"User-Agent": "ForexWarningBot/1.1", "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)

def parse_date(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Kalenderdatum ohne Zeitzone")
    return dt.astimezone(BERLIN)

def load_calendar(tomorrow, today):
    # Am Sonntag liegen Montags-Termine in der nächsten Kalenderwoche.
    feed = "ff_calendar_nextweek.json" if today.weekday() == 6 else "ff_calendar_thisweek.json"
    events = get_json(BASE + feed)
    if not isinstance(events, list) or not events:
        raise ValueError("Kalenderdaten fehlen oder haben ein ungültiges Format")
    result = []
    for e in events:
        if not isinstance(e, dict) or not all(k in e for k in ("title", "date", "country", "impact")):
            raise ValueError("Unerwartetes Datenformat von Forex Factory")
        dt = parse_date(e["date"])
        impact = str(e["impact"]).strip().lower()
        if dt.date() == tomorrow and impact in IMPACT:
            result.append((dt, impact, e))
    return sorted(result, key=lambda x: (x[0], x[2]["country"], x[2]["title"]))

def send_message(token, chat_id, msg):
    result = get_json(f"https://api.telegram.org/bot{token}/sendMessage", {
        "chat_id": chat_id, "text": msg, "disable_web_page_preview": "true"
    })
    if not result.get("ok"):
        raise RuntimeError("Telegram hat die Nachricht nicht akzeptiert")

def save(state):
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)

def event_key(dt, impact, e):
    val = "\x1f".join([dt.isoformat(), impact, str(e["country"]), str(e["title"])])
    return hashlib.sha256(val.encode()).hexdigest()

def run():
    now = datetime.now(BERLIN)
    if now.hour < 17 or now.hour >= 23:
        logging.info("Vorabinformation startet erst um 17 Uhr Berlin; jetzt %s.", now.strftime("%H:%M"))
        return
    token = os.getenv("BOT_TOKEN", "").strip()
    chat_id = os.getenv("CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("BOT_TOKEN oder CHAT_ID fehlt")
    tomorrow = now.date() + timedelta(days=1)
    entries = load_calendar(tomorrow, now.date())
    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Gespeicherter Stand ist ungültig")
    delivered = state.setdefault("announced_next_day", {})
    if not isinstance(delivered, dict):
        raise ValueError("Gespeicherte Ankündigungen sind ungültig")
    day = tomorrow.isoformat()
    done = set(delivered.get(day, []))
    pending = []
    for dt, impact, e in entries:
        key = event_key(dt, impact, e)
        if key not in done:
            pending.append((key, f'{IMPACT[impact]} {dt:%H:%M}  {e["country"]} – {e["title"]}'))
    if not pending:
        logging.info("Keine neuen Vorabinformationen für %s (%d Termine im Kalender).", day, len(entries))
        return
    header = f"📅 Forex Factory – Termine für morgen, {tomorrow:%d.%m.%Y}\nZeiten: Deutschland (Berlin)\n\n"
    batch = []
    size = len(header)
    def send_batch(items):
        if not items:
            return
        message = header + "\n".join(line for _, line in items) + "\n\nhttps://www.forexfactory.com/calendar"
        send_message(token, chat_id, message)
        done.update(key for key, _ in items)
        delivered[day] = sorted(done)
        # Aufbewahrungszeit begrenzen, damit der GitHub-Stand klein bleibt
        for d in list(delivered):
            if d < (now.date() - timedelta(days=14)).isoformat():
                del delivered[d]
        save(state)
    for item in pending:
        length = len(item[1]) + 1
        if batch and size + length + 55 > MAX_MESSAGE:
            send_batch(batch)
            batch = []
            size = len(header)
        batch.append(item)
        size += length
    send_batch(batch)
    logging.info("%d Termine für morgen angekündigt.", len(pending))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run()
    except Exception as exc:
        logging.error("Vorabinformation fehlgeschlagen: %s", type(exc).__name__)
        sys.exit(1)
