---
updated: 2026-04-14
---

# Subscription License Flow (Electron App)

How the Kommandr Electron app decides whether to show the main UI vs. the "Subscription Required" screen.

## Components

- **Renderer store:** `packages/electron/gui/src/lib/auth-store.ts` — Zustand store tracking `user`, `subscription`, `subscriptionLoading`.
- **Main process:** `packages/electron/src/main.ts` — owns the authoritative subscription check and the signed license file.
- **Shared crypto:** `packages/shared/src/crypto/license.ts` — `verifyLicenseSignature`, `getMachineFingerprint`, `SubscriptionLicense` type.
- **Cached license file:** `~/.kommandr/subscription.json` (mode 0o600).
- **Backend:** `https://kommandr.com/api/subscription/license` (v2, Ed25519-signed) with legacy fallback to `/api/subscription/status` (v1, HMAC).

## License File Shape

```json
{
  "active": true,
  "email": "user@example.com",
  "plan": "monthly",
  "machineId": "<sha256 of hostname:username:homedir>",
  "verifiedAt": 1772424868907,
  "expiresAt": 1775016868907,   // verifiedAt + 30 days
  "signatureVersion": "v2",      // v2 = Ed25519, else v1 HMAC
  "signature": "<base64 or hex>"
}
```

`readSubscriptionLicense()` in main.ts rejects the cache if ANY of:
- File missing
- `machineId !== getMachineFingerprint()` (moving the file to another machine/user fails)
- `Date.now() > expiresAt` (30-day TTL)
- Signature mismatch

On rejection it returns `null` — it does NOT delete the file. `clearSubscriptionLicense()` only runs on sign-out or after a server check confirms inactive.

## Startup Flow

1. `useAuthStore` constructor calls `window.kommandrAPI.getCachedSubscription()` (IPC `subscription:cached`). If valid → sets `subscription.active = true` immediately, preventing a "Subscription Required" flash.
2. Firebase SDK restores auth via IndexedDB persistence → `onAuthStateChanged` fires.
3. If no cached token AND no cached license AND no Firebase user → sign-in screen.
4. If authenticated + active subscription → main app.

## Verification Path (after sign-in)

1. User clicks Sign In → `shell.openExternal(kommandr.com/login?callback=...)`.
2. Browser redirects to `http://localhost:<random>/auth-callback?token=...`.
3. Main sets `currentFirebaseToken = token` and calls `verifyAndWriteSubscription(token)`.
4. POST to `/api/subscription/license` with `Authorization: Bearer <firebaseToken>` and `{ machineId }`.
5. On success, main writes signed license to `~/.kommandr/subscription.json` and starts hourly refresh timer (`startSubscriptionRefresh`).
6. Main emits `subscription:status` IPC event → renderer store updates.

## Known Gap: Expired Cache + App Restart

`currentFirebaseToken` is **in-memory only** — it's not persisted in main. After app restart:
- Cached license may have expired (>30 days since last successful verify).
- `readSubscriptionLicense()` returns null.
- Firebase auth state is restored, but nothing in the renderer auto-triggers `refreshSubscription()` when the user is restored with a null/expired subscription.
- Hourly refresh timer never starts because `currentFirebaseToken` is null.
- User sees "Subscription Required" until they manually click "Check Status".

`refreshSubscription()` in auth-store works because it fetches a fresh Firebase token via `user.getIdToken(true)` and passes it through IPC `subscription:check` — main rehydrates `currentFirebaseToken` from that argument.

**Fix direction:** in `auth-store.ts`, when `onAuthStateChanged` fires with a non-null user AND `subscription?.active !== true`, auto-call `refreshSubscription()`.

## IPC Surface

| Channel | Direction | Purpose |
|---|---|---|
| `subscription:cached` | renderer → main | Read & validate local license file |
| `subscription:check` | renderer → main | Re-verify (optionally with fresh Firebase token) |
| `subscription:status` | main → renderer | Push status updates after verify |
| `subscription:expired` | main → renderer | Hourly timer detected expiry |
| `auth:token-received` | main → renderer | Browser auth callback delivered a token |
| `auth:sign-out` | renderer → main | Clears token, stops timer, deletes license file |

## Signature Versions

- **v2 (current):** Ed25519, verified against hardcoded public key in `packages/shared/src/crypto/license.ts` (`ED25519_PUBLIC_KEY_B64`). Private key is a Cloudflare Workers secret (`LICENSE_SIGNING_KEY`).
- **v1 (fallback):** HMAC-SHA256 using the server secret from `~/.kommandr/secret.key`. Used only when the v2 backend endpoint returns non-2xx.

`buildLicensePayloadString()` determines the canonical payload for both sign and verify — edit with care, any change breaks all existing licenses.
