"""Narration for the YouTube autopilot — free TTS, no key required.

Primary: Microsoft Edge TTS (natural neural voices, free, no API key).
  Works on GitHub Actions runners (direct internet). May fail behind strict
  egress proxies — the pipeline then falls back automatically.
Fallback: gTTS (Google Translate TTS, free, no key, plain HTTPS).
  Less natural, but always available as a safety net.
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
GTTS_LANG = os.environ.get("TTS_LANG", "en")


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


def synth_scene(text, voice, out_path, index):
    """Narrate one scene. Edge TTS first, gTTS fallback. Returns (ok, engine)."""
    try:
        if edge_tts_scene(text, voice, out_path):
            return True, "edge-tts"
        print("Scene %d: edge-tts produced nothing, trying gTTS..." % index)
    except Exception as e:
        print("Scene %d: edge-tts failed (%s), trying gTTS..." % (index, e))
    try:
        if gtts_scene(text, GTTS_LANG, out_path):
            return True, "gtts"
    except Exception as e:
        print("Scene %d: gTTS failed too: %s" % (index, e))
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
