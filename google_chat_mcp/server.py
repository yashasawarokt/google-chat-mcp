"""MCP server for Google Chat.

Exposes 4 tools via the Model Context Protocol (stdio transport):
  - gchat_list_spaces
  - gchat_search_messages
  - gchat_get_space_messages
  - gchat_get_space_members
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import GoogleChatClient, format_message

mcp = FastMCP(
    name="google-chat",
    instructions=(
        "You have access to the user's Google Chat workspace. "
        "Use gchat_list_spaces first to discover available spaces, "
        "then search or read messages as needed. "
        "Always show the space name and sender with each message."
    ),
)

# Lazy client — instantiated on first tool call
_client: GoogleChatClient | None = None
_spaces_cache: dict[str, dict[str, Any]] | None = None


def _get_client() -> GoogleChatClient:
    global _client
    if _client is None:
        creds_file = os.environ.get("GOOGLE_CHAT_CREDENTIALS")
        _client = GoogleChatClient(credentials_file=creds_file)
    return _client


def _get_spaces_by_name() -> dict[str, dict[str, Any]]:
    """Return a dict mapping space resource name → space dict (cached)."""
    global _spaces_cache
    if _spaces_cache is None:
        spaces = _get_client().list_spaces()
        _spaces_cache = {s["name"]: s for s in spaces}
    return _spaces_cache


# ------------------------------------------------------------------
# Tool: gchat_list_spaces
# ------------------------------------------------------------------

@mcp.tool()
def gchat_list_spaces() -> str:
    """List all Google Chat spaces, group chats, and DMs the user is a member of.

    Returns a formatted list with each space's resource name (for use in
    other tools), display name, and type (SPACE, GROUP_CHAT, DIRECT_MESSAGE).
    """
    spaces = _get_client().list_spaces()
    if not spaces:
        return "No spaces found."

    lines = [f"Found {len(spaces)} spaces:\n"]
    for s in spaces:
        stype = s.get("spaceType", s.get("type", "UNKNOWN"))
        display = s.get("displayName") or s.get("name", "")
        resource = s.get("name", "")
        lines.append(f"• [{stype}] {display or '(unnamed)'} — {resource}")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Tool: gchat_search_messages
# ------------------------------------------------------------------

@mcp.tool()
def gchat_search_messages(
    query: str,
    space_ids: str | None = None,
    max_results: int = 500,
    days_back: int | None = None,
) -> str:
    """Search Google Chat message history across all spaces (or specific ones).

    Args:
        query: Text to search for — words, phrases, names, topics, etc.
        space_ids: Comma-separated list of space resource names to search
                   (e.g. "spaces/ABC,spaces/XYZ"). Leave empty to search ALL spaces.
        max_results: Maximum number of messages to return (default 500, no upper limit).
        days_back: Limit search to this many days of history. Leave empty for full history.

    Returns:
        Matching messages formatted as: [timestamp] SpaceName | Sender: message text
    """
    client = _get_client()
    spaces_by_name = _get_spaces_by_name()

    # Parse optional space filter
    search_spaces: list[str] | None = None
    if space_ids:
        raw = [s.strip() for s in space_ids.split(",") if s.strip()]
        search_spaces = raw if raw else None

    max_results = max(1, max_results)

    results = client.search_messages(
        query,
        space_names=search_spaces,
        max_results=max_results,
        days_back=days_back,
    )

    if not results:
        scope = f"in the last {days_back} days" if days_back else "across all history"
        return f"No messages found matching '{query}' {scope}."

    lines = [f"Found {len(results)} messages matching '{query}':\n"]
    for msg in results:
        lines.append(format_message(msg, spaces_by_name, client))

    return "\n".join(lines)


# ------------------------------------------------------------------
# Tool: gchat_get_space_messages
# ------------------------------------------------------------------

@mcp.tool()
def gchat_get_space_messages(
    space_id: str,
    limit: int = 500,
    hours_back: int | None = None,
    days_back: int | None = None,
) -> str:
    """Get recent messages from a specific Google Chat space or DM.

    Args:
        space_id: Space resource name (e.g. "spaces/XXXXXXXX").
                  Get this from gchat_list_spaces.
        limit: Number of messages to fetch (default 500, no upper limit).
        hours_back: Only return messages from the last N hours.
        days_back: Only return messages from the last N days.
                   If neither is set, returns the N most recent messages.

    Returns:
        Messages formatted as: [timestamp] SpaceName | Sender: message text
    """
    client = _get_client()
    spaces_by_name = _get_spaces_by_name()

    limit = max(1, limit)

    messages = client.get_messages(
        space_id,
        limit=limit,
        hours_back=hours_back,
        days_back=days_back,
    )

    if not messages:
        return f"No messages found in {space_id}."

    space_display = space_id
    if space_id in spaces_by_name:
        space_display = spaces_by_name[space_id].get("displayName") or space_id

    lines = [f"{len(messages)} messages from '{space_display}':\n"]
    for msg in messages:
        lines.append(format_message(msg, spaces_by_name, client))

    return "\n".join(lines)


# ------------------------------------------------------------------
# Tool: gchat_get_space_members
# ------------------------------------------------------------------

@mcp.tool()
def gchat_get_space_members(space_id: str) -> str:
    """List the members of a Google Chat space or group chat.

    Args:
        space_id: Space resource name (e.g. "spaces/XXXXXXXX").
                  Get this from gchat_list_spaces.

    Returns:
        A list of member names and their roles in the space.
    """
    client = _get_client()
    members = client.get_members(space_id)

    if not members:
        return f"No members found for {space_id} (or access is restricted)."

    lines = [f"{len(members)} members in {space_id}:\n"]
    for m in members:
        member_info = m.get("member", {})
        resource = member_info.get("name", "")
        display = member_info.get("displayName")
        if not display and resource:
            display = client.get_display_name(resource)
        display = display or resource or "Unknown"
        role = m.get("role", "ROLE_MEMBER")
        mtype = member_info.get("type", "HUMAN")
        lines.append(f"• {display} ({mtype}, {role})")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def serve():
    """Start the MCP server (stdio transport)."""
    mcp.run(transport="stdio")
