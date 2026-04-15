---
updated: 2026-04-13
---

# provider-adapter-architecture

---
updated: 2026-04-13
---

# Multi-Provider Adapter Architecture

## Overview

Kommandr supports multiple AI coding CLI providers (Claude Code, OpenAI Codex, etc.) through a pluggable adapter pattern in `src/lib/providers/`. All consumers (chat-manager, task-runner, scaffold-manager, check-done-manager) route through the registry instead of importing `claude-cli.ts` directly.

## Status

Phases 1-5 implemented and tested. Codex full chat sessions work end-to-end (confirmed 2026-04-11). Task runner with Codex is the remaining manual test item.

## Key Files

| File | Purpose |
|------|---------|
| `src/lib/providers/types.ts` | All interfaces: `ProviderAdapter`, `ProviderSession`, `ProviderOutputChunk`, `ProviderStatus`, `ProviderKind` |
| `src/lib/providers/registry.ts` | `registerAdapter()`, `getAdapter(kind)`, `getDefaultProvider()`, `closeAllProviderSessions()` |
| `src/lib/providers/detection.ts` | `detectBinary(name, customPath?, managedPath?)` — finds CLIs on system |
| `src/lib/providers/claude/adapter.ts` | `ClaudeAdapter` — wraps `claude-cli.ts`, `claude-code-manager.ts`, `claude-auth.ts` |
| `src/lib/providers/codex/adapter.ts` | `CodexAdapter` — long-lived `codex app-server` process, JSON-RPC 2.0 over stdio |
| `src/lib/providers/index.ts` | `initProviders()` — registers all adapters, re-exports types |
| `src/lib/notification-stream.ts` | Shared singleton notification SSE (prevents duplicate connections) |

## Detection Priority

`detectBinary()` checks in this order for each provider:
1. **Custom path** — `settings.providers.<kind>.binaryPath` (user-configured)
2. **System PATH** — `which <binaryName>` (e.g., `which claude`, `which codex`)
3. **Managed install** — `~/.kommandr/bin/claude` (Claude only, via GCS download)

The result includes `source: 'custom' | 'system' | 'managed'` so the UI can show where the binary was found.

## Codex Adapter — `codex app-server` JSON-RPC

The `CodexAdapter` in `src/lib/providers/codex/adapter.ts` uses a **long-lived `codex app-server` process** that speaks JSON-RPC 2.0 over stdio (newline-delimited JSON on stdin/stdout).

### Protocol Lifecycle

```
1. spawn `codex app-server` (cwd = project path)
2. → initialize { clientInfo, capabilities: { experimentalApi: true } }
   ← { result: { userAgent, codexHome, ... } }
3. → initialized (notification, no id)
4. → thread/start { model, approvalPolicy, sandbox, cwd, instructions? }
   ← { result: { thread: { id } }, model, ... }
   ← thread/started (notification)
   ← mcpServer/startupStatus/updated (notification — codex_apps starting/ready)
5. → turn/start { threadId, input: [{ type: "text", text, text_elements: [] }], model, effort }
   ← turn/started (notification)
   ← item/started { item: { type: "reasoning" } }
   ← item/completed (reasoning done)
   ← item/started { item: { type: "agentMessage", phase: "final_answer" } }
   ← item/agentMessage/delta (notification, repeated — streaming text)
   ← item/completed (message done)
   ← thread/tokenUsage/updated (notification — cumulative token counts)
   ← turn/completed { turn: { id, status, durationMs } }
6. Subsequent messages: repeat step 5 on same threadId
```

### Agent/Planner Instructions for Codex

The Codex CLI has no `--system-prompt` flag like Claude. To pass behavioral instructions (e.g. the planner system prompt):

1. **`thread/start.instructions`** — passed as a param; may or may not be honored depending on Codex version
2. **First message prepend** (guaranteed path) — on `session.isFirstMessage`, the adapter prepends `session.agentPrompt` wrapped in `<system-instructions>` tags to the user's message text in `turn/start`

This is critical for Planner mode: without these instructions, Codex has no awareness it should only plan (create tasks/epics) and will try to implement code directly.

**Ordering note:** `session.isFirstMessage` must be checked BEFORE setting it to `false` in `sendMessage()`.

### Critical: `experimentalApi: true`

The `initialize` request MUST include `capabilities: { experimentalApi: true }`. Discovered by comparing with the t3code reference implementation.

### Token Usage

Token counts do NOT arrive in `turn/completed`. They come in a separate `thread/tokenUsage/updated` notification that fires BEFORE `turn/completed`. The adapter stores the latest usage in `ctx.lastUsage` and includes it in the `done` chunk.

### Session Context & State Persistence

The adapter maintains three lookup maps stored on `globalThis` (survives module re-evaluation — see `hmr-and-module-reload-state-persistence` doc):
- `sessions: Map<string, ProviderSession>` — keyed by adapter's internal UUID
- `contexts: Map<string, CodexSessionContext>` — holds child process, readline, pending requests
- `contextsByProcess: WeakMap<ChildProcess, CodexSessionContext>` — fallback lookup

**Important:** `sendMessage()` waits for `ctx.initPromise` to resolve before sending `turn/start`. This handles the ~1 second window between session creation and thread initialization.

### Server Requests (auto-approved)

