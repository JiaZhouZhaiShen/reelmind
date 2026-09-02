# 02 Frontend Standard

> Rules: R2.1-R2.10 (EN mirror of `docs/规范/02_前端规范.md`; the Chinese file is authoritative)
> Purpose: state management, component structure, and code quality boundaries for the React SPA (`web/src/`).

---

## R2.1 Business State Belongs in Stores

Boundary:
- API data must go into Zustand stores.
- Component `useState` is only for UI state (input values, dropdown open state, selected items).

```tsx
// OK
const pendingCounts = useAIStore(s => s.pendingCounts)
// NOT OK
const [pendingCounts, setPendingCounts] = useState(null)
useEffect(() => { api.xxx().then(setPendingCounts) }, [])
```

Exception: purely local UI state (modal toggles, tab selection) may stay in the component.

## R2.2 Children Read from Stores

Boundary: children prefer reading from stores; parents do not drill business props down. More than 5 business props is a warning.

```
Priority: read from store by default -> props override only for tests/reuse
```

## R2.3 Components Self-Handle Three States

Boundary: every component handles loading / error / empty internally instead of relying on its parent. This is what prevents empty catches from blanking the page.

```tsx
if (loading) return <SkeletonCard />
if (!data) return <div className="text-gray-500">No data</div>
return <div>...</div>
```

## R2.4 Page-Level ErrorBoundary

Boundary: every routed page is wrapped in an ErrorBoundary.

```tsx
<Route path="/ai" element={
  <ErrorBoundary fallback={<AIPageError />}>
    <AIEnginePage />
  </ErrorBoundary>
} />
```

## R2.5 Memoize Hot Components

Boundary: hot re-rendering components (list items, cards, sidebar) are wrapped in `React.memo`. A project with zero `React.memo` is a performance bug.

Priority: VideoCard -> SearchVideoCard -> Sidebar -> AIPendingOverview -> GPUInfo -> AIModelStatus

## R2.6 No Empty Catches

Boundary: every catch must give user-visible feedback (setError / console + message).

```tsx
// OK
catch (err) { setError("Failed to connect to the server") }
// NOT OK
catch {}
```

Exceptions: `video.play().catch(() => {})` (browser autoplay policy), clipboard API, SSE JSON parsing.

Check:
```bash
grep -rn "catch\s*()\s*=>\s*{}\|catch\s*{}" web/src/ | grep -v "video\.play\|clipboard\|node_modules"
```

## R2.7 No Hard-Coded Chinese Outside i18n

Boundary: all user-visible text goes through `t('key')`; writing Chinese string literals directly in components/js is forbidden. i18n keys live in `web/src/i18n/locales/{zh,en}.json`.

```tsx
// OK
<ErrorBar message={t('errors.loadFailed')} />
// NOT OK
<ErrorBar message="Failed to load library list" />
```

Check:
```bash
grep -rn '["'"'"'].*[一-鿿].*["'"'"']' web/src/ --include="*.tsx" --include="*.ts" | grep -v "i18n\|locales\|node_modules"
```

## R2.8 No Dead-Code Leftovers

Boundary: source trees forbid `.bak` / `.refactor-backup` / `.original` files. Unused page components must be deleted in the same change. Use `scripts/backup.sh` (into `backups/`) instead of leaving `.bak` files in source.

Check:
```bash
find web/src server \( -name "*.bak*" -o -name "*.refactor-backup" -o -name "*.original" \)
```

## R2.9 Strict TypeScript

Boundary: `tsconfig.json` must enable `strict` + `noUnusedLocals` + `noUnusedParameters`. Turning these off opens the door to code rot.

```bash
cd web && npm run typecheck   # must be zero errors
```

## R2.10 Page Components <= 1000 Lines

Boundary: `.tsx` files under `pages/` and `components/` must not exceed 1000 lines. Split into sub-components beyond that.

> Note: the previous 500-line ceiling was too tight for large pages and was raised to 1000 on 2026-09-02. It remains a hard ceiling; split beyond it.

Check:
```bash
find web/src/pages web/src/components -name "*.tsx" -exec wc -l {} \; | awk '$1 > 1000'
```
