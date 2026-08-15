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
import re
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
    if table == "products":
        _normalize_category_variant(row, report)
    return row, report


# 同物异名防线 (2026-08-11): "双联/双连""磨砂/磨沙"这类谐音异写,
# 录入时归一到既有类别写法, 防止类别裂成两个统计口径。规则见 tools/name_variants.py
def _normalize_category_variant(row: dict, report: list[tuple[str, str]]) -> None:
    cat = (row.get("product_category") or "").strip()
    if not cat:
        return
    try:
        from name_variants import near_match
        existing = [r["product_category"] for r in list_options(
            "SELECT DISTINCT product_category FROM products "
            "WHERE product_category IS NOT NULL AND product_category<>''")]
        hit = near_match(cat, existing)
        if hit:
            row["product_category"] = hit
            report.append(("warn",
                           f"产品类别『{cat}』与既有类别『{hit}』疑似同物异名, 已自动归一为『{hit}』;"
                           f"如确为新类别请改回并告知管理员扩充别名表"))
    except Exception:
        pass  # 防线失效不阻断录入主流程


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
            # 注意: pymysql 参数替换走 Python % 格式化, SQL 里写字面 % 必须转义成 %%
            cur.execute(
                "SELECT DISTINCT currency FROM receipts WHERE DATE_FORMAT(paid_date,'%%Y-%%m')=%s",
                (eff_month,),
            )
            used = {r["currency"] for r in cur.fetchall()}
            cur.execute(
                "SELECT currency FROM exchange_rates WHERE DATE_FORMAT(effective_date,'%%Y-%%m')=%s",
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


def list_salespersons() -> list[dict]:
    """业务员档案下拉 (客户录入页用)"""
    return list_options(
        "SELECT code, name, digit FROM salespersons WHERE is_active=1 ORDER BY code")


def create_salesperson(data: dict, operator: str = "frontend-react") -> dict:
    """业务员建档: 代码(首字母)唯一 + 首位数字必填 (客户编码推荐的权威来源)"""
    code = (data.get("code") or "").strip().upper()[:1]
    digit = str(data.get("digit") or "").strip()[:1]
    name = (data.get("name") or "").strip()
    errors: list[str] = []
    if not code or not code.isalpha():
        errors.append("业务员代码应为 1 个字母 (客户编码的首字母)")
    if not digit or not digit.isdigit():
        errors.append("首位数字应为 0-9 (该业务员的数字编码, 客户编码的第一位数字)")
    if errors:
        return {"ok": False, "errors": errors, "code": None}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM salespersons WHERE code=%s", (code,))
            if cur.fetchone():
                conn.rollback()
                return {"ok": False, "errors": [f"业务员代码已存在: {code}"], "code": None}
            cur.execute(
                "INSERT INTO salespersons (code, name, digit, phone, commission_rate, remark) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (code, name, digit, (data.get("phone") or "").strip() or None,
                 data.get("commission_rate") or None, (data.get("remark") or "").strip()))
            record_id = cur.lastrowid
        write_audit(conn, "salespersons", record_id, "INSERT", None,
                    {"code": code, "digit": digit, "name": name}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "code": code}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"业务员建档失败: {e}"], "code": None}
    finally:
        conn.close()


def list_salespersons_full() -> list[dict]:
    """业务员档案全字段列表 (业务员管理页用, 含停用)"""
    return list_options(
        "SELECT id, code, name, digit, phone, commission_rate, is_active, remark "
        "FROM salespersons ORDER BY code")


def update_salesperson(code: str, data: dict, operator: str = "frontend-react") -> dict:
    """业务员档案编辑: 姓名/电话/提成比例/停用/备注; code 与 digit 不可改 (客户编码的锚)"""
    code = (code or "").strip().upper()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, code, name, digit, phone, commission_rate, is_active, remark "
                "FROM salespersons WHERE code=%s", (code,))
            old = cur.fetchone()
            if not old:
                conn.rollback()
                return {"ok": False, "errors": [f"业务员不存在: {code}"]}
            if "code" in data or "digit" in data:
                conn.rollback()
                return {"ok": False, "errors": [
                    "代码/首位数字不可修改——它们是客户编码的锚; 换业务员请改客户编码的字母"]}
            fields = {
                "name": (data.get("name") or "").strip(),
                "phone": (data.get("phone") or "").strip() or None,
                "commission_rate": data.get("commission_rate") or None,
                "is_active": 1 if data.get("is_active", 1) else 0,
                "remark": (data.get("remark") or "").strip(),
            }
            if not fields["name"]:
                conn.rollback()
                return {"ok": False, "errors": ["姓名不能为空"]}
            cur.execute(
                "UPDATE salespersons SET name=%s, phone=%s, commission_rate=%s, "
                "is_active=%s, remark=%s WHERE code=%s",
                (fields["name"], fields["phone"], fields["commission_rate"],
                 fields["is_active"], fields["remark"], code))
        write_audit(conn, "salespersons", old["id"], "UPDATE", dict(old), fields, operator)
        conn.commit()
        return {"ok": True, "errors": [], "code": code}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"业务员更新失败: {e}"]}
    finally:
        conn.close()


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


# 报价/合同头的"付款条件/包装条款"下拉预置值 (2026-08-02 老板: 付款条件以后影响账期计算/
# 业务员提成/预计回款时间; 包装条款针对整单, 如打托盘/装箱/装袋。均为"预置+历史值下拉, 可手填"模式)
PAYMENT_TERM_PRESETS = (
    "TT 出厂前付清",
    "TT 30% 定金, 70% 发货前付清",
    "TT 30% 定金, 70% 见提单副本付款",
    "月结 30 天",
    "月结 60 天",
    "LC 即期",
)
PACKING_PRESETS = (
    "编织袋装",
    "纸箱装",
    "编织袋装+打托盘",
    "纸箱装+打托盘",
    "散装",
    "按客户指定包装",
)


def doc_header_term_options(field: str, limit: int = 10) -> list[str]:
    """付款条件/包装条款下拉清单: 预置值在前, 报价+合同的历史使用值(频次倒序)去重追加在后"""
    if field == "payment_term":
        presets = PAYMENT_TERM_PRESETS
    elif field == "packing":
        presets = PACKING_PRESETS
    else:
        raise ValueError(f"不允许下拉的字段: {field} (白名单: payment_term/packing)")
    rows = list_options(
        f"SELECT v, COUNT(*) AS cnt FROM ("
        f"SELECT {field} AS v FROM quotations WHERE {field} IS NOT NULL AND {field}!='' "
        f"UNION ALL "
        f"SELECT {field} AS v FROM sales_contracts WHERE {field} IS NOT NULL AND {field}!=''"
        f") t GROUP BY v ORDER BY cnt DESC LIMIT %s",
        (limit,),
    )
    out = list(presets)
    for r in rows:
        if r["v"] not in out:
            out.append(r["v"])
    return out


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
            # 标签纸是计量辅料: 建档即给 AUX 仓零库存行
            if aux_type == "label_paper":
                cur.execute(
                    "INSERT IGNORE INTO aux_inventory (aux_code, warehouse_code, quantity) VALUES (%s, 'AUX', 0)",
                    (code,),
                )
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
            # 标签纸是计量辅料: 建档即给 AUX 仓零库存行, 收发存页立即可见可操作
            if clean.get("aux_type") == "label_paper":
                cur.execute(
                    "INSERT IGNORE INTO aux_inventory (aux_code, warehouse_code, quantity) VALUES (%s, 'AUX', 0)",
                    (clean["aux_code"],),
                )
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
            # 存在性 + 类型护栏: 纯档案辅料(包装/喷码等)不计量, 不能收发
            cur.execute("SELECT aux_type FROM aux_materials WHERE aux_code=%s AND is_active=1 LIMIT 1", (aux_code,))
            mat = cur.fetchone()
            if not mat:
                conn.rollback()
                return {"ok": False, "errors": [f"辅料不存在或已停用: {aux_code}"], "move_no": None, "after_qty": None}
            if mat["aux_type"] != "label_paper":
                conn.rollback()
                return {"ok": False,
                        "errors": [f"{aux_code} 是{mat['aux_type']}类纯档案辅料, 不计量不进收发存 (目前只有标签纸管库存)"],
                        "move_no": None, "after_qty": None}
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


