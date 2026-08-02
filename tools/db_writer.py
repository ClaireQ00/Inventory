#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db_writer.py — 前端写入规则层 (A 期, 2026-08-01)

定位: 前端 (streamlit) 所有写库操作的**唯一入口**。老板 2026-08-01 拍板放开前端写入,
但立下铁律: 不允许裸写 SQL 绕过业务规则。本模块把 CSV 流水线的保障原样搬到写库路径:

    录入数据
      → ① 字段校验 (必填/类型/枚举/外键存在)
      → ② 派生计算 (复用 csv_to_sql.apply_derived_rules + DERIVED_RULES, 与 CSV 导入同引擎)
      → ③ 预览 (返回给前端, 人确认后才提交)
      → ④ INSERT 入库
      → ⑤ 写后子校验 (与 16 步校验同口径的定点检查, 如收款累计 ≤ 合同额)
      → ⑥ audit_logs 留痕 (旧值/新值/操作人/时间)

使用方式 (两段式, 跟参考项目"预览→确认"习惯一致):
    preview = preview_insert("receipts", data)          # ①②③ 不落库
    result  = insert_row("receipts", data, operator)    # ①②④⑤⑥ 落库

A 期开放三张表: exchange_rates / receipts / products (物料)。
报价/合同/发货 (带明细行和快照规则) 在 C 期开放, 见 TASKS.md FC.1。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import pymysql

# 复用 CSV 导入管线的派生引擎 (csv_to_sql.py 有 __main__ 守卫, import 无副作用)
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from csv_to_sql import apply_derived_rules  # noqa: E402

# ──────────────────────────────────────────────────────────────
# 数据库连接 (与 streamlit_app.py 同一套环境变量)
# ──────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "inventory"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "inventory_db"),
    "charset": "utf8mb4",
}


def get_connection():
    return pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **DB_CONFIG)


# ──────────────────────────────────────────────────────────────
# 字段规则: A 期三张表的录入约束
#   required: 必填 | kind: 类型检查 | enum: 枚举 | max: 长度 | fk: (表, 列, 显示名) 外键须存在
# ──────────────────────────────────────────────────────────────
FIELD_RULES = {
    "exchange_rates": {
        "currency": {"required": True, "kind": "str", "max": 3},
        "rate_to_cny": {"required": True, "kind": "posnum"},
        "effective_date": {"required": True, "kind": "date"},
        "source": {"kind": "str", "max": 32},
        "remark": {"kind": "str", "max": 255},
    },
    "receipts": {
        "receipt_no": {"required": True, "kind": "str", "max": 32},
        "customer_code": {"required": True, "kind": "str", "fk": ("customers", "code", "客户")},
        "contract_no": {"kind": "str", "fk": ("sales_contracts", "contract_no", "合同")},
        "amount": {"required": True, "kind": "posnum"},
        "currency": {"required": True, "kind": "str", "max": 3},
        "paid_date": {"required": True, "kind": "date"},
        "pay_method": {"kind": "enum", "values": ["T/T", "L/C", "D/P", "D/A", "other"]},
        "bank_ref": {"kind": "str", "max": 64},
        "status": {"kind": "enum", "values": ["draft", "confirmed", "cancelled"]},
        "remark": {"kind": "str", "max": 512},
    },
    "products": {
        "material_id": {"required": True, "kind": "str", "max": 32},
        "customer_code": {"required": True, "kind": "str", "fk": ("customers", "code", "客户")},
        "brand": {"kind": "str", "max": 32},
        "product_category": {"required": True, "kind": "str", "max": 32},
        "material_type": {"kind": "str", "max": 32},
        "spec": {"kind": "str", "max": 32},
        "inner_diameter": {"required": True, "kind": "posnum"},
        "inner_diameter_inch": {"kind": "str", "max": 16},
        "outer_diameter": {"kind": "posnum"},
        "thickness": {"kind": "posnum"},
        "id_x_od": {"kind": "str", "max": 32},
        "length": {"kind": "posnum"},
        "spec_meter": {"kind": "posnum"},
        "virtual_weight": {"kind": "posnum"},
        "virtual_length": {"kind": "posnum"},
        "wire_spacing": {"kind": "str", "max": 32},
        "weight_per_meter": {"kind": "posnum"},
        "weight": {"kind": "posnum"},
        "appearance_inner": {"kind": "posnum"},
        "appearance_outer": {"kind": "posnum"},
        "appearance_height": {"kind": "posnum"},
        "volume": {"kind": "posnum"},
        "package": {"kind": "str", "max": 32},
        "label_paper": {"kind": "str", "max": 32},
        "material_used": {"kind": "str", "max": 64},
        "wire_pattern": {"kind": "str", "max": 64},
        "coil_type": {"kind": "str", "max": 64},
        "pressure": {"kind": "posnum"},
        "spray_code": {"kind": "str", "max": 512},
        "meter_mark": {"kind": "str", "max": 64},
        "meter_mark_count": {"kind": "posnum"},
        "remark": {"kind": "str", "max": 512},
    },
}

# 各表的唯一键 (录入前查重, 比撞 UNIQUE KEY 报错友好)
UNIQUE_KEYS = {
    "exchange_rates": ["currency", "effective_date"],
    "receipts": ["receipt_no"],
    "products": ["material_id"],
}

