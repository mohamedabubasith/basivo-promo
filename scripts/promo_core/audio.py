"""Voiceover (Kokoro-82M or macOS say), music (@simpllyf/ditty) and the final mix."""
import base64
import hashlib
import math
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from . import ff
from .paths import KOKORO_FILES, MODELS, VENDOR, PromoError

VO_RATE = 24000
MIX_RATE = 48000


def _trim(samples, threshold=0.004, pad=0.04):
    """Cut leading/trailing silence so scene timing follows the actual speech."""
    idx = np.flatnonzero(np.abs(samples) > threshold)
    if idx.size == 0:
        return samples[:0]
    p = int(pad * VO_RATE)
    return samples[max(0, idx[0] - p): idx[-1] + p]


class Voice:
    def __init__(self, cfg):
        self.engine, self.voice, self.speed = cfg["engine"], cfg.get("voice") or "", float(cfg.get("speed", 1.0))
        self._kokoro = None

    def _load_kokoro(self):
        if self._kokoro is None:
            missing = [n for n in KOKORO_FILES if not (MODELS / n).is_file()]
            if missing:
                raise PromoError("the Kokoro voice model is not installed. Run: promo setup (downloads ~120 MB once)")
            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro(str(MODELS / "kokoro-v1.0.int8.onnx"), str(MODELS / "voices-v1.0.bin"))
            voices = self._kokoro.get_voices()
            if self.voice not in voices:
                sample = ", ".join(v for v in voices if v[:2] in ("af", "am", "bf", "bm"))
                raise PromoError(f"unknown Kokoro voice '{self.voice}'. English voices: {sample}")
        return self._kokoro

    def synth(self, text):
        if self.engine == "kokoro":
            k = self._load_kokoro()
            lang = "en-gb" if self.voice.startswith("b") else "en-us"
            samples, rate = k.create(text, voice=self.voice, speed=self.speed, lang=lang)
            samples = np.asarray(samples, dtype=np.float32)
            if rate != VO_RATE:
                raise PromoError(f"unexpected Kokoro sample rate {rate}")
            return samples
        if self.engine == "say":
            if platform.system() != "Darwin" or not shutil.which("say"):
                raise PromoError("voice engine 'say' needs macOS; use 'kokoro' or 'none'")
            with tempfile.TemporaryDirectory() as td:
                txt, aiff, wav = Path(td, "line.txt"), Path(td, "line.aiff"), Path(td, "line.wav")
                txt.write_text(text, encoding="utf-8")  # -f avoids passing copy as argv
                cmd = ["say", "-f", str(txt), "-o", str(aiff)]
                if self.voice:
                    cmd += ["-v", self.voice]
                if self.speed != 1.0:
                    cmd += ["-r", str(int(175 * self.speed))]
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    raise PromoError(f"say failed: {r.stderr.strip()[:200]}")
                ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(aiff), "-ac", "1", "-ar", str(VO_RATE), "-c:a", "pcm_f32le", str(wav)], "converting say output")
                samples, _ = sf.read(str(wav), dtype="float32")
                return samples
        raise PromoError(f"unknown voice engine {self.engine}")


def voiceover(sb, work):
    """Synthesize each scene's line (cached by content). Returns [(path or None, seconds or None)]."""
    cfg = sb["voice"]
    out = []
    if cfg["engine"] == "none":
        return [(None, None)] * len(sb["scenes"])
    voice = Voice(cfg)
    cache = work / "vo"
    cache.mkdir(parents=True, exist_ok=True)
    for sc in sb["scenes"]:
        text = (sc.get("vo") or "").strip()
        if not text:
            out.append((None, None))
            continue
        key = hashlib.sha256(f"{cfg['engine']}|{voice.voice}|{voice.speed}|{text}".encode()).hexdigest()[:20]
        path = cache / f"{key}.wav"
        if not path.is_file():
            samples = _trim(voice.synth(text))
            if samples.size == 0:
                raise PromoError(f"the voice engine produced silence for: {text[:60]}")
            sf.write(str(path), samples, VO_RATE, subtype="FLOAT")
        info = sf.info(str(path))
        out.append((path, info.frames / info.samplerate))
    return out


def vo_track(vo, tl, work):
    """Place every line at its scene's voice cue on one mono track."""
    if not any(p for p, _ in vo):
        return None
    track = np.zeros(int(math.ceil(tl["total"] * VO_RATE)) + VO_RATE, dtype=np.float32)
    for (path, _), sc in zip(vo, tl["scenes"]):
        if not path:
            continue
        samples, _ = sf.read(str(path), dtype="float32")
        at = int(round(sc["vo_at"] * VO_RATE))
        end = min(len(track), at + len(samples))
        track[at:end] += samples[: end - at]
    path = work / "vo_track.wav"
    sf.write(str(path), track, VO_RATE, subtype="FLOAT")
    return path


DITTY_JS = """async ({style, seed, seconds, bpm}) => {
  const { sampleRate, channels } = await Ditty.renderOffline({ style, seed, seconds, bpm });
  const wav = Ditty.encodeWav(channels, sampleRate);
  let s = "";
  for (let i = 0; i < wav.length; i += 0x8000) s += String.fromCharCode.apply(null, wav.subarray(i, i + 0x8000));
  return btoa(s);
}"""


def music(sb, total, work, browser):
    """Render the ditty track for this video (cached by style, seed and length)."""
    m = sb["music"]
    seconds = int(math.ceil(total + 1.5))
    path = work / f"music_{m['style']}_{m['seed']}_{m['bpm']}_{seconds}.wav"
    if path.is_file():
        return path
    page = browser.new_page()
    try:
        page.add_script_tag(path=str(VENDOR / "ditty.global.js"))
        data = page.evaluate(DITTY_JS, {"style": m["style"], "seed": m["seed"], "seconds": seconds, "bpm": m["bpm"]})
    finally:
        page.close()
    path.write_bytes(base64.b64decode(data))
    return path