# ──────────────────────────────────────────────────────────────
# 辅料采购需求 (2026-08-02 老板): 合同录入缺料提示可"下推采购需求单"
# 只登记需求, 不联动库存; 采购到货后走辅料入库 (aux_stock_move source_type='purchase')
# 消化, 状态人工流转 pending→ordered→received (后续模块可自动对账)
# ──────────────────────────────────────────────────────────────

def aux_create_purchase_requests(lines: list[dict], source_type: str = "manual",
                                 source_no: str = "", operator: str = "frontend-react") -> dict:
    """批量下推辅料采购需求: 每行一条记录, req_no=PR+日期+3位流水顺排。任何一行失败整体回滚"""
    errors: list[str] = []
    if source_type not in ("contract_label", "manual"):
        errors.append(f"来源类型无效: {source_type}")
    if not lines:
        errors.append("至少需要一行需求")
    rows = []
    for i, ln in enumerate(lines, 1):
        aux_code = (ln.get("aux_code") or "").strip()
        try:
            qty = int(ln.get("quantity"))
            if qty <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"第{i}行({aux_code or '?'}): 需求数量必须为正整数")
            continue
        rows.append({"aux_code": aux_code, "quantity": qty,
                     "remark": (ln.get("remark") or "").strip()})
    if errors:
        return {"ok": False, "errors": errors, "req_nos": []}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute("SELECT 1 FROM aux_materials WHERE aux_code=%s AND is_active=1", (r["aux_code"],))
                if not cur.fetchone():
                    errors.append(f"辅料不存在或已停用: {r['aux_code']}")
            if errors:
                conn.rollback()
                return {"ok": False, "errors": errors, "req_nos": []}
            d = date.today().isoformat().replace("-", "")[:8]
            cur.execute(
                "SELECT req_no FROM aux_purchase_requests WHERE req_no LIKE %s ORDER BY req_no DESC LIMIT 1",
                (f"PR{d}%",),
            )
            last = cur.fetchone()
            seq = int(last["req_no"][-3:]) if last else 0
            req_nos = []
            for r in rows:
                seq += 1
                req_no = f"PR{d}{seq:03d}"
                cur.execute(
                    "INSERT INTO aux_purchase_requests (req_no, aux_code, quantity, source_type, source_no, remark, operator) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (req_no, r["aux_code"], r["quantity"], source_type, source_no, r["remark"], operator),
                )
                req_nos.append(req_no)
                write_audit(conn, "aux_purchase_requests", cur.lastrowid, "INSERT", None,
                            {"req_no": req_no, "aux_code": r["aux_code"], "quantity": r["quantity"],
                             "source": f"{source_type}:{source_no}"}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "req_nos": req_nos}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"采购需求落库失败: {e}"], "req_nos": []}
    finally:
        conn.close()


def aux_purchase_requests(status: str | None = None) -> list[dict]:
    """采购需求清单 (带辅料名称/单位); status=pending 看待采购"""
    sql = """SELECT r.id, r.req_no, r.aux_code, m.name, m.unit, r.quantity,
                    r.source_type, r.source_no, r.status, r.remark, r.operator, r.created_at
             FROM aux_purchase_requests r
             JOIN aux_materials m ON m.aux_code = r.aux_code"""
    params: tuple = ()
    if status:
        sql += " WHERE r.status=%s"
        params = (status,)
    return list_options(sql + " ORDER BY r.id DESC", params)


# ──────────────────────────────────────────────────────────────
# 客户建档 (2026-08-02 老板): 编号 Q+3位顺推建议 (Q024/Q025 → Q026), 可手改
# 品牌/喷码等"按客户历史值下拉"依赖这里的建档, 客户是整条单据链的源头
# ──────────────────────────────────────────────────────────────

CUSTOMER_FIELDS = ("code", "name", "contact_person", "phone", "address",
                   "bank_account", "brand_name", "company_profiles", "billing_profiles", "remark")


def suggest_customer_code(letter: str | None = None) -> str:
    """建议下一个客户编号 (2026-08-11 老板规则: 字母+4位数字补全)。

    letter = 业务员代码 (customers 编码首字母)。默认 Q (公共/非业务员引入序列)。
    数字段 = salespersons.digit (首位, 业务员数字编码) + 3位流水。
    新业务员/空序列 → 从 001 起推荐 ("找相应的空值推荐")。
    可手改, 这只是建议值。历史 Q+3位 (Q024/Q025) 已补全为 Q0024/Q0025。
    """
    letter = (letter or "Q").strip().upper()[:1] or "Q"
    digit = None
    try:
        rows = list_options("SELECT digit FROM salespersons WHERE code=%s AND is_active=1", (letter,))
        if rows:
            digit = str(rows[0]["digit"])
    except Exception:
        pass  # salespersons 表未建(老库) 时兜底
    if digit is None:
        digit = "0" if letter == "Q" else None
    if digit is None:
        return ""  # 未知业务员且无档案: 不给建议, 让人先建业务员档案
    prefix = f"{letter}{digit}"
    rows = list_options("SELECT code FROM customers WHERE code LIKE %s", (f"{prefix}%",))
    max_seq = 0
    for r in rows:
        suffix = r["code"][len(prefix):]
        # 只认恰好 3 位流水的合规码 (字母+digit+3位=字母+4位数字);
        # D11150 这类历史 5 位异常码不参与推荐, 否则会推出 D11151 违反规则
        if suffix.isdigit() and len(suffix) == 3:
            max_seq = max(max_seq, int(suffix))
    if max_seq >= 999:
        return ""  # 该业务员的 3 位流水用尽 (999 个客户): 不给建议, 需老板定扩段规则
    return f"{prefix}{max_seq + 1:03d}"


# 客户编码规则 (2026-08-11 老板定):
#   字母 + 四位数字补全。字母 = 当前负责业务员代码; 数字 = 客户终身唯一号,
#   其中第一位数字 = 首次把客户引入系统的业务员数字编码。
#   客户更换业务员只换字母, 四位数字不再变化 (所以 A8039/D8039 是同一客户的沿革)。
CUSTOMER_CODE_RE = re.compile(r"^[A-Z]\d{4}$")


def create_customer(data: dict, operator: str = "frontend-react") -> dict:
    """客户建档: 编号唯一 + 名称必填 + 编号格式(字母+4位数字), 写审计"""
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    errors: list[str] = []
    if not code:
        errors.append("缺少客户编号 code")
    elif not CUSTOMER_CODE_RE.match(code):
        errors.append(f"客户编号格式应为 字母+4位数字 (如 Q0026): {code}。"
                      "字母=负责业务员, 数字=客户终身唯一号(首位=首次引入的业务员数字编码)")
    if not name:
        errors.append("缺少客户名称 name")
    if errors:
        return {"ok": False, "errors": errors, "code": None}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM customers WHERE code=%s", (code,))
            if cur.fetchone():
                conn.rollback()
                return {"ok": False, "errors": [f"客户编号已存在: {code}"], "code": None}
            clean = {k: (data.get(k) or "").strip() if isinstance(data.get(k), str) else data.get(k)
                     for k in CUSTOMER_FIELDS if data.get(k) not in (None, "")}
            clean["code"], clean["name"] = code, name
            cols = ", ".join(clean.keys())
            phs = ", ".join(["%s"] * len(clean))
            cur.execute(f"INSERT INTO customers ({cols}) VALUES ({phs})", tuple(clean.values()))
            record_id = cur.lastrowid
        write_audit(conn, "customers", record_id, "INSERT", None,
                    {"code": code, "name": name}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "code": code}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"客户建档失败: {e}"], "code": None}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# 单据录入 (F2.6): 报价 / 合同 / 发货 —— 头+明细单事务落库
