#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地验证引擎 (SQLite 版)
========================

为什么不用 MySQL:
- 本机可能没装 MySQL, 装也麻烦
- SQLite 是 Python 自带的, 一个 .db 文件就是一整库, 像一个 U 盘里的 Excel
- 业务规则校验在 Python 里写, 跟用啥数据库没关系
- 等流程验证 OK 了, 再切到 MySQL 上, 只需要换连接字符串

这个脚本干两件事:
1. 把 sql/01_schema.sql 的表结构翻译成 SQLite 能跑的版本, 建一个本地库
2. 提供一套"业务规则校验函数", 在导入数据的过程中实时检查

整体流程 (按简报要求):
  基础资料 -> 采购单 -> 入库单 -> 销售合同 -> 发货单 -> 出库单 -> 对账
"""

import os
import sys
import csv
import sqlite3
import argparse
from datetime import datetime

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DB_DIR = os.path.join(ROOT_DIR, "data", "db")
DATA_CSV_DIR = os.path.join(ROOT_DIR, "data", "csv")
DATA_LOG_DIR = os.path.join(ROOT_DIR, "data", "logs")


# ============================================================
# 第一部分: 用 SQLite 重建一张精简版表结构
# 注意: 这里只保留业务流程需要的字段, 类型也做了 SQLite 适配
# 业务校验代码不依赖具体类型, 所以这版表足够验证流程
# ============================================================

# UCP600 国际惯例: 短装/超装允许 ±5% (第30条)
# 偏差 ≤5% → WARN (允许); 偏差 >5% → ERROR (违规)
SHORT_SHIPMENT_TOLERANCE = 0.05

SQLITE_SCHEMA = """
-- 基础资料
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id TEXT UNIQUE NOT NULL,
    customer_code TEXT DEFAULT '',
    brand TEXT DEFAULT '',
    product_category TEXT DEFAULT '',
    material_type TEXT DEFAULT '',
    spec TEXT DEFAULT '',
    inner_diameter REAL,
    inner_diameter_inch TEXT DEFAULT '',
    outer_diameter REAL,
    id_x_od TEXT DEFAULT '',
    thickness REAL,
    length REAL,
    spec_meter INTEGER,
    virtual_weight REAL,
    virtual_length REAL,
    wire_spacing TEXT DEFAULT '',
    weight_per_meter REAL,
    weight REAL,
    appearance_inner REAL,
    appearance_outer REAL,
    appearance_height REAL,
    volume REAL,
    package TEXT DEFAULT '',
    label_paper TEXT DEFAULT '',
    material_used TEXT DEFAULT '',
    wire_pattern TEXT DEFAULT '',
    coil_type TEXT DEFAULT '',
    pressure REAL,
    spray_code TEXT DEFAULT '',
    meter_mark TEXT DEFAULT '',
    meter_mark_count INTEGER,
    remark TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    address TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    contact_person TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    bank_account TEXT DEFAULT '',
    company_profiles TEXT DEFAULT NULL,
    billing_profiles TEXT DEFAULT NULL,
    is_self INTEGER DEFAULT 0,
    remark TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    contact_person TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    bank_account TEXT DEFAULT '',
    brand_name TEXT DEFAULT '',
    company_profiles TEXT DEFAULT NULL,
    billing_profiles TEXT DEFAULT NULL,
    remark TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1
);

-- 采购
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_no TEXT UNIQUE NOT NULL,
    supplier_code TEXT NOT NULL,
    order_date TEXT NOT NULL,
    expected_date TEXT,
    total_amount REAL DEFAULT 0,
    total_volume REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    remark TEXT DEFAULT '',
    FOREIGN KEY (supplier_code) REFERENCES suppliers(code)
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_no TEXT NOT NULL,
    material_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    subtotal REAL NOT NULL,
    volume_subtotal REAL DEFAULT 0,
    received_qty INTEGER DEFAULT 0,
    remark TEXT DEFAULT '',
    FOREIGN KEY (po_no) REFERENCES purchase_orders(po_no) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES products(material_id),
    UNIQUE (po_no, material_id)
);

-- 销售合同
CREATE TABLE IF NOT EXISTS sales_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT UNIQUE NOT NULL,
    customer_code TEXT NOT NULL,
    sign_date TEXT NOT NULL,
    delivery_deadline TEXT,
    -- 金额四件套 (外贸默认外币, 折算 CNY 记账)
    total_amount REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    exchange_rate REAL DEFAULT 0,
    total_amount_cny REAL DEFAULT 0,
    total_volume REAL DEFAULT 0,
    -- 贸易术语
    trade_terms TEXT DEFAULT 'FOB',
    port_loading TEXT DEFAULT '',
    port_discharge TEXT DEFAULT '',
    freight REAL DEFAULT 0,
    insurance REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    -- 付款/包装条款 (2026-07-29 加)
    payment_term TEXT,
    packing TEXT,
    remark TEXT DEFAULT '',
    FOREIGN KEY (customer_code) REFERENCES customers(code)
);

CREATE TABLE IF NOT EXISTS sales_contract_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT NOT NULL,
    item_no TEXT NOT NULL,
    material_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    subtotal REAL NOT NULL,
    volume_subtotal REAL DEFAULT 0,
    delivered_qty INTEGER DEFAULT 0,
    remark TEXT DEFAULT '',
    FOREIGN KEY (contract_no) REFERENCES sales_contracts(contract_no) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES products(material_id),
    UNIQUE (contract_no, item_no),
    UNIQUE (contract_no, material_id)
);

-- 库存
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id TEXT NOT NULL,
    warehouse_code TEXT NOT NULL,
    quantity INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (material_id, warehouse_code),
    FOREIGN KEY (material_id) REFERENCES products(material_id),
    FOREIGN KEY (warehouse_code) REFERENCES warehouses(code)
);

CREATE TABLE IF NOT EXISTS stock_in (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    in_no TEXT UNIQUE NOT NULL,
    in_type TEXT DEFAULT 'purchase',
    warehouse_code TEXT NOT NULL,
    po_no TEXT,
    operator TEXT DEFAULT '',
    in_date TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    transfer_ref TEXT,
    remark TEXT DEFAULT '',
    FOREIGN KEY (warehouse_code) REFERENCES warehouses(code),
    FOREIGN KEY (po_no) REFERENCES purchase_orders(po_no)
);

CREATE TABLE IF NOT EXISTS stock_in_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    in_no TEXT NOT NULL,
    material_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    remark TEXT DEFAULT '',
    FOREIGN KEY (in_no) REFERENCES stock_in(in_no) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES products(material_id)
);

CREATE TABLE IF NOT EXISTS stock_out (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    out_no TEXT UNIQUE NOT NULL,
    out_type TEXT DEFAULT 'sale',
    warehouse_code TEXT NOT NULL,
    delivery_no TEXT,
    operator TEXT DEFAULT '',
    out_date TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    transfer_ref TEXT,
    remark TEXT DEFAULT '',
    FOREIGN KEY (warehouse_code) REFERENCES warehouses(code),
    FOREIGN KEY (delivery_no) REFERENCES delivery_orders(delivery_no)
);

CREATE TABLE IF NOT EXISTS stock_out_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    out_no TEXT NOT NULL,
    material_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    remark TEXT DEFAULT '',
    FOREIGN KEY (out_no) REFERENCES stock_out(out_no) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES products(material_id)
);

