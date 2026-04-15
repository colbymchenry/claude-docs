---
updated: 2026-04-13
---

# Frequently Bought Together (FBT) — Tag-Based Product Sourcing

## Tag Convention

Companion products for the FBT section are defined via product tags with the prefix `fbt:` followed by the companion product's handle.

**Format:** `fbt:<product-handle>`

**Examples:**
- `fbt:auburn-freeze-pearl-koozie`
- `fbt:auburn-schoolhouse-comfort-colors-t-shirt-unisex-1`

Up to **2 companion products** are shown (additional `fbt:` tags are ignored via `.slice(0, 2)` in JS).

## Data Flow

1. **Liquid** (`sections/frequently-bought-together.liquid`, lines 14-25): Loops through `product.tags`, filters tags where the first 4 chars are `fbt:`, extracts the handle via `| slice: 4, 200`, and builds a comma-separated string output as `data-fbt-handles` on the `<frequently-bought>` web component.

2. **JavaScript** (`loadCompanions()` method): Reads the `data-fbt-handles` data attribute, splits on comma, and fetches each product via the **JSON product API**: `/products/<handle>.js`. Returns full product JSON including variants.

3. **Inline rendering** (`renderCompanions()` method): Builds each companion item's DOM inline — checkbox, 60×60 thumbnail, title, price, and optional variant `<select>`. No external snippet or section rendering is used. Variant data is stored in `data-fbt-variants` on each `.fbt__item` element.

## Layout

The FBT section uses a **compact list layout** (mobile-first):
- Items stack vertically (`flex-direction: column`) with border separators
- Each row: checkbox → 60px thumbnail → details (title + price, optional variant select)
- Product titles use `text-overflow: ellipsis` for overflow protection
- Add-all button is full-width on mobile, auto-width on desktop (breakpoint: 769px)
- `overflow: hidden` on the container prevents horizontal scroll

Old layout elements (`.fbt__plus` separators, `product-card` snippet, `.fbt__rule` underline, `.fbt__item-label`) were removed in the redesign.

## Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| No `fbt:` tags on product | No `data-fbt-handles` attribute rendered; `loadCompanions()` returns immediately; section stays `hidden` |
| `fbt:` tag with invalid/nonexistent handle | Fetch returns 404 → `res.ok` is false → `null` → skipped in render loop |
| Only 1 of 2 handles resolves | Shows 1 companion product (section still reveals) |
| 0 handles resolve | `querySelectorAll` check finds no companion items → section stays `hidden` |

## Adding FBT Companions to a Product

In Shopify Admin (or via API), add tags to the product:
```
fbt:companion-product-handle-1
fbt:companion-product-handle-2
```

The handle must exactly match the companion product's URL handle in Shopify.

## Test Data

The product "Auburn Pearl/Freeze '25 Comfort Colors T-Shirt - Unisex" (`auburn-pearl-freeze-25-comfort-colors-t-shirt-unisex`) has FBT tags pointing to:
- `auburn-freeze-pearl-koozie` (Auburn Freeze/Pearl Koozie)
- `auburn-schoolhouse-comfort-colors-t-shirt-unisex-1` (Auburn SchoolHouse Tee)

This product also has 20 variants (size × color), making it useful for testing variant select behavior.

The FBT e2e tests (`e2e/frequently-bought-together.spec.ts`) use this product as the test fixture across 3 test suites: core behavior, compact list layout assertions, and mobile viewport tests.