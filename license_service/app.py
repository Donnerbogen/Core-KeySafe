import os, time, base64, secrets, hashlib, json, threading, logging
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv
import requests

load_dotenv()
app = FastAPI(title="CORE KeySafe License Service", docs_url=None, redoc_url=None)
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
LICENSE_DAYS = int(os.getenv("LICENSE_DAYS", "365"))
OFFLINE_GRACE_HOURS = min(72, max(1, int(os.getenv("OFFLINE_GRACE_HOURS", "72"))))
# Lizenzdaten werden in einer einzelnen JSON-Datei in einem PRIVATEN GitHub-Repository gespeichert.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "").strip()  # owner/repository
GITHUB_STORE_PATH = os.getenv("GITHUB_STORE_PATH", "data/keysafe_store.json").strip().strip("/")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
GITHUB_API_URL = "https://api.github.com"
STORE_LOCK = threading.RLock()


def _github_headers():
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY or not GITHUB_STORE_PATH or not GITHUB_BRANCH:
        raise RuntimeError("GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_STORE_PATH und GITHUB_BRANCH müssen konfiguriert sein")
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CORE-KeySafe-License-Service",
    }


def _github_file_url():
    from urllib.parse import quote
    return f"{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/contents/{quote(GITHUB_STORE_PATH, safe='/')}"


def _read_remote_file():
    response = requests.get(
        _github_file_url(), headers=_github_headers(),
        params={"ref": GITHUB_BRANCH}, timeout=15,
    )
    if response.status_code == 404:
        return None, None
    if response.status_code != 200:
        raise RuntimeError(f"GitHub-Datei konnte nicht gelesen werden (HTTP {response.status_code}): {response.text[:300]}")
    result = response.json()
    if result.get("type") != "file" or not result.get("content"):
        raise RuntimeError("Die konfigurierte GitHub-Speicherdatei ist keine lesbare Datei")
    try:
        raw = base64.b64decode(result["content"]).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Die JSON-Datei im GitHub-Repository ist ungültig") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Die GitHub-Speicherdatei muss ein JSON-Objekt enthalten")
    data.setdefault("licenses", [])
    data.setdefault("audit", [])
    data.setdefault("issue_events", {})
    return data, result.get("sha")

ISSUE_LIMIT = 5
ISSUE_WINDOW_SECONDS = 24 * 60 * 60


def private_key():
    raw = os.getenv("LICENSE_SIGNING_PRIVATE_KEY", "")
    if not raw:
        raise RuntimeError("LICENSE_SIGNING_PRIVATE_KEY is not configured")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))


def _empty_store():
    return {"licenses": [], "audit": [], "issue_events": {}}


def _read_store():
    data, _sha = _read_remote_file()
    return data if data is not None else _empty_store()