# 原则:
#   - 派生全部后端算 (total_weight/unit_price/subtotal/汇率带出/总额), 不信前端
#   - ADR-0005 快照重量: weight_per_unit 从 products.weight 带出存行上,
#     客户谈价改重量只改行快照, products.weight 永不被单据改动
#   - 任何一行校验失败 → 整体回滚, 脏数据不进库
# ──────────────────────────────────────────────────────────────

DOC_KINDS = {
    "quotation": ("quotations", "quote_no", "QT"),
    "contract": ("sales_contracts", "contract_no", "SC"),
    "delivery": ("delivery_orders", "delivery_no", "DN"),
    "stock_in": ("stock_in", "in_no", "IN"),
    "stock_out": ("stock_out", "out_no", "OUT"),
}

TRADE_TERMS = ("FOB", "CIF", "CFR", "EXW")


def suggest_doc_no(kind: str, day: str | None = None) -> dict:
    """单号建议: 前缀+日期+3位当日流水 (如 QT20260802001)。用户可手改。"""
    if kind not in DOC_KINDS:
        return {"ok": False, "doc_no": None, "error": f"未知单据类型: {kind}"}
    table, col, prefix = DOC_KINDS[kind]
    d = (day or date.today().isoformat()).replace("-", "")[:8]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {col} FROM {table} WHERE {col} LIKE %s ORDER BY {col} DESC LIMIT 1",
                (f"{prefix}{d}%",),
            )
            row = cur.fetchone()
        seq = int(row[col][-3:]) + 1 if row else 1
        return {"ok": True, "doc_no": f"{prefix}{d}{seq:03d}", "error": None}
    finally:
        conn.close()


def list_products_picker(customer_code: str | None = None) -> list[dict]:
    """明细行物料选择器: 编码/规格/品牌/快照重量/单件体积/标签纸 一次带齐"""
    sql = """SELECT material_id, spec, brand, product_category, weight, volume, label_paper
             FROM products WHERE is_active=1"""
    params: tuple = ()
    if customer_code:
        sql += " AND customer_code=%s"
        params = (customer_code,)
    return list_options(sql + " ORDER BY material_id", params)


def list_quotations(customer_code: str | None = None) -> list[dict]:
    """报价单下拉 (转合同源头): 未取消的都列出, 已转合同的标注"""
    sql = """SELECT quote_no, customer_code, quote_type, quote_date, total_amount, currency, status
             FROM quotations WHERE status != 'cancelled'"""
    params: tuple = ()
    if customer_code:
        sql += " AND customer_code=%s"
        params = (customer_code,)
    return list_options(sql + " ORDER BY quote_date DESC, quote_no DESC", params)


def get_quotation(quote_no: str) -> dict:
    """取报价头+明细 (转合同预填用)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM quotations WHERE quote_no=%s", (quote_no,))
            header = cur.fetchone()
            if not header:
                return {"found": False, "header": None, "items": []}
            cur.execute(
                """SELECT qi.*, p.spec, p.volume AS product_volume
                   FROM quotation_items qi LEFT JOIN products p ON p.material_id = qi.material_id
                   WHERE qi.quote_no=%s ORDER BY qi.item_no""",
                (quote_no,),
            )
            items = list(cur.fetchall())
        return {"found": True, "header": header, "items": items}
    finally:
        conn.close()


def get_contract_pending(contract_no: str) -> dict:
    """取合同未发明细 (发货录入用): pending = quantity - delivered_qty"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT contract_no, customer_code, status, currency FROM sales_contracts WHERE contract_no=%s",
                (contract_no,),
            )
            header = cur.fetchone()
            if not header:
                return {"found": False, "header": None, "items": []}
            cur.execute(
                """SELECT ci.item_no, ci.material_id, ci.quantity, ci.delivered_qty,
                          (ci.quantity - ci.delivered_qty) AS pending_qty,
                          ci.unit_price, p.spec, p.volume
                   FROM sales_contract_items ci LEFT JOIN products p ON p.material_id = ci.material_id
                   WHERE ci.contract_no=%s ORDER BY ci.item_no""",
                (contract_no,),
            )
            items = list(cur.fetchall())
        return {"found": True, "header": header, "items": items}
    finally:
        conn.close()


def _doc_insert(cur, table: str, row: dict) -> int:
    """按表实际列过滤后插入 (与 insert_row 同款防御)"""
    cur.execute(f"SHOW COLUMNS FROM {table}")
    valid = {c["Field"] for c in cur.fetchall()} - {"id", "created_at", "updated_at"}
    clean = {k: v for k, v in row.items() if k in valid and v is not None and v != ""}
    cols = ", ".join(clean.keys())
    cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join(['%s'] * len(clean))})",
                tuple(clean.values()))
    return cur.lastrowid


def _fetch_product(cur, material_id: str) -> dict | None:
    cur.execute(
        "SELECT material_id, weight, volume, spec, label_paper FROM products WHERE material_id=%s AND is_active=1",
        (material_id,),
    )
    return cur.fetchone()


def _pos(v, digits=4) -> float | None:
    """正数解析, 失败/非正返回 None"""
    try:
        f = float(v)
        return round(f, digits) if f > 0 else None
    except (TypeError, ValueError):
        return None


