#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
MCP_FILE="$HOME/.claude.json"
SETTINGS_FILE="$HOME/.claude/settings.json"
HOOK_PATH="$HOME/.claude/hooks/claude-docs-stop.sh"

echo "Installing claude-docs from $REPO_DIR"

# Check dependencies
if ! command -v jq &>/dev/null; then
    echo "Error: jq is required. Install with: brew install jq (macOS) or apt install jq (Linux)"
    exit 1
fi

if ! command -v uv &>/dev/null; then
    echo "Error: uv is required. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v claude &>/dev/null; then
    echo "Error: claude CLI is required. Install Claude Code first."
    exit 1
fi

# Install Python dependencies
echo "Installing Python dependencies..."
cd "$REPO_DIR"
uv sync

# Remove old npm-based installation if present
npm uninstall -g claude-docs 2>/dev/null || true
npm uninstall -g @colbymchenry/claude-docs 2>/dev/null || true
claude mcp remove claude-docs 2>/dev/null || true

# Ensure settings.json exists
mkdir -p "$HOME/.claude"
if [ ! -f "$SETTINGS_FILE" ]; then
    echo '{}' > "$SETTINGS_FILE"
fi

# Backup settings
cp "$SETTINGS_FILE" "$SETTINGS_FILE.backup"
echo "Backed up settings to $SETTINGS_FILE.backup"

# Add MCP server to ~/.claude.json (where Claude Code reads MCP configs)
echo "Configuring MCP server..."
if [ ! -f "$MCP_FILE" ]; then
    echo '{}' > "$MCP_FILE"
fi
cp "$MCP_FILE" "$MCP_FILE.backup"
UPDATED=$(jq --arg dir "$REPO_DIR" '
    .mcpServers = (.mcpServers // {}) |
    .mcpServers."claude-docs" = {
        "command": "uv",
        "args": ["run", "--directory", $dir, "python", "server.py"]
    }
' "$MCP_FILE")
echo "$UPDATED" > "$MCP_FILE"

# Add permissions
echo "Adding permissions..."
UPDATED=$(jq '
    .permissions = (.permissions // {}) |
    .permissions.allow = (.permissions.allow // []) |
    .permissions.allow += [
        "mcp__claude-docs__list_docs",
        "mcp__claude-docs__lookup_doc",
        "mcp__claude-docs__save_doc",
        "mcp__claude-docs__search_docs",
        "mcp__claude-docs__delete_doc",
        "mcp__claude-docs__semantic_search_docs"
    ] |
    .permissions.allow = (.permissions.allow | unique)
' "$SETTINGS_FILE")
echo "$UPDATED" > "$SETTINGS_FILE"

# Install UserPromptSubmit hook (auto doc recall)
echo "Adding UserPromptSubmit hook..."
PROMPT_HOOK_PATH="$REPO_DIR/hooks/claude-docs-on-prompt.sh"
UPDATED=$(jq --arg cmd "$PROMPT_HOOK_PATH" '
    .hooks = (.hooks // {}) |
    .hooks.UserPromptSubmit = (.hooks.UserPromptSubmit // []) |
    (if (.hooks.UserPromptSubmit | map(select(.hooks[]?.command == $cmd)) | length) == 0
     then .hooks.UserPromptSubmit += [{
         "matcher": ".*",
         "hooks": [{"type": "command", "command": $cmd, "timeout": 10}]
     }]
     else . end)
' "$SETTINGS_FILE")
echo "$UPDATED" > "$SETTINGS_FILE"

# Install stop hook script
echo "Installing stop hook..."
mkdir -p "$HOME/.claude/hooks"
cat > "$HOOK_PATH" << 'HOOKEOF'
#!/bin/bash
# claude-docs stop hook: reminds Claude to document findings once per session

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')

# Only remind once per session
MARKER="/tmp/claude-docs-reminded-${SESSION_ID}"
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
HOOKEOF
chmod +x "$HOOK_PATH"

# Register stop hook in settings
UPDATED=$(jq --arg cmd "$HOOK_PATH" '
    .hooks = (.hooks // {}) |
    .hooks.Stop = (.hooks.Stop // []) |
    (if (.hooks.Stop | map(select(.hooks[]?.command == $cmd)) | length) == 0
     then .hooks.Stop += [{
         "matcher": "",
         "hooks": [{"type": "command", "command": $cmd, "timeout": 10}]
     }]
     else . end)
' "$SETTINGS_FILE")
echo "$UPDATED" > "$SETTINGS_FILE"

# Bootstrap embeddings for existing docs (in current project if applicable)
echo "Indexing existing docs..."
uv run --directory "$REPO_DIR" python server.py --index "$(pwd)" 2>/dev/null || echo "No existing docs to index."

echo ""
echo "Installation complete! Restart Claude Code for changes to take effect."
echo ""
echo "MCP tools available after restart:"
echo "  - list_docs()                    — tree listing of all docs"
echo "  - lookup_doc(topic)              — retrieve a doc by topic"
echo "  - save_doc(topic, content)       — create or update a doc"
echo "  - search_docs(query)             — keyword/regex search"
echo "  - delete_doc(topic)              — remove a doc"
echo "  - semantic_search_docs(query)    — search by meaning (NEW)"