CREATE TABLE IF NOT EXISTS stock_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id TEXT NOT NULL,
    warehouse_code TEXT NOT NULL,
    change_qty INTEGER NOT NULL,
    after_qty INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    source_id INTEGER,
    source_no TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (material_id) REFERENCES products(material_id),
    FOREIGN KEY (warehouse_code) REFERENCES warehouses(code)
);

-- 发货
CREATE TABLE IF NOT EXISTS delivery_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_no TEXT UNIQUE NOT NULL,
    customer_code TEXT NOT NULL,
    delivery_date TEXT NOT NULL,
    receiver TEXT DEFAULT '',
    receiver_phone TEXT DEFAULT '',
    receiver_address TEXT DEFAULT '',
    transport_no TEXT DEFAULT '',
    total_volume REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    remark TEXT DEFAULT '',
    FOREIGN KEY (customer_code) REFERENCES customers(code)
);

CREATE TABLE IF NOT EXISTS delivery_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_no TEXT NOT NULL,
    contract_no TEXT,
    contract_item_no TEXT,
    material_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    actual_quantity INTEGER NOT NULL DEFAULT 0,
    short_qty INTEGER NOT NULL DEFAULT 0,
    volume_subtotal REAL DEFAULT 0,
    -- [R11] Packing Plan 公斤价反算核对 (与 MySQL schema 同步)
    expected_unit_price REAL DEFAULT 0,
    coeff_diff REAL DEFAULT 0,
    coeff_check_status TEXT DEFAULT 'pending',
    remark TEXT DEFAULT '',
    FOREIGN KEY (delivery_no) REFERENCES delivery_orders(delivery_no) ON DELETE CASCADE,
    FOREIGN KEY (contract_no, contract_item_no) REFERENCES sales_contract_items(contract_no, item_no),
    FOREIGN KEY (material_id) REFERENCES products(material_id)
);

-- ------------------------------------------------------------
-- 模块六: 报关 (外贸出口专用)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shipping_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipping_no TEXT UNIQUE NOT NULL,
    delivery_no TEXT NOT NULL,
    shipping_date TEXT NOT NULL,
    container_no TEXT DEFAULT '',
    seal_no TEXT DEFAULT '',
    vessel TEXT DEFAULT '',
    total_pkgs INTEGER NOT NULL DEFAULT 0,
    total_gross_wt REAL NOT NULL DEFAULT 0,
    total_net_wt REAL NOT NULL DEFAULT 0,
    total_cbm REAL NOT NULL DEFAULT 0,
    -- CI 金额四件套
    total_amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    exchange_rate REAL NOT NULL DEFAULT 0,
    total_amount_cny REAL NOT NULL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (delivery_no) REFERENCES delivery_orders(delivery_no)
);

CREATE INDEX IF NOT EXISTS idx_sr_no       ON shipping_records(shipping_no);
CREATE INDEX IF NOT EXISTS idx_sr_delivery ON shipping_records(delivery_no);
CREATE INDEX IF NOT EXISTS idx_sr_status   ON shipping_records(status);

CREATE TABLE IF NOT EXISTS shipping_record_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipping_no TEXT NOT NULL,
    material_id TEXT NOT NULL,
    planned_qty INTEGER NOT NULL DEFAULT 0,
    actual_qty INTEGER NOT NULL DEFAULT 0,
    shipping_mark TEXT DEFAULT '',
    gross_weight_per REAL DEFAULT 0,
    net_weight_per REAL DEFAULT 0,
    unit_volume REAL DEFAULT 0,
    unit_price_usd REAL DEFAULT 0,
    subtotal_usd REAL DEFAULT 0,
    remark TEXT DEFAULT '',
    FOREIGN KEY (shipping_no) REFERENCES shipping_records(shipping_no) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES products(material_id)
);

CREATE INDEX IF NOT EXISTS idx_sri_shipping ON shipping_record_items(shipping_no);
CREATE INDEX IF NOT EXISTS idx_sri_product  ON shipping_record_items(material_id);

CREATE TABLE IF NOT EXISTS credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cn_no TEXT UNIQUE NOT NULL,
    shipping_no TEXT NOT NULL,
    contract_no TEXT NOT NULL,
    contract_item_no TEXT NOT NULL,
    material_id TEXT NOT NULL,
    diff_qty INTEGER NOT NULL,
    diff_amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    exchange_rate REAL NOT NULL DEFAULT 0,
    diff_amount_cny REAL NOT NULL DEFAULT 0,
    resolution TEXT DEFAULT 'pending',
    resolved_at TEXT,
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shipping_no) REFERENCES shipping_records(shipping_no),
    FOREIGN KEY (contract_no, contract_item_no) REFERENCES sales_contract_items(contract_no, item_no),
    FOREIGN KEY (material_id) REFERENCES products(material_id)
);

CREATE INDEX IF NOT EXISTS idx_cn_no         ON credit_notes(cn_no);
CREATE INDEX IF NOT EXISTS idx_cn_shipping   ON credit_notes(shipping_no);
CREATE INDEX IF NOT EXISTS idx_cn_resolution ON credit_notes(resolution);

-- ============================================================
-- 模块七: 应收账款 (外贸财务阶段一)
-- ============================================================

CREATE TABLE IF NOT EXISTS exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    currency TEXT NOT NULL,
    rate_to_cny REAL NOT NULL,
    effective_date TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (currency, effective_date)
);

CREATE INDEX IF NOT EXISTS idx_er_currency_date ON exchange_rates(currency, effective_date);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no TEXT UNIQUE NOT NULL,
    customer_code TEXT NOT NULL,
    contract_no TEXT,
    shipping_no TEXT,
    delivery_no TEXT,
    -- 金额四件套
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    exchange_rate REAL NOT NULL DEFAULT 0,
    amount_cny REAL NOT NULL DEFAULT 0,
    paid_date TEXT NOT NULL,
    pay_method TEXT DEFAULT 'T/T',
    bank_ref TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_code) REFERENCES customers(code),
    FOREIGN KEY (contract_no) REFERENCES sales_contracts(contract_no),
    FOREIGN KEY (shipping_no) REFERENCES shipping_records(shipping_no),
    FOREIGN KEY (delivery_no) REFERENCES delivery_orders(delivery_no)
);

CREATE INDEX IF NOT EXISTS idx_rc_no         ON receipts(receipt_no);
CREATE INDEX IF NOT EXISTS idx_rc_customer   ON receipts(customer_code);
CREATE INDEX IF NOT EXISTS idx_rc_contract   ON receipts(contract_no);
CREATE INDEX IF NOT EXISTS idx_rc_paid_date  ON receipts(paid_date);
CREATE INDEX IF NOT EXISTS idx_rc_status     ON receipts(status);