def create_quotation(header: dict, items: list[dict], operator: str = "frontend-react") -> dict:
    """报价单落库: 头+明细单事务。定价公式 unit_price = 快照单重 × 报价系数 (ADR-0005)"""
    errors: list[str] = []
    quote_no = (header.get("quote_no") or "").strip()
    customer = (header.get("customer_code") or "").strip()
    quote_date = (header.get("quote_date") or "").strip()
    currency = (header.get("currency") or "USD").strip().upper()
    if not quote_no:
        errors.append("缺少报价号 quote_no")
    if not customer:
        errors.append("缺少客户 customer_code")
    if not _is_date(quote_date):
        errors.append(f"报价日期无效: {quote_date}")
    if header.get("trade_terms") and header["trade_terms"] not in TRADE_TERMS:
        errors.append(f"贸易术语必须是 {TRADE_TERMS}, 收到: {header['trade_terms']}")
    delivery_days = header.get("delivery_days")
    if delivery_days not in (None, ""):
        try:
            delivery_days = int(delivery_days)
            if delivery_days <= 0:
                errors.append("交货时长必须是正整数(天)")
        except (TypeError, ValueError):
            errors.append(f"交货时长必须是正整数(天), 收到: {delivery_days}")
            delivery_days = None
    else:
        delivery_days = None
    if not items:
        errors.append("至少需要一行明细")
    if errors:
        return {"ok": False, "errors": errors, "doc_no": None}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM customers WHERE code=%s", (customer,))
            if not cur.fetchone():
                errors.append(f"客户不存在: {customer}")
            cur.execute("SELECT 1 FROM quotations WHERE quote_no=%s", (quote_no,))
            if cur.fetchone():
                errors.append(f"报价号已存在: {quote_no}")
            if header.get("parent_quote_no"):
                cur.execute("SELECT 1 FROM quotations WHERE quote_no=%s", (header["parent_quote_no"],))
                if not cur.fetchone():
                    errors.append(f"派生源报价不存在: {header['parent_quote_no']}")

            rows = []
            for i, it in enumerate(items, 1):
                mid = (it.get("material_id") or "").strip()
                p = _fetch_product(cur, mid) if mid else None
                if not p:
                    errors.append(f"第{i}行: 物料不存在或已停用「{mid}」(可先到物料录入建档)")
                    continue
                coeff = _pos(it.get("price_coefficient"))
                qty = _pos(it.get("quantity"), 0)
                if coeff is None:
                    errors.append(f"第{i}行({mid}): 报价系数必须为正数")
                if qty is None:
                    errors.append(f"第{i}行({mid}): 数量必须为正整数")
                if coeff is None or qty is None:
                    continue
                # ADR-0005 快照重量: 行上带的手填值优先, 否则 products.weight 快照
                w = _pos(it.get("weight_per_unit")) or _pos(p.get("weight"))
                if w is None:
                    errors.append(f"第{i}行({mid}): 单卷重量为空且主数据无重量, 请手填")
                    continue
                vol = _pos(it.get("volume")) or _pos(p.get("volume")) or 0.0
                unit_price = round(w * coeff, 2)
                q = int(qty)
                rows.append({
                    "quote_no": quote_no,
                    "item_no": (it.get("item_no") or "").strip() or f"{i:03d}",
                    "material_id": mid,
                    "group_code": (it.get("group_code") or "").strip(),
                    "price_coefficient": coeff,
                    "weight_per_unit": w,
                    "quantity": q,
                    "total_weight": round(w * q, 3),
                    "unit_price": unit_price,
                    "subtotal": round(unit_price * q, 2),
                    "volume": vol,
                    "total_volume": round(vol * q, 2),
                    "remark": (it.get("remark") or "").strip(),
                })
            # 行号/物料查重 (同单内)
            seen_no, seen_mid = set(), set()
            for r in rows:
                if r["item_no"] in seen_no:
                    errors.append(f"行号重复: {r['item_no']}")
                if r["material_id"] in seen_mid:
                    errors.append(f"同报价单物料重复: {r['material_id']}")
                seen_no.add(r["item_no"])
                seen_mid.add(r["material_id"])
            if errors:
                conn.rollback()
                return {"ok": False, "errors": errors, "doc_no": None}

            rate = _pos(header.get("exchange_rate"))
            if rate is None:
                rate, _note = lookup_exchange_rate(conn, currency, quote_date)
            if rate is None:
                conn.rollback()
                return {"ok": False, "errors": [f"缺少 {currency} 汇率 (请先到汇率录入补 {quote_date[:7]} 当月汇率)"], "doc_no": None}

            total = round(sum(r["subtotal"] for r in rows), 2)
            head_row = {
                "quote_no": quote_no, "customer_code": customer,
                "quote_type": header.get("quote_type") or "brief",
                "parent_quote_no": header.get("parent_quote_no") or None,
                "version": int(header.get("version") or 1),
                "quote_date": quote_date,
                "valid_until": header.get("valid_until") or None,
                "total_amount": total, "currency": currency, "exchange_rate": rate,
                "total_amount_cny": round(total * rate, 2),
                "total_volume": round(sum(r["total_volume"] for r in rows), 2),
                "status": header.get("status") or "draft",
                "trade_terms": header.get("trade_terms") or "FOB",
                "port_loading": header.get("port_loading") or "",
                "port_discharge": header.get("port_discharge") or "",
                "payment_term": header.get("payment_term") or None,
                "packing": header.get("packing") or None,
                "delivery_days": delivery_days,
                "remark": header.get("remark") or "",
            }
            _doc_insert(cur, "quotations", head_row)
            for r in rows:
                _doc_insert(cur, "quotation_items", r)
            record_id = cur.lastrowid
        write_audit(conn, "quotations", record_id, "INSERT", None,
                    {"quote_no": quote_no, "items": len(rows), "total": total, "currency": currency}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "doc_no": quote_no,
                "total_amount": total, "exchange_rate": rate, "total_amount_cny": head_row["total_amount_cny"],
                "warnings": []}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"报价单落库失败: {e}"], "doc_no": None}
    finally:
        conn.close()


def create_contract(header: dict, items: list[dict], operator: str = "frontend-react") -> dict:
    """销售合同落库: 头+明细单事务。source_quote_no 传入时同事务把报价标记已转合同"""
    errors: list[str] = []
    contract_no = (header.get("contract_no") or "").strip()
    customer = (header.get("customer_code") or "").strip()
    sign_date = (header.get("sign_date") or "").strip()
    currency = (header.get("currency") or "USD").strip().upper()
    source_quote = (header.get("source_quote_no") or "").strip()
    if not contract_no:
        errors.append("缺少合同号 contract_no")
    if not customer:
        errors.append("缺少客户 customer_code")
    if not _is_date(sign_date):
        errors.append(f"签订日期无效: {sign_date}")
    if header.get("trade_terms") and header["trade_terms"] not in TRADE_TERMS:
        errors.append(f"贸易术语必须是 {TRADE_TERMS}, 收到: {header['trade_terms']}")
    if not items:
        errors.append("至少需要一行明细")
    if errors:
        return {"ok": False, "errors": errors, "doc_no": None}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM customers WHERE code=%s", (customer,))
            if not cur.fetchone():
                errors.append(f"客户不存在: {customer}")
            cur.execute("SELECT 1 FROM sales_contracts WHERE contract_no=%s", (contract_no,))
            if cur.fetchone():
                errors.append(f"合同号已存在: {contract_no}")
            if source_quote:
                cur.execute(
                    "SELECT status, customer_code FROM quotations WHERE quote_no=%s", (source_quote,))
                q = cur.fetchone()
                if not q:
                    errors.append(f"源报价不存在: {source_quote}")
                elif q["customer_code"] != customer:
                    errors.append(f"源报价 {source_quote} 属于客户 {q['customer_code']}, 与合同客户不一致")
                elif q["status"] == "converted":
                    errors.append(f"源报价 {source_quote} 已转过合同")
                elif q["status"] == "cancelled":
                    errors.append(f"源报价 {source_quote} 已取消")

            rows = []
            for i, it in enumerate(items, 1):
                mid = (it.get("material_id") or "").strip()
                p = _fetch_product(cur, mid) if mid else None
                if not p:
                    errors.append(f"第{i}行: 物料不存在或已停用「{mid}」(可先克隆建物料或到物料录入建档)")
                    continue
                qty = _pos(it.get("quantity"), 0)
                price = _pos(it.get("unit_price"))
                if qty is None:
                    errors.append(f"第{i}行({mid}): 数量必须为正整数")
                if price is None:
                    errors.append(f"第{i}行({mid}): 单价必须为正数")
                if qty is None or price is None:
                    continue
                q = int(qty)
                rows.append({
                    "contract_no": contract_no,
                    "item_no": (it.get("item_no") or "").strip() or f"{i:03d}",
                    "material_id": mid,
                    "quantity": q,
                    "unit_price": price,
                    "subtotal": round(price * q, 2),
                    "volume_subtotal": round((_pos(p.get("volume")) or 0.0) * q, 2),
                    "delivered_qty": 0,
                    "remark": (it.get("remark") or "").strip(),
                })
            seen_no, seen_mid = set(), set()
            for r in rows:
                if r["item_no"] in seen_no:
                    errors.append(f"行号重复: {r['item_no']}")
                if r["material_id"] in seen_mid:
                    errors.append(f"同合同物料重复: {r['material_id']}")
                seen_no.add(r["item_no"])
                seen_mid.add(r["material_id"])
            if errors:
                conn.rollback()
                return {"ok": False, "errors": errors, "doc_no": None}

            rate = _pos(header.get("exchange_rate"))
            if rate is None:
                rate, _note = lookup_exchange_rate(conn, currency, sign_date)
            if rate is None:
                conn.rollback()
                return {"ok": False, "errors": [f"缺少 {currency} 汇率 (请先到汇率录入补 {sign_date[:7]} 当月汇率)"], "doc_no": None}

            total = round(sum(r["subtotal"] for r in rows), 2)
            head_row = {
                "contract_no": contract_no, "customer_code": customer,
                "sign_date": sign_date,
                "delivery_deadline": header.get("delivery_deadline") or None,
                "total_amount": total, "currency": currency, "exchange_rate": rate,
                "total_amount_cny": round(total * rate, 2),
                "total_volume": round(sum(r["volume_subtotal"] for r in rows), 2),
                "trade_terms": header.get("trade_terms") or "FOB",
                "port_loading": header.get("port_loading") or "",
                "port_discharge": header.get("port_discharge") or "",
                "freight": _pos(header.get("freight")) or 0,
                "insurance": _pos(header.get("insurance")) or 0,
                "status": header.get("status") or "confirmed",
                "payment_term": header.get("payment_term") or None,
                "packing": header.get("packing") or None,
                "remark": header.get("remark") or "",
            }
            _doc_insert(cur, "sales_contracts", head_row)
            for r in rows:
                _doc_insert(cur, "sales_contract_items", r)
            if source_quote:
                cur.execute(
                    "UPDATE quotations SET status='converted', converted_contract_no=%s WHERE quote_no=%s",
                    (contract_no, source_quote),
                )
            record_id = cur.lastrowid
        write_audit(conn, "sales_contracts", record_id, "INSERT", None,
                    {"contract_no": contract_no, "items": len(rows), "total": total,
                     "source_quote": source_quote or None}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "doc_no": contract_no,
                "total_amount": total, "exchange_rate": rate, "total_amount_cny": head_row["total_amount_cny"],
                "warnings": []}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"合同落库失败: {e}"], "doc_no": None}
    finally:
        conn.close()


