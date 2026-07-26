#!/usr/bin/env bash

set -euo pipefail

MODULE="${1:-all}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

print_check() {
  local ok="$1"
  local msg="$2"
  if [[ "$ok" -eq 0 ]]; then
    printf "[PASS] %s\n" "$msg"
  else
    printf "[WARN] %s\n" "$msg"
  fi
}

printf "Running review checks for module: %s\n" "$MODULE"

if [[ "$MODULE" == "all" || "$MODULE" == "docs" ]]; then
  if [[ -f "$ROOT_DIR/docs/AGENT_GUIDE.md" ]]; then
    print_check 0 "Found docs/AGENT_GUIDE.md"
  else
    print_check 1 "Missing docs/AGENT_GUIDE.md"
  fi
  if [[ -f "$ROOT_DIR/CONTRIBUTING.md" ]]; then
    print_check 0 "Found CONTRIBUTING.md"
  else
    print_check 1 "Missing CONTRIBUTING.md"
  fi
fi

if [[ "$MODULE" == "all" || "$MODULE" == "sql" ]]; then
  if [[ -f "$ROOT_DIR/sql/01_schema.sql" ]]; then
    print_check 0 "Found sql/01_schema.sql"
  else
    print_check 1 "Missing sql/01_schema.sql"
  fi
  if [[ -f "$ROOT_DIR/sql/02_seed_data.sql" ]]; then
    print_check 0 "Found sql/02_seed_data.sql"
  else
    print_check 1 "Missing sql/02_seed_data.sql"
  fi
  if [[ -f "$ROOT_DIR/sql/03_master_data.sql" ]]; then
    print_check 0 "Found sql/03_master_data.sql"
  else
    print_check 1 "Missing sql/03_master_data.sql"
  fi
fi

if [[ "$MODULE" == "all" || "$MODULE" == "scripts" ]]; then
  if [[ -x "$ROOT_DIR/scripts/launch-module-workflow.sh" ]]; then
    print_check 0 "launch-module-workflow.sh is executable"
  else
    print_check 1 "launch-module-workflow.sh is not executable"
  fi
  if [[ -x "$ROOT_DIR/scripts/run-review.sh" ]]; then
    print_check 0 "run-review.sh is executable"
  else
    print_check 1 "run-review.sh is not executable"
  fi
fi

printf "Review completed. Use scripts/launch-module-workflow.sh or scripts/run-review.sh for more details.\n"
