---
updated: 2026-04-14
---

# task-runner/epic-session-lifecycle

---
updated: 2026-04-14
---

# Epic Runner Session Lifecycle & Known Issues

## How Epic Execution Works

**Key files:**
- `src/lib/task-runner-manager.ts` — orchestration, session management, completion handling
- `src/lib/task-runner-store.ts` — in-memory state, socket broadcasting
- `src/lib/task-prompt-builder.ts` — prompt construction, completion signal detection
- `src/components/TaskRunnerPanel.svelte` — frontend panel with socket connection

**Flow:**
1. `startTaskRun()` creates ONE Claude session (process) for the epic run; epic children run sequentially through it
2. `executeNextEpicTask()` → `executeTask()` for each child task; `executeTask()` **auto-recreates the session** if the subprocess is gone (see line ~244)
3. Claude signals completion via text patterns parsed by `detectCompletionSignal()` (`task-prompt-builder.ts:268`): `TASK_COMPLETED:`, `AWAITING_INPUT:`, `TASK_BLOCKED:`
4. `handleCompletionSignal()` advances the epic via `setTimeout(1000)` → `executeNextEpicTask()`
5. `startStatusPolling()` (line ~704) also checks every 2s whether the current issue flipped to `closed`; if so, it calls `handleCompletionSignal(runId, 'completed', …)` as a backstop
6. `completionHandled` Set (keyed `runId:taskIndex`) guards against double-firing from signal + polling

## Completion Signal Now Closes the Issue (fixed 2026-04-13)

When Claude emits `TASK_COMPLETED:`, `handleCompletionSignal('completed')` does:
1. **Calls `store.updateIssue(currentTaskId, { status: 'closed' })`** if the issue isn't already closed (`task-runner-manager.ts:504-511` for epic branch, `539-546` for single-task branch)
2. Calls `store.notifyChange()` + `await store.refresh()` so the SSE stream's `getDataVersion()` poll picks up the change and broadcasts to EpicsView + KanbanColumn
3. Updates the in-memory `taskRunnerStore` (chat panel reflects completion)
4. Calls `notifyTaskCompleted()` (notification bell)
5. For epics: advances `epicSequence.currentIndex`, schedules `executeNextEpicTask()` 1s later
6. For single tasks: calls `terminateSession(runId)`, `removeActiveTask(runId)`

The earlier "Critical Gap" (signal fired but issue stayed open in DB, so Kanban/Epic UI didn't reflect completion) is resolved.

## Race: Subprocess Keeps Emitting After TASK_COMPLETED (epic path)

**Symptom:** While running a TaskRunner on an Epic, the UI shows "Task completed successfully" green banner while new tool_use actions (Read, Terminal, Edit) keep appearing in the action list below.

**Cause:** `handleCompletionSignal('completed')` in the **epic subtask branch** (`task-runner-manager.ts:491-529`) never calls `terminateSession(runId)`. It only stops status polling, updates progress, and schedules `executeNextEpicTask()` on a 1-second `setTimeout`. The Claude subprocess stays alive and keeps streaming `tool_use` chunks for that ~1s (plus stdout flush). Those chunks arrive via `handleClaudeOutput` → `addEvent`, so they render in the panel.

For the **final** subtask of an epic, this is especially visible: after the 1s delay, `executeNextEpicTask()` hits the "all tasks done" branch at `task-runner-manager.ts:335-353`, which broadcasts `status: 'completed'` *and* calls `terminateSession(runId)`. But the events emitted during the race window are already in the UI, so the banner appears alongside "still-happening" actions.

Contrast: the single-task branch (`task-runner-manager.ts:530-561`) terminates the session immediately at line 552, so this race doesn't exist there.

**Fix:** Call `terminateSession(runId)` in the epic `'completed'` branch (right after `stopStatusPolling` at line 514) and mirror in the epic `'blocked'` branch (line ~582). `executeTask()` already auto-recreates a fresh session for the next subtask (line 244-277), so this is safe. The comment at `task-runner-manager.ts:90-94` and `339-343` describes the same failure mode and is the guiding rationale.

## Session Close Handling

`handleClaudeClose()` (line 643):
1. If the run is an epic with remaining tasks (`currentIndex < taskIds.length`):
   - exit code 0 → log and return (expected between-tasks close; next subtask's `executeTask` will recreate)
   - non-zero → fail the current task, advance index, `setTimeout(1000)` → `executeNextEpicTask()`
2. Otherwise (single task, or epic past the last task) and run is still `running`:
   - exit code 0 → `updateStatus('completed', 'Session ended normally')`
   - non-zero → `updateStatus('failed', …)`
   - notify + remove active task

## Session Creation Parameters

When `executeTask()` creates or recreates a session:
- `effort: 'max'`, `thinking: 'enabled'`, `maxTurns: 100`
- `strictMcpConfig: true` with MCP config from `buildTaskRunnerMcpConfig()`
- Settings from `buildTaskRunnerSettings()` for hook filtering
- `agentPrompt` restored from `agentPrompts` Map (survives session recreation across epic transitions)

## Subprocess Termination Helpers

- `terminateSession(runId)` (`task-runner-manager.ts:96`) — calls `adapter.cancelResponse()` (SIGINT + 3s SIGKILL fallback, `claude-cli.ts:850`) then `adapter.closeSession()` (`removeAllListeners` + `killProcess`, `claude-cli.ts:912`), then deletes from `providerSessions`. Safe to call when the session is already gone.
- Must be called at every terminal transition (`completed` / `blocked` / `failed`). The comment at line 90-94 documents this requirement explicitly.

## Module-level State Maps

- `providerSessions: Map<string, ProviderSession>` — active provider sessions by run ID (renamed from `claudeSessions` when the provider adapter was introduced)
- `statusPollers: Map<string, NodeJS.Timeout>` — polling intervals by run ID
- `completionHandled: Set<string>` — guards against double completion (`runId:taskIndex` or `runId:single`)
- `agentPrompts: Map<string, string>` — agent prompts by run ID, for session-recreation restore

All are cleaned up in `stopRun()` and `cleanup()`.

## Frontend Status Broadcasts

The "Task completed successfully" banner in `TaskRunnerPanel.svelte:718-728` triggers off `status === 'completed'`. Status changes come from the backend via two message types:
- `{ type: 'status', status, reason }` — emitted by `updateRunStatus` (`task-runner-store.ts:140`)
- `{ type: 'state', run }` — full run snapshot on reconnect

`{ type: 'epic_progress', epicSequence }` (emitted by `updateEpicProgress`) does NOT change the top-level status — it only updates `epicSequence` on the frontend. So advancing through subtasks doesn't trigger the completion banner; only the final-epic-done or single-task-done paths do.

## Multi-Process Live Updates Caveat (PostgreSQL)

Single SvelteKit process: `notifyChange()` increments an in-memory `changeCounter` that the SSE stream's `getDataVersion()` poll picks up. Task Runner writes reach the stream consumer because both share the cached `PostgresProjectStore` instance from `getProjectStore()`.

**Breaks across instances.** Other dashboards writing the same Postgres database don't bump our `changeCounter`. The Postgres triggers `pg_notify('kommandr_changes', ...)`, but the `LISTEN` consumer isn't wired yet (deferred in `PLUGGABLE-STORAGE.md`).