def create_delivery(header: dict, items: list[dict], operator: str = "frontend-react") -> dict:
    """发货单落库: 头+明细+回写合同已发数, 单事务。
    闸门: 每行发货量 ≤ 合同未发量 (超发拦截); 全部发完合同置 completed, 否则 delivering。
    R11 公斤价反算三列留 pending, 由发货校验(第16步)口径复核, 不在录入时算。
    """
    errors: list[str] = []
    warnings: list[str] = []
    delivery_no = (header.get("delivery_no") or "").strip()
    customer = (header.get("customer_code") or "").strip()
    delivery_date = (header.get("delivery_date") or "").strip()
    # 老板特批低价先发货 (2026-08-14): 默认拦截, 仅当 price_gap_approved 为真
    # 且填写 price_gap_reason 时放行 (原因随审计留痕)
    price_gap_approved = bool(header.get("price_gap_approved"))
    price_gap_reason = (header.get("price_gap_reason") or "").strip()
    if not delivery_no:
        errors.append("缺少发货单号 delivery_no")
    if not customer:
        errors.append("缺少客户 customer_code")
    if not _is_date(delivery_date):
        errors.append(f"发货日期无效: {delivery_date}")
    if not items:
        errors.append("至少需要一行明细")
    if errors:
        return {"ok": False, "errors": errors, "doc_no": None}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM customers WHERE code=%s", (customer,))
            if not cur.fetchone():
                errors.append(f"客户不存在: {customer}")
            cur.execute("SELECT 1 FROM delivery_orders WHERE delivery_no=%s", (delivery_no,))
            if cur.fetchone():
                errors.append(f"发货单号已存在: {delivery_no}")

            rows = []
            touched_contracts: set[str] = set()
            for i, it in enumerate(items, 1):
                cno = (it.get("contract_no") or "").strip()
                ino = (it.get("contract_item_no") or "").strip()
                qty = _pos(it.get("quantity"), 0)
                if not cno or not ino:
                    errors.append(f"第{i}行: 必须关联合同号+合同行号")
                    continue
                cur.execute(
                    """SELECT ci.material_id, ci.quantity, ci.delivered_qty, ci.status AS item_status,
                              ci.unit_price AS item_price,
                              sc.customer_code, sc.status
                       FROM sales_contract_items ci
                       JOIN sales_contracts sc ON sc.contract_no = ci.contract_no
                       WHERE ci.contract_no=%s AND ci.item_no=%s""",
                    (cno, ino),
                )
                ci = cur.fetchone()
                if not ci:
                    errors.append(f"第{i}行: 合同明细不存在 {cno}#{ino}")
                    continue
                if ci["customer_code"] != customer:
                    errors.append(f"第{i}行: 合同 {cno} 属于客户 {ci['customer_code']}, 与发货单客户不一致")
                if ci["status"] == "cancelled":
                    errors.append(f"第{i}行: 合同 {cno} 已取消")
                if ci["item_status"] == "closed":
                    errors.append(f"第{i}行: 合同行 {cno}#{ino} 已关闭(客户放弃余量), 不能再发货")
                if qty is None:
                    errors.append(f"第{i}行({ci['material_id']}): 发货数量必须为正整数")
                    continue
                pending = int(ci["quantity"]) - int(ci["delivered_qty"])
                if int(qty) > pending:
                    errors.append(
                        f"第{i}行({ci['material_id']}): 发货 {int(qty)} 超合同未发 {pending} (合同 {cno}#{ino})")
                    continue
                # 低价先发货拦截 (2026-08-14 老板定, WARN 升级为 ERROR):
                # 同客户同物料, 旧合同还有未发且单价更高, 先发低价合同会造成价差损失。
                # 默认拦截; 客户已协商同意时由老板特批 (price_gap_approved + price_gap_reason) 放行
                cur.execute(
                    """SELECT ci2.contract_no, ci2.item_no, ci2.unit_price,
                              (ci2.quantity - ci2.delivered_qty) AS remain
                       FROM sales_contract_items ci2
                       JOIN sales_contracts sc2 ON sc2.contract_no = ci2.contract_no
                       WHERE sc2.customer_code=%s AND ci2.material_id=%s
                         AND ci2.status='active'
                         AND sc2.status IN ('confirmed','delivering')
                         AND ci2.delivered_qty < ci2.quantity
                         AND NOT (ci2.contract_no=%s AND ci2.item_no=%s)
                         AND ci2.unit_price > %s""",
                    (customer, ci["material_id"], cno, ino, ci["item_price"]),
                )
                gap_hit = False
                for hi in cur.fetchall():
                    loss = round((float(hi["unit_price"]) - float(ci["item_price"])) * int(qty), 2)
                    msg = (
                        f"第{i}行({ci['material_id']}): ⚠️ 高价旧合同 {hi['contract_no']}#{hi['item_no']} "
                        f"还有 {int(hi['remain'])} 卷未发 (单价 {hi['unit_price']} > 本单 {ci['item_price']}), "
                        f"本次先发低价 {int(qty)} 卷, 价差损失约 {loss} (原币/卷价差×卷数)。"
                    )
                    if price_gap_approved and price_gap_reason:
                        warnings.append(msg + f"老板特批放行: {price_gap_reason}")
                    else:
                        errors.append(
                            msg + "已拦截。如客户已协商同意, 由老板在发货单上加 "
                            "price_gap_approved=true 并填写 price_gap_reason 后重试")
                        gap_hit = True
                if gap_hit:
                    continue
                # actual_quantity 闸门: 未显式传默认=quantity; 显式传必须 1<=actual<=pending
                raw_actual = it.get("actual_quantity")
                if raw_actual is None or (isinstance(raw_actual, str) and raw_actual.strip() == ""):
                    actual = int(qty)
                else:
                    try:
                        actual = int(raw_actual)
                    except (TypeError, ValueError):
                        errors.append(f"第{i}行({ci['material_id']}): actual_quantity 必须是整数")
                        continue
                    if actual < 1 or actual > pending:
                        errors.append(
                            f"第{i}行({ci['material_id']}): 实际发货 {actual} 超合同未发 {pending} "
                            f"或小于 1 (合同 {cno}#{ino})"
                        )
                        continue
                p = _fetch_product(cur, ci["material_id"])
                vol = _pos(p.get("volume")) if p else None
                rows.append({
                    "delivery_no": delivery_no,
                    "contract_no": cno,
                    "contract_item_no": ino,
                    "material_id": ci["material_id"],
                    "quantity": int(qty),
                    "actual_quantity": actual,
                    "volume_subtotal": round((vol or 0.0) * int(qty), 2),
                    "remark": (it.get("remark") or "").strip(),
                })
                touched_contracts.add(cno)
            if errors:
                conn.rollback()
                return {"ok": False, "errors": errors, "doc_no": None, "warnings": warnings}

            head_row = {
                "delivery_no": delivery_no, "customer_code": customer,
                "delivery_date": delivery_date,
                "receiver": header.get("receiver") or "",
                "receiver_phone": header.get("receiver_phone") or "",
                "receiver_address": header.get("receiver_address") or "",
                "transport_no": header.get("transport_no") or "",
                "total_volume": round(sum(r["volume_subtotal"] for r in rows), 2),
                "price_gap_approved": 1 if price_gap_approved else 0,
                "price_gap_reason": price_gap_reason if price_gap_approved else "",
                "status": header.get("status") or "confirmed",
                "remark": header.get("remark") or "",
            }
            _doc_insert(cur, "delivery_orders", head_row)
            for r in rows:
                _doc_insert(cur, "delivery_order_items", r)
                cur.execute(
                    """UPDATE sales_contract_items SET delivered_qty = delivered_qty + %s
                       WHERE contract_no=%s AND item_no=%s""",
                    (r["actual_quantity"], r["contract_no"], r["contract_item_no"]),
                )
            # 合同状态联动: 全部发完或关闭 completed, 否则 delivering (不动 cancelled/draft)
            # 2026-08-14 起: closed 行 (客户放弃余量) 不再算 pending
            for cno in touched_contracts:
                cur.execute(
                    """SELECT SUM(quantity - delivered_qty) AS pending FROM sales_contract_items
                       WHERE contract_no=%s AND status='active'""",
                    (cno,),
                )
                left = int(cur.fetchone()["pending"] or 0)
                cur.execute(
                    """UPDATE sales_contracts SET status=%s
                       WHERE contract_no=%s AND status IN ('confirmed','delivering')""",
                    ("completed" if left == 0 else "delivering", cno),
                )
            record_id = cur.lastrowid
        write_audit(conn, "delivery_orders", record_id, "INSERT", None,
                    {"delivery_no": delivery_no, "items": len(rows),
                     "contracts": sorted(touched_contracts),
                     "price_gap_approved": price_gap_approved,
                     "price_gap_reason": price_gap_reason if price_gap_approved else None}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "doc_no": delivery_no,
                "total_volume": head_row["total_volume"],
                "contracts_updated": sorted(touched_contracts), "warnings": warnings}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"发货单落库失败: {e}"], "doc_no": None}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# 合同明细行关闭 (2026-08-14 老板定: 客户可只放弃某一行, 不用整合同关单)
