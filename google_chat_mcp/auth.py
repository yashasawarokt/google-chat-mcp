"""OAuth 2.0 authentication for Google Chat API.

Handles the OAuth flow, token caching, and credential refresh.
Each user authenticates independently — tokens are stored locally.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.messages.create",
    "https://www.googleapis.com/auth/chat.messages",
    "https://www.googleapis.com/auth/chat.memberships.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
]

TOKEN_DIR = Path.home() / ".config" / "google-chat-mcp"
TOKEN_FILE = TOKEN_DIR / "token.json"



def get_credentials(credentials_file: Path | None = None) -> Credentials:
    """Load cached credentials or run the OAuth flow to get new ones.

    Resolution order:
      1. credentials_file argument (explicit path)
      2. GCHAT_CLIENT_ID + GCHAT_CLIENT_SECRET environment variables (preferred)
      3. GOOGLE_CHAT_CREDENTIALS environment variable (path to credentials file)
      4. ~/.config/google-chat-mcp/credentials.json (local file)

    Args:
        credentials_file: Optional explicit path to an OAuth client secrets JSON.

    Returns:
        Valid Google OAuth2 Credentials object.
    """
    creds: Credentials | None = None

    # Load cached token if it exists
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh if expired, or run OAuth flow if no valid token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = _build_flow(credentials_file)
            creds = flow.run_local_server(port=0, open_browser=True)

        # Cache the token for next time
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())

    return creds


def _build_flow(credentials_file: Path | None) -> InstalledAppFlow:
    """Return an InstalledAppFlow using the best available credentials source."""
    # 1. Explicit file path argument
    if credentials_file:
        return InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)

    # 2. Direct env vars — preferred for sharing (no credentials file needed)
    client_id = os.environ.get("GCHAT_CLIENT_ID")
    client_secret = os.environ.get("GCHAT_CLIENT_SECRET")
    if client_id and client_secret:
        config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            }
        }
        return InstalledAppFlow.from_client_config(config, SCOPES)

    # 3. Environment variable pointing to a credentials file
    env_path = os.environ.get("GOOGLE_CHAT_CREDENTIALS")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.exists():
            return InstalledAppFlow.from_client_secrets_file(str(p), SCOPES)

    # 4. Local credentials file at default location
    default = TOKEN_DIR / "credentials.json"
    if default.exists():
        return InstalledAppFlow.from_client_secrets_file(str(default), SCOPES)

    # 5. No credentials found
    raise FileNotFoundError(
        "No credentials found. Set the following environment variables and run `google-chat-mcp auth`:\n\n"
        "  export GCHAT_CLIENT_ID='your-client-id'\n"
        "  export GCHAT_CLIENT_SECRET='your-client-secret'\n\n"
        "Get these values from your team's shared 1Password note or ask a teammate.\n\n"
        "Alternatively, place a credentials.json file at:\n"
        "  ~/.config/google-chat-mcp/credentials.json"
    )


def revoke_credentials() -> None:
    """Delete the cached token, forcing re-authentication on next use."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"Token deleted: {TOKEN_FILE}")
    else:
        print("No cached token found.")
