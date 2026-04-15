---
updated: 2026-04-14
---

# Markdown Rendering in Svelte Components

When user-visible text may contain markdown (Claude/Codex responses, question prompts, issue descriptions, etc.), render it through `renderMarkdownSafe`. Rendering raw text will display `**bold**` and `1. 2. 3.` as literal characters, which looks broken.

## The Helper

`src/lib/sanitize-html.ts` exposes one function:

```ts
import { renderMarkdownSafe } from '$lib/sanitize-html';
// renderMarkdownSafe(content: string): string
```

It runs `marked(content)` → `DOMPurify.sanitize(...)`. Safe to drop into `{@html ...}`.

## Usage Pattern

```svelte
<script lang="ts">
  import { renderMarkdownSafe } from '$lib/sanitize-html';
</script>

<div class="some-text">{@html renderMarkdownSafe(text)}</div>
```

**Do NOT put `{@html ...}` inside an `<h1>`–`<h6>`.** marked wraps content in `<p>` tags by default, and block elements inside heading tags are invalid HTML. Use a `<div>` (or `<section>`) container and style it to look heading-like if needed.

## Required CSS (Svelte scoping gotcha)

Svelte scopes component CSS, so markdown-generated elements (`<p>`, `<strong>`, `<ol>`, etc.) have no styling applied — you must declare rules with `:global(...)`. Tailwind/app.css preflight also resets `list-style` on `ol`/`ul`, so numbered/bulleted lists render with no markers unless you re-enable it.

Minimum rule set for a reasonable look (paragraphs, bold/italic, lists, inline/block code):

```css
.some-text :global(p) { margin: 0 0 12px 0; }
.some-text :global(p:last-child) { margin-bottom: 0; }
.some-text :global(strong) { font-weight: 700; }
.some-text :global(em) { font-style: italic; }
.some-text :global(ol), .some-text :global(ul) {
  margin: 8px 0 12px 0;
  padding-left: 24px;
}
.some-text :global(ol) { list-style: decimal; }
.some-text :global(ul) { list-style: disc; }
.some-text :global(li) { margin: 4px 0; }
.some-text :global(li > p) { margin: 0; }
.some-text :global(code) {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 0.88em;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f3f4f6;
}
.some-text :global(pre) {
  margin: 8px 0;
  padding: 12px;
  border-radius: 8px;
  background: #f3f4f6;
  overflow-x: auto;
  font-size: 13px;
}
.some-text :global(pre code) { padding: 0; background: transparent; }
```

## Consumers (current)

Components already using this pattern — copy their style blocks when adding a new consumer:

- `src/components/ChatMessage.svelte` — assistant chat bubbles (has light-on-dark variant for user bubbles)
- `src/components/ExplanationChat.svelte`
- `src/components/ClaudeQuestionPanel.svelte` — wizard-style question prompts
- `src/components/TaskRunnerPanel.svelte`
- `src/components/SessionEventLog.svelte`
- `src/components/SessionEventDetail.svelte`
- `src/components/IssueDetailSheet.svelte`
- `src/components/AgentEditSheet.svelte`
- `src/components/MarkdownEditor.svelte`

## When NOT to Use

- Field values rendered as-is in form inputs or badges — no markdown expected.
- Preformatted CLI/log output where you want monospace + newline preservation without parsing — use `<pre>{text}</pre>` directly.
- Single-line labels (issue titles, button text) — marked will wrap in a `<p>`, which may add unwanted margin.
