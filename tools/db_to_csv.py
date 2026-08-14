#!/usr/bin/env python3
# ============================================================
# MySQL → CSV 导出工具 (双轨同步的"回写"方向)
# ------------------------------------------------------------
# 背景: 项目铁律是 MySQL 与 data/csv/*.csv 双轨一致。
#   CSV → MySQL 有 scripts/load-csv-to-db.sh;
#   但录入端 (React/FastAPI) 和手工 SQL 写进 MySQL 的数据
#   不会自动回到 CSV —— 本工具补齐这个方向。
#
# 用法:
#   python3 tools/db_to_csv.py 表名 [表名...]   # 导出指定表
#   python3 tools/db_to_csv.py --all            # 导出所有已有 CSV 对应的表
#   python3 tools/db_to_csv.py --check          # 只对比行数差异, 不写文件
#
# 说明:
#   - 导出不带自增 id 列 (与现有 CSV 约定一致, id 由数据库分配)
#   - 行顺序按 id (即写入时间), 保证单据行序稳定
#   - 会整文件覆盖对应 CSV; 执行前请确认 MySQL 一侧是较新的数据
# ============================================================
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"

# 从 .env 读数据库配置 (与 db_writer.py 同一套环境变量)
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "inventory"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "inventory_db"),
    "charset": "utf8mb4",
}


def export_table(conn, table: str, write: bool = True) -> tuple[int, int]:
    """导出一张表, 返回 (DB行数, CSV现有行数)。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
            (DB_CONFIG["database"], table),
        )
        cols = [r[0] for r in cur.fetchall() if r[0] != "id"]
        if not cols:
            print(f"  ✗ {table}: 表不存在或无列")
            return (0, -1)
        cur.execute(f"SELECT `{ '`,`'.join(cols) }` FROM `{table}` ORDER BY id")
        rows = cur.fetchall()

    csv_path = CSV_DIR / f"{table}.csv"
    csv_rows = -1
    if csv_path.exists():
        with open(csv_path, newline="") as f:
            csv_rows = sum(1 for _ in csv.reader(f)) - 1

    if write:
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in rows:
                w.writerow(["" if v is None else v for v in row])
    return (len(rows), csv_rows)


def main() -> int:
    args = sys.argv[1:]
    check_only = "--check" in args
    tables = [a for a in args if not a.startswith("--")]
    if "--all" in args or not tables:
        # --all 或未指定表名: 覆盖所有已有 CSV 对应的表
        tables = sorted(p.stem for p in CSV_DIR.glob("*.csv"))
    if not tables:
        print("用法: python3 tools/db_to_csv.py [表名...] [--all] [--check]")
        return 1

    conn = pymysql.connect(**DB_CONFIG)
    try:
        changed = 0
        for t in tables:
            db_n, csv_n = export_table(conn, t, write=not check_only)
            flag = "✓ 一致" if db_n == csv_n else f"⚠ CSV原有 {csv_n} 行"
            if db_n != csv_n:
                changed += 1
            action = "对比" if check_only else "导出"
            print(f"  {action} {t}: DB {db_n} 行 ({flag})")
        print(f"\n完成: {len(tables)} 张表, {changed} 张有差异"
              + ("(仅对比未写入)" if check_only else ""))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
