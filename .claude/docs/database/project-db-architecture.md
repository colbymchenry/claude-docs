---
updated: 2026-04-13
---

# Project Database Architecture

## Overview

The dashboard uses two database layers with different coupling levels:

- **ProjectStore interface** (`src/lib/stores/project-store.ts`) — async interface for per-project data, with pluggable backends
- **Dashboard DB** (`dashboard-db.ts`) — global SQLite at `~/.kommandr/dashboard.db`, schema self-initialized
- **Session DB** (`session-db.ts`) — uses the dashboard DB connection, manages session/event tables

## ProjectStore Interface (Phase 0 + Phase 1)

All methods are **async** (`Promise<T>`) to support both synchronous (SQLite) and asynchronous (PostgreSQL, etc.) backends.

### Key Files
- `src/lib/stores/project-store.ts` — interface definition
- `src/lib/stores/sqlite-store.ts` — SQLite implementation (default)
- `src/lib/stores/postgresql-store.ts` — PostgreSQL implementation
- `src/lib/stores/index.ts` — factory + cache + adapter.json reader + lazy proxy for non-SQLite adapters

### Factory: `getProjectStore(projectPath)`

Returns a cached `ProjectStore` for the given path. On first call:
1. Reads `<project>/.kommandr/adapter.json` (if it exists)
2. Resolves `${env:VAR_NAME}` placeholders in config values
3. Instantiates the appropriate backend (defaults to SQLite if no adapter.json)

```json
// Example .kommandr/adapter.json for PostgreSQL
{
  "adapter": "postgresql",
  "config": {
    "host": "db.example.com",
    "port": 5432,
    "database": "kommandr",
    "user": "kommandr_app",
    "password": "${env:KOMMANDR_PG_PASSWORD}"
  }
}
```

### Adding a new ProjectStore method

When you add a method to the interface, you must update **all** of these in lockstep or the build breaks:

1. `src/lib/stores/project-store.ts` — interface signature
2. `src/lib/stores/sqlite-store.ts` — SQLite implementation
3. `src/lib/stores/postgresql-store.ts` — PostgreSQL implementation (call `await this.ensureSchema()` first)
4. `src/lib/stores/index.ts` — add to the lazy proxy in `createLazyProxy()` (otherwise PG adapters hit a missing-method error)

### Consumer Files (update ALL when interface changes)
1. `src/routes/api/projects/+server.ts` — `getProjectCounts()`
2. `src/routes/api/projects/[id]/+server.ts` — `getProjectCounts()`
3. `src/routes/api/projects/[id]/issues/[issueId]/+server.ts` — CRUD operations
4. `src/routes/api/projects/[id]/stream/+server.ts` — SSE subscription loop (heaviest consumer)
5. `src/lib/task-runner-manager.ts` — task execution, epic sequencing, status polling
6. `src/lib/check-done-manager.ts` — issue detail lookup
7. `src/routes/api/projects/[id]/task-runner/+server.ts` — calls `startTaskRun()` (async)

### SQLite Backend (`SqliteProjectStore`)
- Uses `better-sqlite3` (synchronous under the hood, async methods resolve immediately)
- WAL mode, single connection per project
- Schema created on first instantiation by `SqliteProjectStore` constructor (also used by `init-kommandr` route during project initialization)
- Change detection: `PRAGMA data_version` + manual `changeCounter`

