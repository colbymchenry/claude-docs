---
updated: 2026-04-14
---

# socket-io-architecture

---
updated: 2026-04-14
---

## Purpose

All real-time server → client streaming uses **socket.io over a single multiplexed WebSocket**. One `Manager` per browser tab, 9 namespaces, rooms per entity. Replaces fetch-based SSE entirely (no legacy SSE streams remain as of 2026-04-14). The multiplexed WebSocket sidesteps Chromium's 6-per-origin HTTP/1.1 connection limit that used to saturate with 5+ concurrent SSE streams and hang API calls.

## Server Attachment — How socket.io Meets SvelteKit

SvelteKit's `adapter-node` default entry (`build/index.js`) constructs and listens on the HTTP server internally, giving us no way to attach socket.io to it. We replace that entry with a thin Node wrapper.

### File layout

- `server/custom-server.mjs` — checked into the repo; the actual runtime entry point
- `build/custom-server.mjs` — copied from `server/` by a Vite `closeBundle` plugin (`copyCustomServerPlugin` in `vite.config.js`) after every `npm run build`
- `build/handler.js` — emitted by `@sveltejs/adapter-node`; the raw Node request handler for SvelteKit

The wrapper:

1. Creates `http.Server` manually
2. Constructs `new IOServer(httpServer, { cors, transports })`
3. Stashes the IO instance on `globalThis.__KOMMANDR_IO__`
4. Imports `./handler.js` and wires it as the HTTP request listener
5. Calls `httpServer.listen(PORT, HOST, ...)`

### Why `globalThis` as the handoff

`custom-server.mjs` runs at Node runtime and isn't processed by Vite. SvelteKit's SSR bundle (including `hooks.server.ts` and all `$lib/*` imports) is loaded lazily when the first request arrives at `handler.js`. There is no direct import path between the two worlds — `custom-server.mjs` can't import `$lib/server/socket-server.ts`, and SSR code can't import the running `io` instance.

`globalThis` is the shared escape hatch. It's typed in `src/lib/server/socket-server.ts`:

```typescript
declare global {
  var __KOMMANDR_IO__: IOServer | undefined;
  var __KOMMANDR_IO_INITIALIZED__: boolean | undefined;
}
```

Emit sites call `getIO()` which returns the global or `undefined`. Every emit must tolerate `undefined` — a tests/SSR probe context may load the SSR bundle without socket.io attached.

### Namespace registration

Namespace handlers (connection listeners, room management, auth middleware) live in `$lib/server/*` and need SSR-bundle context. They're registered from SvelteKit's **`init` hook** in `src/hooks.server.ts`:

```typescript
export const init: ServerInit = async () => {
  const io = getIO();
  if (io) await initNamespaces(io);
};
```

The `init` hook fires once when the SSR bundle loads (on the first HTTP request to SvelteKit). By that point `custom-server.mjs` has already attached socket.io and set `globalThis.__KOMMANDR_IO__`, so `getIO()` resolves and we wire up the 9 namespaces.

`initNamespaces` is idempotent (guarded by `globalThis.__KOMMANDR_IO_INITIALIZED__`) because in dev both Vite's `configureServer` plugin and the SvelteKit init hook can race to attach handlers after HMR.

### Dev-mode parity

`npm run dev` doesn't use `custom-server.mjs` — Vite owns the HTTP server. The `socketIoDevPlugin` in `vite.config.js` mirrors the wiring:

```javascript
configureServer(server) {
  if (globalThis.__KOMMANDR_IO__) return;
  const io = new IOServer(server.httpServer, { cors, transports });
  globalThis.__KOMMANDR_IO__ = io;
  server.httpServer.on('close', () => { io.close(); ... });
}
```

Both paths set the same global, so `hooks.server.ts` `init` treats dev and prod identically.

## Electron-builder Gotcha

`server/custom-server.mjs` is **not bundled by Vite**. Its `import { Server as IOServer } from 'socket.io'` is a runtime import resolved against `node_modules/`. In packaged Electron builds the server runs from `Resources/server/`, so socket.io + its transitive deps must be shipped there as real npm packages.

`electron-builder.yml` has explicit `extraResources` entries for every transitive dep. The full list lives in the config; when you touch socket.io versions, re-check that the set is complete. Current entries:

```
socket.io, socket.io-adapter, socket.io-parser, engine.io, engine.io-parser,
ws, accepts, base64id, cors, debug, ms, mime-types, mime-db, negotiator,
vary, object-assign, cookie, @socket.io/*, @types/cookie, @types/cors, @types/node
```

