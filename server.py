#!/usr/bin/env python3
"""MCP server giving Claude a persistent, per-project knowledge base with semantic search.

Uses ChromaDB with built-in all-MiniLM-L6-v2 embeddings (ONNX, no PyTorch).
Documents stored as plain markdown in .claude/docs/.
Embeddings stored in .claude/docs/.embeddings/.
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import date, datetime

import chromadb
from mcp.server.fastmcp import FastMCP
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------


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


def _init_paths(start_dir: str | None = None) -> tuple[str, str, str]:
    root = find_project_root(start_dir or os.getcwd())
    docs = os.path.join(root, ".claude", "docs")
    embeddings = os.path.join(docs, ".embeddings")
    return root, docs, embeddings


PROJECT_ROOT, DOCS_DIR, EMBEDDINGS_DIR = _init_paths()

# ---------------------------------------------------------------------------
# ChromaDB setup
# ---------------------------------------------------------------------------


def _probe_chromadb(embeddings_dir: str) -> bool:
    # A corrupt on-disk HNSW index (e.g. from a prior process killed mid-write)
    # segfaults ChromaDB's C extension on load, which can't be caught via
    # try/except. Run the probe in a child process so a crash is survivable.
    sqlite_path = os.path.join(embeddings_dir, "chroma.sqlite3")
    if not os.path.exists(sqlite_path):
        return True

    probe = (
        "import chromadb;"
        f"c=chromadb.PersistentClient(path={embeddings_dir!r});"
        "col=c.get_or_create_collection("
        "name='doc-chunks',metadata={'hnsw:space':'cosine'});"
        "col.count()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _init_chromadb(embeddings_dir: str) -> chromadb.Collection:
    os.makedirs(embeddings_dir, exist_ok=True)
    if not _probe_chromadb(embeddings_dir):
        print(
            f"[claude-docs] ChromaDB index at {embeddings_dir} is corrupt; "
            "wiping and rebuilding from source docs.",
            file=sys.stderr,
            flush=True,
        )
        shutil.rmtree(embeddings_dir, ignore_errors=True)
        os.makedirs(embeddings_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=embeddings_dir)
    return client.get_or_create_collection(
        name="doc-chunks",
        metadata={"hnsw:space": "cosine"},
    )


collection = _init_chromadb(EMBEDDINGS_DIR)


def _auto_index_if_needed() -> None:
    """Index any docs on disk that are missing from ChromaDB.

    Handles docs created/modified while the MCP server wasn't running.
    The DocWatcher also does this on startup, but this covers --index mode.
    """
    docs = get_all_doc_paths()
    if not docs:
        return

    # Get all indexed topics to find gaps
    indexed_topics: set[str] = set()
    try:
        all_indexed = collection.get()
        indexed_topics = {m["topic"] for m in all_indexed["metadatas"]}
    except Exception:
        pass

    for doc_path in docs:
        topic = topic_from_path(doc_path)
        if topic not in indexed_topics:
            with open(doc_path) as f:
                content = f.read()
            index_document(topic, content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def topic_from_path(file_path: str) -> str:
    return os.path.relpath(file_path, DOCS_DIR).removesuffix(".md")


def resolve_doc_path(topic: str) -> str:
    normalized = topic.removesuffix(".md").strip("/")
    resolved = os.path.normpath(os.path.join(DOCS_DIR, f"{normalized}.md"))
    if not resolved.startswith(DOCS_DIR):
        raise ValueError("Topic path escapes docs directory")
    return resolved


def get_all_doc_paths(directory: str | None = None) -> list[str]:
    directory = directory or DOCS_DIR
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


def find_docs(topic: str) -> list[str]:
    # 1. Exact path match
    try:
        exact = resolve_doc_path(topic)
        if os.path.isfile(exact):
            return [exact]
    except ValueError:
        pass

    all_docs = get_all_doc_paths()
    norm = topic.lower()

    # 2. Case-insensitive exact match
    found = [d for d in all_docs if topic_from_path(d).lower() == norm]
    if found:
        return found

    # 3. Substring match (both directions)
    found = [
        d
        for d in all_docs
        if norm in topic_from_path(d).lower() or topic_from_path(d).lower() in norm
    ]
    if found:
        return found

    # 4. Path segment match
    return [
        d
        for d in all_docs
        if any(
            norm in seg or seg in norm
            for seg in topic_from_path(d).lower().split("/")
        )
    ]


def extract_wiki_links(content: str) -> list[str]:
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def check_staleness(content: str) -> str | None:
    m = re.match(r"^---\s*\n[\s\S]*?updated:\s*(\d{4}-\d{2}-\d{2})[\s\S]*?\n---", content)
    if not m:
        return None
    updated = datetime.strptime(m.group(1), "%Y-%m-%d").date()
    days = (date.today() - updated).days
    if days > 60:
        return f"\u26a0 This doc was last updated {days} days ago \u2014 verify against source code before relying on it."
    return None


def set_updated_timestamp(content: str) -> str:
    today = date.today().isoformat()
    fm_regex = r"^---\n([\s\S]*?)\n---"
    m = re.match(fm_regex, content)

    if not m:
        return f"---\nupdated: {today}\n---\n\n{content}"

    fm = m.group(1)
    if re.search(r"^updated:", fm, re.MULTILINE):
        new_fm = re.sub(r"^updated:.*$", f"updated: {today}", fm, flags=re.MULTILINE)
        return re.sub(fm_regex, f"---\n{new_fm}\n---", content, count=1)
    return re.sub(fm_regex, f"---\nupdated: {today}\n{fm}\n---", content, count=1)


# ---------------------------------------------------------------------------
# Doc tree
# ---------------------------------------------------------------------------


@dataclass
class DocEntry:
    name: str
    topic: str
    size: int
    modified: date
    is_directory: bool
    children: list["DocEntry"] = field(default_factory=list)


def build_doc_tree(directory: str | None = None) -> list[DocEntry]:
    directory = directory or DOCS_DIR
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name)
    except OSError:
        return []

    results: list[DocEntry] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        full_path = entry.path
        if entry.is_dir():
            children = build_doc_tree(full_path)
            if children:
                results.append(
                    DocEntry(
                        name=entry.name,
                        topic=os.path.relpath(full_path, DOCS_DIR),
                        size=0,
                        modified=date.today(),
                        is_directory=True,
                        children=children,
                    )
                )
        elif entry.name.endswith(".md"):
            st = entry.stat()
            results.append(
                DocEntry(
                    name=entry.name,
                    topic=os.path.relpath(full_path, DOCS_DIR).removesuffix(".md"),
                    size=st.st_size,
                    modified=datetime.fromtimestamp(st.st_mtime).date(),
                    is_directory=False,
                )
            )
    return results


def format_tree(entries: list[DocEntry], indent: str = "") -> str:
    lines: list[str] = []
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        prefix = indent + ("\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 ")
        child_indent = indent + ("    " if is_last else "\u2502   ")
        if entry.is_directory:
            sub = "\n" + format_tree(entry.children, child_indent) if entry.children else ""
            lines.append(f"{prefix}{entry.name}/{sub}")
        else:
            size = (
                f"{entry.size} B"
                if entry.size < 1024
                else f"{entry.size / 1024:.1f} KB"
            )
            lines.append(f"{prefix}{entry.name} ({size}, updated {entry.modified.isoformat()})")
    return "\n".join(lines)


def get_tree_listing() -> str:
    tree = build_doc_tree()
    if not tree:
        return ""
    return f".claude/docs/\n{format_tree(tree)}"


# ---------------------------------------------------------------------------
# Chunking & embedding
# ---------------------------------------------------------------------------


def chunk_document(topic: str, content: str) -> list[dict]:
    """Split a markdown doc into chunks for embedding."""
    # Strip frontmatter
    body = re.sub(r"^---\n[\s\S]*?\n---\n*", "", content).strip()
    if not body:
        return []

    # Extract updated date for metadata
    updated_match = re.search(
        r"^---\n[\s\S]*?updated:\s*(\S+)[\s\S]*?\n---", content
    )
    updated = updated_match.group(1) if updated_match else ""

    # Split on ## or ### headers
    parts = re.split(r"^(#{2,3}\s+.+)$", body, flags=re.MULTILINE)

    chunks: list[dict] = []
    current_h2 = ""

    # Handle text before first header
    idx = 0
    if parts[0].strip():
        intro = parts[0].strip()
        chunks.append(
            {
                "id": f"{topic}:intro",
                "text": f"{topic}: {intro}",
                "metadata": {"topic": topic, "header": "", "updated": updated},
            }
        )
    idx = 1

    # Process header/content pairs
    while idx < len(parts):
        header_line = parts[idx].strip()
        content_text = parts[idx + 1].strip() if idx + 1 < len(parts) else ""
        idx += 2

        if header_line.startswith("### "):
            header = header_line.lstrip("#").strip()
            context = (
                f"{topic} > {current_h2} > {header}"
                if current_h2
                else f"{topic} > {header}"
            )
        elif header_line.startswith("## "):
            header = header_line.lstrip("#").strip()
            current_h2 = header
            context = f"{topic} > {header}"
        else:
            continue

        if content_text:
            # Include parent h2 in slug for h3s, and deduplicate
            if header_line.startswith("### ") and current_h2:
                slug_base = re.sub(r"[^a-z0-9]+", "-", f"{current_h2}-{header}".lower()).strip("-")
            else:
                slug_base = re.sub(r"[^a-z0-9]+", "-", header.lower()).strip("-")
            # Ensure uniqueness by appending a counter if needed
            slug = slug_base
            existing_ids = {c["id"] for c in chunks}
            counter = 2
            while f"{topic}:{slug}" in existing_ids:
                slug = f"{slug_base}-{counter}"
                counter += 1
            chunks.append(
                {
                    "id": f"{topic}:{slug}",
                    "text": f"{context}: {content_text}",
                    "metadata": {"topic": topic, "header": header, "updated": updated},
                }
            )

    # If no chunks created (no headers), treat whole doc as one chunk
    if not chunks:
        chunks.append(
            {
                "id": f"{topic}:full",
                "text": f"{topic}: {body}",
                "metadata": {"topic": topic, "header": "", "updated": updated},
            }
        )

    return chunks


def index_document(topic: str, content: str) -> None:
    """Delete old chunks for topic, re-chunk, and embed."""
    remove_from_index(topic)
    chunks = chunk_document(topic, content)
    if chunks:
        collection.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
        )


def remove_from_index(topic: str) -> None:
    """Remove all chunks for a topic from the index."""
    try:
        existing = collection.get(where={"topic": topic})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass


def index_all_existing_docs() -> int:
    """Bootstrap: index all existing docs into ChromaDB."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    count = 0
    for doc_path in get_all_doc_paths():
        topic = topic_from_path(doc_path)
        with open(doc_path) as f:
            content = f.read()
        index_document(topic, content)
        count += 1
    return count


