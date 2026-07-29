#!/usr/bin/env bash
#
# claude-driver.sh —— 让本地 claude CLI 在本项目里持续、无人值守地干活。
#
# 设计思路:
#   1. 不写死任务文本。每轮让 claude 自己读 CLAUDE.md + docs/CLAUDE_BRIEF.md,
#      判断"还没做完的事",挑一件推进。这样最贴合本项目已有的工作约定。
#   2. 每轮干完后强制跑 scripts/run_local_validation.sh(CLAUDE.md 规定的自检,
#      12 步全过才算对)。自检失败 → 计入失败连击,3 次就熔断。
#   3. 安全护栏:最大轮数 / 超时 / 失败熔断 / 紧急停止哨兵文件。
#
# 用法:
#   bash scripts/claude-driver.sh              # 默认 10 轮
#   MAX_ROUNDS=30 bash scripts/claude-driver.sh
#   紧急停止: 另开终端执行 touch /tmp/claude-driver.stop  (下一轮开头会检测并退出)
#
# 注意:
#   - 脚本会 git commit,所以请确保工作区初始是干净的(脚本启动时会检查)。
#   - claude --continue 让它跨轮保留记忆;若想每轮干净开始,改用 -p(去掉 --continue)。

set -uo pipefail

# ============================ 可调参数 ============================
PROJECT_DIR="/Users/guixinqie/inventory"
MAX_ROUNDS="${MAX_ROUNDS:-10}"          # 最大轮数(护栏)
ROUND_TIMEOUT="${ROUND_TIMEOUT:-1800}"  # 单轮超时秒数(默认 30 分钟)
MAX_FAIL_STREAK=3                        # 连续失败熔断阈值
STOP_FILE="/tmp/claude-driver.stop"      # 紧急停止哨兵文件
LOG_DIR="$PROJECT_DIR/.claude-driver-logs"
VALIDATE_SCRIPT="scripts/run_local_validation.sh"
# ==================================================================

cd "$PROJECT_DIR" || { echo "❌ 项目目录不存在: $PROJECT_DIR"; exit 1; }
mkdir -p "$LOG_DIR"

# ---- 启动前检查 ----
echo "▶ 启动 claude-driver"
echo "  项目: $PROJECT_DIR"
echo "  最大轮数: $MAX_ROUNDS   单轮超时: ${ROUND_TIMEOUT}s   熔断: 连续 $MAX_FAIL_STREAK 次失败"

if ! [ -x "$(command -v claude)" ]; then
  echo "❌ 找不到 claude CLI,请先确认已安装并在 PATH 中。"; exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "❌ 不是 git 仓库。"; exit 1
fi

# 工作区必须干净,否则脚本无法可靠地"每轮提交一次"
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  工作区不干净。请先提交或 stash 当前改动,再跑本脚本:"
  git status -s
  exit 1
fi

rm -f "$STOP_FILE"
echo "  紧急停止: 在另一终端执行  touch $STOP_FILE  (下一轮开头会退出)"
echo

ROUND=0
FAIL_STREAK=0

while [ "$ROUND" -lt "$MAX_ROUNDS" ]; do
  # ---- 1. 紧急停止检查 ----
  if [ -f "$STOP_FILE" ]; then
    echo "⛔ 检测到停止哨兵文件 ($STOP_FILE),停止驱动。"
    rm -f "$STOP_FILE"
    break
  fi

  ROUND=$((ROUND + 1))
  ROUND_LOG="$LOG_DIR/round-$(date +%Y%m%d-%H%M%S)-$ROUND.log"
  echo "==================== 第 $ROUND / $MAX_ROUNDS 轮 ===================="
  echo "  日志: $ROUND_LOG"

  # ---- 2. 调 claude 干一轮 ----
  # 任务指令:基于 SDD 文档体系,从 docs/TASKS.md 挑一件未勾选的任务推进。
  # 用 --continue 跨轮保留记忆。--max-turns 防止单轮里它无限调工具。
  PROMPT="你是本项目的开发者,现在按 SDD 文档体系继续推进开发。

