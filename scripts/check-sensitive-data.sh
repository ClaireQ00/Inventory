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
fi
if [[ -d "$ROOT_DIR/private" ]]; then
  echo "[INFO] Local private directory exists: private/ (should not be committed)"
fi

# 检查常见未忽略敏感文件
find . -maxdepth 2 \( -name ".env" -o -name ".env.*" \) -print | while read -r f; do
  if [[ "$f" != "./.git" && "$f" != "" ]]; then
    echo "[WARN] Sensitive environment file exists: $f"
    ERROR=1
  fi
 done

if [[ "$ERROR" -eq 1 ]]; then
  echo ""
  echo "请确保上述敏感路径/文件未提交到 Git，并且是本地测试用的。"
  exit 1
fi

echo "No obvious sensitive files found in repository paths."
