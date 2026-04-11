---
updated: 2026-04-09
---

# Session Persistence System

Added 2026-04-09. Persists task/epic execution sessions to `~/.beads-dashboard/dashboard.db` for history browsing.

## Architecture

**Write path:** `task-runner-store.ts` → persistence callbacks → `session-db.ts` → SQLite

The store fires callbacks on mutations (create, status change, event add, epic progress). `session-persistence.ts` wires these to `session-db.ts` CRUD functions. Errors in persistence never block the in-memory store.

**Read path:** `/api/sessions` → `session-db.ts` → SQLite → SideNav + Session detail page

## Key Files

| File | Purpose |
|------|---------|
| `src/lib/session-db.ts` | CRUD for sessions/session_events tables |
| `src/lib/session-persistence.ts` | Wires store callbacks to session-db (auto-inits on import) |
| `src/lib/task-runner-store.ts` | Added `setPersistenceCallbacks()` and callback invocations |
| `src/lib/task-runner-manager.ts` | Imports session-persistence to trigger init |
| `src/routes/api/sessions/+server.ts` | GET list, DELETE bulk cleanup |
| `src/routes/api/sessions/[id]/+server.ts` | GET detail with events, DELETE single |
| `src/components/SessionTimeline.svelte` | Horizontal timeline bar with clickable task segments |
| `src/components/SessionEventLog.svelte` | Event log with task group headers, tool call rendering |
| `src/routes/(protected)/sessions/[id]/+page.svelte` | Session detail page |
| `src/components/SideNav.svelte` | Added Sessions section between Dashboard and Projects |

## DB Tables (in dashboard.db)

- `sessions` — one row per task/epic run (id matches TaskRun.id)
- `session_events` — events with `seq` ordering, `epic_task_id` for task grouping

Content truncation: 10KB for content, 5KB for tool_input/tool_result JSON (constants in `constants.ts`).

## Sidenav Integration

Sessions section appears between Dashboard and Projects when sessions exist. Shows up to 8 sessions, active ones first. Polled every 15 seconds alongside projects. Each item links to `/sessions/{id}`.
