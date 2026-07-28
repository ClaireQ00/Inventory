#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Running CI checks..."

# 1. 文件清单 + Python 语法检查
bash scripts/run-review.sh all

# 2. 历史 sample/import_products.py 兼容性检查
if [[ -f sample/import_products.py ]]; then
  echo "- Checking Python syntax for sample/import_products.py"
  python3 -m py_compile sample/import_products.py
fi

# 3. 关键: 用临时演示数据跑端到端业务校验
# 不动 data/csv 下用户的真实数据, 而是临时生成假数据
echo "- Running end-to-end business validation with demo data..."
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
# 临时改 CSV_DIR, 让脚本读临时目录的数据
CSV_DIR="$TMPDIR" python3 - <<'PY' || { echo "CI FAIL: 端到端校验失败"; exit 1; }
import os, sys
sys.path.insert(0, 'tools')
# 1) 生成演示数据到临时目录
import make_demo_data
make_demo_data.CSV_DIR = os.environ['CSV_DIR']
make_demo_data.main()
PY

CSV_DIR="$TMPDIR" python3 tools/local_validator.py --csv-dir "$TMPDIR" || {
  echo "CI FAIL: 端到端业务校验失败"
  exit 1
}

echo "CI checks passed."