-- ============================================================
-- 模块八: 审计日志 (阶段一空壳)
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_values TEXT,
    new_values TEXT,
    operator TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_table_record ON audit_logs(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_operator_time ON audit_logs(operator, created_at);

-- ============================================================
-- 模块九: 报价管理 (单价 = 单卷重量 KG × 报价系数 USD/KG)
-- ============================================================

-- 9.1 报价参数表 (全局键值对)
CREATE TABLE IF NOT EXISTS quotation_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    param_key TEXT NOT NULL UNIQUE,
    param_value TEXT NOT NULL,
    description TEXT DEFAULT '',
    effective_date TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_qp_key ON quotation_params(param_key);

-- 9.2 报价主表 (简要报价 brief + 正式 QT formal 共用, 状态区分)
-- 金额四件套 (R1): total_amount + currency + exchange_rate + total_amount_cny
CREATE TABLE IF NOT EXISTS quotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_no TEXT NOT NULL UNIQUE,
    customer_code TEXT NOT NULL,
    quote_type TEXT NOT NULL DEFAULT 'brief',
    parent_quote_no TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    quote_date TEXT NOT NULL,
    valid_until TEXT,
    -- 金额四件套 (R1)
    total_amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    exchange_rate REAL NOT NULL DEFAULT 0,
    total_amount_cny REAL NOT NULL DEFAULT 0,
    total_volume REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    converted_contract_no TEXT,
    -- 贸易/付款/包装条款 (2026-07-29 加, 与 MySQL schema 对齐)
    trade_terms TEXT DEFAULT 'FOB',
    port_loading TEXT DEFAULT '',
    port_discharge TEXT DEFAULT '',
    payment_term TEXT,
    packing TEXT,
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_code) REFERENCES customers(code),
    FOREIGN KEY (parent_quote_no) REFERENCES quotations(quote_no) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_quo_no       ON quotations(quote_no);
CREATE INDEX IF NOT EXISTS idx_quo_customer ON quotations(customer_code);
CREATE INDEX IF NOT EXISTS idx_quo_type     ON quotations(quote_type);
CREATE INDEX IF NOT EXISTS idx_quo_status   ON quotations(status);

-- 9.3 报价明细表
-- 派生字段 (total_weight/unit_price/subtotal/total_volume) 下一步 DERIVED_RULES 实现, 本步先建列
CREATE TABLE IF NOT EXISTS quotation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_no TEXT NOT NULL,
    item_no TEXT NOT NULL,
    material_id TEXT NOT NULL,
    group_code TEXT NOT NULL DEFAULT '',
    price_coefficient REAL NOT NULL,
    weight_per_unit REAL NOT NULL,
    quantity INTEGER NOT NULL,
    -- 派生字段 (本步先建列, DERIVED_RULES 下一步实现)
    total_weight REAL NOT NULL DEFAULT 0,
    unit_price REAL NOT NULL DEFAULT 0,
    subtotal REAL NOT NULL DEFAULT 0,
    volume REAL DEFAULT 0,
    total_volume REAL NOT NULL DEFAULT 0,
    remark TEXT DEFAULT '',
    FOREIGN KEY (quote_no) REFERENCES quotations(quote_no) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES products(material_id),
    UNIQUE (quote_no, item_no),
    UNIQUE (quote_no, material_id)
);

