# GitHub-Startpaket – CORE KeySafe ohne Datenbank

1. Neues GitHub-Repository `CORE-KeySafe` erstellen.
2. Inhalt dieses Ordners in das Repository hochladen (Ordnerinhalte, nicht die ZIP-Datei).
3. Vor dem Push `desktop/core_keysafe/config.py` bearbeiten: `LICENSE_API_URL` und der öffentliche Ed25519-Schlüssel müssen auf die eigene Render-Instanz zeigen.
4. Niemals `.env`, private Signaturschlüssel, echte Lizenzschlüssel, Tresordateien oder Zugangsdaten committen.
5. GitHub Actions prüft grundlegende Python-Syntax.

Der Lizenzdienst speichert Lizenzdaten in einer JSON-Datei auf einem persistenten Render-Datenträger. Es wird keine Datenbank verwendet.
