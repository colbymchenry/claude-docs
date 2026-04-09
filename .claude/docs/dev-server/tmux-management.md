---
updated: 2026-04-08
---

# Dev Server Management (tmux-based)

## Overview

Dev servers run inside **tmux sessions**, not as direct child processes. This gives session persistence (survives app restarts), automatic reattach, and eliminates the old port conflict modal flow.

Core file: `src/lib/dev-server-manager.ts`

## tmux Session Lifecycle

### Session Naming
```
beads-dev-<projectId>   (non-alphanumeric chars stripped)
```

### Starting a Server
1. Check if tmux session `beads-dev-<id>` already exists → reattach if so
2. Check if port is free → if busy, auto-find next available port (no user prompt)
3. `tmux new-session -d -s <name> -c <projectPath> '<env> <devCommand>'`
4. `tmux pipe-pane -t <name> -o 'cat >> "<logFile>"'` — captures output to file
5. `tail -f <logFile>` — Node child process tails the log for real-time streaming
6. EventEmitter emits `output`, `ready`, `error`, `exit` events (same as before)
7. Port polling runs as backup ready detection

### Log Files
```
~/.beads-dashboard/logs/dev-servers/<projectId>.log
```
Created fresh on each server start. Pipe-pane appends all tmux pane output.

### Stopping a Server
1. `tmux send-keys -t <name> C-c` — graceful Ctrl+C
2. Wait 3 seconds
3. `tmux kill-session -t <name>` — force kill if still alive

### Reattaching to Orphaned Sessions
If the app restarts but a tmux session still exists from a prior run:
- Re-enables `pipe-pane` on the existing session
- Loads existing log file content into output buffer
- Checks if port is already responding (marks as ready immediately)
- Starts session liveness monitor

### Session Liveness Monitor
Every 3 seconds, checks `tmux has-session -t <name>`. If session is gone, emits `exit` and cleans up.

## Status Detection & Port Validation

`getServerStatus(projectId, configPort?)` is **async** and validates liveness by checking the port:

1. If tmux session exists and port is **free** → server process died, tmux is stale. Kills the tmux session, cleans up, returns `running: false`.
2. If tmux session exists, no in-memory session, but port is **occupied** → orphaned but live. Returns `running: true, ready: true, logsAvailable: false`.
3. If tmux session exists with in-memory session → returns full status from session state.

The `configPort` parameter is needed for orphaned sessions where there's no in-memory session to get the port from. All API callers pass `config.defaultPort`.

### `logsAvailable` Flag

- `true` = fully tracked in-memory session with EventEmitter and tail watcher
- `false` = orphaned tmux session, no stream/emitter available yet

This flag drives the reattach flow:
- **Start endpoint** (`/dev-server/start`): Only short-circuits with `alreadyRunning` if `logsAvailable` is true. If false, falls through to `startDevServer()` → `reattachToExistingSession()` to rebuild in-memory state.
- **LiveEditMode**: If status is `running` but `logsAvailable` is false, calls `startServer()` to trigger reattach before attempting stream connection.

### Stale Session Cleanup

Previously, the dashboard could show "Stop Server" for a server that had actually died (tmux session existed but process was dead). Now `getServerStatus` proactively cleans these up by checking the port — if free, the tmux session is killed and removed.

## Shopify Preview URL

Shopify CLI output contains preview URLs with ANSI escape codes (e.g. `\x1B[22m`). The output is stripped of ANSI codes before regex matching via `SHOPIFY_PREVIEW_PATTERN`.

The preview URL always uses `http://localhost:<port>` for all frameworks including Shopify. The Shopify CLI runs a local proxy, so `localhost` is correct for iframe preview. The remote Shopify URL (e.g. `https://store.myshopify.com/?preview_theme_id=...`) is stored on the session but not used for preview display.

## Data Flow

1. User enters Live Edit → `LiveEditMode.svelte` calls `checkAndStartServer()`
2. Checks `GET /dev-server/status` — validates port liveness
3. If running + `logsAvailable`: connects to SSE stream directly
4. If running + NOT `logsAvailable` (orphaned): calls `POST /dev-server/start` to reattach, which rebuilds in-memory session, then connects to stream
5. If not running: `POST /dev-server/start` creates new tmux session
6. `GET /dev-server/stream` SSE endpoint subscribes to EventEmitter (fed by `tail -f`)
7. Ready detection via stdout pattern matching + port polling fallback

## Polling Intervals

- **Project page status check**: every 2 seconds (`+page.svelte`)
- **Ready timeout in LiveEditMode**: 2 seconds — if server reports running but not ready after this, it restarts
- **Session liveness monitor**: every 3 seconds

## What Was Removed (April 2026)

The following were eliminated when switching to tmux:

- **PortConflictModal** (`src/components/PortConflictModal.svelte`) — deleted. Port conflicts are auto-resolved by finding the next available port.
- **External server attachment** — `attachToExternalServer()`, `detachFromExternalServer()`, `AttachedServer` interface, liveness polling for external processes
- **API routes**: `dev-server/attach/+server.ts`, `dev-server/kill-port/+server.ts`
- **Port conflict types**: `PortConflictInfo`, `KillPortResult`
- **`dev-server-state.svelte.ts`** simplified — removed `resolvePortConflict()`, `cancelPortConflict()`, `externalRunning`, `externalProcessInfo`, `showPortConflictModal`, `timeWaitError`

## Key Interfaces

```typescript
interface ServerStatus {
  running: boolean;
  pid?: number;
  port?: number;
  startedAt?: string;
  ready: boolean;
  previewUrl?: string;
  error?: string;
  tmuxSession?: string;    // tmux session name
  logsAvailable: boolean;  // true = fully tracked, false = orphaned
}
```

## Requires

- `tmux` must be installed on the host machine (verified: `tmux 3.6a` on macOS via Homebrew)
