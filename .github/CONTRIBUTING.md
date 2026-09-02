# Contributing to ReelMind

Thanks for your interest! This project is governed by its development iron rules (`docs/铁律.md`, English mirror `docs/en/IRON_RULES.md`).

## Quick start

```bash
git clone https://github.com/JiaZhouZhaiShen/reelmind.git
cd reelmind
cp .env.example .env     # set strong DB_PASSWORD / JWT_SECRET
cd web && npm install && npm run build && cd ..
docker compose build && docker compose up -d
```

## Before submitting changes

Every change must follow the iron rules:

1. **Verify first** — reproduce / confirm current behavior before editing.
2. **Propose first** — for cross-file / DB / behavior changes, describe the plan and scope first.
3. **Backup** — anything touching `data/` or DBs: use `scripts/backup.sh`.
4. **Minimal scope** — only change what the task requires; no drive-by fixes.
5. **Boundaries** — every plan states what it does *and* what it does not do.

## Quality gates (must pass)

```bash
./scripts/check.sh          # 13 iron-rule checks (also runs in CI)
cd web && npm run typecheck # tsc --noEmit
cd web && npm run build
```

## Commit conventions

`<type>(<scope>): <subject>` — type: feat/fix/refactor/style/docs/chore/perf/test; scope: server/web/ai/orchestrator/docker/docs.

No `.env`, `.bak`, or `backups/` files in commits. Use LF line endings (`.gitattributes` is enforced).

## Docs

Code changes must keep docs in sync: `docs/铁律.md` is the single source of truth for rules (Chinese authoritative, EN mirrors in `docs/en/`).
