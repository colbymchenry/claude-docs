---
updated: 2026-04-14
---

# chat-session-lifecycle

---
updated: 2026-04-14
---

# Chat Session Lifecycle & Real-Time Transport

How the planner/agent chat sidebar manages sessions, real-time streams, provider switching, cleanup, and **cross-restart resumption** (sessions survive app restart / DMG reinstall for both Claude and Codex).

**Transport:** as of 2026-04-14, all chat streaming uses socket.io on the `/chat` namespace (and `/helper-chat` for ExplanationChat). SSE is gone. See `socket-io-architecture` for the transport-layer details; this doc focuses on the chat-specific lifecycle rules that sit on top of it.

## Key Files

| File | Role |
|------|------|
| `src/lib/chat-session.svelte.ts` | Client-side session state factory (reactive Svelte 5 runes). Tracks `sessionId` + `providerSessionId` + exposes `loadedMeta` so the parent can restore provider/model/mode. Owns the `/chat` socket subscription and the `detachSocket()` helper. |
| `src/components/ChatSheet.svelte` | Sidebar UI, lifecycle effects, provider selection. Restores saved provider/model/mode on init and sequences `fetchProviders` → `checkInitialization`. |
| `src/components/ChatInput.svelte` | Input area with provider/mode/model pills |
| `src/lib/chat-manager.ts` | Server-side provider process management + socket.io broadcast. `broadcastToSession()` routes to `/chat` or `/helper-chat` based on `markHelperSession()` tagging. `getOrCreateProcess()` accepts a `resumeSessionId` arg. |
| `src/lib/chat-session-config.ts` | Pure helper `buildChatSessionConfig(projectId, projectPath, agentFilename)` that returns MCP/agent/tools/settings. Used by both create and resume endpoints so a resumed session gets the exact same shape. |
| `src/lib/providers/registry.ts` | Maps `ProviderKind` → `ProviderAdapter` |
| `src/lib/providers/claude/adapter.ts` | Claude adapter — forwards `resumeSessionId` to `createClaudeSession`. |
| `src/lib/providers/codex/adapter.ts` | Codex adapter — calls `thread/resume` (vs `thread/start`) when `resumeSessionId` is set. Prepends the agent prompt to every turn. |
| `src/lib/session-store.ts` | In-memory server-side session store (30min timeout). `createSession()` accepts an optional `id` so resumed sessions keep their original Kommandr id. |
| `src/lib/server/chat-namespace.ts` | `/chat` and `/helper-chat` room handlers. Accepts `join { sessionId }`, validates via `sessionStore`, replays `connected` + `history` chunks on join. |
| `src/lib/helper-session-store.ts` | Background Claude sonnet/ask session for quick explanations. Exposes `subscribeHelperChunks(projectId, handler)` for UI consumers. |
| `src/lib/chat-history.ts` | localStorage persistence for messages, sessionId, and resume metadata (`providerSessionId`, `provider`, `model`, `mode`, `agentFilename`) |
| `src/routes/api/projects/[id]/chat/+server.ts` | POST creates new session (accepts `provider`, `helper` in body). Tags helper sessions via `markHelperSession` for broadcast routing. |
| `src/routes/api/projects/[id]/chat/[sessionId]/+server.ts` | POST sends message, DELETE closes session and kills process |
| `src/routes/api/projects/[id]/chat/[sessionId]/status/+server.ts` | GET session existence check (memory only) |
| `src/routes/api/projects/[id]/chat/[sessionId]/resume/+server.ts` | POST rebuilds the in-memory session from client-held metadata so the next message goes out with `--resume` (Claude) / `thread/resume` (Codex) |

> **Gone:** `src/routes/api/projects/[id]/chat/[sessionId]/stream/+server.ts` was deleted when `/chat` migrated to socket.io. The stream-endpoint hydration (history replay on connect) now happens inside `chat-namespace.ts`.

## Session Lifecycle Rules (IMPORTANT)

These are product requirements, not implementation details:

