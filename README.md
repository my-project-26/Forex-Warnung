# Forex-Warnung

Überwacht den Forex-Factory-Wochenkalender und meldet **neu erkannte High-Impact-Ereignisse** aller Währungen an Telegram.

## Einmalig einrichten

1. In `Settings → Secrets and variables → Actions` Repository-Secrets `BOT_TOKEN` und `CHAT_ID` anlegen.
2. Unter `Settings → Actions → General` GitHub Actions erlauben. Falls erforderlich: Workflow permissions auf **Read and write permissions** setzen.
3. Unter `Actions → Forex-Warnung → Run workflow` einmal manuell starten.
4. Ersten erfolgreichen Lauf prüfen: Er speichert zunächst nur den aktuellen Bestand in `seen_events.json`.

Danach startet die Prüfung ungefähr alle 15 Minuten. GitHub Actions garantiert keinen exakten Ausführungszeitpunkt. Der Forex-Factory-Wochenexport hat Abruflimits und kann verzögert sein. Beim Wochenwechsel wird der Bestand neu initialisiert. Keine Nachricht bei bereits geplanten Wirtschaftsdaten zu deren Veröffentlichungszeit.

**Sicherheit:** Token niemals im Repository, in Issues oder Screenshots veröffentlichen. Das Repository ist derzeit öffentlich; ausschließlich nicht-geheime Daten hochladen. `seen_events.json` enthält Ereigniskennungen und Bewertungen, keine Zugangsdaten.
