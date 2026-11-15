"""One-video orchestrator for the YouTube autopilot.

Usage: python run_one.py <job_index 0-5> [work_dir]
  - Picks today's topic by rotation: topics[(day_number*6 + index) % N]
    (no cross-job state, no races between the 6 parallel jobs).
  - Gemini writes the script (super hook + hook every ~60s).
  - Edge TTS (fallback gTTS) narrates scene by scene.
  - Pollinations fetches 2 images per scene (Pexels fallback if key set).
  - FFmpeg assembles the 4-5 min video with Ken Burns + SFX + music bed.
  - Pillow builds the thumbnail.
  - YouTube Data API uploads it (private + staggered publishAt).

Env required: GEMINI_API_KEY, YT_CLIENT_ID, YT_CLIENT_SECRET,
YT_REFRESH_TOKEN. Optional: PEXELS_API_KEY, TTS_VOICE, DRY_RUN=1 (build
the video but skip the upload — used for the first local test).
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from assemble import assemble
from images import fetch_scene_images
from script_gen import generate_script
from thumbnail import make_thumbnail
from tts import narrate_scenes
from upload import upload_full

TOPICS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "topics.json")


def pick_topic(index):
    with open(TOPICS_FILE) as f:
        topics = json.load(f)
    day_number = datetime.date.today().toordinal()
    return topics[(day_number * 6 + index) % len(topics)]


def publish_at_for(index):
    """Stagger releases through the day: 09:30 IST + 2h per video.
    Returns an RFC3339 UTC timestamp, or None to publish immediately."""
    base = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=4, minute=0, second=0, microsecond=0)  # 09:30 IST = 04:00 UTC
    target = base + datetime.timedelta(hours=2 * index)
    if target <= datetime.datetime.now(datetime.timezone.utc):
        target = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
    return target.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    work_dir = sys.argv[2] if len(sys.argv) > 2 else "work_%d" % index
    os.makedirs(work_dir, exist_ok=True)

    topic = pick_topic(index)
    print("Job %d — topic: %s" % (index, topic))

    gemini_key = os.environ["GEMINI_API_KEY"]
    script = generate_script(gemini_key, used_topics=[], topic=topic)
    if not script:
        sys.exit("Script generation failed.")
    with open(os.path.join(work_dir, "script.json"), "w") as f:
        json.dump(script, f, indent=2)

    scenes = script["scenes"]
    audio_dir = os.path.join(work_dir, "audio")
    timings = narrate_scenes(scenes, audio_dir)

    img_dir = os.path.join(work_dir, "images")
    images = fetch_scene_images(scenes, img_dir,
                                pexels_key=os.environ.get("PEXELS_API_KEY"))

    video_path = os.path.join(work_dir, "video.mp4")
    assemble(images, timings, scenes, work_dir, video_path)

    thumb_path = os.path.join(work_dir, "thumbnail.jpg")
    make_thumbnail(images[0], script["thumbnail_text"], thumb_path)

    description = script["description"] + (
        "\n\nWhat would YOU want us to explore next? Tell us in the comments!"
        "\n\n#WhatIf #Earth #Nature")
    result = {
        "topic": topic, "title": script["title"],
        "words": script["total_words"],
        "duration_s": sum(t["duration"] for t in timings),
        "video": video_path, "thumbnail": thumb_path,
    }
    if os.environ.get("DRY_RUN") == "1":
        print("DRY RUN — skipping upload.")
    else:
        video_id, url = upload_full(
            video_path, thumb_path, script["title"], description,
            script["tags"], publish_at=publish_at_for(index))
        result["video_id"] = video_id
        result["url"] = url
    with open(os.path.join(work_dir, "result.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
