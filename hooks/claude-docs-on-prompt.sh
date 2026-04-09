#!/bin/bash
# UserPromptSubmit hook: search doc embeddings for context relevant to the
# user's prompt. Injects matching doc chunks as additionalContext so Claude
# has relevant knowledge before responding.

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INPUT=$(cat)

# Skip subagents/background processes
AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // empty')
if [ -n "$AGENT_ID" ]; then
    exit 0
fi

PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')
if [ -z "$PROMPT" ]; then
    exit 0
fi

# Get the project directory from cwd
PROJECT_DIR=$(echo "$INPUT" | jq -r '.cwd // empty')
if [ -z "$PROJECT_DIR" ]; then
    exit 0
fi

# Query doc embeddings scoped to the current project
DOCS=$(cd "$REPO_DIR" && echo "$PROMPT" | uv run python query.py --project-dir "$PROJECT_DIR" 2>/dev/null)

if [ -n "$DOCS" ]; then
    jq -n --arg ctx "Relevant project docs (from .claude/docs/ semantic search — use lookup_doc(topic) for full content):\n$DOCS" \
        '{"hookSpecificOutput": {"additionalContext": $ctx}}'
fi

exit 0
