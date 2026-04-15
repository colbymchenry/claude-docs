---
updated: 2026-04-13
---

# kommandr_ask_user — MCP Round-Trip & Freeze Debugging

How the `mcp__kommandr__kommandr_ask_user` MCP tool blocks the agent while the UI collects answers, and how to diagnose a chat that appears "frozen" on **Thinking…**.

## The Round-Trip

Unlike most kommandr MCP tools (which return immediately), `kommandr_ask_user` intentionally **blocks the agent's stdin** until the user answers in the UI. The provider CLI is stuck at the tool_use — no error, no output, no timeout.

```
Claude CLI  ──tool_use──▶  kommandr MCP server (node subprocess)
                                    │
                                    │ HTTP POST /api/projects/[id]/ask-user
                                    ▼
                           SvelteKit ask-user handler
                                    │
                                    ├─ pendingQuestions.set(questionId, { sessionId, resolve })
                                    ├─ broadcastToSession(sessionId, { type: 'ask_user', questionId, questions })
                                    │
                                    │ (HTTP response held open)
                                    ▼
                             Frontend renders modal
                                    │
                                    │ user submits answers
                                    │ POST /api/projects/[id]/ask-user/[questionId]/answer
                                    ▼
                               resolve(answers)  ◀── unblocks the held POST
                                    │
                                    │ HTTP response returns answers to MCP server
                                    ▼
                           MCP server returns tool_result to Claude CLI
                                    │
                                    ▼
                              Agent continues
```

The whole thing hinges on **one in-flight HTTP request** that the SvelteKit endpoint deliberately doesn't reply to until `resolve()` is called.

## Key Files

| File | Role |
|------|------|
| `src/lib/chat-manager.ts` (~line 60–85) | Owns `pendingQuestions: Map<questionId, { sessionId, resolve }>`. Stores the resolve fn, broadcasts SSE `type: 'ask_user'`. |
| `src/routes/api/projects/[id]/ask-user/+server.ts` | POST from MCP server. Creates the pending entry and returns `await new Promise(resolve => …)`. |
| `src/routes/api/projects/[id]/ask-user/[questionId]/answer/+server.ts` | POST from frontend. Looks up `pendingQuestions.get(questionId)`, calls `resolve(answers)`, deletes the entry. |
| `src/lib/claude-cli.ts` | Declares `'ask_user'` in the `ClaudeOutputChunk.type` union (line ~56) but doesn't emit it directly — the SSE broadcast is what the client sees. |
| kommandr MCP server (separate process, started per-session) | Posts to `/ask-user`, waits for the HTTP response, returns it as the MCP tool_result. |

Also `cancelSessionResponse()` in `chat-manager.ts:272+` iterates `pendingQuestions` and calls `resolve({ cancelled: true })` **before** cancelling the adapter — otherwise the MCP tool keeps the HTTP response open and the agent's stdin can't drain. Preserve that order if you touch cancellation.

## Frozen-Chat Diagnostic Recipe

UI symptom: the chat sits on **"Claude Code is working… Thinking…"** after an agent was clearly making progress (tool calls visible in the action list, then nothing).

### 1. `~/.kommandr/logs/claude-cli.log` — find the last tool_use

The file is huge because every `[STDOUT RAW]` is one long line of JSON. Avoid cat — use line-ranged awk with a truncation, e.g.:

```bash
awk 'NR>=N {print NR": "substr($0,1,300)}' ~/.kommandr/logs/claude-cli.log
```

Tail until you find a `[PARSED CHUNK]: {"type":"tool_use",…}` with **no matching `tool_result` after it**. If the `toolName` is `mcp__kommandr__kommandr_ask_user`, that's the freeze.

Useful markers in this log:
- `[TURN] assistant tool_use after tool_result gap=Nms` — agent issued a tool call
- `[TURN] tool_result received | pid=…` — tool call completed
- The absence of the second line after a tool_use is the freeze signature

### 2. `~/.kommandr/logs/api.log` — check the pending question

Grep for `[ask-user]`. Each successful round-trip produces two lines:
```
[ask-user] POST session=<sid> count=<n>
[ask-user] answer questionId=<qid> delivered=true cancelled=false
```

A lone `POST` with **no matching `answer` line** = the user never saw or never submitted the modal.

### 3. `~/.kommandr/logs/mcp-server.log` — confirm transport

Look for `ask-user request failed` or `Fetch failed (network/transport)` near the incident time. These indicate the MCP server couldn't reach the SvelteKit endpoint at all (e.g., during a server restart) — different failure mode from "posted but not answered."

## Failure Modes

| Evidence | Cause |
|----------|-------|
| `api.log` has `[ask-user] POST` but no `answer`; `mcp-server.log` clean | MCP → server POST succeeded; SSE broadcast fired; frontend didn't render the modal. Bug is client-side (stream handler, modal component, or SSE not subscribed for this session). |
| `mcp-server.log` shows `Fetch failed (network/transport)` on `/ask-user` | Server was down/restarting when the tool fired. Usually self-heals on next prompt. |
| `claude-cli.log` shows the `ask_user` tool_use, `api.log` has **no** matching `[ask-user] POST` | kommandr MCP server didn't forward it — check that the MCP server subprocess is alive and reachable on 127.0.0.1:5555. |
| Cancelling the chat leaves the agent stuck anyway | `cancelSessionResponse` didn't resolve `pendingQuestions` first — restore the ordering at `chat-manager.ts:272+`. |

## Do-Not-Break Invariants

- The `/ask-user` POST handler **must** return a promise that only resolves when the frontend posts an answer (or cancellation resolves it). Returning early turns `kommandr_ask_user` into a no-op and the agent gets a meaningless tool_result.
- SSE broadcast (`type: 'ask_user'`) uses the **Kommandr session id** (e.g. `dcf9e089-…`), not the provider's internal session id (e.g. Claude's `019ac3b0-…` seen in `[PARSED CHUNK]` lines). The two id spaces show up side-by-side in logs — don't conflate them when matching.
- Cancellation order: resolve `pendingQuestions` with `{ cancelled: true }` **before** calling the adapter's cancel. Reversing this order can deadlock stdin.