# ──────────────────────────────────────────────────────────────
def close_contract_item(contract_no: str, item_no: str, reason: str,
                        operator: str) -> dict:
    """关闭合同明细行: 客户放弃该行余量, 余量不再计入任何还欠/需求统计。

    幂等: 已关闭的行再次调用直接返回成功。
    联动: 该合同所有行都"发完或关闭"时, 合同自动 completed。
    2026-08-14 起: 关闭原因必填; 放弃余量>5% 的关行进 8501 首页老板复核卡。
    (事前审批待登录权限上线后再做, 见 BUSINESS_RULES 变更记录)
    """
    if not (reason or "").strip():
        return {"ok": False, "errors": ["关闭原因必填 (如: 客户确认放弃余量 / 转其他合同)。"
                                        "无原因的关行无法追溯, 直接拒绝"]}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status, quantity, delivered_qty, remark "
                "FROM sales_contract_items WHERE contract_no=%s AND item_no=%s",
                (contract_no, item_no),
            )
            row = cur.fetchone()
            if not row:
                return {"ok": False, "errors": [f"合同 {contract_no} 没有行号 {item_no}"]}
            if row["status"] == "closed":
                return {"ok": True, "errors": [], "warnings": ["该行已是关闭状态, 无需重复操作"]}
            remaining = int(row["quantity"]) - int(row["delivered_qty"])
            stamp = f" | {date.today().isoformat()} {operator} 关闭(客户放弃余量 {remaining} 卷): {reason}"
            cur.execute(
                "UPDATE sales_contract_items SET status='closed', "
                "remark=%s WHERE id=%s",
                (((row["remark"] or "") + stamp)[:255], row["id"]),
            )
            # 合同状态联动: 剩余 active 行全部发完 → completed
            cur.execute(
                """SELECT SUM(quantity - delivered_qty) AS pending FROM sales_contract_items
                   WHERE contract_no=%s AND status='active'""",
                (contract_no,),
            )
            left = int(cur.fetchone()["pending"] or 0)
            if left == 0:
                cur.execute(
                    """UPDATE sales_contracts SET status='completed'
                       WHERE contract_no=%s AND status IN ('confirmed','delivering')""",
                    (contract_no,),
                )
        write_audit(conn, "sales_contract_items", row["id"], "UPDATE",
                    {"status": "active"}, {"status": "closed", "reason": reason},
                    operator)
        conn.commit()
        warns = []
        if int(row["quantity"]) > 0 and remaining / int(row["quantity"]) > 0.05:
            warns.append(f"⚠️ 放弃余量 {remaining} 卷占合同量 {remaining / int(row['quantity']) * 100:.1f}% (>5%), "
                         f"已列入 8501 首页老板复核清单")
        warns.append(f"已关闭 {contract_no} 行 {item_no}, 放弃余量 {remaining} 卷"
                     + ("; 合同已全部了结, 状态置 completed" if left == 0 else ""))
        return {"ok": True, "errors": [], "warnings": warns}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"关闭合同行失败: {e}"]}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# 成品出入库 (2026-08-02 老板: "要先有入库才有发货")
# 约定 (与 16 步校验口径一致):
#   - 录入=实际发生, 状态直接 confirmed (校验只数 confirmed)
#   - 入库类型: purchase(采购, 需关联PO)/production(生产完工)/return(退货); 调拨走 CSV 暂不进 UI
#   - 出库类型: sale(销售, 需关联发货单)/production(生产领用)/scrap(报废)
#   - 库存结果表 inventory 与流水 stock_logs 同步维护, 单事务
#   - 负库存: 按项目约定允许"先做后补", 不拦截, 但 warnings 显著提示 (校验第6步同款 WARN)
# ──────────────────────────────────────────────────────────────

STOCK_IN_TYPES = ("purchase", "production", "transfer", "return", "adjust")
STOCK_OUT_TYPES = ("sale", "production", "transfer", "scrap", "adjust")


def list_deliveries() -> list[dict]:
    """发货单下拉 (销售出库关联用)"""
    return list_options(
        "SELECT delivery_no, customer_code, delivery_date, status FROM delivery_orders "
        "WHERE status != 'cancelled' ORDER BY delivery_date DESC, delivery_no DESC")


def list_purchase_orders() -> list[dict]:
    """采购单下拉 (采购入库关联用)"""
    return list_options(
        "SELECT po_no, supplier_code, order_date, status FROM purchase_orders "
        "WHERE status != 'cancelled' ORDER BY order_date DESC, po_no DESC")


