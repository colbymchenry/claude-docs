---
updated: 2026-04-12
---

# PostgreSQL Store — Raw SQL Conventions

`src/lib/stores/postgresql-store.ts` writes raw SQL via `pg` (no ORM, no query builder). A few non-obvious gotchas to watch for when adding/modifying queries here.

## Avoid reserved keywords as identifiers (table aliases, column aliases, CTE names)

PostgreSQL's reserved keyword list is stricter than you might expect. Notably reserved words that commonly appear as aliases: `desc`, `asc`, `user`, `order`, `group`, `table`, `check`, `limit`, `offset`, `end`, `all`, `any`, `case`, `when`, `then`, `cast`, `current_user`.

These fail at parse time if used unquoted as an identifier — producing an opaque syntax error that surfaces as a 500 from whatever endpoint called the store.

**Known past bug:** `getAllDescendantIssues` used `JOIN descendants desc ON ...` in a recursive CTE. `DESC` is reserved (`ORDER BY x DESC`), so every call threw a syntax error. Fix was renaming the alias to `descs`. See commit that fixes the DELETE-epic 500 for the full context.

**Rule:** Pick short but non-reserved aliases. Safe choices: `i` (issues), `d` (dependencies), `c` (comments), `e` (events), `descs`, `anc` (ancestors), `t` (generic tree CTE).

## Shared trigger functions must be table-shape-agnostic

`kommandr_notify_change()` is a single trigger function attached to four tables via `AFTER INSERT OR UPDATE OR DELETE` triggers: `issues`, `dependencies`, `comments`, `events`. These tables have **different primary key shapes**:

| Table          | Primary key                                 | Has `id` column? |
|----------------|---------------------------------------------|------------------|
| `issues`       | `id TEXT PRIMARY KEY`                       | yes              |
| `comments`     | `id SERIAL PRIMARY KEY`                     | yes              |
| `events`       | `id SERIAL PRIMARY KEY`                     | yes              |
| `dependencies` | `PRIMARY KEY (issue_id, depends_on_id, type)` | **no**         |

A plpgsql trigger function that references `NEW.id` / `OLD.id` directly will fail on `dependencies` with:

```
error: record "new" has no field "id"
```

This error aborts the INSERT/UPDATE/DELETE on `dependencies`, which in turn breaks:
- `kommandr_dep_add` (direct insert into `dependencies`) — visible as "Failed to add dependency"
- `kommandr_create` with a `parent` or `deps` — because POST `/issues` calls `store.addDependency(...)` after creating the row (see `src/routes/api/projects/[id]/issues/+server.ts`).

**Fix pattern:** use `to_jsonb(NEW)->>'field'` for safe field access. If the row has no such field, it returns NULL instead of erroring. Current implementation:

```sql
CREATE OR REPLACE FUNCTION kommandr_notify_change() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('kommandr_changes', json_build_object(
    'table', TG_TABLE_NAME,
    'op', TG_OP,
    'id', COALESCE(
      to_jsonb(NEW)->>'id', to_jsonb(OLD)->>'id',
      to_jsonb(NEW)->>'issue_id', to_jsonb(OLD)->>'issue_id'
    )
  )::text);
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
```

**Rule:** Any shared trigger function (or future one) that spans tables with different row shapes must use `to_jsonb(NEW)->>'...'` — never bare `NEW.<col>` — for any column not guaranteed to exist on every table it's attached to.

## Schema is replayed on every server start

`ensureSchema()` (postgresql-store.ts:185) runs `SCHEMA_SQL` once per process, guarded by `this.initialized`. All `CREATE ... IF NOT EXISTS` and `CREATE OR REPLACE FUNCTION` statements run every fresh boot — so editing a function body in `SCHEMA_SQL` and restarting the app is enough to propagate the change to live Postgres. No migration file needed for function bodies.

Caveat: `CREATE TABLE IF NOT EXISTS` will NOT alter an existing table's columns. Column additions/renames do need explicit `ALTER TABLE ... IF NOT EXISTS` or a real migration.

## Recursive CTEs

