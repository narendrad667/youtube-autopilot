# YouTube Autopilot — FreeAiTools-style permanent system

Goal (Narendra, 2026-11-15): 6 videos/day, each 4-5 min, What If style like his
earlier videos (rain / insects), fully free, zero Muse tokens after one-time
setup, runs forever on its own like the Blogger auto-news system.

## Format (defaults — user can change)
- Style: What If — Earth & Nature (his sub-niche 3.1), same as before
- Language: English audio first (his earlier workflow), 16:9 landscape
- Channel: The Reality Shift
- Length: 4-5 min (~650-750 words of narration at ~150 wpm)
- Retention structure (user's spec): SUPER HOOK in first 10 seconds, then a
  mini-hook every ~60 seconds so interest never drops
- Motion: Ken Burns zoom/pan (keyframes) on every image, crossfades
- Sound: narration + background music + SFX per scene (synthesized / CC0,
  never paid Epidemic/Artlist tracks)
- No text inside scene images (his rule); bold text only on the thumbnail

## Pipeline (one video = one GitHub Actions job, 6 parallel jobs/day)
1. `script_gen.py` — Gemini free API (gemini-3.5-flash-lite) writes: topic,
   script with hook structure, scene-by-scene image prompts + SFX cues,
   title, description, tags, thumbnail text. De-dup via used-topics file.
2. `tts.py` — Edge TTS (Microsoft, free, no key) narrates scene by scene.
3. `images.py` — Pollinations (free, no key) AI images per scene, 4 retries
   with backoff (the service 503s under load — seen in local test 2026-11-15),
   then Openverse (free, no key) real photos, then Pexels (free API key)
   as the last fallback. 8s pacing between Pollinations requests.
4. `assemble.py` — FFmpeg: zoompan keyframes + crossfade + narration +
   music + SFX, 1280x720 30fps, H.264.
5. `thumbnail.py` — Pillow 1280x720 bold-text thumbnail.
6. `upload.py` — YouTube Data API v3 resumable upload + thumbnail +
   description/tags; publishAt staggered through the day.

## Runner
- GitHub Actions, scheduled daily. Repo must be PUBLIC (code only, no
  secrets) so Actions minutes are unlimited; a private repo caps at
  2000 min/month, too tight for 6 x 4-5 min videos/day.
- Secrets (GitHub Secrets, never in code): GEMINI_API_KEY, YT_CLIENT_ID,
  YT_CLIENT_SECRET, YT_REFRESH_TOKEN, PEXELS_API_KEY (optional fallback).

## Free-tier budget (honest limits)
- YouTube Data API: 10,000 units/day. 6 uploads x 1600 = 9600. Thumbnails
  6 x 50 = 300. Total ~9900 — NO slack. If one upload fails and retries,
  that day only 5 go up. 6/day is the hard max on the free quota.
- Gemini free API: ~6 script calls/day, far inside the Flash-Lite free tier.
- Edge TTS: free, no quota. Pollinations: free, ~1 image/45s anonymous.
- GitHub Actions: public repo = unlimited minutes; each video job ~40-60 min.
- OAuth: the Google Cloud OAuth app MUST be set to Production, otherwise
  the refresh token expires after 7 days (testing mode).

## Local validation (2026-11-15, this VM)
- Test video rendered end-to-end: 48.5s, 1280x720, h264+aac, 3.3 MB,
  video duration matches narration to 0.01s, audio mean -21.7 dB / max
  -5.0 dB (healthy, not silent, not clipping). Frames checked visually:
  cinematic scenes match the script; thumbnail "MOON GONE?" clean.
- Edge TTS FAILS from this VM (egress proxy blocks speech.platform.bing.com
  with SSL wrong-version) — gTTS fallback worked and is the safety net.
  Edge TTS remains primary for GitHub Actions (direct internet).
- Pollinations 503s under load — retries + Openverse fallback validated.
- Known cosmetic issue: Pollinations images carry a small
  "pollinations.ai" watermark bottom-right despite nologo=true.
- NOT yet validated: Gemini script generation (no key on this VM),
  YouTube upload (no OAuth yet), GitHub Actions run.
- Muse video generation (blocked for this account: 403 video_not_available).
- AI moving video (Runway/Pika/Luma free tiers give only 5-10s clips and no
  free API) — that stays a separate, mostly manual 1 Short/day at best.
- The Facebook account attempt (2026-11-15, 'John Wick') is dropped per user.
