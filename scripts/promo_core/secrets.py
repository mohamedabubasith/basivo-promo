"""Resolve ${secret:name} values without the model ever seeing them. Standard library only.

Order: environment variable PROMO_SECRET_<NAME>, then the OS keychain (service
"basivo-promo", account <name>), then a native masked popup. Values live only in this
process's memory and are passed straight to the browser. Nothing here prints or logs a value.
"""
import os
import platform
import shutil
import subprocess

from .paths import PromoError

SERVICE = "basivo-promo"


def _keychain(name):
    try:
        if platform.system() == "Darwin" and shutil.which("security"):
            r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
                               capture_output=True, text=True, timeout=10)
        elif shutil.which("secret-tool"):
            r = subprocess.run(["secret-tool", "lookup", "service", SERVICE, "account", name],
                               capture_output=True, text=True, timeout=10)
        else:
            return None
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = r.stdout[:-1] if r.stdout.endswith("\n") else r.stdout
    return value if r.returncode == 0 and value else None


def _popup_mac(prompt):
    # The prompt is passed as an argument, never spliced into AppleScript source.
    script = ['on run argv',
              'display dialog (item 1 of argv) default answer "" with hidden answer with title "basivo-promo" '
              'buttons {"Cancel", "OK"} default button "OK" with icon caution',
              'return text returned of result', 'end run']
    cmd = ["osascript"]
    for line in script:
        cmd += ["-e", line]
    try:
        r = subprocess.run(cmd + [prompt], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        raise PromoError("secret entry was cancelled")
    return r.stdout[:-1] if r.stdout.endswith("\n") else r.stdout


def _popup_tk(prompt):
    try:
        import tkinter
        from tkinter import simpledialog
    except ImportError:
        return None
    try:
        root = tkinter.Tk()
    except tkinter.TclError:  # no display
        return None
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        value = simpledialog.askstring("basivo-promo", prompt, show="*", parent=root)
    finally:
        root.destroy()
    if value is None:
        raise PromoError("secret entry was cancelled")
    return value


class Secrets:
    """Lazily resolves and caches secrets for one run."""

    def __init__(self, purpose=""):
        self._cache = {}
        self.purpose = purpose

    def get(self, name):
        if name in self._cache:
            return self._cache[name]
        value = os.environ.get("PROMO_SECRET_" + name.upper()) or _keychain(name)
        if not value:
            prompt = (f"basivo-promo needs the secret \"{name}\"{' for ' + self.purpose if self.purpose else ''}.\n\n"
                      "It goes straight into the browser and is never shown to Claude, logged, or saved.")
            value = _popup_mac(prompt) if platform.system() == "Darwin" and shutil.which("osascript") else None
            if value is None:
                value = _popup_tk(prompt)
        if not value:
            raise PromoError(f"no value for secret '{name}'. Set PROMO_SECRET_{name.upper()} in your shell, "
                             f"add it to the keychain (service '{SERVICE}', account '{name}'), or run where a popup can open")
        self._cache[name] = value
        return value

    def values(self):
        return list(self._cache.values())