请按顺序做:
1. 先读 CLAUDE.md(路由约定)和 docs/TASKS.md(任务清单,取代旧的 CLAUDE_BRIEF.md)。
2. 从 docs/TASKS.md 里挑【一件】状态为'待办'且优先级最高(P0>P1>P2)、依赖已满足的任务。
3. 实现前先查阅相关 SDD 文档:
   - 功能要看什么:见 docs/SPECS.md
   - 数据表/字段/派生:见 docs/DATA_MODEL.md
   - 设计决策与理由:见 docs/DESIGN.md + docs/adr/
   - 业务规则(铁律):见 docs/BUSINESS_RULES.md (R1金额四件套/R5派生/R6不硬编码/R7三处同步)
   - 验收场景:见 docs/SCENARIOS.md
4. 严格遵守:改 schema 三处同步(R7)、客户/币种/口岸/品类都是数据不硬编码(R6)、真实敏感数据只放 data/ 或 private/ 不进仓库(R8)。
5. 做完这一小块后:
   (a) 务必运行: bash $VALIDATE_SCRIPT  (13 步全过才算对)
   (b) 在 docs/TASKS.md 里把该任务的状态从'待办'改为'已完成',打勾 [x]
6. 最后在【单独一行】输出本轮状态:
   CONTINUE  —— 还有后续待办任务,下一轮请继续
   DONE      —— docs/TASKS.md 里所有非阶段二任务都已完成
   BLOCKED   —— 遇到需要人工判断的阻碍,说明清楚阻塞原因
本轮请只聚焦一件可独立完成的小事,不要贪多。"

  # 用 timeout 兜底,超时就杀掉;stderr 合并进日志
  set +e
  timeout "$ROUND_TIMEOUT" claude --continue --max-turns 80 -p "$PROMPT" \
    >"$ROUND_LOG" 2>&1
  CLAUDE_EXIT=$?
  set -e

  # 把本轮输出回显到终端(方便实时看)
  tail -n 40 "$ROUND_LOG"

  # ---- 3. 处理结果 ----
  if [ "$CLAUDE_EXIT" -ne 0 ]; then
    FAIL_STREAK=$((FAIL_STREAK + 1))
    echo "⚠️  claude 本轮异常退出 (exit=$CLAUDE_EXIT),失败连击 $FAIL_STREAK/$MAX_FAIL_STREAK"
    [ "$FAIL_STREAK" -ge "$MAX_FAIL_STREAK" ] && {
      echo "⛔ 连续失败 $FAIL_STREAK 次,熔断退出。最近日志: $ROUND_LOG"; exit 1; }
    sleep 5
    continue
  fi

  # 解析最后一行状态
  STATUS=$(tail -n 3 "$ROUND_LOG" | grep -E '^(CONTINUE|DONE|BLOCKED)$' | tail -n 1)
  STATUS="${STATUS:-UNKNOWN}"

  # ---- 4. 额外自检:无论 claude 说什么,独立验证一次 ----
  if [ -f "$VALIDATE_SCRIPT" ]; then
    echo "→ 运行独立自检 $VALIDATE_SCRIPT"
    if bash "$VALIDATE_SCRIPT" >>"$ROUND_LOG" 2>&1; then
      echo "  ✅ 自检通过"
    else
      FAIL_STREAK=$((FAIL_STREAK + 1))
      echo "  ❌ 自检失败,失败连击 $FAIL_STREAK/$MAX_FAIL_STREAK"
      [ "$FAIL_STREAK" -ge "$MAX_FAIL_STREAK" ] && {
        echo "⛔ 连续 $MAX_FAIL_STREAK 轮自检失败,熔断退出。日志: $ROUND_LOG"; exit 1; }
      sleep 3
      continue
    fi
  fi

  # ---- 5. 提交本轮成果(只提交非敏感文件;data/ private/ 已被 .gitignore 忽略)----
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "chore(driver): 第 $ROUND 轮自动推进 [$STATUS]" >/dev/null 2>&1 \
      && echo "  📦 已提交本轮改动" \
      || echo "  ⚠️  提交失败(可能无实质改动),继续"
  else
    echo "  (本轮无文件改动)"
  fi

  FAIL_STREAK=0   # 成功一轮就清零

  case "$STATUS" in
    DONE)
      echo "🎉 claude 报告所有任务已完成,停止驱动。"
      break
      ;;
    BLOCKED)
      echo "🛑 claude 报告遇到阻碍,已停止。请看日志: $ROUND_LOG"
      break
      ;;
    CONTINUE|*)
      echo "→ 继续下一轮"
      ;;
  esac

  echo
done

echo
echo "🏁 驱动结束,共完成 $ROUND 轮。"
echo "   日志目录: $LOG_DIR"
echo "   查看最近提交: git -C $PROJECT_DIR log --oneline -10"