# ---------------------------------------------------------------------------
# File watcher — auto-indexes docs on filesystem changes
# ---------------------------------------------------------------------------


def _hash_file(path: str) -> str:
    """SHA256 of file contents for change detection."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class DocWatcher(FileSystemEventHandler):
    """Watches .claude/docs/ and re-indexes changed files with debouncing.

    Mirrors the codegraph FileWatcher pattern: content hashing to detect real
    changes, debounce timer to coalesce rapid edits, backpressure handling to
    re-sync if changes arrive during indexing.
    """

    def __init__(
        self,
        docs_dir: str,
        sync_fn: callable,
        debounce_s: float = 2.0,
    ):
        super().__init__()
        self.docs_dir = docs_dir
        self.sync_fn = sync_fn
        self.debounce_s = debounce_s

        self._hashes: dict[str, str] = {}  # path -> sha256
        self._has_changes = False
        self._syncing = False
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._observer: Observer | None = None

        # Snapshot current state
        self._snapshot_hashes()

    def _snapshot_hashes(self) -> None:
        """Build initial hash map of all docs on disk and index any untracked docs."""
        indexed_topics = set()
        try:
            all_indexed = collection.get()
            indexed_topics = {m["topic"] for m in all_indexed["metadatas"]}
        except Exception:
            pass

        for doc_path in get_all_doc_paths(self.docs_dir):
            try:
                self._hashes[doc_path] = _hash_file(doc_path)
            except OSError:
                continue

            # Index docs that exist on disk but aren't in ChromaDB
            topic = topic_from_path(doc_path)
            if topic not in indexed_topics:
                with open(doc_path) as f:
                    content = f.read()
                self.sync_fn(topic, content)
                log.info("Indexed %s (found untracked on startup)", topic)

    def _is_doc_file(self, path: str) -> bool:
        """Filter: only .md files, not inside .embeddings/."""
        if not path.endswith(".md"):
            return False
        if "/.embeddings/" in path or path.startswith(
            os.path.join(self.docs_dir, ".embeddings")
        ):
            return False
        return path.startswith(self.docs_dir)

    # -- watchdog event handler ------------------------------------------------

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = event.src_path
        if not self._is_doc_file(path):
            return
        self._has_changes = True
        self._schedule_sync()

    # -- debounce + sync -------------------------------------------------------

    def _schedule_sync(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_s, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        if self._syncing:
            return

        self._has_changes = False
        self._syncing = True
        try:
            self._do_sync()
        except Exception:
            log.exception("Doc watcher sync failed")
        finally:
            self._syncing = False
            # If changes arrived during sync, re-schedule (backpressure)
            if self._has_changes:
                self._schedule_sync()

    def _do_sync(self) -> None:
        """Diff files on disk vs hashes, index added/modified, remove deleted."""
        current_files = {p: None for p in get_all_doc_paths(self.docs_dir)}

        # Detect added + modified
        for doc_path in current_files:
            try:
                new_hash = _hash_file(doc_path)
            except OSError:
                continue
            old_hash = self._hashes.get(doc_path)
            if new_hash != old_hash:
                topic = topic_from_path(doc_path)
                with open(doc_path) as f:
                    content = f.read()
                self.sync_fn(topic, content)
                self._hashes[doc_path] = new_hash
                log.info("Indexed %s (changed)" if old_hash else "Indexed %s (new)", topic)

        # Detect deleted
        deleted = set(self._hashes) - set(current_files)
        for doc_path in deleted:
            topic = topic_from_path(doc_path)
            remove_from_index(topic)
            del self._hashes[doc_path]
            log.info("Removed from index: %s", topic)

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> bool:
        os.makedirs(self.docs_dir, exist_ok=True)
        self._observer = Observer()
        self._observer.schedule(self, self.docs_dir, recursive=True)
        self._observer.daemon = True
        try:
            self._observer.start()
            log.info("Doc watcher started on %s", self.docs_dir)
            return True
        except Exception:
            log.exception("Failed to start doc watcher")
            return False

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

_auto_index_if_needed()

mcp = FastMCP("claude-docs")


@mcp.tool()
def list_docs() -> str:
    """List all available project documentation. Call this at the start of every task to understand what knowledge already exists about this project. Returns a tree of all docs with metadata. Docs in the workflow/ directory are auto-inlined because they contain project conventions that apply to every task."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    listing = get_tree_listing()

    if not listing:
        return "No documentation found in .claude/docs/. Use save_doc to create documentation as you discover project architecture and patterns."

    # Auto-inline workflow docs
    workflow_dir = os.path.join(DOCS_DIR, "workflow")
    workflow_docs: list[str] = []
    try:
        for file_path in get_all_doc_paths(workflow_dir):
            with open(file_path) as f:
                content = f.read()
            topic = topic_from_path(file_path)
            workflow_docs.append(f"### {topic}\n{content}")
    except OSError:
        pass

    parts = [listing]
    if workflow_docs:
        parts.append("")
        parts.append("---")
        parts.append(
            "## Workflow conventions (always apply \u2014 read before starting any task):"
        )
        parts.append("")
        parts.append("\n\n".join(workflow_docs))

    return "\n".join(parts)