Symptoms if this set is incomplete: `Cannot find module 'ms'` (or similar) from the packaged server process at startup.

## Namespace Map

Defined in `src/lib/socket-events.ts` (`NAMESPACES` constant). All 9 are migrated:

| Namespace | Room key | Auth | Handler module | Client-to-server event |
|---|---|---|---|---|
| `/project` | projectId | required | `project-namespace.ts` | `join { projectId }`, `leave` |
| `/chat` | sessionId | required | `chat-namespace.ts` | `join { sessionId }`, `leave` |
| `/helper-chat` | sessionId | required | `chat-namespace.ts` | `join { sessionId }`, `leave` |
| `/task-runner` | runId | required | `task-runner-namespace.ts` | `join { runId, skipHistory? }`, `leave` |
| `/scaffold` | sessionId | **anon ok** | `scaffold-namespace.ts` | `join { sessionId }`, `leave` |
| `/active-tasks` | global | required | `socket-namespaces.ts` | none |
| `/notifications` | global | required | `socket-namespaces.ts` | none |
| `/dashboard` | global | required | `socket-namespaces.ts` | none |
| `/dev-server` | projectId | required | `dev-server-namespace.ts` | `join { projectId }`, `leave` |

`sessionId` / `runId` / `projectId` come from the `join` event payload, **not** handshake auth. That lets a single long-lived socket per tab switch rooms (e.g. navigate between projects, swap chat sessions) without disconnecting.

Auth middleware is installed per-namespace by `installAuthMiddleware(ns, { requireAuth })`. It currently accepts any connection because the server only listens on 127.0.0.1 (Electron same-origin); Firebase token verification is stubbed pending full auth wire-up.

## Server-to-Client Event Shapes

Each namespace has its own event name, but several of the per-entity namespaces (`/task-runner`, `/scaffold`, `/dev-server`) emit a **single `event` channel** whose payload carries a tagged `type` field (the exact shape the old SSE streams put inside `data: {...}\n\n`). That keeps the client-side switch statements identical to what they were when reading SSE chunks:

- `/task-runner` `event`: `{ type: 'connected' | 'state' | 'event' | 'status' | 'epic_progress' | 'awaiting_input' | 'error', ... }`
- `/scaffold` `event`: `{ type: 'init' | 'text' | 'tool_use' | 'tool_result' | 'status' | 'done' | 'error', ... }`
- `/dev-server` `event`: `{ type: 'init' | 'output' | 'ready' | 'preview-url' | 'exit' | 'error' | 'heartbeat', ... }`

`/chat` and `/helper-chat` instead use a named `chunk` event — the payload is a raw `ProviderOutputChunk` from the adapter, same as what SSE used to wrap. The server also emits the legacy `{ type: 'connected', sessionId, agentName, messageCount }` + a stream of `{ type: 'history', message }` chunks as the initial hydration prelude on join.

## /chat vs /helper-chat Broadcast Routing

There is ONE `chat-manager.ts` that handles both regular chat and helper chat (ExplanationChat). Broadcasts are routed to the right namespace by a tag:

```typescript
// In src/lib/chat-manager.ts
export function markHelperSession(sessionId: string): void { ... }

// In broadcastToSession:
const nsPath =
  sessionNamespace.get(sessionId) === 'helper-chat'
    ? NAMESPACES.HELPER_CHAT
    : NAMESPACES.CHAT;
io.of(nsPath).to(sessionId).emit('chunk', chunk);
```

`markHelperSession(sessionId)` is called from `POST /api/projects/[id]/chat` when the request body has `helper: true`. The helper-session-store client passes `helper: true` automatically. Regular `ChatSheet` calls to the same endpoint omit it.

This avoids duplicating chat-manager or requiring helper chat to connect to a different endpoint.

## Dev-Server Namespace EventEmitter Refcount

`dev-server-manager.ts` exposes an `EventEmitter` per project. The `/dev-server` namespace subscribes to it **once per project**, refcounted across multiple sockets in the same room:

- First socket to join a project → attach `output/ready/preview-url/exit/error` listeners + a 30s `heartbeat` interval, broadcast to the room.
- Last socket to leave → detach listeners + clear heartbeat.

Without refcounting, N tabs watching the same project would attach N duplicate listeners to the same emitter and fire each log line N times into the room.

## Client Singleton

