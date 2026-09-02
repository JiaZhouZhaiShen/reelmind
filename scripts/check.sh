#!/usr/bin/env bash
# ============================================================
# REELMIND 铁律硬规则检查  scripts/check.sh
# 铁律本体: docs/铁律.md    执行细则: docs/规范/
#
# 用法:
#   ./scripts/check.sh            # 全量检查
#   ./scripts/check.sh --staged   # 只检查 git 暂存区改动 (pre-commit 用)
#
# 退出码: 0=通过, 1=有违规
# 硬规则(grep可查)在此检查; 软规则(职责单一/三态自包含)靠 Code Review
# ============================================================
set -u

# Windows 非登录 shell 下 Git Bash 的 PATH 可能缺 /usr/bin；先兜底再自检
export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"

REQUIRED_TOOLS="dirname grep awk find xargs tr sed sort head wc git"
MISSING=""
for t in $REQUIRED_TOOLS; do
  command -v "$t" >/dev/null 2>&1 || MISSING="$MISSING $t"
done
if [ -n "$MISSING" ]; then
  echo "❌ check.sh 运行环境缺工具:$MISSING（Windows 请使用 Git Bash 完整环境）" >&2
  exit 2
fi

cd "$(dirname "$0")/.."

MODE="full"
STAGED_FILES=""
if [ "${1:-}" = "--staged" ]; then
  MODE="staged"
  STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || echo "")
  if [ -z "$STAGED_FILES" ]; then
    echo "✅ (staged) 无暂存区改动"
    exit 0
  fi
  echo "🔍 (staged) 检查暂存区 $(echo "$STAGED_FILES" | wc -l | tr -d ' ') 个文件"
fi

FAIL=0
PASS=0

# ok <编号> <描述>   — 通过
# bad <编号> <描述>  — 违规
ok() { PASS=$((PASS+1)); printf "✅ %-8s %s\n" "$1" "$2"; }
bad() { FAIL=$((FAIL+1)); printf "❌ %-8s %s\n" "$1" "$2"; }

# 在暂存模式下判断某路径是否相关
is_staged() {
  [ "$MODE" = "full" ] && return 0
  echo "$STAGED_FILES" | grep -q "\.$1$"
}

echo "============================================="
echo " 铁律硬规则检查  (mode=$MODE)"
echo "============================================="

# ---------- R1.1 Server 无 AI 推理库 ----------
if [ "$MODE" = "full" ]; then
  if grep -rn --include="*.py" "torch\|transformers\|model\.predict\|model\.encode" server/app/ 2>/dev/null | grep -q .; then
    bad R1.1 "Server 调用了 AI 推理库"
  else
    ok  R1.1 "Server 无 AI 推理库"
  fi
else
  ok R1.1 "(staged) 跳过, 此规则为全量检查"
fi

# ---------- R1.3 状态唯一写入口: 无直接写 ai_engine_jobs / processing_state ----------
R13_WHITELIST="^server/app/core/job_helpers\.py:|^server/ai_service/job_helpers\.py:"
r13_violations() {
  echo "$1" | xargs grep -rnE --include="*.py" "INSERT INTO ai_engine_jobs|UPDATE[[:space:]]+ai_engine_jobs|DELETE FROM ai_engine_jobs|UPDATE[[:space:]]+processing_state|query\(AIEngineJob\).*\.update\(" 2>/dev/null \
    | grep -vE "alembic|migration" \
    | grep -vE "$R13_WHITELIST" || true
}
if is_staged py; then
  if [ "$MODE" = "full" ]; then
    R13_OUT=$(r13_violations "server")
  else
    R13_TARGET=$(echo "$STAGED_FILES" | grep "\.py$" | grep "^server/" | tr '\n' ' ')
    R13_OUT=$(r13_violations "$R13_TARGET")
  fi
  if [ -n "$R13_OUT" ]; then
    bad R1.3 "存在绕过写入口直接写 ai_engine_jobs / processing_state"
    echo "$R13_OUT" | head -5 | sed 's/^/       /'
  else
    ok  R1.3 "无直接写 ai_engine_jobs"
  fi
fi

# ---------- R1.4 后端 api 文件 ≤1000 行 ----------
if [ "$MODE" = "full" ]; then
  if find server/app/api -name "*.py" -exec wc -l {} \; 2>/dev/null | awk '$1 > 1000' | grep -q .; then
    bad R1.4 "后端 api 文件超 1000 行"
    find server/app/api -name "*.py" -exec wc -l {} \; 2>/dev/null | awk '$1 > 1000' | sort -rn | head -5 | sed 's/^/       /'
  else
    ok  R1.4 "后端 api 文件均 ≤1000 行"
  fi
else
  if echo "$STAGED_FILES" | grep -q "^server/app/api/.*\.py$"; then
    for f in $(echo "$STAGED_FILES" | grep "^server/app/api/.*\.py$"); do
      n=$(wc -l < "$f")
      if [ "$n" -gt 1000 ]; then
        bad R1.4 "$f 共 $n 行, 超 1000 行"
      fi
    done
  fi
  [ "$(echo "$STAGED_FILES" | grep -c "^server/app/api/.*\.py$" || true)" = "0" ] && ok R1.4 "(staged) 暂存区无 api 文件"