Use `WITH RECURSIVE` (not recursive JS traversal) for tree walks. The SQLite store does recursive JS because `better-sqlite3` is sync; the PG store should prefer a single round-trip via CTE.

Pattern used for parent-child descendant traversal:

```sql
WITH RECURSIVE descendants AS (
  -- base case: direct children of $1
  SELECT i.<cols>
  FROM issues i
  JOIN dependencies d ON i.id = d.issue_id
  WHERE d.depends_on_id = $1 AND d.type = 'parent-child' AND i.deleted_at IS NULL
UNION
  -- recursive case: children of already-found descendants
  SELECT i.<cols>
  FROM issues i
  JOIN dependencies d ON i.id = d.issue_id
  JOIN descendants descs ON d.depends_on_id = descs.id
  WHERE d.type = 'parent-child' AND i.deleted_at IS NULL
)
SELECT * FROM descendants;
```

Column names in the CTE are inferred from the first SELECT — keep both arms' column lists identical and in the same order.

## Delete semantics — hard delete

`deleteIssueWithDescendants` **hard-deletes** issues (and their descendants) from the database. The `deleted_at TIMESTAMPTZ` column is still present in `SCHEMA_SQL` and queries still include `AND i.deleted_at IS NULL` defensively, but new deletes never set it — the row is simply gone.

**Cascade behavior:** the schema declares `REFERENCES issues(id) ON DELETE CASCADE` on `dependencies`, `comments`, and `labels`. The `events` table is **not** declared with a FK to `issues` (see `SCHEMA_SQL` — it only has `issue_id TEXT NOT NULL`), so `events` rows must be deleted **explicitly** before deleting from `issues`, or the issue row can be removed while orphan event rows persist.

Current implementation wraps the two statements in a transaction (postgresql-store.ts `deleteIssueWithDescendants`):

```ts
await client.query('BEGIN');
await client.query(`DELETE FROM events WHERE issue_id = ANY($1)`, [allIds]);
await client.query(`DELETE FROM issues WHERE id = ANY($1)`, [allIds]);
await client.query('COMMIT');
```

**Rule:** If you add a new table that references `issues.id` **without** `ON DELETE CASCADE`, you must also add an explicit `DELETE FROM <table> WHERE issue_id = ANY($1)` call to this transaction — otherwise deletes will leave orphans.

The parallel SQLite implementation (`src/lib/stores/sqlite-store.ts`) does **not** rely on FK cascade (the beads-managed SQLite schema doesn't declare them) — it explicitly deletes from `comments`, `events`, `dependencies`, then `issues` inside a `better-sqlite3` transaction.

## Array params

Use `= ANY($1)` with a JS array for `IN (...)` semantics — do NOT build placeholder strings like the SQLite store does. Example:

```ts
await this.pool.query(
  `DELETE FROM events WHERE issue_id = ANY($1)`,
  [allIds]
);
```

## API routes must surface the underlying error

The routes under `src/routes/api/projects/[id]/issues/` and `.../dependencies/` historically returned generic strings like `"Failed to create issue"` and logged the real error only to stderr. That hid SQL trigger errors from the MCP server (and from the Claude planner UI, which only shows the 500 body as a tool result). Current convention: include `e.message` in the JSON body:

```ts
} catch (e) {
  console.error('Error creating issue:', e);
  const message = e instanceof Error ? e.message : String(e);
  return json({ error: `Failed to create issue: ${message}` }, { status: 500 });
}
```

Apply this pattern to every new route that wraps a store call — the MCP server surfaces `body.error` directly to Claude, so the real reason (e.g. `record "new" has no field "id"`) needs to be in the body, not just the logs.

## Testing queries against the live DB

No local Postgres is assumed; the project connects to Neon via `.kommandr/adapter.json`. Before shipping a new query, either:
- Run it against a dev Neon branch, or
- At minimum, paste it into a PG linter/formatter to catch reserved-word and syntax issues.

`npx tsc --noEmit` will NOT catch SQL syntax errors — it only validates the TypeScript around the query string.
