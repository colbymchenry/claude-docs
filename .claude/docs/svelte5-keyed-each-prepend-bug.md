---
updated: 2026-04-12
---

# Svelte 5 keyed `{#each}` crash on prepend: `reading 'prev'`

## Symptom

```
Uncaught TypeError: Cannot read properties of undefined (reading 'prev')
    at io (reconcile)
    at ur / lt (update_reaction / update_effect)
    at xt.Gt / xt.process / xt.flush (Batch)
    at Array.<anonymous>
```

Confirmed in **svelte 5.46.1** and **svelte 5.55.3** (latest as of this writing). Fully reproducible, not a race condition.

## Root cause

Bug in `node_modules/svelte/src/internal/client/dom/blocks/each.js` inside `reconcile()` (~line 544 in 5.55). When an item is inserted at position 0 of a keyed `{#each}` list while existing items stay, the reconciler walks `current` past every existing effect trying to find the new one, `current` hits `null` without pushing to `matched`, then the *next* iteration encounters an effect that IS in `seen` (one of the stashed items), takes this branch:

```js
if (matched.length < stashed.length) {   // 0 < N, enters branch
    var start = stashed[0];
    prev = start.prev;
    var a = matched[0];                   // undefined — matched is []
    var b = matched[matched.length - 1];  // undefined
    ...
    link(state, a.prev, b.next);          // crashes reading 'prev' on undefined
}
```

The condition should guard against `matched.length === 0`.

## When it fires in our code

Any state write of the shape `arr = [newItem, ...arr]` (prepend a new key) feeding a keyed `{#each arr as x (x.id)}`. Appending is fine. Removing is fine. Reordering existing keys is fine. **Prepending a NEW key while keeping existing keys is the trigger.**

## Fix pattern

Use non-keyed `{#each}` for these display-only lists. Svelte's non-keyed path uses index-based diffing and doesn't hit the buggy branch. Safe when list items don't need cross-reorder identity (cards that display data, no internal state).

**Do NOT** patch svelte or downgrade. Do not try to work around by mutating the array in place — Svelte's derived chains still produce new array refs for filters and the reconcile still runs.

## Known prepend sites in this repo (all fixed to non-keyed)

| State write | Rendered by | Each block |
|---|---|---|
| `src/lib/notification-store.ts:151` — `[notification, ...n]` | `NotificationBell.svelte:136`, `NotificationBellWrapper.svelte:222` | notifications list |
| `src/lib/notification-store.ts:196` — `[toast, ...t]` | `ToastContainer.svelte:107`, `ToastContainerWrapper.svelte:146` | toasts |
| `src/lib/project-stream.svelte.ts:~127` — `[...data.events, ...events]` | `EventFeed.svelte:54` | recent activity |

If you add a new "newest-first" list backed by an SSE/stream that prepends, **do not key it**. Or switch to append-and-reverse-render.

## Unrelated but discovered during the hunt

- `src/lib/project-stream.svelte.ts` now skips the `issues = data.issues` reassignment when the incoming update is structurally identical (same IDs in same order, `changedIds` empty). This was originally added hoping it would fix the prepend bug — it didn't, but it cuts per-second reactive churn and noticeably improved project/task load times. Keep it.
- `src/routes/(protected)/projects/[id]/+page.svelte` `handleSheetClose` now sets `selectedIssue = null` in addition to `sheetOpen = false`, and `IssueDetailSheet.svelte` gates the body on `{#if issue && isOpen}`. This prevents the sheet's internal each blocks (blockers, comments, etc.) from reconciling during the sheet's close animation. Not the root cause of the prepend bug, but a good hygiene fix.

## History

- Showed up after commit `119dd731` (EventSource → fetch-based SSE). It looked stream-related but wasn't — EventSource just happened to space out notification broadcasts enough that the prepend reconcile rarely coincided with other reactive work. The fetch path is fine; the bug exists either way.
- Fix landed 2026-04-12.
