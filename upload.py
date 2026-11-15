"""YouTube upload for the autopilot — YouTube Data API v3, free quota.

Quota: videos.insert = 1600 units, thumbnails.set = 50 units.
6 videos/day = 9600 + 300 = 9900/10000 — no slack. A failed upload that
retries costs another 1600, so retries are limited to one.
Auth: OAuth2 refresh token from env (YT_CLIENT_ID, YT_CLIENT_SECRET,
YT_REFRESH_TOKEN). The OAuth app MUST be in Production in Google Cloud —
in Testing mode the refresh token expires after 7 days.
Scope used: https://www.googleapis.com/auth/youtube.upload (covers upload
and thumbnails.set).

Publish timing: videos are uploaded as private with a publishAt time
(staggered through the day). If the channel cannot schedule (unverified
account), the API rejects publishAt and we fall back to public immediately.
"""
import os
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
CATEGORY_EDUCATION = "27"  # What If explainers fit Education best


def get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=SCOPES)
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_video(service, video_path, title, description, tags,
                 publish_at=None, category_id=CATEGORY_EDUCATION):
    """Upload one video. Returns the YouTube video id."""
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "private" if publish_at else "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at
    media = MediaFileUpload(video_path, mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    try:
        req = service.videos().insert(part="snippet,status", body=body,
                                      media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        video_id = resp["id"]
        print("Uploaded: %s -> https://youtu.be/%s" % (title, video_id))
        return video_id
    except HttpError as e:
        # Scheduling needs a verified channel; fall back to public now.
        if publish_at and e.resp.status in (400, 403):
            print("publishAt rejected (%s) — retrying as public now."
                  % e.resp.status)
            body["status"].pop("publishAt", None)
            body["status"]["privacyStatus"] = "public"
            media = MediaFileUpload(video_path, mimetype="video/mp4",
                                    chunksize=8 * 1024 * 1024, resumable=True)
            req = service.videos().insert(part="snippet,status", body=body,
                                          media_body=media)
            resp = None
            while resp is None:
                _, resp = req.next_chunk()
            video_id = resp["id"]
            print("Uploaded (public): %s -> https://youtu.be/%s"
                  % (title, video_id))
            return video_id
        raise


def set_thumbnail(service, video_id, thumb_path):
    """Upload the thumbnail (50 quota units). Non-fatal if it fails."""
    try:
        media = MediaFileUpload(thumb_path, mimetype="image/jpeg",
                                resumable=False)
        service.thumbnails().set(videoId=video_id,
                                 media_body=media).execute()
        print("Thumbnail set for %s" % video_id)
        return True
    except HttpError as e:
        print("Thumbnail failed (non-fatal): %s" % e)
        return False


def upload_full(video_path, thumb_path, title, description, tags,
                publish_at=None):
    """Upload + thumbnail in one call. Returns (video_id, url)."""
    service = get_service()
    video_id = upload_video(service, video_path, title, description, tags,
                            publish_at=publish_at)
    if thumb_path and os.path.exists(thumb_path):
        set_thumbnail(service, video_id, thumb_path)
    return video_id, "https://youtu.be/" + video_id


if __name__ == "__main__":
    import sys
    vid, url = upload_full(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None,
                           sys.argv[3] if len(sys.argv) > 3 else "Test upload",
                           "Test description", ["test"])
    print(url)
