---
updated: 2026-04-08
---

# claude-docs MCP Server Architecture

## Overview

Python MCP server that provides Claude with persistent, project-specific documentation management with semantic search. Stores plain markdown files in `.claude/docs/` with ChromaDB vector embeddings for similarity search.

## Tech Stack

- **Language**: Python 3
- **Framework**: `FastMCP` (from `mcp.server.fastmcp`)
- **Embeddings**: ChromaDB with built-in `all-MiniLM-L6-v2` (ONNX, no PyTorch)
- **Source**: Single file `server.py` (~630 lines)
- **CLI query tool**: `query.py` — standalone semantic search for use in hooks/scripts

## Tools Exposed

| Tool | Purpose |
|------|---------|
| `list_docs()` | Tree listing of all docs with metadata. Auto-inlines all `workflow/` docs. |
| `lookup_doc(topic)` | Retrieve doc by topic with fuzzy matching (exact → case-insensitive → substring → path segment). Warns if doc >60 days stale. Validates `[[wiki-links]]`. |
| `save_doc(topic, content)` | Create/update doc. Auto-manages YAML frontmatter with `updated: YYYY-MM-DD`. Re-indexes embeddings. Returns previous content if overwriting. |
| `search_docs(query)` | Full-text regex search across all docs. Case-insensitive with context lines. |
| `semantic_search_docs(query, n_results)` | Vector similarity search via ChromaDB. Finds conceptually related content even when keywords don't match. Similarity threshold 0.25. |
| `delete_doc(topic)` | Remove doc and its embeddings. Cleans up empty parent directories. |

## Storage

- **Docs**: `.claude/docs/` (relative to project root, committed to git)
- **Embeddings**: `.claude/docs/.embeddings/` (ChromaDB persistent client, gitignored)
- **Format**: Markdown with optional YAML frontmatter (`updated` field)
- **Topic paths**: Map to filesystem — `database/schema` → `.claude/docs/database/schema.md`
- **Project root**: Detected by looking for `.git` or `CLAUDE.md`

## Chunking Strategy

Documents are split by markdown headers (`##`, `###`) for embedding. Each chunk is prefixed with its topic + header hierarchy for context (e.g., `"auth/flow > OAuth > Token refresh: ..."`). Documents without headers are embedded as a single chunk. Frontmatter is stripped before chunking.

## Embedding Lifecycle

- `save_doc()` automatically re-chunks and re-indexes the document
- `delete_doc()` removes all chunks for the topic from ChromaDB
- On server startup, `_auto_index_if_needed()` bootstraps embeddings if the collection is empty but docs exist on disk
- CLI: `python server.py --index [project-dir]` rebuilds all embeddings

## query.py — CLI Semantic Search

Standalone script for use in hooks and scripts that don't have MCP access:

```bash
# Via stdin
echo "how does auth work" | uv run --directory /path/to/claude-docs python query.py --project-dir /path/to/project

# Via --prompt flag
uv run --directory /path/to/claude-docs python query.py --prompt "auth flow" --project-dir /path/to/project
```

Returns concise `- [topic > header] snippet...` lines. Used by the `memory-on-prompt.sh` UserPromptSubmit hook to inject relevant docs into prompts.

## Installation & Hooks

- MCP server registered in `~/.claude/settings.json` under `mcpServers.claude-docs`
- **Stop hook** (`~/.claude/hooks/claude-docs-stop.sh`): Fires once per session, reminds Claude to document findings using `save_doc()`
- **Limitation**: The stop hook assumes MCP tools are available. In sessions spawned without the claude-docs MCP server (e.g., dashboard-spawned sessions), the hook fires but Claude cannot call `save_doc()`.

## Known Limitation: Non-MCP Sessions

Sessions that don't load the claude-docs MCP server (e.g., those spawned by the beads-live-dashboard with `--strict-mcp-config`) can read docs via filesystem tools (grep/read on `.claude/docs/`) and get semantic matches injected via the UserPromptSubmit hook + `query.py`, but cannot save new docs. Potential solutions: modify the stop hook to use Write tool + CLI re-index, add a CLI save command to `query.py`, or pass the MCP config to those sessions.