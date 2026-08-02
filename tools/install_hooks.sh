#!/bin/bash
# 安装防泄露守门钩子: 把 hooks/ 下的版本化副本链接到 .git/hooks/
# 用法: bash tools/install_hooks.sh   (克隆仓库后跑一次即可)
set -e
cd "$(dirname "$0")/.."
mkdir -p .git/hooks
for h in pre-commit pre-push; do
    ln -sf "../../hooks/$h" ".git/hooks/$h"
    chmod +x "hooks/$h"
    echo "✓ 已安装 .git/hooks/$h -> hooks/$h"
done
echo "守门钩子已生效: 提交/推送时会自动拦截 data/ .env mysql-data/ 等敏感路径"
