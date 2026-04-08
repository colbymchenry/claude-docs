#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  readdir,
  stat,
  readFile,
  writeFile,
  mkdir,
  unlink,
  rmdir,
  access,
} from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, dirname, relative, resolve } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const rgPath: string = require("@vscode/ripgrep").rgPath;
const execFileAsync = promisify(execFile);

// --- Project root detection ---

function findProjectRoot(startDir: string): string {
  let dir = resolve(startDir);
  while (true) {
    if (existsSync(join(dir, ".git")) || existsSync(join(dir, "CLAUDE.md"))) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) return resolve(startDir);
    dir = parent;
  }
}

const PROJECT_ROOT = findProjectRoot(process.cwd());
const DOCS_DIR = join(PROJECT_ROOT, ".claude", "docs");

// --- Helpers ---

async function ensureDocsDir(): Promise<void> {
  await mkdir(DOCS_DIR, { recursive: true });
}

interface DocEntry {
  name: string;
  topic: string;
  size: number;
  modified: Date;
  isDirectory: boolean;
  children?: DocEntry[];
}

async function buildDocTree(dir: string = DOCS_DIR): Promise<DocEntry[]> {
  try {
    const entries = await readdir(dir, { withFileTypes: true });
    const results: DocEntry[] = [];
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const fullPath = join(dir, entry.name);
      if (entry.isDirectory()) {
        const children = await buildDocTree(fullPath);
        if (children.length > 0) {
          results.push({
            name: entry.name,
            topic: relative(DOCS_DIR, fullPath),
            size: 0,
            modified: new Date(),
            isDirectory: true,
            children,
          });
        }
      } else if (entry.name.endsWith(".md")) {
        const s = await stat(fullPath);
        results.push({
          name: entry.name,
          topic: relative(DOCS_DIR, fullPath).replace(/\.md$/, ""),
          size: s.size,
          modified: s.mtime,
          isDirectory: false,
        });
      }
    }
    return results;
  } catch {
    return [];
  }
}

function formatTree(entries: DocEntry[], indent = ""): string {
  return entries
    .map((entry, i) => {
      const isLast = i === entries.length - 1;
      const prefix = indent + (isLast ? "└── " : "├── ");
      const childIndent = indent + (isLast ? "    " : "│   ");
      if (entry.isDirectory) {
        const sub = entry.children
          ? "\n" + formatTree(entry.children, childIndent)
          : "";
        return `${prefix}${entry.name}/${sub}`;
      }
      const size =
        entry.size < 1024
          ? `${entry.size} B`
          : `${(entry.size / 1024).toFixed(1)} KB`;
      const date = entry.modified.toISOString().split("T")[0];
      return `${prefix}${entry.name} (${size}, updated ${date})`;
    })
    .join("\n");
}

async function getAllDocPaths(dir: string = DOCS_DIR): Promise<string[]> {
  const results: string[] = [];
  try {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) results.push(...(await getAllDocPaths(full)));
      else if (entry.name.endsWith(".md")) results.push(full);
    }
  } catch {}
  return results;
}

function topicFromPath(filePath: string): string {
  return relative(DOCS_DIR, filePath).replace(/\.md$/, "");
}

function resolveDocPath(topic: string): string {
  const normalized = topic.replace(/\.md$/, "").replace(/^\/+|\/+$/g, "");
  const resolved = resolve(DOCS_DIR, `${normalized}.md`);
  if (!resolved.startsWith(DOCS_DIR)) {
    throw new Error("Topic path escapes docs directory");
  }
  return resolved;
}

async function findDocs(topic: string): Promise<string[]> {
  // 1. Exact path match
  const exact = resolveDocPath(topic);
  try {
    await access(exact);
    return [exact];
  } catch {}

  const allDocs = await getAllDocPaths();
  const norm = topic.toLowerCase();

  // 2. Case-insensitive exact match
  let found = allDocs.filter(
    (d) => topicFromPath(d).toLowerCase() === norm,
  );
  if (found.length > 0) return found;

  // 3. Substring match
  found = allDocs.filter((d) => {
    const t = topicFromPath(d).toLowerCase();
    return t.includes(norm) || norm.includes(t);
  });
  if (found.length > 0) return found;

  // 4. Path segment match
  return allDocs.filter((d) =>
    topicFromPath(d)
      .toLowerCase()
      .split("/")
      .some((s) => s.includes(norm) || norm.includes(s)),
  );
}

function extractWikiLinks(content: string): string[] {
  const links: string[] = [];
  let match;
  const re = /\[\[([^\]]+)\]\]/g;
  while ((match = re.exec(content))) links.push(match[1]);
  return links;
}