### PostgreSQL Backend (`PostgresProjectStore`)
- Uses `pg` (node-postgres) with connection pooling (`pg.Pool`, default 10 connections)
- Schema auto-created on first query via `CREATE TABLE IF NOT EXISTS`
- Tables: `issues`, `dependencies`, `comments`, `events`, `labels` with indexes
- LISTEN/NOTIFY triggers on all tables for real-time change detection
- Uses `ANY($1)` arrays instead of SQLite's `IN (?,?,?)` for array params
- `getAllDescendantIssues()` uses recursive CTE (more efficient than SQLite's JS recursion)
- Change detection: `txid_current_snapshot()` + manual `changeCounter`
- Foreign keys declared with `ON DELETE CASCADE`

### Key Query Patterns
- `getIssueWithDetails()` — fetches issue + blockers + blocked_by + children (sorted) + parent + comments + blocking relations
- `getChildIssuesSorted(epicId)` — topological sort via Kahn's algorithm (in-memory JS, both backends). Priority breaks ties (lower number = higher priority). Returns disconnected/cycle tasks appended by priority.
- `getChildBlockingRelations(epicId)` — returns `{source, target}[]` for a single epic's children (edges where `source` blocks `target`)
- `getAllBlockingRelations()` — returns all `type='blocks'` edges project-wide with both ends not `deleted_at`. Shipped in the SSE stream payload so clients can do per-epic toposort without per-epic fetches.
- All queries filter `deleted_at IS NULL`
- Deletes through UI use `deleteIssueViaCli()` for proper JSONL tombstones

### Change Detection & SSE Broadcasting
- `getDataVersion()` — returns a version number for change detection
- `notifyChange()` — increments manual counter (sync, not async)
- `refresh()` — no-op for both backends (SQLite single-conn sees own writes; PG pool sees latest commits)
- `subscribe(collection, callback)` — push-based change notification. SQLite polls internally; PostgreSQL uses `LISTEN/NOTIFY`. Consumer refetches on each event.
- `/api/projects/[id]/stream` uses `store.subscribe('issues' | 'events' | 'dependencies' | 'comments', ...)` — no setInterval. Refresh calls are coalesced via a `processing` / `pending` flag so concurrent change bursts collapse into a single broadcast.

### SSE stream payload (`/api/projects/[id]/stream`)

The stream sends `init` once, then `update` on every coalesced change. Both payloads include:

- `project` (init only): `{ id, name, path }`
- `issues: Issue[]` — all non-deleted issues
- `events: Event[]` — recent audit events (50 for init, new-since-last for update)
- `blockingRelations: BlockingRelation[]` — all `type='blocks'` edges project-wide. Used by `EpicsView` to topologically sort each epic's children on the client so ordering matches the Task Runner's execution order.
- `dataVersion: number`

Client consumer is `src/lib/project-stream.svelte.ts` (`createProjectStream`), which exposes each field as a reactive `$state` getter.

Type: `StreamMessage` in `src/lib/types.ts`.

## Project Initialization Flow (Add Project)

When a user adds a project that doesn't have `.kommandr/` set up:

1. `AddProjectForm` validates path via `POST /api/projects/validate`
2. `validateProjectPath()` checks for `.kommandr/kommandr.db` — returns `needsInit: true` if missing
3. UI shows "Initialize Project?" prompt with a **Storage Backend** dropdown (connectors loaded from `GET /api/connectors`)
4. User picks a connector (or defaults to "Local SQLite") and clicks Initialize
5. `POST /api/projects/init-kommandr` creates `.kommandr/` directory:
   - **SQLite (default):** Instantiates `SqliteProjectStore` to create the db + schema, then closes it
   - **Connector selected:** Calls `writeAdapterJson()` to write `.kommandr/adapter.json` with the connector's config
6. `POST /api/projects` adds the project to the dashboard DB; if `connectorId` provided, calls `assignConnectorToProject()` to set the FK

### Key: `init-kommandr` route
- File: `src/routes/api/projects/init-kommandr/+server.ts`
- Accepts `{ path, connectorId? }` — creates `.kommandr/` dir + storage backend
- Returns `{ success: true }` or `{ success: false, error: string }`

## Connectors (Dashboard DB)

Connectors are reusable database connection configs stored in `~/.kommandr/dashboard.db`.

### Tables
- `connectors` — id (UUID), name (UNIQUE), adapter_type, config (JSON), credentials (JSON), timestamps
- `projects.connector_id` — FK to `connectors(id) ON DELETE SET NULL`

### Key Functions in `dashboard-db.ts`
- `getAllConnectors()` — returns connectors with their linked projects
- `getConnectorForProject(projectId)` — JOIN query
- `assignConnectorToProject(projectId, connectorId | null)` — sets/clears the FK
- `writeAdapterJson(projectPath, connector)` — writes `.kommandr/adapter.json` (merges config + credentials)
- `removeAdapterJson(projectPath)` — deletes adapter.json (reverts to SQLite)

## Dashboard DB (`src/lib/dashboard-db.ts`)

### Tables
- `projects` — id (UUID), name, path (UNIQUE), added_at, last_accessed, dev_config (JSON), icon_path, connector_id (FK)
- `connectors` — id (UUID), name (UNIQUE), adapter_type, config (JSON), credentials (JSON), timestamps
- `notifications` — id (UUID), type, title, body, project_id, question fields, read/dismissed/answered flags
- `sessions` — id (UUID), project_id, issue fields, mode, status, epic progress (JSON), timestamps, archived
- `session_events` — id (UUID), session_id (CASCADE), seq, type, content (10KB cap), tool fields (5KB cap)

### Real-Time: Push + Poll Hybrid
- `sseControllers: Set<ReadableStreamDefaultController>` — registered clients
- `notifyDashboardChange(tables: string[])` — pushes SSE immediately on write
- Safety-net poll every 2 seconds
- Dashboard DB remains local SQLite — NOT pluggable (user-specific state)

## Shutdown
- `closeAllProjectStores()` is **async** — called with `await` in `src/lib/shutdown.ts`
- `closeProjectStore(path)` also async
- `closeDashboardDb()` remains sync