fi

# ---------- R2.5 高频组件加 memo (Card/Item/Row 列表项) ----------
if is_staged tsx; then
  GREP_TARGET=""
  if [ "$MODE" = "full" ]; then
    GREP_TARGET=$(find web/src/components -name "*Card*.tsx" -o -name "*Item*.tsx" -o -name "*Row*.tsx" 2>/dev/null | tr '\n' ' ')
  else
    GREP_TARGET=$(echo "$STAGED_FILES" | grep -E "^web/src/components/.*(Card|Item|Row)\.tsx$" | tr '\n' ' ')
  fi
  if [ -n "$GREP_TARGET" ]; then
    NOMEMO=""
    for f in $GREP_TARGET; do
      [ -f "$f" ] || continue
      grep -q "React.memo\|memo(" "$f" 2>/dev/null || NOMEMO="$NOMEMO $f"
    done
    if [ -n "$NOMEMO" ]; then
      bad R2.5 "列表项组件(Card/Item/Row)未加 React.memo"
      echo "$NOMEMO" | tr ' ' '\n' | sed '/^$/d' | head -5 | sed 's/^/       /'
    else
      ok  R2.5 "列表项组件均加 memo"
    fi
  else
    ok R2.5 "无 Card/Item/Row 列表项组件"
  fi
fi

# ---------- R2.6 禁止空 catch ----------
if is_staged tsx || is_staged ts; then
  if [ "$MODE" = "full" ]; then
    GREP_TARGET="web/src"
  else
    GREP_TARGET=$(echo "$STAGED_FILES" | grep -E "\.(tsx|ts)$" | grep "^web/src/" | tr '\n' ' ')
  fi
  if [ -n "$GREP_TARGET" ] && echo "$GREP_TARGET" | xargs grep -n "catch\s*()\s*=>\s*{}\|catch\s*{}" 2>/dev/null | grep -v "video\.play\|clipboard" | grep -q .; then
    bad R2.6 "存在空 catch"
    echo "$GREP_TARGET" | xargs grep -n "catch\s*()\s*=>\s*{}\|catch\s*{}" 2>/dev/null | grep -v "video\.play\|clipboard" | head -5 | sed 's/^/       /'
  else
    ok  R2.6 "无空 catch"
  fi
fi

# ---------- R2.7 i18n 无硬编码中文 ----------
if is_staged tsx || is_staged ts; then
  if [ "$MODE" = "full" ]; then
    GREP_TARGET="web/src"
  else
    GREP_TARGET=$(echo "$STAGED_FILES" | grep -E "\.(tsx|ts)$" | grep "^web/src/" | grep -v "^web/src/i18n/" | tr '\n' ' ')
  fi
  if [ -n "$GREP_TARGET" ] && echo "$GREP_TARGET" | xargs grep -nP '["'"'"'][\x{4e00}-\x{9fff}].*["'"'"']' 2>/dev/null | grep -v "i18n\|locales\|node_modules" | grep -q .; then
    bad R2.7 "存在硬编码中文"
    echo "$GREP_TARGET" | xargs grep -nP '["'"'"'][\x{4e00}-\x{9fff}].*["'"'"']' 2>/dev/null | grep -v "i18n\|locales\|node_modules" | head -5 | sed 's/^/       /'
  else
    ok  R2.7 "无硬编码中文"
  fi
fi

# ---------- R2.8 无死代码残留 (.bak/original/refactor-backup) ----------
if [ "$MODE" = "full" ]; then
  if find web/src server -name "*.bak*" -o -name "*.original" -o -name "*.refactor-backup" 2>/dev/null | grep -q .; then
    bad R2.8 "源码目录存在死代码残留 (.bak/original/refactor-backup)"
    find web/src server -name "*.bak*" -o -name "*.original" -o -name "*.refactor-backup" 2>/dev/null | head -10 | sed 's/^/       /'
  else
    ok  R2.8 "源码目录无死代码残留"
  fi
else
  if echo "$STAGED_FILES" | grep -qE "\.(bak|bak2|original|refactor-backup)$"; then
    bad R2.8 "暂存区包含 .bak/死代码残留文件"
    echo "$STAGED_FILES" | grep -E "\.(bak|bak2|original|refactor-backup)$" | sed 's/^/       /'
  else
    ok  R2.8 "暂存区无 .bak 文件"
  fi
fi

# ---------- R2.9 TS 严格模式开启 ----------
if [ "$MODE" = "full" ]; then
  if [ -f web/tsconfig.json ] && grep -q '"noUnusedLocals" *: *true' web/tsconfig.json && grep -q '"noUnusedParameters" *: *true' web/tsconfig.json && grep -q '"strict" *: *true' web/tsconfig.json; then
    ok R2.9 "TS 严格模式已开启"
  else
    bad R2.9 "tsconfig.json 未开启 strict/noUnusedLocals/noUnusedParameters"
  fi
else
  ok R2.9 "(staged) 跳过, 此规则为全量检查"
fi

