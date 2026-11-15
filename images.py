"""Scene images for the YouTube autopilot — free, no key required.

Primary: Openverse (api.openverse.org, free, no key) — real CC photos.
  Chosen 2026-11-15 after Pollinations started returning HTTP 402
  Payment Required from GitHub Actions runners (shared egress IPs are
  rate-limited there), which killed test run #7 at the image stage even
  though script + TTS had already succeeded. Openverse is a fast search
  API, so images fetch in seconds instead of ~45s of AI generation.
Fallback 1: Pollinations (image.pollinations.ai, free, no key, FLUX).
  One try only — it 402s/503s from runners, so no retry loop. Kept as a
  backup for prompts where Openverse finds nothing. Pollinations stamps a
  small "pollinations.ai" logo bottom-right even with nologo=true, so its
  images have the bottom 7% cropped off with Pillow (verified: logo gone).
Fallback 2: Pexels (free API, needs PEXELS_API_KEY) — real stock photos.

Never-fail rule: if every source fails for one image, the most recent
successfully downloaded image is reused for that slot instead of killing
the whole video — one bad image must never waste a 40-minute run.
"""
import hashlib
import json
import os
import shutil
import time
import urllib.request
import urllib.error

POLLINATIONS_URL = ("https://image.pollinations.ai/prompt/{prompt}"
                    "?width=1280&height=720&model=flux&seed={seed}&nologo=true")
OPENVERSE_URL = ("https://api.openverse.org/v1/images/?q={q}&page_size=5"
                 "&license_type=commercial&filter_dead=false")
USER_AGENT = "FreeAiTools-YT-Autopilot/1.0"
# Polite pacing between Openverse search calls (fast API, no generation).
OPENVERSE_PACE_S = 1
# Generic queries tried when no image has succeeded yet at all.
GENERIC_QUERIES = ["planet earth from space", "outer space stars",
                   "dramatic sky clouds"]


def _seed(prompt):
    return int(hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8], 16) % 100000


