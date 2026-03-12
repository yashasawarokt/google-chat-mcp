"""CLI entry point for google-chat-mcp.

Usage:
    google-chat-mcp auth     # Authenticate with Google (opens browser)
    google-chat-mcp serve    # Start MCP server (stdio, for Cursor/Claude Code)
    google-chat-mcp logout   # Revoke cached token
"""

from __future__ import annotations

import sys

import click


@click.group()
def main():
    """Google Chat MCP server — connect Claude to your Google Chat workspace."""
    pass


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
    from pathlib import Path
    from .auth import get_credentials, TOKEN_FILE

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
    """Start the MCP server (stdio transport).

    Add this to your MCP config in Cursor, Claude Code, or Claude Desktop:

    \b
    {
      "mcpServers": {
        "google-chat": {
          "command": "google-chat-mcp",
          "args": ["serve"]
        }
      }
    }
    """
    from .server import serve as _serve
    _serve()


@main.command()
def logout():
    """Revoke the cached OAuth token (forces re-authentication on next use)."""
    from .auth import revoke_credentials
    revoke_credentials()


if __name__ == "__main__":
    main()
