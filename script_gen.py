"""Script generation for the YouTube autopilot (What If — Earth & Nature).

Uses the Gemini free API (same free key family as the Blogger auto-news
system). No Muse tokens. Stdlib only — no extra pip packages needed.

Output contract (JSON):
{
  "topic": "What If ...?",
  "title": "YouTube title, under 70 chars",
  "description": "2-3 sentences + CTA",
  "tags": ["...", ... 8-12 tags],
  "thumbnail_text": "3-5 BOLD WORDS",
  "total_words": 712,
  "scenes": [
    {"narration": "...",            # ~45-55 words, ~18-22 seconds spoken
     "image_prompts": ["...", "...", "...", "..."],
     # 4 cinematic prompts, NO text in image — one per ~5 seconds
     "sfx": "low rumble"}           # short SFX cue for this scene
  ]
}

Retention structure (user's spec):
- Scene 1 = SUPER HOOK: a shocking question/fact in the first 10 seconds.
- Scenes ~4, ~7, ~10, ~13 open with a mini-hook line (surprising question
  or fact) so interest never drops — roughly one hook every 60 seconds.
- No labels like "HOOK:" anywhere in the text — write the content itself.
- ~13 scenes x ~50 words = ~650 words = ~4.5 minutes at ~150 wpm.
"""
import json
import time
import urllib.request
import urllib.error

DEFAULT_MODEL = "gemini-3.5-flash-lite"
GENERATE_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
                "{model}:generateContent?key={key}")

PROMPT_TEMPLATE = """Write a YouTube video script for the channel's "What If — Earth & Nature" series, in simple clear English for a general audience.

TOPIC: {topic}
LENGTH: at least 650 words of narration total (about 4.5 minutes spoken). Every scene below must be 50-60 words — never write a shorter scene, or the video will be too short.

RETENTION STRUCTURE (mandatory):
- Scene 1 is a SUPER HOOK: open with a shocking question or fact in the first 10 seconds that makes the viewer unable to click away.
- Scenes 4, 7, 10 and 13 must each OPEN with a mini-hook line — a surprising question or a jaw-dropping fact — so there is a hook roughly every 60 seconds.
- Do NOT write labels such as "HOOK:" in the script — write the hook lines themselves as normal sentences.
- Keep every fact plausible and science-based. Do not invent fake statistics, fake studies, or fake quotes. If you are unsure of a number, say it approximately ("roughly", "around").

SCENES: exactly 13 scenes. For each scene give:
- "narration": 45-55 words of spoken script.
- "image_prompts": exactly 4 prompts for cinematic photorealistic 16:9 images that illustrate the narration, one for roughly every 5 seconds of the scene, each showing a different moment or angle of the scene. No text, no words, no letters, no cartoon, no stick figures — realistic cinematic photography style.
- "sfx": one short sound-effect cue (e.g. "deep rumble", "rain falling", "heartbeat", "wind gust", "silence").

ALSO GIVE:
- "title": a curiosity-driven YouTube title under 70 characters.
- "description": 2-3 sentences summarising the video, ending with a question inviting comments.
- "tags": 8-12 short search tags.
- "thumbnail_text": 3-5 bold words for the thumbnail.

Return ONLY a JSON object, no markdown fences, no extra text. Keys in this order:
{{"topic": "...", "title": "...", "description": "...", "tags": [...], "thumbnail_text": "...", "total_words": 0, "scenes": [{{"narration": "...", "image_prompts": ["...", "...", "...", "..."], "sfx": "..."}}]}}

TOPIC RULE: the topic must be a fresh "What If" question about Earth or nature. Do NOT reuse any of these already-used topics: {used_topics}
"""

