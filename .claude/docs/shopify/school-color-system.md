---
updated: 2026-04-14
---

# School Color System

How school-specific colors are resolved and applied across the Shopify theme.

## School Metaobject Fields (type: `school`)

Key color-related fields:
- `primary_color` — Main school color (e.g., Auburn's navy `#0C2340`)
- `secondary_color` — Secondary school color (e.g., Auburn's orange `#DD550C`)
- `use_secondary_for_accent` — **Boolean** (true_false). When `true`, interactive elements (buttons, accents) use `secondary_color` instead of `primary_color`. Added because some schools' primary colors are too dark for button backgrounds.
- `slug` — URL-friendly handle, used to match against collection handles
- `logo` — School logo image
- `slogan` — School slogan text

## School Resolution Pattern

Every section that needs school data uses the same pattern — matching product collections to school slugs:

```liquid
{%- assign school = nil -%}
{%- paginate shop.metaobjects.school.values by 250 -%}
  {%- for col in product.collections -%}
    {%- assign found_school = shop.metaobjects.school.values | where: 'slug', col.handle | first -%}
    {%- if found_school -%}
      {%- assign school = found_school -%}
      {%- break -%}
    {%- endif -%}
  {%- endfor -%}
{%- endpaginate -%}
```

Collection pages use a simpler version (direct slug match):
```liquid
{%- assign school = shop.metaobjects.school.values | where: 'slug', collection.handle | first -%}
```

## CSS Variable: `--school-primary`

The main CSS variable that drives school-colored UI. Set via inline `style` attributes.

### Sections that set `--school-primary`:

| Section | Lines | Context |
|---------|-------|---------|
| `sections/product.liquid` | line 22 | `<product-page>` element |
| `sections/product-features.liquid` | line 17 | `.product-features` wrapper |
| `sections/collection.liquid` | lines 14, 46, 145 | Coming-soon, school-header, product grid |
| `sections/404.liquid` | line 58 (JS), line 69 (JS) | JS-built schools map, applied via `setProperty` |

### Other school color usage (NOT `--school-primary`):

| File | Line | Variable | Notes |
|------|------|----------|-------|
| `sections/cart.liquid` | 29 | `--line-accent` | Cart line item accent |
| `sections/marquee.liquid` | 12–14 | Inline `background-color` | Conditional via `use_school_color` checkbox; sets bg to accent color, text to `#FFFFFF` |
| `snippets/slidecart-school-badges.liquid` | 14 | `color` in JSON via snippet | Badge text color, uses `school-accent-color` snippet |
| `sections/collection.liquid` | 46 | `--school-secondary` | Also sets secondary alongside primary |
| `sections/schools.liquid` | 136 | Inline `background-color` | School dot indicator |

### CSS consumers of `--school-primary`:

Used for button backgrounds, text accents, border colors, and decorative stripes. Fallback is typically `var(--color-foreground)`:
- `product.liquid` — Add-to-cart button background (line ~363), price color (line ~273)
- `product-features.liquid` — Accent heading color (line ~86)
- `collection.liquid` — Border stripes, logo ring, filter pills, product card buttons
- `404.liquid` — Coming-soon stripes and decorative elements

## Accent Color Snippet: `school-accent-color.liquid`

The reusable snippet at `snippets/school-accent-color.liquid` resolves the correct accent color for a school. It checks `use_secondary_for_accent` and `secondary_color != blank`, falling back to `primary_color`.

Since `{% render %}` creates an isolated scope (variables assigned inside aren't available to the parent), the snippet **outputs the color value directly** as text. Callers use `{% capture %}` to grab it:

```liquid
{% capture accent_color %}{% render 'school-accent-color', school: school %}{% endcapture %}
<div style="--school-primary: {{ accent_color | strip }};">
```

The snippet uses whitespace-trimming tags (`{%-`, `{{-`) to ensure the captured value is a clean color string with no surrounding whitespace. The `| strip` filter on output is a safety net.

### Migration pattern for existing sections

Replace hardcoded `school.primary_color` references:

```liquid
{%- comment -%} Before -%}
{% if school %}style="--school-primary: {{ school.primary_color }};"{% endif %}

{%- comment -%} After -%}
{% capture accent_color %}{% render 'school-accent-color', school: school %}{% endcapture %}
{% if school %}style="--school-primary: {{ accent_color | strip }};"{% endif %}
```

For JS/JSON contexts, use `{% capture %}` inside the loop before building the JSON value. Example from `slidecart-school-badges.liquid`:

```liquid
{%- for school in shop.metaobjects.school.values -%}
  {%- capture accent_color -%}{%- render 'school-accent-color', school: school -%}{%- endcapture -%}
  {{ school.slug | json }}: {
    "name": {{ school.name | json }},
    "color": "{{ accent_color | strip }}"
  }
{%- endfor -%}
```

### Migration status

| File | Status |
|------|--------|
| `snippets/slidecart-school-badges.liquid` | Migrated |
| `sections/marquee.liquid` | Migrated (uses accent snippet with `use_school_color` toggle) |
| `sections/cart.liquid` | Pending |
| `sections/product.liquid` | Pending |
| `sections/product-features.liquid` | Pending |
| `sections/collection.liquid` | Pending |
| `sections/404.liquid` | Pending |
| `sections/schools.liquid` | Pending |
