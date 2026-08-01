#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T2.X 独立测试套件 (2026-07-31)

目的: 让 4 类"故意出错"的校验场景有真实代码覆盖, 但**不污染 demo 数据**
      (demo 必须 0 错误是铁律, 见 docs/TASKS.md T2.X)。

覆盖场景:
  1. 跨字段不一致(米重×长度 vs 单重, 偏差 >5%) -> WARN, 不阻止生成 (csv_to_sql.py)
  2. 手填派生列超容差(outer_diameter 偏 0.1mm) -> ERROR, 阻止生成 (csv_to_sql.py)
  3. 短装超 UCP600 ±5% 容差 -> ERROR + pending 贷记单挂账 >90 天 -> ERROR (local_validator.py)
  4. 跨月汇率缺失 -> ERROR (local_validator.py)

用法: python3 tests/run_tests.py
"""
import contextlib
import csv
import io
import os
import shutil
import sys
from datetime import datetime, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))
sys.path.insert(0, ROOT_DIR)

import csv_to_sql          # noqa: E402
import local_validator     # noqa: E402
import make_demo_data      # noqa: E402

FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")


# ---------------------------------------------------------------- 工具函数
def build_fixture(name):
    """用 demo 生成器造一套完整假数据, 放到 tests/fixtures/<name>/ (与 data/ 隔离)"""
    fixture_dir = os.path.join(FIXTURES_DIR, name)
    shutil.rmtree(fixture_dir, ignore_errors=True)
    os.makedirs(fixture_dir)
    make_demo_data.CSV_DIR = fixture_dir
    with contextlib.redirect_stdout(io.StringIO()):
        make_demo_data.main()
    return fixture_dir


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def build_db(fixture_dir, db_path):
    """按业务导入顺序把 CSV 灌进 SQLite, 返回连接"""
    conn = local_validator.setup_db(db_path)
    report = local_validator.ValidationReport()
    for filename, table in local_validator.IMPORT_ORDER:
        p = os.path.join(fixture_dir, filename)
        if os.path.exists(p):
            local_validator.load_csv_into_sqlite(conn, p, table, report)
    conn.commit()
    return conn


def run_validation(conn):
    report = local_validator.ValidationReport()
    local_validator.run_validation(conn, report)
    return report


def convert_products(csv_path, out_path):
    """跑 csv_to_sql 的 products 转换, 返回 (行数, 打印输出)"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        n = csv_to_sql.convert_csv_to_sql(csv_path, "products", out_path, "insert")
    return n, buf.getvalue()


# ---------------------------------------------------------------- 4 个用例
def test_cross_field_warn():
    """① 米重×长度/1000 vs 单重偏差 >5% -> WARN, 不阻止生成 SQL"""
    fixture = build_fixture("cross_field_warn")
    products_csv = os.path.join(fixture, "products.csv")
    rows = read_csv(products_csv)
    rules = csv_to_sql.DERIVED_RULES["products"]
    for i, r in enumerate(rows):
        ctx = {
            "product_category": r["product_category"],
            "inner_diameter": r["inner_diameter"],
            "thickness": r["thickness"],
        }
        if i == 0:
            # 第一行: 单重/米重各自离理论值 4% (在 5% 容差内, 不触发反向 ERROR),
            # 但两者互相反推偏差 8%+ (触发跨字段 WARN)。跨字段校验需要 length。
            ctx["length"] = "100"
            r["length"] = "100"
            r["weight"] = str(round(float(rules["weight"]["expr"](ctx)) * 1.04, 4))
            r["weight_per_meter"] = str(round(float(rules["weight_per_meter"]["expr"](ctx)) * 0.96, 4))
        else:
            # 其余行: 米重改成理论值。demo 原值本身离理论 10%+, 不修正会误触发反向 ERROR
            # (demo 平时走 SQLite 直载不经 csv_to_sql, 所以没暴露)。
            r["weight_per_meter"] = str(round(float(rules["weight_per_meter"]["expr"](ctx)), 3))
    write_csv(products_csv, rows)

    out_sql = os.path.join(fixture, "products_out.sql")
    n, output = convert_products(products_csv, out_sql)
    assert n > 0, "WARN 场景不应阻止生成 SQL"
    assert "[跨字段提醒]" in output, f"应打印[跨字段提醒], 实际输出:\n{output}"
    assert os.path.exists(out_sql), "WARN 场景应正常写出 SQL 文件"
    return "① 跨字段不一致 -> WARN (不阻止生成)"


