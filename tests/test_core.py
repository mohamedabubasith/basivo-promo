"""Unit tests for the standard-library parts of basivo-promo. Run: python3 -m unittest discover -s tests"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from promo_core import secrets as sec  # noqa: E402
from promo_core.brief import BriefError, looks_secret, secret_names, validate  # noqa: E402
from promo_core.design import _contrast, directions, to_profile  # noqa: E402
from promo_core.extract import _rgb, contrast, palette  # noqa: E402
from promo_core.paths import PromoError  # noqa: E402
from promo_core.screen import camera_keys, plan, remap, speed_segments  # noqa: E402
from promo_core.summary import describe, describe_hf  # noqa: E402


def brief(**over):
    b = {"version": 2, "product": "Acme", "formats": ["16x9", "9x16"]}
    b.update(over)
    return b


class TempDir(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)
        self._env = mock.patch.dict(os.environ, {"BASIVO_PROMO_HOME": str(self.dir / "home")})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._td.cleanup()


class BriefTests(TempDir):
    def test_defaults_from_taste_profile(self):
        b = validate(brief(), self.dir)
        self.assertEqual(b["style"], "midnight")
        self.assertIn("style", b["music"])
        self.assertIn("direction", b["taste"])

    def test_every_problem_is_reported(self):
        with self.assertRaises(BriefError) as cm:
            validate(brief(formats=["4x3"], length=2, colour="red"), self.dir)
        text = "\n".join(cm.exception.errors)
        for needle in ("formats", "length", "colour"):
            self.assertIn(needle, text)

    def test_credentials_rejected(self):
        for text in ("password=hunter22", "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz012345-_x", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"):
            self.assertTrue(looks_secret(text), text)
            with self.assertRaises(BriefError):
                validate(brief(brief=text), self.dir)

    def test_marketing_copy_is_not_a_secret(self):
        for text in ("Single sign-on and auth flows", "Your password is never stored", "Write to hello@acme.com"):
            self.assertFalse(looks_secret(text), text)

    def test_secret_references_listed_by_name(self):
        b = validate(brief(site={"url": "https://app.acme.com"},
                           flows=[{"name": "f", "steps": [{"type": ["#pw", "${secret:acme_pw}"]}, {"pause": 500}]}]), self.dir)
        self.assertEqual(secret_names(b), ["acme_pw"])


class ScreenPlanTests(unittest.TestCase):
    EVENTS = [{"t": 0.2, "type": "move", "x": 0.5, "y": 0.5}, {"t": 1.4, "type": "click", "x": 0.5, "y": 0.6},
              {"t": 2.5, "type": "click", "x": 0.5, "y": 0.7}, {"t": 2.6, "type": "nav"},
              {"t": 9.0, "type": "click", "x": 0.9, "y": 0.05}]

    def test_idle_stretch_is_sped_up(self):
        segs = speed_segments(self.EVENTS, 11.0, 3.0)
        self.assertTrue(any(sp == 3.0 for _, _, sp in segs))
        self.assertAlmostEqual(segs[-1][1], 11.0)
        f = remap(segs)
        self.assertLess(f(11.0), 11.0)
        self.assertAlmostEqual(f(0.5), 0.5)

    def test_camera_zooms_to_clicks(self):
        keys = camera_keys(self.EVENTS, 11.0, 1.9)
        self.assertEqual(keys[0]["s"], 1.0)
        self.assertEqual([k["t"] for k in keys], sorted(k["t"] for k in keys))
        self.assertTrue(any(k["s"] > 1 and abs(k["x"] - 0.9) < 1e-6 for k in keys))

    def test_plan_mobile_zoom(self):
        p = plan({"events": self.EVENTS, "duration": 11.0, "viewport": "mobile"})
        self.assertEqual(p["zoom"], 1.5)
        self.assertEqual(len(p["clicks"]), 3)


class DesignTests(unittest.TestCase):
    def test_three_readable_directions(self):
        _, dirs, _ = directions("meditation and sleep app")
        self.assertEqual(len(dirs), 3)
        for d in dirs:
            p = d["palette"]
            self.assertGreaterEqual(_contrast(p["fg"], p["bg"]), 7, d["style"])
            self.assertGreaterEqual(_contrast(p["accent"], p["bg"]), 3, d["style"])
        self.assertIn("brand", to_profile(dirs[0], "x"))

    def test_unknown_type(self):
        with self.assertRaises(PromoError):
            directions("x", product_type="No Such Type")


class PaletteTests(unittest.TestCase):
    def test_saturated_button_wins(self):
        p = palette({"bg": "#ffffff", "fg": "#eeeeee", "buttons": [{"bg": "rgb(83, 58, 253)", "area": 5000}]})
        self.assertEqual(p["accent"], "#533afd")
        self.assertGreaterEqual(contrast(_rgb(p["fg"]), _rgb(p["bg"])), 4.5)

    def test_monochrome_brand_keeps_black(self):
        p = palette({"bg": "#fdfcfc", "fg": "#000000", "buttons": [{"bg": "rgb(0, 0, 0)", "area": 4000}]})
        self.assertEqual(p["accent"], "#000000")


class HookTests(unittest.TestCase):
    def run_hook(self, name, payload, env=None):
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / name)], input=json.dumps(payload),
                           capture_output=True, text=True, env={**os.environ, **(env or {})})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def decision(self, cmd, env=None):
        out = self.run_hook("gate.py", {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp"}, env)
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def test_promo_commands_ask(self):
        self.assertEqual(self.decision('"${CLAUDE_PLUGIN_ROOT}/scripts/promo" render a/promo.json'), "ask")

    def test_hyperframes_policy(self):
        hf = '"${CLAUDE_PLUGIN_ROOT}/scripts/hf"'
        self.assertIsNone(self.decision(f"{hf} check --json"))
        self.assertEqual(self.decision(f"{hf} render --output x.mp4"), "ask")
        self.assertEqual(self.decision(f"{hf} publish"), "ask")
        self.assertIn("UPLOAD", describe_hf(["cloud", "render"])[1])
        self.assertEqual(self.decision("npx hyperframes render"), "deny")

    def test_unrelated_commands_untouched(self):
        for cmd in ("ls -la", "git status", "env"):
            self.assertIsNone(self.decision(cmd), cmd)

    def test_sessions_and_secrets_denied(self):
        for tool, ti in [("Read", {"file_path": "/Users/x/.basivo-promo/sessions/app.json"}),
                         ("Bash", {"command": "security find-generic-password -s basivo-promo -a pw -w"}),
                         ("Bash", {"command": "echo $PROMO_SECRET_PW"})]:
            out = self.run_hook("gate.py", {"tool_name": tool, "tool_input": ti})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", ti)
        self.assertEqual(self.decision("env | sort", env={"PROMO_SECRET_PW": "x"}), "deny")

    def test_prompt_guard(self):
        for p in ("here: sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz012345-_x", "-----BEGIN OPENSSH PRIVATE KEY-----"):
            self.assertEqual(self.run_hook("prompt_guard.py", {"prompt": p})["decision"], "block", p)
        self.assertIsNone(self.run_hook("prompt_guard.py", {"prompt": "make a promo for acme.com"}))

    def test_record_summary_names_secrets_not_values(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "promo.json").write_text(json.dumps(brief(site={"url": "https://app.acme.com"},
                                                               flows=[{"name": "deploy", "steps": [{"type": ["#pw", "${secret:acme_pw}"]}]}])))
            _, lines = describe(["record-web", "promo.json"], td)
        text = "\n".join(lines)
        self.assertIn("app.acme.com", text)
        self.assertIn("acme_pw", text)


class SecretTests(unittest.TestCase):
    def test_env_first_and_nothing_printed(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"PROMO_SECRET_DEMO": "canary-7f3a"}), redirect_stdout(buf):
            self.assertEqual(sec.Secrets().get("demo"), "canary-7f3a")
        self.assertNotIn("canary", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
