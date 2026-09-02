# 06 Quality Standard

> Rules: R0.6 (common quality standard covering every layer of R0-R7; EN mirror of `docs/规范/06_质量规范.md`; the Chinese file is authoritative)
> Purpose: unified rules for naming, commits, formatting, and documentation maintenance.

---

## 1. New File Rules

| File type | Location | Naming |
|-----------|----------|--------|
| Python API route | `server/app/api/` | snake_case, e.g. `tag_export.py` |
| Python model | `server/app/models/` | snake_case |
| React page | `web/src/pages/` | PascalCase, e.g. `VideoDetail.tsx` |
| React component | `web/src/components/` | PascalCase, grouped in feature subdirectories |
| Zustand store | `web/src/stores/` | camelCase, e.g. `videoStore.ts` |
| API module | `web/src/api/` | camelCase, e.g. `videoApi.ts` |
| Documentation | `docs/` | Chinese names allowed; the `必读_` prefix marks onboarding must-reads |

## 2. Git Commit Rules

```
Format: <type>(<scope>): <subject>
type: feat / fix / refactor / style / docs / chore / perf / test
scope: server / web / ai / orchestrator / docker / docs

OK:   feat(web): add batch video delete
OK:   fix(server): fix N+1 query during scan
NOT:  update / fix bug / changed some stuff
```

Forbidden:
- Pushing directly to main
- Committing `.bak` / `.refactor-backup` / `.original` files
- Mixing unrelated changes into one commit (fixing a bug while reformatting -> split into two commits)
- Empty commit messages

## 3. Code Formatting

```bash
# Backend - required before commit (black is not bundled; install it first: pip install black)
cd server && black --line-length=100 .

# Frontend - required before commit (prettier is not bundled; install it first: cd web && npm i -D prettier)
cd web && npx prettier --write "src/**/*.{ts,tsx,css}"

# Type check (CI gate)
cd web && npm run typecheck
```

## 4. Iron Rule Self-Check (required before commit)

```bash
# Full hard-rule check
./scripts/check.sh

# Rules reference (full text)
cat docs/铁律.md
```

## 5. Documentation Maintenance

- `docs/铁律.md` is the single source of truth for the iron rules. Other documents must not restate rule details (prevents drift).
- Changing a rule requires syncing the standard + script + revision log (four-step closure).
- Proposal documents are named `方案_<topic>.md` and archived when approved.
- Files currently over the line-count limit (2026-09-02): see `docs/规范/01_后端规范.md`; these converge gradually.