`src/lib/socket.ts` owns the browser-side transport. One `Manager` per tab; each namespace reuses the underlying WebSocket via socket.io multiplexing.

Key rules:

1. **Browser-gated.** All exports no-op on SSR (`if (!browser) return null`). Safe to import from `+page` components.
2. **Call `getNamespace('/foo')` or `subscribe('/foo', event, handler)`** — never `new Socket(...)` directly.
3. **`subscribe()` returns an unsubscribe closure.** Always call it in `onDestroy` / `$effect` cleanup. Leaked handlers under HMR double-handle messages.
4. **`import.meta.hot.dispose`** tears down the Manager automatically to prevent doubled handlers on hot reload (wired in `socket.ts`).
5. **Auth token is provided as a function** passed to `mgr.socket(ns, { auth: (cb) => {...} })`. socket.io calls it on every reconnect, so expired Firebase tokens get refreshed automatically.

### Transport selection (Electron vs browser)

`transports: isElectron() ? ['websocket'] : ['websocket', 'polling']` — where `isElectron()` reads `window.electronAPI?.isElectron`. Electron runs on loopback Chromium where WebSocket is always available, and skipping polling prevents a specific wake-from-sleep failure mode where stranded polling sessions multiply connections. Browser mode keeps polling fallback for corporate-proxy edge cases.

### Reconnection tuning

```
reconnection: true
reconnectionAttempts: Infinity
reconnectionDelay: 500
reconnectionDelayMax: 8000
timeout: 20000
```

Retries forever with exponential backoff between 500ms and 8s. A fresh token is resolved on every handshake because `auth` is a function, not a static value.

### Auth-aware reconnect (Firebase token rotation)

`src/lib/socket.ts` keeps a per-namespace `forceTokenRefresh: Set<string>`. On any `connect_error` whose message matches `auth|token|unauthorized|forbidden`, the namespace is added to the set; the **next** handshake calls `user.getIdToken(true)` instead of `getIdToken()`, which bypasses the Firebase SDK cache and hits Firebase's token endpoint for a fresh token. After one successful use the flag is cleared. Non-auth connect errors fall through the normal reconnection schedule unchanged.

This is the path that recovers a tab whose Firebase ID token expired in the background (tokens rotate hourly) without a user-visible sign-out.

## Reconnect Rejoin Pattern

Socket.io drops room memberships when the underlying connection dies. Clients that joined a room must re-emit `join` on every `connect` event, not just the initial one. The canonical pattern (used by chat-session.svelte.ts, TaskRunnerPanel, LiveEditMode, CreateProjectWizard, helper-session-store, and project-stream):

```typescript
const onConnect = () => {
  connected = true;
  if (joinedId) socket.emit('join', { runId: joinedId /* or projectId/sessionId */ });
};
socket.on('connect', onConnect);
```

Without this, a wake-from-sleep reconnect leaves the client with an open socket but no room membership, and server-side broadcasts (scoped to the room) silently drop.

## Leave, Don't Disconnect, on Drawer Dismiss

When a UI surface closes (chat drawer, task runner panel, LiveEditMode dialog), the client should:

1. `socket.off(event, handler)` on every listener it registered
2. `socket.emit('leave')` to tell the server to remove this socket from the room

**Never** call `socket.disconnect()`. The Manager + socket are shared across the whole tab — other panels may still need them. The detach pattern is codified in the `detachDevSocket()` / `detachRunnerSocket()` / `detachSocket()` helpers inside LiveEditMode.svelte, TaskRunnerPanel.svelte, and chat-session.svelte.ts respectively. Follow that shape for new consumers.

## Resume Race: /chat (cross-restart)

For the `/chat` namespace specifically, cross-restart resume requires:

1. Client POSTs `/api/projects/[id]/chat/[sessionId]/resume` with `{ providerSessionId, provider, model, mode, agentFilename }`.
2. **Await the 200 response.**
3. **Then** call `getNamespace('/chat').emit('join', { sessionId })`.

If the client joins before `/resume` completes, the server has no in-memory session to validate against and emits an `error` chunk. See `chat-session-lifecycle` doc's "Cross-Restart Persistence" section for the full sequence.

## Emit-Site Pattern

Server-side emit sites follow this shape:

```typescript
import { getIO } from '$lib/server/socket-server';
import { NAMESPACES } from '$lib/socket-events';

const io = getIO();
io?.of(NAMESPACES.DASHBOARD).emit('update', { ... });
io?.of(NAMESPACES.TASK_RUNNER).to(runId).emit('event', msg);
```

