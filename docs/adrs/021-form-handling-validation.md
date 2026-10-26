# ADR 021: Form Handling + Validation — React Hook Form + Zod with Custom UI

## Status
Accepted

## Context
Frontend needs forms for: Login, TriggerModal, FeedbackModal, and future Manager/Company forms. Options:
- **A. React Hook Form + Zod** (with custom UI built from scratch)
- **B. TanStack Form + Zod**
- **C. Formik + Yup**
- **D. Manual controlled components** (no library)

## Decision
**Option A: React Hook Form + Zod with custom UI components** (built from scratch per ADR 020).

## Consequences

### Positive
- You build all UI primitives (learning-rich)
- RHF/Zod replace only form state boilerplate (battle-tested)
- Zod schema inference = perfect TypeScript types
- `setErrorsFromApiError` maps backend `details` to RHF fields
- Uncontrolled RHF = performant, fewer re-renders

### Negative
- Manual schema sync (Zod ↔ Pydantic) until ADR 015 triggers
- Two patterns: RHF for state, custom components for UI

### Neutral
- Migration path: manual → OpenAPI → Zod generation
- Form drafts stay in RHF (local)

## Options Considered

### Option A: React Hook Form + Zod (Chosen)
**Pros**: De facto standard, perfect TS inference, performant, server error mapping, accessible patterns
**Cons**: Learning curve, manual schema sync

### Option B: TanStack Form + Zod
**Pros**: TanStack ecosystem, type-safe
**Cons**: Newer, less community, migration from RHF non-trivial

### Option C: Formik + Yup
**Pros**: Mature, simple mental model
**Cons**: Controlled (re-renders), larger bundle, TS inference weaker

### Option D: Manual Controlled Components
**Pros**: Zero deps, full control
**Cons**: Boilerplate, bug-prone, no schema reuse, manual accessibility

## Compliance
- [ ] Zod schemas in `src/schemas/` (feedback, trigger, login)
- [ ] Custom form fields: `FormField`, `InputField`, `TextareaField`, `SelectField`
- [ ] `useForm` wrapper with defaults (onBlur, zodResolver)
- [ ] `setErrorsFromApiError` maps backend `details` to RHF
- [ ] Forms: LoginForm, TriggerModal, FeedbackModal
- [ ] Validation flow: onBlur → submit → 200/422/401/5xx handling

## Notes
- Schema sharing: manual sync now → OpenAPI generation later (ADR 015)
- Related: ADR 019 (ApiError, interceptor), ADR 020 (custom Select/Dialog), ADR 024 (Testing)
- Review date: 2026-09-20

## References
- ADR 019: Error Handling (ApiError, interceptor, useApiError)
- ADR 020: Component Library (custom Select, Dialog)
- React Hook Form: https://react-hook-form.com/
- Zod: https://zod.dev/
- @hookform/resolvers: https://react-hook-form.com/get-started#SchemaValidation