function checkStaleness(content: string): string | null {
  const m = content.match(
    /^---\s*\n[\s\S]*?updated:\s*(\d{4}-\d{2}-\d{2})[\s\S]*?\n---/,
  );
  if (!m) return null;
  const days = Math.floor(
    (Date.now() - new Date(m[1]).getTime()) / 86_400_000,
  );
  return days > 60
    ? `⚠ This doc was last updated ${days} days ago — verify against source code before relying on it.`
    : null;
}

function setUpdatedTimestamp(content: string): string {
  const today = new Date().toISOString().split("T")[0];
  const fmRegex = /^---\n([\s\S]*?)\n---/;
  const match = content.match(fmRegex);

  if (!match) {
    return `---\nupdated: ${today}\n---\n\n${content}`;
  }

  const fm = match[1];
  if (/^updated:/m.test(fm)) {
    const newFm = fm.replace(/^updated:.*$/m, `updated: ${today}`);
    return content.replace(fmRegex, `---\n${newFm}\n---`);
  }
  return content.replace(fmRegex, `---\nupdated: ${today}\n${fm}\n---`);
}

async function getTreeListing(): Promise<string> {
  const tree = await buildDocTree();
  if (tree.length === 0) return "";
  return `.claude/docs/\n${formatTree(tree)}`;
}

// --- MCP Server ---

const server = new McpServer({
  name: "claude-docs",
  version: "1.0.0",
});

