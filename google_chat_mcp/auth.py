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

# Read-only scopes — we never write to Google Chat or the directory
SCOPES = [
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.memberships.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
]

TOKEN_DIR = Path.home() / ".config" / "google-chat-mcp"
TOKEN_FILE = TOKEN_DIR / "token.json"



def get_credentials(credentials_file: Path | None = None) -> Credentials:
    """Load cached credentials or run the OAuth flow to get new ones.

    Resolution order:
      1. credentials_file argument (explicit path)
      2. GOOGLE_CHAT_CREDENTIALS environment variable (path to file)
      3. ~/.config/google-chat-mcp/credentials.json (local file)
      4. Embedded credentials bundled in this package (default)

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

    # 2. Environment variable pointing to a file
    env_path = os.environ.get("GOOGLE_CHAT_CREDENTIALS")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.exists():
            return InstalledAppFlow.from_client_secrets_file(str(p), SCOPES)

    # 3. Local credentials file at default location
    default = TOKEN_DIR / "credentials.json"
    if default.exists():
        return InstalledAppFlow.from_client_secrets_file(str(default), SCOPES)

    # 4. No credentials found
    raise FileNotFoundError(
        "No credentials file found. Please either:\n"
        "  1. Place credentials.json in the project folder and run:\n"
        "       google-chat-mcp auth --credentials ./credentials.json\n"
        "  2. Set the GOOGLE_CHAT_CREDENTIALS env var to your credentials.json path\n"
        "  3. Copy credentials.json to ~/.config/google-chat-mcp/credentials.json\n\n"
        "Get credentials.json from your team's shared credential store (Slack, 1Password, etc.)."
    )


def revoke_credentials() -> None:
    """Delete the cached token, forcing re-authentication on next use."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"Token deleted: {TOKEN_FILE}")
    else:
        print("No cached token found.")