def _validate_stock_items(cur, items: list[dict]) -> tuple[list[dict], list[str]]:
    """出入库明细公共校验: 物料存在且启用 + 数量正整数 + 同单物料查重"""
    errors: list[str] = []
    rows: list[dict] = []
    seen: set[str] = set()
    for i, it in enumerate(items, 1):
        mid = (it.get("material_id") or "").strip()
        p = _fetch_product(cur, mid) if mid else None
        if not p:
            errors.append(f"第{i}行: 物料不存在或已停用「{mid}」")
            continue
        qty = _pos(it.get("quantity"), 0)
        if qty is None:
            errors.append(f"第{i}行({mid}): 数量必须为正整数")
            continue
        if mid in seen:
            errors.append(f"同单物料重复: {mid} (请合并成一行)")
        seen.add(mid)
        rows.append({"material_id": mid, "quantity": int(qty),
                     "remark": (it.get("remark") or "").strip()})
    return rows, errors


def _apply_inventory(cur, warehouse: str, rows: list[dict], sign: int,
                     source_type: str, source_id: int, source_no: str) -> list[str]:
    """库存结果表 ±qty + 写流水 (逐行算 after_qty 运行结余)。返回负库存警告清单"""
    warnings: list[str] = []
    balance: dict[str, int] = {}
    for r in rows:
        mid = r["material_id"]
        if mid not in balance:
            cur.execute(
                "SELECT quantity FROM inventory WHERE material_id=%s AND warehouse_code=%s FOR UPDATE",
                (mid, warehouse),
            )
            row = cur.fetchone()
            balance[mid] = int(row["quantity"]) if row else 0
        after = balance[mid] + sign * r["quantity"]
        cur.execute(
            """INSERT INTO inventory (material_id, warehouse_code, quantity) VALUES (%s,%s,%s)
               ON DUPLICATE KEY UPDATE quantity=%s""",
            (mid, warehouse, after, after),
        )
        cur.execute(
            """INSERT INTO stock_logs (material_id, warehouse_code, change_qty, after_qty,
                                       source_type, source_id, source_no, remark)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (mid, warehouse, sign * r["quantity"], after, source_type, source_id, source_no, r["remark"]),
        )
        if after < 0:
            warnings.append(f"{mid} 在 {warehouse} 仓出库后库存为 {after} (允许先做后补, 请尽快补入库)")
        balance[mid] = after
    return warnings


def create_stock_in(header: dict, items: list[dict], operator: str = "frontend-react") -> dict:
    """入库单落库: 头+明细+库存增加+流水, 单事务, 状态直接 confirmed"""
    errors: list[str] = []
    in_no = (header.get("in_no") or "").strip()
    in_type = (header.get("in_type") or "production").strip()
    warehouse = (header.get("warehouse_code") or "").strip()
    in_date = (header.get("in_date") or "").strip()
    po_no = (header.get("po_no") or "").strip()
    if not in_no:
        errors.append("缺少入库单号 in_no")
    if in_type not in STOCK_IN_TYPES:
        errors.append(f"入库类型必须是 {STOCK_IN_TYPES}, 收到: {in_type}")
    if in_type == "purchase" and not po_no:
        errors.append("采购入库必须关联采购单号 po_no")
    if in_type != "purchase":
        po_no = ""
    # 2026-08-02 老板: 生产入库挂合同 (按单生产); 采购/退货与合同无关
    contract_no = (header.get("contract_no") or "").strip()
    if in_type == "production" and not contract_no:
        errors.append("生产入库必须关联合同号 contract_no")
    if in_type != "production":
        contract_no = ""
    # 2026-08-10: 调拨入库需 transfer_ref (与调拨出库同号配对, 校验第14步);
    # adjust=期初/调整入库, 不挂任何单据 (系统切换建账专用)
    transfer_ref = (header.get("transfer_ref") or "").strip()
    if in_type == "transfer" and not transfer_ref:
        errors.append("调拨入库必须填调拨关联号 transfer_ref (与调拨出库同号)")
    if in_type != "transfer":
        transfer_ref = ""
    if not warehouse:
        errors.append("缺少仓库 warehouse_code")
    if not _is_date(in_date):
        errors.append(f"入库日期无效: {in_date}")
    if not items:
        errors.append("至少需要一行明细")
    if errors:
        return {"ok": False, "errors": errors, "doc_no": None}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM warehouses WHERE code=%s", (warehouse,))
            if not cur.fetchone():
                errors.append(f"仓库不存在: {warehouse}")
            cur.execute("SELECT 1 FROM stock_in WHERE in_no=%s", (in_no,))
            if cur.fetchone():
                errors.append(f"入库单号已存在: {in_no}")
            if po_no:
                cur.execute("SELECT status FROM purchase_orders WHERE po_no=%s", (po_no,))
                po = cur.fetchone()
                if not po:
                    errors.append(f"采购单不存在: {po_no}")
                elif po["status"] == "cancelled":
                    errors.append(f"采购单 {po_no} 已取消")
            if contract_no:
                cur.execute("SELECT status FROM sales_contracts WHERE contract_no=%s", (contract_no,))
                sc = cur.fetchone()
                if not sc:
                    errors.append(f"合同不存在: {contract_no}")
                elif sc["status"] == "cancelled":
                    errors.append(f"合同 {contract_no} 已取消")
                else:
                    cur.execute(
                        "SELECT material_id FROM sales_contract_items WHERE contract_no=%s",
                        (contract_no,),
                    )
                    contract_materials = {r["material_id"] for r in cur.fetchall()}
            rows, item_errors = _validate_stock_items(cur, items)
            errors.extend(item_errors)
            if contract_no and not errors:
                for r in rows:
                    if r["material_id"] not in contract_materials:
                        errors.append(f"物料 {r['material_id']} 不在合同 {contract_no} 的明细里, 不能挂这个合同")
            if errors:
                conn.rollback()
                return {"ok": False, "errors": errors, "doc_no": None}

            head_id = _doc_insert(cur, "stock_in", {
                "in_no": in_no, "in_type": in_type, "warehouse_code": warehouse,
                "po_no": po_no or None, "operator": operator, "in_date": in_date,
                "transfer_ref": transfer_ref or None,
                "status": "confirmed", "remark": (header.get("remark") or "").strip(),
            })
            for r in rows:
                _doc_insert(cur, "stock_in_items",
                            {"in_no": in_no, "material_id": r["material_id"],
                             "contract_no": contract_no or None,
                             "quantity": r["quantity"], "remark": r["remark"]})
            warnings = _apply_inventory(cur, warehouse, rows, +1, "stock_in", head_id, in_no)
            # 采购入库联动: 到货量够则推进采购单状态 (部分到货/已全部到货)
            if po_no:
                cur.execute(
                    """UPDATE purchase_orders SET status='received'
                       WHERE po_no=%s AND status IN ('confirmed','partial_received')
                         AND (SELECT COALESCE(SUM(sii.quantity),0) FROM stock_in_items sii
                              JOIN stock_in si ON si.in_no=sii.in_no
                              WHERE si.po_no=%s AND si.status='confirmed')
                           >= (SELECT COALESCE(SUM(quantity),0) FROM purchase_order_items WHERE po_no=%s)""",
                    (po_no, po_no, po_no),
                )
                cur.execute(
                    """UPDATE purchase_orders SET status='partial_received'
                       WHERE po_no=%s AND status='confirmed'""",
                    (po_no,),
                )
        write_audit(conn, "stock_in", head_id, "INSERT", None,
                    {"in_no": in_no, "in_type": in_type, "warehouse": warehouse,
                     "items": len(rows), "po_no": po_no}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "doc_no": in_no, "warnings": warnings}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"入库单落库失败: {e}"], "doc_no": None}
    finally:
        conn.close()


def create_stock_out(header: dict, items: list[dict], operator: str = "frontend-react") -> dict:
    """出库单落库: 头+明细+库存扣减+流水, 单事务, 状态直接 confirmed。
    负库存不拦截 (项目约定: 允许先做后补), 但 warnings 显著提示"""
    errors: list[str] = []
    out_no = (header.get("out_no") or "").strip()
    out_type = (header.get("out_type") or "sale").strip()
    warehouse = (header.get("warehouse_code") or "").strip()
    out_date = (header.get("out_date") or "").strip()
    delivery_no = (header.get("delivery_no") or "").strip()
    if not out_no:
        errors.append("缺少出库单号 out_no")
    if out_type not in STOCK_OUT_TYPES:
        errors.append(f"出库类型必须是 {STOCK_OUT_TYPES}, 收到: {out_type}")
    if out_type == "sale" and not delivery_no:
        errors.append("销售出库必须关联发货单号 delivery_no")
    if out_type != "sale":
        delivery_no = ""
    # 2026-08-10: 调拨出库需 transfer_ref (与调拨入库同号配对); adjust=期初历史货物出清
    transfer_ref = (header.get("transfer_ref") or "").strip()
    if out_type == "transfer" and not transfer_ref:
        errors.append("调拨出库必须填调拨关联号 transfer_ref (与调拨入库同号)")
    if out_type != "transfer":
        transfer_ref = ""
    if not warehouse:
        errors.append("缺少仓库 warehouse_code")
    if not _is_date(out_date):
        errors.append(f"出库日期无效: {out_date}")
    if not items:
        errors.append("至少需要一行明细")
    if errors:
        return {"ok": False, "errors": errors, "doc_no": None}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM warehouses WHERE code=%s", (warehouse,))
            if not cur.fetchone():
                errors.append(f"仓库不存在: {warehouse}")
            cur.execute("SELECT 1 FROM stock_out WHERE out_no=%s", (out_no,))
            if cur.fetchone():
                errors.append(f"出库单号已存在: {out_no}")
            if delivery_no:
                cur.execute("SELECT status FROM delivery_orders WHERE delivery_no=%s", (delivery_no,))
                d = cur.fetchone()
                if not d:
                    errors.append(f"发货单不存在: {delivery_no}")
                elif d["status"] == "cancelled":
                    errors.append(f"发货单 {delivery_no} 已取消")
                else:
                    # 2026-08-02 老板: 销售出库挂合同 —— 用户只选发货单,
                    # 后端按 (发货单, 物料) 从发货明细自动反解合同号, 防挂错
                    cur.execute(
                        "SELECT material_id, contract_no FROM delivery_order_items WHERE delivery_no=%s",
                        (delivery_no,),
                    )
                    delivery_contract = {}
                    for r in cur.fetchall():
                        delivery_contract.setdefault(r["material_id"], r["contract_no"])
            rows, item_errors = _validate_stock_items(cur, items)
            errors.extend(item_errors)
            resolved_contracts: dict[str, str] = {}
            if delivery_no and not errors:
                for r in rows:
                    cno = delivery_contract.get(r["material_id"])
                    if not cno:
                        errors.append(f"物料 {r['material_id']} 不在发货单 {delivery_no} 的明细里")
                    else:
                        resolved_contracts[r["material_id"]] = cno
            if errors:
                conn.rollback()
                return {"ok": False, "errors": errors, "doc_no": None}

            head_id = _doc_insert(cur, "stock_out", {
                "out_no": out_no, "out_type": out_type, "warehouse_code": warehouse,
                "delivery_no": delivery_no or None, "operator": operator, "out_date": out_date,
                "transfer_ref": transfer_ref or None,
                "status": "confirmed", "remark": (header.get("remark") or "").strip(),
            })
            for r in rows:
                _doc_insert(cur, "stock_out_items",
                            {"out_no": out_no, "material_id": r["material_id"],
                             "contract_no": resolved_contracts.get(r["material_id"]),
                             "quantity": r["quantity"], "remark": r["remark"]})
            warnings = _apply_inventory(cur, warehouse, rows, -1, "stock_out", head_id, out_no)
        write_audit(conn, "stock_out", head_id, "INSERT", None,
                    {"out_no": out_no, "out_type": out_type, "warehouse": warehouse,
                     "items": len(rows), "delivery_no": delivery_no}, operator)
        conn.commit()
        return {"ok": True, "errors": [], "doc_no": out_no, "warnings": warnings}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "errors": [f"出库单落库失败: {e}"], "doc_no": None}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# 合同 ↔ 库存 关联查询 (2026-08-02 老板: 出入库挂合同, 查询表要看库存关系)
# ──────────────────────────────────────────────────────────────

def list_contract_materials(contract_no: str) -> list[dict]:
    """合同明细物料 picker (生产入库选合同后, 物料下拉过滤为该合同的物料)"""
    return list_options(
        """SELECT ci.material_id, p.spec, p.brand, ci.quantity AS contract_qty, ci.delivered_qty
           FROM sales_contract_items ci
           LEFT JOIN products p ON p.material_id = ci.material_id
           WHERE ci.contract_no=%s ORDER BY ci.item_no""",
        (contract_no,),
    )


def list_delivery_materials(delivery_no: str) -> list[dict]:
    """发货单明细物料 picker (销售出库选发货单后, 物料下拉过滤)"""
    return list_options(
        """SELECT di.material_id, p.spec, p.brand, di.contract_no, di.quantity AS delivery_qty
           FROM delivery_order_items di
           LEFT JOIN products p ON p.material_id = di.material_id
           WHERE di.delivery_no=%s ORDER BY di.contract_item_no""",
        (delivery_no,),
    )


def contract_stock_progress(contract_no: str) -> dict:
    """合同库存进度: 以合同明细为轴, 聚合 生产入库/已发货/销售出库/当前库存。
    生产入库与销售出库按明细行 contract_no 聚合 (2026-08-02 加的关联列);
    库存是该物料全部仓库合计 (库存不挂合同, 刻意设计)"""
    head = list_options(
        """SELECT sc.contract_no, c.name AS customer_name, sc.sign_date, sc.status,
                  sc.total_amount, sc.currency
           FROM sales_contracts sc JOIN customers c ON c.code = sc.customer_code
           WHERE sc.contract_no=%s""",
        (contract_no,),
    )
    if not head:
        return {"found": False, "contract_no": contract_no, "lines": []}
    lines = list_options(
        """SELECT ci.item_no, ci.material_id, p.spec, p.brand,
                  ci.quantity AS contracted, ci.delivered_qty AS delivered,
                  (SELECT COALESCE(SUM(sii.quantity),0)
                     FROM stock_in_items sii JOIN stock_in si ON si.in_no=sii.in_no
                    WHERE sii.contract_no=ci.contract_no AND sii.material_id=ci.material_id
                      AND si.status='confirmed') AS produced_in,
                  (SELECT COALESCE(SUM(soi.quantity),0)
                     FROM stock_out_items soi JOIN stock_out so ON so.out_no=soi.out_no
                    WHERE soi.contract_no=ci.contract_no AND soi.material_id=ci.material_id
                      AND so.status='confirmed') AS stocked_out,
                  (SELECT COALESCE(SUM(quantity),0) FROM inventory
                    WHERE material_id=ci.material_id) AS in_stock
           FROM sales_contract_items ci
           LEFT JOIN products p ON p.material_id = ci.material_id
           WHERE ci.contract_no=%s ORDER BY ci.item_no""",
        (contract_no,),
    )
    return {"found": True, **head[0], "lines": lines}
