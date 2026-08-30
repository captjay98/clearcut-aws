---
title: Respect Reduced Motion Preference
impact: MEDIUM
tags: [accessibility, animation, reduced-motion]
---

# Respect Reduced Motion Preference

Honor `prefers-reduced-motion` so animation never becomes a barrier or vestibular trigger. ClearCut's shared stylesheet owns motion behavior; do not introduce a utility framework for this.

## CSS First

Keep the default transition subtle, then disable nonessential motion in the media query:

```css
.attention-row {
  transition: background-color 160ms ease, transform 160ms ease;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto;
  }

  .attention-row {
    transition-duration: 0.01ms;
    transform: none;
  }

  .decorative-motion {
    animation: none;
  }
}
```

Do not hide content in reduced-motion mode. Replace decorative motion with a static state and keep loading/progress meaning perceivable.

## JavaScript-Controlled Motion

Only read the preference in JavaScript when behavior—not merely styling—depends on it:

```tsx
function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia("(prefers-reduced-motion: reduce)");
      query.addEventListener("change", notify);
      return () => query.removeEventListener("change", notify);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
}

function MonitoringTicker({ entries }: Props) {
  const prefersReducedMotion = usePrefersReducedMotion();
  return <Ticker entries={entries} autoAdvance={!prefersReducedMotion} />;
}
```

## Reduce or Remove

- Decorative parallax, floating particles, count-up animations, and animated backgrounds.
- Auto-advancing carousels/tickers and nonessential page transitions.
- Long transforms or motion used as the only state cue.

Simple progress indicators and focus feedback may remain, but must not flash, strobe, or loop aggressively.

## Rules

1. Implement the CSS media query in the shared token/style layer.
2. Use JavaScript preference detection only for behavior that CSS cannot control.
3. Disable autoplay and provide static alternatives.
4. Preserve content, status, and progress meaning without motion.
5. Verify with the operating system reduced-motion setting and automated media emulation.
