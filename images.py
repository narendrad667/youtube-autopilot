"""Scene images for the YouTube autopilot — free, no key required.

Primary: Pollinations (image.pollinations.ai, free, no key, FLUX model).
  ~1 image/45s on the anonymous tier; each video job fetches its own
  images, so 6 parallel jobs stay within the pace. Retries 4 times with
  backoff — the service 503s under load, so the fallbacks matter.
  Note: Pollinations returns 1024x576 for a 1280x720 request — still 16:9;
  the assembler scales/crops to 1280x720.
Fallback 1: Openverse (api.openverse.org, free, no key) — real CC photos.
Fallback 2: Pexels (free API, needs PEXELS_API_KEY) — real stock photos.
"""
import hashlib
import json
import os
import time
import urllib.request
import urllib.error

POLLINATIONS_URL = ("https://image.pollinations.ai/prompt/{prompt}"
                    "?width=1280&height=720&model=flux&seed={seed}&nologo=true")
OPENVERSE_URL = ("https://api.openverse.org/v1/images/?q={q}&page_size=3"
                 "&license_type=commercial&filter_dead=false")
USER_AGENT = "FreeAiTools-YT-Autopilot/1.0"
# Polite pacing between Pollinations requests (anonymous tier ~1/45s).
POLLINATIONS_PACE_S = 8


def _seed(prompt):
    return int(hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8], 16) % 100000


def fetch_pollinations(prompt, out_path, timeout=120):
    """Download one Pollinations image. Returns True on success."""
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
        return True
    except Exception as e:
        print("Pollinations failed: %s" % e)
        return False


def fetch_openverse(query, out_path, timeout=60):
    """Download a CC photo from Openverse (no key). True on success."""
    url = OPENVERSE_URL.format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results") or []
        for item in results:
            img_url = item.get("url")
            if not img_url:
                continue
            try:
                req2 = urllib.request.Request(
                    img_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                    blob = resp2.read()
                    ctype = resp2.headers.get("Content-Type", "")
                if resp2.status == 200 and ctype.startswith("image/") \
                        and len(blob) > 5000:
                    with open(out_path, "wb") as f:
                        f.write(blob)
                    return True
            except Exception:
                continue
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


def fetch_image(prompt, out_path, pexels_key=None, attempts=4):
    """Fetch one scene image: Pollinations (retries + backoff), then
    Openverse, then Pexels (if a key is set)."""
    backoff = [10, 20, 40]
    for attempt in range(1, attempts + 1):
        if fetch_pollinations(prompt, out_path):
            return True, "pollinations"
        print("Retry %d/%d for: %s" % (attempt, attempts, prompt[:60]))
        time.sleep(backoff[min(attempt - 1, len(backoff) - 1)])
    query = " ".join(prompt.split()[:4])
    if fetch_openverse(query, out_path):
        return True, "openverse"
    if pexels_key:
        if fetch_pexels(query, out_path, pexels_key):
            return True, "pexels"
    return False, "none"


def fetch_scene_images(scenes, out_dir, pexels_key=None):
    """Fetch 2 images per scene. Returns list of image paths in order."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, scene in enumerate(scenes):
        for j, prompt in enumerate(scene["image_prompts"][:2]):
            path = os.path.join(out_dir, "scene_%02d_img%d.jpg" % (i, j))
            ok, engine = fetch_image(prompt, path, pexels_key)
            if not ok:
                raise RuntimeError("Image failed: scene %d img %d (%s)"
                                   % (i, j, prompt[:60]))
            print("Scene %02d img %d: %s" % (i, j, engine))
            paths.append(path)
            time.sleep(POLLINATIONS_PACE_S)
    return paths


if __name__ == "__main__":
    ok, engine = fetch_image(
        "a massive volcano erupting at dusk, lava river, cinematic",
        "/tmp/img_smoke.jpg")
    print("ok=%s engine=%s" % (ok, engine))
