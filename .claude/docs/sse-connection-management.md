---
updated: 2026-04-14
---

# sse-connection-management

---
updated: 2026-04-14
---

# sse-connection-management

## Status — HISTORICAL. All SSE migrated to socket.io.

As of 2026-04-14, there are **no SSE streams remaining** for the real-time bus. The nine legacy `text/event-stream` endpoints have all been deleted in favor of socket.io namespaces. See `socket-io-architecture` for the replacement pattern.

| Original stream | Replacement |
|---|---|
| `/api/dashboard/stream` | `/dashboard` socket.io namespace |
| `/api/notifications/stream` | `/notifications` namespace |
| `/api/active-tasks/stream` | `/active-tasks` namespace |
| `/api/projects/[id]/stream` | `/project` namespace (rooms per projectId) |
| `/api/projects/[id]/chat/[sid]/stream` | `/chat` namespace (rooms per sessionId) |
| `/api/projects/[id]/task-runner/[runId]/stream` | `/task-runner` namespace (rooms per runId) |
| `/api/projects/create/scaffold/stream` | `/scaffold` namespace (rooms per sessionId, anon OK) |
| `/api/projects/[id]/dev-server/stream` | `/dev-server` namespace (rooms per projectId) |
| (helper chat shared `/chat/[sid]/stream`) | `/helper-chat` namespace — routed via `markHelperSession()` tag in chat-manager |

**Do not add new SSE endpoints.** All new real-time streams go through socket.io.

## Remaining `text/event-stream` — out of scope

Three `text/event-stream` endpoints are still in the codebase and are NOT part of the real-time bus:

- `src/routes/api/projects/[id]/claude-init/+server.ts`
- `src/routes/api/claude-code/update/+server.ts`
- `src/routes/api/claude-code/install/+server.ts`

These are **one-shot progress streams for long-running setup operations** (project init, Claude Code CLI install/update). They're consumed via `fetch().body.getReader()` in the exact UI surface that starts them, hold exactly one HTTP connection for the duration of the operation, and close when the operation finishes. They don't multiplex, don't reconnect, and don't contribute to the 6-per-origin pressure the migration was about. They can stay as SSE.

## The HTTP/1.1 Connection Limit Problem (why we migrated)

Chromium (used by Electron's BrowserWindow) enforces a maximum of **6 concurrent HTTP/1.1 connections per origin**. The SvelteKit server runs on `http://127.0.0.1:5555` (HTTP/1.1, not HTTP/2), so ALL fetch and SSE connections share this 6-connection pool.

SSE streams are long-lived — each occupied a slot for the duration it was open. With 5+ SSE streams open on a project page, only 0-1 slots remained for API calls, and subsequent `fetch()` calls were **queued indefinitely** by the browser with no error or timeout.

Socket.io uses a single WebSocket (one HTTP/1.1 upgrade) and multiplexes all namespaces over it. The 6-connection limit no longer applies because all streams collapsed onto it.

## Symptoms of the Old Failure Mode

If you see these symptoms with one of the remaining out-of-scope SSE endpoints above, it could be connection saturation — but most plausibly it's something else (socket.io not attached, auth issue, etc.):

- Chat message POST hangs (no response, no error)
- `curl` to the same endpoint works perfectly
- SSE streams appear connected (opened before the limit was hit)
- Server logs show no incoming request for the POST
- `~/.kommandr/hooks.log` shows stream GETs but no POST

## Historical Context (why this doc exists)

This issue was discovered when Codex chat integration appeared to work (session created, SSE connected, Codex process running) but message POSTs never reached the server. The Codex JSON-RPC protocol worked perfectly via curl but not from the browser. The root cause was 3 duplicate `EventSource('/api/notifications/stream')` connections from separate components, plus `EventSource` connections for dashboard, project, and active-tasks streams — totaling 8 connections against a limit of 6.

The fix was two-stage: (1) consolidate to fetch-based SSE with shared singletons, which got us down to 5 streams, then (2) migrate to socket.io entirely, which eliminates per-stream connection cost. Stage 2 is complete as of 2026-04-14; see `SOCKETIO-MIGRATION.md` at repo root for the migration history and `socket-io-architecture` doc for the current architecture.

## Rules That Still Apply

### NEVER use `EventSource`

`EventSource` creates HTTP/1.1 persistent connections that count toward the 6-per-origin limit, and it's harder to control than fetch-based SSE:
- No `AbortController` support
- Built-in auto-reconnect creates connections without your control
- Cannot share headers or credentials easily

The three remaining one-shot progress streams use `fetch().body.getReader()`, not `EventSource`. Follow that pattern if you ever add another one-shot progress stream.

### Abort on navigation

One-shot progress streams must be aborted if the user navigates away mid-operation. Pattern:

```typescript
const controller = new AbortController();
const response = await fetch('/api/...', { signal: controller.signal });
// ... read loop ...

// In cleanup:
controller.abort();
```
