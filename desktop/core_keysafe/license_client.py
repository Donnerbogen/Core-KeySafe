import base64, json, os, time, hashlib, uuid
from pathlib import Path
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from .config import LICENSE_API_URL, LICENSE_SIGNING_PUBLIC_KEY_B64, OFFLINE_GRACE_HOURS

def device_id(state_dir: Path) -> str:
    p = state_dir / "device.id"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    value = str(uuid.uuid4())
    p.write_text(value, encoding="utf-8")
    try: p.chmod(0o600)
    except OSError: pass
    return value

def _public_key():
    try:
        raw = base64.b64decode(LICENSE_SIGNING_PUBLIC_KEY_B64)
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception:
        return None

def verify_ticket(ticket: dict) -> bool:
    pub = _public_key()
    if pub is None: return False
    try:
        signature = base64.b64decode(ticket["signature"])
        payload = ticket["payload"]
        pub.verify(signature, json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        now = int(time.time())
        return now <= int(payload["offline_until"]) and now <= int(payload["expires_at"])
    except (Exception, InvalidSignature):
        return False

def check_license(license_key: str, state_dir: Path):
    """Returns (status, message, signed_ticket_or_none, response_data)."""
    if os.getenv("KEYSAFE_DEV_MODE") == "1":
        return "valid", "Entwicklungsmodus", None, {"expires_at": int(time.time()) + 365*86400, "dev": True}
    if not LICENSE_API_URL.startswith("https://") or "REPLACE-WITH" in LICENSE_API_URL:
        return "error", "Lizenzserver ist noch nicht konfiguriert.", None, {}
    did = device_id(state_dir)
    try:
        r = requests.post(LICENSE_API_URL.rstrip("/") + "/api/license/check",
                          json={"license_key": license_key, "device_id": did},
                          timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                ticket = data.get("ticket")
                if ticket and verify_ticket(ticket):
                    saved = {"license_key": license_key, "device_id": did,
                             "ticket": ticket, "last_success": int(time.time())}
                    (state_dir / "license.json").write_text(json.dumps(saved), encoding="utf-8")
                    try: (state_dir / "license.json").chmod(0o600)
                    except OSError: pass
                return "valid", data.get("message", "Lizenz gültig."), ticket, data
            return "invalid", data.get("message", "Lizenz ungültig."), None, data
        return "invalid", r.json().get("message", "Lizenzprüfung fehlgeschlagen."), None, {}
    except requests.RequestException:
        saved_path = state_dir / "license.json"
        if saved_path.exists():
            try:
                saved = json.loads(saved_path.read_text(encoding="utf-8"))
                ticket = saved["ticket"]
                if saved.get("device_id") == did and verify_ticket(ticket):
                    return "offline", "Offline-Berechtigung aktiv.", ticket, ticket["payload"]
            except Exception:
                pass
        return "offline_denied", "Lizenzserver nicht erreichbar und keine gültige Offline-Berechtigung vorhanden.", None, {}

def release_license(state_dir: Path):
    if os.getenv("KEYSAFE_DEV_MODE") == "1":
        return True, "Entwicklungsmodus: Freigabe simuliert."
    saved_path = state_dir / "license.json"
    if not saved_path.exists(): return False, "Keine gespeicherte Lizenz gefunden."
    try:
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        r = requests.post(LICENSE_API_URL.rstrip("/") + "/api/license/release",
                          json={"license_key": saved["license_key"], "device_id": device_id(state_dir)},
                          timeout=8)
        if r.ok and r.json().get("ok"):
            saved_path.unlink(missing_ok=True)
            return True, "Lizenz wurde serverseitig freigegeben."
        return False, r.json().get("message", "Freigabe abgelehnt.")
    except Exception:
        return False, "Freigabe benötigt eine funktionierende Internetverbindung."
