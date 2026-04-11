---
updated: 2026-04-09
---

# Opening URLs in the System Default Browser

## The Problem

In Electron, `window.open(url, '_blank')` does NOT open the system default browser. It creates a new Electron `BrowserWindow` — a small, featureless chromium window that confuses users.

## The Fix

Use `electronAPI.openExternal()` which calls Electron's `shell.openExternal()` under the hood. This opens the URL in the user's actual default browser (Chrome, Safari, Edge, Firefox, etc.).

```typescript
const electronAPI = (window as any).electronAPI;
if (electronAPI?.openExternal) {
  await electronAPI.openExternal(url);
} else {
  // Fallback for non-Electron (e.g., dev in regular browser)
  window.open(url, '_blank');
}
```

## IPC Plumbing

- **Preload** (`electron/preload.ts` line 43): `openExternal: (url) => ipcRenderer.invoke('shell:open-external', url)`
- **Main process** (`electron/main.ts` line ~156): Handles `shell:open-external` via `shell.openExternal(url)`
- **Type definition** (`src/lib/window-types.d.ts` line 29): `openExternal: (url: string) => Promise<{ success: boolean; error?: string }>`

## Where This Applies

Any "Open in browser" button or link that should leave the Electron app and open in the system browser. Fixed in:
- `src/components/LiveEditMode.svelte` — `handleOpenInBrowser()` function

Already correctly using `electronAPI.openExternal`:
- `src/lib/firebase.ts` — OAuth auth URL
- `src/components/ChatSheet.svelte` — Opening file paths
