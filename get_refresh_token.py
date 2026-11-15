"""One-time helper: get a YouTube OAuth refresh token.

Run this ONCE on a machine with a browser (the setup browser task runs it):
  1. Create OAuth client (Desktop app) in Google Cloud for the project with
     the YouTube Data API v3 enabled.
  2. Save the client JSON as client_secret.json next to this script.
  3. Run: python get_refresh_token.py
  4. Open the printed URL in a browser, sign in with the Google account
     that owns the YouTube channel, allow access, paste the code back.
  5. Copy the printed refresh token into the GitHub Secret YT_REFRESH_TOKEN
     (and YT_CLIENT_ID / YT_CLIENT_SECRET from client_secret.json).
IMPORTANT: set the OAuth consent screen to Production afterwards, or the
refresh token expires after 7 days (Testing mode).
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json", SCOPES)
    creds = flow.run_console()
    print("\n--- COPY THESE INTO GITHUB SECRETS ---")
    print("YT_CLIENT_ID=%s" % creds.client_id)
    print("YT_CLIENT_SECRET=%s" % creds.client_secret)
    print("YT_REFRESH_TOKEN=%s" % creds.refresh_token)