ALLOWED_TABLES = tuple(FIELD_RULES.keys())


# ──────────────────────────────────────────────────────────────
# ① 字段校验
# ──────────────────────────────────────────────────────────────
def _is_date(v) -> bool:
    if isinstance(v, (date, datetime)):
        return True
    try:
        date.fromisoformat(str(v)[:10])
        return True
    except ValueError:
        return False


def validate_fields(table: str, data: dict, conn=None) -> list[str]:
    """字段级校验, 返回错误列表 (空 = 通过)"""
    errors: list[str] = []
    rules = FIELD_RULES[table]
    for field, rule in rules.items():
        v = data.get(field)
        empty = v is None or (isinstance(v, str) and v.strip() == "")
        if rule.get("required") and empty:
            errors.append(f"缺少必填字段: {field}")
            continue
        if empty:
            continue
        kind = rule.get("kind")
        if kind == "posnum":
            try:
                if float(v) <= 0:
                    errors.append(f"{field} 必须是正数, 收到: {v}")
            except (TypeError, ValueError):
                errors.append(f"{field} 必须是数字, 收到: {v}")
        elif kind == "date" and not _is_date(v):
            errors.append(f"{field} 必须是日期 (YYYY-MM-DD), 收到: {v}")
        elif kind == "enum" and v not in rule["values"]:
            errors.append(f"{field} 必须是 {rule['values']} 之一, 收到: {v}")
        elif kind == "str" and rule.get("max") and len(str(v)) > rule["max"]:
            errors.append(f"{field} 超长 (>{rule['max']} 字符)")
        # 外键存在性
        if rule.get("fk") and conn is not None:
            fk_table, fk_col, fk_label = rule["fk"]
            with conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM {fk_table} WHERE {fk_col}=%s LIMIT 1", (v,))
                if not cur.fetchone():
                    errors.append(f"{field}={v}: {fk_label}不存在 (请先维护基础资料)")
    # 查重
    if conn is not None:
        keys = UNIQUE_KEYS[table]
        if all(data.get(k) not in (None, "") for k in keys):
            where = " AND ".join(f"{k}=%s" for k in keys)
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT 1 FROM {table} WHERE {where} LIMIT 1",
                    tuple(data[k] for k in keys),
                )
                if cur.fetchone():
                    errors.append(f"唯一键冲突: {'+'.join(keys)} = {'+'.join(str(data[k]) for k in keys)} 已存在")
    return errors


# ──────────────────────────────────────────────────────────────
# ② 派生计算 (与 CSV 导入同一个引擎)
# ──────────────────────────────────────────────────────────────
def apply_derived(table: str, data: dict) -> tuple[dict, list[tuple[str, str]]]:
    """返回 (补全后的数据, 引擎信息列表 [(level, msg)])"""
    row = dict(data)
    # 空字符串统一成 None 语义由引擎内部判断; 数值字段转成 float 帮助引擎计算
    report: list[tuple[str, str]] = []
    apply_derived_rules(table, row, row_index=1, report=report)
    return row, report


# ──────────────────────────────────────────────────────────────
# 收款专用: 按 paid_date 所在月自动查汇率
# ──────────────────────────────────────────────────────────────
def lookup_exchange_rate(conn, currency: str, paid_date_str: str) -> tuple[float | None, str]:
    """返回 (rate, 说明)。找不到返回 (None, 提示先录汇率)。汇率月固定 (R7): 取 paid_date 当天或之前最近一条"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT rate_to_cny, effective_date FROM exchange_rates
               WHERE currency=%s AND effective_date<=%s
               ORDER BY effective_date DESC LIMIT 1""",
            (currency, paid_date_str),
        )
        row = cur.fetchone()
    if not row:
        return None, f"找不到 {currency} 在 {paid_date_str} 之前生效的汇率, 请先到【录入中心→汇率】补录"
    eff = str(row["effective_date"])[:10]
    # 汇率月固定 (R7): 必须用 paid_date 所在月或之前的最近一条; 跨月太久给出提示
    note = f"汇率 {row['rate_to_cny']} (生效 {eff})"
    if eff[:7] != str(paid_date_str)[:7]:
        note += f" ⚠️ 不是 {str(paid_date_str)[:7]} 当月汇率, 请确认是否需要补录当月汇率"
    return float(row["rate_to_cny"]), note


