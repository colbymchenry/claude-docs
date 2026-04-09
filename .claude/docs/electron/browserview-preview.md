---
updated: 2026-04-08
---

# Electron BrowserView Preview

## How the Preview Works

The live edit preview uses Electron's `BrowserView` — a native view that renders independently from the web content DOM. This is managed by `electron/preview-manager.ts`.

Key files:
- `electron/preview-manager.ts` — Creates and manages the `BrowserView` instance
- `src/components/DevServerPreview.svelte` — DOM container that tracks bounds for the BrowserView
- `electron/preload.ts` — Exposes IPC: `showPreview()`, `hidePreview()`, `setPreviewBounds()`

## Critical: BrowserView Paints Above DOM

BrowserView is a **native OS-level view**, not a DOM element. It always renders on top of all web content regardless of CSS `z-index`. This means:

- **DOM overlays (modals, tooltips, dropdowns) cannot cover the BrowserView area.** Any fixed/absolute positioned DOM element will appear behind the native preview.
- **The logs panel works differently than you'd expect.** `ServerLogsPanel` appears to overlay the preview, but actually it takes space in the flex layout, which shrinks the `.preview-content` container. A `ResizeObserver` on the container fires `updatePreviewBounds()`, which calls `setPreviewBounds()` via IPC to resize the native BrowserView. The preview shrinks to make room — it's not overlaid.

## Positioning UI Near the Preview

When adding modals or overlays in `LiveEditMode`:

1. **Don't center fixed modals on the full screen** — the dialog will land behind the BrowserView.
2. **Position modals over the chat panel area** (right side) where there's only DOM content. Use `justify-content: flex-end` on the overlay.
3. **Alternatively, resize the BrowserView** by adjusting the container layout (like the logs panel does), which triggers `ResizeObserver → updatePreviewBounds()`.
4. **As a last resort**, call `hidePreview()`/`showPreview()` via `window.electronAPI`, but this removes the preview entirely.

## IPC Handlers for Preview Control

Defined in `electron/main.ts`, exposed via `electron/preload.ts`:

| IPC Channel | Preload Method | Purpose |
|---|---|---|
| `preview:show` | `showPreview()` | Show the BrowserView |
| `preview:hide` | `hidePreview()` | Hide the BrowserView |
| `preview:set-bounds` | `setPreviewBounds({x,y,w,h})` | Reposition/resize the BrowserView |
| `preview:load` | `loadPreview(url)` | Load a URL in the preview |
| `preview:refresh` | `refreshPreview()` | Reload current page |

## Bounds Update Flow

```
Container resizes (layout change, window resize)
  → ResizeObserver fires
  → DevServerPreview.updatePreviewBounds()
  → containerEl.getBoundingClientRect()
  → window.electronAPI.setPreviewBounds({ x, y, width, height })
  → IPC → preview-manager.setBounds()
  → BrowserView.setBounds()
```
