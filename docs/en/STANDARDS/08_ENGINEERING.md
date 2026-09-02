# 08 Engineering Process Standard

> Rules: R7.1-R7.3 (EN mirror of `docs/规范/08_工程流程规范.md`; the Chinese file is authoritative)
> Purpose: engineering boundaries for dependency changes, config changes, and new modules.

---

## R7.1 Dependency Changes Require Rebuilds

Boundary: after changing `server/requirements.txt` / `server/ai_service/requirements.txt` / `web/package.json`, rebuild the affected image and verify. Changing files alone is not enough.

```bash
# changed server/requirements.txt
docker compose build reelmind-server

# changed ai_service/requirements.txt
docker compose build reelmind-ai

# changed web/package.json
cd web && npm install && npm run build
```

Forbidden:
- Changing dependencies without rebuilding (the container still runs old deps; behavior diverges)
- Adding a dependency without checking whether another container already has it (duplicates bloat images)

## R7.2 Config Changes Require Verification

Boundary: after changing `.env` / `server/app/config.py`, restart the containers and verify the change took effect.

```bash
# changed .env
docker compose restart reelmind-server reelmind-ai reelmind-orchestrator
# verify
docker logs reelmind-server | grep "config"
```

Forbidden:
- Committing `.env` (contains real passwords/tokens). `.gitignore` excludes it; `git add -f .env` is a violation.
- Claiming "it took effect" without restarting after a config change

Check:
```bash
# Is .env tracked by git? (should be empty)
git ls-files | grep -E "^\.env$"
```

## R7.3 New Modules Must Be Registered

Boundary: adding a container / service / engine / directory requires syncing:

| New object | Must sync |
|------------|-----------|
| New container | `docker-compose.yml` service definition + container table in `docs/必读_README.md` + architecture table in CLAUDE.md |
| New AI engine | `docs/规范/01_后端规范.md` / AI pipeline docs |
| New route file | matching api file under `web/src/api/` (per R3.1) |
| New store | split by domain per R2.1 |

Forbidden: adding a container/service while leaving compose and docs out of sync (others cannot find it, environments fail to start).

Check: PRs/proposals that add modules must include a documentation sync item.
