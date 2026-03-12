"""Google Chat API client wrapper.

Wraps the Google Chat REST API v1 for listing spaces,
fetching messages, and searching across message history.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import get_credentials

_SPACES_CACHE_TTL = 300  # 5 minutes


class GoogleChatClient:
    """Thin wrapper around the Google Chat API with search helpers."""

    def __init__(self, credentials_file=None):
        self._creds = get_credentials(credentials_file)
        self._local = threading.local()
        self._display_name_cache: dict[str, str] = {}
        self._spaces_cache: list[dict[str, Any]] | None = None
        self._spaces_cache_time: float = 0

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
        """Resolve a Google user resource name to a display name."""
        if user_resource in self._display_name_cache:
            return self._display_name_cache[user_resource]

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
        """Batch-resolve a list of user resource names to display names."""
        return {r: self.get_display_name(r) for r in user_resources}

    # ------------------------------------------------------------------
    # Spaces (cached)
    # ------------------------------------------------------------------

    def list_spaces(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Return all spaces the authenticated user is a member of.

        Results are cached for 5 minutes to avoid repeated API calls during search.
        """
        now = time.monotonic()
        if (
            not force_refresh
            and self._spaces_cache is not None
            and (now - self._spaces_cache_time) < _SPACES_CACHE_TTL
        ):
            return self._spaces_cache

        spaces: list[dict[str, Any]] = []
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

        self._spaces_cache = spaces
        self._spaces_cache_time = now
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

    def _filter_active_spaces(
        self, space_names: list[str], days_back: int,
    ) -> list[str]:
        """Pre-filter spaces to only those with recent activity.

        Probes each space with a single message fetch (limit=1) with a time
        filter. Spaces with no messages in the window are skipped entirely.
        Much cheaper than running a full hasWords search on 1000+ spaces.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        ts = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        filter_str = f'createTime > "{ts}"'

        active: list[str] = []
        lock = threading.Lock()

        def _probe(space_name: str) -> None:
            try:
                msgs = self.get_messages(
                    space_name, limit=1, filter_str=filter_str,
                )
                if msgs:
                    with lock:
                        active.append(space_name)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=30) as pool:
            list(pool.map(_probe, space_names))

        return active

    def search_messages(
        self,
        query: str,
        *,
        space_names: list[str] | None = None,
        max_results: int = 500,
        days_back: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search message content across all (or specified) spaces.

        Optimized for large workspaces (1000+ spaces):

        1. If days_back is set and searching all spaces, pre-filter to only
           spaces with recent activity (cheap 1-message probe per space).
           This typically reduces 1000+ spaces down to ~50-100.

        2. Use server-side hasWords filter on active spaces in parallel.

        3. Fallback to client-side filtering only for spaces where the API
           returned an error (not empty results).

        4. Early termination once max_results is reached.
        """
        if space_names is None:
            all_spaces = self.list_spaces()
            space_names = [s["name"] for s in all_spaces]

        if not space_names:
            return []

        # Pre-filter: when searching all spaces with a time window,
        # probe for activity first to avoid searching 1000+ dead spaces
        if days_back and len(space_names) > 50:
            space_names = self._filter_active_spaces(space_names, days_back)
            if not space_names:
                return []

        time_filter = ""
        if days_back:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
            ts = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
            time_filter = f' AND createTime > "{ts}"'

        max_per_space = max(20, max_results // max(1, len(space_names)))
        collected: list[dict[str, Any]] = []
        needs_fallback: list[str] = []
        lock = threading.Lock()

        def _has_enough() -> bool:
            with lock:
                return len(collected) >= max_results

        def _search_server(space_name: str) -> None:
            if _has_enough():
                return
            try:
                filter_str = f'hasWords:"{_escape_filter(query)}"{time_filter}'
                msgs = self.get_messages(
                    space_name,
                    limit=max_per_space,
                    filter_str=filter_str,
                )
                if msgs:
                    with lock:
                        collected.extend(msgs)
            except HttpError as e:
                if e.resp.status not in (403, 404):
                    with lock:
                        needs_fallback.append(space_name)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(_search_server, space_names))

        # Fallback: only for spaces where hasWords errored (not empty)
        if needs_fallback and not _has_enough():
            remaining = max_results - len(collected)
            fallback_limit = min(100, remaining)

            def _search_fallback(space_name: str) -> None:
                if _has_enough():
                    return
                try:
                    msgs = self.get_messages(
                        space_name,
                        limit=fallback_limit,
                        days_back=days_back or 7,
                    )
                    query_lower = query.lower()
                    matches = [
                        m for m in msgs
                        if query_lower in _msg_text(m).lower()
                    ]
                    if matches:
                        with lock:
                            collected.extend(matches)
                except Exception:
                    pass

            with ThreadPoolExecutor(max_workers=10) as pool:
                list(pool.map(_search_fallback, needs_fallback))

        # Deduplicate and sort newest-first
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for msg in sorted(collected, key=lambda m: m.get("createTime", ""), reverse=True):
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
