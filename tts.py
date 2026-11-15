"""Narration for the YouTube autopilot — free TTS, no key required.

Primary: Microsoft Edge TTS (natural neural voices, free, no API key).
  Works on GitHub Actions runners (direct internet). May fail behind strict
  egress proxies — the pipeline then falls back automatically.
Fallback 1: Kokoro TTS (free open-source neural voice, hexgrad/Kokoro-82M).
  Natural American male voice (am_adam), runs locally on CPU, no key.
  Needs espeak-ng installed and the ~310 MB model downloaded on first use.
Fallback 2: gTTS (Google Translate TTS, free, no key, plain HTTPS).
  Robotic, last resort only — the voice should never end up robotic.
Optional: Google Cloud TTS if GOOGLE_TTS_API_KEY is set (1M chars/month
  free tier) — not required.

One mp3 per scene, plus a timings JSON with each scene's duration (measured
with ffprobe) so the assembler can size every image hold to the narration.
"""
import asyncio
import json
import os
import subprocess

DEFAULT_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "am_adam")
GTTS_LANG = os.environ.get("TTS_LANG", "en")
# TTS_ENGINE=kokoro forces the Kokoro path (used for local testing).
FORCE_ENGINE = os.environ.get("TTS_ENGINE", "")

_KOKORO_PIPE = None
_KOKORO_FAILED = False


def probe_duration(path):
    """Audio duration in seconds via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


async def _edge_tts_one(text, voice, out_path):
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    await comm.save(out_path)


def edge_tts_scene(text, voice, out_path):
    asyncio.run(_edge_tts_one(text, voice, out_path))
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def gtts_scene(text, lang, out_path):
    from gtts import gTTS
    gTTS(text=text, lang=lang, slow=False).save(out_path)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def kokoro_scene(text, voice, out_path):
    """Narrate with Kokoro (natural, free, local CPU). The pipeline object
    is loaded once and reused for all scenes. Returns True on success."""
    global _KOKORO_PIPE, _KOKORO_FAILED
    if _KOKORO_FAILED:
        return False
    try:
        if _KOKORO_PIPE is None:
            from kokoro import KPipeline
            _KOKORO_PIPE = KPipeline(lang_code="a")
        import numpy as np
        import soundfile as sf
        chunks = []
        for _, _, audio in _KOKORO_PIPE(text, voice=voice):
            chunks.append(audio)
        if not chunks:
            return False
        tmp_wav = out_path + ".kokoro.wav"
        sf.write(tmp_wav, np.concatenate(chunks), 24000)
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", tmp_wav,
             "-codec:a", "libmp3lame", "-q:a", "3", out_path],
            capture_output=True, text=True)
        os.remove(tmp_wav)
        return r.returncode == 0 and os.path.exists(out_path) \
            and os.path.getsize(out_path) > 1000
    except Exception as e:
        print("Kokoro failed (%s)" % e)
        _KOKORO_FAILED = True
        return False


def synth_scene(text, voice, out_path, index):
    """Narrate one scene. Edge TTS first, Kokoro fallback, gTTS last
    resort. Returns (ok, engine)."""
    order = ["edge-tts", "kokoro", "gtts"]
    if FORCE_ENGINE == "kokoro":
        order = ["kokoro", "gtts"]
    elif FORCE_ENGINE == "gtts":
        order = ["gtts"]
    for engine in order:
        try:
            if engine == "edge-tts":
                ok = edge_tts_scene(text, voice, out_path)
            elif engine == "kokoro":
                ok = kokoro_scene(text, KOKORO_VOICE, out_path)
            else:
                ok = gtts_scene(text, GTTS_LANG, out_path)
            if ok:
                return True, engine
            print("Scene %d: %s produced nothing, trying next..."
                  % (index, engine))
        except Exception as e:
            print("Scene %d: %s failed (%s), trying next..."
                  % (index, engine, e))
    return False, "none"


def narrate_scenes(scenes, out_dir, voice=DEFAULT_VOICE):
    """Narrate every scene. Returns list of {audio, duration, engine}."""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for i, scene in enumerate(scenes):
        path = os.path.join(out_dir, "scene_%02d.mp3" % i)
        ok, engine = synth_scene(scene["narration"], voice, path, i)
        if not ok:
            raise RuntimeError("TTS failed for scene %d" % i)
        dur = probe_duration(path)
        if dur <= 0:
            raise RuntimeError("Zero-length audio for scene %d" % i)
        print("Scene %02d: %.1fs (%s)" % (i, dur, engine))
        results.append({"audio": path, "duration": dur, "engine": engine})
    timings_path = os.path.join(out_dir, "timings.json")
    with open(timings_path, "w") as f:
        json.dump(results, f, indent=2)
    total = sum(r["duration"] for r in results)
    print("Total narration: %.1fs (%.1f min)" % (total, total / 60.0))
    return results


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else (
        "What if the Moon suddenly disappeared? The tides would collapse, "
        "and the night would never be the same again.")
    ok, engine = synth_scene(text, DEFAULT_VOICE, "/tmp/tts_smoke.mp3", 0)
    print("ok=%s engine=%s duration=%.1fs"
          % (ok, engine, probe_duration("/tmp/tts_smoke.mp3")))
