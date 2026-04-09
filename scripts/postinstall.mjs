#!/usr/bin/env node

/**
 * claude-docs postinstall script
 *
 * Automatically configures Claude Code with:
 * 1. Python dependencies via uv
 * 2. MCP server registration
 * 3. Tool auto-allow permissions
 * 4. Stop hook that nudges Claude to document findings each session
 * 5. Bootstrap embedding index for existing docs
 */

import { readFileSync, writeFileSync, mkdirSync, chmodSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import { execFileSync, execSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = dirname(__dirname); // package root (one level up from scripts/)

const CLAUDE_DIR = join(homedir(), ".claude");
const MCP_PATH = join(homedir(), ".claude.json"); // MCP server configs
const SETTINGS_PATH = join(CLAUDE_DIR, "settings.json"); // hooks, permissions
const HOOKS_DIR = join(CLAUDE_DIR, "hooks");
const HOOK_PATH = join(HOOKS_DIR, "claude-docs-stop.sh");

const PERMISSIONS = [
  "mcp__claude-docs__list_docs",
  "mcp__claude-docs__lookup_doc",
  "mcp__claude-docs__save_doc",
  "mcp__claude-docs__search_docs",
  "mcp__claude-docs__delete_doc",
  "mcp__claude-docs__semantic_search_docs",
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
You MUST now call list_docs() and review what you learned this session. Then call save_doc() for anything worth preserving. This is NOT optional.

What to document — if you did ANY of these, save a doc:
- Read code to understand how something works
- Hit an error and found the fix
- Discovered config formats, correct types, or non-obvious conventions
- Learned how subsystems connect or data flows
- Received workflow instructions from the user ("always run X", "never do Y")

What NOT to skip:
- "Derivable from code" is NOT a reason to skip — the whole point is saving future sessions from re-deriving it
- User workflow instructions are PROJECT conventions — save to .claude/docs/, not personal memory
- If you read or referenced any docs this session that are now stale due to your changes, UPDATE them

Procedure:
1. Call list_docs() to see existing docs
2. Call semantic_search_docs() with your topic to find related docs
3. UPDATE existing docs rather than creating duplicates
4. Be specific: include actual config values, correct types, file paths, function names, working examples

If you made code changes this session, you almost certainly have something to document. Do it now.
EOF
exit 2
`;

function readJson(path) {
  if (!existsSync(path)) return {};
  try {
    return JSON.parse(readFileSync(path, "utf-8"));
  } catch {
    return {};
  }
}

function writeJson(path, data) {
  writeFileSync(path, JSON.stringify(data, null, 2) + "\n");
}

function readSettings() {
  return readJson(SETTINGS_PATH);
}

function writeSettings(settings) {
  writeJson(SETTINGS_PATH, settings);
}

function commandExists(cmd) {
  try {
    execSync(`command -v ${cmd}`, { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

function main() {
  // Check for uv
  if (!commandExists("uv")) {
    console.log("claude-docs: uv is required but not found.");
    console.log("  Install with: curl -LsSf https://astral.sh/uv/install.sh | sh");
    console.log("  Then re-run: npm install -g @colbymchenry/claude-docs");
    return;
  }

  // Check if ~/.claude exists (Claude Code installed)
  if (!existsSync(CLAUDE_DIR)) {
    console.log("claude-docs: ~/.claude not found — install Claude Code first, then re-run: npm install -g @colbymchenry/claude-docs");
    return;
  }

  // 1. Install Python dependencies
  console.log("claude-docs: installing Python dependencies...");
  try {
    execFileSync("uv", ["sync"], { cwd: PKG_DIR, stdio: "pipe" });
    console.log("claude-docs: Python dependencies installed");
  } catch (err) {
    console.log("claude-docs: failed to install Python deps — run manually: cd " + PKG_DIR + " && uv sync");
    console.log(err.stderr?.toString() || err.message);
    return;
  }

  // 2. Register MCP server in ~/.claude.json
  const mcpConfig = readJson(MCP_PATH);
  if (!mcpConfig.mcpServers) mcpConfig.mcpServers = {};
  mcpConfig.mcpServers["claude-docs"] = {
    command: "uv",
    args: ["run", "--directory", PKG_DIR, "python", "server.py"],
  };
  writeJson(MCP_PATH, mcpConfig);
  console.log("claude-docs: registered MCP server in ~/.claude.json");

  const settings = readSettings();
  let changed = false;

  // 3. Add permissions
  if (!settings.permissions) settings.permissions = {};
  if (!settings.permissions.allow) settings.permissions.allow = [];
  const missing = PERMISSIONS.filter((p) => !settings.permissions.allow.includes(p));
  if (missing.length > 0) {
    settings.permissions.allow.push(...missing);
    changed = true;
    console.log("claude-docs: added tool permissions");
  }

  // 4. Register UserPromptSubmit hook (auto doc recall)
  if (!settings.hooks) settings.hooks = {};
  if (!settings.hooks.UserPromptSubmit) settings.hooks.UserPromptSubmit = [];

  const promptHookPath = join(PKG_DIR, "hooks", "claude-docs-on-prompt.sh");
  const promptHookExists = settings.hooks.UserPromptSubmit.some((entry) =>
    entry.hooks?.some((h) => h.command?.includes("claude-docs-on-prompt.sh"))
  );

  if (!promptHookExists) {
    settings.hooks.UserPromptSubmit.push({
      matcher: ".*",
      hooks: [
        {
          type: "command",
          command: promptHookPath,
          timeout: 10,
        },
      ],
    });
    changed = true;
    console.log("claude-docs: registered prompt hook (auto doc recall)");
  }

  // 5. Install stop hook script
  mkdirSync(HOOKS_DIR, { recursive: true });
  writeFileSync(HOOK_PATH, HOOK_SCRIPT);
  chmodSync(HOOK_PATH, 0o755);
  console.log("claude-docs: installed stop hook");

  // 5. Register stop hook in settings
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

  // 6. Bootstrap embedding index for existing docs (in cwd if it's a project)
  try {
    execFileSync("uv", ["run", "--directory", PKG_DIR, "python", "server.py", "--index", process.cwd()], {
      cwd: PKG_DIR,
      stdio: "pipe",
    });
    console.log("claude-docs: bootstrapped embedding index");
  } catch {
    // No docs to index yet, or first install — not a problem
  }

  console.log("claude-docs: setup complete — restart Claude Code for changes to take effect");
}

main();
