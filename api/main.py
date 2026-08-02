#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inventory API — FastAPI HTTP 包装层 (阶段二, 2026-08-01)

定位: 只做 HTTP 路由/参数校验, **业务逻辑零重写**, 全部复用 tools/ 下现有资产:
    - 派生引擎   : csv_to_sql.apply_derived_rules (DERIVED_RULES)
    - 写入规则层 : db_writer.preview_insert / insert_row (两段式提交+写后校验+审计)
    - 下拉数据   : db_writer.list_customers / list_contracts / distinct_categories ...
    - 16 步校验  : local_validator.py (子进程, 对 /app/data/csv)

React 录入端 (frontend/) 通过这些接口连 MySQL; Streamlit 降级为查询/报表。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# tools/ 与 api/ 同级的项目根布局; 容器内为 /app/tools
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import db_writer  # noqa: E402

app = FastAPI(title="Inventory API", version="2.0")

# 开发期 Vite (任意端口) + NAS 局域网访问; 生产由 Nginx 同源反代
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_DIR = Path(os.getenv("CSV_DIR", "/app/data/csv"))


# ──────────────────────────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────────────────────────
class DeriveReq(BaseModel):
    table: str = "products"
    data: dict


class PreviewReq(BaseModel):
    table: str
    data: dict


class InsertReq(BaseModel):
    table: str
    data: dict
    operator: str = "frontend-react"


# ──────────────────────────────────────────────────────────────
# 基础
# ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    try:
        conn = db_writer.get_connection()
        conn.close()
        return {"ok": True, "db": "connected"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "db": str(e)}


# ──────────────────────────────────────────────────────────────
# 下拉选项 (录入表单用)
# ──────────────────────────────────────────────────────────────
@app.get("/api/options/customers")
def opt_customers():
    return db_writer.list_customers()


@app.get("/api/options/contracts")
def opt_contracts(customer_code: str | None = None):
    return db_writer.list_contracts(customer_code or None)


@app.get("/api/options/categories")
def opt_categories():
    """产品原始类别 (真实数据, 按使用频次倒序)"""
    return db_writer.distinct_categories()


@app.get("/api/options/suggest-material-id")
def opt_suggest_material_id(customer_code: str):
    return {"material_id": db_writer.suggest_material_id(customer_code)}


@app.get("/api/options/exchange-rates")
def opt_exchange_rates():
    return db_writer.list_options(
        "SELECT currency, rate_to_cny, effective_date, source FROM exchange_rates "
        "ORDER BY effective_date DESC, currency LIMIT 10"
    )


# ──────────────────────────────────────────────────────────────
# 实时派生 (边填边算, 不落库)
# ──────────────────────────────────────────────────────────────
@app.post("/api/derive")
def derive(req: DeriveReq):
    """物料录入实时派生: 返回补全行/自动算出字段/引擎信息/密度/大类。

    目前仅 products 有完整实时派生 (live_derive_products); 其他表走通用 apply_derived。
    """
    if req.table == "products":
        row, computed, msgs, density, group = db_writer.live_derive_products(req.data)
        return {
            "row": row,
            "computed": sorted(computed),
            "msgs": [{"level": lv, "msg": m} for lv, m in msgs],
            "density": density,
            "category_group": group,
        }
    row, msgs = db_writer.apply_derived(req.table, req.data)
    return {
        "row": row,
        "computed": [],
        "msgs": [{"level": lv, "msg": m} for lv, m in msgs],
        "density": None,
        "category_group": None,
    }


# ──────────────────────────────────────────────────────────────
# 两段式提交 (预览 → 确认 → 落库)
# ──────────────────────────────────────────────────────────────
@app.post("/api/preview")
def preview(req: PreviewReq):
    """①②③: 字段校验 + 派生 + 预览, 不落库"""
    pv = db_writer.preview_insert(req.table, req.data)
    pv["engine_msgs"] = [{"level": lv, "msg": m} for lv, m in pv.get("engine_msgs", [])]
    return pv


@app.post("/api/insert")
def insert(req: InsertReq):
    """①②④⑤⑥: 落库 + 写后子校验 (ERROR 自动回滚) + 审计留痕"""
    result = db_writer.insert_row(req.table, req.data, operator=req.operator)
    result["checks"] = [{"level": lv, "msg": m} for lv, m in result.get("checks", [])]
    if not result["ok"]:
        # 校验不过不是服务器错误, 用 200+ok:false 让前端展示错误列表
        return result
    return result


# ──────────────────────────────────────────────────────────────
# 16 步校验 (子进程, 只读真实 CSV)
# ──────────────────────────────────────────────────────────────
@app.post("/api/validate")
def validate():
    script = TOOLS_DIR / "local_validator.py"
    if not script.exists():
        raise HTTPException(500, f"找不到 {script}")
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--csv-dir", str(CSV_DIR)],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "校验超时 (>180s)")
    return {"exit_code": proc.returncode, "output": (proc.stdout + proc.stderr)[-8000:]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
