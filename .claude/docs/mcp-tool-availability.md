---
updated: 2026-04-09
---

# MCP Tool Availability

## Active Tools (as of 2026-04-09)

Only 2 of 9 MCP tools are currently enabled in `src/mcp/tools.ts`:

| Tool | Status | Line |
|------|--------|------|
| `codegraph_status` | **Active** | 93 |
| `codegraph_explore` | **Active** | 103 |
| `codegraph_search` | Commented out | 126 |
| `codegraph_context` | Commented out | 148 |
| `codegraph_callers` | Commented out | 173 |
| `codegraph_callees` | Commented out | 196 |
| `codegraph_impact` | Commented out | 213 |
| `codegraph_node` | Commented out | 233 |
| `codegraph_files` | Commented out | 255 |

## Impact

The `tools` array (line 92) only includes `codegraph_status` and `codegraph_explore`. All other tools are commented out in the array but their handlers still exist in `ToolHandler.execute()` (line 410-436) and work if called.

### Key gap: No discovery step
The CLAUDE.md recommends "search first, then explore" but `codegraph_search` is disabled. Agents using `codegraph_explore` must guess symbol names without a discovery tool, leading to vague queries and poor results.

### Handlers still wired up
The `execute()` switch statement (line 412) still routes all tool names to their handlers. Re-enabling a tool only requires uncommenting it in the `tools` array — no handler changes needed.

## Explore Budget

`getExploreBudget()` at line 23:
- <500 files → 1 call
- <5000 files → 2 calls
- <15000 files → 3 calls
- <25000 files → 4 calls
- 25000+ files → 5 calls

## Explore Output Limit

`ToolHandler.EXPLORE_MAX_OUTPUT` caps character output (checked at line 874, 792). The `handleExplore` method reads contiguous file sections around discovered symbols, clustering nearby symbols within a 15-line gap threshold.