#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Checking for sensitive or private data paths..."

ERROR=0

detect_path() {
  local path="$1"
  if [[ -e "$path" ]]; then
    echo "[WARN] Found sensitive path: $path"
    ERROR=1
  fi
}

# 检查本地敏感数据目录（应该被忽略）
if [[ -d "$ROOT_DIR/data" ]]; then
  echo "[INFO] Local data directory exists: data/ (should not be committed)"
  # 双保险: 确认 data/ 被 .gitignore 忽略
  if git check-ignore -q data/ 2>/dev/null; then
    echo "[OK]   data/ is properly gitignored"
  else
    echo "[ERROR] data/ is NOT gitignored, real data could leak!"
    ERROR=1
  fi
fi
if [[ -d "$ROOT_DIR/private" ]]; then
  echo "[INFO] Local private directory exists: private/ (should not be committed)"
  if git check-ignore -q private/ 2>/dev/null; then
    echo "[OK]   private/ is properly gitignored"
  else
    echo "[ERROR] private/ is NOT gitignored, real data could leak!"
    ERROR=1
  fi
fi

# 检查常见未忽略敏感文件
find . -maxdepth 2 \( -name ".env" -o -name ".env.*" \) -print 2>/dev/null | while read -r f; do
  if [[ "$f" != "./.git" && "$f" != "" ]]; then
    echo "[WARN] Sensitive environment file exists: $f"
    ERROR=1
  fi
 done

# 关键: 防止真实数据 CSV/Excel 被误传到仓库目录
# 规则: data/ 和 private/ 之外, 不应该有 *.csv/.xlsx/.db 文件
# 例外: sample/ 下的模板和示例文件 (是仓库教学/工具用, 不是真实数据)
echo "Scanning for stray data files in repo (excluding data/ and private/)..."
STRAY=$(find . -maxdepth 3 \
  \( -name "*.csv" -o -name "*.xlsx" -o -name "*.db" -o -name "*.sqlite" \) \
  -not -path "./.git/*" \
  -not -path "./data/*" \
  -not -path "./private/*" \
  -not -path "./sample/*" \
  2>/dev/null || true)
if [[ -n "$STRAY" ]]; then
  echo "[ERROR] 发现疑似数据文件出现在仓库目录 (应放到 data/ 或 private/):"
  echo "$STRAY"
  echo ""
  echo "例外: sample/ 目录下的 *.csv/*.xlsx 是项目自带的模板/示例, 视为正常。"
  ERROR=1
fi

if [[ "$ERROR" -eq 1 ]]; then
  echo ""
  echo "请确保上述敏感路径/文件未提交到 Git，并且是本地测试用的。"
  echo "真实数据请放到 data/csv/ 或 private/ 下, 这两个目录已被 .gitignore 忽略。"
  exit 1
fi

echo "No obvious sensitive files found in repository paths."
