#!/usr/bin/env bash
# ============================================================
# 模板 ↔ Schema 字段同步检查 (R7 三处同步原则的补强)
# ------------------------------------------------------------
# 背景:
#   项目铁律 R7 说改 schema 必须 sync 三处 (schema/SQLite 镜像/DERIVED_RULES),
#   但还有第 4 处容易被忘: sample/templates/*_template.csv 的表头字段。
#   2026-07-30 真实数据试用时就踩到: customers 表加了 brand_name/
#   company_profiles/billing_profiles 3 个字段, 但模板没同步, 导致字段错位。
#
# 作用:
#   对比 sql/01_schema.sql 的 CREATE TABLE 字段 vs 模板 CSV 的表头,
#   发现不一致立刻报警。可以加到 CI 或 run_local_validation.sh 里。
#
# 用法:
#   bash scripts/check-template-schema-sync.sh
#   返回 0 = 全部一致; 返回 1 = 发现不一致
# ============================================================

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

exec python3 - <<'PYEOF'
import csv
import os
import re
import sys

SCHEMA = "sql/01_schema.sql"
TEMPLATE_DIR = "sample/templates"
# 系统字段豁免: 这些是 DB 自动维护的, 模板故意不含, 漏了不算 bug
SYS_FIELDS = {"id", "created_at", "updated_at", "deleted_at"}

if not os.path.exists(SCHEMA):
    print(f"[FATAL] 找不到 {SCHEMA}", file=sys.stderr)
    sys.exit(2)
if not os.path.exists(TEMPLATE_DIR):
    print(f"[FATAL] 找不到 {TEMPLATE_DIR}", file=sys.stderr)
    sys.exit(2)

print("检查模板表头 ↔ schema 字段一致性...")
print()

# ---- 1. 解析 schema, 提取每张表的字段名 ----
schema_text = open(SCHEMA, encoding="utf-8").read()
schema_fields = {}  # {table_name: [field1, field2, ...]}

# CREATE TABLE 表名 ( 字段定义 ) ENGINE
for m in re.finditer(r'CREATE TABLE\s+`?(\w+)`?\s*\((.*?)\)\s*ENGINE', schema_text, re.S):
    table = m.group(1)
    body = m.group(2)
    fields = []
    for raw_line in body.split('\n'):
        line = raw_line.strip().rstrip(',')
        if not line: continue
        if line.startswith('--') or line.startswith('#'): continue
        # 跳过约束行
        if re.match(r'^(PRIMARY\s+KEY|UNIQUE\s+KEY|KEY|INDEX|FOREIGN\s+KEY|CONSTRAINT|CHECK)\b', line, re.I):
            continue
        # 字段行: 可选反引号 + 字段名 + 空格 + 类型
        fm = re.match(r'^`?(\w+)`?\s+(INT|VARCHAR|DECIMAL|TEXT|DATE|DATETIME|TIMESTAMP|ENUM|TINYINT|BIGINT|CHAR|FLOAT|DOUBLE|JSON|BLOB|MEDIUMTEXT|LONGTEXT|SMALLINT)', line, re.I)
        if fm:
            fields.append(fm.group(1))
    if fields:
        schema_fields[table] = fields

# ---- 2. 对比每个模板 ----
mismatches = 0
checked = 0
GREEN = '\033[0;32m'
YELLOW = '\033[0;33m'
RED = '\033[0;31m'
NC = '\033[0m'

for table, sf_list in schema_fields.items():
    template = f"{TEMPLATE_DIR}/{table}_template.csv"
    if not os.path.exists(template):
        continue   # 有些表故意没模板 (audit_logs 等)

    checked += 1
    with open(template, encoding="utf-8") as f:
        tmpl_fields = next(csv.reader(f))

    # 过滤系统字段
    schema_set = {f for f in sf_list if f not in SYS_FIELDS}
    tmpl_set = set(tmpl_fields)

    missing = schema_set - tmpl_set     # schema 有但模板没
    extra = tmpl_set - schema_set       # 模板有但 schema 没

    if missing or extra:
        print(f"{RED}[不一致] {table}{NC}")
        if missing:
            print(f"  模板缺字段: {YELLOW}{', '.join(sorted(missing))}{NC}")
        if extra:
            print(f"  模板多余字段(可能已删?): {YELLOW}{', '.join(sorted(extra))}{NC}")
        mismatches += 1

print()
print(f"已检查 {checked} 个模板, 不一致 {mismatches} 个")
if mismatches > 0:
    print(f"{RED}✗ 发现不一致! 修改 schema 后必须同步 sample/templates/<表名>_template.csv{NC}")
    print("   详见 docs/IMPORT_TEMPLATES.md (R7 三处同步原则补强为四处)")
    sys.exit(1)
else:
    print(f"{GREEN}✓ 全部一致{NC}")
    sys.exit(0)
PYEOF
