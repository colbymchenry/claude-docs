---
updated: 2026-04-14
---

# Theme Settings & Locale Files

## Two separate locale files

Shopify themes use **two** locale JSON files with different purposes:

| File | Purpose | Used by |
|------|---------|---------|
| `locales/en.default.json` | Storefront-facing strings (cart, search, 404, etc.) | Liquid templates via `{{ 'key' \| t }}` |
| `locales/en.default.schema.json` | Theme editor labels for settings/sections | `settings_schema.json` and section `{% schema %}` via `t:namespace.key` |

## Storefront locale file (`en.default.json`)

### File format
The file has a **comment header block** (`/* ... */`) before the JSON body. This makes it technically JSONC, not pure JSON. To validate programmatically, strip the comment block first:
```bash
sed '/^\/\*/,/\*\//d' locales/en.default.json | node -e "let d=''; process.stdin.on('data',c=>d+=c); process.stdin.on('end',()=>JSON.parse(d))"
```

### Key conventions
- Keys use `snake_case` (e.g., `clear_all`, `no_products_found`)
- Nested namespaces group related strings (e.g., `collections.filters.title`)
- `_html` suffix for strings containing Liquid interpolation variables: `"products_count_html": "{{ count }} products"`
- `_aria_label` suffix for accessibility strings: `"toggle_filters_aria_label": "Toggle product filters"`
- Top-level namespaces match Shopify resource types: `cart`, `collections`, `search`, `customers`, `gift_card`, etc.

### Usage in Liquid
```liquid
{# Simple string #}
{{ 'collections.filters.title' | t }}

{# String with variable interpolation (must have _html suffix) #}
{{ 'collections.filters.products_count_html' | t: count: collection.products_count }}

{# Aria labels with variables #}
aria-label="{{ 'collections.filters.remove_chip_aria_label' | t: filter: filter_name }}"
```

### Current namespaces in `en.default.json`
- `404` — not-found page
- `blog` — article comments
- `cart` — cart page and drawer
- `customers` — login (nested: `customers.login`)
- `collections` — collection pages, filter UI (nested: `collections.filters`)
- `gift_card` — gift card template
- `password` — password-protected storefront
- `templates` — misc templates (nested: `templates.contact.form`)
- `search` — search results

## Schema locale file (`en.default.schema.json`)

### Adding a new theme setting

When adding a setting to `config/settings_schema.json`, the `"label": "t:labels.foo"` translation key must be added to **`locales/en.default.schema.json`** under the `"labels"` namespace — NOT to `locales/en.default.json`.

#### Example: adding a simple color setting

**`config/settings_schema.json`** (in the Colors section):
```json
{
  "type": "color",
  "id": "color_page_background",
  "default": "#F5F2EB",
  "label": "t:labels.page_background"
}
```

**`locales/en.default.schema.json`** (alphabetical in `labels`):
```json
"page_background": "Page background",
```

**`snippets/css-variables.liquid`** (wire it to a CSS variable):
```css
--color-page-background: {{ settings.color_page_background }};
```

### Key conventions
- Schema labels are alphabetically sorted within each namespace in `en.default.schema.json`
- Setting IDs use `snake_case` (e.g., `color_page_background`)
- CSS variables use `kebab-case` (e.g., `--color-page-background`)
- Color settings use `"type": "color"` and hex defaults

## Deriving responsive CSS variables from a single setting

A single theme setting can generate responsive `clamp()` values using Liquid math filters (`times`, `round`). This avoids exposing multiple settings to the merchant while still providing mobile-friendly scaling.

#### Example: `section_vertical_padding` → two responsive variables

**`config/settings_schema.json`** (one range input):
```json
{
  "type": "range",
  "id": "section_vertical_padding",
  "min": 32,
  "max": 96,
  "step": 8,
  "unit": "px",
  "label": "t:labels.section_vertical_padding",
  "default": 56
}
```

**`snippets/css-variables.liquid`** (derive two clamp-based variables):
```liquid
--section-padding-block: clamp({{ settings.section_vertical_padding | times: 0.7 | round }}px, 5vw, {{ settings.section_vertical_padding }}px);
--section-padding-block-sm: clamp({{ settings.section_vertical_padding | times: 0.4 | round }}px, 3vw, {{ settings.section_vertical_padding | times: 0.7 | round }}px);
```

With default 56px this renders as:
- `--section-padding-block: clamp(39px, 5vw, 56px)` — standard sections
- `--section-padding-block-sm: clamp(22px, 3vw, 39px)` — compact sections (marquee, conference-nav)

**Key Liquid math filters:** `times` (multiply), `divided_by` (divide), `round` (round to nearest integer), `floor`, `ceil`. These can be chained: `{{ value | times: 0.7 | round }}`.

### Consuming `--section-padding-block` in sections

Use `padding-block` (not `padding`) so horizontal padding is unaffected. The `clamp()` already handles responsive scaling, so **mobile media query overrides for vertical padding should be removed** — they're redundant and fight the variable.

#### Standard section (most pages):
```css
.my-section {
  padding-block: var(--section-padding-block);
}
```

#### Compact section (marquee, conference-nav):
```css
.my-compact-section {
  padding-block: var(--section-padding-block-sm);
}
```

#### Section with horizontal padding (e.g., contact form):
When a section also needs horizontal padding, use shorthand `padding` with the variable for block and `var(--page-margin)` for inline:
```css
.contact-page {
  padding: var(--section-padding-block) var(--page-margin);
}
```

#### Migration checklist
1. Replace hardcoded `padding: Xpx 0 Ypx` with `padding-block: var(--section-padding-block)`
2. Remove mobile `@media` overrides that only changed vertical padding — `clamp()` handles it
3. Leave internal spacing (line-item gaps, grid gaps) unchanged — only the outer section padding uses the variable
4. If the section has an alternate state (e.g., `.cart--empty`), apply the variable there too

#### Sections already migrated (as of 2026-04-14)
Homepage, product, collection, about, careers (all sub-sections), cart, search, FAQs, contact.