| User Action | Session | Socket Room | Server Process |
|-------------|---------|------------|----------------|
| **Dismiss drawer** | Kept | Kept (work continues in background) | Kept running |
| **Reopen drawer** | Reconnects to same session | Already joined | Still running |
| **Stop button** | Kept | Kept | Sends `/cancel`, process stays alive for next message |
| **New Chat button** | DELETEs old session, creates new | `leave` old, `join` new | Old process killed, new spawned |
| **Switch provider** | DELETEs old session, creates new | `leave` old, `join` new | Old process killed, new spawned |
| **Switch model** (same provider) | No change | No change | No change (model used on next turn) |
| **App restart / reinstall** | Rehydrated via `/resume` endpoint; provider/model/mode restored from localStorage | Client emits `join` after `/resume` 200 | Re-spawned on resume; next message uses the provider's resume mechanism |

**Key principle:** Dismissing the chat drawer must NOT kill the session, the socket subscription, or the provider process. The user expects Claude/Codex to keep working while they look at other things. Only explicit user actions (New Chat, Stop, provider switch) should interrupt work.

**Do not disconnect the shared socket on drawer dismiss.** The Manager + `/chat` socket are tab-wide. `closeEventSource()` (name kept for call-site compat) now calls `detachSocket()`, which `socket.off()`s the chunk handler and emits `leave` — but never `socket.disconnect()`. Disconnecting would break every other consumer on the tab.

## Agent Prompt Injection (Per-Turn)

Both providers re-inject the agent prompt on **every** turn, not just the first. This prevents persona drift — a Planner that stops calling `kommandr_*` tools, a custom agent that reverts to generic software-engineer behavior, etc. The delivery mechanism differs because the two CLIs expose different surfaces:

- **Claude** — each message is its own CLI spawn. We pass `--system-prompt-file` (or `--append-system-prompt-file`) on every spawn. Comment at `claude-cli.ts:239-248` documents the reason: `--resume` restores conversation history but NOT the system-prompt contents, so without re-passing we'd lose agent identity after turn 1. For standalone-prompt agents (Planner), `--system-prompt-file` replaces the built-in "software engineer" system prompt entirely.
- **Codex** — one long-running `codex app-server` process per session; turns happen via `turn/start` on the existing thread. There is no dedicated system-prompt field on `turn/start`, and while `thread/start` / `thread/resume` accept `baseInstructions`, those only take effect at thread-open time. So we prepend the agent prompt wrapped in `<system-instructions>…</system-instructions>` to every user turn's text (`codex/adapter.ts` `sendMessage`). On long conversations this is what keeps the early instructions from scrolling out of effective attention.

Cost: ~500 tokens/turn for a typical agent prompt. Both providers cache repeated prefixes, so the marginal cost after turn 1 is effectively a cache read, not a fresh billed prefill.

`isFirstMessage` is retained on the `ProviderSession` type because Claude uses it to decide whether to pass `--resume` on the CLI spawn, but it no longer gates the Codex prepend — that runs every turn.

## Cross-Restart Persistence

Both providers persist their own conversation transcript outside the app:

- **Claude** — `~/.claude/projects/<encoded-project-path>/<claudeSessionId>.jsonl`. Resumed via `--resume <id>` on the next CLI spawn.
- **Codex** — rollout file on disk keyed by `threadId`. Resumed via the `thread/resume` JSON-RPC call against a freshly spawned `codex app-server`.

Both files live in the user's home (not the `.app` bundle), so they survive app updates and DMG reinstalls. All we need to retain is the provider-side id and the **originating provider**.

**Why provider selection must persist too**

localStorage history is keyed by `agentFilename` (or `'general'`), not by provider. The same key can hold either a Claude `claudeSessionId` or a Codex `threadId`. If the UI booted with its default provider (Claude) but the saved session was started under Codex, a naive resume would try to rebuild a Claude session around a Codex id and fail. So we persist and restore `provider`, `model`, and `mode` alongside the session id.

**What persists where**

