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


def insert_row(table: str, data: dict, operator: str = "frontend") -> dict:
    """①②④⑤⑥: 完整写入。返回 {ok, errors, warnings, record_id, checks}"""
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
    rows = list_options(
        "SELECT brand, COUNT(*) AS cnt FROM products "
        "WHERE customer_code=%s AND brand IS NOT NULL AND brand!='' "
        "GROUP BY brand ORDER BY cnt DESC",
        (customer_code,),
    )
    return [r["brand"] for r in rows]


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