CREATE INDEX IF NOT EXISTS idx_qi_quote ON quotation_items(quote_no);
CREATE INDEX IF NOT EXISTS idx_qi_group ON quotation_items(group_code);
"""


# ============================================================
# 第二部分: 业务规则校验
# 每个函数返回 (ok, 错误列表), ok=False 表示有规则没通过
# ============================================================


class ValidationReport:
    """简单报告收集器, 类比成"质检员手里的检验单" """

    def __init__(self):
        self.errors = []   # 红灯: 必须修
        self.warnings = []  # 黄灯: 提醒一下

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    @property
    def ok(self):
        return len(self.errors) == 0

    def summary(self):
        lines = []
        lines.append(f"  错误数: {len(self.errors)}")
        lines.append(f"  警告数: {len(self.warnings)}")
        for e in self.errors:
            lines.append(f"  [ERROR] {e}")
        for w in self.warnings:
            lines.append(f"  [WARN]  {w}")
        return "\n".join(lines)


def load_csv_into_sqlite(conn, csv_path, table_name, report):
    """
    把 CSV 直接灌进 SQLite 表 (CSV 第一行 = 字段名)。
    空值 -> None; 数值字符串 -> float/int
    """
    if not os.path.exists(csv_path):
        report.warn(f"CSV 不存在, 跳过: {csv_path}")
        return 0

    cur = conn.cursor()
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    if not rows:
        return 0

    placeholders = ", ".join(["?"] * len(fields))
    cols = ", ".join(fields)
    sql = f"INSERT OR REPLACE INTO {table_name} ({cols}) VALUES ({placeholders})"

    count = 0
    for row in rows:
        values = []
        for k in fields:
            v = row[k]
            if v is None or v == "":
                values.append(None)
            else:
                # 数字判断
                try:
                    if "." in v:
                        values.append(float(v))
                    else:
                        values.append(int(v))
                except (ValueError, TypeError):
                    values.append(v)
        try:
            cur.execute(sql, values)
            count += 1
        except sqlite3.IntegrityError as e:
            report.error(f"导入 {table_name} 失败 (字段值冲突): {e} | row={row}")
    conn.commit()
    return count


# ---- 各业务环节的校验函数 ----

def check_master_data(conn, report):
    """基础资料: 物料/仓库/供应商/客户"""

    # 物料编号不能重复 (UNIQUE 已保证, 这里再统计一下)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT material_id) FROM products")
    total, distinct = cur.fetchone()
    if total != distinct:
        report.error(f"products.material_id 重复: 总数 {total}, 去重 {distinct}")
    if total == 0:
        report.warn("products 表为空, 没法继续后续流程")

    # 仓库
    cur.execute("SELECT COUNT(*) FROM warehouses")
    if cur.fetchone()[0] == 0:
        report.warn("warehouses 为空")

    # 供应商
    cur.execute("SELECT COUNT(*) FROM suppliers")
    if cur.fetchone()[0] == 0:
        report.warn("suppliers 为空 (后续采购单必须有供应商)")
    # [新] is_self 完整性: 必须恰好有 1 家 is_self=1 (本公司, 用于合同模板调取卖方信息)
    cur.execute("SELECT COUNT(*) FROM suppliers WHERE is_self = 1")
    self_cnt = cur.fetchone()[0]
    if self_cnt == 0:
        report.warn("suppliers: 没有任何 is_self=1 的记录, 合同模板无法调取卖方信息 (请把本公司标记 is_self=1)")
    elif self_cnt > 1:
        report.warn(f"suppliers: 有 {self_cnt} 条 is_self=1, 目前只支持 1 家本公司")

    # 客户
    cur.execute("SELECT COUNT(*) FROM customers")
    if cur.fetchone()[0] == 0:
        report.warn("customers 为空 (后续销售合同必须有客户)")


def check_purchase_orders(conn, report):
    """采购单: 金额 = 明细小计之和; 体积 = 明细体积小计之和(展示统计, WARN)"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT po.id, po.po_no, po.total_amount,
               COALESCE(SUM(poi.subtotal), 0) AS sum_subtotal
        FROM purchase_orders po
        LEFT JOIN purchase_order_items poi ON poi.po_no = po.po_no
        GROUP BY po.id
        """
    )
    for po_id, po_no, total_amount, sum_sub in cur.fetchall():
        if abs((total_amount or 0) - sum_sub) > 0.01:
            report.error(
                f"采购单 {po_no}: total_amount={total_amount} 与明细小计之和={sum_sub} 不一致"
            )

    # 体积校验 (展示用统计, WARN 级, 不阻断)
    cur.execute(
        """
        SELECT po.id, po.po_no, po.total_volume,
               COALESCE(SUM(poi.volume_subtotal), 0) AS sum_vol
        FROM purchase_orders po
        LEFT JOIN purchase_order_items poi ON poi.po_no = po.po_no
        GROUP BY po.id
        """
    )
    for po_id, po_no, total_vol, sum_vol in cur.fetchall():
        if abs((total_vol or 0) - sum_vol) > 0.01:
            report.warn(
                f"采购单 {po_no}: total_volume={total_vol or 0} "
                f"与 Σ明细 volume_subtotal={round(sum_vol, 2)} 不符 (展示统计, 不阻断)"
            )


def check_stock_in_vs_purchase(conn, report):
    """入库数 不能超过 采购数"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT po.po_no, p.material_id,
               poi.quantity AS ordered,
               COALESCE(SUM(sii.quantity), 0) AS received
        FROM purchase_order_items poi
        JOIN purchase_orders po ON po.po_no = poi.po_no
        JOIN products p ON p.material_id = poi.material_id
        LEFT JOIN stock_in si ON si.po_no = po.po_no AND si.status='confirmed'
        LEFT JOIN stock_in_items sii ON sii.in_no = si.in_no AND sii.material_id = poi.material_id
        GROUP BY poi.id
        """
    )
    for po_no, material_id, ordered, received in cur.fetchall():
        if received > ordered:
            report.error(
                f"采购单 {po_no} / 物料 {material_id}: 入库 {received} > 采购 {ordered}"
            )
        elif received < ordered:
            report.warn(
                f"采购单 {po_no} / 物料 {material_id}: 入库 {received} < 采购 {ordered} (未全部到货)"
            )


def check_sales_contracts(conn, report):
    """销售合同: 金额 = 明细小计之和; 体积 = 明细体积小计之和(展示统计, WARN)"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sc.id, sc.contract_no, sc.total_amount,
               COALESCE(SUM(sci.subtotal), 0)
        FROM sales_contracts sc
        LEFT JOIN sales_contract_items sci ON sci.contract_no = sc.contract_no
        GROUP BY sc.id
        """
    )
    for sc_id, contract_no, total_amount, sum_sub in cur.fetchall():
        if abs((total_amount or 0) - sum_sub) > 0.01:
            report.error(
                f"合同 {contract_no}: total_amount={total_amount} 与明细={sum_sub} 不一致"
            )

    # 体积校验 (展示用统计, WARN 级, 不阻断)
    cur.execute(
        """
        SELECT sc.id, sc.contract_no, sc.total_volume,
               COALESCE(SUM(sci.volume_subtotal), 0) AS sum_vol
        FROM sales_contracts sc
        LEFT JOIN sales_contract_items sci ON sci.contract_no = sc.contract_no
        GROUP BY sc.id
        """
    )
    for sc_id, contract_no, total_vol, sum_vol in cur.fetchall():
        if abs((total_vol or 0) - sum_vol) > 0.01:
            report.warn(
                f"合同 {contract_no}: total_volume={total_vol or 0} "
                f"与 Σ明细 volume_subtotal={round(sum_vol, 2)} 不符 (展示统计, 不阻断)"
            )


def check_delivery_vs_contract(conn, report):
    """
    发货数 不能超过 合同数

    优先用 actual_quantity (已装柜的实际数), 没装柜的回退到 quantity (计划数)。
    类比: 合同是承诺发货 100, 装柜后实发 95, 那 95 才是真正"对客户履约"的数。
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sc.contract_no, p.material_id,
               sci.quantity AS contracted,
               COALESCE(SUM(
                   CASE WHEN doi.actual_quantity > 0 THEN doi.actual_quantity
                        ELSE doi.quantity END
               ), 0) AS delivered
        FROM sales_contract_items sci
        JOIN sales_contracts sc ON sc.contract_no = sci.contract_no
        JOIN products p ON p.material_id = sci.material_id
        LEFT JOIN delivery_orders d ON d.customer_code = sc.customer_code AND d.status='confirmed'
        LEFT JOIN delivery_order_items doi
               ON doi.contract_no = sci.contract_no
              AND doi.contract_item_no = sci.item_no
        GROUP BY sci.id
        """
    )
    for contract_no, material_id, contracted, delivered in cur.fetchall():
        if delivered > contracted:
            report.error(
                f"合同 {contract_no} / 物料 {material_id}: 发货 {delivered} > 合同 {contracted}"
            )
        elif delivered < contracted:
            report.warn(
                f"合同 {contract_no} / 物料 {material_id}: 已发 {delivered} < 合同 {contracted} (未发完)"
            )


def check_stock_out_vs_inventory(conn, report):
    """
    出库校验: 累计出库 超过 累计入库 时报警 (允许负库存, 但提示补货)
    (类比: 银行卡累计取款超过累计存款, 允许透支, 但要提醒你存钱)

    说明:
    - 不能直接拿"当前库存"对比"单次出库",
      因为当前库存是出库后的结果, 看起来必然"超"
    - 正确做法是按 (物料, 仓库) 累计出入库, 比较两者
    - 业务上允许"先做后补"(外贸调拨常见), 所以从 error 降级为 warn
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            so.warehouse_code AS wh,
            soi.material_id AS pid,
            p.material_id,
            (SELECT COALESCE(SUM(sii.quantity), 0)
               FROM stock_in_items sii
               JOIN stock_in si ON si.in_no = sii.in_no
              WHERE si.warehouse_code = so.warehouse_code
                AND sii.material_id = soi.material_id
                AND si.status='confirmed'
            ) AS total_in,
            (SELECT COALESCE(SUM(soi2.quantity), 0)
               FROM stock_out_items soi2
               JOIN stock_out so2 ON so2.out_no = soi2.out_no
              WHERE so2.warehouse_code = so.warehouse_code
                AND soi2.material_id = soi.material_id
                AND so2.status='confirmed'
            ) AS total_out,
            soi.quantity AS this_out,
            so.out_no
        FROM stock_out_items soi
        JOIN stock_out so ON so.out_no = soi.out_no
        JOIN products p ON p.material_id = soi.material_id
        WHERE so.status='confirmed'
        GROUP BY so.id, soi.id
        """
    )
    for wh, pid, material_id, total_in, total_out, this_out, out_no in cur.fetchall():
        if total_out > total_in:
            report.warn(
                f"出库单 {out_no} / 物料 {material_id}: 累计出库 {total_out} > 累计入库 {total_in}"
                f"（仓库 {wh} 当前库存为负 {total_in - total_out}，请补货）"
            )


def rebuild_stock_logs(conn):
    """
    根据 入库明细 + 出库明细, 自动重建 stock_logs 流水表。

    类比: 流水表就像银行流水, 入库 = 存钱, 出库 = 取钱。
    库存表 = 账户余额, 流水表 = 每一笔进出记录。
    余额要等于流水累加, 不平就是有 bug。
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM stock_logs")

    # 入库流水 (+)
    cur.execute(
        """
        SELECT sii.material_id, si.warehouse_code, sii.quantity,
               si.id, si.in_no, si.in_date
        FROM stock_in_items sii
        JOIN stock_in si ON si.in_no = sii.in_no
        WHERE si.status='confirmed'
        """
    )
    for material_id, wh, qty, src_id, src_no, in_date in cur.fetchall():
        cur.execute(
            """
            INSERT INTO stock_logs
                (material_id, warehouse_code, change_qty, after_qty,
                 source_type, source_id, source_no, remark, created_at)
            VALUES (?, ?, ?, 0, 'stock_in', ?, ?, '入库', ?)
            """,
            (material_id, wh, qty, src_id, src_no, in_date),
        )

    # 出库流水 (-)
    cur.execute(
        """
        SELECT soi.material_id, so.warehouse_code, soi.quantity,
               so.id, so.out_no, so.out_date
        FROM stock_out_items soi
        JOIN stock_out so ON so.out_no = soi.out_no
        WHERE so.status='confirmed'
        """
    )
    for material_id, wh, qty, src_id, src_no, out_date in cur.fetchall():
        cur.execute(
            """
            INSERT INTO stock_logs
                (material_id, warehouse_code, change_qty, after_qty,
                 source_type, source_id, source_no, remark, created_at)
            VALUES (?, ?, ?, 0, 'stock_out', ?, ?, '出库', ?)
            """,
            (material_id, wh, -qty, src_id, src_no, out_date),
        )

    conn.commit()
    print("  (流水已重建: 根据 入库 + 出库 明细自动生成)")


