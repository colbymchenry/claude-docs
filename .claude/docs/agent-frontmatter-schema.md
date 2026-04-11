---
updated: 2026-04-10
---

# Agent Frontmatter Schema: Field Wiring Guide

Adding or modifying an agent frontmatter field requires changes across multiple files. This doc maps every touchpoint.

## Files to modify (in order)

### 1. TypeScript interface — `src/lib/types.ts`
The `AgentFrontmatter` interface (around line 77) defines the shape. Add the new field here with its TypeScript type.

Note: `AgentFrontmatter` has `[key: string]: unknown` as a catch-all, so unrecognized YAML keys won't break parsing — but they won't have type safety either.

### 2. Zod validation schema — `src/lib/schemas/agent.ts`
The `agentSchema` z.object defines form validation. All fields are stored as **strings** in the form (even numeric ones like `maxTurns`). Use `.refine()` for numeric validation. The inferred type is `AgentFormData`.

### 3. Edit sheet UI — `src/components/AgentEditSheet.svelte`
Six spots need updating:

| Location | What to do |
|----------|-----------|
| `managedKeys` Set (~line 39) | Add the field name string so it's not treated as an "unmanaged" preserved field |
| `defaults()` call (~line 56) | Add field with empty string default |
| `$effect` block (~line 81) | Map `frontmatter.<field>` → `$form.<field>` (handle type conversion) |
| `handleCancel()` (~line 222) | Same mapping as above (resets form on cancel) |
| `saveChanges()` (~line 163) | Map `$form.<field>` back to `frontmatter.<field>` (parse strings back to numbers, arrays, etc.) |
| Advanced auto-expand `$effect` (~line 262) | Add `$form.<field>` to the condition if it belongs in the Advanced section |
| Template HTML | Add the actual input control in the Advanced `<Collapsible.Content>` section |

### 4. CLI integration — `src/lib/claude-cli.ts`
- The `ClaudeSessionOptions` interface (~line 55) holds session config
- CLI args are built in `buildClaudeArgs()` (~line 310) — add `--<flag>` if the CLI supports it
- The `createClaudeSession()` function (~line 130) destructures options and passes them through

### 5. Chat session creation — `src/routes/api/projects/[id]/chat/+server.ts`
Where agent frontmatter fields are read and passed into `createClaudeSession()`. Check that the new field is forwarded.

## Current fields

| Field | TS Type | Zod Type | CLI Flag |
|-------|---------|----------|----------|
| `name` | `string` | `z.string().min(1)` | N/A (display only) |
| `description` | `string?` | `z.string().default('')` | N/A (display only) |
| `model` | `string?` | `z.string().default('')` | `--model` |
| `provider` | `string?` | `z.string().default('')` | Provider adapter selection |
| `color` | `string?` | `z.string().default('')` | N/A (display only) |
| `allowedTools` | `string[]?` | `z.string().default('')` (newline-separated) | `--allowed-tools` |
| `disallowedTools` | `string[]?` | `z.string().default('')` (newline-separated) | `--disallowed-tools` |
| `maxTurns` | `number?` | `z.string().default('').refine(1-25)` | `--max-turns` |
| `permissionMode` | `string?` | `z.string().default('')` | `--permission-mode` |
| `apiKeyEnvVar` | `string?` | `z.string().default('')` | Sets env var |
| `mcpServers` | `AgentMcpConfig?` | Not in Zod (managed separately via toggle UI) | `--mcp-config` |

## Key patterns

- **Numeric fields** are stored as strings in the Zod schema/form, converted with `parseInt()` or `parseFloat()` in `saveChanges()`, and converted back with `String()` in the `$effect`/`handleCancel` blocks.
- **Array fields** (allowedTools, disallowedTools) are stored as newline-separated strings in the form, converted with `linesToArray()`/`arrayToLines()` helpers.
- **mcpServers** is special — it bypasses Zod entirely and is managed via a separate toggle UI with `serverToggles` state.
- **Unmanaged fields** (any YAML key not in `managedKeys`) are preserved in `preservedFields` and merged back via `Object.assign(frontmatter, preservedFields)` in `saveChanges()`.

## Parsing flow

```
.md file → parseFrontmatter() [agents-client.ts] → AgentFrontmatter object
                                                          ↓
AgentEditSheet $effect → maps to $form (all strings)
                                                          ↓
saveChanges() → reconstructs AgentFrontmatter → serializeAgent() → YAML .md file
```
