---
updated: 2026-04-10
---

# Electron Build & Packaging Pipeline

## Build Stages

The full build (`npm run electron:build:mac`) runs three stages sequentially:

1. **`vite build`** — SvelteKit compiled via `@sveltejs/adapter-node` into `build/` (a standalone Node.js server with `build/index.js` as entry point)
2. **`build:electron`** — TypeScript compilation of `electron/*.ts` to JS in-place, using two separate tsconfigs:
   - `electron/tsconfig.json` — ES2022 modules for main process (excludes `preload.ts`)
   - `electron/tsconfig.preload.json` — CommonJS for preload script (Electron requirement)
3. **`electron-builder`** — Packages into `.app`, DMG, and ZIP. Config in `electron-builder.yml`.

## Two Node.js Runtimes

The packaged app contains **two separate Node.js runtimes** — this is the most important architectural detail:

- **Electron's internal Node.js** — runs `main.js` (Electron main process, IPC handlers, window management)
- **Bundled standalone Node.js v22.12.0** — runs the SvelteKit server as a child process on port 5555

Native modules (`better-sqlite3`, `node-pty`) must be compiled against the **bundled** Node.js, not Electron's internal one, because they run in the server subprocess.

## Vite SSR Bundling Strategy

In `vite.config.js`:
- `ssr.noExternal: true` — All pure-JS dependencies are inlined into the server bundle
- `ssr.external: ['pg', 'better-sqlite3', 'node-pty']` — Native modules kept external (can't be bundled by Vite)

This means the packaged app only needs `node_modules` for these three native module trees, not the full dependency tree.

## What Goes Into the Package

Defined in `electron-builder.yml`:

### `files` (app code loaded by Electron directly)
- `build/**/*` — SvelteKit server output
- `electron/**/*.js` — Compiled Electron main/preload scripts
- `package.json`

### `extraResources` (copied to `Contents/Resources/` in .app)
- `build/` → `Resources/server/` — The SvelteKit server (duplicated here for runtime resolution)
- Native module trees shipped as real `node_modules` alongside the server:
  - `better-sqlite3` + `bindings` + `file-uri-to-path`
  - `node-pty`
  - `pg` and its full dependency tree (11 packages: `pg-connection-string`, `pg-pool`, `pg-protocol`, `pg-types`, `pgpass`, `pg-int8`, `postgres-array`, `postgres-bytea`, `postgres-date`, `postgres-interval`, `split2`, `xtend`)

Native module filters exclude `src/`, `deps/`, and `build/node_gyp_bins/` to reduce size.

### Final `.app` Structure

```
Kommandr.app/Contents/
├── Resources/
│   ├── app.asar          # Electron main.js, preload.js, package.json
│   ├── bin/
│   │   └── node           # Bundled Node.js 22.12.0
│   └── server/
│       ├── index.js       # SvelteKit server entry
│       ├── client/        # Frontend assets
│       └── node_modules/  # Native modules only (better-sqlite3, node-pty, pg)
├── MacOS/
│   └── Kommandr           # Electron binary
└── Info.plist
```

## Bundled Node.js Binary

The app ships its own Node.js binary instead of relying on the system Node.

- **Source location**: `src-tauri/bin/node-{arch}-apple-darwin` (naming is a holdover from a Tauri origin)
- **Currently available**: only `node-aarch64-apple-darwin` (arm64)
- **`scripts/after-pack.cjs`**: Copies the correct arch binary to `Resources/bin/node` during electron-builder's pack phase
- Architecture mapping: arm64 → `aarch64`, x64 → `x86_64`

### Runtime Path Resolution (`electron/server-manager.ts`)

| Resource | Packaged (`app.isPackaged`) | Development |
|----------|---------------------------|-------------|
| Node binary | `Resources/bin/node` | `src-tauri/bin/node-{arch}-apple-darwin`, fallback to system `node` |
| Server entry | `Resources/server/index.js` | `build/index.js` |

The server is spawned as a child process with env vars: `PORT=5555`, `HOST=127.0.0.1`, `NODE_ENV`, `MANAGED_CLAUDE_PATH`.

## Native Module Rebuild

- `npmRebuild: false` in electron-builder config — native modules are NOT rebuilt during packaging
- Native `.node` binaries must already be compiled for the **bundled Node.js** (not Electron's internal Node) before building
- `@electron/rebuild` is a devDependency for development use

## Code Signing & Notarization

- **Identity**: `Developer ID Application: RETAILER LLC (C7G662Y5QT)`
- **Certificate**: Stored in `APPLE_CERTIFICATE` env var (base64-encoded P12)
- **Entitlements**: `build-resources/entitlements.mac.plist` (hardened runtime enabled):
  - `com.apple.security.cs.allow-jit` — required for Node.js V8 JIT
  - `com.apple.security.cs.allow-unsigned-executable-memory` — required for V8 JIT
  - `com.apple.security.cs.disable-library-validation` — required for native `.node` modules
  - `com.apple.security.network.client` + `server` — for localhost server and external requests
- **Signing targets**: `.node` native module files and `spawn-helper` executables from node-pty are explicitly signed
- **`scripts/notarize.cjs`** (afterSign hook): Uses `@electron/notarize` with env vars:
  - `APPLE_ID` — Apple developer email
  - `APPLE_PASSWORD` or `APPLE_APP_SPECIFIC_PASSWORD`
  - `APPLE_TEAM_ID` — defaults to `C7G662Y5QT`
- **Unsigned builds**: `npm run electron:build:mac:unsigned` sets `CSC_IDENTITY_AUTO_DISCOVERY=false`

## Auto-Updates

- Uses `electron-updater` package
- Publishes to Cloudflare R2: `https://pub-d15dba8b41ac4f10bd183bdaac2ee2ed.r2.dev/electron`
- Artifact naming: `Kommandr-{version}-{arch}.{ext}`
- Update metadata: `latest-mac.yml` with SHA512 hashes for both architectures

## Release Workflow

**Cross-architecture strategy**: Local machine builds its own architecture, GitHub Actions CI builds the other.

### Local (`scripts/release.sh`)
1. Bump version in `package.json`
2. Download Node.js for both architectures
3. Build SvelteKit + Electron TypeScript
4. Rebuild native modules against bundled Node.js
5. Sign native `.node` files and `spawn-helper` executables
6. Run `electron-builder` with code signing + notarization
7. Create DMG + update ZIP, calculate SHA512 hashes
8. Upload to Cloudflare R2
9. Trigger GitHub Actions for the complementary architecture

### CI (`.github/workflows/release-single-arch.yml`)
- Runs on `macos-13` (x86_64) or `macos-latest` (ARM)
- Mirrors local build process with CI credentials
- Waits for local build info, then generates `latest-mac.yml` covering both architectures
- Uploads DMG + update ZIP to R2

### Local Testing (`scripts/local-build.sh`)
1. Download bundled Node.js v22.12.0 to `src-tauri/bin/`
2. `vite build` (SvelteKit)
3. `tsc` Electron TypeScript
4. `npm rebuild better-sqlite3` + `node-pty`
5. `electron-builder --mac` (unsigned)

## Build Output

- Output directory: `release/` (configured via `directories.output`)
- macOS targets: DMG + ZIP
- DMG has custom background from `src-tauri/dmg/background.png`
- Architectures: ARM (`Kommandr-{v}-arm64.dmg`) and Intel (`Kommandr-{v}-x64.dmg`)
