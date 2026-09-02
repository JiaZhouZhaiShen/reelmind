#!/usr/bin/env bash
# ============================================================
# REELMIND 统一备份脚本  scripts/backup.sh
# 对应铁律 R0.3(代码) + R6.2(数据): 修改文件/操作数据库前先备份
#
# 用法:
#   ./scripts/backup.sh <描述> [文件...]           # 备份指定文件
#   ./scripts/backup.sh <描述> --dir <目录>        # 备份整个目录
#   ./scripts/backup.sh <描述> --db                # 备份数据库(PG pg_dump + 本地 SQLite)
#   ./scripts/backup.sh <描述> --db pg             # 仅备份 PG
#   ./scripts/backup.sh <描述> --db sqlite         # 仅备份本地 SQLite (.db)
#
# 示例:
#   ./scripts/backup.sh 修复搜索N+1 server/app/api/search.py
#   ./scripts/backup.sh 数据清理 --db
#
# 备份位置: backups/{YYYYMMDD_HHMMSS}_{描述}/
# ============================================================
set -eu
cd "$(dirname "$0")/.."

if [ $# -lt 2 ]; then
  echo "用法: $0 <描述> [文件...|--dir <目录>|--db [pg|sqlite]]" >&2
  exit 1
fi

DESC="$1"; shift
STAMP=$(date +%Y%m%d_%H%M%S)
DEST="backups/${STAMP}_${DESC}"
mkdir -p "$DEST"

# ---------- 数据库备份 (R6.2) ----------
if [ "${1:-}" = "--db" ]; then
  SCOPE="${2:-all}"
  if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "pg" ]; then
    if docker compose ps postgres 2>/dev/null | grep -q "Up"; then
      docker compose exec -T postgres pg_dump -U reelmind -F c -f /tmp/reelmind_backup.dump reelmind
      docker compose cp postgres:/tmp/reelmind_backup.dump "$DEST/reelmind_pg.dump"
      docker compose exec -T postgres rm -f /tmp/reelmind_backup.dump
      echo "✅ 已备份 PG: reelmind_pg.dump → $DEST/"
    else
      echo "⚠️ postgres 容器未运行, 跳过 PG 备份" >&2
    fi
  fi
  if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "sqlite" ]; then
    count=0
    for db in data/*.db; do
      [ -f "$db" ] || continue
      cp "$db" "$DEST/$(basename "$db")"
      count=$((count+1))
    done
    echo "✅ 已备份 SQLite: $count 个 .db 文件 → $DEST/"
  fi
  echo ""
  echo "数据库备份完成: $DEST"
  echo "记住: 数据变更验证通过后再删除备份。"
  exit 0
fi

if [ "${1:-}" = "--dir" ]; then
  SRC="$2"
  cp -r "$SRC" "$DEST/"
  echo "✅ 已备份目录: $SRC → $DEST/"
  exit 0
fi

for f in "$@"; do
  if [ -f "$f" ]; then
    cp "$f" "$DEST/"
    echo "✅ 已备份: $f → $DEST/"
  else
    echo "⚠️ 跳过(不存在): $f" >&2
  fi
done

echo ""
echo "备份完成: $DEST"
echo "记住: 修改并验证通过后再删除备份。"
