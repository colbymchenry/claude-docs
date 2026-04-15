---
updated: 2026-04-13
---

# Shopify Section JavaScript: `{% javascript %}` vs Inline `<script>`

## The Problem

Shopify's `{% javascript %}` tag compiles all section JS into a single `compiled_assets/scripts.js` bundle. The dev server's compilation pipeline can produce **truncated output**, causing a `SyntaxError: Unexpected end of input` that breaks ALL sections using `{% javascript %}` blocks.

## Which Sections Are Affected

Only sections using `{% javascript %}` go through the compiled_assets pipeline. Sections using inline `<script>` tags are immune — their JS is embedded directly in the HTML.

**Current pattern in this theme:**
- `sections/recently-viewed.liquid` — uses inline `<script>` (works reliably)
- `sections/featured-collection.liquid` — converted from `{% javascript %}` to inline `<script>` (April 2026) to fix truncation
- `sections/announcement-bar.liquid` — still uses `{% javascript %}` (potentially affected)
- `sections/collection.liquid` — still uses `{% javascript %}` (potentially affected)

## Recommendation

**Prefer inline `<script>` tags** for section JavaScript in this theme. Wrap in an IIFE to avoid polluting global scope. Use the `customElements.get()` guard for custom element definitions:

```liquid
<script>
  (function() {
    class MyElement extends HTMLElement {
      connectedCallback() { /* ... */ }
    }
    if (!customElements.get('my-element')) {
      customElements.define('my-element', MyElement);
    }
  })();
</script>
```

## Diagnosis

If `product-carousel` or other custom elements stop working:
1. Check browser console for `SyntaxError: Unexpected end of input`
2. Verify with `customElements.get('product-carousel')` — returns `undefined` if broken
3. Inspect the served `compiled_assets/scripts.js` — look for truncation at the end of the file
4. Dev server restart may or may not fix it; converting to inline `<script>` is the reliable fix

## Playwright Testing Note

The `{% javascript %}` vs inline `<script>` distinction matters for e2e tests. If tests fail because a custom element never registers (e.g., IntersectionObserver never fires, `.carousel--visible` never added), the compiled_assets truncation is the likely cause.