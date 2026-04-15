---
updated: 2026-04-12
---

# Logging Conventions

Kommandr has three loggers running in parallel across processes. Use the right one for the right code, and never log secrets.

## Logger locations

| Process | File | Import path |
|---------|------|-------------|
| SvelteKit server (any `src/` file running on Node, including `+server.ts` routes and `src/lib/*`) | `src/lib/logger.ts` | `import { loggers } from '$lib/logger'` or `'../logger'` depending on depth |
| Electron main process | `electron/logger.ts` | `import { loggers } from './logger.js'` |
| Kommandr MCP server (spawned standalone Node process) | `mcp/mcp-logger.mjs` | `import { mcpLog } from './mcp-logger.mjs'` |

All three write to `~/.kommandr/logs/<category>.log`. File format is shared:

```
[2026-04-13T00:40:30.746Z] [ERROR] [database] Message | {"field":"value"}
```

5 MB per file, 5 rotations kept. `error()` calls flush the buffer immediately; everything else flushes on a 1s timer or when the buffer hits 50 entries.

## Do NOT use `console.log` / `console.error` in server or Electron code

The legacy pattern `console.error('[subsystem] message:', err)` writes only to stdout/stderr and does NOT land in `~/.kommandr/logs/`. Users can't upload stderr when filing a bug. Replace with the appropriate logger.

The single exception: `src/lib/agents-client.ts` is imported by the browser bundle. `fs`/`path`/`os` would crash there, so that file keeps `console.error` and MUST NOT import `loggers`.

## Categories and which to use

**SvelteKit side** (`loggers.X` where X is):

| Category | Use for |
|----------|---------|
| `api` | REST route handlers (`src/routes/api/**/+server.ts`) |
| `database` | Postgres / SQLite errors, pool events, schema init |
| `chatManager` | Chat session lifecycle, SSE controller registration |
| `claudeCli` | Claude CLI subprocess spawn/exit/stream-json parse |
| `devServer` | Per-project dev server lifecycle |
| `taskRunner` | Background epic/task execution |
| `notifications` | Notification persistence |
| `auth` | Login, session, OAuth flows (**redact tokens**) |
| `git` | Git routes and subprocess wrappers |
| `settings` | Settings file load/save, Claude path detection |
| `app` | Catch-all for `src/lib/*` that doesn't fit above |

**Electron side** (`loggers.X`):

| Category | Use for |
|----------|---------|
| `electron` | App lifecycle, window creation, renderer crashes |
| `preview` | BrowserView / webview preview |
| `serverManager` | SvelteKit subprocess lifecycle |
| `updater` | Auto-updater events and errors |
| `ipc` | Generic IPC handler errors |
| `oauth` | OAuth server and callbacks (**redact tokens**) |
| `notifications` | Native macOS notifications |

**MCP server** — only `mcpLog.info/warn/error/debug(message, data)`. Writes to `~/.kommandr/logs/mcp-server.log` AND mirrors to stderr so `claude-cli.log` captures context too.

## Signature and data conventions

```ts
log.info('Short descriptive message', { key: value, anotherKey: value });
log.error('What failed', {
  projectId,
  message: err instanceof Error ? err.message : String(err),
  // include error .code when present (pg errors, Node fs errors)
  code: (err as { code?: string })?.code,
});
```

- **First arg** is a short human-readable sentence. Do not include field values here — put them in `data`.
- **`data` arg** must be JSON-serializable. Circular refs will `[object Object]` silently — normalize before logging.
- **Never pass the raw `Error`** — it stringifies to `{}` because error fields are non-enumerable. Extract `.message`, `.stack`, `.code`.

## Secret redaction — mandatory

Never log these values, even if the user could have caused a leak themselves:

- Claude/Anthropic OAuth tokens (`access_token`, `refresh_token`, `sk-ant-…`)
- `postgresql://user:password@host` — log only `host:port/database` (see `src/routes/api/connectors/[id]/test/+server.ts` `safeConnLabel()` helper)
- Any `Authorization:` / `Bearer …` / `x-api-key:` header value
- User prompt content in full — log length + 60-char preview at debug level only
- Tool-use output from Claude when it could contain file contents
- `.kommandr/adapter.json` contents (credentials merged in)
- Git diff output (may contain secrets user committed by mistake)
- Git commit messages (may contain paste-ins like `DATABASE_URL=…`)
- Full file paths when they could contain a user's home dir + project name (`basename` + `extname` only is fine)
- Full OAuth callback URLs — log booleans: `hasAccessToken`, `hasRefreshToken`, `tokenType`, `expiresIn`

**`src/hooks.server.ts`** has a `redactSecrets()` helper that regex-masks bearer tokens, `Authorization:` headers, `sk-*` keys, and pg connection passwords. Apply it before persisting any error stack that could quote third-party library errors.

## Pattern for `+server.ts` error paths

```ts
import { loggers } from '$lib/logger';
const log = loggers.api; // or loggers.git, loggers.database, etc.

export const POST: RequestHandler = async ({ params, request }) => {
  try {
    // ... work ...
    return json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log.error('Descriptive action failed', { projectId: params.id, message });
    return json({ error: `Action failed: ${message}` }, { status: 500 });
  }
};
```

**Surface `e.message` in the 500 response body, not just in logs.** The Kommandr MCP server relays `body.error` directly to Claude, and without it planner agents see `"Failed to create issue"` with zero actionable signal. See `mcp/kommandr-server.mjs` `api()` helper — it throws with `data.error`, and the planner shows that string verbatim in the "action row" of the task UI.

## Postgres-specific: pool error handler

`src/lib/stores/postgresql-store.ts` registers `pool.on('error', …)` in the constructor to catch idle-client errors (connection drops while nobody's actively querying). Without this, `pg` crashes the Node process. Redact: log `.message` / `.code` / `.severity` only; never log the full error object (`internalQuery` can carry connection strings).

## Electron main-process signal handling

`electron/main.ts` registers `process.on('uncaughtException'|'unhandledRejection')`. These now log `message`, `stack`, `name`. Don't remove them — without these, a crash leaves only the Electron console (invisible to a packaged build).

## MCP server logging pattern

`mcp/kommandr-server.mjs` uses `mcpLog` for: startup, missing env vars, fetch failures, non-JSON responses, and API error responses. The `api()` helper parses the body as text first so non-JSON (HTML error pages from Vite crashes) can be logged verbatim via `bodyPreview: rawBody.slice(0, 500)`.

## Where to find logs

```bash
# Everything
ls ~/.kommandr/logs/

# Live tail by subsystem
tail -f ~/.kommandr/logs/api.log ~/.kommandr/logs/database.log

# Error sweep across all categories
grep -r 'ERROR' ~/.kommandr/logs/
```

`src/lib/logger.ts` exposes `getLogContents(category, lines)` and `getLogCategories()` for in-app log viewers.
