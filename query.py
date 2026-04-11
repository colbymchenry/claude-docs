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
import re
import sys
from datetime import datetime

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


def list_docs(project_dir: str) -> str:
    """Return doc tree listing + inlined workflow docs, matching server's list_docs()."""
    root = find_project_root(project_dir)
    docs_dir = os.path.join(root, ".claude", "docs")

    if not os.path.isdir(docs_dir):
        return ""

    # Build tree listing
    def get_all_doc_paths(directory: str) -> list[str]:
        results: list[str] = []
        try:
            for entry in os.scandir(directory):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    results.extend(get_all_doc_paths(entry.path))
                elif entry.name.endswith(".md"):
                    results.append(entry.path)
        except OSError:
            pass
        return results

    def format_entry(path: str) -> str:
        topic = os.path.relpath(path, docs_dir).removesuffix(".md")
        st = os.stat(path)
        size = st.st_size
        modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
        size_str = f"{size} B" if size < 1024 else f"{size / 1024:.1f} KB"
        return f"  {topic} ({size_str}, updated {modified})"

    all_docs = get_all_doc_paths(docs_dir)
    if not all_docs:
        return ""

    lines = [".claude/docs/"]
    for doc_path in sorted(all_docs):
        lines.append(format_entry(doc_path))

    # Inline workflow docs
    workflow_dir = os.path.join(docs_dir, "workflow")
    workflow_docs: list[str] = []
    try:
        for file_path in get_all_doc_paths(workflow_dir):
            with open(file_path) as f:
                content = f.read()
            topic = os.path.relpath(file_path, docs_dir).removesuffix(".md")
            workflow_docs.append(f"### {topic}\n{content}")
    except OSError:
        pass

    if workflow_docs:
        lines.append("")
        lines.append("## Workflow conventions (always apply):")
        lines.append("")
        lines.append("\n\n".join(workflow_docs))

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="", help="The prompt to search against")
    parser.add_argument("--project-dir", default=os.getcwd(), help="Project directory")
    parser.add_argument("--limit", type=int, default=MAX_RESULTS, help="Max results")
    parser.add_argument("--list", action="store_true", help="Output doc tree listing")
    args = parser.parse_args()

    if args.list:
        listing = list_docs(args.project_dir)
        if listing:
            print(listing)
        sys.exit(0)

    prompt = args.prompt or sys.stdin.read().strip()
    if not prompt:
        sys.exit(0)

    results = query(prompt, project_dir=args.project_dir, n_results=args.limit)
    if results:
        # Deduplicate to unique topics, keeping the best similarity per topic
        topic_best: dict[str, float] = {}
        for r in results:
            topic = r["topic"]
            if topic not in topic_best or r["similarity"] > topic_best[topic]:
                topic_best[topic] = r["similarity"]

        # Only include topics whose best score is within 0.10 of the top match,
        # so weak secondary matches don't bloat the context
        top_score = max(topic_best.values())
        relevant_topics = [t for t, s in topic_best.items() if s >= top_score - 0.10]

        root = find_project_root(args.project_dir)
        docs_dir = os.path.join(root, ".claude", "docs")
        seen_topics: set[str] = set()

        for r in results:
            topic = r["topic"]
            if topic in seen_topics or topic not in relevant_topics:
                continue
            seen_topics.add(topic)

            doc_path = os.path.join(docs_dir, f"{topic}.md")
            try:
                with open(doc_path) as f:
                    content = f.read()
            except OSError:
                continue

            print(f"## Existing doc: {topic}")
            print(f"(source: .claude/docs/{topic}.md)")
            print()
            print(content)
            print()
            print("---")
            print()
