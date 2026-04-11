---
updated: 2026-04-09
---

# Event Content Section

**File:** `sections/event-content.liquid`

## Purpose
Renders content blocks for event pages (e.g., charity-water-event). Each block displays a title, optional image, and rich text body within a centered layout.

## Block Schema
Single block type: `content_block` with these settings:

| Setting | Type | ID | Default | Notes |
|---------|------|----|---------|-------|
| Background Color | `color` | `background_color` | `#ffffff` | Applied via inline `style` attribute |
| Text Color | `select` | `text_color` | `dark` | Options: `dark`, `light`. Light adds `event-content__block--light-text` class to flip text to `#ffffff` |
| Title | `text` | `title` | — | Rendered as `<h2>` |
| Image | `image_picker` | `image` | — | Rendered at 1200px width with lazy loading |
| Body | `richtext` | `body` | — | Rich text content |

## Styling Details
- Background color is set via inline `style="background: ..."` on each block (not CSS classes)
- Text defaults to dark (`#1f1f1f`). When `text_color` is `light`, the `--light-text` modifier class overrides title and body text to `#ffffff`
- Max content width: 780px, centered
- Desktop padding: 80px vertical; mobile (≤749px): 48px
- Uses `--font-shoulders` for titles, `--font-poppins` for body text

## History
- Originally used alternating odd/even logic to auto-assign light/blue backgrounds. Replaced with per-block color picker settings for manual control.
