---
title: Touch Target Sizes
impact: MEDIUM
tags: [accessibility, touch, mobile]
---

# Touch Target Sizes

Ensure interactive elements have sufficient target size and spacing across input types.

## Why

- Users with motor impairments need larger tap targets
- Fat finger problem on mobile devices
- WCAG 2.5.5 recommends 44x44px for AAA; WCAG 2.5.8 allows 24x24px minimum if spaced
- Touch targets need spacing to avoid accidental taps

## Minimum Sizes

| Level    | Minimum Size | Use Case                          |
| -------- | ------------ | --------------------------------- |
| WCAG AA  | 24x24px      | Minimum if targets don't overlap  |
| WCAG AAA | 44x44px      | Recommended for all touch targets |
| iOS HIG  | 44x44pt      | Apple's recommendation            |
| General mobile guidance | 44x44px | Comfortable target size |

## Implementation

### Buttons

```tsx
// Good - explicit minimum size
<button type="button" className="touch-target button-primary">
  {t("Submit")}
</button>

// Glyph controls remain native and dependency-free
<button type="button" className="touch-target icon-button" aria-label={t("Close")}>
  <span aria-hidden="true">×</span>
</button>
```

### Links in Lists

```tsx
// Good - padding on the link (target) itself
<nav>
  {links.map((link) => (
    <a key={link.href} href={link.href} className="touch-target action-link">
      {link.label}
    </a>
  ))}
</nav>
```

### Checkboxes and Radios

```tsx
// Good - label wraps input for larger tap area
<label className="touch-target checkbox-label">
  <input type="checkbox" />
  <span>{t("Accept terms")}</span>
</label>
```

## Common Issues

### Too Small or Too Close

```tsx
// Bad - glyph button too small
<button className="h-6 w-6">
  <span aria-hidden="true">×</span>
</button>

// Bad - links too close together
<div className="flex gap-1">
  <a href="/a">A</a>
  <a href="/b">B</a>
  <a href="/c">C</a>
</div>
```

### Adequate Spacing

```tsx
// Good - adequate spacing between targets
<div className="flex gap-4">
  <button type="button">Option A</button>
  <button type="button">Option B</button>
  <button type="button">Option C</button>
</div>
```

## Expanding Target Area

Make the clickable area larger than the visible element:

```tsx
// Technique 1: Padding on the target
<button type="button" className="p-3">
  <span aria-hidden="true">×</span>
</button>

// Technique 2: Pseudo-element (in CSS)
.small-button {
  position: relative;
}
.small-button::before {
  content: "";
  position: absolute;
  inset: -8px; /* Expands clickable area */
}
```

## Spacing and Context

- Small targets need more spacing between them
- Large targets can sit closer without overlap
- Inline links rely on line height; increase `leading` for readability

## Rules

1. Aim for 44x44px targets; allow 24x24px only with sufficient spacing
2. Increase spacing when targets are small or dense
3. Apply padding to the clickable element itself
4. Glyph-only buttons need explicit size (min 44x44)
5. Avoid dead zones between related targets
6. Test on real touch devices, not just DevTools
