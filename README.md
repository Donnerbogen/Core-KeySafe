# CORE KeySafe

Lokaler Windows-/Linux-Passwortmanager mit verschlüsseltem Ein-Datei-Tresor und separatem Lizenzdienst. Der Lizenzdienst speichert Lizenzdatensätze und Audit-Metadaten in einer einzelnen JSON-Datei in einem privaten GitHub-Repository über die GitHub Contents API.

## Komponenten
- `desktop/`: PySide6 Desktop-App, AES-256-GCM, Argon2id, Importordner, Generator und automatische Sperre.
- `license_service/`: FastAPI-Lizenz-API und konto-freie Weboberfläche zur Erzeugung von Lizenzschlüsseln.
- `deploy/render.yaml`: Render Blueprint mit GitHub-Dateispeicher.
- `.github/workflows/`: Basis-CI.

## Wichtige Grenzen
- Tresordaten bleiben lokal verschlüsselt; der Lizenzdienst erhält weder Tresordaten noch Master-Passwort.
- Lizenzschlüssel werden nur gehasht gespeichert. Der vollständige Schlüssel wird nur bei der Erstellung einmal angezeigt.
- Das Lizenzsystem prüft online und stellt signierte Offline-Tickets für maximal 72 Stunden aus, niemals über das Lizenzende hinaus.
- Ein offline befindliches Gerät kann einen serverseitigen Lizenzwechsel erst beim nächsten Kontakt erkennen.
- Kein CORE Account und keine Datenbank sind erforderlich.
- **GitHub-Hinweis:** Lizenzdaten liegen in `GITHUB_STORE_PATH` in einem privaten GitHub-Repository. Der Render-Dienst benötigt einen Fine-grained GitHub Token mit `Contents: Read and write`. Jeder Schreibvorgang erzeugt einen Commit; das ist kein transaktionaler Datenbankersatz. Nutze nur eine Instanz/einen Worker und beachte die GitHub API-Limits.
- Das Projekt ist ein Entwicklungsstand und wurde nicht unabhängig sicherheitsgeprüft. Vor öffentlicher Nutzung sind zusätzliche Schutzmaßnahmen, Backups und Sicherheitstests erforderlich.

## Desktop lokal starten
Python 3.11+ wird empfohlen.
```bash
cd desktop
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
Beim ersten Start wird ein Lizenzschlüssel verlangt. `KEYSAFE_DEV_MODE=1` ist ausschließlich für lokale Entwicklung vorgesehen und darf niemals in einer ausgelieferten Version gesetzt sein.

## Lizenzdienst lokal starten
```bash
cd license_service
python -m venv .venv
# aktivieren
pip install -r requirements.txt
cp .env.example .env
# GitHub-Token, Repository, Branch und LICENSE_SIGNING_PRIVATE_KEY setzen
uvicorn app:app --host 127.0.0.1 --port 8000
```
Der Lizenzdienst liest und schreibt `GITHUB_STORE_PATH` im privaten GitHub-Repository. Die Datei wird beim ersten Schreibvorgang automatisch angelegt. Löscht oder beschädigt man die Datei oder verliert der Dienst den GitHub-Zugriff, kann die Lizenzprüfung nicht zuverlässig arbeiten.

## Signaturschlüssel erzeugen
Im `license_service`-Verzeichnis:
```bash
python generate_signing_key.py
```
Den privaten Schlüssel nur als Render Secret `LICENSE_SIGNING_PRIVATE_KEY` speichern. Den öffentlichen Schlüssel in `desktop/core_keysafe/config.py` übernehmen. Niemals den privaten Schlüssel in GitHub committen.

## Render bereitstellen
1. Repository-Inhalt zu GitHub pushen.
2. Render: **New + → Blueprint** und das Repository verbinden. `deploy/render.yaml` konfigurieren.
3. Setze `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_STORE_PATH`, `GITHUB_BRANCH`, `LICENSE_SIGNING_PRIVATE_KEY` und `APP_BASE_URL` als Render-Environment-Werte.
4. Ein Render-Persistent-Disk ist für die Lizenzdaten nicht erforderlich; die JSON-Datei liegt im privaten GitHub-Repository.
5. Setze `LICENSE_API_URL` in `desktop/core_keysafe/config.py` auf die öffentliche HTTPS-URL und trage dort den öffentlichen Signaturschlüssel ein.

## Lizenzregeln
- Laufzeit: 365 Tage.
- Erster erfolgreicher Check bindet den Schlüssel an eine Geräte-ID.
- `Lizenz auswerfen` löst die Bindung nur online.
- Offline-Ticket: Ed25519-signiert, maximal 72 Stunden und begrenzt durch das Ablaufdatum.
- Ablaufwarnungen: 30, 14 und 7 Tage; danach bei jedem Start.
