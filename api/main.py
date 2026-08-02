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

from fastapi import FastAPI, HTTPException, UploadFile
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


@app.get("/api/options/brands")
def opt_brands(customer_code: str):
    """该客户已有物料用过的品牌 (按频次倒序), 前端仍可手填新品牌"""
    return db_writer.distinct_brands(customer_code)


@app.get("/api/options/field-values")
def opt_field_values(customer_code: str, field: str):
    """该客户某字段的历史值下拉 (白名单字段: 品牌/喷码/物料类型/用料/打线/米标)"""
    try:
        return db_writer.distinct_field_values(customer_code, field)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/options/nominal-inches")
def opt_nominal_inches():
    """标准管型标称英寸序列 (录入页 inch 字段下拉; 建议值=向上取, 可手改)"""
    return db_writer.nominal_inch_options()


@app.get("/api/options/warehouses")
def opt_warehouses():
    return db_writer.list_options("SELECT code, name FROM warehouses ORDER BY code")


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


# ──────────────────────────────────────────────────────────────
# 生产辅料 (标签纸等) — M1 档案+附件 / M2 收发存 / M3 需求提示
# 计划: docs/AUX_MATERIALS_PLAN.md (Q1-Q7 已定案)
# ──────────────────────────────────────────────────────────────
ATTACH_DIR = Path(os.getenv("ATTACH_DIR", "/app/data/attachments"))
AUX_FILE_TYPES = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
AUX_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class AuxMaterialReq(BaseModel):
    data: dict
    operator: str = "frontend-react"


class AuxMoveReq(BaseModel):
    aux_code: str
    warehouse_code: str = "AUX"
    qty: int
    source_type: str           # in: purchase/adjust; out: production_use/scrap/adjust
    source_no: str = ""        # 生产领用时填合同号
    operator: str = "frontend-react"
    move_date: str | None = None
    remark: str = ""


@app.get("/api/aux/material-types")
def aux_material_types():
    """物料类型档案 (录入页下拉源; 成本指导价预留)"""
    return db_writer.list_material_type_profiles()


@app.get("/api/aux/materials")
def aux_materials(aux_type: str | None = None):
    return db_writer.aux_list_materials(aux_type)


@app.post("/api/aux/materials")
def aux_create(req: AuxMaterialReq):
    return db_writer.aux_create_material(req.data, req.operator)


@app.get("/api/aux/inventory")
def aux_inventory(low_only: bool = False):
    return db_writer.aux_inventory_list(low_only)


@app.post("/api/aux/stock-in")
def aux_stock_in(req: AuxMoveReq):
    return db_writer.aux_stock_move(req.aux_code, req.warehouse_code, "in", req.qty,
                                    req.source_type, req.source_no, req.operator,
                                    req.move_date, req.remark)


@app.post("/api/aux/stock-out")
def aux_stock_out(req: AuxMoveReq):
    return db_writer.aux_stock_move(req.aux_code, req.warehouse_code, "out", req.qty,
                                    req.source_type, req.source_no, req.operator,
                                    req.move_date, req.remark)


@app.get("/api/aux/moves")
def aux_moves(aux_code: str | None = None, limit: int = 200):
    return db_writer.aux_moves(aux_code, limit)


@app.get("/api/aux/label-demand")
def aux_label_demand(contract_no: str):
    """合同标签纸需求测算: 需求/库存/缺口 (只提示不扣减)"""
    return db_writer.aux_label_demand(contract_no)


@app.post("/api/aux/materials/{aux_code}/attachments")
async def aux_upload(aux_code: str, file: UploadFile, uploaded_by: str = "frontend-react"):
    """上传辅料附件 (pdf/doc/docx/jpg/png ≤10MB, sha256 去重)"""
    import hashlib
    import uuid as _uuid

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in AUX_FILE_TYPES:
        raise HTTPException(400, f"不支持的文件类型: .{ext} (允许: {sorted(AUX_FILE_TYPES)})")
    content = await file.read()
    if len(content) > AUX_MAX_FILE_SIZE:
        raise HTTPException(400, f"文件超过 10MB ({len(content) / 1024 / 1024:.1f}MB)")
    sha = hashlib.sha256(content).hexdigest()
    rel_path = f"aux/{aux_code}/{_uuid.uuid4().hex[:12]}.{ext}"
    abs_path = ATTACH_DIR / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)
    result = db_writer.aux_add_attachment(aux_code, file.filename or f"file.{ext}",
                                          ext, rel_path, len(content), sha, uploaded_by)
    if not result["ok"]:
        abs_path.unlink(missing_ok=True)
        raise HTTPException(400, "; ".join(result["errors"]))
    if result.get("duplicate"):
        abs_path.unlink(missing_ok=True)  # 内容重复, 不留第二份文件
    return result


@app.get("/api/aux/attachments")
def aux_attachment_list(aux_code: str):
    return db_writer.aux_attachments(aux_code)


@app.get("/api/aux/attachments/{attachment_id}/download")
def aux_download(attachment_id: int):
    from fastapi.responses import FileResponse
    rows = db_writer.list_options(
        "SELECT file_name, file_path FROM aux_attachments WHERE id=%s", (attachment_id,))
    if not rows:
        raise HTTPException(404, "附件不存在")
    abs_path = ATTACH_DIR / rows[0]["file_path"]
    if not abs_path.exists():
        raise HTTPException(404, "附件文件已丢失 (DB 有记录但磁盘没有)")
    return FileResponse(abs_path, filename=rows[0]["file_name"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
