#!/bin/bash
set -e

SETTINGS_FILE="$HOME/.claude/settings.json"
HOOK_PATH="$HOME/.claude/hooks/claude-docs-stop.sh"

echo "Uninstalling claude-docs..."

if [ ! -f "$SETTINGS_FILE" ]; then
    echo "No settings file found at $SETTINGS_FILE"
    exit 0
fi

# Backup settings
cp "$SETTINGS_FILE" "$SETTINGS_FILE.backup"
echo "Backed up settings to $SETTINGS_FILE.backup"

# Remove MCP server
echo "Removing MCP server..."
UPDATED=$(jq 'del(.mcpServers."claude-docs")' "$SETTINGS_FILE")
echo "$UPDATED" > "$SETTINGS_FILE"

# Remove permissions
echo "Removing permissions..."
UPDATED=$(jq '
    if .permissions.allow then
        .permissions.allow = [.permissions.allow[] | select(startswith("mcp__claude-docs__") | not)]
    else . end
' "$SETTINGS_FILE")
echo "$UPDATED" > "$SETTINGS_FILE"

# Remove stop hook from settings
echo "Removing stop hook..."
UPDATED=$(jq --arg cmd "$HOOK_PATH" '
    if .hooks.Stop then
        .hooks.Stop = [.hooks.Stop[] | select(.hooks | all(.command != $cmd))]
    else . end
' "$SETTINGS_FILE")
echo "$UPDATED" > "$SETTINGS_FILE"

# Remove prompt hook from settings
echo "Removing prompt hook..."
UPDATED=$(jq '
    if .hooks.UserPromptSubmit then
        .hooks.UserPromptSubmit = [.hooks.UserPromptSubmit[] | select(.hooks | all(.command | contains("claude-docs-on-prompt.sh") | not))]
    else . end
' "$SETTINGS_FILE")
echo "$UPDATED" > "$SETTINGS_FILE"

# Remove hook script
if [ -f "$HOOK_PATH" ]; then
    rm "$HOOK_PATH"
    echo "Removed hook script"
fi

echo ""
echo "Uninstall complete. Restart Claude Code for changes to take effect."
echo "Note: .claude/docs/ and .claude/docs/.embeddings/ were NOT deleted."
