"""OAuth 2.0 authentication for Google Chat API.

Handles the OAuth flow, token caching, and credential refresh.
Each user authenticates independently — tokens are stored locally.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Read-only scopes — we never write to Google Chat or the directory
SCOPES = [
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.memberships.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
]

TOKEN_DIR = Path.home() / ".config" / "google-chat-mcp"
TOKEN_FILE = TOKEN_DIR / "token.json"


def get_credentials_path() -> Path:
    """Return the path to the OAuth credentials JSON file.

    Priority:
    1. GOOGLE_CHAT_CREDENTIALS environment variable
    2. ~/.config/google-chat-mcp/credentials.json
    """
    env_path = os.environ.get("GOOGLE_CHAT_CREDENTIALS")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.exists():
            return p
        raise FileNotFoundError(
            f"GOOGLE_CHAT_CREDENTIALS points to a file that doesn't exist: {p}\n"
            "Please check the path and try again."
        )

    default = TOKEN_DIR / "credentials.json"
    if default.exists():
        return default

    raise FileNotFoundError(
        "No credentials file found. Please either:\n"
        "  1. Set the GOOGLE_CHAT_CREDENTIALS env var to your credentials.json path, or\n"
        "  2. Copy credentials.json to ~/.config/google-chat-mcp/credentials.json\n\n"
        "See README.md for instructions on creating a Google Cloud project and OAuth credentials."
    )


def get_credentials(credentials_file: Path | None = None) -> Credentials:
    """Load cached credentials or run the OAuth flow to get new ones.

    Args:
        credentials_file: Path to the OAuth client secrets JSON. If None,
                          auto-detected via get_credentials_path().

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
            creds_path = credentials_file or get_credentials_path()
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        # Cache the token for next time
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())

    return creds


def revoke_credentials() -> None:
    """Delete the cached token, forcing re-authentication on next use."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"Token deleted: {TOKEN_FILE}")
    else:
        print("No cached token found.")