- **Kommandr `sessionId`** — generated server-side at session creation. Sent back to client. Stored in localStorage.
- **Provider `sessionId`** (a.k.a. `claudeSessionId` / Codex `threadId`) — emitted by the adapter as a synthetic `{ type: 'provider_session_id', sessionId, provider }` chunk on the `/chat` socket:
  - Claude: emitted by `claude-cli.ts` the first time it sees `sessionId` on a stream-json chunk.
  - Codex: emitted by `codex/adapter.ts` immediately after `thread/start` resolves with the new `threadId`.
  Client saves it alongside `sessionId` in localStorage.
- **Session config** (`provider`, `model`, `mode`, `agentFilename`) — persisted alongside so the parent component can restore UI selection and the resume endpoint can rebuild the exact same MCP/agent/tools setup.

**Resume flow on app restart**

1. `ChatSheet` mounts → `chat.loadHistory()` restores `sessionId` + `providerSessionId` + messages, and sets `chat.loadedMeta` with the saved `{ provider, model, mode, agentFilename }`.
2. ChatSheet applies `loadedMeta.provider/model/mode` to its `selectedProvider/selectedModel/selectedMode` state, setting `suppressNextProviderEffect = true` so the first provider-change effect fires a no-op (the restore is not a real "switch").
3. `await fetchProviders()` runs. If the saved provider isn't installed/enabled, it falls back to the first available provider and returns `true` (autoSwitched). The provider-change effect then runs normally and `startNewChat()` clears the unresumable session.
4. `await chat.checkInitialization({ skipSessionStart: autoSwitched })` runs. It hits `/chat/{sid}/status`. Server memory is cold → 404.
5. With `providerSessionId` present, client POSTs `/chat/{sid}/resume` with `{ providerSessionId, provider, model, mode, agentFilename }` — using the now-restored values, so the correct adapter is used.
6. Resume handler:
   - Builds config via `buildChatSessionConfig()` (same helper POST `/chat` uses) — this reconstructs `agentPrompt` from `agentFilename` so per-turn injection keeps working on the resumed session.
   - `sessionStore.create(projectId, agentFilename, agentName, sid)` reuses the original Kommandr `sessionId`.
   - `getOrCreateProcess(..., resumeSessionId: providerSessionId)` plumbs the id through `ProviderSessionOptions.resumeSessionId` to the adapter.
7. **Client awaits the `/resume` 200** and THEN calls `connectToStream(sid)`, which calls `getNamespace('/chat').emit('join', { sessionId: sid })`. Joining before `/resume` is a race — the server has no in-memory session yet and the `/chat` handler emits an `error` chunk.
8. Next turn picks up on the existing transcript:
   - **Claude:** `claude-cli.ts` sees `!isFirstMessage && claudeSessionId`, adds `--resume <claudeSessionId>` to the CLI args. `--system-prompt-file` is re-passed as always.
   - **Codex:** adapter sends `thread/resume { threadId, model, approvalPolicy, sandbox, cwd, persistExtendedHistory: false }` in place of `thread/start`. The agent prompt is re-prepended on the next (and every) `turn/start` just like a fresh thread.

**Failure modes**

- No `providerSessionId` saved yet (user quit before sending the first message that triggers id capture) → `reconnectToSession` falls back to `startSession()`.
- Saved provider no longer installed → `fetchProviders()` auto-switches, provider-change effect fires `startNewChat()`, fresh session under the new provider.
- Resume endpoint 500s (e.g. disk transcript deleted) → client falls back to `startSession()`.
- Client joins `/chat` before `/resume` completes → server emits `error` chunk; client should fall back to `startSession()` (TODO — not yet wired in handleStreamMessage).

## Ordering Gotcha: fetchProviders ↔ checkInitialization

These two MUST run sequentially — not concurrently — during ChatSheet init. **And `checkInitialization` MUST always run, even when `fetchProviders` auto-switches.** Use the `skipSessionStart` flag to suppress only the session-creation half:

```typescript
(async () => {
  const autoSwitched = await fetchProviders();
  await chat.checkInitialization({ skipSessionStart: autoSwitched });
})();
```

`checkInitialization(opts)` (in `chat-session.svelte.ts`) does two things:
1. Always: clear `checkingInit`, set `claudeConfigured`, fetch `/claude-status`, set `isInitialized`.
2. Conditionally (only when `!opts.skipSessionStart`): call `reconnectToSession()` or `startSession()` to actually open a chat session.

