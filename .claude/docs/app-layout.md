---
updated: 2026-04-09
---

# App Layout Structure

## Layout Hierarchy

```
+layout.svelte (root)
  → TitleBar (dark, 28px, sticky)
  → ClaudeUpdateBanner
  → children

(protected)/+layout.svelte
  → Auth guard (redirects to /login if unauthenticated)
  → .app-shell (flex row):
      → SideNav (dark sidebar, 240px / 52px collapsed)
      → .main-content (flex: 1, overflow: auto)
          → page content
```

## SideNav Component (`src/components/SideNav.svelte`)

Dark sidebar (`#1a1a1a`) that visually connects with the dark titlebar, creating an L-shaped frame.

**Features:**
- Collapsible "Projects" section with chevron toggle (like Claude Console)
- Each project shows folder icon, name, colored issue count badges (blue=open, amber=in-progress)
- Active project has blue left-accent border + highlight background
- Full sidebar collapse to 52px icon-only rail
- Collapse state persisted in `localStorage` key: `beads-sidenav-collapsed`
- Footer: Add Project, Settings, Sign Out links
- Auto-fetches project list, polls every 15s
- Active project derived from URL: `/projects/[id]` pattern match

**Props:**
- `collapsed: boolean` — whether sidebar is in icon-only mode
- `oncollapse: (collapsed: boolean) => void` — callback when collapse state changes

## Viewport Height Management

The `(protected)/+layout.svelte` `.app-shell` manages the full viewport height:
```css
.app-shell {
  display: flex;
  height: calc(100vh - var(--titlebar-height, 28px));
  overflow: hidden;
}
```

**Important:** Individual pages use `min-height: 100%` (NOT `calc(100vh - titlebar)`), since the layout's `.main-content` div already constrains the height and provides scrolling.

## Navigation

All back-links (← Projects, ← Back) were removed from individual pages — the sidebar handles all top-level navigation:
- Dashboard: `/` (home icon)
- Projects: listed in collapsible section
- Add Project: `/projects/add` (plus icon in footer)
- Settings: `/settings` (gear icon in footer)
- Sign Out: logout button in footer

## Routes Under Protected Layout

| Route | Page |
|-------|------|
| `/` | Dashboard — project grid with cards |
| `/projects/add` | Add/create project wizard |
| `/projects/[id]` | Project workspace (tabs: Board, Epics, Agents, History) |
| `/settings` | Global settings (MCP, hooks, Claude config) |
