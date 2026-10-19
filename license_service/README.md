# CORE KeySafe License Service (GitHub-Dateispeicher)

Dieser Dienst benötigt weder eine Datenbank noch einen CORE Account. Lizenzdatensätze, Gerätebindungen, Audit-Metadaten und das Erstellungs-Limit werden in einer einzelnen JSON-Datei in einem **privaten GitHub-Repository** gespeichert. Jede Änderung wird über die GitHub Contents API als Commit gespeichert.

## GitHub vorbereiten
1. Erstelle ein privates Repository für die Lizenzdaten. Es kann dasselbe Repository wie der Quellcode sein, aber ein separates privates Repository ist besser.
2. Erstelle einen Fine-grained Personal Access Token, beschränkt auf genau dieses private Repository und mit `Contents: Read and write`. Setze ein Ablaufdatum und rotiere den Token regelmäßig.
3. Lege die Datei `data/keysafe_store.json` im ausgewählten Branch nicht selbst an; der Dienst erstellt sie beim ersten Schreiben. Falls du sie vorab erstellst, muss sie gültiges JSON mit `{ "licenses": [], "audit": [], "issue_events": {} }` enthalten.
4. Veröffentliche den Dienst nicht mit einem öffentlichen Repository. Die Datei enthält gehashte Lizenzschlüssel, Geräte-IDs und Audit-Metadaten; außerdem speichert GitHub frühere Dateiversionen in der Commit-Historie.

## Lokal starten
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python generate_signing_key.py
# Trage alle Werte aus .env korrekt ein, danach:
uvicorn app:app --host 127.0.0.1 --port 8000
```

## Render konfigurieren
Setze folgende Environment Variables im Render-Dashboard:
- `GITHUB_TOKEN`: privater Fine-grained Token mit Zugriff auf genau das Speicher-Repository.
- `GITHUB_REPOSITORY`: `owner/repository`.
- `GITHUB_STORE_PATH`: z. B. `data/keysafe_store.json`.
- `GITHUB_BRANCH`: z. B. `main`.
- `LICENSE_SIGNING_PRIVATE_KEY`: privater Ed25519-Schlüssel, nur als Secret.
- `APP_BASE_URL`: öffentliche HTTPS-URL des Render-Dienstes.

Ein Render-Persistent-Disk ist für die Lizenzdatei nicht mehr erforderlich. `/health` sollte `storage: github-file` zurückgeben.

## Wichtige Grenzen
- **Nur eine Render-Instanz/ein Worker:** Der Lock ist lokal und schützt nicht mehrere Serverinstanzen. GitHub-Contents-Dateien sind kein transaktionaler Datenbankersatz. Bei parallelen Schreibzugriffen können Konflikte auftreten; der Dienst meldet dann einen Fehler, statt stillschweigend so zu tun, als wäre gespeichert worden.
- Jeder Schreibvorgang erstellt einen Git-Commit. GitHub API-Limits gelten.
- Git-Historie enthält frühere Versionen. Halte das Speicher-Repository privat und beschränke Token-Rechte.
- Der Token und `LICENSE_SIGNING_PRIVATE_KEY` dürfen niemals in GitHub-Quellcode, Desktop-App oder Logs stehen.
- Für hohe Last oder mehrere Instanzen ist ein transaktionaler Speicher geeigneter; GitHub-Dateien sind für kleine Projekte gedacht.
