---
updated: 2026-04-14
---

# ui-component-stack

---
updated: 2026-04-14
---

# UI Component Stack

This project uses **shadcn-svelte** — the Svelte port of shadcn/ui. Components are copied into the project (not installed as a package).

## Core Dependencies

| Package | Version | Role |
|---------|---------|------|
| `bits-ui` | ^2.17.3 | Headless component primitives (shadcn-svelte builds on this) |
| `tailwindcss` | ^4.2.2 | Utility-first CSS framework (v4) |
| `@tailwindcss/vite` | ^4.2.2 | Tailwind Vite plugin |
| `tailwind-merge` | ^3.5.0 | Deduplicates/merges Tailwind classes |
| `tailwind-variants` | ^3.2.2 | Variant-based class composition |
| `@lucide/svelte` | ^1.8.0 | Icon library (newer package) |
| `lucide-svelte` | ^1.0.1 | Icon library (legacy package, both present) |
| `formsnap` | ^2.0.1 | Form handling integration for shadcn-svelte |
| `svelte-sonner` | ^1.1.0 | Toast notifications (used via shadcn `Toaster` + `toast()` — see `NotificationToastListener.svelte`) |

## shadcn-svelte Configuration (`components.json`)

| Setting | Value |
|---------|-------|
| Style | `nova` |
| Base color | `stone` |
| Icon library | `lucide` |
| TypeScript | `true` |
| Registry | `https://shadcn-svelte.com/registry` |
| CSS file | `src/app.css` |
| UI components path | `$lib/components/ui` |
| Utils path | `$lib/utils` |
| Hooks path | `$lib/hooks` |

Add new components via: `npx shadcn-svelte@latest add <component>`

## Component Location

shadcn-svelte components live in `src/lib/components/ui/` — ~50+ component directories, each with small Svelte files and an `index.ts` barrel export.

## Adoption Convention

**Prefer shadcn-svelte wrappers over custom reimplementations.** Before building a custom button, modal, dropdown, avatar, empty-state, badge, etc., check `src/lib/components/ui/` — nearly every shadcn-svelte primitive is already installed.

**Import path rule:** always import from `$lib/components/ui/<name>` — never from `bits-ui` directly. The shadcn wrapper applies the project's Tailwind styling layer; using bits-ui raw bypasses it.

**Common reinvention patterns to avoid** (each has a shadcn primitive already installed):
- Modals / sheets / drawers → `Dialog`, `AlertDialog`, `Sheet`, `Drawer`
- Floating panels with backdrop + click-outside → `Popover`, `DropdownMenu`
- Status pills / chips / tags → `Badge`
- Avatar circles with initials fallback → `Avatar` + `AvatarFallback`
- "No items yet" blocks → `Empty`
- List items with icon + title + description → `Item`
- Border-top/bottom dividers → `Separator`
- `animate-pulse` placeholder blocks → `Skeleton`
- CSS-border spinners (`border-top-color + animation: spin`) → `Spinner`
- Hidden `<input type="radio">` with `:has(input:checked)` styling → `RadioGroup` or `ToggleGroup`
- View switchers (list/grid/kanban buttons) → `ToggleGroup`
- Searchable selects / autocomplete → Combobox (Popover + Command)
- Inline styled `<kbd>` → `Kbd`
- Scrollable divs with `::-webkit-scrollbar` CSS → `ScrollArea`
- Toast notifications → `Toaster` + `toast()` from `svelte-sonner` (replaced the old custom `ToastContainer`)

## Component API Notes (pitfalls worth knowing)

### Tailwind v4 CSS-variable syntax: use parens, NOT brackets

Tailwind v4 introduced a dedicated shorthand for referencing CSS custom properties as utility values: `w-(--foo)`, `bg-(--foo)`, etc. The v3-era bracket form `w-[--foo]` is still parsed by v4 but Chrome now emits a deprecation warning in the console:

```
[Deprecation] Custom state pseudo classes have been changed from ":--bits-dropdown-menu-anchor-width" to ":state(bits-dropdown-menu-anchor-width)".
```

