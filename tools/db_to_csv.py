#!/usr/bin/env python3
# ============================================================
# MySQL → CSV 导出工具 (双轨同步的"回写"方向)
# ------------------------------------------------------------
# 背景: 项目铁律是 MySQL 与 data/csv/*.csv 双轨一致。
#   CSV → MySQL 有 scripts/load-csv-to-db.sh;
#   但录入端 (React/FastAPI) 和手工 SQL 写进 MySQL 的数据
#   不会自动回到 CSV —— 本工具补齐这个方向。
#
# 用法 (在宿主机项目根目录跑):
#   python3 tools/db_to_csv.py 表名 [表名...]   # 导出指定表
#   python3 tools/db_to_csv.py --all            # 导出所有已有 CSV 对应的表
#   python3 tools/db_to_csv.py --check          # 只对比行数差异, 不写文件
#
# 说明:
#   - 零第三方依赖: 通过 docker compose exec 调容器里的 mysql 客户端,
#     不装 pymysql, 不怕 Python 环境重建
#   - 导出不带自增 id 列 (与现有 CSV 约定一致, id 由数据库分配)
#   - 行顺序按 id (即写入时间), 保证单据行序稳定
#   - 会整文件覆盖对应 CSV; 执行前请确认 MySQL 一侧是较新的数据
# ============================================================
from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"

# 从 .env 读数据库配置 (与宿主机其他脚本同一套约定)
_env = {}
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            _env[k.strip()] = v.strip()

DB_NAME = os.getenv("MYSQL_DATABASE") or _env.get("MYSQL_DATABASE", "inventory_db")
DB_USER = os.getenv("MYSQL_USER") or _env.get("MYSQL_USER", "inventory")
DB_PASS = os.getenv("MYSQL_PASSWORD") or _env.get("MYSQL_PASSWORD", "")


def mysql_query(sql: str) -> list[list[str]]:
    """通过容器内 mysql 客户端跑查询, 返回行列表 (batch 模式, 转义已还原)。"""
    r = subprocess.run(
        ["docker", "compose", "exec", "-T", "db",
         "mysql", f"-u{DB_USER}", f"-p{DB_PASS}", DB_NAME, "--batch", "-e", sql],
        capture_output=True, text=True, cwd=ROOT,
    )
    if r.returncode != 0:
        raise RuntimeError(f"mysql 执行失败: {r.stderr.strip()}")
    rows = []
    for line in r.stdout.splitlines():
        # batch 模式: 字段内换行/制表符被转义成 \n \t, 这里还原
        fields = [
            f.replace("\\n", "\n").replace("\\t", "\t").replace("\\0", "\0").replace("\\\\", "\\")
            for f in line.split("\t")
        ]
        rows.append(fields)
    return rows


def export_table(table: str, write: bool = True) -> tuple[int, int]:
    """导出一张表, 返回 (DB行数, CSV现有行数)。"""
    col_rows = mysql_query(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA='{DB_NAME}' AND TABLE_NAME='{table}' "
        "ORDER BY ORDINAL_POSITION"
    )
    cols = [r[0] for r in col_rows if r and r[0] != "id" and r[0] != "COLUMN_NAME"]
    if not cols:
        print(f"  ✗ {table}: 表不存在或无列")
        return (0, -1)

    data = mysql_query(f"SELECT `{ '`,`'.join(cols) }` FROM `{table}` ORDER BY id")
    # 第一行是表头
    rows = data[1:] if data else []

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
                # mysql batch 模式 NULL 输出为字面 "NULL"
                w.writerow(["" if v == "NULL" else v for v in row])
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

    changed = 0
    for t in tables:
        db_n, csv_n = export_table(t, write=not check_only)
        flag = "✓ 一致" if db_n == csv_n else f"⚠ CSV原有 {csv_n} 行"
        if db_n != csv_n:
            changed += 1
        action = "对比" if check_only else "导出"
        print(f"  {action} {t}: DB {db_n} 行 ({flag})")
    print(f"\n完成: {len(tables)} 张表, {changed} 张有差异"
          + ("(仅对比未写入)" if check_only else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
