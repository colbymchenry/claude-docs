# claude-docs

A global MCP server for Claude Code that gives Claude a persistent, per-project knowledge base. Instead of rediscovering how your auth works, what your database schema looks like, or which config values matter every session, Claude reads and writes organized markdown docs that live in your project repo.

Think of it as giving Claude its own wiki per project — except it's just markdown files in `.claude/docs/`.

## Why

Claude Code is stateless between sessions. Every new conversation starts from scratch — Claude re-reads source files, re-discovers patterns, and re-learns conventions it already figured out last time. This wastes time and tokens.

claude-docs fixes this by giving Claude 6 tools to maintain a project knowledge base:

- **`list_docs()`** — See what's documented. Called at the start of every task.
- **`lookup_doc(topic)`** — Read a doc. Fuzzy matches topic names, warns if docs are stale (60+ days old), notes `[[wiki-links]]` to related docs.
- **`save_doc(topic, content)`** — Write a doc. Auto-sets timestamps, returns previous content if overwriting.
- **`search_docs(query)`** — Regex search across all docs.
- **`semantic_search_docs(query)`** — Search by meaning using ChromaDB vector embeddings. Finds conceptually related content even without keyword matches.
- **`delete_doc(topic)`** — Remove a doc. Cleans up empty directories.

## Install

Requires [uv](https://docs.astral.sh/uv/) and [jq](https://jqlang.github.io/jq/).

```bash
git clone https://github.com/colbymchenry/claude-docs.git
cd claude-docs
./install.sh
```

This installs Python dependencies, registers the MCP server in `~/.claude.json`, adds tool permissions, and sets up Stop + UserPromptSubmit hooks. Restart Claude Code after installing.

Alternatively, install via npm (runs the same setup automatically via postinstall):

```bash
npm install -g @colbymchenry/claude-docs
```

### Auto-allowed tools

The installer adds these permissions to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__claude-docs__list_docs",
      "mcp__claude-docs__lookup_doc",
      "mcp__claude-docs__save_doc",
      "mcp__claude-docs__search_docs",
      "mcp__claude-docs__delete_doc",
      "mcp__claude-docs__semantic_search_docs"
    ]
  }
}
```

## How It Works

### Storage

Docs live in `.claude/docs/` at your project root. Embeddings are stored in `.claude/docs/.embeddings/`. Commit the docs to git so the whole team benefits (embeddings are regenerated automatically).

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
  .embeddings/     # ChromaDB vector store (auto-generated, gitignore this)
```

A file watcher monitors `.claude/docs/` and auto-indexes any changes — docs created via `save_doc()`, `Edit`, `Write`, or even your text editor are all picked up.

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

## Hooks (installed automatically)

The installer configures two hooks:

### UserPromptSubmit — auto doc recall

On every prompt, `hooks/claude-docs-on-prompt.sh` queries your doc embeddings for context relevant to what you just asked. Matching doc chunks are injected as `additionalContext` so Claude has project knowledge before responding — no manual `lookup_doc()` needed.

### Stop — document findings

Once per session, Claude is prompted to call `list_docs()` and `save_doc()` for anything it learned.

The hook script (`~/.claude/hooks/claude-docs-stop.sh`):

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

### Manual hook setup

If you didn't use the installer, create the stop hook script above, then register both hooks in `~/.claude/settings.json`:

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
    ],
    "UserPromptSubmit": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/claude-docs/hooks/claude-docs-on-prompt.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

## What This Is NOT

- **Not a memory system** — it stores project knowledge, not conversation history or personal preferences.
- **Not complex** — the server is a single Python file. Embeddings use ChromaDB's built-in ONNX model (no PyTorch).

## Tech Stack

- Python 3.10+ with [FastMCP](https://github.com/modelcontextprotocol/python-sdk)
- [ChromaDB](https://www.trychroma.com/) for vector embeddings (all-MiniLM-L6-v2 via ONNX, no PyTorch)
- [watchdog](https://github.com/gorakhargosh/watchdog) for filesystem monitoring — docs written via any tool are auto-indexed
- [uv](https://docs.astral.sh/uv/) for dependency management

## License

MIT
