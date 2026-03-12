---
name: gchat-search
description: >
  Search Google Chat spaces, DMs, and message history. Look up decisions,
  shared links, discussions, and past conversations across your entire
  Google Chat workspace using the google-chat MCP connector. Resolves real
  display names for all senders and space members via the Google People API.
triggers:
  - google chat
  - gchat
  - chat history
  - chat message
  - look up in chat
  - search chat
  - find message
  - what did someone say
  - chat spaces
  - team discussion
  - who said
  - chat DM
  - who have I spoken to
  - who messaged me
  - people I talked to
---

# Google Chat Search Skill

## Overview

You have access to the user's Google Chat workspace via the `google-chat` MCP server.
You can search message history, browse spaces, look up past discussions, and resolve
all sender/member user IDs to real display names via the Google People (Directory) API.

## Available Tools

- **`gchat_list_spaces`** — lists all spaces, group chats, and DMs the user belongs to
- **`gchat_search_messages`** — full-text search across all (or specific) spaces
- **`gchat_get_space_messages`** — read recent messages from a specific space
- **`gchat_get_space_members`** — list who is in a given space (returns real names)

## Workflow

### For general questions about what was discussed / decided / shared:

1. Call `gchat_search_messages` with the most relevant keywords from the user's question
2. If results are thin, broaden the query or try alternate keywords
3. Summarize the relevant messages and cite sender + timestamp
4. If the user asks to go deeper into a specific space, use `gchat_get_space_messages`

### For "what spaces am I in?" or "show me the Eng team space":

1. Call `gchat_list_spaces` first
2. Show the list, then offer to search or read messages from any of them

### For "what happened recently in X space":

1. If you don't have the space_id, call `gchat_list_spaces` to find it
2. Call `gchat_get_space_messages` with `days_back` set appropriately (e.g. 7 for "last week")

### For "who have I spoken to recently?" or "list people I've talked to":

1. Call `gchat_search_messages` with a broad query and `days_back` set to the requested window
2. Collect all unique senders from the results (names are already resolved)
3. Supplement with `gchat_get_space_members` on any private/DM spaces active in that window
4. Group by: 1-on-1 DMs first, then group spaces

### For "who's in this space?":

1. Call `gchat_get_space_members` with the space_id — names are fully resolved

## Display Name Resolution

All sender and member names are **automatically resolved** to real display names via the
Google People/Directory API. You will never see raw `users/123456` IDs in tool output.
No extra steps needed — just use the names as returned.

## Search Tips

- Use **short, specific keyword phrases** — the search works best with 2–4 key terms
- For people's names, just use their first name (e.g. `"query": "sarah"`)
- For decisions/links, search for the topic word (e.g. `"budget", "API docs", "launch date"`)
- Combine multiple searches if the first comes back empty
- Use `days_back` to narrow down time range when the user specifies "recently" or "last week"
- Leave `query` as an empty string with `days_back` set to get all recent activity

## Response Format

Always include for each relevant message:
- **Who** said it (sender name)
- **When** (timestamp)
- **Where** (space/channel name)
- **What** (the message text, quoted or paraphrased)

Example:
> On **2026-03-12**, **Caroline Tan** in **#product-visa**: "We decided to use the legacy SDK solution."

## Setup (for new users)

If you get an authentication error, the user needs to:
1. Run `google-chat-mcp setup` in their terminal (prompts for Client ID + Secret, configures everything)
2. Complete the Google OAuth flow in their browser (grants Chat + Directory read access)
3. Reload Cursor (Cmd+Shift+P → Developer: Reload Window)

If they've already run setup but the token expired, just run `google-chat-mcp auth`.

If there's no MCP connection at all, direct them to the README for full setup instructions.
