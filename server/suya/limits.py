"""Mengenbegrenzung. Adressen liegen nur im Arbeitsspeicher und nur so lange, wie die Grenze gilt."""
import threading
import time

from . import config

lock = threading.Lock()          # schützt alle Zähler hier und die Prüfungen in api vor dem Speichern
ip_hits = {}                     # Adresse → Zeitpunkte der Anfragen der letzten Stunde
bug_hits = {}
day = {"date": "", "bytes": 0}   # angenommene Bytes heute, insgesamt
donor_bytes = {}                 # Spender → angenommene Bytes heute
ip_bytes = {}                    # Adresse → [(Zeitpunkt, Bytes)] der letzten Stunde (nie länger gehalten)
bug_day = {"date": "", "count": 0}


def reset():
    """Für Tests"""
    with lock:
        ip_hits.clear()
        bug_hits.clear()
        donor_bytes.clear()
        ip_bytes.clear()
        day.update(date="", bytes=0)
        bug_day.update(date="", count=0)


def client_key(handler):
    """Adresse für die Begrenzung; IPv6 je /64-Netz. Der Container ist nur über den DSM-Proxy erreichbar
    (127.0.0.1), dessen Eintrag in X-Forwarded-For steht zuletzt."""
    forwarded = handler.headers.get("X-Forwarded-For", handler.client_address[0])
    ip = forwarded.split(",")[-1].strip()
    if ":" in ip:
        return ":".join(ip.split(":")[:4]) + "::/64"
    return ip


def _hit(table, ip, now):
    hits = [t for t in table.get(ip, []) if now - t < 3600]
    hits.append(now)
    table[ip] = hits
    if len(table) > 10000:       # nur abgelaufene Einträge verwerfen, nie alle Zähler
        for k in [k for k, v in table.items() if now - v[-1] >= 3600]:
            del table[k]
    return len(hits)


def too_many_requests(handler):
    with lock:
        return _hit(ip_hits, client_key(handler), time.time()) > config.REQUESTS_PER_IP_HOUR


def bug_report_allowed(handler):
    """Zählt die Anfrage je Adresse; der Tageszähler steigt erst mit count_bug_report (nur angenommene Berichte)."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with lock:
        n = _hit(bug_hits, client_key(handler), time.time())
        if bug_day["date"] != today:
            bug_day.update(date=today, count=0)
        return n <= config.BUG_PER_IP_HOUR and bug_day["count"] < config.BUG_PER_DAY


def count_bug_report():
    with lock:
        bug_day["count"] += 1


def _roll_day():
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if day["date"] != today:
        day.update(date=today, bytes=0)
        donor_bytes.clear()


def _ip_hour_bytes(ip, now):
    recent = [(t, b) for t, b in ip_bytes.get(ip, []) if now - t < 3600]
    if recent:
        ip_bytes[ip] = recent
    else:
        ip_bytes.pop(ip, None)
    if len(ip_bytes) > 10000:
        for k in [k for k, v in ip_bytes.items() if now - v[-1][0] >= 3600]:
            del ip_bytes[k]
    return sum(b for _, b in recent)


def bytes_refusal(donor, n, ip=None):
    """Fehlertext, wenn n weitere Bytes heute zu viel wären (lock muss gehalten werden), sonst None.
    Ohne App Attest kann sich jeder beliebig viele Spender-Nummern ausdenken; deshalb zusätzlich je Adresse."""
    _roll_day()
    if ip is not None and _ip_hour_bytes(ip, time.time()) + n > config.IP_HOUR_BYTES:
        return 429, "address_limit", "zu viel von dieser Adresse, bitte später"
    if day["bytes"] + n > config.DAY_BYTES:
        return 503, "day_limit", "Tageslimit erreicht"
    if donor_bytes.get(donor, 0) + n > config.DONOR_DAY_BYTES:
        return 429, "donor_day_limit", "Tageslimit für diese Spender-Nummer"
    return None


def add_bytes(donor, n, ip=None):
    """lock muss gehalten werden"""
    _roll_day()
    if ip is not None:
        ip_bytes.setdefault(ip, []).append((time.time(), n))
    day["bytes"] += n
    donor_bytes[donor] = donor_bytes.get(donor, 0) + n
