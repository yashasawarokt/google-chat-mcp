# google-chat-mcp

An MCP (Model Context Protocol) server that connects Claude to your Google Chat workspace — search spaces, DMs, and full message history. All sender and member names are **automatically resolved to real display names** via the Google People/Directory API.

**Each user authenticates with their own Google account.** No shared credentials, no admin access required.

---

## What you can do with it

- Search your full message history across all spaces and DMs
- Ask Claude questions like "what did the team decide about X?", "find the doc Sarah shared in the eng channel", "what were we discussing last week about the API?"
- Browse spaces, read recent messages, see who's in a given space — with **real names**, not user IDs
- Ask "who have I spoken to in the last 3 days?" and get a named list
- Works with **Cursor**, **Claude Code**, **Claude Desktop**, and **Cowork**

---

## Setup

**Step 1 — Install**

```bash
git clone https://github.com/ROKT/google-chat-mcp-yash.git
cd google-chat-mcp-yash
pipx install -e .
```

> **Don't have pipx?** `brew install pipx`

**Step 2 — Get `credentials.json`**

Get `credentials.json` from the team's shared credential store (Slack, 1Password, etc.) and place it in the project root.

**Step 3 — Authenticate**

```bash
google-chat-mcp auth --credentials ./credentials.json
```

This opens a browser window. Sign in with your **Rokt Google account** and grant the requested permissions. Your token is saved to `~/.config/google-chat-mcp/token.json` — you won't need to do this again unless you log out.

> **Tip:** Copy `credentials.json` to `~/.config/google-chat-mcp/credentials.json` once and you can just run `google-chat-mcp auth` without the flag in future.

---

## Connecting to your MCP client

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "google-chat": {
      "command": "google-chat-mcp",
      "args": ["serve"]
    }
  }
}
```

> Find the full binary path with `which google-chat-mcp` if Cursor can't find it, and use that instead of `"google-chat-mcp"`.

Then reload Cursor: **Cmd+Shift+P → Developer: Reload Window**

### Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "google-chat": {
      "command": "google-chat-mcp",
      "args": ["serve"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "google-chat": {
      "command": "google-chat-mcp",
      "args": ["serve"]
    }
  }
}
```

### Cowork (Claude desktop app)

Copy `skill/SKILL.md` to your Cowork skills folder, or install it via the skill management UI.

---

## Usage

Once connected, just ask Claude naturally:

| What you want | What to ask |
|---|---|
| Search history | "Search my Google Chat for any messages about the Q4 budget" |
| Find a decision | "What did we decide about the API versioning policy?" |
| Find a doc that was shared | "Did anyone share a link to the new design doc in the product channel?" |
| Recent activity | "What was discussed in the engineering space last week?" |
| Who's in a space | "Who's in the #data-platform space?" |
| Browse spaces | "Show me all my Google Chat spaces" |
| Recent conversations | "Who have I spoken to in the last 3 days?" |

---

## Available MCP tools

| Tool | Description |
|---|---|
| `gchat_list_spaces` | List all spaces, group chats, and DMs |
| `gchat_search_messages` | Search messages across all or specific spaces |
| `gchat_get_space_messages` | Get recent messages from one space |
| `gchat_get_space_members` | List members of a space (with real display names) |

All tools return **real display names** for senders and members — no raw user IDs.

---

## OAuth Scopes

This server requests the following read-only scopes:

| Scope | Purpose |
|---|---|
| `chat.spaces.readonly` | List spaces and DMs |
| `chat.messages.readonly` | Read message history |
| `chat.memberships.readonly` | Read space membership |
| `directory.readonly` | Resolve user IDs → real names via Google People API |

Nothing is ever written — all scopes are read-only.

---

## Troubleshooting

**`Connection closed` in Cursor** — Run `which google-chat-mcp` in your terminal, and use the full path in `mcp.json` instead of just `"google-chat-mcp"`.

**`Error 403: The caller does not have permission`** — Your Google Workspace may restrict Chat or People API access. Ask your admin to allow them.

**`No messages found`** — The Google Chat API only returns messages in spaces where you're a member. DMs with inactive accounts may also return empty.

**Token expired** — Run `google-chat-mcp auth` again to refresh.

**Force re-authentication** — Run `google-chat-mcp logout` then `google-chat-mcp auth`.

---

## Commands

```
google-chat-mcp auth     # Authenticate with Google (run once)
google-chat-mcp serve    # Start MCP server (called automatically by MCP clients)
google-chat-mcp logout   # Revoke cached token
```

---

## Privacy & security

- All authentication is handled by Google OAuth 2.0 — your password is never stored
- The server only requests **read-only** scopes — it cannot send messages or modify anything
- Your token is stored locally at `~/.config/google-chat-mcp/token.json`
- Nothing is sent to any third-party server — the MCP server runs entirely on your machine

---

## License

MIT
