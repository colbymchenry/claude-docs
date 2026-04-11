---
updated: 2026-04-10
---

# Beads CLI Removal — COMPLETED

The Beads CLI (`bd`) and all references have been fully removed from the codebase as part of the Kommandr rebrand. This doc is retained for historical context only.

## What Was Done

- Deleted: `beads-manager.ts`, `beads-cli.ts`, `beads-instructions.ts`, `mcp/beads-server.mjs`, beads API routes
- Created: `kommandr-instructions.ts` with `kommandr_*` MCP tool names
- All paths updated: `~/.kommandr/`, `.kommandr/adapter.json`, `.kommandr/kommandr.db`
- PostgreSQL triggers renamed from `beads_*` to `kommandr_*`
- All UI strings, test files, docs, and electron source renamed from "Beads" to "Kommandr"
- Pre-existing TypeScript errors fixed (was 8, now 0)

## Kommandr MCP Tool Names

- `kommandr_create` — create an issue
- `kommandr_list` — list issues
- `kommandr_show` — view issue details
- `kommandr_update` — update status/priority
- `kommandr_close` — close an issue
- `kommandr_dep_add` — add dependency
- `kommandr_dep_tree` — show dependency tree
- `kommandr_epic_status` — epic progress

Standard Scrum terminology for work items: epics, tasks, subtasks, bugs, features, stories, spikes.
