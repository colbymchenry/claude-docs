---
updated: 2026-04-10
---

# Multi-Provider Adapter Architecture

## Overview

Kommandr supports multiple AI coding CLI providers (Claude Code, OpenAI Codex, etc.) through a pluggable adapter pattern in `src/lib/providers/`. All consumers (chat-manager, task-runner, scaffold-manager, check-done-manager) route through the registry instead of importing `claude-cli.ts` directly.

## Key Files

| File | Purpose |
|------|---------|
| `src/lib/providers/types.ts` | All interfaces: `ProviderAdapter`, `ProviderSession`, `ProviderOutputChunk`, `ProviderStatus`, `ProviderKind` |
| `src/lib/providers/registry.ts` | `registerAdapter()`, `getAdapter(kind)`, `getDefaultProvider()`, `closeAllProviderSessions()` |
| `src/lib/providers/detection.ts` | `detectBinary(name, customPath?, managedPath?)` — finds CLIs on system |
| `src/lib/providers/claude/adapter.ts` | `ClaudeAdapter` — wraps `claude-cli.ts`, `claude-code-manager.ts`, `claude-auth.ts` |
| `src/lib/providers/codex/adapter.ts` | `CodexAdapter` — full implementation: spawn CLI, parse NDJSON, manage sessions |
| `src/lib/providers/index.ts` | `initProviders()` — registers all adapters, re-exports types |

## Detection Priority

`detectBinary()` checks in this order for each provider:
1. **Custom path** — `settings.providers.<kind>.binaryPath` (user-configured)
2. **System PATH** — `which <binaryName>` (e.g., `which claude`, `which codex`)
3. **Managed install** — `~/.kommandr/bin/claude` (Claude only, via GCS download)

The result includes `source: 'custom' | 'system' | 'managed'` so the UI can show where the binary was found.

## How Consumers Use It

```typescript
import { initProviders, getAdapter, getDefaultProvider } from './providers';
import type { ProviderSession, ProviderOutputChunk } from './providers';

initProviders(); // Safe to call multiple times

const adapter = getAdapter(getDefaultProvider()); // or getAdapter('claude')
const session = adapter.createSession({ projectPath, model: 'opus', ... });
adapter.sendMessage(session, message, onData, onError, onClose);
adapter.cancelResponse(session);
adapter.closeSession(session);
```

## Chat UI Provider Selection (Phase 4)

Users can pick which provider to use when starting a chat session:

- **ChatSheet.svelte** — owns `selectedProvider` state (`ProviderKind`), fetches available providers from `GET /api/providers/status?all=true` on mount, passes list down to ChatInput
- **ChatInput.svelte** — shows a provider dropdown (only when 2+ providers are available) alongside the mode and model dropdowns. Changing provider resets the model to the first available for that provider. Props: `provider` (bindable), `providerLocked`, `availableProviders: ProviderStatus[]`
- **chat-session.svelte.ts** — `ChatSessionDeps.getProvider()` returns the selected `ProviderKind`. `startSession()` sends `provider` in the POST body to `/api/projects/{id}/chat`
- **ChatModel type** — widened from `'opus' | 'sonnet' | ...` to `string` to support any provider's model slugs
- **Agent frontmatter** — `provider: codex` in an agent's YAML frontmatter auto-selects and locks that provider in the UI. The `providerLocked` flag prevents the user from switching.

Model list is dynamic: `ChatInput` derives models from `availableProviders.find(p => p.provider === selectedProvider).models`.

## Codex Adapter (Phase 5)

The `CodexAdapter` in `src/lib/providers/codex/adapter.ts` is a full implementation:

### CLI Invocation
Each `sendMessage()` spawns a new process:
```
codex --quiet --output-format json --model <model> --approval-mode <mode> <message>
```

Key flags:
- `--quiet` — non-interactive scripting mode
- `--output-format json` — NDJSON output for structured parsing
- `--approval-mode full-auto` (agent mode) or `suggest` (plan/ask mode)
- `--conversation-id <id>` — for multi-turn continuation (captured from first response)
- `--instructions <prompt>` — agent system prompt (first message only)

### Output Parsing
Inline `parseCodexLine()` function normalizes Codex NDJSON events to `ProviderOutputChunk`:

| Codex Event | ProviderOutputChunk Type |
|---|---|
| `{ type: "message", content }` | `text` |
| `{ type: "function_call", name, arguments }` | `tool_use` |
| `{ type: "function_call_output", output }` | `tool_result` |
| `{ type: "error", message }` | `error` |
| `{ type: "status", status }` | `status` |
| `{ type: "thinking", content }` | `thinking` |
| `{ type: "usage"/"done", input_tokens, ... }` | `done` (with usage stats) |

### Auth Detection
`detect()` checks auth via:
1. Running `codex auth status` (5s timeout)
2. Falling back to checking `OPENAI_API_KEY` env var

### Session Management
- Sessions stored in a module-level `Map<string, ProviderSession>`
- `cancelResponse()` sends SIGINT with SIGKILL fallback after 3s
- `closeAllSessions()` terminates all active processes

## Model Styles

`src/lib/agents-client.ts` `modelStyles` contains badge colors for all providers:

| Provider | Model Slugs | Color Theme |
|---|---|---|
| Claude | `opus`, `opus[1m]`, `sonnet`, `sonnet[1m]`, `haiku` | Amber/blue/green |
| Codex | `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5.2` | Indigo/violet |

`getModelStyle(slug)` returns label + bg + color; falls back to `sonnet` style for unknown slugs.

## Adding a New Provider

1. Create `src/lib/providers/<name>/adapter.ts` implementing `ProviderAdapter`
2. Add the kind to `ProviderKind` union in `types.ts` (e.g., `'claude' | 'codex' | 'gemini'`)
3. Register in `src/lib/providers/index.ts`
4. Add `<name>?: ProviderSettings` to `AppSettings.providers` in `settings.ts`
5. Add model badge styles to `modelStyles` in `agents-client.ts`
6. The adapter must implement: `detect()`, `createSession()`, `sendMessage()`, `cancelResponse()`, `closeSession()`, `closeAllSessions()`
7. Optional: `auth` (login/logout/status) and `installer` (managed install/update)

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

## API Endpoints

- `GET /api/providers/status?all=true` — Runs `detect()` on all adapters, returns `ProviderStatus[]`
- `GET/PUT /api/settings/providers` — Read/write provider settings and default provider
- `POST /api/projects/[id]/chat` — Accepts `provider` in body to select which provider to use

## Backward Compatibility

- `claude-cli.ts` is unchanged — the Claude adapter wraps it
- `chat-manager.ts` exports `getOrCreateClaudeProcess` as an alias for `getOrCreateProcess`
- `closeClaudeSession` is an alias for `closeProviderSession`
- The `/api/claude-code/*` endpoints remain for Claude-specific install/update/login flows

## Roadmap

Tracked in `MULTI-PROVIDER-ROADMAP.md` at repo root. Phases 1-5 are implemented. Remaining: manual testing for Phase 4/5, and Future Providers section documents the pattern for adding more.