server.tool(
  "list_docs",
  "List all available project documentation. Call this at the start of every task to understand what knowledge already exists about this project. Returns a tree of all docs with metadata. Docs in the workflow/ directory are auto-inlined because they contain project conventions that apply to every task.",
  {},
  { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  async () => {
    await ensureDocsDir();
    const listing = await getTreeListing();
    if (!listing) {
      return {
        content: [
          {
            type: "text" as const,
            text: "No documentation found in .claude/docs/. Use save_doc to create documentation as you discover project architecture and patterns.",
          },
        ],
      };
    }

    // Auto-inline workflow docs — they're small and always applicable
    const workflowDir = join(DOCS_DIR, "workflow");
    const workflowDocs: string[] = [];
    try {
      const files = await getAllDocPaths(workflowDir);
      for (const file of files) {
        const content = await readFile(file, "utf-8");
        const topic = topicFromPath(file);
        workflowDocs.push(`### ${topic}\n${content}`);
      }
    } catch {}

    const parts = [listing];
    if (workflowDocs.length > 0) {
      parts.push("");
      parts.push("---");
      parts.push(
        "## Workflow conventions (always apply — read before starting any task):",
      );
      parts.push("");
      parts.push(workflowDocs.join("\n\n"));
    }

    return { content: [{ type: "text" as const, text: parts.join("\n") }] };
  },
);

server.tool(
  "lookup_doc",
  "Retrieve project documentation for a specific topic or subsystem. ALWAYS check for existing documentation before reading source code for any subsystem — this saves significant time. Supports nested topics like 'database/schema'. If no exact match is found, returns available docs so you can pick the closest one. If a doc hasn't been updated in over 60 days, verify its claims against source code before relying on it.",
  {
    topic: z
      .string()
      .describe("Topic or path like 'auth', 'database/schema', 'design-system'"),
  },
  { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  async ({ topic }) => {
    await ensureDocsDir();
    const matches = await findDocs(topic);

    if (matches.length === 0) {
      const listing = await getTreeListing();
      const text = listing
        ? `No doc found matching "${topic}". Available docs:\n\n${listing}`
        : `No doc found matching "${topic}". No documentation exists yet.`;
      return { content: [{ type: "text" as const, text }], isError: true };
    }

    if (matches.length > 1) {
      const list = matches.map((m) => `  - ${topicFromPath(m)}`).join("\n");
      const text = `Multiple docs match "${topic}":\n${list}\n\nCall lookup_doc with a more specific topic.`;
      return { content: [{ type: "text" as const, text }], isError: true };
    }

    const docPath = matches[0];
    const content = await readFile(docPath, "utf-8");
    const resolvedTopic = topicFromPath(docPath);
    const parts: string[] = [];

    const stalenessWarning = checkStaleness(content);
    if (stalenessWarning) {
      parts.push(stalenessWarning);
      parts.push("");
    }

    parts.push(`# ${resolvedTopic}`);
    parts.push("");
    parts.push(content);

    const wikiLinks = extractWikiLinks(content);
    if (wikiLinks.length > 0) {
      parts.push("");
      parts.push("---");
      parts.push("Related docs referenced in this file:");
      for (const link of wikiLinks) {
        const linkMatches = await findDocs(link);
        parts.push(
          `  - [[${link}]] ${linkMatches.length > 0 ? "✓ exists" : "✗ not found"}`,
        );
      }
    }

    return { content: [{ type: "text" as const, text: parts.join("\n") }] };
  },
);

server.tool(
  "save_doc",
  "Create or update project documentation in .claude/docs/. ALWAYS use this tool to write docs — NEVER use Edit or Write tools on .claude/docs/ files directly. ALWAYS call lookup_doc() first to read existing content before overwriting — never save blindly. Document anything you had to look up or figure out: config formats, correct setting names/types, API patterns, schema details, how subsystems connect, error fixes, non-obvious conventions. If you read code to learn it, it belongs in a doc — 'derivable from code' is not a reason to skip. Write docs that are factual and specific — include actual config values, correct types, file paths, function names, and working examples. When updating an existing doc, rewrite it completely to reflect current state — do not append.",
  {
    topic: z
      .string()
      .describe("Topic path like 'auth', 'database/schema', 'api/middleware'"),
    content: z.string().describe("Full markdown content for the doc"),
  },
  async ({ topic, content }) => {
    const docPath = resolveDocPath(topic);
    await mkdir(dirname(docPath), { recursive: true });

    let previousContent: string | null = null;
    try {
      previousContent = await readFile(docPath, "utf-8");
    } catch {}

    const finalContent = setUpdatedTimestamp(content);
    await writeFile(docPath, finalContent, "utf-8");

    const parts: string[] = [];
    if (previousContent) {
      parts.push(`Updated doc: ${topic}`);
      parts.push("");
      parts.push("Previous content that was overwritten:");
      parts.push("```markdown");
      parts.push(previousContent);
      parts.push("```");
    } else {
      parts.push(`Created doc: ${topic}`);
    }

    return { content: [{ type: "text" as const, text: parts.join("\n") }] };
  },
);

server.tool(
  "search_docs",
  "Search across the contents of all project documentation. Use this when you know a keyword, function name, config value, or concept but aren't sure which doc covers it. Supports regex patterns. Returns matching doc names with context snippets. Complements lookup_doc (which matches by topic name) with content-based search.",
  { query: z.string().describe("Search query (supports regex)") },
  { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  async ({ query }) => {
    await ensureDocsDir();

    try {
      const { stdout } = await execFileAsync(rgPath, [
        "--ignore-case",
        "--line-number",
        "--context",
        "2",
        "--color",
        "never",
        "--heading",
        "--glob",
        "*.md",
        query,
        DOCS_DIR,
      ]);

      if (!stdout.trim()) {
        return {
          content: [
            {
              type: "text" as const,
              text: `No matches found for "${query}" in docs.`,
            },
          ],
        };
      }

      // Rewrite absolute paths to relative topic paths
      const docsPrefix = DOCS_DIR + "/";
      const output = stdout.replaceAll(docsPrefix, "");

      return {
        content: [
          {
            type: "text" as const,
            text: `Search results for "${query}":\n\n${output}`,
          },
        ],
      };
    } catch (err: unknown) {
      const execErr = err as { stderr?: string };
      // ripgrep exits with code 1 when no matches found
      if (!execErr.stderr?.trim()) {
        return {
          content: [
            {
              type: "text" as const,
              text: `No matches found for "${query}" in docs.`,
            },
          ],
        };
      }
      return {
        content: [
          {
            type: "text" as const,
            text: `Search error: ${execErr.stderr}`,
          },
        ],
        isError: true,
      };
    }
  },
);

server.tool(
  "delete_doc",
  "Delete a project documentation file. Use when a subsystem has been removed or when consolidating multiple docs.",
  {
    topic: z
      .string()
      .describe("Exact topic path like 'auth', 'database/schema'"),
  },
  { destructiveHint: true, openWorldHint: false },
  async ({ topic }) => {
    const docPath = resolveDocPath(topic);
    try {
      await access(docPath);
    } catch {
      return {
        content: [
          {
            type: "text" as const,
            text: `No doc found at "${topic}". Use list_docs to see available docs.`,
          },
        ],
        isError: true,
      };
    }

    await unlink(docPath);

    // Clean up empty parent directories
    let dir = dirname(docPath);
    while (dir !== DOCS_DIR && dir.startsWith(DOCS_DIR)) {
      try {
        const entries = await readdir(dir);
        if (entries.length === 0) {
          await rmdir(dir);
          dir = dirname(dir);
        } else {
          break;
        }
      } catch {
        break;
      }
    }

    return {
      content: [{ type: "text" as const, text: `Deleted doc: ${topic}` }],
    };
  },
);

// --- Start ---

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Failed to start claude-docs server:", err);
  process.exit(1);
});
