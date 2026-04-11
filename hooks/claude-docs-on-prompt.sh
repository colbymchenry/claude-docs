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

# Get doc tree listing (always include if docs exist)
LISTING=$(cd "$REPO_DIR" && uv run python query.py --list --project-dir "$PROJECT_DIR" 2>/dev/null)

# Query doc embeddings scoped to the current project
DOCS=$(cd "$REPO_DIR" && echo "$PROMPT" | uv run python query.py --project-dir "$PROJECT_DIR" 2>/dev/null)

CTX=""
if [ -n "$DOCS" ]; then
    # Full doc content injected — Claude gets the docs directly
    CTX="Relevant project documentation for this task. These docs already exist in .claude/docs/. Do NOT create new docs that overlap with these — if you need to update one, use save_doc with the EXACT same topic name shown below:\n\n$DOCS"
    if [ -n "$LISTING" ]; then
        CTX="$CTX\nFull doc index (.claude/docs/):\n$LISTING"
    fi
elif [ -n "$LISTING" ]; then
    CTX="Project documentation (.claude/docs/):\n$LISTING"
fi

if [ -n "$CTX" ]; then
    jq -n --arg ctx "$CTX" \
        '{"hookSpecificOutput": {"additionalContext": $ctx}}'
fi

exit 0
