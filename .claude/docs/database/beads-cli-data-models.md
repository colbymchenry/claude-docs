---
updated: 2026-04-09
---

# Beads CLI Data Models & Storage Architecture

Source: `/Users/colby/Downloads/beads-main` (Go codebase)

## Issue Model (`internal/types/types.go`)

Full field set (dashboard currently uses a subset):

### Core Fields
- `id` (hash-based, e.g. `bd-a1b2`), `title`, `description`, `design`, `acceptance_criteria`, `notes`, `spec_id`

### Status & Workflow
- `status`: open, in_progress, blocked, deferred, closed, pinned, hooked
- `priority`: 0-4 (P0=critical to P4=backlog)
- `issue_type`: bug, feature, task, epic, chore, decision, message, spike, story, milestone, molecule

### Assignment
- `assignee`, `owner` (human for CV attribution)
- `estimated_minutes`

### Timestamps
- `created_at`, `created_by`, `updated_at`, `closed_at`, `close_reason`, `closed_by_session`
- `due_at`, `defer_until`

### Advanced
- `labels[]`, `dependencies[]`, `comments[]`, `metadata` (arbitrary JSON)
- `ephemeral` (local-only wisps), `no_history`
- `external_ref` (link to GitHub, Jira, etc.)
- `await_type`, `await_id`, `timeout`, `waiters[]` (async coordination gates)

## Dependency Types (19 well-known)
- **Blocking:** blocks, parent-child, conditional-blocks, waits-for
- **Association:** related, discovered-from
- **Graph:** replies-to, relates-to, duplicates, supersedes
- **Entity:** authored-by, assigned-to, approved-by, attests
- **Delegation:** delegated-from (cascading completion)
- **Other:** tracks (convoy), until (time-based), caused-by, validates

Dashboard currently only uses `blocks` and `parent-child`.

## Storage Backend: Dolt

Beads CLI uses Dolt (Git-like versioned SQL database):
- **Embedded mode** (default): in-process, `.beads/embeddeddolt/`, single writer
- **Server mode**: external `dolt sql-server` on port 3307, MySQL protocol, multi-writer

## Storage Interface (`internal/storage/`)

Well-abstracted in Go with composable interfaces:
- `Storage` — base CRUD for issues, dependencies, labels, comments
- `VersionControl` — branch, checkout, commit, merge, log, status
- `HistoryViewer` — time-travel (History, AsOf, Diff)
- `RemoteStore` — remote management, push/pull/fetch
- `SyncStore` — peer sync with conflict resolution
- `FederationStore` — peer management with sovereignty tiers (T1-T4)
- `BulkIssueStore` — batch operations
- `DependencyQueryStore` — 16 extended dependency query methods
- `CompactionStore` — semantic memory decay
- `RunInTransaction(ctx, message, callback)` — atomic multi-operation

## Sync Mechanisms
- **Write path:** CLI command → Dolt write → auto-commit → push on demand
- **Read path:** CLI query → optional pull → Dolt SQL query
- **Remote types:** DoltHub, GitHub (git+ssh), S3, GCS, local filesystem
- **Conflict resolution:** Cell-level merge (Dolt native), hash-based deduplication

## Team Features
- **Contributor isolation:** Auto-routing based on git role (SSH=maintainer→project DB, HTTPS=contributor→personal DB)
- **Federation:** Peer-to-peer with sovereignty tiers
- **Async gates:** await_type (gh:run, gh:pr, timer, human, mail) with timeout/escalation
- **Molecules:** Reusable workflow templates (proto→mol→wisp→digest lifecycle)
- **Wisps:** Ephemeral local-only issues for temporary work

## Dashboard vs CLI Field Gap
The dashboard's `project-db.ts` uses a subset of the full Beads model. Notable fields NOT in the dashboard schema:
- `design`, `acceptance_criteria`, `notes`, `spec_id`
- `owner`, `estimated_minutes`
- `due_at`, `defer_until`
- `labels` (table exists in CLI but queries not in dashboard)
- `metadata`, `external_ref`
- `ephemeral`, `no_history`
- All async coordination fields (await_type, etc.)
- 17 of 19 dependency types (only blocks + parent-child used)