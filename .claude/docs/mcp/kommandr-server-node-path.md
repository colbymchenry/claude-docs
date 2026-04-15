---
updated: 2026-04-14
---

# MCP Server Spawning in Packaged Electron

## The Bug

Kommandr's kommandr MCP server failed to start in the packaged app (`/Applications/Kommandr.app`) with `mcp_servers: [{"name":"kommandr","status":"failed"}]` in the stream-json `system/init` line. Downstream: the planner called `kommandr_create` and got `<tool_use_error>Error: No such tool available: kommandr_create</tool_use_error>`.

Same class of bug affected third-party MCP servers the user added — anything that used a bare `npx`/`npm`/`node` command.

## Root Cause

Two layers of the same problem:

**1. Bare `node` in Kommandr's own kommandr MCP config.**

The chat config builder used `command: 'node'`. Claude CLI resolved it against PATH, which in packaged Electron is minimal (`/usr/bin:/bin:/usr/sbin:/sbin` — no nvm, no homebrew, no `/usr/local/bin`). `~/.kommandr/bin/` was the only thing `claude-cli.ts` prepended to PATH and it's empty on most installs.

**2. Bare `npx`/`npm` in user-configured third-party MCP configs.**

User-added MCP servers (via `~/.claude.json`, `~/.claude/settings.json`, or project `.mcp.json`) are typically `{ command: 'npx', args: ['-y', '<pkg>'] }`. Same PATH problem: `npx` doesn't resolve in packaged Electron.

## The Fix

### For Kommandr's own MCP server

`src/lib/chat-session-config.ts` defines `buildKommandrMcpServer(projectId, sessionId?)`:

```ts
function buildKommandrMcpServer(projectId: string, sessionId?: string): McpServerConfig {
    const env: Record<string, string> = {
        KOMMANDR_API_URL: `http://127.0.0.1:${process.env.PORT || '5555'}`,
        KOMMANDR_PROJECT_ID: projectId,
    };
    if (sessionId) env.KOMMANDR_SESSION_ID = sessionId;
    return {
        type: 'stdio',
        command: process.execPath,  // absolute path to bundled node
        args: [resolveKommandrMcpServerPath()],
        env,
    };
}
```

`process.execPath` is the node binary currently running the SvelteKit server. In packaged builds that's `Resources/bin/node` (the bundled Node.js 22.12.0 set up by `electron/server-manager.ts:getBundledNodePath()`). In dev it's whatever spawned the server. Guaranteed to exist in both — no PATH lookup, no system-node-version lottery.

**`sessionId` is optional and semantic.** The kommandr MCP server uses it to route `kommandr_ask_user` answers back to the right SSE channel. For autonomous contexts (task-runner, scaffolding) there is no interactive UI to answer, so the caller omits `sessionId` — `kommandr_ask_user` then surfaces a clear "no session" error instead of silently hanging on an unanswered question.

### For third-party MCP servers

`src/lib/claude-cli.ts` augments PATH for the Claude CLI subprocess with the user's login-shell PATH, resolved once and cached:

```ts
function getUserShellPath(): string {
    // cached ...
    const shell = globalThis.process.env.SHELL || '/bin/zsh';
    return execSync(`${shell} -ilc 'echo -n "$PATH"'`, { timeout: 3000 }).trim();
}

const augmentedPath = [CURRENT_NODE_DIR, BUNDLED_NODE_DIR, userShellPath, currentPath]
    .filter(Boolean).join(':');
```

`CURRENT_NODE_DIR = path.dirname(process.execPath)` handles `node` resolution for any MCP server that uses bare `node`. The login-shell PATH (from `zsh -ilc 'echo $PATH'`) brings in the user's nvm/homebrew/volta/asdf paths so `npx`/`npm`/etc. resolve the way they do in the user's terminal. Cached on first spawn (~100–500ms cost), then free.

## Which session entry points register the Kommandr MCP?

`buildKommandrMcpServer` is **not** automatic — every new session-creating entry point has to register it explicitly, and the list is currently inconsistent:

| Entry point | Builder function | Registers `kommandr`? | `sessionId` passed? |
|---|---|---|---|
| Planner chat | `chat-session-config.ts` planner branch (L169) | ✅ yes | ✅ yes |
| General assistant chat | `chat-session-config.ts` general branch (L224) | ✅ yes | ✅ yes |
| Task runner (autonomous) | `task-runner-manager.ts` `buildTaskRunnerMcpConfig` | ❌ **no** | — |
| Scaffolding | `scaffold-manager.ts` | ❌ no (by design — new project, no issues yet) | — |

Because all of these also pass `strictMcpConfig: true`, any Kommandr MCP registered elsewhere (global `~/.claude.json`, project `.mcp.json`) is **ignored**. If the builder doesn't include it in the handed-in `--mcp-config` file, the `mcp__kommandr__*` tools don't exist for that session.

**Gotcha (task runner):** autonomous epic runs report "Kommandr tools aren't available in this session." That's the `buildTaskRunnerMcpConfig` gap — it copies only global + project MCPs and never adds Kommandr. Fix is to merge in `buildKommandrMcpServer(projectId)` (no `sessionId`) alongside the other servers.

**When adding a new entry point** that spawns a provider session: if the flow should manage issues via `kommandr_*` tools, you must call `buildKommandrMcpServer` and include it in `mcpConfigs`. If the flow is autonomous (no modal UI), pass no `sessionId` so `kommandr_ask_user` fails loudly.

## Why process.execPath and Not the Bundled-Node Path

`process.execPath` is authoritative: it's the binary actually running this code. The alternative — re-resolving `Resources/bin/node` via `KOMMANDR_RESOURCES_PATH` — duplicates logic already in `server-manager.ts` and drifts if that changes. `process.execPath` always reflects the real answer in both packaged and dev modes.

Exception: `electron/server-manager.ts` itself still has to resolve the bundled node path (to spawn the SvelteKit process in the first place), so that logic stays. In the Electron main process `process.execPath` is the Electron binary, not node — it can't use this trick.

## How to Confirm the Bug

1. `grep '"subtype":"init"' ~/.kommandr/logs/claude-cli.log | tail -1` and parse the JSON.
2. `mcp_servers` with `"status":"failed"` → an MCP server couldn't spawn.
3. Look at the MCP config file path in the preceding `Args` log line (under `--mcp-config`) to see what `command` was used.
4. For the "tools not available" variant: grep Claude's response for "Kommandr tools aren't available" — if seen in a task-runner session, the cause is the missing registration, not a spawn failure.

## Related Code

- `src/lib/chat-session-config.ts:30-69` — `resolveKommandrMcpServerPath()` + `buildKommandrMcpServer()`
- `src/lib/chat-session-config.ts:169, 224` — call sites for planner and general chat
- `src/lib/task-runner-manager.ts:33-61` — `buildTaskRunnerMcpConfig()` (missing Kommandr registration)
- `src/lib/claude-cli.ts:16-48` — `CURRENT_NODE_DIR` + `getUserShellPath()`
- `electron/server-manager.ts:19-38` — bundled node resolution (for spawning the SvelteKit server)
- `BUNDLED_NODE_DIR = ~/.kommandr/bin` in `claude-cli.ts:15` is effectively dead code for node resolution — kept in the PATH prepend for backward compatibility with `node-manager.ts` installs, but that flow doesn't run on current machines (`~/.kommandr/node/` is empty).
