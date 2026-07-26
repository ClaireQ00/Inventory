#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Running CI checks..."

bash scripts/run-review.sh all

if [[ -f sample/import_products.py ]]; then
  echo "- Checking Python syntax for sample/import_products.py"
  python3 -m py_compile sample/import_products.py
fi

echo "CI checks passed."
