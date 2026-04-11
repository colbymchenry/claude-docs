---
updated: 2026-04-09
---

# codegraph_explore Limitations

## What explore is good at
- Finding named code symbols (functions, classes, components, variables, methods)
- Showing source code around those symbols with contiguous sections
- Mapping relationships between symbols (calls, imports, extends, etc.)
- Graph traversal from entry points through call chains

## What explore cannot find

### CSS / Styling
CSS custom properties (`--color-primary`), style rules, and theme definitions are NOT extracted as graph nodes. They live in `<style>` blocks and `.css` files that tree-sitter parses but CodeGraph doesn't create symbol nodes for. Agents must fall back to grep/read for CSS exploration.

### Filesystem conventions
Framework conventions like SvelteKit's `+layout.svelte`, `+page.svelte`, route groups `(protected)/`, and Next.js `app/` directory routing are filesystem patterns, not named symbols. The graph has `file` and `component` nodes but searching for "layout" doesn't convey the routing/nesting concept.

### UI/design concepts
Terms like "sidebar", "navigation", "theme", "dark mode" are UI concepts that rarely map to specific symbol names. Explore's search (`findRelevantContext` in `src/context/index.ts:284`) works by:
1. Extracting potential symbol names from the query (`extractSymbolsFromQuery`)
2. Looking up exact name matches in the DB
3. Running FTS text search against node names/paths
4. BFS graph traversal from matched entry points

Generic UI terms match too many unrelated symbols or none at all.

### Template markup
Svelte `{#if}`, `{#each}`, slot composition, and HTML structure aren't extracted as named symbols. Component *usages* in templates are captured as edges (the explore handler queries outgoing edges at line 822 to include template references), but the structural HTML around them is only visible by reading the full file.

## Workaround for broad exploration queries
For design/layout/theming questions, agents should:
1. Use `codegraph_explore` with **component names** (e.g., "TitleBar ProjectCard") not concepts
2. Fall back to glob/grep for CSS files, layout files, and route structure
3. Read full Svelte files when template structure matters (not just script block symbols)