---
updated: 2026-04-09
---

# Beads CLI Update & Version System

## Installation Methods

Beads CLI (`bd`) can be installed via:
- **Homebrew (recommended):** `brew install beads`
- **npm:** `npm install -g @beads/bd` (may lag behind GitHub releases)
- **curl:** `curl -sSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash`
- **Manual:** Download binary from GitHub releases

## GitHub Repository

The repo moved from `steveyegge/beads` to `gastownhall/beads`. The old URL redirects, but Node.js `https.get` does NOT follow redirects automatically — must handle explicitly.

- Releases: `https://github.com/gastownhall/beads/releases`
- CLI docs: `https://gastownhall.github.io/beads/cli-reference`
- Code constant: `GITHUB_REPO = 'gastownhall/beads'`

## Release Archive Format

Tarballs contain a **subdirectory** with the binary inside:
```
beads_1.0.0_darwin_arm64/
  bd
  LICENSE
  CHANGELOG.md
  README.md
```
Must search subdirectories when extracting — `bd` is NOT at the archive root.

Platform identifiers: `darwin_arm64`, `darwin_amd64`, `linux_arm64`, `linux_amd64`, `windows_arm64`, `windows_amd64`

## npm vs GitHub Releases

As of 2026-04-09:
- npm `@beads/bd`: v0.63.3 (outdated)
- GitHub releases: v1.0.0 (latest)
- Colby's installed: was v0.46.0 at `~/.local/bin/bd`

The npm package lags significantly behind GitHub releases. The dashboard uses GitHub binary downloads for updates.

## CLI Changes in v1.0.0

The v1.0.0 release removed/changed several commands:
- **No `status` subcommand** — use `bd list`, `bd ready`, `bd blocked` instead
- **No `--no-activity` flag** — does not exist
- Available global flags: `--db`, `--json`, `--quiet`, `--verbose`, `--help`
- Version check: `bd --version` or `bd version`

## Per-Project Version Tracking

Each project stores its beads version in `.beads/.local_version`. The per-project update endpoint writes this file directly (does NOT run `bd status` which no longer exists).

## Key Files

| File | Purpose |
|------|---------|
| `src/lib/beads-manager.ts` | CLI installation, version detection, GitHub binary download |
| `src/routes/api/beads/status/+server.ts` | GET — installation status |
| `src/routes/api/beads/update/+server.ts` | GET — check for updates; POST — update with SSE progress |
| `src/routes/api/projects/[id]/update-beads/+server.ts` | POST — update project's `.local_version` |
| `src/components/BeadsUpdateBanner.svelte` | Global update banner (purple theme) |
| `src/components/ProjectCard.svelte` | Shows version badge + per-project update button |
