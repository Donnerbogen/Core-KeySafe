import json, secrets, string, time
from datetime import datetime, timezone
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QMessageBox, QInputDialog, QTableWidget, QTableWidgetItem,
    QFormLayout, QComboBox, QTextEdit, QSpinBox, QCheckBox)
from .crypto_vault import create_vault, open_vault, atomic_write
from .license_client import check_license, release_license, device_id
from .config import APP_NAME, AUTO_LOCK_MINUTES

class KeySafeWindow(QMainWindow):
    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        self.entries = []
        self.master = None
        self.last_activity = time.monotonic()
        self.setWindowTitle(APP_NAME)
        self.resize(1000, 680)
        self.setMinimumSize(760, 520)
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#08111d; color:#e8f4fb; font-size:14px; }
            QLabel#hero { color:#52dce8; font-size:24px; font-weight:700; }
            QPushButton { background:#10313d; color:#eafaff; border:1px solid #236b7a; padding:9px 14px; border-radius:8px; }
            QPushButton:hover { background:#164958; }
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QTableWidget { background:#0c1b2a; color:#f0f7ff; border:1px solid #244154; padding:7px; selection-background-color:#146477; }
            QHeaderView::section { background:#102a3a; color:#7de8f0; padding:6px; }
        """)
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root)
        hero = QLabel("CORE KeySafe"); hero.setObjectName("hero"); layout.addWidget(hero)
        self.status = QLabel("Lokaler Passwort-Safe · verschlüsselter Tresor")
        layout.addWidget(self.status)
        self.stack = QVBoxLayout(); layout.addLayout(self.stack)
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_idle); self.timer.start(15000)
        self.ensure_license()

    def clear_stack(self):
        while self.stack.count():
            item = self.stack.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

    def ensure_license(self):
        if __import__("os").getenv("KEYSAFE_DEV_MODE") == "1":
            self.show_vault_gate()
            return
        saved = self.paths["license"]
        key = ""
        if saved.exists():
            try: key = json.loads(saved.read_text(encoding="utf-8")).get("license_key", "")
            except Exception: pass
        if not key:
            key, ok = QInputDialog.getText(self, "Lizenz erforderlich", "CORE KeySafe benötigt einen gültigen Jahres-Lizenzschlüssel:")
            if not ok or not key.strip():
                self.clear_stack()
                label = QLabel("Ohne gültigen Lizenzschlüssel kann CORE KeySafe nicht verwendet werden.\nBesorge dir einen Lizenzschlüssel auf der CORE-Lizenzwebseite.")
                label.setWordWrap(True); self.stack.addWidget(label)
                btn = QPushButton("Lizenz-Webseite öffnen")
                btn.clicked.connect(self.open_license_site); self.stack.addWidget(btn)
                return
            key = key.strip()
        state, message, ticket, data = check_license(key, self.paths["state"])
        if state in ("valid", "offline"):
            self.status.setText("Lizenz: " + message)
            self.warn_expiry(data)
            self.show_vault_gate()
        else:
            self.clear_stack()
            label = QLabel("LIZENZPRÜFUNG NICHT ERFOLGREICH\n\n" + message + "\n\nOhne gültige Lizenz bleibt CORE KeySafe gesperrt.")
            label.setWordWrap(True); self.stack.addWidget(label)
            btn = QPushButton("Lizenzschlüssel erneut eingeben")
            btn.clicked.connect(self.ensure_license); self.stack.addWidget(btn)
            web = QPushButton("Lizenz-Webseite öffnen"); web.clicked.connect(self.open_license_site); self.stack.addWidget(web)

    def open_license_site(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from .config import LICENSE_API_URL
        if LICENSE_API_URL.startswith("https://") and "REPLACE-WITH" not in LICENSE_API_URL:
            QDesktopServices.openUrl(QUrl(LICENSE_API_URL))
        else:
            QMessageBox.information(self, "Noch nicht konfiguriert", "Die Lizenz-Webseite muss in core_keysafe/config.py eingetragen werden.")

    def warn_expiry(self, data):
        try:
            expires = int(data.get("expires_at"))
            days = (expires - int(time.time())) // 86400
            if days <= 30 and days > 14: msg = f"Deine Lizenz läuft in {days} Tagen ab."
            elif days <= 14 and days > 7: msg = f"ACHTUNG: Deine Lizenz läuft in {days} Tagen ab."
            elif days <= 7 and days > 0: msg = f"DRINGEND: Deine Lizenz läuft in {days} Tagen ab."
            elif days <= 0: msg = "Deine Lizenz ist abgelaufen."
            else: return
            QMessageBox.warning(self, "Lizenz läuft ab", msg + "\nBitte besorge rechtzeitig einen neuen Lizenzschlüssel.")
        except Exception: pass

    def show_vault_gate(self):
        self.clear_stack()
        row = QHBoxLayout()
        self.stack.addLayout(row)
        open_btn = QPushButton("Tresor öffnen / erstellen"); open_btn.clicked.connect(self.open_or_create); row.addWidget(open_btn)
        import_btn = QPushButton("Importordner öffnen"); import_btn.clicked.connect(self.open_import_folder); row.addWidget(import_btn)
        release_btn = QPushButton("Lizenz auswerfen"); release_btn.clicked.connect(self.release); row.addWidget(release_btn)
        self.scan_import()

    def scan_import(self):
        candidates = [p for p in self.paths["import"].glob("*.vault") if p.is_file()]
        if not candidates: return
        if self.paths["vault"].exists():
            answer = QMessageBox.question(self, "Neuer Tresor gefunden",
                f"Im Importordner liegt {candidates[0].name}. Soll der aktuell verwendete Tresor gewechselt werden?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes: return
        source = candidates[0]
        password, ok = QInputDialog.getText(self, "Import prüfen", "Master-Passwort des importierten Tresors:", QLineEdit.Password)
        if not ok: return
        try:
            open_vault(source.read_bytes(), password)
            dest = self.paths["vault"]
            if dest.exists():
                backup = dest.with_suffix(".vault.previous")
                if not backup.exists(): dest.replace(backup)
                else:
                    QMessageBox.warning(self, "Import abgebrochen", "Ein vorheriger Tresor existiert bereits. Sichere ihn zuerst manuell.")
                    return
            source.replace(dest)
            QMessageBox.information(self, "Import erfolgreich", "Der Tresor wurde sicher in den internen Speicher verschoben.")
        except Exception as e:
            QMessageBox.critical(self, "Import fehlgeschlagen", str(e))

    def open_import_folder(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths["import"])))

    def open_or_create(self):
        if not self.paths["vault"].exists():
            pw, ok = QInputDialog.getText(self, "Neuen Tresor erstellen", "Neues Master-Passwort:", QLineEdit.Password)
            if not ok: return
            if len(pw) < 12:
                QMessageBox.warning(self, "Zu schwach", "Bitte mindestens 12 Zeichen verwenden.")
                return
            confirm, ok = QInputDialog.getText(self, "Master-Passwort bestätigen", "Master-Passwort erneut eingeben:", QLineEdit.Password)
            if not ok or pw != confirm:
                QMessageBox.warning(self, "Fehler", "Die Passwörter stimmen nicht überein."); return
            atomic_write(self.paths["vault"], create_vault(pw, []))
        pw, ok = QInputDialog.getText(self, "Tresor entsperren", "Master-Passwort:", QLineEdit.Password)
        if not ok: return
        try:
            data = open_vault(self.paths["vault"].read_bytes(), pw)
            self.master, self.entries = pw, data["entries"]
            self.last_activity = time.monotonic()
            self.show_entries()
        except Exception as e:
            QMessageBox.critical(self, "Tresor konnte nicht geöffnet werden", str(e))

    def show_entries(self):
        self.clear_stack()
        toolbar = QHBoxLayout(); self.stack.addLayout(toolbar)
        add = QPushButton("＋ Eintrag"); add.clicked.connect(self.add_entry); toolbar.addWidget(add)
        gen = QPushButton("Passwort generieren"); gen.clicked.connect(self.generate_password); toolbar.addWidget(gen)
        save = QPushButton("Speichern"); save.clicked.connect(self.save_vault); toolbar.addWidget(save)
        lock = QPushButton("Sperren"); lock.clicked.connect(self.lock_vault); toolbar.addWidget(lock)
        search = QLineEdit(); search.setPlaceholderText("Suchen…"); toolbar.addWidget(search)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["Titel", "Benutzername", "Webseite", "Kategorie"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.stack.addWidget(self.table)
        search.textChanged.connect(lambda text: self.populate_table(text))
        self.table.cellDoubleClicked.connect(self.edit_entry)
        self.populate_table()
        self.status.setText(f"Entsperrt · {len(self.entries)} Einträge · nur lokal")

    def populate_table(self, query=""):
        self.table.setRowCount(0)
        q = query.casefold()
        for e in self.entries:
            if q and q not in json.dumps(e, ensure_ascii=False).casefold(): continue
            row = self.table.rowCount(); self.table.insertRow(row)
            for col, key in enumerate(("title", "username", "url", "category")):
                self.table.setItem(row, col, QTableWidgetItem(str(e.get(key, ""))))

    def add_entry(self):
        fields = self.entry_dialog()
        if fields:
            self.entries.append(fields); self.save_vault(); self.populate_table()

    def edit_entry(self, row, col):
        visible = []
        for e in self.entries:
            visible.append(e)
        title = self.table.item(row, 0).text() if self.table.item(row,0) else ""
        e = next((x for x in self.entries if x.get("title","") == title), None)
        if e is None: return
        fields = self.entry_dialog(e)
        if fields:
            e.update(fields); self.save_vault(); self.populate_table()

    def entry_dialog(self, existing=None):
        d = QWidget(); form = QFormLayout(d)
        widgets = {}
        for key, label in [("title","Titel"),("username","Benutzername"),("password","Passwort"),("url","Webseite"),("category","Kategorie"),("notes","Notizen"),("tags","Tags, Komma getrennt")]:
            w = QTextEdit() if key == "notes" else QLineEdit()
            if key == "notes": w.setFixedHeight(80)
            w.setText(str((existing or {}).get(key,"")))
            if key == "password": w.setEchoMode(QLineEdit.Password)
            form.addRow(label, w); widgets[key] = w
        buttons = QHBoxLayout()
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dialog = QDialog(self); dialog.setWindowTitle("Tresoreintrag"); dialog.setLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        form.addRow(box); box.accepted.connect(dialog.accept); box.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.Accepted: return None
        out = {}
        for key,w in widgets.items():
            out[key] = w.toPlainText() if isinstance(w, QTextEdit) else w.text()
        return out

    def generate_password(self):
        length, ok = QInputDialog.getInt(self, "Passwortgenerator", "Länge:", 24, 12, 128)
        if not ok: return
        chars = string.ascii_letters + string.digits + "!#$%&()*+,-./:;<=>?@[]^_{|}~"
        password = ''.join(secrets.choice(chars) for _ in range(length))
        QMessageBox.information(self, "Generiertes Passwort", password)

    def save_vault(self):
        if not self.master: return
        atomic_write(self.paths["vault"], create_vault(self.master, self.entries))
        self.last_activity = time.monotonic()
        self.status.setText(f"Gespeichert · {len(self.entries)} Einträge")

    def check_idle(self):
        if self.master and time.monotonic() - self.last_activity >= AUTO_LOCK_MINUTES * 60:
            self.lock_vault()

    def lock_vault(self):
        self.master = None
        self.entries = []
        self.show_vault_gate()
        self.status.setText("Tresor gesperrt")

    def release(self):
        if QMessageBox.question(self, "Lizenz auswerfen", "Lizenz online freigeben? Dieses Gerät verliert danach seine Aktivierung.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        ok, msg = release_license(self.paths["state"])
        if ok:
            QMessageBox.information(self, "Lizenz freigegeben", msg)
            self.ensure_license()
        else:
            QMessageBox.warning(self, "Freigabe fehlgeschlagen", msg)
