---
updated: 2026-04-12
---

# SvelteKit Server Subprocess Crash Diagnostics

The packaged Electron app spawns the SvelteKit server as a child process via `electron/server-manager.ts`. When that subprocess dies, the symptom is distinctive and the existing logging has a gap — this doc captures both, plus the known trigger pattern (system sleep/wake).

## Known trigger: macOS sleep/wake with open SSE streams

Observed console sequence (confirmed from live devtools, 2026-04-12):

1. `GET /api/notifications ... net::ERR_NETWORK_IO_SUSPENDED` — macOS suspended the renderer's network stack (system sleep, lid close, or long backgrounding).
2. `SSE stream error: TypeError: network error` on every open stream.
3. Client reconnects → `net::ERR_INCOMPLETE_CHUNKED_ENCODING (200 OK)` — server *started* a 200 response then the connection tore mid-body. Server is still up at this point.
4. Client retries in a tight loop (1/5 → 5/5 per stream, across multiple streams simultaneously).
5. Every request flips to `net::ERR_CONNECTION_REFUSED` — the Node subprocess is now dead.

Interpretation: on wake, every suspended SSE stream resumes and the server writes to controllers whose underlying sockets are half-dead. An unhandled throw inside a `ReadableStream` source or an unhandled promise rejection from `controller.enqueue()` tears the Node process down. The client's retry-storm (5 retries × multiple streams × new connects) piles on.

## Symptom signature (after the crash)

- DevTools Network floods with `net::ERR_CONNECTION_REFUSED` on `http://127.0.0.1:5555/*`
- A previously-loaded page may show "500 Internal Error" (server's last gasp before fully exiting)
- `lsof -i :5555` returns nothing
- Main Electron process (`/Applications/Kommandr.app/Contents/MacOS/Kommandr`) is still running; only the Node child died

## Why the crash is invisible in `~/.kommandr/logs/`

`electron/server-manager.ts:151-168` pipes the child's stdout/stderr to `console.log` / `console.error` of the **Electron main process** — *not* to any file. The file-backed loggers in `src/lib/logger.ts` live inside the SvelteKit process and can't capture its own death: an uncaught exception or unhandled rejection tears the process down before the next `log.info` runs.

Concretely, the last entries in `api.log` / `chat-manager.log` are ordinary activity, then logs go silent — **no crash trace in `~/.kommandr/logs/`**. The trace only exists in Electron's stderr, which is lost unless the app was launched from a terminal.

## No auto-restart

`server-manager.ts:159`:

```ts
this.serverProcess.on('exit', (code, signal) => {
  console.log(`Server exited with code ${code}, signal ${signal}`);
  this.isRunning = false;
  this.serverProcess = null;
});
```

No restart-on-exit. Port 5555 stays empty until Kommandr is quit and relaunched. `ServerManager.stop()` is only called on `before-quit`.

## How to recover

1. **Quit and relaunch** Kommandr (Cmd-Q). `server-manager.ts:120-126` frees port 5555 on startup (`isPortAvailable` → `killProcessOnPort`), then respawns the child.
2. **Force-kill** if quit hangs: find Kommandr main PID with `ps aux | grep Kommandr`, then `kill -9 <pid>`.

## Fixes worth implementing

- **Harden SSE handlers** (`src/routes/api/**/stream/+server.ts`): guard every `controller.enqueue` / `controller.close` against "controller is closed" and "write after end" (`ERR_STREAM_WRITE_AFTER_END`). Register `cancel()` on every `ReadableStream` to unregister cleanly. Prevents the crash itself.
- **Capture subprocess stderr to file**: in the `stderr?.on('data')` handler at `server-manager.ts:155`, append to a rotated log (e.g. `~/.kommandr/logs/svelte-server.log`). Gives us a trace if it still happens.
- **Auto-restart with backoff**: on non-zero `exit` or `SIGKILL`, respawn up to N times with exponential backoff, skipped during intentional `stop()`.
- **Electron `powerMonitor`**: listen for `suspend` to proactively close SSE streams before sleep, and for `resume` to trigger a clean reconnect from the client instead of a retry storm.
- **Client reconnect backoff**: in `src/lib/chat-session.svelte.ts` and notifications, exponential backoff instead of 5 rapid retries, and pause reconnects when `document.visibilityState === 'hidden'`.

## Related docs

- `electron/build-and-packaging.md` — how the server subprocess is located and spawned
- `sse-connection-management.md` — how SSE streams are structured in the routes
- `hmr-and-module-reload-state-persistence.md` — note that a server restart wipes `sessionStore`; clients reconnect via `reconnectToSession()`