### Why both halves matter

Three failure modes informed this shape:

1. **Race: resume gets destroyed.** If `fetchProviders` auto-switches the provider, the provider-change `$effect` fires `startNewChat()` — which DELETEs the current session on the server and starts a fresh one. If `checkInitialization` had ALSO started a `/resume` call, the resume might succeed first and then `startNewChat` deletes the freshly-resumed session. `skipSessionStart: true` short-circuits checkInitialization's reconnect path so only `startNewChat` creates a session.

2. **Stale `selectedProvider` read.** Without sequential ordering, `checkInitialization` could read `selectedProvider` before `fetchProviders` has finished swapping it. The `await fetchProviders()` first guarantees the swap is done before `startSession()` reads `deps.getProvider()`.

3. **`checkingInit` stuck on true (the bug this shape fixes).** `checkingInit` is initialized to `true` in `createChatSession()` — that's what powers the "Checking Claude Code status..." spinner. It is **only** cleared in `checkInitialization`'s finally block. The previous version `if (!autoSwitched) await chat.checkInitialization()` skipped the call entirely on auto-switch, leaving the spinner stuck forever. Concretely: any user with a saved chat under a no-longer-installed provider (e.g. Codex saved, only Claude installed) would open the chat panel — or Live Edit mode — and see a permanent loading spinner. Always call `checkInitialization`; use `skipSessionStart` to suppress the session-start path only.

If you add a third path that creates a session during init, do the same: don't skip `checkInitialization`, just suppress the session-start half. Or extract a `clearCheckingInit()` helper. Anything else risks the same hang.

## Socket.io Architecture (replaces the old SSE section)

### Client-side (`chat-session.svelte.ts`)

```typescript
// connectToStream attaches a chunk listener on /chat and joins the sessionId room.
function connectToStream(sid: string) {
  detachSocket();
  const socket = getNamespace(NAMESPACES.CHAT);
  if (!socket) return;

  chatSocket = socket;
  currentJoinedSessionId = sid;

  chunkHandler = (chunk) => handleStreamMessage(chunk as StreamMessageData);
  connectHandler = () => {
    isConnected = true;
    socket.emit('join', { sessionId: sid });  // rejoin on every reconnect
  };
  disconnectHandler = () => { isConnected = false; };

  socket.on('chunk', chunkHandler);
  socket.on('connect', connectHandler);
  socket.on('disconnect', disconnectHandler);

  if (socket.connected) socket.emit('join', { sessionId: sid });
}
```

- `chatSocket: Socket | null` + handler refs replace the old `sseAbortController`.
- Reconnect-rejoin is required — socket.io drops room memberships when the underlying connection drops (wake-from-sleep, network blip). The `connectHandler` above re-emits `join` on every `connect` event.
- `detachSocket()` removes all listeners and emits `leave` but does NOT call `socket.disconnect()` — the socket is tab-shared.

### Server-side

- `broadcastToSession(sessionId, chunk)` in `chat-manager.ts` routes to `/chat` by default, or `/helper-chat` when `markHelperSession(sessionId)` was called.
- `/chat` + `/helper-chat` namespace handlers live in `src/lib/server/chat-namespace.ts`. On `join`, the server validates the session via `sessionStore.get(sessionId)`, joins the socket to the room, and emits the hydration prelude: `{ type: 'connected', sessionId, agentName, messageCount }` + one `{ type: 'history', message }` chunk per existing message.
- `registerSSEController` / `unregisterSSEController` / `sseControllers` Map are gone. If you find references to them, they're stale.

### Helper Session (`helper-session-store.ts`)

The helper session (background Claude sonnet/ask session for quick explanations) has its own browser-side store and uses the `/helper-chat` namespace for its chunk stream.