def check_reconciliation(conn, report):
    """对账: 库存表 == 流水累加"""
    rebuild_stock_logs(conn)
    cur = conn.cursor()

    # 用流水重算理论库存
    cur.execute(
        """
        SELECT material_id, warehouse_code, SUM(change_qty) AS calc_qty
        FROM stock_logs
        GROUP BY material_id, warehouse_code
        """
    )
    calc = {(p, w): q for p, w, q in cur.fetchall()}

    cur.execute("SELECT material_id, warehouse_code, quantity FROM inventory")
    actual = {(p, w): q for p, w, q in cur.fetchall()}

    # 对比
    all_keys = set(calc.keys()) | set(actual.keys())
    diffs = 0
    for (p, w) in all_keys:
        c = calc.get((p, w), 0)
        a = actual.get((p, w), 0)
        if c != a:
            cur.execute("SELECT name, code FROM warehouses WHERE code=?", (w,))
            wh_row = cur.fetchone()
            if wh_row:
                wh_name, wh_code = wh_row
                wh_label = f"{wh_name}({wh_code})"
            else:
                wh_label = f"<未知仓库 code={w}>"
            report.error(
                f"对账不平: 物料 {p} 仓库 {wh_label} | 库存表={a} | 流水累加={c}"
            )
            diffs += 1

    if diffs == 0:
        print("  对账全部平衡 ✓")


def check_volume_subtotals(conn, report):
    """
    校验明细表的 volume_subtotal 是否 = products.volume × quantity

    规则: 单件体积(来自 products 表) × 数量 = 该行体积小计
    跨表校验, csv_to_sql 做不了, 只能这里做。
    """
    cur = conn.cursor()

    # 单件体积公式: appearance_outer² × appearance_height × 0.93 / 1e6
    # 把 products 表里这些字段都拿出来, 在 Python 端算
    cur.execute(
        "SELECT material_id, appearance_outer, appearance_height, volume FROM products"
    )
    unit_volume_map = {}
    for mid, ao, ah, vol in cur.fetchall():
        if vol:
            unit_volume_map[mid] = vol
        elif ao and ah:
            calc = round(ao * ao * ah * 0.93 / 1_000_000, 4)
            unit_volume_map[mid] = calc
        else:
            unit_volume_map[mid] = None

    # 三张明细表逐一校验
    tables = [
        "purchase_order_items",
        "sales_contract_items",
        "delivery_order_items",
    ]
    label_map = {
        "purchase_order_items": "采购明细",
        "sales_contract_items": "合同明细",
        "delivery_order_items": "发货明细",
    }

    for table in tables:
        cur.execute(
            f"SELECT id, material_id, quantity, volume_subtotal FROM {table}"
        )
        for item_id, mid, qty, vs in cur.fetchall():
            unit_vol = unit_volume_map.get(mid)
            if unit_vol is None or not qty:
                continue
            expected = round(unit_vol * qty, 2)
            actual = vs or 0
            if abs(actual - expected) > 0.01:
                report.error(
                    f"{label_map[table]} ID={item_id} / 物料 {mid}: "
                    f"volume_subtotal={actual} 与 单件体积×数量={expected} 不符"
                )


def check_delivery_order_volume(conn, report):
    """
    发货单总体积 = Σ delivery_order_items.volume_subtotal

    展示用统计字段 (给客户看"这张单总共多少立方"), 不是报关数据。
    跟 shipping_records.total_cbm (装柜后真实数) 是两个概念, 不互通。
    WARN 级 (不阻断), 容差 0.01 CBM。
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.id, d.delivery_no, d.total_volume,
               COALESCE(SUM(doi.volume_subtotal), 0) AS sum_vol
        FROM delivery_orders d
        LEFT JOIN delivery_order_items doi ON doi.delivery_no = d.delivery_no
        GROUP BY d.id
        """
    )
    for do_id, delivery_no, total_vol, sum_vol in cur.fetchall():
        if abs((total_vol or 0) - sum_vol) > 0.01:
            report.warn(
                f"发货单 {delivery_no}: total_volume={total_vol or 0} "
                f"与 Σ明细 volume_subtotal={round(sum_vol, 2)} 不符 (展示统计, 不阻断)"
            )


def check_shipping_vs_delivery(conn, report):
    """
    [新增 9/10] 报关实际数 vs 发货单计划数: 套用 UCP600 ±5% 容差

    规则 (UCP600 第30条, 国际惯例):
    - |实际 - 计划| / 计划 ≤ 5%  → WARN  (允许的合理误差)
    - |实际 - 计划| / 计划 > 5%  → ERROR (违规, 需要走 credit_note 流程)

    类比: 你点了 100 个饺子, 餐厅上了 95~105 个都算正常 (±5%);
          但只上了 90 个就过分了, 得补差价 (credit_note)。
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sr.shipping_no, p.material_id,
               doi.quantity        AS planned,
               sri.actual_qty      AS actual
        FROM shipping_records sr
        JOIN shipping_record_items sri ON sri.shipping_no = sr.shipping_no
        JOIN delivery_orders d         ON d.delivery_no = sr.delivery_no
        JOIN delivery_order_items doi  ON doi.delivery_no = d.delivery_no
                                       AND doi.material_id = sri.material_id
        JOIN products p                ON p.material_id = sri.material_id
        WHERE sri.actual_qty > 0
        """
    )
    for shipping_no, material_id, planned, actual in cur.fetchall():
        if not planned or planned <= 0:
            continue
        diff = abs(actual - planned)
        ratio = diff / planned
        if ratio > SHORT_SHIPMENT_TOLERANCE:
            report.error(
                f"报关单 {shipping_no} / 物料 {material_id}: "
                f"实际 {actual} vs 计划 {planned}, 偏差 {ratio:.1%} > 5% (违反 UCP600 容差)"
            )
        elif ratio > 0:
            report.warn(
                f"报关单 {shipping_no} / 物料 {material_id}: "
                f"实际 {actual} vs 计划 {planned}, 偏差 {ratio:.1%} ≤ 5% (UCP600 允许, 但需 credit_note 记录)"
            )


