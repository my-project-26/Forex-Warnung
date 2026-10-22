#!/usr/bin/env python3
"""Einmalige Prüfung neuer Forex-Factory-Ereignisse (Low/Medium/High)."""
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "seen_events.json"
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
BERLIN = ZoneInfo("Europe/Berlin")

def get_json(url, data=None):
    payload = urlencode(data).encode() if data is not None else None
    req = Request(url, data=payload, headers={"User-Agent": "ForexFactoryTelegramAlert/1.0", "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)

def fetch_events():
    events = get_json(FEED_URL)
    if not isinstance(events, list) or not events:
        raise ValueError("Kalenderantwort ist leer oder kein JSON-Array.")
    for event in events:
        if not isinstance(event, dict) or not all(k in event for k in ("date", "country", "title", "impact")):
            raise ValueError("Unerwartetes Kalenderformat.")
    return events

def parse_date(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Datum ohne Zeitzone")
    return dt

def week_id(events):
    earliest = min(parse_date(x["date"]).astimezone(BERLIN).date() for x in events)
    return (earliest - timedelta(days=(earliest.weekday() + 1) % 7)).isoformat()

def key_for(event):
    text = "\x1f".join(str(event[k]).strip() for k in ("date", "country", "title"))
    return hashlib.sha256(text.encode()).hexdigest()

def send_alert(token, chat_id, event):
    date = parse_date(event["date"]).astimezone(BERLIN).strftime("%d.%m.%Y, %H:%M Uhr (Berlin)")
    impact = str(event["impact"]).strip().casefold()
    icon, label = {"low": ("🟡", "LOW"), "medium": ("🟠", "MEDIUM"), "high": ("🔴", "HIGH")}[impact]
    message = (
        f"{icon} NEUES {label}-IMPACT-EREIGNIS\n\n"
        f"Währung: {event['country']}\n"
        f"Ereignis: {event['title']}\n"
        f"Termin: {date}\n\n"
        "Neu im Forex-Factory-Wochenkalender erkannt.\n"
        "https://www.forexfactory.com/calendar"
    )
    answer = get_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"},
    )
    if answer.get("ok") is not True:
        raise RuntimeError("Telegram hat die Nachricht nicht akzeptiert.")

def save(state):
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)

def run():
    token = os.environ.get("BOT_TOKEN", "").strip()
    chat_id = os.environ.get("CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("GitHub-Secrets BOT_TOKEN und CHAT_ID fehlen.")
    events = fetch_events()
    week = week_id(events)
    snapshot = {key_for(e): str(e["impact"]).strip().casefold() for e in events}
    state = None
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("events"), dict):
            raise ValueError("Gespeicherter Kalenderstand ungültig.")
    if state is None or state.get("week") != week:
        save({"week": week, "events": snapshot})
        logging.info("Ausgangsbestand gespeichert: %d Einträge; keine Alarme.", len(events))
        return
    seen = state["events"]
    sent = 0
    for e in events:
        key = key_for(e)
        impact = str(e["impact"]).strip().casefold()
        if impact in ("low", "medium", "high") and seen.get(key) != impact:
            send_alert(token, chat_id, e)
            sent += 1
            seen[key] = "high"
            save(state)
        else:
            seen[key] = impact
    save(state)
    logging.info("Geprüft: %d Ereignisse, %d neue Warnungen (Gelb/Orange/Rot).", len(events), sent)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run()
    except Exception as exc:
        logging.error("Prüfung fehlgeschlagen: %s", type(exc).__name__)
        sys.exit(1)
