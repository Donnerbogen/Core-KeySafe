# Render deployment – GitHub-Dateispeicher, ohne Datenbank

1. Lege ein privates GitHub-Repository für die Lizenzdaten an (separat vom Quellcode empfohlen).
2. Erstelle einen Fine-grained GitHub Token mit `Contents: Read and write`, beschränkt auf dieses Repository.
3. Lade den CORE-KeySafe-Quellcode in ein GitHub-Repository und wähle bei Render **New + → Blueprint**.
4. Setze im Render-Dashboard `GITHUB_TOKEN`, `GITHUB_REPOSITORY` (`owner/repository`), `GITHUB_STORE_PATH` (z. B. `data/keysafe_store.json`) und `GITHUB_BRANCH`.
5. Setze außerdem `LICENSE_SIGNING_PRIVATE_KEY` als Secret und `APP_BASE_URL` auf die öffentliche HTTPS-URL.
6. Setze im Desktop-Client `LICENSE_API_URL` auf die Render-URL und den öffentlichen Ed25519-Schlüssel in `LICENSE_SIGNING_PUBLIC_KEY_B64`.
7. Prüfe `/health`; erwartet wird `ok: true` und `storage: github-file`.

## Sicherheit
- Das GitHub-Repository mit den Lizenzdaten muss **privat** sein.
- Der GitHub Token und `LICENSE_SIGNING_PRIVATE_KEY` dürfen nie in Quellcode, Desktop-App oder Logs gelangen.
- Ein Render-Persistent-Disk ist für die Lizenzdaten nicht mehr erforderlich.
- Nutze nur eine Render-Instanz/einen Worker. Die GitHub Contents API ist kein transaktionaler Datenbankersatz; parallele Schreibzugriffe können Konflikte erzeugen.
- Jeder Schreibvorgang erstellt einen Commit. Die Commit-Historie enthält frühere Versionen der Lizenzdatei.
