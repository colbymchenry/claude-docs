---
updated: 2026-04-14
---

# Shopify Theme Check CLI

## Basic Usage

Run from the **project root** with no arguments:

```bash
shopify theme check
```

## Gotcha: `--path` expects a directory, not a file

The `--path` flag takes a **directory** path. Passing a file path (e.g., `--path sections/product.liquid`) causes an `ENOTDIR` error:

```
ENOTDIR: not a directory, scandir '/path/to/sections/product.liquid'
```

There is no built-in way to check a single file — always run from the project root against the full theme.

## Output

On success, reports the number of files inspected and offenses found:

```
Theme Check Summary.
74 files inspected with no offenses found.
```

Exit code 0 = clean, exit code 1 = errors found (or CLI error).