# ---------- R2.10 前端页面组件 ≤1000 行 ----------
if [ "$MODE" = "full" ]; then
  if find web/src/pages web/src/components -name "*.tsx" -exec wc -l {} \; 2>/dev/null | awk '$1 > 1000' | grep -q .; then
    bad R2.10 "前端页面/组件超 1000 行"
    find web/src/pages web/src/components -name "*.tsx" -exec wc -l {} \; 2>/dev/null | awk '$1 > 1000' | sort -rn | head -5 | sed 's/^/       /'
  else
    ok  R2.10 "前端页面组件均 ≤1000 行"
  fi
else
  if echo "$STAGED_FILES" | grep -qE "^(web/src/pages|web/src/components)/.*\.tsx$"; then
    for f in $(echo "$STAGED_FILES" | grep -E "^(web/src/pages|web/src/components)/.*\.tsx$"); do
      n=$(wc -l < "$f")
      if [ "$n" -gt 1000 ]; then
        bad R2.10 "$f 共 $n 行, 超 1000 行"
      fi
    done
  fi
  [ "$(echo "$STAGED_FILES" | grep -cE "^(web/src/pages|web/src/components)/.*\.tsx$" || true)" = "0" ] && ok R2.10 "(staged) 暂存区无页面组件"
fi

# ---------- R3.1 API 按域拆分: client.ts 只做 barrel 导出 ≤50 行 ----------
if [ "$MODE" = "full" ]; then
  n=$(wc -l < web/src/api/client.ts 2>/dev/null || echo 0)
  if [ "$n" -gt 50 ]; then
    bad R3.1 "web/src/api/client.ts 共 $n 行, 超 50 行"
  else
    ok  R3.1 "client.ts ≤50 行 ($n)"
  fi
else
  if echo "$STAGED_FILES" | grep -qE "^web/src/api/client\.ts$"; then
    n=$(wc -l < web/src/api/client.ts 2>/dev/null || echo 0)
    if [ "$n" -gt 50 ]; then
      bad R3.1 "web/src/api/client.ts 共 $n 行, 超 50 行"
    else
      ok  R3.1 "client.ts ≤50 行 ($n)"
    fi
  else
    ok R3.1 "(staged) 暂存区无 client.ts"
  fi
fi

# ---------- R5.2 禁止 docker.sock 挂载 ----------
if [ "$MODE" = "full" ]; then
  if grep -n "docker\.sock" docker-compose*.yml 2>/dev/null | awk -F'docker.sock' '!($1 ~ /#/)' | grep -q .; then
    bad R5.2 "docker-compose 存在 docker.sock 挂载"
  else
    ok  R5.2 "无 docker.sock 挂载"
  fi
else
  if echo "$STAGED_FILES" | grep -qE "docker-compose.*\.yml$"; then
    for f in $(echo "$STAGED_FILES" | grep -E "docker-compose.*\.yml$"); do
      if grep -n "docker\.sock" "$f" 2>/dev/null | awk -F'docker.sock' '!($1 ~ /#/)' | grep -q .; then
        bad R5.2 "$f 存在 docker.sock 挂载"
      fi
    done
  fi
  echo "$STAGED_FILES" | grep -qE "docker-compose.*\.yml$" || ok R5.2 "(staged) 暂存区无 compose 文件"
fi

# ---------- R6.1 模型变更走迁移: 源码目录无手写 DDL ----------
if is_staged py; then
  GREP_TARGET=""
  if [ "$MODE" = "full" ]; then
    GREP_TARGET="server/app server/ai_service"
  else
    GREP_TARGET=$(echo "$STAGED_FILES" | grep "\.py$" | grep -E "^(server/app|server/ai_service)/" | tr '\n' ' ')
  fi
  if [ -n "$GREP_TARGET" ] && echo "$GREP_TARGET" | xargs grep -rn --include="*.py" "ALTER TABLE\|CREATE TABLE\|DROP TABLE" 2>/dev/null | grep -v "alembic\|migration" | grep -q .; then
    bad R6.1 "源码存在手写 DDL (ALTER/CREATE/DROP TABLE), 应走 alembic 迁移"
    echo "$GREP_TARGET" | xargs grep -rn "ALTER TABLE\|CREATE TABLE\|DROP TABLE" 2>/dev/null | grep -v "alembic\|migration" | head -5 | sed 's/^/       /'
  else
    ok  R6.1 "源码无手写 DDL"
  fi
fi

# ---------- R7.2 配置变更必验证: .env 禁止提交入库 ----------
if [ "$MODE" = "full" ]; then
  if git ls-files 2>/dev/null | grep -qE "^\.env$"; then
    bad R7.2 ".env 被 git 追踪, 禁止提交入库"
  else
    ok  R7.2 ".env 未被 git 追踪"
  fi
else
  if echo "$STAGED_FILES" | grep -qE "^\.env$"; then
    bad R7.2 "暂存区包含 .env, 禁止提交入库"
  else
    ok  R7.2 "(staged) 暂存区无 .env"
  fi
fi

# ---------- 汇总 ----------
echo "============================================="
echo " 结果: 通过 $PASS 项, 违规 $FAIL 项"
echo "============================================="
exit $FAIL
