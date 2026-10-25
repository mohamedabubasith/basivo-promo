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
from promo_core.extract import contrast, palette, _rgb  # noqa: E402
from promo_core.paths import PromoError  # noqa: E402
from promo_core.storyboard import (StoryboardError, caption_cues, looks_secret, secret_names, srt,  # noqa: E402
                                   timeline, validate)
from promo_core.summary import describe  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def board(**over):
    sb = {"version": 1, "product": "Acme", "scenes": [
        {"type": "logo", "vo": "Meet Acme."},
        {"type": "headline", "text": "Ship *faster*", "vo": "Ship faster than ever before with Acme."},
        {"type": "cta", "text": "Try it", "button": "Start", "vo": "Try it today."}]}
    sb.update(over)
    return sb


class TempDir(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)
        self._home = mock.patch.dict(os.environ, {"BASIVO_PROMO_HOME": str(self.dir / "home")})
        self._home.start()

    def tearDown(self):
        self._home.stop()
        self._td.cleanup()


class StoryboardTests(TempDir):
    def test_minimal_board_gets_style_defaults(self):
        sb = validate(board(), self.dir)
        self.assertEqual(sb["style"], "midnight")
        self.assertEqual(sb["brand"]["bg"], "#0b0d12")
        self.assertEqual(sb["music"]["bpm"], 96)
        self.assertEqual(sb["formats"], ["16x9", "9x16", "1x1"])

    def test_storyboard_overrides_style(self):
        sb = validate(board(style="neon", brand={"accent": "#123456"}, music=None), self.dir)
        self.assertEqual(sb["brand"]["accent"], "#123456")
        self.assertEqual(sb["brand"]["bg"], "#07070c")  # still from the style
        self.assertIsNone(sb["music"])

    def test_every_problem_is_reported(self):
        bad = board(fps=29, formats=["4x3"])
        bad["scenes"].append({"type": "device", "media": "../outside.png", "colour": "red"})
        with self.assertRaises(StoryboardError) as cm:
            validate(bad, self.dir)
        text = "\n".join(cm.exception.errors)
        for needle in ("fps", "formats", "inside the storyboard folder", "unknown field 'colour'"):
            self.assertIn(needle, text)

    def test_unknown_style(self):
        with self.assertRaises(StoryboardError):
            validate(board(style="nope"), self.dir)

    def test_rejects_credentials_in_copy(self):
        for text in ("password=hunter22", "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz012345-_x", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"):
            self.assertTrue(looks_secret(text), text)
            with self.assertRaises(StoryboardError):
                validate(board(scenes=[{"type": "headline", "text": "x", "vo": text}]), self.dir)

    def test_marketing_copy_is_not_a_secret(self):
        for text in ("Single sign-on and auth flows", "Your password is never stored", "Pin your favourite token pairs",
                     "Write to hello@acme.com"):
            self.assertFalse(looks_secret(text), text)

    def test_capture_fill_needs_secret_reference(self):
        cap = {"url": "https://app.acme.com", "steps": [{"fill": ["#pw", "token=abcdef123456"]}]}
        with self.assertRaises(StoryboardError):
            validate(board(capture=cap), self.dir)
        cap["steps"] = [{"fill": ["#pw", "${secret:acme_pw}"]}, {"click": "#go", "shot": "home"}]
        sb = validate(board(capture=cap), self.dir)
        self.assertEqual(secret_names(sb), ["acme_pw"])

    def test_media_must_exist_unless_capturing(self):
        sc = [{"type": "device", "media": "captures/desktop/home.png"}]
        with self.assertRaises(StoryboardError):
            validate(board(scenes=sc), self.dir)
        validate(board(scenes=sc), self.dir, check_media=False)
        (self.dir / "captures/desktop").mkdir(parents=True)
        (self.dir / "captures/desktop/home.png").write_bytes(PNG)
        validate(board(scenes=sc), self.dir)

    def test_auto_click_point_from_captures(self):
        (self.dir / "captures").mkdir()
        (self.dir / "captures/a.png").write_bytes(PNG)
        (self.dir / "captures.json").write_text(json.dumps({"captures/a.png": {"point": [0.25, 0.75]}}))
        sb = validate(board(scenes=[{"type": "click", "media": "captures/a.png", "point": "auto"}]), self.dir)
        self.assertEqual(sb["scenes"][0]["point"], [0.25, 0.75])

    def test_project_style_and_style_logo(self):
        styles = self.dir / "promo-styles"
        styles.mkdir()
        (self.dir / "logo.png").write_bytes(PNG)
        (styles / "house.json").write_text(json.dumps({"name": "house", "brand": {"accent": "#abcdef", "logo": "../logo.png"}}))
        sub = self.dir / "promos" / "acme" / "x"
        sub.mkdir(parents=True)
        sb = validate(board(style="house"), sub)
        self.assertEqual(sb["brand"]["accent"], "#abcdef")
        self.assertEqual(Path(sb["brand"]["logo"]), (self.dir / "logo.png").resolve())

    def test_style_with_unknown_key_is_rejected(self):
        (self.dir / "promo-styles").mkdir()
        (self.dir / "promo-styles/bad.json").write_text(json.dumps({"scenes": []}))
        with self.assertRaises(StoryboardError):
            validate(board(style="bad"), self.dir)


class TimelineTests(TempDir):
    def test_voice_never_overlaps_and_cuts_hit_the_beat(self):
        sb = validate(board(), self.dir)
        tl = timeline(sb, [1.2, 3.4, 1.0])
        sc = tl["scenes"]
        for a, b in zip(sc, sc[1:]):
            self.assertGreaterEqual(b["vo_at"], a["vo_at"] + a["vo_len"] + 0.5)
            cut = b["start"] + b["tr"] / 2
            beats = cut / tl["beat"]
            self.assertAlmostEqual(beats, round(beats), places=2)
        self.assertAlmostEqual(tl["total"], sc[-1]["start"] + sc[-1]["dur"], places=3)

    def test_without_music_no_beat(self):
        sb = validate(board(music=None), self.dir)
        tl = timeline(sb, [None, None, None])
        self.assertIsNone(tl["beat"])
        self.assertEqual(tl["scenes"][0]["start"], 0)

    def test_captions_split_and_timed(self):
        sb = validate(board(), self.dir)
        tl = timeline(sb, [1.0, 4.0, 1.0])
        cues = caption_cues(sb, tl)
        self.assertTrue(all(len(c["text"]) <= 42 for c in cues))
        self.assertTrue(all(c["end"] > c["start"] for c in cues))
        text = srt(cues)
        self.assertIn("00:00:00,350 --> ", text)
        self.assertTrue(text.startswith("1\n"))


class HookTests(unittest.TestCase):
    def run_hook(self, name, payload, env=None):
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / name)], input=json.dumps(payload),
                           capture_output=True, text=True, env={**os.environ, **(env or {})})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_promo_commands_ask_with_description(self):
        for cmd in ('"${CLAUDE_PLUGIN_ROOT}/scripts/promo" render a/storyboard.json --draft',
                    "sh /x/scripts/promo setup", "uv run --script /p/scripts/promo.py doctor"):
            out = self.run_hook("gate.py", {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp"})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask", cmd)
            self.assertTrue(out["hookSpecificOutput"]["permissionDecisionReason"].strip())

    def test_unrelated_commands_untouched(self):
        for cmd in ("ls -la", "git status", "npm run promo", "env"):
            self.assertIsNone(self.run_hook("gate.py", {"tool_name": "Bash", "tool_input": {"command": cmd}}), cmd)

    def test_sessions_and_secrets_denied(self):
        cases = [("Read", {"file_path": "/Users/x/.basivo-promo/sessions/app.json"}),
                 ("Grep", {"pattern": "x", "path": "/Users/x/.basivo-promo/sessions"}),
                 ("Bash", {"command": "cat ~/.basivo-promo/sessions/a.json"}),
                 ("Bash", {"command": "security find-generic-password -s basivo-promo -a pw -w"}),
                 ("Bash", {"command": "echo $PROMO_SECRET_PW"})]
        for tool, ti in cases:
            out = self.run_hook("gate.py", {"tool_name": tool, "tool_input": ti})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", ti)

    def test_env_dump_denied_only_when_secrets_set(self):
        p = {"tool_name": "Bash", "tool_input": {"command": "env | sort"}}
        self.assertIsNone(self.run_hook("gate.py", p))
        out = self.run_hook("gate.py", p, env={"PROMO_SECRET_PW": "x"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_docs_mentioning_sessions_can_be_written(self):
        p = {"tool_name": "Write", "tool_input": {"file_path": "/r/README.md", "content": "stored in ~/.basivo-promo/sessions/"}}
        self.assertIsNone(self.run_hook("gate.py", p))

    def test_prompt_guard(self):
        blocked = ["here: sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz012345-_x", "password: hunter22",
                   "-----BEGIN OPENSSH PRIVATE KEY-----", "key AKIAIOSFODNN7EXAMPLE"]
        for p in blocked:
            out = self.run_hook("prompt_guard.py", {"prompt": p})
            self.assertEqual(out["decision"], "block", p)
        for p in ("make a promo for acme.com, mail hello@acme.com", "the password is never stored",
                  "commit 4f9c2a1b8e7d6c5b4a39281706f5e4d3c2b1a090"):
            self.assertIsNone(self.run_hook("prompt_guard.py", {"prompt": p}), p)
        self.assertIsNone(self.run_hook("prompt_guard.py", {"prompt": "password: hunter22"}, env={"BASIVO_PROMO_PROMPT_GUARD": "0"}))

    def test_capture_summary_names_secrets_not_values(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "storyboard.json").write_text(json.dumps(board(capture={
                "url": "https://app.acme.com", "steps": [{"fill": ["#pw", "${secret:acme_pw}"]}, {"shot": "home"}]})))
            title, lines = describe(["capture", "storyboard.json"], td)
        text = "\n".join(lines)
        self.assertIn("app.acme.com", text)
        self.assertIn("acme_pw", text)
        self.assertIn("home", text)


class SecretTests(unittest.TestCase):
    def test_env_first_and_nothing_printed(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"PROMO_SECRET_DEMO": "canary-7f3a"}), redirect_stdout(buf):
            s = sec.Secrets()
            self.assertEqual(s.get("demo"), "canary-7f3a")
            self.assertEqual(s.get("demo"), "canary-7f3a")
        self.assertNotIn("canary", buf.getvalue())

    def test_popup_used_when_missing_and_cancel_is_an_error(self):
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(sec, "_keychain", return_value=None), \
                mock.patch.object(sec, "_popup_mac", return_value=None), mock.patch.object(sec, "_popup_tk", return_value="typed"):
            os.environ.pop("PROMO_SECRET_X", None)
            self.assertEqual(sec.Secrets().get("x"), "typed")
        with mock.patch.object(sec, "_keychain", return_value=None), \
                mock.patch.object(sec, "_popup_mac", side_effect=PromoError("secret entry was cancelled")):
            os.environ.pop("PROMO_SECRET_Y", None)
            with mock.patch.object(sec.platform, "system", return_value="Darwin"), mock.patch.object(sec.shutil, "which", return_value="/usr/bin/osascript"):
                with self.assertRaises(PromoError):
                    sec.Secrets().get("y")

    def test_no_way_to_ask_gives_clear_error(self):
        with mock.patch.object(sec, "_keychain", return_value=None), mock.patch.object(sec, "_popup_mac", return_value=None), \
                mock.patch.object(sec, "_popup_tk", return_value=None):
            os.environ.pop("PROMO_SECRET_Z", None)
            with self.assertRaises(PromoError) as cm:
                sec.Secrets().get("z")
            self.assertIn("PROMO_SECRET_Z", str(cm.exception))


class PaletteTests(unittest.TestCase):
    def test_brand_colour_wins_over_status_tokens(self):
        facts = {"bg": "rgb(8, 9, 10)", "fg": "rgb(247, 248, 248)", "muted": "rgb(138, 143, 152)", "buttons": [],
                 "vars": {"--color-red": "#eb5757", "--color-green": "#27a644", "--focus-ring-color": "#5e69d1",
                          "--color-indigo": "#5e6ad2"}, "links": [], "used": []}
        p = palette(facts)
        self.assertEqual(p["theme"], "dark")
        self.assertIn(p["accent"], ("#5e69d1", "#5e6ad2"))

    def test_unreadable_text_is_fixed(self):
        p = palette({"bg": "#ffffff", "fg": "#eeeeee", "buttons": [{"bg": "rgb(83, 58, 253)", "area": 5000}]})
        self.assertGreaterEqual(contrast(_rgb(p["fg"]), _rgb(p["bg"])), 4.5)
        self.assertEqual(p["accent"], "#533afd")

    def test_browser_default_link_blue_ignored(self):
        p = palette({"bg": "#ffffff", "fg": "#111111", "links": ["rgb(0, 0, 238)"] * 20, "buttons": [], "used": []})
        self.assertNotEqual(p["accent"], "#0000ee")


if __name__ == "__main__":
    unittest.main()