@mcp.tool()
def lookup_doc(topic: str) -> str:
    """Retrieve project documentation for a specific topic or subsystem. ALWAYS check for existing documentation before reading source code for any subsystem — this saves significant time. Supports nested topics like 'database/schema'. If no exact match is found, returns available docs so you can pick the closest one. If a doc hasn't been updated in over 60 days, verify its claims against source code before relying on it."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    matches = find_docs(topic)

    if not matches:
        listing = get_tree_listing()
        if listing:
            return f'No doc found matching "{topic}". Available docs:\n\n{listing}'
        return f'No doc found matching "{topic}". No documentation exists yet.'

    if len(matches) > 1:
        doc_list = "\n".join(f"  - {topic_from_path(m)}" for m in matches)
        return f'Multiple docs match "{topic}":\n{doc_list}\n\nCall lookup_doc with a more specific topic.'

    doc_path = matches[0]
    with open(doc_path) as f:
        content = f.read()
    resolved_topic = topic_from_path(doc_path)

    parts: list[str] = []

    staleness = check_staleness(content)
    if staleness:
        parts.append(staleness)
        parts.append("")

    parts.append(f"# {resolved_topic}")
    parts.append("")
    parts.append(content)

    wiki_links = extract_wiki_links(content)
    if wiki_links:
        parts.append("")
        parts.append("---")
        parts.append("Related docs referenced in this file:")
        for link in wiki_links:
            link_matches = find_docs(link)
            status = "\u2713 exists" if link_matches else "\u2717 not found"
            parts.append(f"  - [[{link}]] {status}")

    return "\n".join(parts)


@mcp.tool()
def save_doc(topic: str, content: str) -> str:
    """Create or update project documentation in .claude/docs/. Prefer this tool when available, but files written directly to .claude/docs/ via Edit/Write tools are also auto-indexed by the file watcher. ALWAYS call lookup_doc() first to read existing content before overwriting — never save blindly. Document anything you had to look up or figure out: config formats, correct setting names/types, API patterns, schema details, how subsystems connect, error fixes, non-obvious conventions. If you read code to learn it, it belongs in a doc — 'derivable from code' is not a reason to skip. Write docs that are factual and specific — include actual config values, correct types, file paths, function names, and working examples. When updating an existing doc, rewrite it completely to reflect current state — do not append."""
    doc_path = resolve_doc_path(topic)
    os.makedirs(os.path.dirname(doc_path), exist_ok=True)

    previous_content = None
    try:
        with open(doc_path) as f:
            previous_content = f.read()
    except FileNotFoundError:
        pass

    final_content = set_updated_timestamp(content)
    with open(doc_path, "w") as f:
        f.write(final_content)

    # Indexing handled by DocWatcher on filesystem change

    parts: list[str] = []
    if previous_content:
        parts.append(f"Updated doc: {topic}")
        parts.append("")
        parts.append("Previous content that was overwritten:")
        parts.append("```markdown")
        parts.append(previous_content)
        parts.append("```")
    else:
        parts.append(f"Created doc: {topic}")

    return "\n".join(parts)


@mcp.tool()
def search_docs(query: str) -> str:
    """Search across the contents of all project documentation. Use this when you know a keyword, function name, config value, or concept but aren't sure which doc covers it. Supports regex patterns. Returns matching doc names with context snippets. Complements lookup_doc (which matches by topic name) with content-based search."""
    os.makedirs(DOCS_DIR, exist_ok=True)

    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    results: list[str] = []

    for doc_path in get_all_doc_paths():
        try:
            with open(doc_path) as f:
                lines = f.readlines()
        except OSError:
            continue

        match_indices = [i for i, line in enumerate(lines) if pattern.search(line)]
        if not match_indices:
            continue

        topic = topic_from_path(doc_path)
        file_lines = [f"{topic}.md"]

        for match_idx in match_indices:
            start = max(0, match_idx - 2)
            end = min(len(lines), match_idx + 3)
            for j in range(start, end):
                prefix = f"{j + 1}:" if j == match_idx else f"{j + 1}-"
                file_lines.append(f"{prefix}{lines[j].rstrip()}")
            file_lines.append("--")

        results.append("\n".join(file_lines))

    if not results:
        return f'No matches found for "{query}" in docs.'

    return f'Search results for "{query}":\n\n' + "\n\n".join(results)


