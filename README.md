# claude-docs

A global MCP server for Claude Code that gives Claude a persistent, per-project knowledge base. Instead of rediscovering how your auth works, what your database schema looks like, or which config values matter every session, Claude reads and writes organized markdown docs that live in your project repo.

Think of it as giving Claude its own wiki per project — except it's just markdown files in `.claude/docs/`.

## Why

Claude Code is stateless between sessions. Every new conversation starts from scratch — Claude re-reads source files, re-discovers patterns, and re-learns conventions it already figured out last time. This wastes time and tokens.

claude-docs fixes this by giving Claude 5 tools to maintain a project knowledge base:

- **`list_docs()`** — See what's documented. Called at the start of every task.
- **`lookup_doc(topic)`** — Read a doc. Fuzzy matches topic names, warns if docs are stale (60+ days old), notes `[[wiki-links]]` to related docs.
- **`save_doc(topic, content)`** — Write a doc. Auto-sets timestamps, returns previous content if overwriting.
- **`search_docs(query)`** — Grep across all docs. Powered by ripgrep (bundled via `@vscode/ripgrep`).
- **`delete_doc(topic)`** — Remove a doc. Cleans up empty directories.

## Install

```bash
npm install -g claude-docs
claude mcp add -s user claude-docs claude-docs
```

That's it. Every project you open with Claude Code now has the tools available.

### Auto-allow the tools (recommended)

Add these to your `~/.claude/settings.json` permissions so Claude doesn't prompt for each tool call:

```json
{
  "permissions": {
    "allow": [
      "mcp__claude-docs__list_docs",
      "mcp__claude-docs__lookup_doc",
      "mcp__claude-docs__save_doc",
      "mcp__claude-docs__search_docs",
      "mcp__claude-docs__delete_doc"
    ]
  }
}
```

## How It Works

### Storage

Docs live in `.claude/docs/` at your project root. Commit them to git so the whole team benefits.

```
.claude/docs/
  auth.md
  database/
    schema.md
    migrations.md
  workflow/
    typescript-validation.md
  api/
    routes.md
```

### Doc format

Plain markdown with an auto-managed `updated` timestamp:

```markdown
---
updated: 2025-06-15
---

# Authentication

This project uses better-auth with Drizzle adapter...

## Related
- [[database/schema]] - user and session tables
- [[api/middleware]] - auth middleware chain
```

### Workflow docs

Docs saved under `workflow/` are special — `list_docs()` auto-inlines their full content so Claude sees them at the start of every task. Use this for conventions that always apply:

- "Always run `shopify theme check` before finishing theme changes"
- "Always run `npx tsc --noEmit` before finishing TypeScript changes"
- "Always run tests before committing"

### Staleness warnings

When a doc hasn't been updated in over 60 days, `lookup_doc()` includes a warning:

> ⚠ This doc was last updated 93 days ago — verify against source code before relying on it.

## Stop Hook (Optional)

The real power comes from pairing claude-docs with a Stop hook that nudges Claude to document findings at the end of every session.

Create `~/.claude/hooks/claude-docs-stop.sh`:

```bash
#!/bin/bash
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')

MARKER="/tmp/claude-docs-reminded-${SESSION_ID}"
if [ -f "$MARKER" ]; then
  exit 0
fi
touch "$MARKER"

cat >&2 <<'MSG'
You MUST now call list_docs() and review what you learned this session. Then call save_doc() for anything worth preserving. This is NOT optional. If you made code changes, you almost certainly have something to document.
MSG
exit 2
```

```bash
chmod +x ~/.claude/hooks/claude-docs-stop.sh
```

Register it in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/claude-docs-stop.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Now Claude gets nudged once per session to document what it learned — error fixes, config gotchas, API patterns, workflow conventions — so the next session doesn't repeat the work.

## What This Is NOT

- **Not a memory system** — it stores project knowledge, not conversation history or personal preferences.
- **Not semantic search** — it's filename fuzzy matching + ripgrep, not vector embeddings.
- **Not complex** — the entire server is a single TypeScript file with zero heavy dependencies.

## Tech Stack

- TypeScript + MCP SDK (`@modelcontextprotocol/sdk`)
- `@vscode/ripgrep` for content search (bundled, no system install)
- Node.js `fs` for everything else
- No database, no embeddings, no ML

## License

MIT
