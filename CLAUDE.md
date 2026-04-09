# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

claude-docs is a global MCP server that gives Claude Code a persistent, per-project knowledge base with semantic search. It stores markdown docs in `.claude/docs/` and vector embeddings in `.claude/docs/.embeddings/` via ChromaDB. Originally TypeScript/npm, now Python-based (v2.0.0).

## Commands

```bash
# Install dependencies
uv sync

# Run the MCP server (stdio transport)
uv run python server.py

# Bootstrap embedding index for a project
uv run python server.py --index /path/to/project

# Query embeddings from CLI
echo "some prompt" | uv run python query.py --project-dir /path/to/project

# Full install (MCP registration, hooks, permissions, dependencies)
./install.sh

# Uninstall (removes MCP config, hooks, permissions; preserves docs)
./uninstall.sh
```

No test suite exists.

## Architecture

**`server.py`** — The entire MCP server in one file. Exposes 6 tools via `FastMCP`:
- `list_docs`, `lookup_doc`, `save_doc`, `search_docs`, `delete_doc`, `semantic_search_docs`
- Detects project root by walking up to find `.git` or `CLAUDE.md`
- Uses ChromaDB `PersistentClient` with cosine similarity for semantic search
- `DocWatcher` (watchdog-based) monitors `.claude/docs/` for filesystem changes and auto-re-indexes with debouncing and content hashing
- Documents are chunked by `##`/`###` headers before embedding
- `workflow/` docs are auto-inlined by `list_docs()` so conventions are always visible
- Staleness warnings trigger after 60 days without update

**`query.py`** — Standalone CLI that queries the ChromaDB embeddings. Used by the `UserPromptSubmit` hook to inject relevant doc context into every prompt.

**`hooks/claude-docs-on-prompt.sh`** — `UserPromptSubmit` hook. Pipes the user's prompt through `query.py` to find semantically relevant docs and returns them as `additionalContext`.

**`install.sh`** / **`scripts/postinstall.mjs`** — Two parallel install paths (shell script for local dev, postinstall for `npm install -g`). Both do the same thing: `uv sync`, register MCP server in `~/.claude.json`, add tool permissions and hooks to `~/.claude/settings.json`.

**`uninstall.sh`** — Removes MCP config, permissions, and hooks. Does not delete `.claude/docs/`.

## Key Design Decisions

- Embeddings use ChromaDB's built-in `all-MiniLM-L6-v2` (ONNX) — no PyTorch dependency
- `save_doc` no longer calls `index_document()` directly; the `DocWatcher` handles indexing on file change, so docs written via Edit/Write tools are also indexed
- The stop hook uses a `/tmp/claude-docs-reminded-{session_id}` marker file to fire only once per session
- `search_docs` is regex-based keyword search; `semantic_search_docs` is vector similarity — both exist because they complement each other
