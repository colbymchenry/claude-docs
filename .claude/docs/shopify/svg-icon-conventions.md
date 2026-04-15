---
updated: 2026-04-14
---

# SVG Icon Conventions

All icon SVGs in `assets/` follow a consistent pattern. When creating new icons, match these exact attributes.

## Standard Attributes

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
  fill="none" stroke="currentColor" stroke-width="1.5"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <!-- paths here -->
</svg>
```

Key properties:
- **ViewBox:** `0 0 24 24` (square aspect ratio)
- **Style:** Stroke-based line icons, not filled
- **Color:** `stroke="currentColor"` with `fill="none"` — inherits text color via CSS
- **Stroke width:** `1.5` (consistent across all icons)
- **Line caps/joins:** Both `round`
- **Accessibility:** `aria-hidden="true"` (icons are decorative)

## Referencing Icons in Section Schemas

Icons stored in `assets/` are referenced via a **text field** containing the filename, rendered with `asset_url` — NOT via `image_picker`. This is the established convention for SVG icons in this theme.

**Schema pattern:**
```json
{
  "type": "text",
  "id": "icon",
  "label": "Icon filename",
  "default": "icon-licensed.svg",
  "info": "SVG filename from assets/ (e.g., icon-licensed.svg)"
}
```

**Liquid rendering pattern:**
```liquid
<img src="{{ block.settings.icon | asset_url }}" alt="" width="24" height="24" loading="lazy">
```

Why text field instead of `image_picker`: SVG icons are theme assets (checked into `assets/`), not merchant-uploaded media. `image_picker` uploads to Shopify's CDN and returns a different object type — it doesn't work with `asset_url`. The text field + `asset_url` approach keeps icons version-controlled in the theme.

## Existing Icons

| File | Description |
|------|-------------|
| `icon-search.svg` | Magnifying glass |
| `icon-account.svg` | Person silhouette |
| `icon-cart.svg` | Shopping bag |
| `icon-menu.svg` | Hamburger menu |
| `icon-close.svg` | X close button |
| `icon-licensed.svg` | Shield with checkmark (trust badge) |
| `icon-shipping.svg` | Delivery truck (trust badge) |
| `icon-returns.svg` | Refresh/return arrow (trust badge) |
| `icon-guarantee.svg` | Thumbs-up (trust badge) |

## Naming Convention

Files are named `icon-{purpose}.svg` in lowercase with hyphens.