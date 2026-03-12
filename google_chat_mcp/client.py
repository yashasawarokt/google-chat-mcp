"""Google Chat API client wrapper.

Wraps the Google Chat REST API v1 for listing spaces,
fetching messages, and searching across message history.
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import get_credentials


class GoogleChatClient:
    """Thin wrapper around the Google Chat API with search helpers."""

    def __init__(self, credentials_file=None):
        self._creds = get_credentials(credentials_file)
        self._local = threading.local()
        self._display_name_cache: dict[str, str] = {}

    @property
    def _service(self):
        """Return a thread-local service instance.

        googleapiclient uses httplib2 under the hood, which is NOT thread-safe.
        Creating one service per thread avoids concurrent connection corruption
        that causes Python to segfault under heavy parallel search load.
        """
        if not hasattr(self._local, "service"):
            self._local.service = build("chat", "v1", credentials=self._creds, cache_discovery=False)
        return self._local.service

    @property
    def _people_service(self):
        """Return a thread-local People API service instance."""
        if not hasattr(self._local, "people_service"):
            self._local.people_service = build("people", "v1", credentials=self._creds, cache_discovery=False)
        return self._local.people_service

    # ------------------------------------------------------------------
    # People API — display name resolution
    # ------------------------------------------------------------------

    def get_display_name(self, user_resource: str) -> str:
        """Resolve a Google user resource name to a display name.

        Args:
            user_resource: e.g. "users/113563209800934591916"

        Returns:
            Display name string, or the original resource name if lookup fails.
        """
        if user_resource in self._display_name_cache:
            return self._display_name_cache[user_resource]

        # Convert "users/123" → "people/123" for the People API
        people_resource = user_resource.replace("users/", "people/", 1)
        try:
            result = (
                self._people_service.people()
                .get(resourceName=people_resource, personFields="names,emailAddresses")
                .execute()
            )
            names = result.get("names", [])
            display = names[0].get("displayName") if names else None
            if not display:
                emails = result.get("emailAddresses", [])
                display = emails[0].get("value") if emails else None
            display = display or user_resource
        except Exception:
            display = user_resource

        self._display_name_cache[user_resource] = display
        return display

    def resolve_display_names(self, user_resources: list[str]) -> dict[str, str]:
        """Batch-resolve a list of user resource names to display names.

        Returns a dict mapping resource name → display name.
        """
        return {r: self.get_display_name(r) for r in user_resources}

    # ------------------------------------------------------------------
    # Spaces
    # ------------------------------------------------------------------

    def list_spaces(self) -> list[dict[str, Any]]:
        """Return all spaces the authenticated user is a member of.

        Includes SPACE (named rooms), GROUP_CHAT, and DIRECT_MESSAGE.
        """
        spaces = []
        page_token = None

        while True:
            kwargs: dict[str, Any] = {"pageSize": 1000}
            if page_token:
                kwargs["pageToken"] = page_token

            result = self._service.spaces().list(**kwargs).execute()
            spaces.extend(result.get("spaces", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return spaces

    # ------------------------------------------------------------------
    # Messages — single space
    # ------------------------------------------------------------------

    def get_messages(
        self,
        space_name: str,
        *,
        limit: int = 1000,
        hours_back: int | None = None,
        days_back: int | None = None,
        filter_str: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch messages from a single space, newest first.

        Args:
            space_name: Resource name like "spaces/XXXXXXXX".
            limit: Max messages to return.
            hours_back: Only return messages from the last N hours.
            days_back: Only return messages from the last N days.
                       Takes precedence over hours_back if both set.
            filter_str: Raw Google Chat API filter string.
        """
        filters: list[str] = []

        if filter_str:
            filters.append(filter_str)
        elif days_back is not None or hours_back is not None:
            delta = timedelta(days=days_back) if days_back else timedelta(hours=hours_back or 24)
            cutoff = datetime.now(timezone.utc) - delta
            # RFC3339 format required by the API
            ts = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
            filters.append(f'createTime > "{ts}"')

        messages: list[dict[str, Any]] = []
        page_token = None

        while len(messages) < limit:
            batch = min(1000, limit - len(messages))
            kwargs: dict[str, Any] = {
                "parent": space_name,
                "pageSize": batch,
                "orderBy": "createTime desc",
            }
            if filters:
                kwargs["filter"] = " AND ".join(filters)
            if page_token:
                kwargs["pageToken"] = page_token

            try:
                result = self._service.spaces().messages().list(**kwargs).execute()
            except HttpError as e:
                # Some spaces (e.g. DMs) may have restricted APIs — skip silently
                if e.resp.status in (403, 404):
                    break
                raise

            batch_msgs = result.get("messages", [])
            messages.extend(batch_msgs)

            page_token = result.get("nextPageToken")
            if not page_token or len(batch_msgs) == 0:
                break

        return messages[:limit]

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def get_members(self, space_name: str) -> list[dict[str, Any]]:
        """Return all members of a space."""
        members: list[dict[str, Any]] = []
        page_token = None

        while True:
            kwargs: dict[str, Any] = {"parent": space_name, "pageSize": 1000}
            if page_token:
                kwargs["pageToken"] = page_token

            try:
                result = self._service.spaces().members().list(**kwargs).execute()
            except HttpError as e:
                if e.resp.status in (403, 404):
                    break
                raise

            members.extend(result.get("memberships", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return members

    # ------------------------------------------------------------------
    # Single-item getters
    # ------------------------------------------------------------------

    def get_space(self, space_name: str) -> dict[str, Any]:
        """Get details for a single space."""
        return self._service.spaces().get(name=space_name).execute()

    def get_message(self, message_name: str) -> dict[str, Any]:
        """Get a single message by resource name (e.g. spaces/X/messages/Y)."""
        return self._service.spaces().messages().get(name=message_name).execute()

    def get_member(self, member_name: str) -> dict[str, Any]:
        """Get a single member by resource name (e.g. spaces/X/members/Y)."""
        return self._service.spaces().members().get(name=member_name).execute()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def send_message(self, space_name: str, text: str) -> dict[str, Any]:
        """Send a text message to a space.

        Args:
            space_name: Resource name like "spaces/XXXXXXXX".
            text: Message body text.

        Returns:
            The created message dict.
        """
        return (
            self._service.spaces().messages()
            .create(parent=space_name, body={"text": text})
            .execute()
        )

    def delete_message(self, message_name: str) -> None:
        """Delete a message by resource name (e.g. spaces/X/messages/Y)."""
        self._service.spaces().messages().delete(name=message_name).execute()

    # ------------------------------------------------------------------
    # Search — across spaces
    # ------------------------------------------------------------------

    def search_messages(
        self,
        query: str,
        *,
        space_names: list[str] | None = None,
        max_results: int = 500,
        days_back: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search message content across all (or specified) spaces.

        Strategy:
          1. Try the hasWords API filter first — fast server-side search.
          2. If that returns nothing (unsupported or no match), fall back to
             fetching recent messages and filtering client-side.
          3. Search up to 20 spaces in parallel for speed.

        Args:
            query: Text to search for.
            space_names: List of resource names to search in. Searches all
                         spaces if None.
            max_results: Max total results to return.
            days_back: Limit search to this many days of history. None = all time.

        Returns:
            List of message dicts sorted by createTime descending.
        """
        if space_names is None:
            all_spaces = self.list_spaces()
            space_names = [s["name"] for s in all_spaces]

        max_per_space = max(50, max_results // max(1, len(space_names)))

        def _search_one(space_name: str) -> list[dict[str, Any]]:
            # Try hasWords filter first
            try:
                time_filter = ""
                if days_back:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
                    ts = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
                    time_filter = f' AND createTime > "{ts}"'

                filter_str = f'hasWords:"{_escape_filter(query)}"{time_filter}'
                msgs = self.get_messages(
                    space_name,
                    limit=max_per_space,
                    filter_str=filter_str,
                )
                if msgs:
                    return msgs
            except HttpError:
                pass

            # Fallback: fetch recent messages and filter client-side
            fetch_limit = max(200, max_per_space * 10)
            msgs = self.get_messages(
                space_name,
                limit=fetch_limit,
                days_back=days_back,
            )
            query_lower = query.lower()
            return [
                m for m in msgs
                if query_lower in _msg_text(m).lower()
            ][:max_per_space]

        all_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=50) as pool:
            futures = {pool.submit(_search_one, name): name for name in space_names}
            for future in as_completed(futures):
                try:
                    all_results.extend(future.result())
                except Exception:
                    pass  # Skip spaces that error out

        # Sort newest-first and deduplicate by message name
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for msg in sorted(all_results, key=lambda m: m.get("createTime", ""), reverse=True):
            name = msg.get("name", "")
            if name not in seen:
                seen.add(name)
                unique.append(msg)

        return unique[:max_results]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _msg_text(msg: dict[str, Any]) -> str:
    """Extract plain text body from a message dict."""
    return msg.get("text", "") or msg.get("formattedText", "") or ""


def _escape_filter(value: str) -> str:
    """Escape special characters in a Google Chat API filter value."""
    return value.replace('"', '\\"')


def format_message(
    msg: dict[str, Any],
    spaces_by_name: dict[str, dict[str, Any]] | None = None,
    client: "GoogleChatClient | None" = None,
) -> str:
    """Format a message dict as a readable string for LLM consumption."""
    sender_info = msg.get("sender", {})
    sender = sender_info.get("displayName")
    if not sender:
        sender_resource = sender_info.get("name", "")
        if sender_resource and client:
            sender = client.get_display_name(sender_resource)
        else:
            sender = sender_resource or "Unknown"
    timestamp = msg.get("createTime", "")
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            timestamp = dt.strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            pass

    space_name = msg.get("space", {}).get("name", "")
    space_display = space_name
    if spaces_by_name and space_name in spaces_by_name:
        space_info = spaces_by_name[space_name]
        space_display = space_info.get("displayName") or space_info.get("name", space_name)

    text = _msg_text(msg)
    return f"[{timestamp}] {space_display} | {sender}: {text}"