# ──────────────────────────────────────────────────────────────
# ⑤ 写后子校验 (与 16 步校验同口径的定点检查)
# ──────────────────────────────────────────────────────────────
def post_checks(table: str, conn, data: dict) -> list[tuple[str, str]]:
    """返回 [(level, msg)], level ∈ info/warn/error"""
    msgs: list[tuple[str, str]] = []
    if table == "receipts" and data.get("contract_no"):
        # 对齐第 13 步 check_receipts_vs_contract: 累计收款 ≤ 合同金额
        with conn.cursor() as cur:
            cur.execute(
                """SELECT sc.total_amount, sc.currency,
                          COALESCE(SUM(r.amount), 0) AS received
                   FROM sales_contracts sc
                   LEFT JOIN receipts r ON r.contract_no = sc.contract_no
                                        AND r.status != 'cancelled'
                   WHERE sc.contract_no = %s
                   GROUP BY sc.contract_no""",
                (data["contract_no"],),
            )
            row = cur.fetchone()
        if row and float(row["received"]) > float(row["total_amount"]):
            msgs.append((
                "error",
                f"累计收款 {row['received']} {row['currency']} 已超合同总额 "
                f"{row['total_amount']} (对齐第13步校验口径)",
            ))
        elif row:
            msgs.append((
                "info",
                f"该合同累计收款 {row['received']} / 合同额 {row['total_amount']} {row['currency']}",
            ))
    if table == "exchange_rates":
        # 对齐第 12 步: 当月汇率是否齐全 (已有 receipts 用到这个月)
        eff_month = str(data["effective_date"])[:7]
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT currency FROM receipts WHERE DATE_FORMAT(paid_date,'%Y-%m')=%s",
                (eff_month,),
            )
            used = {r["currency"] for r in cur.fetchall()}
            cur.execute(
                "SELECT currency FROM exchange_rates WHERE DATE_FORMAT(effective_date,'%Y-%m')=%s",
                (eff_month,),
            )
            have = {r["currency"] for r in cur.fetchall()}
        missing = used - have - {data["currency"]}
        if missing:
            msgs.append(("warn", f"{eff_month} 有 {sorted(missing)} 币种的收款但尚无当月汇率"))
    return msgs


# ──────────────────────────────────────────────────────────────
# ⑥ 审计留痕
# ──────────────────────────────────────────────────────────────
def _jsonable(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "__str__") and type(obj).__name__ == "Decimal":
        return float(obj)
    return str(obj)


def write_audit(conn, table: str, record_id, action: str,
                old_values: dict | None, new_values: dict | None, operator: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO audit_logs (table_name, record_id, action, old_values, new_values, operator)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                table,
                int(record_id or 0),
                action,
                json.dumps(old_values, ensure_ascii=False, default=_jsonable) if old_values else None,
                json.dumps(new_values, ensure_ascii=False, default=_jsonable) if new_values else None,
                (operator or "frontend").strip()[:32],
            ),
        )


# ──────────────────────────────────────────────────────────────
# 两段式主接口
# ──────────────────────────────────────────────────────────────
def preview_insert(table: str, data: dict) -> dict:
    """①②③: 校验 + 派生 + 预览, 不落库。返回 {ok, errors, derived_row, engine_msgs, rate_note}"""
    if table not in ALLOWED_TABLES:
        return {"ok": False, "errors": [f"A期未开放该表录入: {table} (开放: {ALLOWED_TABLES})"]}
    conn = get_connection()
    try:
        errors = validate_fields(table, data, conn)
        row, engine_msgs = apply_derived(table, data)
        rate_note = ""
        if table == "receipts" and not errors:
            # 汇率自动带出: 没填 exchange_rate 就按 paid_date 查表
            if not row.get("exchange_rate"):
                rate, rate_note = lookup_exchange_rate(conn, row["currency"], str(row["paid_date"])[:10])
                if rate is None:
                    errors.append(rate_note)
                else:
                    row["exchange_rate"] = rate
                    row, more = apply_derived(table, row)  # 重算 amount_cny
                    engine_msgs += more
        return {
            "ok": not errors,
            "errors": errors,
            "derived_row": row,
            "engine_msgs": engine_msgs,
            "rate_note": rate_note,
        }
    finally:
        conn.close()


def insert_row(table: str, data: dict, operator: str = "frontend",
               options: dict | None = None) -> dict:
    """①②④⑤⑥: 完整写入。返回 {ok, errors, warnings, record_id, checks}

    options 可选开关:
      - auto_archive_package: products 专用。手填的新包装在物料入库成功后
        自动建档进 aux_materials(packaging), 下次下拉直接可选 (2026-08-02 老板要求)
    """
    pv = preview_insert(table, data)
    if not pv["ok"]:
        return {"ok": False, "errors": pv["errors"], "warnings": [], "record_id": None, "checks": []}
    row = pv["derived_row"]

    # 只写表存在的列 (派生引擎可能算出录入表没有的辅助键)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW COLUMNS FROM {table}")
            valid_cols = {c["Field"] for c in cur.fetchall()}
        valid_cols.discard("id")
        valid_cols.discard("created_at")
        clean = {k: v for k, v in row.items()
                 if k in valid_cols and v is not None and v != ""}
        cols = ", ".join(clean.keys())
        phs = ", ".join(["%s"] * len(clean))
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({phs})", tuple(clean.values()))
            record_id = cur.lastrowid
        checks = post_checks(table, conn, row)
        errors = [m for lv, m in checks if lv == "error"]
        warnings = [m for lv, m in checks if lv == "warn"]
        if errors:
            # 写后校验出 ERROR → 回滚, 脏数据不进库 (跟 16 步校验 ERROR 同级语义)
            conn.rollback()
            return {"ok": False, "errors": errors, "warnings": warnings,
                    "record_id": None, "checks": checks}
        write_audit(conn, table, record_id, "INSERT", None, clean, operator)
        conn.commit()
        # 物料入库成功后的联动开关 (独立小事务, 建档失败不影响已入库的物料)
        if table == "products":
            opts = options or {}
            if opts.get("auto_archive"):
                # 总开关: AUTO_ARCHIVE_FIELDS 全部字段 (包装/标签纸/喷码/米标/用料/打线/盘型)
                for f in AUTO_ARCHIVE_FIELDS:
                    msg = _auto_archive_value(f, clean.get(f), operator)
                    if msg:
                        warnings.append(msg)
            elif opts.get("auto_archive_package"):
                # 兼容旧调用: 只管包装
                archive_msg = _auto_archive_value("package", clean.get("package"), operator)
                if archive_msg:
                    warnings.append(archive_msg)
        return {
            "ok": True,
            "errors": [],
            "warnings": warnings,
            "record_id": record_id,
            "checks": checks,
        }
    except Exception as e:
        conn.rollback()
        return {"ok": False, "errors": [f"数据库写入失败: {e}"], "warnings": [],
                "record_id": None, "checks": []}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# 下拉数据助手 (录入表单用)
