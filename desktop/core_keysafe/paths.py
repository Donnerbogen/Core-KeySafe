import os, sys, shutil
from pathlib import Path
from platformdirs import user_desktop_dir

APP_DIR_NAME = "CORE KeySafe"
ROOT_DIR_NAME = "Core Network"

def app_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / ROOT_DIR_NAME / APP_DIR_NAME

def ensure_layout():
    root = app_root()
    root.mkdir(parents=True, exist_ok=True)
    for name in ("Import", "vault", "state", "logs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    try:
        if os.name != "nt":
            root.chmod(0o700)
            for p in root.iterdir():
                if p.is_dir(): p.chmod(0o700)
    except OSError:
        pass
    return {
        "root": root,
        "import": root / "Import",
        "vault_dir": root / "vault",
        "vault": root / "vault" / "CORE-KeySafe.vault",
        "state": root / "state",
        "license": root / "state" / "license.json",
    }

def create_desktop_shortcut():
    # Best-effort shortcut. For packaged builds the target is the installed executable.
    try:
        desktop = Path(user_desktop_dir())
        desktop.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            import winshell
            from win32com.client import Dispatch
            target = Path(sys.executable)
            if getattr(sys, "frozen", False):
                target = Path(sys.executable)
                args = ""
            else:
                target = Path(sys.argv[0]).resolve()
                args = ""
            link = desktop / "CORE KeySafe.lnk"
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(str(link))
            shortcut.Targetpath = str(target)
            shortcut.Arguments = args
            shortcut.WorkingDirectory = str(target.parent)
            shortcut.Description = "CORE KeySafe"
            shortcut.save()
        else:
            target = Path(sys.executable) if getattr(sys, "frozen", False) else Path(sys.argv[0]).resolve()
            entry = desktop / "CORE-KeySafe.desktop"
            entry.write_text(
                "[Desktop Entry]\nType=Application\nName=CORE KeySafe\n"
                f"Exec={target}\nTerminal=false\nCategories=Utility;Security;\n",
                encoding="utf-8"
            )
            entry.chmod(0o700)
    except Exception:
        # Some minimal Linux desktops do not expose a Desktop directory.
        pass
