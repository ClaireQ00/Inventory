#!/bin/bash
# ============================================================
# Kimi 只读代码审查 (2026-08-15 加, 分工协议见 DECISIONS.md)
# 用法: bash scripts/kimi_review.sh [N]    # N=审查最近几次 commit, 默认 3
# 产出: .research/review_YYYYMMDD.md (Kimi 当天唯一允许写的文件)
# 铁律: Kimi 只读代码 (git log/diff/读文件), 不改任何源码,
#       不碰数据库, 不跑 docker; 结论只写报告文件。
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

N="${1:-3}"
DATE=$(date +%Y%m%d)
OUT=".research/review_${DATE}.md"
KIMI=/Users/guixinqie/.kimi-code/bin/kimi

[ -x "$KIMI" ] || { echo "kimi CLI 不存在: $KIMI (先 kimi login)"; exit 1; }
mkdir -p .research

echo "[kimi_review] 审查范围: 最近 ${N} 次 commit → ${OUT}"

"$KIMI" -p "你是本项目的只读代码审查员（分工协议见 DECISIONS.md：只读代码，唯一允许写的文件是 ${OUT}，其余任何文件都禁止修改，禁止 docker/数据库写操作）。

任务：
1. 先读 DECISIONS.md 和 docs/AGENT_GUIDE.md 了解项目约定。
2. 用 git log --oneline -${N} 和 git log -p -${N} 查看最近 ${N} 次 commit 的完整变更（也可 git show <hash> 逐个看）。
3. 对照 docs/REVIEW_BY_CLAUDE_CODE.md 中对应条目的「建议修法」，逐条复核改动是否贴合、有无修偏/漏改/引入新问题（重点：业务规则闸门、SQL 正确性、四处同步 R7）。
4. 把审查报告写到 ${OUT}（覆盖旧内容），格式：
   # 代码审查报告 YYYY-MM-DD（Kimi，只读）
   ## 审查范围
   ## 逐 commit 结论（表格: hash | 条目 | 判定(贴合/修偏/漏改) | 证据 文件:行号）
   ## 新发现问题（如有，🔴/🟡/🔵 分级 + 证据）
   ## 结论（一句话：可否合并/需返工点）
5. 完成后回复一段 200 字以内的摘要（不写其他任何文件）。"

echo "[kimi_review] 完成，报告: ${OUT}"