This is because in v4 the bracket form is interpreted against the browser's custom-state selector grammar, which the CSSWG is renaming from `:--foo` to `:state(foo)`. Always use the parens form:

```svelte
<!-- WRONG (v3 syntax, triggers Chrome deprecation warning) -->
<DropdownMenu.Content class="w-[--bits-dropdown-menu-anchor-width]" />

<!-- RIGHT (v4 syntax) -->
<DropdownMenu.Content class="w-(--bits-dropdown-menu-anchor-width)" />
```

The shadcn wrappers in `src/lib/components/ui/` already use the parens form — only our own call sites slip back to brackets when ported from tutorials or older code. `bits-ui` exposes anchor-sized CSS variables like `--bits-dropdown-menu-anchor-width` and `--bits-select-trigger-width` that are commonly referenced this way.

### DOM-ref pattern: `bind:ref`, NOT `bind:this`

`Input`, `Textarea`, `Button`, and most input-like shadcn components expose the underlying DOM node via a `$bindable` `ref` prop, not through `bind:this`. `bind:this` on a Svelte *component* binds the component instance, not the inner `<input>`/`<textarea>` — so methods like `.focus()`, `.setSelectionRange()`, or `.selectionStart` won't be available.

```svelte
<!-- WRONG: binds the component instance, not the DOM element -->
<Textarea bind:this={textareaEl} />

<!-- RIGHT: exposes the underlying HTMLTextAreaElement -->
<Textarea bind:ref={textareaEl} />
```

Declare the local state as `HTMLInputElement | null` / `HTMLTextAreaElement | null` to match the `ref = $bindable(null)` default in the shadcn wrapper. `undefined` won't widen correctly in tsc.

### `Input` / `Textarea` — overriding default styling

Both components ship with an opinionated look: `h-8` (Input) or `min-h-16` (Textarea), `border`, `rounded-lg`, `px-2.5`, focus ring, and a *dark-mode* background `dark:bg-input/30`. When embedding the control in a parent that already provides its own border, padding, or focus ring, you have to strip all of that through the `class` prop.

Minimum overrides for an "embedded / transparent" look:

```
border-0 h-auto rounded-none p-0 bg-transparent dark:bg-transparent shadow-none focus-visible:ring-0 focus-visible:border-0
```

Notes:
- `bg-transparent` alone is not enough — `dark:bg-input/30` still applies in dark mode. Always pair with `dark:bg-transparent`.
- The focus ring is three classes (`focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:border-ring`) — `focus-visible:ring-0` plus `focus-visible:border-0` suppresses all three via tailwind-merge.
- For a `Textarea` with custom sizing, include `min-h-0` to defeat `min-h-16`.
- `cn()` uses `tailwind-merge`, so arbitrary values (`text-[#d1d5db]`, `selection:bg-blue-500/30`) merge cleanly with defaults.

### Custom classes passed to shadcn children cause "Unused CSS selector" warnings

If you write `<Input class="my-class" />` and define `.my-class { ... }` in the parent's `<style>`, `svelte-check` flags it as an unused selector. Svelte's CSS scoping hash lives on elements *rendered by this component's template*, but the `<input>` lives inside the child component and receives the class via prop — no scope hash is added. Two acceptable fixes:

1. **Prefer:** express the styling with Tailwind utilities in the `class` prop directly (`flex-1` instead of `.my-class { flex: 1 }`).
2. If you truly need raw CSS, wrap the selector in `:global(...)` so scoping is bypassed.

### `Button`

- `size="icon-xs" | "icon-sm" | "icon-lg"` gives `size-6 | size-7 | size-9` square buttons. For a 36px icon button use `size="icon-lg"`.
- `variant="ghost"` + explicit background/text overrides is the right recipe when you need an "off-brand" colored button (e.g. white-on-dark banner buttons). Don't reach for `variant="outline"` unless you actually want a border.
- Button has `active:not(aria-[haspopup]):translate-y-px` in its base — the press animation is inherited for free, don't reimplement it.
- **Base classes include `whitespace-nowrap`** — any text inside the Button (including children multiple levels deep, like an `.option-desc` span in a row layout) inherits it and will overflow horizontally instead of wrapping. When you use `<Button>` as a multi-line list row (label + description stacked), explicitly override on the inner wrapper:
  ```css
  .option-content { white-space: normal; overflow-wrap: anywhere; }
  .option-label, .option-desc { white-space: normal; overflow-wrap: anywhere; }
  ```
  `overflow-wrap: anywhere` is the safety net for unbroken strings (URLs, long tokens). Symptom: text gets clipped at the button's right edge with no ellipsis. Seen in `ClaudeQuestionPanel.svelte` option rows.

