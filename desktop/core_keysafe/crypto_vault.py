import base64, json, os
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT = "COREKEYSAFE1"
def _derive(password: str, salt: bytes) -> bytes:
    if not password:
        raise ValueError("Master-Passwort darf nicht leer sein.")
    return hash_secret_raw(password.encode("utf-8"), salt, time_cost=3,
                           memory_cost=65536, parallelism=2, hash_len=32, type=Type.ID)

def create_vault(password: str, entries=None) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(12)
    header = {"format": FORMAT, "kdf": "argon2id", "salt": base64.b64encode(salt).decode(),
              "nonce": base64.b64encode(nonce).decode(), "version": 1}
    aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    payload = json.dumps({"entries": entries or [], "updated_at": __import__("datetime").datetime.now().isoformat()},
                         ensure_ascii=False, separators=(",", ":")).encode()
    ciphertext = AESGCM(_derive(password, salt)).encrypt(nonce, payload, aad)
    return json.dumps({"header": header, "ciphertext": base64.b64encode(ciphertext).decode()},
                      separators=(",", ":")).encode()

def open_vault(blob: bytes, password: str):
    outer = json.loads(blob.decode("utf-8"))
    header = outer["header"]
    if header.get("format") != FORMAT or header.get("version") != 1:
        raise ValueError("Unbekanntes oder nicht unterstütztes Tresorformat.")
    salt, nonce = base64.b64decode(header["salt"]), base64.b64decode(header["nonce"])
    aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    ciphertext = base64.b64decode(outer["ciphertext"])
    try:
        plain = AESGCM(_derive(password, salt)).decrypt(nonce, ciphertext, aad)
    except Exception as e:
        raise ValueError("Master-Passwort falsch oder Tresordatei manipuliert/beschädigt.") from e
    result = json.loads(plain.decode("utf-8"))
    if not isinstance(result.get("entries"), list):
        raise ValueError("Tresorinhalt ist ungültig.")
    return result

def atomic_write(path, data: bytes):
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".keysafe-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp): os.unlink(tmp)
        except OSError: pass