@mcp.tool()
def delete_doc(topic: str) -> str:
    """Delete a project documentation file. Use when a subsystem has been removed or when consolidating multiple docs."""
    doc_path = resolve_doc_path(topic)
    if not os.path.isfile(doc_path):
        return f'No doc found at "{topic}". Use list_docs to see available docs.'

    os.unlink(doc_path)

    # Embedding removal handled by DocWatcher

    # Clean up empty parent directories
    d = os.path.dirname(doc_path)
    while d != DOCS_DIR and d.startswith(DOCS_DIR):
        try:
            if not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
            else:
                break
        except OSError:
            break

    return f"Deleted doc: {topic}"


@mcp.tool()
def semantic_search_docs(query: str, n_results: int = 5) -> str:
    """Search documentation by meaning using semantic similarity. Use when keyword search doesn't find what you need, or when looking for conceptually related content across docs. For example, searching 'authentication flow' will find docs about login, sessions, and OAuth even if they don't contain the word 'authentication'.

    Args:
        query: Natural language description of what you're looking for.
        n_results: Maximum number of results to return (default 5).
    """
    total = collection.count()
    if total == 0:
        return "No documentation has been indexed yet. Save some docs first."

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, total),
    )

    if not results["documents"][0]:
        return f'No semantic matches found for "{query}".'

    output: list[str] = []
    seen_topics: set[str] = set()

    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        similarity = 1 - dist
        if similarity < 0.25:
            continue

        topic = meta.get("topic", "unknown")
        header = meta.get("header", "")
        location = f"{topic} > {header}" if header else topic

        # Strip the context prefix added during chunking
        display_text = doc
        prefix_end = doc.find(": ")
        if 0 < prefix_end < 80:
            display_text = doc[prefix_end + 2 :]

        output.append(f"[{similarity:.2f}] {location}\n{display_text}")
        seen_topics.add(topic)

    if not output:
        return f'No relevant matches found for "{query}".'

    header = f'Semantic search results for "{query}":'
    footer = f"\nTopics with matches: {', '.join(sorted(seen_topics))}"
    footer += "\nUse lookup_doc(topic) to read the full document."

    return header + "\n\n" + "\n\n---\n\n".join(output) + "\n" + footer


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--index":
        # Optional: --index /path/to/project
        if len(sys.argv) > 2:
            PROJECT_ROOT, DOCS_DIR, EMBEDDINGS_DIR = _init_paths(sys.argv[2])
            collection = _init_chromadb(EMBEDDINGS_DIR)
        count = index_all_existing_docs()
        print(f"Indexed {count} documents in {DOCS_DIR}")
    else:
        # Start file watcher before MCP server
        _watcher = DocWatcher(DOCS_DIR, sync_fn=index_document)
        _watcher.start()
        try:
            mcp.run()
        finally:
            _watcher.stop()