# ──────────────────────────────────────────────────────────────
def list_options(sql: str, params=()) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            # PyMySQL fetchall 返回 tuple, 统一转 list (调用方有列表拼接操作)
            return list(cur.fetchall())
    finally:
        conn.close()


def list_customers() -> list[dict]:
    return list_options("SELECT code, name FROM customers ORDER BY code")


def list_contracts(customer_code: str | None = None) -> list[dict]:
    if customer_code:
        return list_options(
            """SELECT contract_no, total_amount, currency, status FROM sales_contracts
               WHERE customer_code=%s ORDER BY sign_date DESC""",
            (customer_code,),
        )
    return list_options(
        "SELECT contract_no, customer_code, total_amount, currency, status FROM sales_contracts ORDER BY sign_date DESC"
    )


def list_products() -> list[dict]:
    return list_options(
        "SELECT material_id, spec, weight FROM products WHERE is_active=1 ORDER BY material_id"
    )


# ──────────────────────────────────────────────────────────────
# 物料录入专用助手 (2026-08-01 A 期反馈迭代)
# ──────────────────────────────────────────────────────────────
def suggest_material_id(customer_code: str) -> str:
    """按客户编码建议下一个物料编码: M-{客户}-{最大流水+1:03d}。
    没有该客户的物料时从 001 开始。编码可手改, 这只是建议值。"""
    rows = list_options(
        "SELECT material_id FROM products WHERE material_id LIKE %s",
        (f"M-{customer_code}-%",),
    )
    max_seq = 0
    for r in rows:
        suffix = r["material_id"].rsplit("-", 1)[-1]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"M-{customer_code}-{max_seq + 1:03d}"


def distinct_categories() -> list[str]:
    """产品原始类别清单 (真实数据 70+ 种), 按使用频次倒序, 供下拉选择"""
    rows = list_options(
        "SELECT product_category, COUNT(*) AS cnt FROM products "
        "GROUP BY product_category ORDER BY cnt DESC"
    )
    return [r["product_category"] for r in rows if r["product_category"]]


# 标准管型标称英寸序列 (2026-08-01 老板规则): 1" 以内按 1/16 分数段,
# 1" 以上按贸易常用管径 (1-1/4 / 1-1/2 / 2 / 2-1/2 / 3 / 4 ...)。
# 取值规则 = **向上取**: 实际 mm 通常比标称 inch 小 (如 31.5mm 的管叫 1-1/4"),
# 所以选"标称 >= 实际"的最小一级, 而不是就近取。
NOMINAL_INCH_SERIES = [
    0.125, 0.1875, 0.25, 0.3125, 0.375, 0.4375, 0.5, 0.5625,
    0.625, 0.6875, 0.75, 0.8125, 0.875, 0.9375, 1.0,
    1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0,
]


def mm_to_inch_str(mm: float) -> str:
    """内径 mm -> 标称英寸字符串, **向上取**到标准管型序列 (NOMINAL_INCH_SERIES)。

    业务依据 (2026-08-01 老板): 制作的 mm 尺寸通常比标准 inch 小, 标称向上取。
    容忍度 0.8mm: 真实目录里有些规格做得比标称略大但仍归本档 ——
    13mm→1/2" (大0.3)、15mm→9/16" (大0.7)、23mm→7/8" (大0.8)、8mm→5/16"。
    即: 比标称小 → 向上取到第一个 >= 实际的档; 比标称大但超出 ≤0.8mm → 仍归本档。
    与 14,350 条现有目录全量核对一致。超出序列上限退回 1/16 就近取。
    与 tools/gen_products_from_excel.py:mm_to_inch_str 同算法 (两处同步, 避免漂移)。"""
    from fractions import Fraction
    inches = mm / 25.4
    target = None
    for n in NOMINAL_INCH_SERIES:
        if n * 25.4 >= mm - 0.8:  # 0.8mm 容忍: 做得略大的归本档, 否则向上取
            target = n
            break
    if target is None:
        sixteenths = max(1, round(inches * 16))
        frac = Fraction(sixteenths, 16)
    else:
        frac = Fraction(target).limit_denominator(16)
    whole = frac.numerator // frac.denominator
    rem = Fraction(frac.numerator % frac.denominator, frac.denominator)
    if rem == 0:
        return f'{whole}"'
    if whole == 0:
        return f'{rem.numerator}/{rem.denominator}"'
    return f'{whole}-{rem.numerator}/{rem.denominator}"'