def _whoosh(rng, seconds, direction):
    """Filtered noise swell that pans with the transition (direction 1 = right to left, 0 = centre)."""
    n = int(seconds * MIX_RATE)
    t = np.linspace(0, 1, n, dtype=np.float32)
    noise = rng.standard_normal(n).astype(np.float32)
    env = np.clip(np.sin(np.pi * t), 0, 1) ** 2.2
    # One-pole low-pass whose cutoff sweeps up then down: the "air" moving past.
    cutoff = 0.02 + 0.18 * np.sin(np.pi * t)
    out = np.empty(n, dtype=np.float32)
    acc = 0.0
    for i in range(n):  # ponytail: per-sample loop, ~20k samples per whoosh; vectorise if SFX count grows
        acc += cutoff[i] * (noise[i] - acc)
        out[i] = acc
    out *= env / (np.abs(out).max() + 1e-9)
    right = 0.5 - 0.45 * direction * (2 * t - 1)  # direction 1: sweeps right -> left with a push-left cut
    return np.stack([out * np.sqrt(1 - right), out * np.sqrt(right)], axis=1)


def _click(rng):
    n = int(0.06 * MIX_RATE)
    t = np.arange(n, dtype=np.float32) / MIX_RATE
    tick = np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 900)
    body = np.sin(2 * np.pi * 140 * t) * np.exp(-t * 70) * 0.6
    snap = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 2500) * 0.4
    mono = (tick + body + snap).astype(np.float32)
    mono /= np.abs(mono).max() + 1e-9
    return np.stack([mono, mono], axis=1)


def sfx_track(tl, work):
    """Synthesized UI sounds placed on the timeline: a whoosh on every moving cut, a click on every click."""
    rng = np.random.default_rng(7)
    track = np.zeros((int(math.ceil(tl["total"] * MIX_RATE)) + MIX_RATE, 2), dtype=np.float32)
    events = 0

    def place(clip, at, gain):
        nonlocal events
        i = max(0, int(at * MIX_RATE))
        j = min(len(track), i + len(clip))
        if j > i:
            track[i:j] += clip[: j - i] * gain
            events += 1

    for sc in tl["scenes"]:
        if sc["tr"] > 0:
            d = sc["tr"] * 1.4
            direction = 0 if sc["transition"] in ("zoom", "push-up") else 1
            place(_whoosh(rng, d, direction), sc["start"] + sc["tr"] / 2 - d / 2, 0.30)
        if sc.get("click_at") is not None:
            place(_click(rng), sc["click_at"], 0.55)
    if not events:
        return None
    path = work / "sfx.wav"
    sf.write(str(path), track, MIX_RATE, subtype="FLOAT")
    return path


def mix(vo_path, music_path, total, volume, work, sfx_path=None):
    """Duck music under the voice, then normalise the whole mix to -14 LUFS, -1.5 dBTP (two-pass)."""
    if not vo_path and not music_path:
        return None
    rough = work / "mix_rough.wav"
    fade_out = max(0.0, total - 2.5)
    music_chain = f"aresample={MIX_RATE},afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out:.3f}:d=2.5"
    if vo_path and music_path:
        # Music bed sits about 10 dB under the voice, ducks a further ~6 dB while someone speaks.
        bed = max(-40.0, min(-16.0, -26.0 + 20 * math.log10(volume / 0.5)))
        graph = (f"[0:a]aresample={MIX_RATE},loudnorm=I=-16:TP=-2:LRA=11,aresample={MIX_RATE},pan=stereo|c0=c0|c1=c0,asplit=2[v1][v2];"
                 f"[1:a]loudnorm=I={bed:.1f}:TP=-2:LRA=11,{music_chain}[m];"
                 "[m][v1]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[duck];"
                 "[duck][v2]amix=inputs=2:duration=longest:normalize=0[out]")
        inputs = ["-i", str(vo_path), "-i", str(music_path)]
    elif vo_path:
        graph = f"[0:a]aresample={MIX_RATE},pan=stereo|c0=c0|c1=c0[out]"
        inputs = ["-i", str(vo_path)]
    else:
        graph = f"[0:a]{music_chain}[out]"
        inputs = ["-i", str(music_path)]
    if sfx_path:
        # SFX ride on top at a fixed level relative to the bed; the final loudnorm keeps the balance.
        k = len(inputs) // 2
        inputs += ["-i", str(sfx_path)]
        graph = graph.replace("[out]", "[pre]", 1) + f";[{k}:a]aresample={MIX_RATE},volume=-14dB[fx];[pre][fx]amix=inputs=2:duration=first:normalize=0[out]"
    ff.run(["ffmpeg", "-hide_banner", "-y", *inputs, "-filter_complex", graph, "-map", "[out]", "-t", f"{total:.3f}",
            "-ar", str(MIX_RATE), "-ac", "2", "-c:a", "pcm_f32le", str(rough)], "mixing audio")
    m = ff.loudnorm_measure(rough)
    if not all(math.isfinite(float(m[k])) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")):
        raise PromoError("the audio mix came out silent; check the voice and music settings")
    final = work / "mix.wav"
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample={MIX_RATE}")
    ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(rough), "-af", ln, "-ar", str(MIX_RATE), "-ac", "2",
            "-c:a", "pcm_s24le", str(final)], "normalising loudness")
    return final
