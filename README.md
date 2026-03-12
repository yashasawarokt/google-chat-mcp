# google-chat-mcp

An MCP (Model Context Protocol) server that connects Claude to your Google Chat workspace — search spaces, DMs, and full message history. All sender and member names are **automatically resolved to real display names** via the Google People/Directory API.

**Each user authenticates with their own Google account.** No shared credentials files, no admin access required.

---

## What you can do with it

- Search your full message history across all spaces and DMs
- Ask Claude questions like "what did the team decide about X?", "find the doc Sarah shared in the eng channel", "what were we discussing last week about the API?"
- Browse spaces, read recent messages, see who's in a given space — with **real names**, not user IDs
- Ask "who have I spoken to in the last 3 days?" and get a named list
- Works with **Cursor**, **Claude Code**, **Claude Desktop**, and **Cowork**

---

## Setup

### Quick install (one command)

```bash
git clone https://github.com/ROKT/google-chat-mcp-yash.git && cd google-chat-mcp-yash && pipx install -e . && google-chat-mcp setup --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

Replace `YOUR_CLIENT_ID` and `YOUR_CLIENT_SECRET` with the values from 1Password or a teammate.

> **Don't have pipx?** Run `brew install pipx` first.

### What `setup` does

1. Saves your credentials locally to `~/.config/google-chat-mcp/env.json`
2. Automatically configures `~/.cursor/mcp.json`
3. Opens a browser for Google OAuth — sign in with your Rokt account

**That's it.** Reload Cursor (Cmd+Shift+P → Developer: Reload Window) and start chatting.

### Interactive setup (if you prefer)

```bash
google-chat-mcp setup
# Prompts for Client ID and Client Secret interactively
```

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
| Send a message | "Send 'heading out for lunch' to my DM with Caroline" |

---

## Available MCP tools

### Read

| Tool | Description |
|---|---|
| `gchat_list_spaces` | List all spaces, group chats, and DMs |
| `gchat_search_messages` | Search messages across all or specific spaces |
| `gchat_get_space_messages` | Get recent messages from one space |
| `gchat_get_space_members` | List members of a space (with real display names) |
| `gchat_get_space` | Get details of a specific space |
| `gchat_get_message` | Get a single message by resource name |
| `gchat_get_member` | Get details of a specific member |

### Write

| Tool | Description |
|---|---|
| `gchat_send_message` | Send a text message to a space or DM |
| `gchat_delete_message` | Delete a message |

All tools return **real display names** for senders and members — no raw user IDs.

---

## Other MCP clients

The `setup` command auto-configures Cursor. For other clients, add manually:

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

> For Claude Code and Claude Desktop, the `serve` command automatically loads saved credentials from `~/.config/google-chat-mcp/env.json` — no `env` block needed.

### Cowork

Copy `skill/SKILL.md` to your Cowork skills folder.

---

## Commands

```
google-chat-mcp setup    # One-time setup (saves creds, configures Cursor, authenticates)
google-chat-mcp auth     # Re-authenticate with Google
google-chat-mcp serve    # Start MCP server (called automatically by MCP clients)
google-chat-mcp logout   # Revoke cached token
```

---

## OAuth Scopes

| Scope | Purpose |
|---|---|
| `chat.spaces.readonly` | List spaces and DMs |
| `chat.messages.readonly` | Read message history |
| `chat.messages.create` | Send new messages |
| `chat.messages` | Delete messages |
| `chat.memberships.readonly` | Read space membership |
| `directory.readonly` | Resolve user IDs → real names via Google People API |

---

## Troubleshooting

**`No credentials found`** — Run `google-chat-mcp setup` to save your credentials.

**`Connection closed` in Cursor** — Run `which google-chat-mcp` and check the path matches what's in `~/.cursor/mcp.json`. Re-run `google-chat-mcp setup` to fix.

**`Error 403`** — Your Google Workspace may restrict Chat or People API access. Ask your admin.

**Token expired** — Run `google-chat-mcp auth` to refresh.

**Force re-authentication** — `google-chat-mcp logout && google-chat-mcp auth`

---

## Privacy & security

- All authentication is handled by Google OAuth 2.0 — your password is never stored
- Read and write scopes are requested — Claude can search messages and send on your behalf (always with your confirmation)
- Your token is stored locally at `~/.config/google-chat-mcp/token.json`
- OAuth client credentials are stored locally at `~/.config/google-chat-mcp/env.json`
- Nothing is sent to any third-party server — the MCP server runs entirely on your machine

---

## License

MIT