API:
- `getOrCreateHelperSession(projectId): Promise<string>` — creates the session with `helper: true` in the POST body (so the server calls `markHelperSession`), joins the `/helper-chat` room, and returns the sessionId.
- `subscribeHelperChunks(projectId, handler): () => void` — registers a per-project chunk subscriber. The store fans `/helper-chat` `chunk` events out to every subscriber for the matching project. Returns an unsubscribe closure. Use in `$effect` cleanups.
- `isHelperSessionConnected(projectId)` / `getHelperSessionId(projectId)` / `onConnectionChange(projectId, cb)` — unchanged from the SSE era.
- `clearHelperSession(projectId)` / `clearAllHelperSessions()` — emits `leave` and tears down subscriptions.

`ExplanationChat.svelte` consumes chunks via `subscribeHelperChunks`. Prior to the socket.io migration its stream handler was dead code; it now actually receives the stream.

## Session Creation Flow (fresh session)

1. `ChatSheet` mounts → `createChatSession()` factory creates reactive state (`checkingInit = true` initially).
2. First time `(isOpen || embedded) && browser` → run init IIFE: `await fetchProviders()` then `await checkInitialization({ skipSessionStart: autoSwitched })`.
3. Initialization runs **once** (`hasInitialized` flag). Drawer close/reopen does NOT re-initialize.
4. If project initialized and no `sessionId` and not auto-switching: `startSession()` POSTs to `/api/projects/{id}/chat` with `{ provider, model, mode, agentFilename }`.
5. Server creates session in `sessionStore` (storing `provider`, `model`, `mode` for later recovery) + spawns provider process via `getOrCreateProcess()`.
6. Client receives `sessionId` → `connectToStream(sid)` attaches the `/chat` chunk listener and emits `join { sessionId: sid }`.
7. Server validates the session and joins the socket to the `sid` room; emits `connected` + history hydration.
8. Provider emits the `provider_session_id` chunk at the first opportunity (Claude: first stream-json chunk; Codex: `thread/start` response). Client handles it in the stream message switch, sets `providerSessionId`, and persists via `saveHistory()`.

## Provider Switching (manual)

When `selectedProvider` changes for any reason other than an initial restore, a `$effect` in `ChatSheet.svelte` calls `startNewChat()`:

```typescript
let lastProvider = selectedProvider;
let suppressNextProviderEffect = false;
$effect(() => {
  if (selectedProvider !== lastProvider) {
    lastProvider = selectedProvider;
    if (suppressNextProviderEffect) {
      suppressNextProviderEffect = false;
      return;
    }
    chat.startNewChat();
  }
});
```

`startNewChat()` does:
1. `detachSocket()` — `off` the `/chat` chunk handler + emit `leave`
2. DELETE the old session on the server (`DELETE /chat/{oldSessionId}`) — this kills the old provider process
3. Clear client state (`sessionId = null`, `providerSessionId = null`, `isStreaming = false`, etc.)
4. Clear localStorage history
5. Call `startSession()` which creates a fresh session with the new provider

`startNewChat()` does **not** touch `checkingInit` — it assumes init has already finished. This is fine for manual provider switches (which only happen after init) but means the auto-switch path during init must rely on `checkInitialization` to clear the flag (see Ordering Gotcha above).

`suppressNextProviderEffect` is flipped to `true` right before the init code restores the saved provider. That way restoring `selectedProvider = 'codex'` from localStorage doesn't look like a user-initiated switch and doesn't tear down the session we're trying to resume.

**Model changes do NOT trigger a new chat.** The model is passed on each `turn/start` (Codex) or process spawn (Claude), so switching models within the same provider just takes effect on the next message.

## Provider Routing on Message Send

When the message POST handler (`chat/[sessionId]/+server.ts`) calls `getOrCreateProcess`, it passes the **stored provider** from the session:

```typescript
const providerProcess = getOrCreateProcess(
  params.sessionId, params.id,
  session.provider,  // from sessionStore, not defaultProvider
  agentPrompt, session.model, session.mode
);
```

This ensures the correct adapter is used even if the process needs to be re-created (e.g., after module re-evaluation). The `session-store.ts` `ChatSession` interface has `provider?: string`, `model?: string`, `mode?: string` fields for this purpose.

## Server-Side Cleanup

