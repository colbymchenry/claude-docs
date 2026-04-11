---
updated: 2026-04-10
---

# Chat Session Lifecycle & SSE Stream Management

How the planner/agent chat sidebar manages sessions, SSE streams, and reconnection.

## Key Files

| File | Role |
|------|------|
| `src/lib/chat-session.svelte.ts` | Client-side session state factory (reactive Svelte 5 runes) |
| `src/components/ChatSheet.svelte` | Sidebar UI, lifecycle effects for open/close, provider selection |
| `src/components/ChatInput.svelte` | Input area with provider/mode/model dropdowns |
| `src/lib/chat-manager.ts` | Server-side provider process management + SSE broadcast (routes through `src/lib/providers/registry.ts`) |
| `src/lib/providers/registry.ts` | Maps `ProviderKind` → `ProviderAdapter`, routes session calls to correct provider |
| `src/lib/session-store.ts` | In-memory server-side session store (30min timeout), uses `ProviderSession` type |
| `src/lib/chat-history.ts` | localStorage persistence for messages + sessionId |
| `src/routes/api/projects/[id]/chat/+server.ts` | POST creates new session (accepts `provider` in body) |
| `src/routes/api/projects/[id]/chat/[sessionId]/stream/+server.ts` | GET SSE stream endpoint |
| `src/routes/api/projects/[id]/chat/[sessionId]/status/+server.ts` | GET session existence check |

## Session Creation Flow

1. `ChatSheet` mounts → `createChatSession()` factory creates reactive state with `getProvider` dep
2. `$effect` fires when `isOpen=true` → `loadHistory()` (localStorage) → `fetchProviders()` → `checkInitialization()`
3. `fetchProviders()` calls `GET /api/providers/status?all=true`, filters to installed+enabled, stores in `availableProviders` state
4. `checkInitialization()` calls `/api/providers/status` to verify at least one AI provider is available
5. If providers available and project initialized, no `sessionId`: `startSession()` POSTs to `/api/projects/{id}/chat` with `{ provider, model, mode, agentFilename }` → server creates session in `sessionStore` + spawns provider process via `getOrCreateProcess(provider)`
6. `getOrCreateProcess()` resolves `provider ?? getDefaultProvider()`, looks up the adapter from registry, calls `adapter.createSession()`
7. Client receives `sessionId` → `connectToStream(sid)` creates `EventSource` to SSE endpoint

## Provider Selection

### UI Flow
- `ChatSheet` owns `selectedProvider: ProviderKind` state (default `'claude'`)
- `ChatInput` shows a provider dropdown **only when 2+ providers are available** (`availableProviders.length > 1`)
- Changing provider resets the model to the first available for the new provider via `selectProvider()`
- The model dropdown is dynamic — derived from `availableProviders.find(p => p.provider === selectedProvider).models`

### Agent Frontmatter Override
- If `agent.frontmatter.provider` is set (e.g., `provider: codex`), `ChatSheet` auto-selects that provider
- `providerLocked = true` prevents the user from changing it in the dropdown
- If the agent also specifies `model`, that's auto-selected too; otherwise defaults to the provider's first model

### Type: ChatModel
`ChatModel` is `string` (not a narrow union) to support model slugs from any provider. Examples: `'opus'`, `'sonnet[1m]'`, `'gpt-5.4'`, `'gpt-5.4-mini'`.

### ChatSessionDeps Interface
```typescript
interface ChatSessionDeps {
  getProjectId: () => string;
  getAgent: () => Agent | null;
  getProvider: () => ProviderKind;  // Added for multi-provider
  getMode: () => ChatMode;
  getModel: () => ChatModel;       // string, not narrow union
  getEmbedded: () => boolean;
  getLivePreviewUrl: () => string | null;
  getCurrentNavigationUrl: () => string | null;
  getIsOpen: () => boolean;
}
```

## Provider Routing

`chat-manager.ts` no longer imports `claude-cli.ts` directly. All calls go through the provider registry:
- `getOrCreateProcess(sessionId, projectId, provider?, ...)` — looks up adapter, calls `adapter.createSession()`
- `sendMessageToProcess(sessionId, message)` — looks up session's `provider` field, calls `adapter.sendMessage()`
- `cancelSessionResponse(sessionId)` — calls `adapter.cancelResponse()`
- `closeProviderSession(sessionId)` — calls `adapter.closeSession()`

Backward-compatible aliases exist: `getOrCreateClaudeProcess`, `closeClaudeSession`.

## SSE Architecture

- **Server**: `registerSSEController()` adds a `ReadableStreamDefaultController` to a per-session Set
- **Broadcasting**: `broadcastToSession()` sends JSON chunks (`ProviderOutputChunk`) to all registered controllers
- **Client**: `EventSource.onmessage` parses chunks via `handleStreamMessage()` which updates reactive state
- **Reconnect on error**: `onerror` retries after 3s if sidebar is still open (`deps.getIsOpen()`)

## Close/Reopen Reconnection

When the sidebar closes:
1. `handleClose()` → `chat.closeEventSource()` (kills SSE) → `onclose()` (sets `isOpen=false`)
2. `$effect` sees `isOpen=false` → after 300ms animation: `chat.resetState(true)` nulls `sessionId` and resets flags, but preserves `messages`
3. The `saveHistory` effect has already saved both `messages` AND `sessionId` to localStorage
4. Server-side: provider process keeps running, session stays in `sessionStore`

When the sidebar reopens:
1. `$effect` fires with `isOpen=true` → `loadHistory()` restores messages AND `sessionId` from localStorage
2. `fetchProviders()` refreshes the available providers list
3. `checkInitialization()` sees `sessionId` exists → calls `reconnectToSession(sid)`
4. `reconnectToSession()` fetches `/status` endpoint to verify session still exists on server
5. If valid: sets `claudeReady=true`, calls `connectToStream(sid)` to re-register SSE controller
6. If 404 (session expired/gone): nulls `sessionId`, falls back to `startSession()`
7. SSE stream endpoint replays `session.messageHistory` on connect, deduped client-side by message ID

## Server-Side Session Lifecycle

- `sessionStore` (in-memory Map) keeps sessions for 30 minutes of inactivity
- `providerProcesses` Map in `chat-manager.ts` keyed by sessionId — deleted when process exits (`onClose`)
- Provider process can finish while session still exists (tasks still on board, messages in history)
- `startNewChat()` creates a fresh session and clears localStorage history

## localStorage Schema

Key format: `chat-history-{projectId}-{agentFilename|'general'}`

```json
{
  "sessionId": "uuid",
  "messages": [{ "id": "uuid", "role": "user|assistant|system", "content": "...", "timestamp": "ISO" }],
  "savedAt": "ISO"
}
```

Saved by `$effect` whenever messages change and streaming has stopped (`!chat.isStreaming`).
