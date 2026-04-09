#!/usr/bin/env python3
"""Query doc embeddings by semantic similarity to a user prompt.

Finds the project root from --project-dir (or cwd), loads the ChromaDB
collection at .claude/docs/.embeddings/, and returns top matching chunks.

Usage:
    echo "some prompt" | python query.py --project-dir /path/to/project
    python query.py --prompt "some prompt" --project-dir /path/to/project
"""

import argparse
import os
import sys

import chromadb

SIMILARITY_THRESHOLD = 0.3
MAX_RESULTS = 5


def find_project_root(start_dir: str) -> str:
    d = os.path.abspath(start_dir)
    while True:
        if os.path.exists(os.path.join(d, ".git")) or os.path.exists(
            os.path.join(d, "CLAUDE.md")
        ):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start_dir)
        d = parent


def query(prompt: str, project_dir: str, n_results: int = MAX_RESULTS) -> list[dict]:
    root = find_project_root(project_dir)
    embeddings_dir = os.path.join(root, ".claude", "docs", ".embeddings")

    if not os.path.exists(embeddings_dir):
        return []

    try:
        client = chromadb.PersistentClient(path=embeddings_dir)
        collection = client.get_or_create_collection(
            name="doc-chunks",
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        return []

    total = collection.count()
    if total == 0:
        return []

    try:
        results = collection.query(
            query_texts=[prompt],
            n_results=min(n_results, total),
        )
    except Exception:
        return []

    relevant = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        similarity = 1 - dist
        if similarity < SIMILARITY_THRESHOLD:
            continue

        topic = meta.get("topic", "unknown")
        header = meta.get("header", "")
        location = f"{topic} > {header}" if header else topic

        # Strip context prefix added during chunking
        display_text = doc
        prefix_end = doc.find(": ")
        if 0 < prefix_end < 80:
            display_text = doc[prefix_end + 2:]

        relevant.append({
            "location": location,
            "text": display_text,
            "topic": topic,
            "similarity": round(similarity, 2),
        })

    return relevant


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="", help="The prompt to search against")
    parser.add_argument("--project-dir", default=os.getcwd(), help="Project directory")
    parser.add_argument("--limit", type=int, default=MAX_RESULTS, help="Max results")
    args = parser.parse_args()

    prompt = args.prompt or sys.stdin.read().strip()
    if not prompt:
        sys.exit(0)

    results = query(prompt, project_dir=args.project_dir, n_results=args.limit)
    if results:
        lines = []
        for r in results:
            # Truncate text to first 150 chars for concise context injection
            text = r["text"].replace("\n", " ").strip()
            if len(text) > 150:
                text = text[:150] + "..."
            lines.append(f"- [{r['location']}] {text}")
        print("\n".join(lines))
