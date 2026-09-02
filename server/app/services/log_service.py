"""Log aggregation service — fetches logs from Docker containers and file system.

Provides a unified interface for listing log sources, fetching/filtering logs,
and streaming real-time log output via SSE. Follows the REELMIND architecture
principle: server proxies/aggregates, does not compute.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
try:
    from ..api.docker_api import DockerAPI
except Exception:
    DockerAPI = None  # docker.sock not available — container log features disabled

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# ── Known ReelMind containers ────────────────────────────────────────────────
REELMIND_CONTAINERS: dict[str, str] = {
    "server": "reelmind-server",
    "ai": "reelmind-ai",
    "postgres": "reelmind-postgres",
    "redis": "reelmind-redis",
    "orchestrator": "reelmind-orchestrator",
}

DEFAULT_TAIL = 200


# ── Data types ───────────────────────────────────────────────────────────────
@dataclass
class LogEntry:
    timestamp: str = ""
    level: str = "INFO"
    logger: str = ""
    message: str = ""
    raw: str = ""


@dataclass
class LogSource:
    id: str
    label: str
    type: str  # "docker" | "file"
    status: str = "running"  # for docker: running / stopped / unavailable
    has_logs: bool = True


@dataclass
class LogResult:
    source: str
    lines: list[LogEntry]
    total_lines: int
    truncated: bool
    docker_available: bool = True


# ── Pattern cache ────────────────────────────────────────────────────────────
_TIMESTAMP_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*"
)
_UVICORN_RE = re.compile(
    r"^(?P<level>INFO|WARNING|ERROR|DEBUG|CRITICAL):\s+"
)
_PYTHON_LOG_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,\.]\d{3}\s+"
    r"(?P<level>INFO|WARNING|ERROR|DEBUG|CRITICAL|WARN)\s+"
    r"(?P<logger>\S+)\s+(?P<msg>.+)$",
    re.MULTILINE,
)
_KNOWN_LEVELS = {"INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL", "WARN"}


# ── Docker helpers ───────────────────────────────────────────────────────────
_docker_api: DockerAPI | None = None


def _get_docker_api():
    global _docker_api
    if DockerAPI is None:
        return None
    if _docker_api is None:
        _docker_api = DockerAPI()
    return _docker_api


def _check_docker() -> bool:
    """Check if Docker Engine is reachable via Unix socket."""
    api = _get_docker_api()
    if api is None:
        return False
    try:
        return api.ping()
    except Exception:
        return False


async def _container_status(name: str) -> str:
    """Check container status via Docker Engine API."""
    api = _get_docker_api()
    if api is None:
        return "unavailable"
    try:
        info = await asyncio.get_event_loop().run_in_executor(
            None, api.inspect_container, name
        )
        if info is None:
            return "stopped"
        state = info.get("State", {})
        if state.get("Running"):
            return "running"
        if state.get("Restarting"):
            return "restarting"
        return state.get("Status", "stopped")[:20]
    except Exception:
        return "unavailable"
# ── Log line parser ──────────────────────────────────────────────────────────
def _parse_line(line: str) -> LogEntry:
    """Parse a single log line into structured LogEntry."""
    raw = line.rstrip("\n\r")
    entry = LogEntry(raw=raw)

    # Try Python structured log: 2026-06-30 10:15:23,456 INFO module message
    m = _PYTHON_LOG_RE.match(raw)
    if m:
        entry.timestamp = m.group("ts") if "ts" in m.groupdict() else ""
        entry.level = m.group("level")
        entry.logger = m.group("logger")
        entry.message = m.group("msg")
        return entry

    # Try timestamp prefix: 2026-06-30 10:15:23,456 ...
    m = _TIMESTAMP_RE.match(raw)
    if m:
        entry.timestamp = m.group("ts")
        rest = raw[m.end():]
        # Extract level from the rest
        level_m = _UVICORN_RE.match(rest)
        if level_m:
            entry.level = level_m.group("level")
            entry.message = rest[level_m.end():].strip()
        else:
            # Try extracting level word
            for lv in _KNOWN_LEVELS:
                if lv in rest[:20]:
                    entry.level = lv
                    entry.message = rest.strip()
                    break
            else:
                entry.message = rest.strip()
        return entry

    # No timestamp: try uvicorn-style: INFO:     ...
    m = _UVICORN_RE.match(raw)
    if m:
        entry.level = m.group("level")
        entry.message = raw[m.end():].strip()
        return entry

    # Fallback: raw line as message
    entry.message = raw
    return entry


def _detect_level(line: str) -> str:
    """Quick level detection without full parse (for filtering perf)."""
    for lv in ("ERROR", "WARNING", "CRITICAL", "WARN"):
        if lv in line:
            return lv
    if "INFO" in line:
        return "INFO"
    return "DEBUG"


# ── Log fetching ─────────────────────────────────────────────────────────────
async def list_docker_sources() -> list[LogSource]:
    """List all ReelMind Docker containers as log sources."""
    if not _check_docker():
        # Fall back to file sources only
        return []
    sources: list[LogSource] = []
    for sid, cname in REELMIND_CONTAINERS.items():
        status = await _container_status(cname)
        sources.append(LogSource(
            id=sid,
            label=f"reelmind-{sid}",
            type="docker",
            status=status,
            has_logs=status == "running",
        ))
    return sources


async def list_file_sources() -> list[LogSource]:
    """List log files in LOG_DIR as file sources."""
    from ..config import settings as s
    log_dir = s.LOG_DIR
    log_path = Path(log_dir)

    # Try candidate paths
    candidates = [
        log_path,
        Path(s.DATA_ROOT) / "logs",
        Path.cwd() / "logs",
        Path.home() / ".reelmind" / "logs",
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            log_path = c
            break

    if not log_path.exists():
        return []

    sources: list[LogSource] = []
    for f in sorted(log_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.suffix in (".log", ".txt", ".json"):
            sources.append(LogSource(
                id=f"file:{f.name}",
                label=f"📄 {f.name}",
                type="file",
                status="",
                has_logs=True,
            ))
    return sources


async def list_sources() -> list[LogSource]:
    """List all available log sources (Docker containers + files)."""
    docker = await list_docker_sources()
    files = await list_file_sources()
    return docker + files


async def fetch_logs(
    source_id: str,
    tail: int = DEFAULT_TAIL,
    search: str | None = None,
    level: str | None = None,
) -> LogResult:
    """Fetch logs from a given source with optional filtering."""
    if source_id.startswith("file:"):
        return await _fetch_file_log(source_id[5:], tail, search, level)

    return await _fetch_docker_log(source_id, tail, search, level)


async def _fetch_docker_log(
    sid: str,
    tail: int,
    search: str | None,
    level: str | None,
) -> LogResult:
    """Fetch logs from a Docker container."""
    cname = REELMIND_CONTAINERS.get(sid)
    if not cname:
        return LogResult(source=sid, lines=[], total_lines=0, truncated=False)

    # Use Docker Engine API instead of docker CLI
    api = _get_docker_api()
    if api is None:
        return LogResult(source=sid, lines=[], total_lines=0, truncated=False)
    output = await asyncio.get_event_loop().run_in_executor(
        None, api.container_logs, cname, tail
    )
    if not output:
        # Try to get container status
        status = await _container_status(cname)
        return LogResult(
            source=sid,
            lines=[LogEntry(
                level="WARN",
                message=f"Container {cname} is {status}. Start it to view logs."
            )],
            total_lines=0,
            truncated=False,
        )

    # Parse lines
    raw_lines = output.splitlines(keepends=False)
    entries: list[LogEntry] = []
    traceback_buffer: list[str] = []

    for raw in raw_lines:
        entry = _parse_line(raw)

        # Handle traceback continuation lines
        if traceback_buffer:
            if raw.startswith(" ") or raw.startswith("\t") or raw == "":
                traceback_buffer.append(raw)
                continue
            else:
                # Flush traceback buffer as single entry
                tb_entry = LogEntry(
                    timestamp=traceback_buffer[0],
                    level="ERROR",
                    logger="",
                    message="\n".join(traceback_buffer),
                    raw="\n".join(traceback_buffer),
                )
                entries.append(tb_entry)
                traceback_buffer = []

        # Detect traceback start
        if "Traceback (most recent call last)" in raw:
            traceback_buffer = [entry.timestamp or "", raw]
            continue

        entries.append(entry)

    # Flush any remaining traceback
    if traceback_buffer:
        tb_entry = LogEntry(
            timestamp=traceback_buffer[0],
            level="ERROR",
            logger="",
            message="\n".join(traceback_buffer),
            raw="\n".join(traceback_buffer),
        )
        entries.append(tb_entry)

    total = len(entries)

    # Apply filters
    if level:
        level_upper = level.upper()
        entries = [e for e in entries if e.level == level_upper]
    if search:
        search_lower = search.lower()
        entries = [e for e in entries if search_lower in e.message.lower()
                   or search_lower in e.raw.lower()]

    return LogResult(
        source=sid,
        lines=entries,
        total_lines=total,
        truncated=tail > 0 and total > 0,
    )


async def _fetch_file_log(
    filename: str,
    tail: int,
    search: str | None,
    level: str | None,
) -> LogResult:
    """Fetch logs from a file in LOG_DIR."""
    from ..config import settings as s

    file_path = Path(s.LOG_DIR) / filename
    if not file_path.exists():
        # Try alternative paths
        candidates = [
            Path(s.DATA_ROOT) / "logs" / filename,
            Path.cwd() / "logs" / filename,
            Path.home() / ".reelmind" / "logs" / filename,
        ]
        for c in candidates:
            if c.exists():
                file_path = c
                break

    if not file_path.exists():
        return LogResult(
            source=f"file:{filename}",
            lines=[LogEntry(level="WARN", message=f"Log file '{filename}' not found")],
            total_lines=0,
            truncated=False,
        )

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
    except Exception as e:
        return LogResult(
            source=f"file:{filename}",
            lines=[LogEntry(level="ERROR", message=f"Failed to read file: {e}")],
            total_lines=0,
            truncated=False,
        )

    entries = [_parse_line(line) for line in all_lines]
    total = len(entries)

    # Apply tail
    if tail > 0 and len(entries) > tail:
        entries = entries[-tail:]

    # Apply filters
    if level:
        level_upper = level.upper()
        entries = [e for e in entries if e.level == level_upper]
    if search:
        search_lower = search.lower()
        entries = [e for e in entries if search_lower in e.message.lower()]

    return LogResult(
        source=f"file:{filename}",
        lines=entries,
        total_lines=total,
        truncated=tail > 0 and len(all_lines) > tail,
    )


async def search_logs(
    query: str,
    sources: list[str] | None = None,
    tail: int = 50,
) -> list[dict]:
    """Quick search across multiple log sources."""
    all_sources = await list_sources()
    results: list[dict] = []

    for src in all_sources:
        if sources and src.id not in sources:
            continue
        try:
            result = await fetch_logs(src.id, tail=tail, search=query)
            if result.lines:
                results.append({
                    "source": src.id,
                    "label": src.label,
                    "matches": [
                        {"timestamp": e.timestamp, "level": e.level, "message": e.message}
                        for e in result.lines[:20]  # limit per source
                    ],
                    "total_matches": len(result.lines),
                })
        except Exception as e:
            logger.warning("Search failed for '%s': %s", src.id, e)

    return results


# ── SSE streaming ────────────────────────────────────────────────────────────
async def stream_logs(source_id: str) -> AsyncIterator[str]:
    """Stream log lines from a Docker container via SSE."""
    if source_id.startswith("file:"):
        yield f"event: error\ndata: Streaming not supported for file sources\n\n"
        return

    cname = REELMIND_CONTAINERS.get(source_id)
    if not cname:
        yield f"event: error\ndata: Unknown source: {source_id}\n\n"
        return

    # Poll-based streaming via Docker API (sync socket)
    api = _get_docker_api()
    if api is None:
        yield f"event: error\ndata: Docker socket not available\n\n"
        return
    last_lines: set[str] = set()
    try:
        while True:
            raw = await asyncio.get_event_loop().run_in_executor(
                None, api.container_logs, cname, 20
            )
            if raw:
                lines_list = raw.splitlines(keepends=False)
                for l in lines_list:
                    if not l or l in last_lines:
                        continue
                    entry = _parse_line(l)
                    payload = json.dumps({
                        "timestamp": entry.timestamp,
                        "level": entry.level,
                        "logger": entry.logger,
                        "message": entry.message,
                        "raw": entry.raw,
                    })
                    yield f"data: {payload}\n\n"
                last_lines = set(lines_list[-100:]) if len(lines_list) > 100 else set(lines_list)
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        raise