def _crop_watermark(path):
    """Crop the bottom 7% off an image (removes the Pollinations logo
    stamped at the bottom-right). No-op if Pillow cannot read the file."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        w, h = img.size
        img.crop((0, 0, w, int(h * 0.93))).save(path, "JPEG", quality=90)
    except Exception as e:
        print("Watermark crop skipped (%s)" % e)


def _valid_image(path, min_bytes=5000):
    """True if the file is a readable image of reasonable size."""
    if not os.path.exists(path) or os.path.getsize(path) < min_bytes:
        return False
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def _is_landscape(path):
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size[0] >= img.size[1]
    except Exception:
        return False


def fetch_pollinations(prompt, out_path, timeout=120):
    """Download one Pollinations image. One try, no retries. True on success."""
    url = POLLINATIONS_URL.format(
        prompt=urllib.parse.quote(prompt + ", cinematic photorealistic, "
                                  "16:9, no text, no watermark"),
        seed=_seed(prompt))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if resp.status != 200 or not ctype.startswith("image/"):
            print("Pollinations bad reply: %s %s" % (resp.status, ctype))
            return False
        if len(data) < 5000:
            print("Pollinations image too small (%d bytes)" % len(data))
            return False
        with open(out_path, "wb") as f:
            f.write(data)
        _crop_watermark(out_path)
        return True
    except Exception as e:
        print("Pollinations failed: %s" % e)
        return False


def fetch_openverse(query, out_path, timeout=60):
    """Download a CC photo from Openverse (no key). Prefers a landscape
    photo; falls back to the first usable result. True on success."""
    url = OPENVERSE_URL.format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results") or []
        first_good = None
        tried = 0
        for item in results:
            if tried >= 3:
                break
            img_url = item.get("url")
            if not img_url:
                continue
            tried += 1
            try:
                req2 = urllib.request.Request(
                    img_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                    blob = resp2.read()
                    ctype = resp2.headers.get("Content-Type", "")
                if resp2.status != 200 or not ctype.startswith("image/") \
                        or len(blob) <= 5000:
                    continue
                tmp = out_path + ".ov"
                with open(tmp, "wb") as f:
                    f.write(blob)
                if not _valid_image(tmp):
                    os.remove(tmp)
                    continue
                if first_good is None:
                    first_good = tmp
                if _is_landscape(tmp):
                    os.replace(tmp, out_path)
                    if first_good != tmp and os.path.exists(first_good):
                        os.remove(first_good)
                    return True
            except Exception:
                continue
        if first_good is not None:
            os.replace(first_good, out_path)
            return True
        return False
    except Exception as e:
        print("Openverse failed: %s" % e)
        return False


def fetch_pexels(query, out_path, api_key, timeout=60):
    """Download the first Pexels search result for a query. True on success."""
    url = ("https://api.pexels.com/v1/search?query="
           + urllib.parse.quote(query) + "&per_page=1&orientation=landscape"
           + "&size=large")
    req = urllib.request.Request(
        url, headers={"Authorization": api_key, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        photos = data.get("photos") or []
        if not photos:
            return False
        img_url = photos[0]["src"]["large2x"] or photos[0]["src"]["large"]
        req2 = urllib.request.Request(img_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req2, timeout=timeout) as resp2:
            blob = resp2.read()
        with open(out_path, "wb") as f:
            f.write(blob)
        return len(blob) > 5000
    except Exception as e:
        print("Pexels failed: %s" % e)
        return False


def _query_variants(prompt):
    """Short keyword queries for a photo search, from an AI image prompt."""
    words = [w.strip(".,;:!?()\"'") for w in prompt.split()]
    words = [w for w in words if w and w.lower() not in
             ("a", "an", "the", "of", "in", "on", "with", "and")]
    variants = []
    if len(words) >= 4:
        variants.append(" ".join(words[:4]))
    if len(words) >= 2:
        variants.append(" ".join(words[:2]))
    return variants


def fetch_image(prompt, out_path, pexels_key=None):
    """Fetch one scene image: Openverse first, Pollinations (1 try), then
    Pexels (if a key is set). Returns (ok, engine)."""
    for query in _query_variants(prompt):
        if fetch_openverse(query, out_path):
            return True, "openverse"
        time.sleep(OPENVERSE_PACE_S)
    if fetch_pollinations(prompt, out_path):
        return True, "pollinations"
    if pexels_key:
        for query in _query_variants(prompt):
            if fetch_pexels(query, out_path, pexels_key):
                return True, "pexels"
    return False, "none"


def fetch_scene_images(scenes, out_dir, pexels_key=None):
    """Fetch one image per image prompt (4 per scene = one every ~5s).
    Never fails the video on a single image: if all sources fail, the
    most recent downloaded image is reused for that slot.
    Returns a list of lists: scene_images[scene][image]."""
    os.makedirs(out_dir, exist_ok=True)
    all_images = []
    last_good = None
    for i, scene in enumerate(scenes):
        scene_paths = []
        for j, prompt in enumerate(scene["image_prompts"]):
            path = os.path.join(out_dir, "scene_%02d_img%d.jpg" % (i, j))
            ok, engine = fetch_image(prompt, path, pexels_key)
            if not ok:
                if last_good is None:
                    for gq in GENERIC_QUERIES:
                        if fetch_openverse(gq, path):
                            ok, engine = True, "openverse-generic"
                            break
                if not ok and last_good is not None:
                    shutil.copyfile(last_good, path)
                    ok, engine = True, "reuse"
                if not ok:
                    raise RuntimeError(
                        "Image failed: scene %d img %d (%s) — no source "
                        "returned any image" % (i, j, prompt[:60]))
            else:
                last_good = path
            print("Scene %02d img %d: %s" % (i, j, engine))
            scene_paths.append(path)
            time.sleep(OPENVERSE_PACE_S)
        all_images.append(scene_paths)
    return all_images


if __name__ == "__main__":
    ok, engine = fetch_image(
        "a massive volcano erupting at dusk, lava river, cinematic",
        "/tmp/img_smoke.jpg")
    print("ok=%s engine=%s" % (ok, engine))
