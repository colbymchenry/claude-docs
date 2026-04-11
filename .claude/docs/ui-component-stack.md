---
updated: 2026-04-10
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
| `svelte-sonner` | ^1.1.0 | Toast notifications |

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

## Key Notes

- Tailwind v4 uses the new `@tailwindcss/vite` plugin (not PostCSS-based like v3)
- Two Lucide icon packages are present (`@lucide/svelte` and `lucide-svelte`) — prefer `@lucide/svelte` for new code
- `bits-ui` provides the accessible, unstyled primitives; shadcn-svelte adds Tailwind styling on top