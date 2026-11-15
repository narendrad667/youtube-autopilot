"""Burned-in captions for the YouTube autopilot.

The captions come from the script itself (the exact words that are
narrated), so the text is 100% accurate — unlike YouTube auto-captions.
Timing is ESTIMATED from word counts within each scene (steady TTS pace),
not word-level forced alignment, so a cue can be a fraction of a second
early or late. The .srt is also saved alongside the video so it can be
uploaded to YouTube Studio separately if ever needed.
Style: white DejaVu Sans with a black outline, bottom-centre.
"""
import re

MAX_CHARS_PER_LINE = 42
MAX_LINES_PER_CUE = 2
MIN_CUE_S = 1.2
MAX_CUE_S = 5.0


def _fmt(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _wrap_words(words, max_chars):
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _cues_for_scene(narration, start, duration):
    """Split one scene's narration into (start, end, text) cues."""
    words = narration.split()
    if not words or duration <= 0:
        return []
    wps = len(words) / duration  # words per second (steady TTS pace)
    chunks = []
    for sent in _split_sentences(narration):
        lines = _wrap_words(sent.split(), MAX_CHARS_PER_LINE)
        for i in range(0, len(lines), MAX_LINES_PER_CUE):
            chunks.append(lines[i:i + MAX_LINES_PER_CUE])
    timed, t = [], start
    for chunk in chunks:
        text = "\n".join(chunk)
        n = len(text.split())
        dur = max(MIN_CUE_S, min(MAX_CUE_S, n / wps)) if wps > 0 else 2.0
        end = min(t + dur, start + duration)
        if end - t < 0.5:
            end = min(t + 0.5, start + duration)
        timed.append((t, end, text))
        t = end
    if timed and timed[-1][1] < start + duration - 0.2:
        s, _, tx = timed[-1]
        timed[-1] = (s, start + duration, tx)
    return timed


def write_srt(scenes, timings, out_path):
    """Write an .srt from scenes + per-scene durations. Returns path."""
    cues, t = [], 0.0
    for scene, timing in zip(scenes, timings):
        cues += _cues_for_scene(scene["narration"], t, timing["duration"])
        t += timing["duration"]
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, _fmt(s), _fmt(e), text))
    print("Wrote %s (%d cues)" % (out_path, len(cues)))
    return out_path


if __name__ == "__main__":
    import json
    import sys
    scenes = json.load(open(sys.argv[1]))["scenes"]
    timings = json.load(open(sys.argv[2]))
    write_srt(scenes, timings, sys.argv[3])
