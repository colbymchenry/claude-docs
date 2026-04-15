---
updated: 2026-04-11
---

# HMR and Module Reload State Persistence

## Problem

The SvelteKit server re-evaluates modules during its lifecycle. This happens in TWO scenarios:

1. **Dev mode (Vite HMR)**: Any code change triggers module hot-replacement
2. **Production (DMG/Electron)**: The SvelteKit production server re-evaluates route handler modules ~10-15 minutes after startup, even without an Electron restart. The exact trigger is unknown but the pattern is consistent in logs.

When modules re-evaluate, any `const map = new Map()` at module scope creates a **new empty Map**, orphaning all state from the previous module instance.

## Affected State

These Maps hold critical runtime state that must survive module reloads:

| File | Map | Contains |
|------|-----|----------|
| `src/lib/chat-manager.ts` | `providerProcesses` | Active provider sessions (child processes) |
| `src/lib/chat-manager.ts` | `sseControllers` | SSE stream controllers for live broadcasts |
| `src/lib/session-store.ts` | `sessions` | Chat session metadata, message history |
| `src/lib/providers/registry.ts` | `adapters` | Provider adapter registry (claude, codex) |
| `src/lib/providers/codex/adapter.ts` | `sessions`, `contexts` | Codex JSON-RPC session contexts |
| `src/lib/claude-cli.ts` | `sessions` | Claude CLI session tracking |

## Solution: globalThis with Symbol.for()

Store Maps on `globalThis` using `Symbol.for()` keys. `Symbol.for()` returns the same Symbol across module instances (it uses a global registry), so the Map persists across re-evaluations within the same Node.js process.

```typescript
// Pattern: HMR-safe module-level Map
const GLOBAL_KEY = Symbol.for('kommandr:my-module');
const myMap: Map<string, Foo> = (() => {
  const g = globalThis as Record<symbol, Map<string, Foo> | undefined>;
  if (!g[GLOBAL_KEY]) {
    g[GLOBAL_KEY] = new Map();
  }
  return g[GLOBAL_KEY]!;
})();
```

For grouped state, use an interface:

```typescript
interface MyModuleState {
  mapA: Map<string, X>;
  mapB: Map<string, Y>;
}

const GLOBAL_KEY = Symbol.for('kommandr:my-module');
function getGlobalState(): MyModuleState {
  const g = globalThis as Record<symbol, MyModuleState | undefined>;
  if (!g[GLOBAL_KEY]) {
    g[GLOBAL_KEY] = { mapA: new Map(), mapB: new Map() };
  }
  return g[GLOBAL_KEY]!;
}

const mapA = getGlobalState().mapA;
const mapB = getGlobalState().mapB;
```

## When This Does NOT Help

- Full Electron process restart (quit + relaunch): `globalThis` resets with the process
- SvelteKit server child process restart: same — entire process memory is gone

For those cases, the client handles reconnection via `reconnectToSession()` and the `startNewChat()` fallback.

## Diagnostic Evidence

Log evidence showing module re-evaluation in production (DMG):
- `chat-manager.ts module loaded` fires ~2x per Electron start PLUS extra times 10-15 min later
- Electron log shows restarts at specific times; extra module loads happen between restarts
- When module re-evaluates, `sessionStore.get(id)` returns undefined for existing sessions, causing 404 on message POST