def nominal_inch_options() -> list[str]:
    """标准管型标称英寸下拉清单 (录入页 inch 字段用, 与 mm_to_inch_str 同一序列)"""
    from fractions import Fraction
    labels = []
    for n in NOMINAL_INCH_SERIES:
        frac = Fraction(n).limit_denominator(16)
        whole = frac.numerator // frac.denominator
        rem = Fraction(frac.numerator % frac.denominator, frac.denominator)
        if rem == 0:
            labels.append(f'{whole}"')
        elif whole == 0:
            labels.append(f'{rem.numerator}/{rem.denominator}"')
        else:
            labels.append(f'{whole}-{rem.numerator}/{rem.denominator}"')
    return labels


def distinct_brands(customer_code: str) -> list[str]:
    """该客户已有物料用过的品牌清单 (按使用频次倒序), 供品牌字段下拉; 仍可手填新品牌"""
    return distinct_field_values(customer_code, "brand")


# 录入页"按客户历史值下拉 + 可手填"模式的字段白名单 (2026-08-01 老板:
# 喷码跟品牌一样; 物料类型/用料/打线/米标同等待遇 —— 后续这些进辅料/档案库, 下拉先行)
DROPDOWN_FIELDS = ("brand", "spray_code", "material_type", "material_used", "wire_pattern", "meter_mark")


def distinct_field_values(customer_code: str, field: str, limit: int = 20) -> list[str]:
    """该客户已有物料里某字段的历史值 (按使用频次倒序), 供下拉; 字段名走白名单防注入"""
    if field not in DROPDOWN_FIELDS:
        raise ValueError(f"不允许下拉的字段: {field} (白名单: {DROPDOWN_FIELDS})")
    rows = list_options(
        f"SELECT {field} AS v, COUNT(*) AS cnt FROM products "
        f"WHERE customer_code=%s AND {field} IS NOT NULL AND {field}!='' "
        f"GROUP BY {field} ORDER BY cnt DESC LIMIT %s",
        (customer_code, limit),
    )
    return [r["v"] for r in rows]


def live_derive_products(data: dict) -> tuple[dict, set, list, float | None, str | None]:
    """物料录入的实时派生 (Streamlit 每次输入变化重跑时调用):

    1. 内径 mm → 自动换算标称英寸 (inner_diameter_inch)
    2. 长度 → spec_meter (四舍五入取整)
    3. 跑 apply_derived_rules("products") —— 已支持的派生全部自动算:
       厚度→外径 / 外径→厚度 / 内径+厚度→米重 / +长度→单重 / 规格描述拼接
    4. 顺带算密度展示

    返回 (补全行, 本次自动算出的字段集合, 引擎信息, 密度, 所属大类)
    """
    from csv_to_sql import calc_density, resolve_category_group
    row = {k: v for k, v in data.items()}
    if row.get("inner_diameter") and not row.get("inner_diameter_inch"):
        try:
            row["inner_diameter_inch"] = mm_to_inch_str(float(row["inner_diameter"]))
        except (TypeError, ValueError):
            pass
    if row.get("length") and not row.get("spec_meter"):
        try:
            row["spec_meter"] = str(round(float(row["length"])))
        except (TypeError, ValueError):
            pass
    filled_before = {k for k, v in row.items() if v not in (None, "")}
    row, msgs = apply_derived("products", row)
    computed = {k for k, v in row.items()
                if k not in filled_before and v not in (None, "")}
    density = calc_density(row)
    group = resolve_category_group(row.get("product_category"))
    return row, computed, msgs, density, group


# ──────────────────────────────────────────────────────────────
# 生产辅料 (标签纸等) — 档案/收发存/需求测算 (2026-08-01 M1+M2)
# 计划: docs/AUX_MATERIALS_PLAN.md (Q1-Q7 已定案)
# 范围: 标签纸=实体收发存; 用料=半成品原材料后续独立模块; 打线/米标/物料类型=工艺档案
# ──────────────────────────────────────────────────────────────
AUX_MATERIAL_RULES = {
    "aux_code": {"required": True, "kind": "str", "max": 32},
    "aux_type": {"kind": "enum", "values": ["label_paper", "packaging", "spray_code", "meter_mark",
                                             "material_used", "wire_pattern", "coil_type", "other"]},
    "name": {"kind": "str", "max": 255},
    "shape": {"kind": "str", "max": 8},
    "width_mm": {"kind": "posnum"},
    "height_mm": {"kind": "posnum"},
    "material_desc": {"kind": "str", "max": 64},
    "supplier_code": {"kind": "str", "fk": ("suppliers", "code", "供应商")},
    "unit": {"kind": "str", "max": 16},
    "pcs_per_unit": {"kind": "posnum"},
    "min_stock": {"kind": "posnum"},
    "remark": {"kind": "str", "max": 255},
}

# 出入库方向各自的来源类型白名单
AUX_SOURCE_TYPES = {
    "in": ("purchase", "adjust"),
    "out": ("production_use", "scrap", "adjust"),
}


