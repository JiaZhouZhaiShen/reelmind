# 05 Container Standard

> Rules: R5.1-R5.3 (EN mirror of `docs/规范/05_容器规范.md`; the Chinese file is authoritative)
> Purpose: architecture boundaries and security checks for Docker deployment (`docker-compose.yml`).

---

## R5.1 AI/Orchestrator Must Be Stateless

Boundary: deleting and recreating a container must not affect any data. AI model weights are pre-baked into the image.

| Container | Volume needs |
|-----------|--------------|
| postgres | PG data |
| reelmind-server | SQLite + media library |
| reelmind-orchestrator | none (stateless) |
| reelmind-ai | shared volumes only (media read-only + SQLite read/write) |

Check: confirm every path a container writes is inside a mounted volume, never in the container's local filesystem.

## R5.2 No docker.sock Mounts

Boundary: no container may mount `/var/run/docker.sock`. This is a container-escape entry point.

```yaml
# FORBIDDEN
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

Check:
```bash
grep "docker.sock" docker-compose*.yml
```

Current state (measured 2026-09-02): `docker-compose.yml` only mentions docker.sock in a comment ("removed"), with no real mount. Compliant.

## R5.3 Cross-Container Traceability

Boundary: all cross-container requests propagate `trace_id`; logs use a structured format and are written to stdout, not files.

```python
logger.info("pipeline_step", trace_id="abc123", engine="scene", step=5, total=10)
```

Check:
```bash
grep -rn "trace_id\|structlog" server/app/ server/ai_service/
```

Note: this is an evolutionary direction. It is **not implemented yet** (measured 2026-09-02: zero `trace_id` occurrences in the repo). It is a future improvement item, not a blocker.