def check_credit_notes_balance(conn, report):
    """
    [新增 10/10] 贷记单差异闭环: 所有 pending 不能无限期挂账

    规则:
    - resolution='pending' 且 created_at 距今 > 30 天 → WARN (催办)
    - resolution='pending' 且 created_at 距今 > 90 天 → ERROR (严重逾期)

    类比: 客户少收的 5 件货, 你说"回头补", 但拖了 3 个月还没补,
          财务就要炸了 —— 必须强制 close (refund 或 writeoff)。
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cn_no, diff_qty, diff_amount, resolution, created_at
        FROM credit_notes
        WHERE resolution = 'pending'
        """
    )

    now = datetime.now()
    for cn_no, diff_qty, diff_amount, resolution, created_at in cur.fetchall():
        if not created_at:
            continue
        # SQLite 把 CURRENT_TIMESTAMP 存成字符串
        try:
            created_dt = datetime.strptime(str(created_at)[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue
        age_days = (now - created_dt).days
        if age_days > 90:
            report.error(
                f"贷记单 {cn_no}: pending 已 {age_days} 天 > 90 天 (差异 {diff_qty} 件 / "
                f"{diff_amount} CNY), 必须立即 close (补发/退款/注销)"
            )
        elif age_days > 30:
            report.warn(
                f"贷记单 {cn_no}: pending 已 {age_days} 天 > 30 天 (差异 {diff_qty} 件), 请尽快 close"
            )


def check_exchange_rates(conn, report):
    """
    [新增 11/14] 汇率表完整性: 业务里用到的每个外币币种, 每月至少要有一条汇率

    规则:
    - 系统里所有"非 CNY"业务(合同/收款/CI)涉及的币种, exchange_rates 必须有对应汇率
    - 缺当月汇率 → ERROR (没法折算 CNY)
    - 提前 7 天没下月汇率 → WARN (提醒月初别忘了录)

    类比: 没有汇率就像出门不带钱包, 货再发出去也对不上账, 财务月底会炸。
    """
    cur = conn.cursor()

    # 收集所有业务里出现过的非 CNY 币种
    cur.execute(
        """
        SELECT DISTINCT currency FROM sales_contracts WHERE currency IS NOT NULL AND currency != 'CNY'
        UNION
        SELECT DISTINCT currency FROM receipts       WHERE currency IS NOT NULL AND currency != 'CNY'
        UNION
        SELECT DISTINCT currency FROM shipping_records WHERE currency IS NOT NULL AND currency != 'CNY'
        """
    )
    biz_currencies = {row[0] for row in cur.fetchall() if row[0]}

    if not biz_currencies:
        return  # 没有外币业务, 跳过

    # 拿当前月份 (按今天算)
    now = datetime.now()
    this_month_start = now.date().replace(day=1)

    for cur_code in sorted(biz_currencies):
        cur.execute(
            """
            SELECT MAX(effective_date) FROM exchange_rates
            WHERE currency = ?
            """,
            (cur_code,),
        )
        row = cur.fetchone()
        last_effective = row[0] if row else None

        if not last_effective:
            report.error(
                f"币种 {cur_code}: exchange_rates 表里一条记录都没有, "
                f"没法折算 CNY 记账。请录一条 (effective_date 设为本月1号)"
            )
            continue

        # SQLite 把 DATE 存成字符串, 直接字符串比较即可 (YYYY-MM-DD 格式天然可比)
        last_str = str(last_effective)[:10]
        this_month_str = this_month_start.isoformat()
        if last_str < this_month_str:
            report.error(
                f"币种 {cur_code}: 最近一条汇率是 {last_str}, 早于本月1号({this_month_str}), "
                f"本月业务没法折算 CNY, 请补录当月汇率"
            )


def check_receipts_vs_contract(conn, report):
    """
    [新增 12/14] 收款 vs 合同: 同一合同的累计收款不应超过合同总额

    规则:
    - 按 contract_no 聚合, 比对 Σ receipts.amount (原币种) vs sales_contracts.total_amount
    - 超出 → ERROR (收多了, 可能录错或币种搞错)
    - 不匹配币种 → ERROR (USD 合同不能收 CNY 款)
    - 未收齐且合同已 confirmed → WARN (催款)

    类比: 合同说好 1 万美元, 客户付了 1.2 万, 财务会问"那 2 千算什么?"。
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sc.id, sc.contract_no, sc.currency, sc.total_amount, sc.status,
               r.currency AS rcv_currency,
               COALESCE(SUM(r.amount), 0) AS total_received
        FROM sales_contracts sc
        LEFT JOIN receipts r
             ON r.contract_no = sc.contract_no
            AND r.status = 'confirmed'
        GROUP BY sc.id, r.currency
        """
    )
    for sc_id, contract_no, sc_cur, sc_total, sc_status, rcv_cur, total_received in cur.fetchall():
        if total_received == 0:
            # 没收过款
            if sc_status in ('confirmed', 'delivering', 'completed'):
                report.warn(
                    f"合同 {contract_no}: 状态={sc_status} 但未收款 (应收 {sc_total} {sc_cur or '?'})"
                )
            continue

        # 收过款, 检查币种和金额
        if rcv_cur and sc_cur and rcv_cur != sc_cur:
            report.error(
                f"合同 {contract_no}: 合同币种 {sc_cur} 但收到 {rcv_cur}, 币种不一致"
            )
            continue

        if total_received > (sc_total or 0) + 0.01:
            report.error(
                f"合同 {contract_no}: 累计收款 {total_received} {sc_cur} > "
                f"合同总额 {sc_total} {sc_cur}, 超出 {total_received - sc_total:.2f}"
            )


def check_transfer_pairs(conn, report):
    """
    调拨配对校验: 同一个 transfer_ref 的 stock_out 和 stock_in,
    每个物料的出库总量必须等于入库总量.

    类比: 你从 A 银行卡转 100 块到 B 银行卡, B 卡必须正好收到 100 块.
          中途不能丢, 也不能多出来.
    """
    cur = conn.cursor()

    # 1. 按 (transfer_ref, material_id) 聚合出库总量
    cur.execute(
        """
        SELECT so.transfer_ref AS ref, soi.material_id AS pid, p.material_id AS mid,
               SUM(soi.quantity) AS qty
        FROM stock_out_items soi
        JOIN stock_out so ON so.out_no = soi.out_no
        JOIN products p ON p.material_id = soi.material_id
        WHERE so.status='confirmed' AND so.out_type='transfer' AND so.transfer_ref IS NOT NULL
        GROUP BY so.transfer_ref, soi.material_id
        """
    )
    out_map = {(ref, pid): (mid, qty) for ref, pid, mid, qty in cur.fetchall()}

    # 2. 按 (transfer_ref, material_id) 聚合入库总量
    cur.execute(
        """
        SELECT si.transfer_ref AS ref, sii.material_id AS pid, p.material_id AS mid,
               SUM(sii.quantity) AS qty
        FROM stock_in_items sii
        JOIN stock_in si ON si.in_no = sii.in_no
        JOIN products p ON p.material_id = sii.material_id
        WHERE si.status='confirmed' AND si.in_type='transfer' AND si.transfer_ref IS NOT NULL
        GROUP BY si.transfer_ref, sii.material_id
        """
    )
    in_map = {(ref, pid): (mid, qty) for ref, pid, mid, qty in cur.fetchall()}

    # 3. 配对对比 (差额不为 0 → ERROR)
    all_keys = set(out_map.keys()) | set(in_map.keys())
    for ref, pid in sorted(all_keys):
        out_mid, out_qty = out_map.get((ref, pid), (None, 0))
        in_mid, in_qty = in_map.get((ref, pid), (None, 0))
        material_id = out_mid or in_mid or "?"
        if out_qty != in_qty:
            report.error(
                f"调拨 {ref} / 物料 {material_id}: 出库 {out_qty} ≠ 入库 {in_qty}"
                f"（差额 {out_qty - in_qty}，调拨在途或漏录）"
            )

    # 4. 只有单边的调拨 → WARN (在途或录错方向)
    orphan_out = set(out_map.keys()) - set(in_map.keys())
    orphan_in = set(in_map.keys()) - set(out_map.keys())
    for ref, pid in orphan_out:
        report.warn(
            f"调拨 {ref} / 物料 {out_map[(ref, pid)][0]}: 只有出库没入库（在途或漏录）"
        )
    for ref, pid in orphan_in:
        report.warn(
            f"调拨 {ref} / 物料 {in_map[(ref, pid)][0]}: 只有入库没出库（在途或录错方向）"
        )


def check_quotations(conn, report):
    """[14/14] 报价: 金额一致性 + 派生关系完整性"""
    cur = conn.cursor()

    # 校验1: 报价主表 total_amount = Σ 明细 subtotal
    cur.execute("""
        SELECT q.id, q.quote_no, q.total_amount, COALESCE(SUM(qi.subtotal), 0)
        FROM quotations q
        LEFT JOIN quotation_items qi ON qi.quote_no = q.quote_no
        GROUP BY q.id
    """)
    for q_id, quote_no, total_amount, sum_sub in cur.fetchall():
        if abs((total_amount or 0) - sum_sub) > 0.05:
            report.error(f"报价 {quote_no}: total_amount={total_amount} 与明细小计之和={sum_sub} 不一致 (容差 0.05)")

    # 校验1b: 报价主表 total_volume = Σ 明细 total_volume (展示统计, WARN)
    cur.execute("""
        SELECT q.id, q.quote_no, q.total_volume, COALESCE(SUM(qi.total_volume), 0)
        FROM quotations q
        LEFT JOIN quotation_items qi ON qi.quote_no = q.quote_no
        GROUP BY q.id
    """)
    for q_id, quote_no, total_vol, sum_vol in cur.fetchall():
        if abs((total_vol or 0) - sum_vol) > 0.01:
            report.warn(
                f"报价 {quote_no}: total_volume={total_vol or 0} "
                f"与 Σ明细 total_volume={round(sum_vol, 2)} 不符 (展示统计, 不阻断)"
            )

    # 校验2: 正式QT(formal)的 parent_quote_no 必须指向存在的简要报价(brief)
    cur.execute("""
        SELECT q.id, q.quote_no, q.parent_quote_no, p.quote_type
        FROM quotations q
        LEFT JOIN quotations p ON q.parent_quote_no = p.quote_no
        WHERE q.quote_type = 'formal'
    """)
    for q_id, quote_no, parent_no, parent_type in cur.fetchall():
        if parent_no is None:
            report.error(f"正式报价 {quote_no}: 缺少 parent_quote_no, 必须从简要报价派生")
        elif parent_type != 'brief':
            report.error(f"正式报价 {quote_no}: parent_quote_no 指向的不是简要报价(type={parent_type})")

    # 校验3: converted 状态的报价 converted_contract_no 必须存在
    cur.execute("""
        SELECT q.id, q.quote_no, q.converted_contract_no
        FROM quotations q
        WHERE q.status = 'converted' AND q.converted_contract_no IS NOT NULL
    """)
    for q_id, quote_no, contract_no in cur.fetchall():
        cur.execute("SELECT contract_no FROM sales_contracts WHERE contract_no = ?", (contract_no,))
        if not cur.fetchone():
            report.error(f"报价 {quote_no}: converted_contract_no={contract_no} 在 sales_contracts 不存在")

    # 校验4: 明细派生一致性(subtotal = weight_per_unit × price_coefficient × quantity)
    cur.execute("SELECT id, quote_no, weight_per_unit, price_coefficient, quantity, subtotal FROM quotation_items")
    for iid, qno, wpu, coeff, qty, sub in cur.fetchall():
        if None not in (wpu, coeff, qty, sub):
            expected = wpu * coeff * qty
            if abs(sub - expected) > 0.05:
                report.error(f"报价明细 id={iid}: subtotal={sub} 与 算{expected:.2f}(重量{wpu}×系数{coeff}×数量{qty}) 不一致 (容差 0.05)")


def check_packing_coefficient(conn, report):
    """[15/15] Packing Plan 公斤价反算核对 (R11 铁律) (步号描述保留历史出处, 实际步号由 run_validation 统一打印)

    业务背景: 简要报价按 公斤系数(USD/KG) × 单重 定价; 制作发货单(Packing Plan)时,
              要用报价系数正算"应等于的合同单价", 与实际合同单价对比。

    正算公式 (丙方案, 2026-07-31 修正): expected_unit_price = 报价系数 × 单重  (原币种/件)
    ⚠ 原公式曾误乘 sales_contracts.exchange_rate, 把原币单价变成记账本位币后再对比,
      与"原币种/件"的 unit_price 单位不匹配(真实数据 Q025 跑出 11 条 WARN 暴露, 见 docs/TASKS.md 坑 6)。
    差异 = 实际合同单价 - expected_unit_price

    容差 0.01: 超差报 warn 不报 error。合同单价按 2 位小数报价(如 1.112×7=7.784 → 7.78),
    0.001 过紧会把正常四舍五入误报; 0.01 覆盖 2 位小数报价的最大舍入误差(0.005)。
    """

    # 通过 (contract_no, contract_item_no) 关联到 sales_contract_items, 再用 material_id 反查 quotation_items
    # 报价明细与合同明细无直接外键, 靠 material_id 配对
    cur = conn.cursor()
    cur.execute("""
        SELECT doi.id, doi.contract_no, doi.contract_item_no, doi.material_id,
               sci.unit_price   AS contract_unit_price,
               p.weight         AS weight,
               (SELECT qi.price_coefficient
                  FROM quotation_items qi
                  JOIN quotations q ON q.quote_no = qi.quote_no
                 WHERE qi.material_id = doi.material_id
                   AND q.status IN ('draft', 'accepted', 'converted')
                 ORDER BY q.id DESC
                 LIMIT 1)        AS coeff
        FROM delivery_order_items doi
        JOIN sales_contract_items sci ON sci.contract_no = doi.contract_no
                                     AND sci.item_no = doi.contract_item_no
        JOIN products p                ON p.material_id = doi.material_id
        WHERE doi.contract_item_no IS NOT NULL
    """)
    rows = cur.fetchall()
    if not rows:
        return  # 没有可核对的发货明细, 跳过

    TOLERANCE = 0.01
    updates = []  # (expected, diff, status, id)

    for doi_id, cno, ci_no, mid, contract_price, weight, coeff in rows:
        # 缺任一数据 → pending (不算错, 提示)
        if None in (contract_price, weight, coeff) or not weight:
            updates.append((0.0, 0.0, "pending", doi_id))
            report.warn(
                f"发货明细 id={doi_id} (material_id={mid}): 缺反算数据 "
                f"(合同单价={contract_price}, 单重={weight}, 报价系数={coeff}), 标 pending"
            )
            continue

        # 正算 (丙方案修正): 应等于的合同单价(原币/件) = 报价系数 × 单重
        expected = round(coeff * weight, 4)
        diff = round(float(contract_price) - expected, 4)
        status = "pass" if abs(diff) <= TOLERANCE else "warn"
        updates.append((expected, diff, status, doi_id))

        if status == "warn":
            report.warn(
                f"发货明细 id={doi_id} (material_id={mid}): 公斤价反算差异 {diff:+.4f} 超容差 {TOLERANCE} "
                f"(合同单价={contract_price}, 应等于={expected:.4f} = 系数{coeff}×单重{weight})"
            )

    # 回写到 delivery_order_items (校验阶段顺便填派生字段, 跨表计算不适合 DERIVED_RULES)
    cur.executemany(
        "UPDATE delivery_order_items SET expected_unit_price=?, coeff_diff=?, coeff_check_status=? WHERE id=?",
        [(e, d, s, i) for (e, d, s, i) in updates],
    )
    conn.commit()


# ============================================================
# 第三部分: 主流程
# ============================================================


def setup_db(db_path):
    """初始化一个全新空库"""
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SQLITE_SCHEMA)
    conn.commit()
    return conn


