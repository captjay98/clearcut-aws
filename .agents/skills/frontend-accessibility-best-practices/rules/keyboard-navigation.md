---
title: Keyboard Navigation
impact: HIGH
tags: [accessibility, keyboard, focus]
---

# Keyboard Navigation

All interactive elements must be accessible via keyboard.

## Why

- Users with motor disabilities may use keyboard only
- Screen reader users navigate with keyboard
- Power users prefer keyboard shortcuts

## Native Keyboard Support

Use semantic HTML elements that have built-in keyboard support:

| Element    | Keyboard Behavior              |
| ---------- | ------------------------------ |
| `<button>` | Enter/Space to activate        |
| `<a href>` | Enter to follow link           |
| `<input>`  | Tab to focus, type to input    |
| `<select>` | Arrow keys to navigate options |

## Bad - Non-interactive Elements as Buttons

```tsx
// Bad - div is not keyboard accessible
<div onClick={handleClick} className="cursor-pointer">
  Click me
</div>

// Bad - span with click handler
<span onClick={handleClick}>Action</span>
```

## Good - Semantic Elements

```tsx
// Good - button is keyboard accessible
<button type="button" onClick={handleClick}>Click me</button>;
```

## When You Must Use Non-Semantic Elements

If you absolutely must use a non-semantic element, add keyboard support:

```tsx
// Only when semantic elements aren't possible
<div
  role="button"
  tabIndex={0}
  onClick={handleClick}
  onKeyDown={(event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleClick();
    }
  }}
>
  Click me
</div>
```

Prefer native controls for complex widgets too. When custom behavior is required, add the keyboard behavior explicitly:

```tsx
function SearchInput({ clearSearch }: { clearSearch: () => void }) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") clearSearch();
  };

  return <input onKeyDown={handleKeyDown} aria-label="Search" />;
}
```

## Tab Order

### Natural Tab Order

Elements are focused in DOM order. Structure your HTML logically:

```tsx
// Good - logical order matches visual order
<form>
  <input name="firstName" />
  <input name="lastName" />
  <input name="email" />
  <button type="submit">Submit</button>
</form>
```

### Avoid Positive tabIndex

```tsx
// Bad - arbitrary tab order is confusing
<input tabIndex={2} />
<input tabIndex={1} />
<input tabIndex={3} />

// Good - let DOM order determine tab order
<input />
<input />
<input />
```

### Remove from Tab Order

Use `tabIndex={-1}` for elements that should be focusable programmatically but not via Tab:

```tsx
// Programmatically focusable, not in tab order
<div tabIndex={-1} ref={errorRef}>
  {error}
</div>

// Later: errorRef.current?.focus()
```

## Keyboard Shortcuts

Use native `onKeyDown` handlers for custom shortcuts and keep the shortcut discoverable in visible help text:

```tsx
function SearchInput() {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      clearSearch();
    }
  };

  return <input onKeyDown={handleKeyDown} aria-label="Search" />;
}
```

## Rules

1. Use `<button>` for actions and `<a>` for navigation
2. Never use `div` or `span` with `onClick` without keyboard support
3. Prefer native HTML and ClearCut primitives for complex interactive widgets
4. Don't use positive `tabIndex` values
5. Use `tabIndex={-1}` for programmatic focus targets
6. Ensure all interactive elements are reachable via Tab key
7. Test keyboard navigation by unplugging your mouse
