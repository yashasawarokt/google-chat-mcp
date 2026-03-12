"""CLI entry point for google-chat-mcp.

Usage:
    google-chat-mcp setup    # One-time setup: saves creds, configures Cursor, authenticates
    google-chat-mcp auth     # Re-authenticate with Google (opens browser)
    google-chat-mcp serve    # Start MCP server (stdio, for Cursor/Claude Code)
    google-chat-mcp logout   # Revoke cached token
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import click

_CONFIG_DIR = Path.home() / ".config" / "google-chat-mcp"
_ENV_FILE = _CONFIG_DIR / "env.json"


def _save_env(client_id: str, client_secret: str) -> None:
    """Persist OAuth client credentials to a local config file."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _ENV_FILE.write_text(json.dumps({
        "GCHAT_CLIENT_ID": client_id,
        "GCHAT_CLIENT_SECRET": client_secret,
    }, indent=2) + "\n")


def _load_env() -> dict[str, str]:
    """Load saved OAuth client credentials, if any."""
    if _ENV_FILE.exists():
        return json.loads(_ENV_FILE.read_text())
    return {}


def _inject_saved_env() -> None:
    """Inject saved credentials into the environment if not already set."""
    saved = _load_env()
    for key in ("GCHAT_CLIENT_ID", "GCHAT_CLIENT_SECRET"):
        if key not in os.environ and key in saved:
            os.environ[key] = saved[key]


@click.group()
def main():
    """Google Chat MCP server — connect Claude to your Google Chat workspace."""
    pass


@main.command()
@click.option("--client-id", prompt="GCHAT_CLIENT_ID", help="Google OAuth Client ID", envvar="GCHAT_CLIENT_ID")
@click.option("--client-secret", prompt="GCHAT_CLIENT_SECRET", help="Google OAuth Client Secret", envvar="GCHAT_CLIENT_SECRET")
def setup(client_id, client_secret):
    """One-time setup: saves credentials, configures Cursor MCP, and authenticates.

    \b
    Interactive:
        google-chat-mcp setup

    One-liner (copy-paste from 1Password):
        google-chat-mcp setup --client-id YOUR_ID --client-secret YOUR_SECRET
    """
    from .auth import get_credentials, TOKEN_FILE

    # 1. Save credentials locally
    _save_env(client_id, client_secret)
    click.echo(f"\n✅ Credentials saved to {_ENV_FILE}")

    # 2. Inject into current process so auth can use them
    os.environ["GCHAT_CLIENT_ID"] = client_id
    os.environ["GCHAT_CLIENT_SECRET"] = client_secret

    # 3. Configure Cursor MCP
    binary = shutil.which("google-chat-mcp") or "google-chat-mcp"
    mcp_entry = {
        "command": binary,
        "args": ["serve"],
        "env": {
            "GCHAT_CLIENT_ID": client_id,
            "GCHAT_CLIENT_SECRET": client_secret,
        },
    }

    cursor_mcp = Path.home() / ".cursor" / "mcp.json"
    cursor_mcp.parent.mkdir(parents=True, exist_ok=True)

    if cursor_mcp.exists():
        config = json.loads(cursor_mcp.read_text())
    else:
        config = {}

    config.setdefault("mcpServers", {})
    config["mcpServers"]["google-chat"] = mcp_entry
    cursor_mcp.write_text(json.dumps(config, indent=2) + "\n")
    click.echo(f"✅ Cursor MCP config updated: {cursor_mcp}")

    # 4. Authenticate
    click.echo("\nOpening browser for Google authentication...")
    try:
        creds = get_credentials()
        click.echo(f"\n✅ Authentication successful!")
        click.echo(f"   Token saved to: {TOKEN_FILE}")
        click.echo("\n🎉 All done! Reload Cursor (Cmd+Shift+P → Developer: Reload Window) and you're good to go.")
    except Exception as e:
        click.echo(f"\n❌ Authentication failed: {e}", err=True)
        click.echo("You can retry with: google-chat-mcp auth")
        sys.exit(1)


@main.command()
@click.option(
    "--credentials",
    envvar="GOOGLE_CHAT_CREDENTIALS",
    help="Path to your OAuth credentials.json file.",
    type=click.Path(exists=True),
)
def auth(credentials):
    """Authenticate with Google (opens browser for OAuth consent).

    Run this once before starting the MCP server.
    Your token will be saved to ~/.config/google-chat-mcp/token.json.
    """
    from .auth import get_credentials, TOKEN_FILE

    _inject_saved_env()

    click.echo("Opening browser for Google authentication...")
    try:
        creds_path = Path(credentials) if credentials else None
        creds = get_credentials(credentials_file=creds_path)
        click.echo(f"\n✅ Authentication successful!")
        click.echo(f"   Token saved to: {TOKEN_FILE}")
        click.echo("\nYou can now start the MCP server with: google-chat-mcp serve")
    except FileNotFoundError as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n❌ Authentication failed: {e}", err=True)
        sys.exit(1)


@main.command()
def serve():
    """Start the MCP server (stdio transport)."""
    _inject_saved_env()

    from .server import serve as _serve
    _serve()


@main.command()
def logout():
    """Revoke the cached OAuth token (forces re-authentication on next use)."""
    from .auth import revoke_credentials
    revoke_credentials()


if __name__ == "__main__":
    main()