### Migrating raw `<button>` to `<Button>` — scoping convention

The repo has an in-progress migration of custom `<button class="...">` elements to `<Button>` tracked in `SHADCN-MIGRATION.md`. The mechanical rules below apply to every file in that migration.

**Import + swap:**

```svelte
import { Button } from '$lib/components/ui/button/index.js';
```

Replace `<button class="...">` with `<Button variant="ghost" class="...">` in almost all cases. Use `variant="destructive"` / `"secondary"` only when the original visual is a solid filled state. For toggles, fold conditional classes into the `class` prop as a template literal instead of `class:active={...}`:

```svelte
<!-- BEFORE -->
<button class="tab" class:active={mode === 'edit'} onclick={...}>Edit</button>

<!-- AFTER -->
<Button variant="ghost" class="tab {mode === 'edit' ? 'active' : ''}" onclick={...}>Edit</Button>
```

**Scoped-style rewrite (the load-bearing part):** the original rule `.tab { ... }` in the parent's `<style>` won't match, because `<Button>` renders its `<button>` in the *child* component — the parent's Svelte scope hash is never applied to that element. Cross-file class names like `.action-btn`, `.close-btn`, `.tab`, `.back-btn`, `.nav-btn` are also used in 3–5 files each, so blanket `:global(.action-btn)` would collide across components.

The convention: anchor every rule under a parent class that IS in the component's own template, then wrap the button class in `:global(...)`. The parent class gets the Svelte scope hash (isolating it per-component), and the `:global()` wrapper lets the selector reach across the component boundary to the actual rendered `<button>`:

```css
/* BEFORE — works when .nav-btn is a raw <button> in this file */
.nav-btn { width: 28px; height: 28px; border-radius: 6px; }
.nav-btn:hover:not(:disabled) { background: #374151; }

/* AFTER — .url-bar is a div in this component's template */
.url-bar :global(.nav-btn) { width: 28px; height: 28px; border-radius: 6px; padding: 0; }
.url-bar :global(.nav-btn:hover:not(:disabled)) { background: #374151; }
```

