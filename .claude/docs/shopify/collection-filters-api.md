---
updated: 2026-04-14
---

# Shopify Collection Filters — Liquid API & Web Component

The `collection.filters` object provides storefront filtering. Used in `sections/collection.liquid` for the filter sidebar/drawer, active filter chips bar, and AJAX filtering via the `<collection-filters>` web component.

## Filter Object Structure

```liquid
{% for filter in collection.filters %}
  filter.label        → "Color", "Size", "Price", "Availability"
  filter.type         → "list" | "price_range" | "boolean"
  filter.active_values → array of active FilterValue objects (for list/boolean)
  filter.values       → array of all FilterValue objects
  filter.url_to_remove → URL that removes this entire filter (price_range uses this)
{% endfor %}
```

## FilterValue Object (for `list` and `boolean` types)

```liquid
{% for value in filter.active_values %}
  value.label          → "Red", "Large", "In stock"
  value.url_to_remove  → URL that removes just this one value
  value.count          → number of products matching
  value.active         → boolean
  value.param_name     → "filter.v.availability" (used as checkbox name)
  value.value          → "1" (used as checkbox value)
{% endfor %}
```

## Price Range Filter (special case)

Price range filters have NO `active_values`. Instead check:

```liquid
{% if filter.type == 'price_range' %}
  filter.min_value.value      → integer cents (nil if not set)
  filter.max_value.value      → integer cents (nil if not set)
  filter.min_value.param_name → "filter.v.price.gte"
  filter.max_value.param_name → "filter.v.price.lte"
  filter.range_max            → maximum price in collection (cents)
  filter.url_to_remove        → URL that clears the price range
{% endif %}
```

Use `| money_without_trailing_zeros` to format price values for display.

## URL Parameters

Filters use query parameters on the collection URL:
- List filters: `?filter.v.availability=1`
- Metaobject filters: `?filter.p.m.custom.school=Alabama`
- Price range: `?filter.v.price.gte=2000&filter.v.price.lte=5000` (values in cents)
- Multiple: combine with `&`
- Clear all: link to `{{ collection.url }}` (base URL without params)

## DOM Structure & Key Selectors

### Filter Sidebar/Drawer
- `<collection-filters data-section-id="...">` — outer web component, wraps everything
- `[data-filter-sidebar]` — the sidebar `<aside>` element
- `[data-filter-toggle]` — mobile filter button (hidden on desktop via CSS)
- `[data-filter-close]` — close button inside drawer
- `[data-filter-backdrop]` — backdrop overlay for mobile drawer
- `[data-collection-filters-form]` — the `<form>` containing all filter inputs
- `.filter-group` — `<details open>` accordion for each filter group
- `.filter-option` — `<label>` wrapping each checkbox filter value
- `.filter-option--disabled` — applied when `value.count == 0`
- `.filter-price` — price range input container

### Active Filter Chips
- `[data-active-filters]` — chips bar container (only rendered when filters are active)
- `.collection__chip` — individual chip `<a>` (links to `url_to_remove`)
- `.collection__clear-all` — "Clear All" link (links to `collection.url`)

### State Classes
- `.collection__sidebar--open` — added to sidebar when drawer is open (mobile)
- `.collection__drawer-backdrop--visible` — added to backdrop when drawer is open
- `.collection__grid--loading` — added to grid during AJAX fetch, removed after

## Responsive Behavior

- **Desktop (>767px):** Sidebar is a sticky column (260px) beside the grid. Toggle button hidden. Close button hidden. Backdrop hidden.
- **Mobile (≤767px):** Sidebar is a fixed drawer (slides in from right via `transform`). Toggle button visible in toolbar. Opened via JS adding `--open` class.

## `<collection-filters>` Web Component (AJAX behavior)

Defined in `sections/collection.liquid` inside `{% javascript %}` block. Key behaviors:

- **Checkbox change** → auto-submits form via `_submitForm()` → AJAX fetch with `section_id` param
- **Price input** → debounced (600ms) then auto-submits
- **Chip click / Clear All click** → intercepts `<a>` clicks, calls `navigateTo(href)` for AJAX
- **Form submit** → prevented, serialized to URL params, AJAX navigated
- **popstate** → listens for browser back/forward, re-fetches via AJAX
- **Escape key** → closes drawer

The `navigateTo(url)` method fetches `url + &section_id=...`, parses the HTML response, and swaps: grid content, product count, chips bar, sidebar body (filter counts), sentinel, pagination, category pills.

## E2E Test Patterns

Tests are in `e2e/collection.spec.ts`. Key patterns for filter tests:

1. **Skip when not deployed:** Check `if (await sidebar.count() === 0) test.skip(...)` since production may not have filters
2. **Wait for web component:** `await page.waitForFunction(() => !!customElements.get('collection-filters'), null, { timeout: 20000, polling: 300 })`
3. **Wait for AJAX:** `page.waitForResponse(r => r.url().includes('section_id') && r.status() === 200)`
4. **Wait for loading complete:** `await expect(grid).not.toHaveClass(/collection__grid--loading/, { timeout: 10000 })`
5. **Scope checkboxes to sidebar:** Use `[data-filter-sidebar] .filter-option:not(.filter-option--disabled) input[type="checkbox"]` to avoid disabled options
6. **Scroll before interact:** `await checkbox.scrollIntoViewIfNeeded()` since sidebar has `overflow-y: auto`

**Note:** The `{% javascript %}` block is subject to the compiled_assets truncation issue (see `shopify/javascript-blocks-vs-inline-scripts` doc). If all JS-dependent filter tests fail with `waitForFunction` timeout, check the compiled JS file.

## i18n Keys (in `locales/en.default.json`)

```
collections.filters.title                    → "Filters"
collections.filters.title_singular           → "Filter"
collections.filters.active_filters           → "Active filters" (aria-label)
collections.filters.clear_all                → "Clear all"
collections.filters.show_results             → "Show results"
collections.filters.from                     → "From"
collections.filters.to                       → "To"
collections.filters.min_price                → "Min"
collections.filters.max_price                → "Max"
collections.filters.remove_chip_aria_label   → "Remove {{ filter }} filter"
collections.filters.toggle_filters_aria_label → "Toggle filters"
collections.filters.close_drawer_aria_label  → "Close filters"
```

## Available Filters on This Store

The `best-sellers` collection currently has: Availability, Price, School (metaobject). The `alabama` collection has the same filters but with fewer School values. Filter availability depends on Shopify admin configuration.
