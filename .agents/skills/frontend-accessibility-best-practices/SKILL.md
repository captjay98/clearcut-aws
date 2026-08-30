---
name: frontend-accessibility-best-practices
description: Accessibility (a11y) best practices for React components. Use when creating UI components, forms, interactive elements, or reviewing code for accessibility compliance.
---

# Accessibility Best Practices

Accessibility patterns for building inclusive React applications following WCAG standards.

**ClearCut override:** Follow `misc/clearcut-flow/` for visual and interaction patterns. Use native HTML and ClearCut custom primitives; do not add external component or icon libraries. Icons are text glyphs or CSS shapes, and both Script and Night shoot themes must remain accessible. Contains 7 rules across 4 categories focused on semantic HTML, screen reader support, keyboard navigation, and user preferences.

## When to Apply

Reference these guidelines when:

- Creating new UI components
- Building forms and interactive elements
- Adding dynamic content or notifications
- Implementing navigation patterns
- Reviewing code for accessibility

## Rules Summary

### Semantic HTML & Structure (HIGH)

#### semantic-html-landmarks - @rules/semantic-html-landmarks.md

Use semantic HTML elements for page structure.

```tsx
// Bad: divs with class names
<div className="header">...</div>
<div className="nav">...</div>
<div className="content">...</div>

// Good: semantic elements
<header>...</header>
<nav aria-label={t("Primary")}>...</nav>
<main>...</main>
<footer>...</footer>
```

### Screen Readers (MEDIUM)

#### screen-reader-sr-only - @rules/screen-reader-sr-only.md

Use sr-only class for visually hidden text.

```tsx
// Icon-only buttons need accessible labels without an icon dependency
<button type="button" onClick={onClose} aria-label={t("Close")}>
  <span aria-hidden="true">×</span>
</button>

// Visually hidden section headings
<section>
  <h2 className="sr-only">{t("Search results")}</h2>
  <SearchResultsList />
</section>
```

#### aria-live-regions - @rules/aria-live-regions.md

Announce dynamic content changes to screen readers.

```tsx
// Error messages - announced immediately
{
  error && (
    <p role="alert" className="banner is-danger">
      {error}
    </p>
  );
}

// Status updates - announced politely
<div role="status" aria-live="polite">
  {t("{{count}} results found", { count })}
</div>;
```

### Keyboard & Focus (HIGH)

#### keyboard-navigation - @rules/keyboard-navigation.md

Use semantic elements for built-in keyboard support.

```tsx
// Bad: div with onClick not keyboard accessible
<div onClick={handleClick}>Click me</div>

// Good: button has Enter/Space support
<button type="button" onClick={handleClick}>Click me</button>
```

#### focus-management - @rules/focus-management.md

Show visible focus indicators and manage modal focus explicitly.

```tsx
// Always use focus-visible for focus styles
<button className="focus-ring">
  Click me
</button>;

// Native dialog provides the modal focus boundary; restore focus to its trigger.
<dialog ref={dialogRef} aria-modal="true" onCancel={onClose}>
  <h2 id="dialog-title">{t("Evidence details")}</h2>
  <button type="button" onClick={onClose}>{t("Close")}</button>
</dialog>;
```

### User Preferences (MEDIUM)

#### reduced-motion - @rules/reduced-motion.md

Respect prefers-reduced-motion setting.

```tsx
import { usePrefersReducedMotion } from "~/hooks/use-prefers-reduced-motion";

// CSS handles reduced motion through the shared token layer.
<div className="animated-counter">
  Bouncing content
</div>;

// JS approach
function AnimatedCounter({ value }) {
  const prefersReducedMotion = usePrefersReducedMotion();
  if (prefersReducedMotion) return <span>{value}</span>;
  return <CountUp target={value} />;
}
```

#### touch-targets - @rules/touch-targets.md

Ensure 44x44px minimum touch targets.

```tsx
// Text glyphs keep the control dependency-free and accessible
<button type="button" className="icon-button" aria-label={t("Close")}>
  <span aria-hidden="true">×</span>
</button>

// Links need padding for tappable area
<a href={href} className="action-link">
  {label}
</a>
```

## Key Files

- No current production component paths exist. When Plan 01 creates `packages/design-system/` and `apps/web/`, follow their real co-located primitives and hooks rather than inventing generic `app/` paths.
