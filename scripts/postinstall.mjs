#!/usr/bin/env node

/**
 * claude-docs postinstall script
 *
 * Automatically configures Claude Code with:
 * 1. MCP server registration (via `claude mcp add -s user`)
 * 2. Tool auto-allow permissions
 * 3. Stop hook that nudges Claude to document findings each session
 */

import { readFileSync, writeFileSync, mkdirSync, chmodSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { execFileSync } from "node:child_process";

const CLAUDE_DIR = join(homedir(), ".claude");
const SETTINGS_PATH = join(CLAUDE_DIR, "settings.json");
const HOOKS_DIR = join(CLAUDE_DIR, "hooks");
const HOOK_PATH = join(HOOKS_DIR, "claude-docs-stop.sh");

const PERMISSIONS = [
  "mcp__claude-docs__list_docs",
  "mcp__claude-docs__lookup_doc",
  "mcp__claude-docs__save_doc",
  "mcp__claude-docs__search_docs",
  "mcp__claude-docs__delete_doc",
];

const HOOK_SCRIPT = `#!/bin/bash
# claude-docs stop hook: reminds Claude to document findings once per session

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')

# Only remind once per session
MARKER="/tmp/claude-docs-reminded-\${SESSION_ID}"
if [ -f "$MARKER" ]; then
  exit 0
fi
touch "$MARKER"

cat >&2 <<'EOF'
Before finishing, call list_docs() and check: should you document anything from this session?

Document if you:
- Looked up how something works (APIs, config formats, setting types, schema details)
- Hit an error and found the fix (wrong field names, type mismatches, correct invocations)
- Discovered non-obvious conventions (string vs int types, naming patterns, required flags)
- Learned how subsystems connect (data flow, dependencies, integration points)
- Received workflow instructions from the user (linting commands, validation steps, deploy procedures, review checklists)

IMPORTANT: User workflow instructions like "always run X before Y" are PROJECT conventions — save them with save_doc(), not personal memory. They belong in .claude/docs/ so all sessions and team members benefit.

"Derivable from the codebase" is NOT a reason to skip — the whole point is saving future sessions from re-deriving it. If you had to read code to figure it out, document it.

Also check if any docs you read, referenced, or saved earlier in this session need updating based on subsequent changes.

Use save_doc() to create or update docs. Be specific: include actual setting names, correct types, file paths, and working examples.
EOF
exit 2
`;

function readSettings() {
  if (!existsSync(SETTINGS_PATH)) return {};
  try {
    return JSON.parse(readFileSync(SETTINGS_PATH, "utf-8"));
  } catch {
    return {};
  }
}

function writeSettings(settings) {
  writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2) + "\n");
}

function main() {
  // Check if ~/.claude exists (Claude Code installed)
  if (!existsSync(CLAUDE_DIR)) {
    console.log("claude-docs: ~/.claude not found — install Claude Code first, then re-run: npm install -g @colbymchenry/claude-docs");
    return;
  }

  const settings = readSettings();
  let changed = false;

  // 1. Register MCP server via `claude mcp add -s user`
  try {
    execFileSync("claude", ["mcp", "add", "-s", "user", "claude-docs", "claude-docs"], {
      stdio: "pipe",
    });
    console.log("claude-docs: registered MCP server");
  } catch (err) {
    // Already registered or claude CLI not found
    if (err.stderr?.toString().includes("already exists")) {
      console.log("claude-docs: MCP server already registered");
    } else {
      console.log("claude-docs: could not register MCP server via CLI — run manually: claude mcp add -s user claude-docs claude-docs");
    }
  }

  // 2. Add permissions
  if (!settings.permissions) settings.permissions = {};
  if (!settings.permissions.allow) settings.permissions.allow = [];
  const missing = PERMISSIONS.filter((p) => !settings.permissions.allow.includes(p));
  if (missing.length > 0) {
    settings.permissions.allow.push(...missing);
    changed = true;
    console.log("claude-docs: added tool permissions");
  }

  // 3. Install stop hook script
  mkdirSync(HOOKS_DIR, { recursive: true });
  writeFileSync(HOOK_PATH, HOOK_SCRIPT);
  chmodSync(HOOK_PATH, 0o755);
  console.log("claude-docs: installed stop hook");

  // 4. Register stop hook in settings
  if (!settings.hooks) settings.hooks = {};
  if (!settings.hooks.Stop) settings.hooks.Stop = [];

  const hookExists = settings.hooks.Stop.some((entry) =>
    entry.hooks?.some((h) => h.command?.includes("claude-docs-stop.sh"))
  );

  if (!hookExists) {
    settings.hooks.Stop.push({
      matcher: "",
      hooks: [
        {
          type: "command",
          command: HOOK_PATH,
          timeout: 10,
        },
      ],
    });
    changed = true;
    console.log("claude-docs: registered stop hook");
  }

  // Write settings if anything changed
  if (changed) {
    writeSettings(settings);
  }

  console.log("claude-docs: setup complete");
}

main();
