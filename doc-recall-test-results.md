# Documentation Recall Test Results

**Date:** 2026-04-10
**Project tested:** beads-live-dashboard
**Method:** `claude -p "<prompt>" --output-format stream-json --verbose` — parsed tool calls from stream output
**Tests:** 8 prompts (5 planning/explanation, 3 implementation), 3 noise prompts

## Final Results

**8/8 passed.** All tests pass both criteria:
1. Hook injects the correct full doc content as `additionalContext`
2. Claude does NOT create duplicate docs via `save_doc`

| Test | Type | Expected Doc | Injected | No Dup | Verdict |
|------|------|-------------|----------|--------|---------|
| forms-planning | plan | `ui/forms-and-validation` | PASS | PASS | PASS |
| chat-architecture | plan | `chat/architecture` | PASS | PASS | PASS |
| electron-packaging | plan | `electron/ssr-bundling-and-packaging` | PASS | PASS | PASS |
| dev-server | plan | `dev-server/tmux-management` | PASS | PASS | PASS |
| shadcn-components | plan | `ui/shadcn-svelte-setup` | PASS | PASS | PASS |
| add-form-impl | impl | `ui/forms-and-validation` | PASS | PASS | PASS |
| event-system-impl | impl | `architecture/events-and-epic-lifecycle` | PASS | PASS | PASS |
| agent-frontmatter | impl | `ui/agent-edit-sheet` | PASS | PASS | PASS |

**Noise test:** 3 unrelated prompts ("Fix the typo in the README", "How do I rebase?", "What is the meaning of life?") correctly inject 0 docs.

## Context Cost Per Prompt

| Prompt | Docs | Doc Tokens | Total Tokens |
|--------|------|------------|-------------|
| forms-planning | 1 | ~1,234 | ~1,800 |
| chat-architecture | 1 | ~1,006 | ~1,572 |
| electron-packaging | 1 | ~589 | ~1,155 |
| dev-server | 2 (both correct) | ~1,612 | ~2,183 |
| shadcn-components | 2 (1 noise) | ~2,156 | ~2,726 |
| add-form-impl | 1 | ~1,234 | ~1,800 |
| event-system-impl | 2 (1 noise) | ~1,438 | ~2,009 |
| agent-frontmatter | 1 | ~672 | ~1,238 |
| noise prompts | 0 | 0 | ~507 |

**Worst case:** ~2,700 tokens. **Baseline** (listing only): ~507 tokens. Well under 1% of context.

## Evolution: v1 -> v2

### v1: "Tell Claude to call lookup_doc" (0/8 passed)

The hook injected a directive: `IMPORTANT: Before starting this task, call the claude-docs MCP tool lookup_doc...`

Claude ignored this 100% of the time. It called `semantic_search_docs` on its own, got content snippets, and considered that sufficient. The stop hook triggered `save_doc` in 6/8 tests, creating duplicate docs.

### v2: Inject full doc content directly (8/8 passed)

The hook reads the full doc content from disk and injects it as `additionalContext`. No intermediary tool call needed.

**Key changes:**

1. **`query.py`** — Reads and outputs full `.md` file content for matched topics instead of truncated snippets. Gap filter (0.10) prevents weak secondary matches from bloating context.

2. **`hooks/claude-docs-on-prompt.sh`** — Injects docs with: `"These docs already exist in .claude/docs/. Do NOT create new docs that overlap with these."`

3. **`server.py` `_auto_index_if_needed()`** — Fixed to check each doc on disk against indexed topics (was skipping entirely when collection had any docs).

4. **`server.py` `chunk_document()`** — Fixed duplicate chunk ID crash when docs have repeated header names. Slugs now include parent h2 context with counter fallback.

## Architecture

```
User prompt
    |
    v
hooks/claude-docs-on-prompt.sh (UserPromptSubmit hook)
    |
    +--> query.py --list (doc tree listing)
    |
    +--> query.py (semantic search via ChromaDB)
    |        |
    |        +--> Reads full .md file for each matched topic
    |        +--> Gap filter: only topics within 0.10 of top score
    |
    v
additionalContext with full doc content
(injected into Claude's context, no tool call needed)
```

## Reproducing

```bash
# Quick hook-only check (instant, no API calls)
echo '{"prompt":"<your prompt>","cwd":"/path/to/project"}' | bash hooks/claude-docs-on-prompt.sh

# Full end-to-end test (runs claude -p, costs API credits)
bash /tmp/test-doc-recall-v2.sh
```

## Test Prompts

```bash
# Planning
"How should I implement a new settings form with validation in this project? Just explain the approach, don't make changes."
"Explain how the chat system works — how does a message go from the user to Claude and back? Don't make changes."
"What do I need to know about bundling and packaging for Electron in this project? Just explain, don't change anything."
"How does the dev server detection and tmux management work? Just explain."
"What UI component library does this project use and how is it set up? Just explain."

# Implementation
"Add a new form component at src/lib/components/UserSettingsForm.svelte that lets users edit their display name and email with Zod validation. Use the project's existing patterns."
"Add a new event type 'tag_added' to the events system. Show me where it needs to be registered."
"Add a new field 'temperature' to the agent frontmatter schema. Where do I need to make changes?"
```
