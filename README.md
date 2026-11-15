# YouTube Autopilot — 6 What If videos/day, fully free

Permanent autopilot for the channel **The Reality Shift** (What If — Earth &
Nature). Once set up, it runs every day on GitHub's free servers and posts 6
videos (4-5 min each) to YouTube — no manual work, no Muse tokens.

## How it works
1. **Topics (plan job, once a day)** — reads competitor YouTube RSS feeds
   (What If, Kurzgesagt, RealLifeLore) + trending science news, and Gemini
   picks 6 fresh topics for today. Falls back to the 102-topic pool.
2. **Script** — Gemini free API writes a ~700-word script with a super hook
   in the first 10 seconds and a mini-hook every ~60 seconds.
3. **Voice** — Edge TTS (free, no key) narrates scene by scene; gTTS is the
   automatic fallback.
4. **Images** — Pollinations (free, no key) generates 4 cinematic images per
   scene (one every ~5 seconds); Openverse / Pexels are the fallbacks.
5. **Video** — FFmpeg: slow Ken Burns zoom/pan on every image, crossfades,
   synthesised music bed + SFX per scene, 1280x720 30fps.
6. **Thumbnail** — Pillow, bold text.
7. **Upload** — YouTube Data API v3, staggered through the day.

## Setup (one time)
- GitHub repo (public, so Actions minutes are unlimited) + Secrets:
  `GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`
  (optional: `PEXELS_API_KEY`).
- Google Cloud: enable YouTube Data API v3, create an OAuth Desktop client,
  run `get_refresh_token.py` once, and set the OAuth consent screen to
  **Production** (otherwise the refresh token expires after 7 days).
- Daily schedule: 04:00 UTC (09:30 IST). Manual test: Actions tab →
  "Run workflow" with an index 0-5.

## Free-tier limits (honest)
- YouTube: 6 uploads/day = 9600/10000 quota units. No slack — if one upload
  fails and retries, that day only 5 go up.
- See `PLAN.md` for the full design and limits.