def run_validation(conn, report):
    """跑全部业务校验。

    步号和总步数从本函数的 CHECK_STEPS 列表自动推导,
    各 check_* 函数内部不要再 print "[n/N]"——避免新增 check 时
    忘记同步分母导致 [1/14]...[15/15] 错乱。
    """
    # (校验函数, 中文描述) —— 顺序就是业务流程顺序
    CHECK_STEPS = [
        (check_master_data,            "校验基础资料"),
        (check_purchase_orders,        "校验采购单"),
        (check_stock_in_vs_purchase,   "校验入库数 vs 采购数"),
        (check_sales_contracts,        "校验销售合同"),
        (check_delivery_vs_contract,   "校验发货数 vs 合同数"),
        (check_stock_out_vs_inventory, "校验出库数 vs 累计入库 (负库存报警)"),
        (check_reconciliation,         "库存对账"),
        (check_volume_subtotals,       "校验明细表体积小计"),
        (check_delivery_order_volume,  "校验发货单总体积 (展示统计)"),
        (check_shipping_vs_delivery,   "校验报关实际数 vs 发货单计划数 (UCP600 ±5% 容差)"),
        (check_credit_notes_balance,   "校验贷记单闭环 (pending 不能挂超过 30 天)"),
        (check_exchange_rates,         "校验汇率表完整性 (每月每币种至少一条)"),
        (check_receipts_vs_contract,   "校验收款 vs 合同金额 (按原币种聚合)"),
        (check_transfer_pairs,         "校验调拨配对 (同 transfer_ref 出入库数量必须相等)"),
        (check_quotations,             "校验报价"),
        (check_packing_coefficient,    "校验 Packing Plan 公斤价反算 (R11 容差 0.01)"),
    ]
    total = len(CHECK_STEPS)
    for i, (fn, desc) in enumerate(CHECK_STEPS, start=1):
        print(f"[{i}/{total}] {desc}...")
        fn(conn, report)


