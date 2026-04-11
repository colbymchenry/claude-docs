---
updated: 2026-04-09
---

# Epic Runner Session Lifecycle & Known Issues

## How Epic Execution Works

**Key files:**
- `src/lib/task-runner-manager.ts` — orchestration, session management, completion handling
- `src/lib/task-runner-store.ts` — in-memory state, SSE broadcasting
- `src/lib/task-prompt-builder.ts` — prompt construction, completion signal detection
- `src/components/TaskRunnerPanel.svelte` — frontend panel with SSE connection

**Flow:**
1. `startTaskRun()` creates ONE Claude session (process) for the entire epic
2. Calls `executeNextEpicTask()` → `executeTask()` for each child task sequentially
3. Claude signals completion via text patterns: `TASK_COMPLETED:`, `AWAITING_INPUT:`, `TASK_BLOCKED:`
4. `detectCompletionSignal()` (regex in task-prompt-builder.ts) parses these from output chunks
5. `handleCompletionSignal()` advances the epic via `setTimeout(1000)` to `executeNextEpicTask()`
6. Status polling (every 2s) also detects completion if the issue status changes to `closed`
7. `completionHandled` Set guards against double-firing from both polling and signal

## Race Condition Fix (2026-04-09)

**Problem:** Claude's process can exit between epic tasks. `handleClaudeClose()` would delete the session from `claudeSessions` Map. The pending `executeNextEpicTask()` (scheduled 1s later) would then fail with "No Claude session".

**Fix applied:**
1. `handleClaudeClose()` now checks for epic runs with remaining tasks. If exit code 0, returns silently (session will be recreated). If non-zero, fails only the current task and continues the epic.
2. `executeTask()` now auto-creates a new Claude session if the existing one is gone (common during epic transitions).
3. `agentPrompts` Map stores agent prompts by run ID so they survive session recreation (previously lost because `handleCompletionSignal` didn't pass agentPrompt when calling `executeNextEpicTask`).

## Session Creation Parameters

When recreating a session in `executeTask()`, these params are used:
- `effort: 'max'`, `thinking: 'enabled'`, `maxTurns: 100`
- `strictMcpConfig: true` with MCP config from `buildTaskRunnerMcpConfig()`
- Settings from `buildTaskRunnerSettings()` for hooks filtering
- Agent prompt from `agentPrompts` Map

## Known Pre-existing Bugs

1. **`taskRunnerStore.updateRun()` doesn't exist** — called at line ~418 in the `auth_expired` handler but the store doesn't export this method. Would throw at runtime if auth expires during a task run.
2. **`agentPrompt` was silently dropped** in several `executeNextEpicTask()` call sites within `handleCompletionSignal()` (completed and blocked cases). Fixed by having `executeNextEpicTask()` look up the prompt from the `agentPrompts` Map instead of taking it as a parameter.

## Module-level State Maps

- `claudeSessions: Map<string, ClaudeSession>` — active Claude processes by run ID
- `statusPollers: Map<string, NodeJS.Timeout>` — polling intervals by run ID
- `completionHandled: Set<string>` — guards against double completion (`runId:taskIndex`)
- `agentPrompts: Map<string, string>` — agent prompts by run ID (added 2026-04-09)

All are cleaned up in `stopRun()` and `cleanup()`.
