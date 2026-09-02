# 03 API Standard

> Rules: R3.1-R3.2 (EN mirror of `docs/规范/03_API规范.md`; the Chinese file is authoritative)
> Purpose: organization and error-handling boundaries for the frontend API layer (`web/src/api/`).

---

## R3.1 Split APIs by Domain

Boundary:
- The `api/` directory is split by business domain: base / auth / assets / ai / system / tags / logs.
- `client.ts` is a barrel export only, contains no business code, and stays <= 50 lines.
- New APIs must be added in their own file, never as methods in `client.ts`.

```
api/
├── base.ts      # request() + token management
├── auth.ts      # login/register
├── assets.ts    # assets
├── ai.ts        # AI engine
├── system.ts    # system settings
├── tags.ts      # tags
├── logs.ts      # logs
└── client.ts    # barrel export (<= 50 lines)
```

Check:
```bash
wc -l web/src/api/client.ts   # <= 50 lines (enforced by scripts/check.sh R3.1)
```

## R3.2 Unified Error Display

Boundary:
- Errors caught in API calls are written into a store (`setError`).
- The page-level `GlobalError` component renders the global error at the top of the page.
- Components additionally show local loading/error states per R2.3.

```tsx
// page layout
<GlobalError />     <- page top
<ErrorBoundary>     <- fallback
  <PageContent />
</ErrorBoundary>
```

Principle: errors are never swallowed. They must be shown either globally or inside the component so the user always knows what happened.
