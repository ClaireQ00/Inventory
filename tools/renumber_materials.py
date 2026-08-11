#!/usr/bin/env python3
"""物料重编码 (2026-08-11 老板规则): M-NNNNN 纯流水 → M-{客户编码}-{3位流水}

规则:
- 客户编码用现行 4 位数字码 (Q0025 而非 Q025); M-Q025-xxx 旧式一并改
- 同客户下按旧编码数字升序分配 001/002/...
- 8039.0 → D8039 (老板: 8039 先A后D, D 现管); 9129.0 与孤儿行不动 (待认领)
- MySQL 与 data/csv/*.csv 用同一映射, 单事务关 FK 检查改 10 张引用表
- 映射表留痕 data/logs/material_remap_YYYYMMDD.csv
"""
import csv
import os
import re
import sys
from datetime import date
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"
LOG_DIR = ROOT / "data" / "logs"

# 引用 products.material_id 的 (csv文件, 列名); stock_logs 无 csv 只改 DB
REF_TABLES = [
    "purchase_order_items", "sales_contract_items", "inventory", "stock_logs",
    "delivery_order_items", "shipping_record_items", "credit_notes",
    "quotation_items", "stock_in_items", "stock_out_items",
]
GARBAGE_MAP = {"8039.0": "D8039"}  # 9129.0 归属待老板确认, 不动


def normalize_cc(cc: str) -> str:
    """机械归一: 全角→半角 + 大写 (w9152→W9152, Ｄ1077→D1077)"""
    return cc.translate(str.maketrans(
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ０１２３４５６７８９",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")).upper()


def get_conn():
    pw = [l.split("=", 1)[1].strip() for l in open(ROOT / ".env") if l.startswith("MYSQL_PASSWORD=")][0]
    return pymysql.connect(host="127.0.0.1", port=3306, user="inventory", password=pw,
                           database="inventory_db", cursorclass=pymysql.cursors.DictCursor)


def build_mapping(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT material_id, customer_code FROM products")
        rows = cur.fetchall()
        cur.execute("SELECT code FROM customers")
        valid = {r["code"] for r in cur.fetchall()}

    def sort_key(mid):
        m = re.search(r"(\d+)(?!.*\d)", mid)
        return int(m.group(1)) if m else 0

    groups: dict[str, list[str]] = {}
    skipped = []
    for r in rows:
        mid, cc = r["material_id"], (r["customer_code"] or "").strip()
        cc = GARBAGE_MAP.get(cc, normalize_cc(cc))
        if not cc or cc not in valid:
            skipped.append((mid, r["customer_code"]))
            continue
        groups.setdefault(cc, []).append(mid)

    mapping = {}
    cc_fix = {}  # material_id → 归一后的 customer_code (原值是小写/全角/垃圾码时)
    for cc, mids in groups.items():
        for i, old in enumerate(sorted(mids, key=sort_key), start=1):
            new = f"M-{cc}-{i:03d}"
            if old != new:
                mapping[old] = new
    for r in rows:
        raw = (r["customer_code"] or "").strip()
        cc = GARBAGE_MAP.get(raw, normalize_cc(raw))
        if raw != cc and cc in valid:
            cc_fix[r["material_id"]] = cc
    return mapping, skipped, cc_fix


def apply_mysql(conn, mapping, cc_fix):
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        try:
            for mid, cc in cc_fix.items():
                cur.execute("UPDATE products SET customer_code=%s WHERE material_id=%s", (cc, mid))
            for old, new in mapping.items():
                cur.execute("UPDATE products SET material_id=%s WHERE material_id=%s", (new, old))
                for t in REF_TABLES:
                    cur.execute(f"UPDATE {t} SET material_id=%s WHERE material_id=%s", (new, old))
        finally:
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()


def apply_csv(mapping, cc_fix):
    changed_files = []
    for csv_path in sorted(CSV_DIR.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if not rows:
            continue
        header = rows[0]
        changed = 0
        # products.csv 先同步 customer_code 归一 (要在 material_id 改号之前, 按旧码索引)
        if csv_path.name == "products.csv" and "customer_code" in header:
            midx, cidx = header.index("material_id"), header.index("customer_code")
            for row in rows[1:]:
                if len(row) > midx and row[midx] in cc_fix:
                    row[cidx] = cc_fix[row[midx]]
                    changed += 1
        if "material_id" in header:
            idx = header.index("material_id")
            for row in rows[1:]:
                if len(row) > idx and row[idx] in mapping:
                    row[idx] = mapping[row[idx]]
                    changed += 1
        if changed:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
            changed_files.append((csv_path.name, changed))
    return changed_files


def main():
    dry = "--dry-run" in sys.argv
    conn = get_conn()
    mapping, skipped, cc_fix = build_mapping(conn)
    print(f"映射 {len(mapping)} 行 (跳过得认领: {len(skipped)}; customer_code 归一: {len(cc_fix)})")
    for mid, cc in skipped:
        print(f"  [跳过] {mid} (customer_code={cc!r})")
    if dry:
        for old, new in list(mapping.items())[:5]:
            print(f"  样例 {old} → {new}")
        return

    apply_mysql(conn, mapping, cc_fix)
    print("MySQL 已更新 (products + 10 张引用表 + customer_code 归一)")
    for name, n in apply_csv(mapping, cc_fix):
        print(f"CSV 同步: {name} ({n} 行)")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / f"material_remap_{date.today():%Y%m%d}.csv"
    with open(log, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["old_material_id", "new_material_id"])
        w.writerows(sorted(mapping.items()))
    print(f"映射留痕: {log}")


if __name__ == "__main__":
    main()
