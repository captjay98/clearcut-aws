---
title: Focus Management
impact: HIGH
tags: [accessibility, focus, keyboard]
---

# Focus Management

Manage focus visibility, modal boundaries, and restoration for keyboard users.

## Focus Visibility

Always show a visible focus indicator for keyboard users.

### Use focus-visible

The `focus-visible` pseudo-class shows focus only for keyboard navigation, not mouse clicks:

```tsx
// Good - focus ring only shows for keyboard users
<button className="focus-ring">
  Click me
</button>
```

### Bad - Removing Focus Outlines

```tsx
// Bad - removes focus indicator entirely
<button className="focus:outline-none">Click me</button>

// Bad - outline:none without replacement
button:focus {
  outline: none;
}
```

### Good - Custom Focus Styles

```tsx
// Good - custom focus style that's still visible
<button className="focus-ring">
  Click me
</button>
```

## Focus Trapping and Restoration

Use the native `<dialog>` element or the repository's ClearCut dialog primitive. Opening a modal must move focus into it, keep Tab navigation inside it, and return focus to the trigger when it closes. Native `showModal()` supplies the modal focus boundary; custom dialog primitives must implement the equivalent behavior explicitly.

```tsx
function EvidenceDialog({ isOpen, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen && !dialog.open) {
      dialog.showModal();
      dialog.querySelector<HTMLElement>("[data-initial-focus]")?.focus();
    } else if (!isOpen && dialog.open) {
      dialog.close();
      triggerRef.current?.focus();
    }
  }, [isOpen]);

  return (
    <>
      <button ref={triggerRef} type="button" onClick={() => onClose(false)}>
        Open evidence
      </button>
      <dialog ref={dialogRef} aria-labelledby="evidence-title" onCancel={() => onClose(false)}>
        <h2 id="evidence-title">Evidence details</h2>
        <button data-initial-focus type="button" onClick={() => onClose(false)}>
          Close
        </button>
      </dialog>
    </>
  );
}
```

## Programmatic Focus

Move focus to important content after navigation or an async result:

```tsx
function SearchResults({ results, error }) {
  const errorRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) {
      errorRef.current?.focus();
    } else if (results.length > 0) {
      resultsRef.current?.focus();
    }
  }, [error, results]);

  return (
    <>
      {error && (
        <div ref={errorRef} tabIndex={-1} role="alert">
          {error}
        </div>
      )}
      <div ref={resultsRef} tabIndex={-1}>
        {/* Results */}
      </div>
    </>
  );
}
```

## Skip Links

Add skip links for keyboard users to bypass navigation:

```tsx
function Layout({ children }) {
  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-white focus:p-4"
      >
        {t("Skip to main content")}
      </a>
      <Header />
      <Main id="main-content">{children}</Main>
    </>
  );
}
```

## Rules

1. Never remove focus outlines without providing an alternative
2. Define visible focus styles with the native `:focus-visible` selector in the shared stylesheet
3. Use native `<dialog>` or a ClearCut dialog primitive with explicit focus trapping
4. Return focus to the trigger element when closing modals
5. Use `tabIndex={-1}` for elements that receive programmatic focus
6. Consider adding skip links for pages with significant navigation
7. Test focus management by navigating with Tab and Shift+Tab
