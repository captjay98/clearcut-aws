---
title: Screen Reader Only Text (sr-only)
impact: MEDIUM
tags: [accessibility, screen-reader, sr-only]
---

# Screen Reader Only Text (sr-only)

Use the `sr-only` class to provide text for screen readers that is visually hidden.

## Why

- Icon-only buttons need text labels for screen readers
- Visual context (like text glyphs, colors) needs text alternatives
- Some content is clear visually but needs explanation for screen readers

## The sr-only Class

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

## Common Use Cases

### Icon-Only Buttons

```tsx
// Bad - no accessible name
<button type="button" onClick={onClose}>
  <span aria-hidden="true">×</span>
</button>

// Good - visible glyph plus an accessible name
<button type="button" onClick={onClose} aria-label={t("Close")}>
  <span aria-hidden="true">×</span>
</button>

// Also good - visible text makes the name clear
<button type="button" onClick={onClose}>
  {t("Close")}
</button>
```

### Visual-Only Table Headers

```tsx
<table>
  <thead className="sr-only">
    <tr>
      <th>{t("Item name")}</th>
      <th>{t("Amount")}</th>
      <th>{t("Date")}</th>
    </tr>
  </thead>
  <tbody>{/* Visual rows with no visible headers */}</tbody>
</table>
```

### Section Headings for Screen Reader Navigation

```tsx
<section>
  <h2 className="sr-only">{t("Search results")}</h2>
  <SearchResultsList />
</section>;
```

### Currency/Unit Indicators

```tsx
<span className="sr-only" id="currency">{t("Currency USD")}</span>
<input type="number" aria-describedby="currency" />
```

### Contextual Information

```tsx
// Badge that's visually clear but needs context
<span className="badge is-success">
  <span aria-hidden="true">✓</span>
  <span className="sr-only">{t("Status:")}</span>
  {t("Approved")}
</span>
```

## When NOT to Use sr-only

### Don't Hide Important Content

```tsx
// Bad - hiding content that should be visible
<button type="button">
  <span className="sr-only">{t("Submit form")}</span>
</button>

// Good - visible text
<button type="button">{t("Submit")}</button>
```

### Don't Duplicate Visible Text

```tsx
// Bad - redundant
<button type="button">
  {t("Submit")}
  <span className="sr-only">{t("Submit")}</span>
</button>

// Good - just the visible text
<button type="button">{t("Submit")}</button>
```

## Rules

1. Use `sr-only` for text that provides context missing from visual presentation
2. Mark decorative glyphs with `aria-hidden="true"`
3. Every interactive element must have an accessible name (visible text, sr-only, or aria-label)
4. Don't use sr-only to hide content that should be visible to all users
5. Don't duplicate visible text with sr-only text