def _validate_with_rules(rules: dict, data: dict, conn) -> list[str]:
    """通用字段校验 (复用 validate_fields 的 kind 语义, 但作用于任意规则表)"""
    errors: list[str] = []
    for field, rule in rules.items():
        v = data.get(field)
        empty = v is None or (isinstance(v, str) and v.strip() == "")
        if rule.get("required") and empty:
            errors.append(f"缺少必填字段: {field}")
            continue
        if empty:
            continue
        kind = rule.get("kind")
        if kind == "posnum":
            try:
                if float(v) <= 0:
                    errors.append(f"{field} 必须是正数, 收到: {v}")
            except (TypeError, ValueError):
                errors.append(f"{field} 必须是数字, 收到: {v}")
        elif kind == "enum" and v not in rule["values"]:
            errors.append(f"{field} 必须是 {rule['values']} 之一, 收到: {v}")
        elif kind == "str" and rule.get("max") and len(str(v)) > rule["max"]:
            errors.append(f"{field} 超长 (>{rule['max']} 字符)")
        if rule.get("fk") and conn is not None:
            fk_table, fk_col, fk_label = rule["fk"]
            with conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM {fk_table} WHERE {fk_col}=%s LIMIT 1", (v,))
                if not cur.fetchone():
                    errors.append(f"{field}={v}: {fk_label}不存在")
    return errors


def contract_receipt_summary(contract_no: str) -> dict | None:
    """合同收款进度 (收款录入页参照 + 第13步校验同口径): 总额/已收/未收"""
    rows = list_options(
        """SELECT sc.total_amount, sc.currency, c.name AS customer_name,
                  COALESCE(SUM(r.amount), 0) AS received
           FROM sales_contracts sc
           JOIN customers c ON c.code = sc.customer_code
           LEFT JOIN receipts r ON r.contract_no = sc.contract_no
                                AND r.status != 'cancelled'
           WHERE sc.contract_no = %s
           GROUP BY sc.contract_no, sc.total_amount, sc.currency, c.name""",
        (contract_no,),
    )
    if not rows:
        return None
    r = rows[0]
    total = float(r["total_amount"])
    received = float(r["received"])
    return {"contract_no": contract_no, "customer_name": r["customer_name"],
            "total_amount": total, "currency": r["currency"],
            "received": received, "remaining": total - received,
            "fully_received": received >= total}


def list_material_type_profiles() -> list[dict]:
    """物料类型档案 (录入页下拉源; 成本指导价预留)"""
    return list_options(
        "SELECT type_code, name, guide_cost_price, price_currency FROM material_type_profiles "
        "WHERE is_active=1 ORDER BY type_code"
    )


# 手填值自动建档映射: products 字段 → (档案类型, 编码前缀, 字段中文名)
# 除 label_paper 外均按 (aux_type, name) 查重、PREFIX-### 顺序编码;
# label_paper 特殊: 档案编码 = LP-前缀 + 手填的 R/C 编号, 按 aux_code 查重 (2026-08-02 老板要求一个开关管全部)
AUTO_ARCHIVE_FIELDS = {
    "package":       ("packaging", "PK", "包装"),
    "label_paper":   ("label_paper", "LP", "标签纸"),
    "spray_code":    ("spray_code", "SP", "喷码"),
    "meter_mark":    ("meter_mark", "MM", "米标"),
    "material_used": ("material_used", "MU", "用料"),
    "wire_pattern":  ("wire_pattern", "WP", "打线"),
    "coil_type":     ("coil_type", "CT", "盘型"),
}


def _auto_archive_value(field: str, value: str | None, operator: str) -> str | None:
    """手填新值自动建档 (insert_row 的 products 联动开关, AUTO_ARCHIVE_FIELDS 驱动)。

    - 已存在 → None (静默)
    - 不存在 → 生成编码建档 + 审计, 返回提示语
    - 任何失败只返回告警文案, 不抛异常 (物料已入库, 建档可手工补)
    """
    if not value or field not in AUTO_ARCHIVE_FIELDS:
        return None
    aux_type, prefix, label = AUTO_ARCHIVE_FIELDS[field]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if field == "label_paper":
                code = value if value.startswith("LP-") else f"LP-{value}"
                cur.execute("SELECT 1 FROM aux_materials WHERE aux_code=%s LIMIT 1", (code,))
                exists = cur.fetchone() is not None
                name = f"标签 {value}"
            else:
                cur.execute(
                    "SELECT 1 FROM aux_materials WHERE aux_type=%s AND name=%s LIMIT 1",
                    (aux_type, value),
                )
                exists = cur.fetchone() is not None
                cur.execute(
                    """SELECT MAX(CAST(SUBSTRING(aux_code, %s) AS UNSIGNED)) AS mx
                       FROM aux_materials WHERE aux_code REGEXP %s""",
                    (len(prefix) + 2, f"^{prefix}-[0-9]+$"),
                )
                code = f"{prefix}-{int(cur.fetchone()['mx'] or 0) + 1:03d}"
                name = value
            if exists:
                return None
            cur.execute(
                """INSERT INTO aux_materials (aux_code, aux_type, name, unit, remark)
                   VALUES (%s, %s, %s, '', %s)""",
                (code, aux_type, name, f"录入物料时手填新{label}自动建档 (操作人 {operator})"),
            )
            record_id = cur.lastrowid
        write_audit(conn, "aux_materials", record_id, "INSERT", None,
                    {"aux_code": code, "aux_type": aux_type, "name": name, "auto": True}, operator)
        conn.commit()
        short = value if len(value) <= 20 else f"{value[:20]}…"
        return f"新{label}「{short}」已自动建档 {code}（辅料档案页可补全信息）"
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return f"新{label}「{value}」自动建档失败: {e}（物料已入库，可到辅料档案页手工补建）"
    finally:
        conn.close()