`io?` because `getIO()` returns `undefined` in contexts where socket.io isn't attached. Never throw from an emit site — emit failures should degrade gracefully.

## Server-Side Error Logging

Per-namespace `connection` handlers in each `*-namespace.ts` log disconnect events with reason via the `socket` logger category:

```typescript
socket.on('disconnect', (reason) => {
  log.debug(`${ns.name}: disconnected`, { id: socket.id, reason });
});
```

Engine-level failures (handshake rejections, malformed frames, transport upgrades that fail before they reach a namespace) are logged in `socket-namespaces.ts` via:

```typescript
io.engine.on('connection_error', (err) => {
  log.warn('engine connection_error', { code: err.code, message: err.message, context: err.context });
});
```

This is the catch-all for connection failures that never hit a namespace middleware — useful when diagnosing why a particular client can't complete a handshake.

## Phase Status

All 8 phases complete as of 2026-04-14.

Phase 8 landed:
- `['websocket']`-only transports in Electron
- Playwright smoke test at `tests/e2e/socket-live-update.spec.ts` (out-of-band POST → kanban card appears via socket)
- `connect_error` → force `getIdToken(true)` on next handshake
- `io.engine.on('connection_error')` server-side logging
- CSP check (no meta CSP in `src/app.html`; nothing to add)
- New `docs/socket-connection-management.md` at repo root (plus this `.claude/docs/socket-io-architecture.md` which is the deeper developer reference)

See `SOCKETIO-MIGRATION.md` at repo root for the full rollout.

## Playwright Smoke Test

`tests/e2e/socket-live-update.spec.ts` launches the Electron app, navigates to the first available project, POSTs a new issue via `http://127.0.0.1:5555/api/projects/<id>/issues` with an `Origin: http://127.0.0.1:5555` header (required to pass `hooks.server.ts` CORS check), then asserts a kanban card with the POSTed title appears within 10 seconds. The card can only appear via the `/project` namespace's `update` event — a reload wouldn't be triggered. Cleanup DELETEs the issue best-effort so re-runs are idempotent.

Skips gracefully if no project exists in the user's local dashboard.

## Related Files

### Runtime entry + config
- `server/custom-server.mjs` — Node server wrapper
- `vite.config.js` — `socketIoDevPlugin`, `copyCustomServerPlugin`
- `electron-builder.yml` — ships socket.io + transitive deps as real `node_modules/`
- `electron/server-manager.ts` — spawns `custom-server.mjs`

### Server
- `src/lib/server/socket-server.ts` — `getIO()`, `initNamespaces()`, global handoff
- `src/lib/server/socket-namespaces.ts` — central namespace registration + auth middleware + engine-level error logging
- `src/lib/server/project-namespace.ts` — `/project` room handler
- `src/lib/server/chat-namespace.ts` — `/chat` + `/helper-chat` room handlers
- `src/lib/server/task-runner-namespace.ts` — `/task-runner` room handler
- `src/lib/server/scaffold-namespace.ts` — `/scaffold` room handler
- `src/lib/server/dev-server-namespace.ts` — `/dev-server` room handler w/ EventEmitter refcount
- `src/hooks.server.ts` — `init` hook that calls `initNamespaces`

### Client
- `src/lib/socket.ts` — browser-side Manager singleton (transports, reconnection, auth-aware refresh, HMR dispose)
- `src/lib/socket-events.ts` — typed event contracts + `NAMESPACES` const
- `src/lib/project-stream.svelte.ts` — `/project` consumer
- `src/lib/dashboard-stream.svelte.ts` — `/dashboard` consumer
- `src/lib/notification-stream.ts` — `/notifications` consumer
- `src/lib/active-tasks-store.ts` — `/active-tasks` consumer (server) + `GlobalTaskIndicator.svelte` (client)
- `src/lib/chat-session.svelte.ts` — `/chat` consumer (factory used by ChatSheet)
- `src/lib/helper-session-store.ts` — `/helper-chat` consumer w/ `subscribeHelperChunks` fan-out
- `src/components/TaskRunnerPanel.svelte` — `/task-runner` consumer
- `src/components/CreateProjectWizard.svelte` — `/scaffold` consumer
- `src/components/LiveEditMode.svelte` — `/dev-server` consumer

### Tests
- `tests/e2e/socket-live-update.spec.ts` — Phase 8 Playwright smoke test