FALLBACK_TOPICS = [
    "What If the Moon Suddenly Disappeared?",
    "What If All the Oceans Turned to Fresh Water?",
    "What If the Earth Stopped Spinning for One Day?",
    "What If It Never Stopped Snowing?",
    "What If All the Deserts Turned Green Overnight?",
    "What If the Sun Never Rose Again?",
    "What If Every Volcano Erupted at Once?",
    "What If the Amazon Rainforest Vanished?",
    "What If Gravity Became Half as Strong?",
    "What If the North Pole Melted Completely?",
]


def _call_gemini(prompt, api_key, model):
    """One Gemini generateContent call. Returns raw text or None."""
    url = GENERATE_URL.format(model=model, key=api_key)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 6000},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("Gemini HTTP %s: %s" % (e.code, e.read().decode("utf-8")[:300]))
        return None
    except Exception as e:  # network errors etc.
        print("Gemini error: %s" % e)
        return None
    try:
        return "".join(p.get("text", "") for p in
                       data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        print("Gemini reply had no text: %s" % json.dumps(data)[:300])
        return None


def _parse_script(text):
    """Extract the JSON object from the model reply and validate it."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        print("No JSON object in Gemini reply: %s" % text[:300])
        return None
    try:
        script = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        print("JSON parse failed: %s | %s" % (e, text[:300]))
        return None
    scenes = script.get("scenes") or []
    if len(scenes) < 10 or not script.get("title"):
        print("Script failed validation: %d scenes" % len(scenes))
        return None
    words = sum(len((s.get("narration") or "").split()) for s in scenes)
    script["total_words"] = words
    return script


def generate_script(api_key, used_topics, model=DEFAULT_MODEL, topic=None):
    """Generate one full video script. Retries up to 3 times if too short
    or invalid; keeps the longest valid script and returns it if it is at
    least 500 words (a slightly shorter video beats no video).

    If topic is None, the model picks a fresh one (not in used_topics).
    Returns the script dict or None.
    """
    used = ", ".join(used_topics) if used_topics else "(none yet)"
    topic_line = topic or "Pick a fresh, surprising one yourself."
    prompt = PROMPT_TEMPLATE.format(topic=topic_line, used_topics=used)
    best = None
    for attempt in (1, 2, 3, 4):
        text = _call_gemini(prompt, api_key, model)
        script = _parse_script(text)
        if script is None:
            print("Attempt %d: invalid script, retrying..." % attempt)
            time.sleep(5)
            continue
        words = script["total_words"]
        print("Script: %s | %d words | %d scenes"
              % (script["title"], words, len(script["scenes"])))
        if best is None or words > best["total_words"]:
            best = script
        if words >= 600:
            return script
        print("Attempt %d: too short (%d words), retrying..." % (attempt, words))
        time.sleep(5)
    if best is not None and best["total_words"] >= 500:
        print("Using longest script (%d words) after 4 attempts."
              % best["total_words"])
        return best
    return None


def generate_fresh_topic(api_key, used_topics, model=DEFAULT_MODEL):
    """Ask Gemini for ONE fresh What If topic not in used_topics.
    Used after the 102-topic pool has cycled once (day 18+).
    Returns the topic string or None."""
    prompt = (
        "Give me ONE fresh, surprising 'What If' question about Earth or "
        "nature for a YouTube video. It must NOT be any of these already-used "
        "topics: " + ", ".join(used_topics) +
        ". Return ONLY the question itself, nothing else. It must start with "
        "'What If' and end with '?'."
    )
    for attempt in (1, 2):
        text = _call_gemini(prompt, api_key, model)
        if text:
            topic = text.strip().strip('"').strip().split("\n")[0].strip()
            if topic.lower().startswith("what if") and topic.endswith("?"):
                return topic
        print("Fresh-topic attempt %d failed, retrying..." % attempt)
        time.sleep(5)
    return None


if __name__ == "__main__":
    import os
    import sys
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        sys.exit("Set GEMINI_API_KEY first.")
    used = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    script = generate_script(key, used)
    if script:
        print(json.dumps(script, indent=2)[:2000])
    else:
        sys.exit("Script generation failed.")