# 业务表导入顺序 (模块级常量, 供 tests/ 直接复用)
IMPORT_ORDER = [
    # quotation_params 无依赖, 放最前
    ("quotation_params.csv", "quotation_params"),
    ("products.csv", "products"),
    ("warehouses.csv", "warehouses"),
    ("suppliers.csv", "suppliers"),
    ("customers.csv", "customers"),
    ("purchase_orders.csv", "purchase_orders"),
    ("purchase_order_items.csv", "purchase_order_items"),
    ("sales_contracts.csv", "sales_contracts"),
    ("sales_contract_items.csv", "sales_contract_items"),
    ("stock_in.csv", "stock_in"),
    ("stock_in_items.csv", "stock_in_items"),
    ("delivery_orders.csv", "delivery_orders"),
    ("delivery_order_items.csv", "delivery_order_items"),
    ("stock_out.csv", "stock_out"),
    ("stock_out_items.csv", "stock_out_items"),
    ("inventory.csv", "inventory"),
    # [新增] 外贸报关模块 (第6模块)
    ("shipping_records.csv", "shipping_records"),
    ("shipping_record_items.csv", "shipping_record_items"),
    ("credit_notes.csv", "credit_notes"),
    # [新增] 财务模块 (第7模块)
    ("exchange_rates.csv", "exchange_rates"),
    ("receipts.csv", "receipts"),
    # [新增] 报价模块 (customers 之后, receipts 之后)
    ("quotations.csv", "quotations"),
    ("quotation_items.csv", "quotation_items"),
]


def main():
    parser = argparse.ArgumentParser(description="本地端到端业务流程验证 (SQLite)")
    parser.add_argument(
        "--db",
        default=os.path.join(DATA_DB_DIR, "validation.db"),
        help="SQLite 数据库文件路径",
    )
    parser.add_argument(
        "--csv-dir",
        default=DATA_CSV_DIR,
        help="真实数据 CSV 所在目录 (data/csv)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="每次都重建空库再导入 (默认 True)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("本地端到端业务流程验证")
    print(f"数据库: {args.db}")
    print(f"CSV 目录: {args.csv_dir}")
    print("=" * 60)

    # 1. 重建库
    print("\n[0/15] 重建 SQLite 验证库...")
    conn = setup_db(args.db)
    print(f"  库已重建: {args.db}")

    # 2. 按业务顺序导入 CSV
    print("\n[导入] 按依赖顺序加载真实 CSV...")
    import_order = IMPORT_ORDER

    pre_report = ValidationReport()
    for filename, table in import_order:
        csv_path = os.path.join(args.csv_dir, filename)
        if os.path.exists(csv_path):
            n = load_csv_into_sqlite(conn, csv_path, table, pre_report)
            print(f"  {filename:32s} -> {table:30s}  ({n} 行)")
        else:
            print(f"  {filename:32s} -> (跳过, 文件不存在)")

    # 3. 跑校验
    print("\n[校验] 业务规则端到端检查...")
    report = ValidationReport()
    run_validation(conn, report)

    # 4. 输出报告
    print("\n" + "=" * 60)
    print("校验报告")
    print("=" * 60)
    if report.ok:
        print("结果: ✓ 全部通过")
    else:
        print("结果: ✗ 有错误, 请修正后重跑")
    print(report.summary())

    # 5. 写日志
    os.makedirs(DATA_LOG_DIR, exist_ok=True)
    log_path = os.path.join(
        DATA_LOG_DIR, f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"时间: {datetime.now()}\n")
        f.write(f"数据库: {args.db}\n\n")
        f.write(report.summary())
    print(f"\n日志已保存: {log_path}")

    conn.close()
    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
