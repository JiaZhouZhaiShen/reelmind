# 00 Workflow Standard

> Rules: R0.1-R0.6 (EN mirror of `docs/规范/00_工作流程.md`; the Chinese file is authoritative)
> Purpose: the complete change workflow for every agent, clarifying what is allowed and what is not.

---

## 1. End-to-End Flow

```
Think -> Plan -> Verify -> Confirm -> Backup -> Change -> Verify -> Remove backup
```

| Step | What to do | Output |
|------|------------|--------|
| Think | Understand the request, assess impact, identify risks | Change plan (in mind) |
| Plan | Produce a concrete plan (files/lines/how) | Plan document or paragraph |
| Verify | Check the plan against the current state | Verification conclusion |
| Confirm | Wait for user confirmation (mandatory for major changes) | User agreement |
| Backup | Back up to `backups/{timestamp}_{description}/` | Backup files |
| Change | Apply the plan precisely | Changed code |
| Verify | Functional/regression/format verification | Verification result |
| Remove backup | Clean up the backup after verification passes | Clean tree |

## 2. R0.1 Verify Before Acting

Always confirm current state before changing anything; never edit from memory:

```bash
# 1. Read the file(s) you will change
# 2. Confirm environment state
docker compose ps
curl http://localhost:2588/api/ping
curl http://localhost:2589/health
# 3. Confirm the change baseline
#    fix bug    -> reproduce it first
#    behavior   -> confirm current behavior first
#    refactor   -> confirm existing logic/tests first
```

Violation example: fixing a bug without confirming it exists, i.e., editing something that is not broken.

## 3. R0.2 Plan Before Code

- Small, unambiguous single-file changes may be made directly.
- Cross-file changes, database changes, behavior changes, and refactors require a plan first, then verification and confirmation.
- When in doubt about whether confirmation is needed, ask.

## 4. R0.3 Backup Rule

```bash
# Prefer backup.sh, or do it manually:
mkdir -p backups/20260902_113001_iron_rules    # format: {YYYYMMDD_HHMMSS}_{description} (matches backup.sh)
cp <file-to-change> backups/20260902_113001_iron_rules/
```

- Back up before modifying any file; modification is not allowed until the backup is complete.
- Delete the backup only after the change has been verified.
- Backup directories live under the repo root `backups/`.

## 5. R0.4 Minimal Change

Allowed: the exact files/lines/logic the task requires; raising contradictions, risks, and side effects of the plan (that is correct behavior).

Forbidden:
- Refactoring/formatting/optimizing unrelated code along the way
- "Fixing" unrelated bugs casually
- Expanding the plan's intent on your own
- Trying multiple fixes on your own after an error: stop and report

## 6. R0.5 Plans Must Have Boundaries

Every plan, large or small, must state its boundary explicitly. Execute strictly inside it.

Required four elements:

```
1. What to do    - goal and content of this change
2. What NOT to do - explicit exclusions (prevents scope creep)
3. Files involved - list of files to change/add/delete
4. Acceptance    - how to tell the change is correct (functional/code/regression)
```

Execution rules:
- After the plan is confirmed, do only what elements 1 and 3 cover.
- Problems found inside element 2 (or outside the boundary): raise them, do not fix them unilaterally.
- Expanding the boundary requires a new plan and confirmation; never "expand while working".
- Out-of-boundary changes are forbidden even if trivial; record them as separate todos.

Typical violations:
- Refactoring code while fixing a bug
- Fixing a backend bug discovered while working on the frontend
- A plan that says "optimize search" but also changes the API

## 7. Forbidden Behavior Summary

```
No: changing code without verification
No: starting major changes without confirmation
No: modifying files without backup
No: casually changing unrelated things
No: fixing problems yourself without reporting
No: acting outside the plan boundary
```

## 8. Four Acceptance Gates (after every change)

Every change follows Change -> Run -> Accept, and must pass all four gates:

### Gate 1: Functional

```
[ ] Does the changed thing behave as expected?
    -> bug fix: the bug no longer reproduces
    -> feature: works as designed
    -> refactor: behavior unchanged, code better
[ ] API up?  curl http://localhost:2588/api/ping
[ ] AI up?   curl http://localhost:2589/health
```

### Gate 2: Code

```
[ ] cd web && npm run typecheck          # zero frontend type errors
[ ] ./scripts/check.sh                   # hard rules, zero new violations
[ ] No new empty catch / .bak / hard-coded Chinese
[ ] Touching ai_engine_jobs -> used the single write entry (R1.3)
[ ] Touching the database -> alembic migration (R6.1)
[ ] Touching dependencies -> image rebuilt (R7.1)
[ ] Touching config -> restarted and verified (R7.2)
[ ] New files placed and named correctly
```

### Gate 3: Regression

```
[ ] Backend changed -> main frontend pages still render
[ ] Frontend changed -> pages render, no API 500s
[ ] Models changed -> migration upgrades cleanly
[ ] Config changed -> persists after container restart
[ ] Docs updated for whatever changed (R7.3)
```

### Gate 4: Final Confirmation

```
[ ] Re-read your own diff (git diff)
[ ] Compare with the verified baseline; confirm it is exactly what you intended
[ ] No leftover debug code (console.log / print / TODO)
```
