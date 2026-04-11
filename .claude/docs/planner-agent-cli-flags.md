---
updated: 2026-04-10
---

# Planner Agent: Native Agent Definition

## Architecture

The planner is defined as a **native Claude Code agent** via the `--agents` JSON flag + `--agent` flag, not as a file on disk. This prevents users from editing the agent definition and leverages Claude Code's built-in agent system for tool restriction enforcement.

### How It Works

1. `+server.ts` builds the agent definition as a JSON object with `prompt`, `tools`, `mcpServers`, `model`, `hooks`, `maxTurns`
2. Passed to Claude CLI via `--agents '<json>'` on the first message
3. `--agent planner` selects it as the main session agent
4. Subsequent messages use `--resume <sessionId>` to continue

### Agent Definition (built in `+server.ts`)

```json
{
  "planner": {
    "description": "Plan features and create Kommandr epics with tasks...",
    "prompt": "<planner system prompt from getPlannerSystemPrompt()>",
    "tools": ["Read", "Glob", "Grep", "AskUserQuestion"],
    "model": "opus",
    "color": "purple",
    "mcpServers": [{"kommandr": {"type": "stdio", "command": "node", "args": ["<path>/kommandr-server.mjs"], "env": {"KOMMANDR_PROJECT_PATH": "..."}}}],
    "hooks": {},
    "maxTurns": 50
  }
}
```

### Key Behavioral Properties

- **`tools`**: Only read-only built-in tools + AskUserQuestion. Edit, Write, Bash are NOT available.
- **`mcpServers`**: Kommandr MCP server defined inline, scoped to the agent. Additional servers only if user explicitly enables them.
- **`hooks: {}`**: Disables all hooks for the planner session.
- **`prompt`**: The planner system prompt (from `getPlannerSystemPrompt()`) that defines planning-only behavior.
- **`--allowed-tools`**: Still passed separately to pre-approve `mcp__kommandr__*` tools without permission prompts.

### Why Not `--bare`?

`--bare` would prevent CLAUDE.md from loading but **breaks OAuth authentication**:
> "Bare mode skips OAuth and keychain reads. Anthropic authentication must come from `ANTHROPIC_API_KEY` or an `apiKeyHelper`."

Since Kommandr uses OAuth (`CLAUDE_CODE_OAUTH_TOKEN` env var), `--bare` is incompatible.

### Why Native Agents Over `--system-prompt-file`?

The previous approach used `--system-prompt-file` to replace the default prompt + `--tools` to restrict capabilities. Problems:
1. `--system-prompt-file` replaces the default system prompt but **CLAUDE.md still loads**, giving the planner implementation context
2. Tool restrictions via `--tools` are flag-level, not agent-level enforcement
3. The agent kept offering to "make edits" despite prompt instructions saying not to

Native agents via `--agents`:
- Agent's `prompt` field is the ONLY system prompt the agent sees
- Agent's `tools` field restricts capabilities at the agent system level
- `mcpServers` scopes MCP access inline without needing `--mcp-config` + `--strict-mcp-config`
- No file on disk for users to edit

### Files Involved

- `src/lib/kommandr-instructions.ts` — `getPlannerSystemPrompt()` and `getPlannerAgentContent()`
- `src/routes/api/projects/[id]/chat/+server.ts` — Builds agent definition JSON, accepts `provider` param in POST body
- `src/lib/claude-cli.ts` — `agentDefinitions` and `mainAgentName` options, `--agents`/`--agent` flag generation (internal to Claude adapter)
- `src/lib/chat-manager.ts` — `getOrCreateProcess()` routes to the correct provider adapter via `src/lib/providers/registry.ts`
- `src/lib/providers/claude/adapter.ts` — Claude adapter wraps `claude-cli.ts` behind `ProviderAdapter` interface
