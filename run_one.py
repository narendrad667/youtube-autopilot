"""One-video orchestrator for the YouTube autopilot.

Usage: python run_one.py <job_index 0-5> [work_dir]
  - Topic: today's trending pick from topics_today.json (written by the
    plan job from competitor RSS + trending news); falls back to the
    102-topic pool rotation, then to a Gemini fresh topic.
  - Gemini writes the script (super hook + hook every ~60s).
  - Edge TTS (fallback gTTS) narrates scene by scene.
  - Pollinations fetches 4 images per scene — one every ~5s
    (Openverse/Pexels fallback if a fetch fails).
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
from captions import write_srt
from images import fetch_scene_images
from script_gen import generate_script, generate_fresh_topic
from thumbnail import make_thumbnail
from trends import pick_topic, TOPICS_FILE, TODAY_FILE
from tts import narrate_scenes
from upload import upload_full


def publish_at_for(index):
    """Stagger releases through the day: 07:00 IST + 3h per video
    (07:00, 10:00, 13:00, 16:00, 19:00, 22:00 IST) so all 6 land on the
    same day. Returns an RFC3339 UTC timestamp, or None to publish
    immediately."""
    base = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=1, minute=30, second=0, microsecond=0)  # 07:00 IST = 01:30 UTC
    target = base + datetime.timedelta(hours=3 * index)
    if target <= datetime.datetime.now(datetime.timezone.utc):
        target = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
    return target.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    work_dir = sys.argv[2] if len(sys.argv) > 2 else "work_%d" % index
    os.makedirs(work_dir, exist_ok=True)

    gemini_key = os.environ["GEMINI_API_KEY"]
    topic = None
    if os.path.exists(TODAY_FILE):
        try:
            with open(TODAY_FILE) as f:
                today_topics = json.load(f)
            topic = today_topics[index]
            print("Job %d — trending topic: %s" % (index, topic))
        except Exception as e:
            print("topics_today.json unusable (%s), using pool." % e)
    if not topic:
        topic, cycle = pick_topic(index)
        if cycle >= 1:
            # The 102-topic pool has cycled: ask Gemini for a fresh topic
            # not in the pool. If that fails, reuse the pool topic (a repeat
            # beats a missing video).
            with open(TOPICS_FILE) as f:
                pool = json.load(f)
            fresh = generate_fresh_topic(gemini_key, pool)
            if fresh:
                print("Pool cycled — fresh topic from Gemini: %s" % fresh)
                topic = fresh
            else:
                print("Fresh-topic call failed — reusing pool topic: %s" % topic)
        print("Job %d — pool topic: %s" % (index, topic))

    script = generate_script(gemini_key, used_topics=[], topic=topic)
    if not script:
        sys.exit("Script generation failed.")
    with open(os.path.join(work_dir, "script.json"), "w") as f:
        json.dump(script, f, indent=2)

    scenes = script["scenes"]
    audio_dir = os.path.join(work_dir, "audio")
    timings = narrate_scenes(scenes, audio_dir)

    # Burned-in captions from the script itself (exact words, no API quota).
    srt_path = os.path.join(work_dir, "captions.srt")
    write_srt(scenes, timings, srt_path)

    img_dir = os.path.join(work_dir, "images")
    scene_images = fetch_scene_images(
        scenes, img_dir, pexels_key=os.environ.get("PEXELS_API_KEY"))

    video_path = os.path.join(work_dir, "video.mp4")
    assemble(scene_images, timings, scenes, work_dir, video_path,
             srt_path=srt_path)

    thumb_path = os.path.join(work_dir, "thumbnail.jpg")
    make_thumbnail(scene_images[0][0], script["thumbnail_text"], thumb_path)

    description = script["description"] + (
        "\n\nWhat would YOU want us to explore next? Tell us in the comments!"
        "\n\n#WhatIf #Earth #Nature")
    result = {
        "topic": topic, "title": script["title"],
        "words": script["total_words"],
        "duration_s": sum(t["duration"] for t in timings),
        "video": video_path, "thumbnail": thumb_path,
        "captions": srt_path,
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