| Method | Response |
|--------|----------|
| `item/commandExecution/requestApproval` | `{ decision: "allow" }` |
| `item/fileChange/requestApproval` | `{ decision: "allow" }` |
| `item/tool/requestUserInput` | `{ answers: {} }` |

### `item/started` — Thread Item Types

Canonical spec is at `codex-rs/app-server-protocol/src/protocol/v2.rs` in the `openai/codex` repo (`ThreadItem` enum, `#[serde(tag = "type", rename_all = "camelCase")]`). The full set of `item.type` values:

| Type | Key fields | Notes |
|------|-----------|-------|
| `userMessage` | `content: UserInput[]` | User's turn input |
| `hookPrompt` | `fragments` | Hook-injected prompt fragments |
| `agentMessage` | `text, phase, memoryCitation` | Assistant reply (streams via `item/agentMessage/delta`) |
| `plan` | `text` | Experimental plan item |
| `reasoning` | `summary[], content[]` | Streams via `item/reasoning/textDelta` and `.../summaryTextDelta` |
| `commandExecution` | `command, cwd, commandActions[], status, aggregatedOutput, exitCode, durationMs` | **See below** |
| `fileChange` | `changes: [{path, kind: "add"\|"delete"\|"update"}], status` | Patch result |
| `mcpToolCall` | `server, tool, arguments, result, error, status` | MCP tool invocation |
| `dynamicToolCall` | `tool, arguments, contentItems, success, status` | Non-MCP tool call |
| `collabAgentToolCall` | `tool, senderThreadId, receiverThreadIds, prompt, ...` | Sub-agent spawn/dispatch |
| `webSearch` | `query, action` | Web search invocation |
| `imageView` | `path` | Image shown to model |
| `imageGeneration` | `status, result, revisedPrompt, savedPath` | Generated image |
| `enteredReviewMode` / `exitedReviewMode` | `review` | `/review` flow |
| `contextCompaction` | — | Auto-compact |

### `commandExecution.commandActions` — semantic tool parsing

Codex wraps every shell invocation in `/bin/zsh -lc "cd <cwd> && …"`, so the raw `command` string looks generic. Codex pre-parses the command into semantic actions on the `commandActions` field — use this, not the shell string, to label tool cards in the UI.

`commandActions` is `Vec<CommandAction>` where each action is (tagged union, `"type"` key, camelCase):

| `type` | Fields | Maps to |
|--------|--------|---------|
| `read` | `command, name, path` | `Read` |
| `listFiles` | `command, path?` | `LS` |
| `search` | `command, query?, path?` | `Grep` |
| `unknown` | `command` | `Bash` (fall back to raw command) |

A single shell command can emit multiple actions when piped (`cat a.txt \| grep foo` → `[Read, Search]`) — the first action is the usual label.

### Current adapter coverage vs. protocol (as of 2026-04-13)

`handleNotification()` in `src/lib/providers/codex/adapter.ts` only handles `commandExecution` and `fileChange`, both hardcoded to `toolName: 'Bash'` / `'Edit'`, and ignores `commandActions`. As a result:

- All Codex actions render as **"Terminal"** with the raw `/bin/zsh -lc "cd …"` wrapper in `ToolCallStack.svelte`, even when Codex already classified the command as Read/Search/LS.
- `mcpToolCall`, `dynamicToolCall`, `webSearch`, `imageView`, `imageGeneration`, `plan`, `collabAgentToolCall` are silently dropped from the UI.
- `item/updated` is not handled, so tool cards never transition from in-progress to completed/failed.

To fix: inspect `item.commandActions[0].type` and map to `Read` / `LS` / `Grep` / `Bash`; use `fileChange.changes[0].kind` for `Write` (add) vs `Edit` (update); add explicit cases for `mcpToolCall` (`toolName: item.tool`), `dynamicToolCall`, `webSearch` (`toolName: 'WebSearch'`), and handle `item/updated` for status transitions.

## SSE Connection Management (CRITICAL)

See the dedicated `sse-connection-management` doc for full details. Key points:

- **NEVER use `EventSource`** — all SSE must use fetch-based streams with AbortController
- **NEVER duplicate SSE connections** — use singletons (e.g., `notification-stream.ts`)
- **Keep total concurrent streams ≤ 5** — Chromium's 6-per-origin HTTP/1.1 limit leaves only 1 slot for API calls
- The Codex integration was blocked for days by this: 7+ SSE connections meant message POSTs were queued forever by Chromium

## Adding a New Provider

1. Create `src/lib/providers/<name>/adapter.ts` implementing `ProviderAdapter`
2. Add the kind to `ProviderKind` union in `types.ts`
3. Register in `src/lib/providers/index.ts`
4. Add `<name>?: ProviderSettings` to `AppSettings.providers` in `settings.ts`
5. Add model badge styles to `modelStyles` in `agents-client.ts`
6. The adapter must implement: `detect()`, `createSession()`, `sendMessage()`, `cancelResponse()`, `closeSession()`, `closeAllSessions()`

## Settings

Provider config in `~/.kommandr/settings.json`:
```json
{
  "providers": {
    "claude": { "enabled": true, "binaryPath": "/custom/path/claude" },
    "codex": { "enabled": true }
  },
  "defaultProvider": "claude"
}
```

## Roadmap

Tracked in `MULTI-PROVIDER-ROADMAP.md` at repo root. Phases 1-5 implemented. Codex chat confirmed working. Remaining: task runner with Codex provider.