def _write_store(data):
    # GitHub Contents API erstellt bei jeder Änderung einen Commit. Das Repository
    # muss privat sein. STORE_LOCK schützt innerhalb einer einzelnen Serverinstanz.
    _data, current_sha = _read_remote_file()
    encoded = base64.b64encode(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    payload = {
        "message": "Update CORE KeySafe license store",
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if current_sha:
        payload["sha"] = current_sha
    response = requests.put(_github_file_url(), headers=_github_headers(), json=payload, timeout=20)
    if response.status_code not in (200, 201):
        # 409/422 häufig bedeuten, dass die Datei zwischenzeitlich geändert wurde.
        raise RuntimeError(f"GitHub-Datei konnte nicht gespeichert werden (HTTP {response.status_code}): {response.text[:300]}")


def hash_key(key):
    return hashlib.sha256(key.strip().encode()).hexdigest()


def now_ts():
    return int(time.time())


def issue_ticket(license_row, device):
    issued = now_ts()
    expires = int(datetime.fromisoformat(license_row["expires_at"].replace("Z", "+00:00")).timestamp())
    payload = {"license_id": license_row["id"], "device_id": device, "issued_at": issued,
               "offline_until": min(issued + OFFLINE_GRACE_HOURS * 3600, expires),
               "expires_at": expires, "license_version": 1}
    signature = private_key().sign(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return {"payload": payload, "signature": base64.b64encode(signature).decode()}


class CheckRequest(BaseModel):
    license_key: str
    device_id: str


class ReleaseRequest(BaseModel):
    license_key: str
    device_id: str


def client_ip(request: Request):
    return request.client.host if request.client else "unknown"


def audit(store, license_id, event, metadata=None):
    store["audit"].append({"id": secrets.token_hex(12), "license_id": license_id,
                           "event": event, "metadata": metadata or {}, "at": datetime.now(timezone.utc).isoformat()})
    # Keep the local file from growing without bound.
    store["audit"] = store["audit"][-10000:]


@app.get("/", response_class=HTMLResponse)
def home():
    content = """
      <h1>CORE KeySafe</h1>
      <p>Erzeuge kostenlos einen Lizenzschlüssel für CORE KeySafe. Es ist kein CORE Account erforderlich.</p>
      <p class="muted">Der Schlüssel gilt ein Jahr und wird beim ersten Aktivieren an ein Gerät gebunden.</p>
      <form method="post" action="/generate"><button>Lizenzschlüssel erstellen</button></form>
      <p class="muted">Der vollständige Schlüssel wird nur einmal angezeigt. Bewahre ihn sicher auf.</p>
    """
    return HTMLResponse(PAGE.replace("{{BASE}}", APP_BASE_URL).replace("{{CONTENT}}", content))


@app.post("/generate", response_class=HTMLResponse)
def generate(request: Request):
    ip = client_ip(request)
    now = now_ts()
    key = "CORE-" + "-".join(secrets.token_hex(4).upper() for _ in range(4))
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(days=LICENSE_DAYS)
    row = {"id": secrets.token_hex(16), "key_hash": hash_key(key), "key_prefix": key[:9],
           "status": "active", "issued_at": issued.isoformat(), "expires_at": expires.isoformat(),
           "device_id": None, "activated_at": None, "released_at": None}
    try:
        with STORE_LOCK:
            store = _read_store()
            recent = [stamp for stamp in store["issue_events"].get(ip, []) if now - stamp < ISSUE_WINDOW_SECONDS]
            if len(recent) >= ISSUE_LIMIT:
                store["issue_events"][ip] = recent
                _write_store(store)
                raise HTTPException(429, "Zu viele Lizenzschlüssel-Anfragen. Bitte versuche es morgen erneut.")
            store["licenses"].append(row)
            store["issue_events"][ip] = recent + [now]
            audit(store, row["id"], "issued", {"key_prefix": row["key_prefix"], "expires_at": expires.isoformat()})
            _write_store(store)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Der Lizenzspeicher ist nicht verfügbar: {exc}") from exc
    safe = key.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    content = ("<h1>Lizenz erstellt</h1><p>Kopiere den Schlüssel jetzt. Er wird nicht erneut im Klartext angezeigt.</p>"
        f'<pre id="key">{safe}</pre><button onclick="navigator.clipboard.writeText(document.getElementById(\'key\').innerText)">Kopieren</button>'
        f"<p>Ablauf: {expires.isoformat()}</p><a href='/'>Zurück</a>")
    return HTMLResponse(PAGE.replace("{{BASE}}", APP_BASE_URL).replace("{{CONTENT}}", content))


@app.post("/api/license/check")
def check(req: CheckRequest):
    if len(req.license_key) > 128 or len(req.device_id) > 128:
        raise HTTPException(400, "Ungültige Anfrage.")
    with STORE_LOCK:
        store = _read_store()
        lic = next((x for x in store["licenses"] if x.get("key_hash") == hash_key(req.license_key)), None)
        if not lic:
            return JSONResponse({"ok": False, "message": "Lizenzschlüssel ist ungültig."}, status_code=403)
        if lic.get("status") != "active":
            return JSONResponse({"ok": False, "message": "Lizenz ist gesperrt oder widerrufen."}, status_code=403)
        expires = int(datetime.fromisoformat(lic["expires_at"].replace("Z", "+00:00")).timestamp())
        if now_ts() >= expires:
            return JSONResponse({"ok": False, "message": "Lizenz ist abgelaufen."}, status_code=403)
        if lic.get("device_id") and lic["device_id"] != req.device_id:
            return JSONResponse({"ok": False, "message": "Lizenz ist bereits an ein anderes Gerät gebunden. Bitte dort online auswerfen."}, status_code=409)
        if not lic.get("device_id"):
            lic["device_id"] = req.device_id
            lic["activated_at"] = datetime.now(timezone.utc).isoformat()
        ticket = issue_ticket(lic, req.device_id)
        audit(store, lic["id"], "checked", {"device_id": req.device_id})
        _write_store(store)
    return {"ok": True, "message": "Lizenz gültig.", "expires_at": expires, "ticket": ticket}


@app.post("/api/license/release")
def release(req: ReleaseRequest):
    if len(req.license_key) > 128 or len(req.device_id) > 128:
        raise HTTPException(400, "Ungültige Anfrage.")
    with STORE_LOCK:
        store = _read_store()
        lic = next((x for x in store["licenses"] if x.get("key_hash") == hash_key(req.license_key)), None)
        if not lic:
            return JSONResponse({"ok": False, "message": "Lizenz nicht gefunden."}, status_code=404)
        if lic.get("device_id") != req.device_id:
            return JSONResponse({"ok": False, "message": "Diese Lizenz ist nicht an dieses Gerät gebunden."}, status_code=403)
        lic["device_id"] = None
        lic["released_at"] = datetime.now(timezone.utc).isoformat()
        audit(store, lic["id"], "released", {"device_id": req.device_id})
        _write_store(store)
    return {"ok": True, "message": "Lizenz wurde freigegeben."}


@app.get("/health")
def health():
    # Liveness-Check für Render: bestätigt, dass die API läuft.
    # Der GitHub-Speicher wird separat geprüft, damit ein temporärer GitHub-Fehler
    # nicht dazu führt, dass Render den gesamten Dienst ständig neu startet.
    return {"ok": True, "service": "CORE KeySafe License Service"}


@app.get("/health/storage")
def health_storage():
    # Separater Diagnose-Endpunkt: prüft, ob der konfigurierte GitHub-Speicher
    # erreichbar und als JSON lesbar ist. Details landen nur in den Server-Logs.
    try:
        with STORE_LOCK:
            _read_store()
        return {"ok": True, "storage": "github-file", "message": "GitHub-Speicher ist erreichbar."}
    except Exception as exc:
        logging.getLogger("uvicorn.error").exception("GitHub-Lizenzspeicher-Prüfung fehlgeschlagen")
        raise HTTPException(
            status_code=503,
            detail="GitHub-Lizenzspeicher ist nicht verfügbar. Siehe Render-Logs für die genaue Ursache.",
        ) from exc


PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CORE KeySafe Lizenzportal</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#123143,#07101b 55%);color:#eaf7ff;font:16px system-ui,sans-serif;min-height:100vh;display:grid;place-items:center;padding:24px}
main{width:min(850px,100%);background:#091725eF;border:1px solid #1f5969;border-radius:20px;padding:clamp(22px,5vw,44px);box-shadow:0 20px 80px #0008}h1{color:#59dbe7;margin-top:0}h2{margin-top:32px}.warning{color:#ffcc7a;background:#3b2a10;padding:12px;border-radius:8px}hr{border:0;border-top:1px solid #244052;margin:26px 0}label{display:block;margin:14px 0 6px}input{width:100%;padding:12px;border-radius:8px;border:1px solid #315366;background:#07111d;color:white}button{margin-top:18px;padding:12px 18px;border:1px solid #278091;border-radius:9px;background:#103d4b;color:#effcff;font-weight:700;cursor:pointer}button:hover{background:#175568}.secondary{background:#202b38}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #244052}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#06101b;padding:16px;border-radius:10px;border:1px solid #2d6777}.muted{color:#9ab3c4;font-size:.9rem}a{color:#69e0ea}form{margin-bottom:10px}
</style></head><body><main>{{CONTENT}}</main></body></html>"""