When writing these rules, also drop these now-meaningless declarations: `cursor: pointer` (Button handles it), `font-family` (inherits), `justify-content` unless specifically needed (Button's default is `center`).

**Default overrides you usually need to add:**

- `padding: 0;` — Button's default padding (`px-4 py-2`) overrides narrow button styling.
- `height: auto;` — Button's base `h-9` fights custom heights like `28px`.
- `border-radius: 0;` — Button's default `rounded-md` leaks through when you want square/pill corners.
- `font-weight: 400;` — Button's `font-medium` overrides inherited weights.
- `justify-content: flex-start;` — Button centers content by default, but most migrated rows are left-aligned.
- **Explicit hover color reset** when your `:hover` changes background — the ghost variant also sets a hover background, and without an explicit override the two stack visibly. For dark-themed buttons (e.g. a pill on a dark surface), add a matching `:hover` rule to re-assert your background/color.

**Cross-boundary descendant selectors:** if a selector combines a parent-scope class with a button class that now lives on the child component, the combinator crosses the scope boundary — wrap the whole right-hand side in `:global()` or restructure the selector:

```css
/* BEFORE — .entry-running on parent <div>, .entry-row on raw <button>, both parent-scoped */
.entry-running .entry-row { background: rgba(34, 197, 94, 0.04); }

/* AFTER — .entry-row is now in child scope, needs :global() */
.entry-running :global(.entry-row) { background: rgba(34, 197, 94, 0.04); }

/* Same issue with descendants under the migrated button — scope by a parent-template class */
/* BEFORE */
.task-item :global(.task-chevron) { color: #cccccc; }
/* AFTER — .task-item moved to child scope; anchor on .task-list which stays in parent */
.task-list :global(.task-item .task-chevron) { color: #cccccc; }
```

**Top-level standalone buttons need a wrapper:** if the migrated button is a sibling at the root of the template with no surrounding element, Svelte has no parent-scoped class to anchor the `:global()` rule to. Wrap it in a semantic div:

```svelte
{#if isExpanded}
  <div class="backdrop-wrap">
    <Button variant="ghost" class="backdrop" onclick={...} aria-label="Close"></Button>
  </div>
{/if}

<style>
  .backdrop-wrap :global(.backdrop) { position: fixed; inset: 0; background: transparent; /* ... */ }
  .backdrop-wrap :global(.backdrop:hover) { background: transparent; } /* kill ghost hover */
</style>
```

**Verify with `npx tsc --noEmit` after each batch.** The project's TypeScript check is the gating verification (per user convention) — there is no `svelte-check` binary installed.

### `Spinner` (`src/lib/components/ui/spinner/spinner.svelte`)

- Defaults: `size-4` (16px) + `animate-spin`, renders Lucide `Loader2` icon.
- Override size with a Tailwind class: `<Spinner class="size-10 text-blue-600" />`.
- **Does NOT accept `strokeWidth`.** The component destructures `stroke` (as a color-adjacent alias from some icon libraries) but `strokeWidth` is not a recognized prop and tsc will reject it with `Object literal may only specify known properties`. If you want a thicker stroke, either pass `stroke={...}` (color) or wrap `Loader2Icon` directly.
- Set color via text color classes (`text-white`, `text-[#3b82f6]`) — Lucide icons inherit `currentColor`.

### `ScrollArea` (`src/lib/components/ui/scroll-area/`)

- Renders `ScrollAreaPrimitive.Root` (wrapper) + `ScrollAreaPrimitive.Viewport` (the actual scrollable element) + `Scrollbar`.
- **`{...restProps}` goes to Root, NOT Viewport.** This means `onscroll={handler}` on the `<ScrollArea>` component will NOT fire when the user scrolls — the scroll event is on the Viewport. To listen for scroll events, `bind:viewportRef={yourRef}` and attach the listener in a `$effect`:
  ```svelte
  let viewportRef: HTMLElement | null = $state(null);
  $effect(() => {
    if (!viewportRef) return;
    viewportRef.addEventListener('scroll', handleScroll);
    return () => viewportRef?.removeEventListener('scroll', handleScroll);
  });
  ```
- For programmatic scroll (`scrollTop = scrollHeight`), use `bind:viewportRef` — do NOT use `bind:this` (that binds the Root wrapper, which isn't scrollable).
- `orientation` prop: `"vertical"` (default), `"horizontal"`, or `"both"` for dual-axis.
- Override scrollbar styling with `scrollbarYClasses` / `scrollbarXClasses` props (e.g., `scrollbarYClasses="w-1"` for a narrower bar).
- Padding/background on the scrollable area goes inside the viewport — wrap children in a `<div class="py-2">` rather than trying to style the Root.

### `Empty` (`src/lib/components/ui/empty/`)

- Structure: `Empty.Root > Empty.Header > (Empty.Media, Empty.Title, Empty.Description)` with optional `Empty.Content` sibling for action buttons.
- `Empty.Root` defaults to `p-6 gap-4 border-dashed flex w-full min-w-0 flex-1 flex-col items-center justify-center text-center`. The `border-dashed` has no `border-*` width, so no visible border — safe to adopt without unwanted outlines.
- `Empty.Media` has `variant="icon"` (size-8 muted-bg rounded square) vs `variant="default"` (bare).
- For floating/overlay empty states (e.g. over an SVG graph), **wrap `Empty.Root` in a positioning `<div>`** rather than putting `absolute` classes on `Empty.Root` itself — its `flex-1 w-full` defaults fight absolute positioning.
- Preserve spin animations with `class="animate-spin"` on the inner icon (don't rely on old `.icon.loader` selectors — feather-icons doesn't emit that class).

## Intentionally Custom (Do NOT "simplify" to shadcn)

Some components deliberately don't use the shadcn equivalent. If you're tempted to refactor these, read the reason first:

- **`src/components/SideNav.svelte`** — Custom app sidebar, NOT shadcn `Sidebar`. Has project list with issue count badges, folder icons, localStorage-persisted collapse state, URL-derived active project. shadcn `Sidebar` is overkill for this bespoke UX. (See `app-layout.md` for details.)
- **`src/components/TaskGraph.svelte`** — Custom SVG dependency graph with zoom/pan. NOT a `Chart` use case — shadcn `Chart` is for bar/line/pie visualizations via layerchart. Task dependencies are a graph, not a chart.
- **`TaskRunnerPanel.svelte` epic progress bar** — Custom, not shadcn `Progress`. Encodes failed-task states alongside completion percentage; domain-specific.
- **`TaskRunnerPanel.svelte` structural container borders** (`.panel-header`, `.epic-progress`, `.floating-todos`, `.complete-footer`) — border-top/bottom applied as container CSS, tightly coupled to padding/bg/conditional color variants (`.complete-footer.success` changes border color). Do NOT replace with `<Separator />` — would require DOM restructure and lose the color variants.
- **`ChatInput.svelte` message input** — Uses `contenteditable` div, not `Textarea`. Intentional for rich-input behavior (mentions, slash commands, attachments). The *file input* inside this component IS migrated (template-declared hidden `<Input type="file">`) — don't confuse the two.
- **Wizard/stepper flows** (`ClaudeQuestionPanel.svelte`, `CreateProjectWizard.svelte`, `ScaffoldingProgress.svelte`) — Step-by-step forms with dot navigators. NOT a `Carousel` use case.

## Project-Specific Extensions

These are non-default props/behaviors added on top of the stock shadcn-svelte components. If the prop isn't documented here or in the source, it doesn't exist upstream.

### `Dialog.Content` props

`src/lib/components/ui/dialog/dialog-content.svelte` extends Bits UI's `DialogPrimitive.Content` with three project-specific props:

| Prop | Default | Effect |
|------|---------|--------|
| `fullscreen` | `false` | Replaces the centered modal sizing with `fixed inset-0 w-screen h-screen overflow-hidden` and skips rendering the overlay backdrop. Used for full-window experiences (Live Edit mode). |
| `showCloseButton` | `true` | Renders the corner X button. Disabled when `fullscreen` regardless. |
| `keepMounted` | `false` | Keeps the dialog (and its overlay) mounted after `open` flips to false instead of unmounting. Hides via `data-closed:invisible data-closed:pointer-events-none` so layout (and any iframes/webviews inside) is preserved with no reload. **Use when inner state must survive a dismiss/reopen** — e.g. `LiveEditMode` keeps its `ChatSheet` session and `DevServerPreview` webview alive across modal close cycles. Without this, every reopen creates fresh component instances and re-runs init flows. |

When `keepMounted` is set, the consumer should NOT also tear down inner state in an `isOpen` `$effect` close branch — that defeats the persistence. Cleanup belongs in the component's destroy hook (`$effect` with a return function) so it only fires when the parent component itself unmounts (e.g. route navigation). See `LiveEditMode.svelte` for the canonical pattern.

## Key Notes

- Tailwind v4 uses the new `@tailwindcss/vite` plugin (not PostCSS-based like v3)
- Two Lucide icon packages are present (`@lucide/svelte` and `lucide-svelte`) — prefer `@lucide/svelte` for new code
- `bits-ui` provides the accessible, unstyled primitives; shadcn-svelte adds Tailwind styling on top
- Forms in modals/sheets typically use direct `Input`/`Label`/`Textarea` imports rather than the formsnap-based `form/` wrappers (see `superforms-zod-validation.md`)
- `SHADCN-MIGRATION.md` at repo root tracks the ongoing audit of custom UI that should migrate to shadcn primitives
