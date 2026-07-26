#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat <<EOF
Usage: $0 <module>

Example modules:
  inventory
  purchase
  sales
  foreign-trade
  logistics
  finance
  quality

This script prints the recommended workflow steps for a given module.
EOF
  exit 1
fi

MODULE="$1"
case "$MODULE" in
  inventory)
    AGENTS=("explore" "general-purpose" "task" "code-review")
    ;;
  purchase)
    AGENTS=("explore" "general-purpose" "task" "code-review")
    ;;
  sales)
    AGENTS=("explore" "general-purpose" "task" "code-review")
    ;;
  foreign-trade)
    AGENTS=("research" "explore" "general-purpose" "task" "security-review")
    ;;
  logistics)
    AGENTS=("explore" "general-purpose" "task" "code-review")
    ;;
  finance)
    AGENTS=("explore" "general-purpose" "task" "security-review")
    ;;
  quality)
    AGENTS=("explore" "general-purpose" "task" "code-review")
    ;;
  *)
    AGENTS=("explore" "general-purpose" "task" "code-review")
    ;;
esac

cat <<EOF
Module: $MODULE
Recommended workflow:

1. 调研阶段
   - 使用 explore/research agent 了解业务边界、流程和对接点。
2. 方案设计
   - 使用 general-purpose agent 设计数据模型、接口和文档结构。
3. 开发实现
   - 使用 general-purpose agent 进行代码和 schema 改动。
4. 验证和校验
   - 使用 task agent 运行验证脚本、检查 SQL 和样例数据。
5. 审查和交付
   - 使用 code-review 或 security-review agent 进行审查。

Suggested agents: ${AGENTS[*]}

Recommended files to update:
- docs/README.md
- docs/AGENT_GUIDE.md
- CONTRIBUTING.md
- sql/01_schema.sql
- sql/02_seed_data.sql
- sql/03_master_data.sql
- scripts/run-review.sh
EOF