def test_derived_reverse_error():
    """② 手填派生列 outer_diameter 偏 0.1mm (>容差 0.05) -> ERROR 阻止生成"""
    fixture = build_fixture("derived_error")
    products_csv = os.path.join(fixture, "products.csv")
    rows = read_csv(products_csv)
    # DEMO-M-001: inner=32, thickness=4.18 -> 应等于 32+4.18×2=40.36, 手填 40.26 偏 0.1
    rows[0]["outer_diameter"] = "40.26"
    write_csv(products_csv, rows)

    out_sql = os.path.join(fixture, "products_out.sql")
    n, output = convert_products(products_csv, out_sql)
    assert n == 0, "超容差应返回 0 (阻止生成)"
    assert "[阻止生成]" in output, f"应打印[阻止生成], 实际输出:\n{output}"
    assert not os.path.exists(out_sql), "失败时不应写出 SQL 文件"
    return "② 手填派生列超容差 -> ERROR (阻止生成)"


def test_short_shipment_and_credit_note():
    """③ 短装超 UCP600 ±5% -> ERROR; pending 贷记单挂账 >90 天 -> ERROR"""
    fixture = build_fixture("short_shipment")
    # 3a. 报关明细: 物料1 计划5 实发4 -> 偏差 20% > 5%
    sri = read_csv(os.path.join(fixture, "shipping_record_items.csv"))
    for r in sri:
        if r["material_id"] == "DEMO-M-001":
            r["actual_qty"] = "4"
            r["subtotal_usd"] = "2000.00"  # 4 × 500
    write_csv(os.path.join(fixture, "shipping_record_items.csv"), sri)
    # 3b. 贷记单: 挂一条 pending 的短装差异 (created_at 由 DB 默认生成, 测试里改成 95 天前)
    write_csv(os.path.join(fixture, "credit_notes.csv"), [{
        "id": "1", "cn_no": "CN20260726001", "shipping_no": "SH20260726001",
        "contract_no": "SC20260720001", "contract_item_no": "001",
        "material_id": "DEMO-M-001", "diff_qty": "1", "currency": "USD",
        "diff_amount": "71.168", "exchange_rate": "7.15", "diff_amount_cny": "508.85",
        "resolution": "pending", "resolved_at": "", "remark": "短装1件挂账",
    }])

    db_path = os.path.join(fixture, "validation.db")
    conn = build_db(fixture, db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE credit_notes SET created_at = datetime('now','-95 days') WHERE cn_no = ?",
        ("CN20260726001",),
    )
    conn.commit()
    report = run_validation(conn)
    summary = report.summary()
    assert any("违反 UCP600 容差" in e for e in report.errors), \
        f"应有短装 ERROR, 实际:\n{summary}"
    assert any("pending 已" in e and "> 90 天" in e for e in report.errors), \
        f"应有贷记单逾期 ERROR, 实际:\n{summary}"
    conn.close()
    return "③ 短装超容差 + 贷记单挂账超90天 -> 双 ERROR"


def test_missing_exchange_rate():
    """④ 外币业务存在但汇率只录到上月 -> ERROR (缺当月汇率)"""
    fixture = build_fixture("missing_exchange_rate")
    this_month_start = datetime.now().replace(day=1)
    first_prev_month = (this_month_start - timedelta(days=1)).replace(day=1)
    write_csv(os.path.join(fixture, "exchange_rates.csv"), [{
        "id": "1", "currency": "USD", "rate_to_cny": "7.15",
        "effective_date": first_prev_month.isoformat(),
        "source": "manual", "remark": "测试: 只录到上月",
    }])

    db_path = os.path.join(fixture, "validation.db")
    conn = build_db(fixture, db_path)
    report = run_validation(conn)
    summary = report.summary()
    assert any("早于本月1号" in e for e in report.errors), \
        f"应有汇率缺失 ERROR, 实际:\n{summary}"
    conn.close()
    return "④ 跨月汇率缺失 -> ERROR"


# ---------------------------------------------------------------- 运行入口
def main():
    tests = [
        test_cross_field_warn,
        test_derived_reverse_error,
        test_short_shipment_and_credit_note,
        test_missing_exchange_rate,
    ]
    print("=" * 60)
    print("T2.X 独立测试套件 (故意触发错误, 不污染 demo)")
    print("=" * 60)
    failed = 0
    for fn in tests:
        try:
            label = fn()
            print(f"  [PASS] {label}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [FAIL] {fn.__name__}: 异常 {type(e).__name__}: {e}")
    print("=" * 60)
    if failed:
        print(f"结果: ✗ {failed} 个用例失败")
        sys.exit(1)
    print(f"结果: ✓ 全部通过 ({len(tests)} 个用例)")


if __name__ == "__main__":
    main()
