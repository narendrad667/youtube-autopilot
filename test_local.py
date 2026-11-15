"""Local validation of the YouTube autopilot (no Gemini key, no YouTube
upload): narrate test_script.json, fetch images, assemble, thumbnail.
Verifies durations, resolution, audio/video streams, and file sizes.
Run: .venv/bin/python test_local.py
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assemble import assemble
from captions import write_srt
from images import fetch_scene_images
from thumbnail import make_thumbnail
from tts import narrate_scenes

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_work")


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height:format=duration",
         "-of", "json", path], capture_output=True, text=True)
    return json.loads(out.stdout)


def main():
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "test_script.json")) as f:
        script = json.load(f)
    scenes = script["scenes"]
    print("Test script: %d scenes, %d words"
          % (len(scenes), script["total_words"]))

    timings = narrate_scenes(scenes, os.path.join(WORK, "audio"))
    srt_path = os.path.join(WORK, "captions.srt")
    write_srt(scenes, timings, srt_path)
    scene_images = fetch_scene_images(scenes, os.path.join(WORK, "images"))
    n_images = sum(len(s) for s in scene_images)
    print("Images: %d (%.1fs each on average)"
          % (n_images, sum(t["duration"] for t in timings) / n_images))

    video = os.path.join(WORK, "video.mp4")
    assemble(scene_images, timings, scenes, WORK, video, srt_path=srt_path)
    thumb = os.path.join(WORK, "thumbnail.jpg")
    make_thumbnail(scene_images[0][0], script["thumbnail_text"], thumb)

    info = probe(video)
    streams = {s["codec_type"]: s for s in info["streams"]}
    dur = float(info["format"]["duration"])
    narr = sum(t["duration"] for t in timings)
    print("VIDEO duration=%.1fs narration=%.1fs diff=%.2fs"
          % (dur, narr, abs(dur - narr)))
    print("VIDEO %sx%s %s | AUDIO %s"
          % (streams["video"].get("width"), streams["video"].get("height"),
             streams["video"].get("codec_name"),
             streams["audio"].get("codec_name")))
    print("SIZE video=%.1fMB thumb=%dKB"
          % (os.path.getsize(video) / 1e6, os.path.getsize(thumb) / 1e3))
    assert streams["video"]["width"] == 1280, "width wrong"
    assert streams["video"]["height"] == 720, "height wrong"
    assert "audio" in streams, "no audio stream"
    assert abs(dur - narr) < 1.0, "duration mismatch > 1s"
    print("LOCAL TEST PASSED")


if __name__ == "__main__":
    main()