def aux_list_materials(aux_type: str | None = None) -> list[dict]:
    """辅料档案列表, 带库存合计"""
    where = "WHERE m.is_active=1"
    params: tuple = ()
    if aux_type:
        where += " AND m.aux_type=%s"
        params = (aux_type,)
    return list_options(
        f"""SELECT m.*, COALESCE(SUM(i.quantity), 0) AS stock_total
            FROM aux_materials m
            LEFT JOIN aux_inventory i ON i.aux_code = m.aux_code
            {where}
            GROUP BY m.id ORDER BY m.aux_code""",
        params,
    )


def aux_create_material(data: dict, operator: str = "frontend-react") -> dict:
    """新增辅料档案: 字段校验 + 查重 + 落库 + 审计"""
    conn = get_connection()
    try:
        errors = _validate_with_rules(AUX_MATERIAL_RULES, data, conn)
        if not errors and data.get("aux_code"):
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM aux_materials WHERE aux_code=%s LIMIT 1", (data["aux_code"],))
                if cur.fetchone():
                    errors.append(f"唯一键冲突: aux_code = {data['aux_code']} 已存在")
        if errors:
            return {"ok": False, "errors": errors, "record_id": None}
        clean = {k: v for k, v in data.items()
                 if k in AUX_MATERIAL_RULES and v is not None and v != ""}
        cols = ", ".join(clean.keys())
        phs = ", ".join(["%s"] * len(clean))
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO aux_materials ({cols}) VALUES ({phs})", tuple(clean.values()))
            record_id = cur.lastrowid
        write_audit(conn, "aux_materials", record_id, "INSERT", None, clean, operator)
        conn.commit()
        return {"ok": True, "errors": [], "record_id": record_id}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"数据库写入失败: {e}"], "record_id": None}
    finally:
        conn.close()


def aux_inventory_list(low_only: bool = False) -> list[dict]:
    """辅料库存查询 (低库存=有安全库存且存量低于它)"""
    base = """SELECT i.aux_code, m.name, m.unit, m.min_stock, i.warehouse_code, w.name AS warehouse_name,
                     i.quantity, i.updated_at,
                     (m.min_stock IS NOT NULL AND i.quantity < m.min_stock) AS low_stock
              FROM aux_inventory i
              JOIN aux_materials m ON m.aux_code = i.aux_code
              JOIN warehouses w ON w.code = i.warehouse_code"""
    if low_only:
        return list_options(
            base + " WHERE m.min_stock IS NOT NULL AND i.quantity < m.min_stock"
                   " ORDER BY i.aux_code"
        )
    return list_options(base + " ORDER BY i.aux_code, i.warehouse_code")


