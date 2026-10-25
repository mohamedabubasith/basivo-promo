"""Shared locations and small helpers. Standard library only."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .mask_pii import mask

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = PLUGIN_ROOT / "templates"
VENDOR = PLUGIN_ROOT / "vendor"
HOME = Path(os.environ.get("BASIVO_PROMO_HOME") or Path.home() / ".basivo-promo")
MODELS = HOME / "models"
SESSIONS = HOME / "sessions"
AUDIT_LOG = HOME / "audit.log"
ERROR_LOG = HOME / "last-error.log"

KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_FILES = {
    "kokoro-v1.0.int8.onnx": ("6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb", 92361271),
    "voices-v1.0.bin": ("bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 28214398),
}


class PromoError(Exception):
    """An expected failure with a message that is safe to show (it is masked anyway)."""


def private_dir(path):
    """Create a directory only the current user can read."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def slug(text, limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s[:limit].strip("-")) or "promo"


def audit(action, target="", outcome="ok"):
    """Append one redacted line to ~/.basivo-promo/audit.log. Never raises."""
    try:
        private_dir(HOME)
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "action": action,
                           "target": mask(str(target)), "outcome": mask(str(outcome))})
        fd = os.open(AUDIT_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
