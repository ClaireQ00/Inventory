#!/usr/bin/env bash
# ============================================================
# auto-review.sh — PostToolUse Hook 自动校验闸机
# ============================================================
#
# 触发时机：Claude Code 在每次 Edit/Write/MultiEdit 之后自动调用
# 作用：拦低级错误（schema 三处不同步 / 校验挂 / 敏感数据混入）
#
# 智能跳过：
#   - 只改了 *.md / docs/ / README / CONTRIBUTING → 直接放行（不打扰文档活）
#   - 只改了 .gitignore / LICENSE → 放行
#
# 失败行为：
#   - 校验挂 → exit 2 + stderr 输出（Claude 会自动看见并尝试修复）
#   - 校验过 → exit 0（静默放行）
#
# 手工测试：
#   bash scripts/auto-review.sh
# ============================================================

set -uo pipefail

# Claude Code 会把项目根目录注入到这个环境变量
ROOT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

# ---------- 1. 判断改动范围（如果项目没装 git，就当作"有改动"处理）----------

CHANGED_FILES=""
if command -v git >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  # 已提交 + 未提交 + 未跟踪的全部纳入
  CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null; git status --porcelain 2>/dev/null | awk '{print $2}')
fi

# ---------- 2. 智能跳过：纯文档改动不打扰 ----------

# 没改动 → 直接放行（可能是 hook 自己第一次跑）
if [[ -z "$CHANGED_FILES" ]]; then
  exit 0
fi

# 业务代码扩展名 / 路径
BUSINESS_PATTERN='\.(sql|py|csv)$|^(sql/|tools/|scripts/|sample/|\.claude/skills/|\.claude/agents/)'

# 看是否有任何文件命中业务模式
HAS_BUSINESS_CHANGE=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if echo "$f" | grep -Eq "$BUSINESS_PATTERN"; then
    HAS_BUSINESS_CHANGE=1
    break
  fi
done <<< "$CHANGED_FILES"

if [[ "$HAS_BUSINESS_CHANGE" -eq 0 ]]; then
  # 纯文档/配置改动 → 直接放行
  exit 0
fi

# ---------- 3. 有业务代码改动 → 跑校验 ----------

# 3.1 先做敏感数据扫描（最快，先跑）
if [[ -x scripts/check-sensitive-data.sh ]]; then
  if ! bash scripts/check-sensitive-data.sh >/dev/null 2>&1; then
    echo "[PostToolUse Hook] 敏感数据扫描未通过，请检查是否把 data/ 或 private/ 下的真实文件加进来了" >&2
    echo "  运行 bash scripts/check-sensitive-data.sh 看详情" >&2
    exit 2
  fi
fi

# 3.2 跑端到端业务校验（用 demo 数据，不污染真实数据）
if [[ -x scripts/run_local_validation.sh ]]; then
  VALIDATION_OUTPUT=$(bash scripts/run_local_validation.sh --demo 2>&1)
  VALIDATION_EXIT=$?

  if [[ $VALIDATION_EXIT -ne 0 ]]; then
    echo "[PostToolUse Hook] run_local_validation.sh --demo 未通过（exit $VALIDATION_EXIT）" >&2
    echo "" >&2
    echo "--- 校验输出（最后 60 行）---" >&2
    echo "$VALIDATION_OUTPUT" | tail -60 >&2
    echo "----------------------------" >&2
    echo "" >&2
    echo "修复提示：" >&2
    echo "  1. 看上面的错误信息，定位是哪一步挂了" >&2
    echo "  2. 常见原因：改了 schema 漏了 SQLITE_SCHEMA / DERIVED_RULES 三处同步" >&2
    echo "  3. 可以让 schema-sync-checker subagent 帮你查三处同步" >&2
    exit 2
  fi
fi

# 全部通过 → 静默放行
exit 0