def aux_stock_move(aux_code: str, warehouse_code: str, direction: str, qty: int,
                   source_type: str, source_no: str = "", operator: str = "frontend-react",
                   move_date: str | None = None, remark: str = "") -> dict:
    """辅料收发 (M2 核心): 单事务内 锁库存行 → 校验 → 改库存 → 写流水 → 审计。

    护栏:
      - 出库库存不足 → 回滚拦截 (脏数据不进库)
      - after_qty 由库存行算, 不信任前端
    """
    import uuid as _uuid
    errors: list[str] = []
    if direction not in ("in", "out"):
        errors.append(f"direction 必须是 in/out, 收到: {direction}")
    if source_type not in AUX_SOURCE_TYPES.get(direction, ()):
        errors.append(f"{direction} 库的来源类型必须是 {AUX_SOURCE_TYPES.get(direction)}, 收到: {source_type}")
    try:
        qty = int(qty)
        if qty <= 0:
            errors.append(f"数量必须是正整数, 收到: {qty}")
    except (TypeError, ValueError):
        errors.append(f"数量必须是正整数, 收到: {qty}")
        qty = 0
    move_date = move_date or date.today().isoformat()
    if not _is_date(move_date):
        errors.append(f"move_date 必须是日期, 收到: {move_date}")
    if errors:
        return {"ok": False, "errors": errors, "move_no": None, "after_qty": None}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 存在性
            cur.execute("SELECT 1 FROM aux_materials WHERE aux_code=%s AND is_active=1 LIMIT 1", (aux_code,))
            if not cur.fetchone():
                conn.rollback()
                return {"ok": False, "errors": [f"辅料不存在或已停用: {aux_code}"], "move_no": None, "after_qty": None}
            cur.execute("SELECT 1 FROM warehouses WHERE code=%s LIMIT 1", (warehouse_code,))
            if not cur.fetchone():
                conn.rollback()
                return {"ok": False, "errors": [f"仓库不存在: {warehouse_code}"], "move_no": None, "after_qty": None}
            # 锁库存行
            cur.execute(
                "SELECT quantity FROM aux_inventory WHERE aux_code=%s AND warehouse_code=%s FOR UPDATE",
                (aux_code, warehouse_code),
            )
            row = cur.fetchone()
            current = int(row["quantity"]) if row else 0
            if direction == "out" and current < qty:
                conn.rollback()
                return {"ok": False,
                        "errors": [f"库存不足: {aux_code}@{warehouse_code} 当前 {current} 张, 要出库 {qty} 张"],
                        "move_no": None, "after_qty": current}
            after = current + qty if direction == "in" else current - qty
            if row:
                cur.execute(
                    "UPDATE aux_inventory SET quantity=%s WHERE aux_code=%s AND warehouse_code=%s",
                    (after, aux_code, warehouse_code),
                )
            else:
                cur.execute(
                    "INSERT INTO aux_inventory (aux_code, warehouse_code, quantity) VALUES (%s,%s,%s)",
                    (aux_code, warehouse_code, after),
                )
            move_no = f"AX{'IN' if direction == 'in' else 'OUT'}{move_date.replace('-', '')}-{_uuid.uuid4().hex[:6].upper()}"
            signed = qty if direction == "in" else -qty
            cur.execute(
                """INSERT INTO aux_stock_moves
                   (move_no, aux_code, warehouse_code, direction, change_qty, after_qty,
                    source_type, source_no, operator, move_date, remark)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (move_no, aux_code, warehouse_code, direction, signed, after,
                 source_type, source_no, operator, move_date, remark),
            )
            move_id = cur.lastrowid
        write_audit(conn, "aux_stock_moves", move_id, "INSERT", None,
                    {"move_no": move_no, "aux_code": aux_code, "qty": signed, "after": after}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "move_no": move_no, "after_qty": after}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"收发失败: {e}"], "move_no": None, "after_qty": None}
    finally:
        conn.close()


def aux_moves(aux_code: str | None = None, limit: int = 200) -> list[dict]:
    """辅料收发流水账 (新的在前)"""
    if aux_code:
        return list_options(
            "SELECT * FROM aux_stock_moves WHERE aux_code=%s ORDER BY id DESC LIMIT %s",
            (aux_code, limit),
        )
    return list_options("SELECT * FROM aux_stock_moves ORDER BY id DESC LIMIT %s", (limit,))


def aux_label_demand(contract_no: str) -> dict:
    """合同标签纸需求测算 (M3 核心, Q1 默认: 每卷产品 1 张标签; Q6: 只提示不扣减)。

    链条: 合同明细.material_id → products.label_paper → aux_materials(LP-前缀) → aux_inventory
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM sales_contracts WHERE contract_no=%s LIMIT 1", (contract_no,))
            if not cur.fetchone():
                return {"contract_no": contract_no, "found": False, "lines": [], "all_sufficient": None}
            cur.execute(
                """SELECT p.label_paper AS lp, SUM(ci.quantity) AS required
                   FROM sales_contract_items ci
                   JOIN products p ON p.material_id = ci.material_id
                   WHERE ci.contract_no=%s AND p.label_paper IS NOT NULL AND p.label_paper!=''
                   GROUP BY p.label_paper""",
                (contract_no,),
            )
            rows = list(cur.fetchall())
        lines = []
        for r in rows:
            aux_code = f"LP-{r['lp']}"
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT m.name, m.unit, COALESCE(SUM(i.quantity),0) AS in_stock
                       FROM aux_materials m
                       LEFT JOIN aux_inventory i ON i.aux_code = m.aux_code
                       WHERE m.aux_code=%s GROUP BY m.aux_code""",
                    (aux_code,),
                )
                stock_row = cur.fetchone()
            required = int(r["required"])
            in_stock = int(stock_row["in_stock"]) if stock_row else 0
            lines.append({
                "label_paper": r["lp"],
                "aux_code": aux_code,
                "name": stock_row["name"] if stock_row else f"(辅料库未建档: {aux_code})",
                "unit": stock_row["unit"] if stock_row else "张",
                "required": required,
                "in_stock": in_stock,
                "shortage": max(0, required - in_stock),
                "profile_missing": stock_row is None,
            })
        return {
            "contract_no": contract_no,
            "found": True,
            "lines": lines,
            "all_sufficient": all(l["shortage"] == 0 and not l["profile_missing"] for l in lines),
        }
    finally:
        conn.close()


def aux_add_attachment(aux_code: str, file_name: str, file_type: str, file_path: str,
                       file_size: int, sha256: str, uploaded_by: str) -> dict:
    """登记辅料附件 (文件已由 API 层落盘)。sha256 同辅料下去重"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM aux_attachments WHERE aux_code=%s AND sha256=%s LIMIT 1",
                (aux_code, sha256),
            )
            dup = cur.fetchone()
            if dup:
                return {"ok": True, "errors": [], "record_id": dup["id"], "duplicate": True}
            cur.execute(
                """INSERT INTO aux_attachments
                   (aux_code, file_name, file_type, file_path, file_size, sha256, uploaded_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (aux_code, file_name, file_type, file_path, file_size, sha256, uploaded_by),
            )
            record_id = cur.lastrowid
        write_audit(conn, "aux_attachments", record_id, "INSERT", None,
                    {"aux_code": aux_code, "file_name": file_name}, uploaded_by)
        conn.commit()
        return {"ok": True, "errors": [], "record_id": record_id, "duplicate": False}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"附件登记失败: {e}"], "record_id": None, "duplicate": False}
    finally:
        conn.close()


def aux_attachments(aux_code: str) -> list[dict]:
    return list_options(
        "SELECT id, aux_code, file_name, file_type, file_size, uploaded_by, created_at "
        "FROM aux_attachments WHERE aux_code=%s ORDER BY id DESC",
        (aux_code,),
    )
