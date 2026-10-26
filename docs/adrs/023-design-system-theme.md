# ADR 023: Design System / Theme — Tailwind v4 @theme + CSS Variables

## Status
Accepted

## Context
Frontend needs a consistent visual language across 15+ custom components and 6 pages. Using Tailwind v4. Need colors, spacing, typography, shadows, transitions, border radius, breakpoints, z-index, and dark mode.

## Decision
**Option A: Tailwind v4 `@theme` directive with CSS custom properties.**

## Consequences

### Positive
- Native to Tailwind v4, single source of truth, zero JS bundle
- CSS variables accessible at runtime for charts/dynamic styles
- Dark mode: media query (system) + class-based (manual toggle)
- Semantic tokens: `color-primary` not `color-blue-800`
- Financial trust palette (Navy primary, Green success, Red danger, Amber warning, Blue info)

### Negative
- Tailwind v4 only (not v3 compatible)
- Learning curve for new `@theme` syntax

### Neutral
- No JS bundle impact
- WCAG AA contrast verified

## Options Considered

### Option A: Tailwind v4 `@theme` + CSS Variables (Chosen)
**Pros**: Native, single source, zero JS, dark mode both ways, semantic tokens
**Cons**: v4 only, new syntax

### Option B: Tailwind v3 Config + CSS Variables
**Pros**: Familiar
**Cons**: Two sources, legacy pattern

### Option C: Design Tokens JSON + Style Dictionary
**Pros**: Multi-platform
**Cons**: Overkill for web-only, build step

### Option D: CSS-in-JS (Emotion/Styled-Components)
**Pros**: Dynamic theming
**Cons**: Defeats Tailwind, runtime cost, two systems

## Compliance
- [ ] `src/styles/globals.css` with `@theme` (colors, spacing, radius, shadows, transitions, typography, breakpoints, z-index)
- [ ] Dark mode: media query (system) + class-based (manual toggle)
- [ ] Semantic color palette: Primary (Navy), Success (Green), Danger (Red), Warning (Amber), Info (Blue)
- [ ] WCAG AA contrast verified
- [ ] `src/utils/designTokens.ts` for chart/runtime access
- [ ] `ThemeProvider` with light/dark/system toggle
- [ ] Components use semantic tokens: `bg-primary`, `text-success-foreground`, etc.

## Notes
- Financial trust palette: Navy=stability, Green=gains, Red=losses, Amber=attention, Blue=info
- Warning text uses `--color-warning-foreground` on `--color-warning-light` for AA
- Related: ADR 020 (Component Library), ADR 021 (Forms), ADR 024 (Testing)
- Review date: 2026-09-20

## References
- Tailwind v4 @theme: https://tailwindcss.com/docs/theme
- CSS Custom Properties: https://developer.mozilla.org/en-US/docs/Web/CSS/--*
- WCAG Contrast: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html