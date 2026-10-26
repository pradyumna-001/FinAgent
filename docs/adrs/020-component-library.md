# ADR 020: Component Library — Build From Scratch (Learning-Focused)

## Status
Accepted

## Context
Frontend needs ~15 UI primitives for Phase 2. Options considered:
- shadcn/ui (copy-paste Radix + Tailwind)
- Radix UI / Headless UI (headless primitives)
- MUI / Chakra (full component libraries)
- **Build from scratch** (custom components with Tailwind v4)

## Decision
**Build all components from scratch** using Tailwind v4.

**Rationale**: Primary objective is learning. Building primitives teaches React component patterns, Tailwind mastery, accessibility, TypeScript, and design system thinking.

## Consequences

### Positive
- Deep learning: polymorphic `as` prop, compound components, forwardRef, portals, focus management
- Full control over design tokens, variants, accessibility
- No vendor lock-in, easy to migrate to shadcn/ui later
- Portfolio-worthy component library

### Negative
- ~6 days implementation vs 30 min for shadcn/ui
- Accessibility burden on you (ARIA, keyboard, focus)
- No pre-built components, all bugs are yours

### Neutral
- Migration path to shadcn/ui documented for Phase 3+

## Options Considered

### Option A: shadcn/ui (Copy-Paste)
**Pros**: 30 min setup, Radix accessibility, Tailwind-native, owned code
**Cons**: Less learning, copy-paste patterns without understanding

### Option B: Radix / Headless UI
**Pros**: Accessible primitives, build your own styling
**Cons**: Still need to build 15 components, no design system

### Option C: MUI / Chakra
**Pros**: Pre-built, theming, enterprise support
**Cons**: Not Tailwind-native, large bundle, CSS-in-JS, two design systems

### Option D: Build From Scratch (Chosen)
**Pros**: Maximum learning, full control, portfolio project, no lock-in
**Cons**: 6 days, accessibility burden, all bugs yours

## Compliance
- [ ] 15 components: Button, Input, Textarea, Select, Modal, Table, Badge, Toast, Card, Avatar, Dropdown, Tooltip, Skeleton, Spinner, Tabs, Progress
- [ ] Patterns: polymorphic `as`, compound components, CVA variants, CSS variables, portals, focus management
- [ ] Accessibility: ARIA roles, keyboard nav, focus trap, focus restoration per component
- [ ] File structure: `src/components/ui/<component>/` with test, story, index
- [ ] Testing: Vitest + RTL per component (polymorphic, variants, accessibility)
- [ ] Migration path: compare with shadcn/ui in Phase 3, extract to `@finagent/ui` in Phase 4

## Notes
- Implementation order: Day 1 Button/Input/Textarea, Day 2 Badge/Card/Avatar, Day 3 Table/Skeleton, Day 4 Dialog/Toast, Day 5 Select/Dropdown/Tooltip, Day 6 Tabs/Progress/Spinner
- Learning goals per component documented
- Related: ADR 023 (Design System), ADR 021 (Forms), ADR 024 (Testing)
- Review date: 2026-09-20

## References
- shadcn/ui source: https://github.com/shadcn/ui
- Radix UI primitives: https://www.radix-ui.com/
- WAI-ARIA: https://www.w3.org/WAI/ARIA/apg/
- Tailwind v4: https://tailwindcss.com/docs
- CVA: https://cva.style/docs