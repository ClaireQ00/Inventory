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
  if git -C "$ROOT_DIR" check-ignore -q data/ 2>/dev/null || grep -Eq '^data/$' "$ROOT_DIR/.gitignore" 2>/dev/null; then
    echo "[OK]   data/ is properly gitignored"
  else
    echo "[ERROR] data/ is NOT gitignored, real data could leak!"
    ERROR=1
  fi
fi
if [[ -d "$ROOT_DIR/private" ]]; then
  echo "[INFO] Local private directory exists: private/ (should not be committed)"
  if git -C "$ROOT_DIR" check-ignore -q private/ 2>/dev/null || grep -Eq '^private/$' "$ROOT_DIR/.gitignore" 2>/dev/null; then
    echo "[OK]   private/ is properly gitignored"
  else
    echo "[ERROR] private/ is NOT gitignored, real data could leak!"
    ERROR=1
  fi
fi

# 检查常见未忽略敏感文件
while IFS= read -r f; do
  [[ "$f" == "./.git" || "$f" == "" ]] && continue
  rel="${f#./}"
  if git -C "$ROOT_DIR" check-ignore -q "$rel" 2>/dev/null; then
    echo "[OK]   $f exists but is gitignored (local config, won't be committed)"
  else
    echo "[ERROR] $f exists and is NOT gitignored, secrets could leak!"
    ERROR=1
  fi
done < <(find . -maxdepth 2 \( -name ".env" -o -name ".env.*" \) -print 2>/dev/null)

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

# [T2.7] 内容侧扫描: 在"会进仓库"的文件里找 11 位手机号 / 18 位身份证
# 排除: data/ private/ (gitignored, 真实数据本来就在这), sample/ (教学模板/示例)
echo ""
echo "Scanning committed file contents for real phone / ID numbers..."
CONTENT_HITS=0
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  case "$f" in
    sample/*|data/*|private/*) continue ;;
  esac
  if grep -HnEI '1[3-9][0-9]{9}|[1-9][0-9]{16}[0-9Xx]' "$f" 2>/dev/null; then
    echo "  ↑ 疑似真实手机号/身份证, 请人工确认是否示例假数据 (示例常用 1380000xxxx 格式)"
    CONTENT_HITS=1
  fi
done < <(git -C "$ROOT_DIR" ls-files -z --cached --others --exclude-standard | tr '\0' '\n')
if [[ "$CONTENT_HITS" -eq 1 ]]; then
  echo "[WARN] 仓库文件内容中发现疑似手机号/身份证 (见上), 如为真实数据请移入 data/ 或 private/ 并清除。"
fi

if [[ "$ERROR" -eq 1 ]]; then
  echo ""
  echo "请确保上述敏感路径/文件未提交到 Git，并且是本地测试用的。"
  echo "真实数据请放到 data/csv/ 或 private/ 下, 这两个目录已被 .gitignore 忽略。"
  exit 1
fi

echo "No obvious sensitive files found in repository paths."