- `startNewChat()` sends `DELETE /api/projects/{id}/chat/{sessionId}` before creating a new session.
- The DELETE handler calls `closeProviderSession(sessionId)` which calls `adapter.closeSession()` — for Codex this kills the `app-server` process; for Claude this kills the CLI process. It also `sessionNamespace.delete(sessionId)` so any lingering broadcast falls back to `/chat` (harmless — no one's joined).
- `sessionStore` has a 30-minute inactivity timeout for automatic cleanup.
- `providerProcesses` Map entries are deleted when the process exits (`onClose` callback).

## Reconnection on Reopen (same app session)

When the drawer reopens (same component instance, `isOpen` goes true again):
- The socket subscription is still active (was never detached on dismiss)
- `claudeReady`, `sessionId`, `isStreaming` all retain their values
- The user sees the same messages and can continue the conversation
- If the underlying WebSocket dropped while the drawer was closed, socket.io reconnects automatically and `connectHandler` re-emits `join`

Cross-restart reopen is a separate path — see "Cross-Restart Persistence" above.

**Live Edit mode:** `LiveEditMode.svelte` mounts `ChatSheet` inside a `Dialog.Root open={isOpen}` with `embedded={true}`. By default Bits UI's Dialog unmounts its content when `open` flips to false — which would create a fresh `ChatSheet` instance on every reopen and re-trigger the init flow. To preserve session state, the dialog passes `keepMounted` (a project-specific extension on `dialog-content.svelte` that toggles Bits UI's `forceMount` and adds `data-closed:invisible data-closed:pointer-events-none`). Result: closing Live Edit hides the modal but keeps `ChatSheet` (and `DevServerPreview`) mounted with all state intact, so reopening is instant. See `ui-component-stack` doc for the `keepMounted` API.

## localStorage Schema

Key format: `chat-history-{projectId}-{agentFilename|'general'}`

```json
{
  "sessionId": "kommandr-uuid",
  "providerSessionId": "claude-cli-uuid-or-codex-thread-id-or-null",
  "provider": "claude",
  "model": "opus",
  "mode": "agent",
  "agentFilename": "planner.md-or-null",
  "messages": [{ "id": "uuid", "role": "user|assistant|system", "content": "...", "timestamp": "ISO" }],
  "savedAt": "ISO"
}
```

The key is agent-scoped (not provider-scoped). `provider`, `model`, and `mode` are saved into the value so the UI can restore the user's last choice even though two different providers share the same storage key.

Saved by `$effect` in `ChatSheet.svelte` whenever messages change and streaming has stopped, **and** explicitly inside the `provider_session_id` stream handler so the id is persisted as soon as it's captured (before the first turn completes).

`loadChatHistory()` returns `{ sessionId, messages, meta: { providerSessionId, provider, model, mode, agentFilename } }`. Callers that mock this function in tests must supply the `meta` field (even if just `{ providerSessionId: null }`).

## Codex app-server Protocol Notes

Generate TS bindings for the wire protocol with:
```bash
codex app-server generate-ts --out /tmp/codex-schema
```

Relevant RPC methods used by the adapter:
- `initialize` → `initialized` — handshake.
- `thread/start` (`ThreadStartParams`) — creates a new thread, returns `threadId`. Accepts `baseInstructions`/`developerInstructions` but they only apply at thread-open time, so we also prepend on every turn.
- `thread/resume` (`ThreadResumeParams`) — **used for cross-restart resume**. Loads a thread from disk by `threadId`. Requires `persistExtendedHistory: boolean` (false is fine). Optional overrides for `model`, `cwd`, `approvalPolicy`, `sandbox` — we re-apply these because they are per-session, not per-thread.
- `turn/start` (`TurnStartParams`) — run a turn against the existing thread. No system-prompt field; agent prompt is prepended to the user text in `<system-instructions>…</system-instructions>`.
- `turn/cancel` (notification) — cancel an in-flight turn.

## Codex-Specific: Init Promise

The Codex adapter's `sendMessage()` waits for `ctx.initPromise` to resolve before dispatching `turn/start`. This handles the ~1 second window between session creation and thread initialization. Without this, messages sent immediately after session creation would fail with "Thread not initialized." The same init promise gates both the `thread/start` (new) and `thread/resume` (restart) paths.
