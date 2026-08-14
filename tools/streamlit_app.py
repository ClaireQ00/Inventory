#!/usr/bin/env python3
"""Inventory Streamlit 工作台

阶段一快速原型：查询库存、合同、基础资料，查看校验报告。
复用标准化外贸工作流的 Streamlit 交互模式。

启动方式（Docker）:
    docker compose up -d streamlit

本地开发（需安装依赖）:
    pip install streamlit pymysql
    streamlit run tools/streamlit_app.py

数据库连接从环境变量读取，与 docker-compose.yml 对齐。
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

# 写入规则层 (A 期): 所有录入/导入必须经过它, 不允许裸写 SQL
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db_writer  # noqa: E402

# ──────────────────────────────────────────────────────────────
# 数据库配置（环境变量，Docker Compose 传入）
# ──────────────────────────────────────────────────────────────
DB_CONFIG: dict[str, Any] = {
    "host": os.getenv("DB_HOST", "db"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "inventory"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "inventory_db"),
    "charset": "utf8mb4",
    "cursorclass": None,  # 运行时动态设置
}

# 校验日志目录（与 local_validator.py 输出路径对齐）
LOG_DIR = Path("/app/data/logs") if Path("/app").exists() else Path(__file__).resolve().parent.parent / "data" / "logs"


# ──────────────────────────────────────────────────────────────
# 数据库连接（懒加载，失败时友好提示）
# ──────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_db_connection():
    """获取 MySQL 连接（缓存复用）。"""
    try:
        import pymysql
        from pymysql.cursors import DictCursor

        cfg = {**DB_CONFIG, "cursorclass": DictCursor}
        return pymysql.connect(**cfg)
    except ImportError:
        st.error("缺少 PyMySQL 依赖。请在容器中运行，或执行: pip install pymysql")
        st.stop()
    except Exception as exc:
        st.error(f"数据库连接失败: {exc}")
        st.info(
            "提示: 如果本地开发，确保 MySQL 已启动且 .env 配置正确。\n"
            "Docker 中请确认 `db` 服务健康后再启动 streamlit。"
        )
        st.stop()


@st.cache_data(ttl=60, show_spinner=False)
def run_query(sql: str, params: tuple | None = None) -> list[dict]:
    """执行 SQL 查询并返回字典列表。"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    except Exception as exc:
        st.error(f"查询出错: {exc}\nSQL: {sql[:200]}")
        return []


def run_execute(sql: str, params: tuple | None = None) -> int:
    """执行 INSERT/UPDATE/DELETE，返回影响行数。"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount
    except Exception as exc:
        st.error(f"执行出错: {exc}")
        conn.rollback()
        return 0


# ──────────────────────────────────────────────────────────────
# 页面配置
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="进销存工作台",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📦 进销存工作台")
    st.caption("阶段一 · Streamlit 快速原型")
    st.markdown("---")

    st.header("系统状态")
    db_host = DB_CONFIG["host"]
    db_name = DB_CONFIG["database"]
    st.code(f"{db_host}/{db_name}", language="text")

    # 测试连接
    try:
        test = run_query("SELECT 1 AS ok")
        if test:
            st.success("数据库连接正常")
        else:
            st.warning("数据库未返回数据")
    except Exception:
        st.error("数据库连接异常")

    st.markdown("---")
    st.header("操作导航")
    nav = st.radio(
        "选择模块",
        [
            "🏠 首页",
            "⚡ 操作中心",
            "📦 库存查询",
            "📋 合同执行",
            "🏭 基础资料",
            "📊 报表中心",
            "🔍 校验日志",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption(
        "【提示】录入/导入全部经过规则层\n"
        "(字段校验→派生→预览→写后校验→留痕)，\n"
        "校验不通过的数据进不了库。"
    )


# ──────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────
def format_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}" if float(value).is_integer() else f"{float(value):,.2f}"


def status_badge(status: str | None) -> str:
    """状态文字 → emoji 标签"""
    if not status:
        return "⬜"
    mapping = {
        "draft": "📝 草稿",
        "confirmed": "✅ 已确认",
        "completed": "🏁 已完成",
        "cancelled": "❌ 已取消",
        "partial_received": "📥 部分到货",
        "delivering": "🚚 发货中",
        "shipped": "🚢 已发运",
        "delivered": "📦 已送达",
        "customs_cleared": "🛃 已清关",
        "closed": "🔒 已关闭",
        "pending": "⏳ 待处理",
        "sent": "📤 已发送",
        "converted": "🔄 已转单",
    }
    return mapping.get(status.lower(), status)


def load_latest_validation_log() -> str:
    """读取最新的校验日志内容。"""
    if not LOG_DIR.exists():
        return "日志目录不存在"
    log_files = sorted(LOG_DIR.glob("validation_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not log_files:
        return "暂无校验日志"
    try:
        return log_files[0].read_text(encoding="utf-8")
    except Exception as exc:
        return f"读取日志失败: {exc}"


# ──────────────────────────────────────────────────────────────
# 首页仪表盘
# ──────────────────────────────────────────────────────────────
def page_dashboard():
    st.header("🏠 首页仪表盘")
    st.caption(f"数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 关键指标
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        inv = run_query("SELECT COUNT(*) AS cnt, COALESCE(SUM(quantity),0) AS total FROM inventory")
        st.metric(
            label="库存品种数",
            value=inv[0]["cnt"] if inv else 0,
            help="当前有库存的物料-仓库组合数",
        )
    with col2:
        contracts = run_query(
            "SELECT COUNT(*) AS cnt FROM sales_contracts WHERE status IN ('confirmed','delivering')"
        )
        st.metric(
            label="执行中合同",
            value=contracts[0]["cnt"] if contracts else 0,
            help="已确认或发货中的销售合同数",
        )
    with col3:
        receipts = run_query(
            "SELECT COALESCE(SUM(amount),0) AS total FROM receipts WHERE status='confirmed'"
        )
        st.metric(
            label="累计收款(USD)",
            value=f"{receipts[0]['total']:,.2f}" if receipts else "0.00",
            help="已确认的收款单原币合计",
        )
    with col4:
        low_stock = run_query(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE quantity < 30"
        )
        st.metric(
            label="低库存预警",
            value=low_stock[0]["cnt"] if low_stock else 0,
            delta="⚠️ 需关注" if low_stock and low_stock[0]["cnt"] > 0 else None,
            delta_color="inverse",
        )

    st.divider()

    # 最近合同 + 库存概览
    left, right = st.columns(2)

    with left:
        st.subheader("📋 最近销售合同")
        recent_contracts = run_query(
            """
            SELECT sc.contract_no, c.name AS customer_name,
                   sc.total_amount, sc.currency, sc.status, sc.sign_date
            FROM sales_contracts sc
            JOIN customers c ON sc.customer_code = c.code
            ORDER BY sc.sign_date DESC
            LIMIT 10
            """
        )
        if recent_contracts:
            st.dataframe(
                [
                    {
                        "合同号": r["contract_no"],
                        "客户": r["customer_name"],
                        "金额": f"{r['total_amount']:,.2f} {r['currency']}",
                        "状态": status_badge(r["status"]),
                        "签约日": r["sign_date"],
                    }
                    for r in recent_contracts
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("暂无销售合同数据")

    with right:
        st.subheader("📦 库存概览（按仓库）")
        wh_summary = run_query(
            """
            SELECT w.code AS warehouse_code, w.name AS warehouse_name,
                   COUNT(*) AS sku_count, COALESCE(SUM(i.quantity),0) AS total_qty
            FROM inventory i
            JOIN warehouses w ON i.warehouse_code = w.code
            GROUP BY w.code, w.name
            ORDER BY total_qty DESC
            """
        )
        if wh_summary:
            st.dataframe(
                [
                    {
                        "仓库": f"{r['warehouse_name']} ({r['warehouse_code']})",
                        "SKU数": r["sku_count"],
                        "库存总量": format_number(r["total_qty"]),
                    }
                    for r in wh_summary
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("暂无库存数据")


# ──────────────────────────────────────────────────────────────
# 库存查询
# ──────────────────────────────────────────────────────────────
def page_inventory():
    st.header("📦 库存查询")

    # 筛选器
    col1, col2, col3 = st.columns(3)
    with col1:
        materials = run_query("SELECT material_id, spec FROM products ORDER BY material_id")
        material_opts = [("", "全部物料")] + [(m["material_id"], f"{m['material_id']} - {m['spec']}") for m in materials]
        sel_material = st.selectbox("物料", material_opts, format_func=lambda x: x[1])
    with col2:
        warehouses = run_query("SELECT code, name FROM warehouses ORDER BY code")
        wh_opts = [("", "全部仓库")] + [(w["code"], f"{w['code']} - {w['name']}") for w in warehouses]
        sel_wh = st.selectbox("仓库", wh_opts, format_func=lambda x: x[1])
    with col3:
        threshold = st.number_input("库存阈值（低于则标红）", min_value=0, value=30, step=10)

    # 构建 WHERE
    where_clauses = []
    params: list[Any] = []
    if sel_material and sel_material[0]:
        where_clauses.append("i.material_id = %s")
        params.append(sel_material[0])
    if sel_wh and sel_wh[0]:
        where_clauses.append("i.warehouse_code = %s")
        params.append(sel_wh[0])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # 库存明细
    sql = f"""
    SELECT p.material_id, p.spec, p.id_x_od, p.weight,
           w.code AS warehouse_code, w.name AS warehouse_name,
           i.quantity
    FROM inventory i
    JOIN products p ON i.material_id = p.material_id
    JOIN warehouses w ON i.warehouse_code = w.code
    {where_sql}
    ORDER BY p.material_id, w.code
    """
    rows = run_query(sql, tuple(params) if params else None)

    if rows:
        st.success(f"查询到 {len(rows)} 条库存记录")

        # 标记低库存
        def highlight_low(row):
            qty = row.get("quantity", 0) or 0
            if qty < threshold:
                return "background-color: #ffcccc"
            return ""

        df_data = [
            {
                "物料号": r["material_id"],
                "规格": r["spec"],
                "内径x外径": r.get("id_x_od", ""),
                "单重(kg)": r.get("weight"),
                "仓库": f"{r['warehouse_name']} ({r['warehouse_code']})",
                "库存数量": r["quantity"],
            }
            for r in rows
        ]
        st.dataframe(df_data, use_container_width=True, hide_index=True)
    else:
        st.info("无库存记录（或筛选条件无匹配）")

    # 出入库流水
    st.divider()
    st.subheader("📜 出入库流水")

    if sel_material and sel_material[0]:
        log_where = "WHERE sl.material_id = %s"
        log_params: tuple = (sel_material[0],)
    else:
        log_where = ""
        log_params = ()

    logs = run_query(
        f"""
        SELECT sl.created_at, sl.source_no, sl.source_type,
               sl.change_qty, sl.after_qty, w.name AS warehouse_name, sl.remark
        FROM stock_logs sl
        JOIN warehouses w ON sl.warehouse_code = w.code
        {log_where}
        ORDER BY sl.created_at DESC
        LIMIT 50
        """,
        log_params if log_params else None,
    )

    if logs:
        st.dataframe(
            [
                {
                    "时间": r["created_at"],
                    "单号": r["source_no"],
                    "类型": r["source_type"],
                    "变动": r["change_qty"],
                    "结存": r["after_qty"],
                    "仓库": r["warehouse_name"],
                    "备注": r.get("remark", ""),
                }
                for r in logs
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无流水记录")


# ──────────────────────────────────────────────────────────────
# 合同执行
# ──────────────────────────────────────────────────────────────
def page_contracts():
    st.header("📋 合同执行")

    # 筛选
    customers = run_query("SELECT code, name FROM customers ORDER BY code")
    cust_opts = [("", "全部客户")] + [(c["code"], f"{c['code']} - {c['name']}") for c in customers]
    sel_customer = st.selectbox("客户", cust_opts, format_func=lambda x: x[1])

    where = "WHERE sc.customer_code = %s" if sel_customer and sel_customer[0] else ""
    params = (sel_customer[0],) if sel_customer and sel_customer[0] else ()

    # 合同列表
    contracts = run_query(
        f"""
        SELECT sc.contract_no, c.name AS customer_name, sc.sign_date,
               sc.total_amount, sc.currency, sc.status,
               COALESCE(SUM(sci.quantity),0) AS total_qty,
               COALESCE(SUM(sci.delivered_qty),0) AS delivered_qty
        FROM sales_contracts sc
        JOIN customers c ON sc.customer_code = c.code
        LEFT JOIN sales_contract_items sci ON sc.contract_no = sci.contract_no
        {where}
        GROUP BY sc.contract_no, c.name, sc.sign_date, sc.total_amount, sc.currency, sc.status
        ORDER BY sc.sign_date DESC
        LIMIT 50
        """,
        params if params else None,
    )

    if contracts:
        st.success(f"查询到 {len(contracts)} 条合同")
        st.dataframe(
            [
                {
                    "合同号": r["contract_no"],
                    "客户": r["customer_name"],
                    "签约日": r["sign_date"],
                    "金额": f"{r['total_amount']:,.2f} {r['currency']}",
                    "状态": status_badge(r["status"]),
                    "合同数": format_number(r["total_qty"]),
                    "已发数": format_number(r["delivered_qty"]),
                    "未发数": format_number((r["total_qty"] or 0) - (r["delivered_qty"] or 0)),
                }
                for r in contracts
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无合同数据")

    # 选中合同看明细
    st.divider()
    st.subheader("🔍 合同明细")

    contract_nos = run_query(
        "SELECT contract_no FROM sales_contracts ORDER BY sign_date DESC LIMIT 20"
    )
    if contract_nos:
        sel_contract = st.selectbox(
            "选择合同",
            [c["contract_no"] for c in contract_nos],
        )
        items = run_query(
            """
            SELECT sci.item_no AS contract_item_no, p.material_id, p.spec,
                   sci.quantity, sci.delivered_qty,
                   (sci.quantity - sci.delivered_qty) AS remaining,
                   sci.unit_price, sci.subtotal
            FROM sales_contract_items sci
            JOIN products p ON sci.material_id = p.material_id
            WHERE sci.contract_no = %s
            ORDER BY sci.item_no
            """,
            (sel_contract,),
        )
        if items:
            st.dataframe(
                [
                    {
                        "行号": r["contract_item_no"],
                        "物料号": r["material_id"],
                        "规格": r["spec"],
                        "合同数": r["quantity"],
                        "已发": r["delivered_qty"],
                        "未发": r["remaining"],
                        "单价": r["unit_price"],
                        "小计": r["subtotal"],
                    }
                    for r in items
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("该合同暂无明细")

        # ── 标签纸需求提示 (M3a, 2026-08-01 辅料模块)
        # 规则: 每卷产品 1 张标签; 只提示不扣减, 生产领用出库才扣库存
        st.subheader("🏷️ 标签纸需求（推送生产前确认）")
        try:
            demand = db_writer.aux_label_demand(sel_contract)
            if not demand["lines"]:
                st.caption("该合同明细的产品均未设置标签纸 (products.label_paper 为空)")
            else:
                for line in demand["lines"]:
                    if line["profile_missing"]:
                        st.warning(f"⚠️ {line['label_paper']}：需 **{line['required']}** 张，"
                                   f"但辅料库未建档（{line['aux_code']}），请到录入端【辅料档案】补档")
                    elif line["shortage"] > 0:
                        st.error(f"🔴 {line['aux_code']}（{line['name']}）：需 **{line['required']}** 张 / "
                                 f"库存 {line['in_stock']} 张 → **缺 {line['shortage']} 张**，请先采购入库")
                    else:
                        st.success(f"🟢 {line['aux_code']}（{line['name']}）：需 **{line['required']}** 张 / "
                                   f"库存 {line['in_stock']} 张，够用")
                st.caption("提示不扣库存；实际扣减发生在录入端【辅料收发存 → 出库(生产领用)】，出库可带合同号溯源")
        except Exception as e:  # noqa: BLE001
            st.caption(f"标签需求测算暂不可用: {e}")

        # ── 合同库存进度 (2026-08-02: 出入库明细挂合同后的四方对账视图)
        # 合同量 / 生产入库 / 已发货 / 销售出库 / 当前库存 一行看齐
        st.subheader("📊 合同库存进度（生产→入库→发货→出库）")
        try:
            prog = db_writer.contract_stock_progress(sel_contract)
            if prog["found"] and prog["lines"]:
                st.dataframe(
                    [
                        {
                            "行号": ln["item_no"],
                            "物料号": ln["material_id"],
                            "规格": ln["spec"],
                            "合同量": ln["contracted"],
                            "已生产入库": ln["produced_in"],
                            "已发货": ln["delivered"],
                            "已销售出库": ln["stocked_out"],
                            "当前库存(全仓)": ln["in_stock"],
                        }
                        for ln in prog["lines"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "口径：已生产入库=生产入库单(挂本合同)累计；已发货=发货单回写；"
                    "已销售出库=销售出库单(按发货单自动反解本合同)累计；"
                    "当前库存=该物料全部仓库合计（库存不挂合同，刻意设计）。"
                    "出入库单只数 confirmed。"
                )
            else:
                st.info("未取到该合同的进度数据")
        except Exception as e:  # noqa: BLE001
            st.caption(f"库存进度暂不可用: {e}")


# ──────────────────────────────────────────────────────────────
# 基础资料
# ──────────────────────────────────────────────────────────────
def page_master_data():
    st.header("🏭 基础资料")
    st.caption("查询页只读；新增/编辑请点按钮跳录入端（8082），两边数据同源实时生效")

    # 录入端地址: 局域网访问时宿主机 IP 不同, 用环境变量覆盖 (.env 加 ENTRY_BASE)
    entry_base = os.getenv("ENTRY_BASE", "http://localhost:8082")

    subtab = st.tabs(["产品", "客户", "供应商", "仓库"])

    with subtab[0]:
        st.subheader("📦 产品物料")
        st.link_button("➕ 新增物料（录入端）", f"{entry_base}/entry/product")
        products = run_query(
            """
            SELECT material_id, spec, product_category, inner_diameter,
                   thickness, outer_diameter, id_x_od, weight_per_meter, weight,
                   length, volume
            FROM products
            ORDER BY material_id
            """
        )
        if products:
            st.dataframe(products, use_container_width=True, hide_index=True)
        else:
            st.info("暂无产品数据")

    with subtab[1]:
        st.subheader("👤 客户")
        col_a, col_b = st.columns(2)
        col_a.link_button("➕ 新增客户（录入端）", f"{entry_base}/entry/customer")
        col_b.link_button("🧑‍💼 业务员档案（录入端）", f"{entry_base}/entry/salesperson")
        customers = run_query(
            "SELECT code, name, brand_name, contact_person, phone, address FROM customers ORDER BY code"
        )
        if customers:
            st.dataframe(customers, use_container_width=True, hide_index=True)
        else:
            st.info("暂无客户数据")

    with subtab[2]:
        st.subheader("🏢 供应商")
        suppliers = run_query(
            "SELECT code, name, contact_person, phone, is_self, is_active FROM suppliers ORDER BY code"
        )
        if suppliers:
            st.dataframe(suppliers, use_container_width=True, hide_index=True)
            self_supplier = [s for s in suppliers if s.get("is_self")]
            if self_supplier:
                st.success(f"本公司: {self_supplier[0]['name']} ({self_supplier[0]['code']})")
            else:
                st.warning("未设置 is_self=1 的本公司记录")
        else:
            st.info("暂无供应商数据")
        st.caption("供应商录入页尚未做（录入端后续补 FB.x）")

    with subtab[3]:
        st.subheader("🏭 仓库")
        warehouses = run_query(
            "SELECT code, name, address, is_active FROM warehouses ORDER BY code"
        )
        if warehouses:
            st.dataframe(warehouses, use_container_width=True, hide_index=True)
        else:
            st.info("暂无仓库数据")
        st.caption("仓库录入页尚未做（录入端后续补 FB.x）")


# ──────────────────────────────────────────────────────────────
# 报表中心
# ──────────────────────────────────────────────────────────────
def page_reports():
    st.header("📊 报表中心")

    report_type = st.selectbox(
        "选择报表",
        [
            "低库存预警（库存 < 30）",
            "未发完合同（已确认但还有未发数量）",
            "待处理差异（pending credit_notes）",
            "本月汇率",
            "业务员提成基数（按客户汇总吨位/回款）",
        ],
    )

    if report_type == "业务员提成基数（按客户汇总吨位/回款）":
        st.caption(
            "提成规则说明：三种方式（按量·元/吨 ｜ 按价格 ｜ 按回款时间）各有系数，"
            "系数未定前本表先出**基数**。坏账扣减规则：损失 ≤1% 不报警，超出部分等额扣提成（R13）。"
        )
        # 吨位基数 = Σ 合同明细数量 × 单重(products.weight 主数据) / 1000 (kg→吨)
        # 回款基数 = receipts 实收 (已确认) 按合同汇总; 业务员 = 客户编码首字母 → salespersons
        rows = run_query(
            """
            SELECT sp.code AS 业务员, sp.name AS 姓名,
                   c.code AS 客户编码, c.name AS 客户名称,
                   COUNT(DISTINCT sc.contract_no) AS 合同数,
                   ROUND(SUM(sci.quantity * p.weight) / 1000, 3) AS 合同吨位,
                   ROUND(SUM(sci.delivered_qty * p.weight) / 1000, 3) AS 已发吨位,
                   ROUND(SUM(sci.subtotal), 2) AS 合同金额_原币,
                   sc.currency AS 币种
            FROM sales_contract_items sci
            JOIN sales_contracts sc ON sci.contract_no = sc.contract_no
            JOIN customers c ON sc.customer_code = c.code
            JOIN products p ON sci.material_id = p.material_id
            JOIN salespersons sp ON sp.code = LEFT(c.code, 1)
            WHERE sc.status NOT IN ('cancelled')
            GROUP BY sp.code, sp.name, c.code, c.name, sc.currency
            ORDER BY sp.code, 合同吨位 DESC
            """
        )
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
            # 业务员小计
            st.subheader("业务员小计")
            summary = run_query(
                """
                SELECT sp.code AS 业务员, sp.name AS 姓名,
                       COUNT(DISTINCT sc.contract_no) AS 合同数,
                       COUNT(DISTINCT c.code) AS 客户数,
                       ROUND(SUM(sci.quantity * p.weight) / 1000, 3) AS 合同吨位合计,
                       ROUND(SUM(sci.delivered_qty * p.weight) / 1000, 3) AS 已发吨位合计
                FROM sales_contract_items sci
                JOIN sales_contracts sc ON sci.contract_no = sc.contract_no
                JOIN customers c ON sc.customer_code = c.code
                JOIN products p ON sci.material_id = p.material_id
                JOIN salespersons sp ON sp.code = LEFT(c.code, 1)
                WHERE sc.status NOT IN ('cancelled')
                GROUP BY sp.code, sp.name
                ORDER BY 合同吨位合计 DESC
                """
            )
            st.dataframe(summary, use_container_width=True, hide_index=True)
            # 回款口径
            st.subheader("回款基数（按客户）")
            receipts = run_query(
                """
                SELECT LEFT(r.customer_code, 1) AS 业务员, r.customer_code AS 客户编码,
                       COUNT(*) AS 收款笔数,
                       ROUND(SUM(r.amount), 2) AS 实收_原币, r.currency AS 币种,
                       ROUND(SUM(r.amount_cny), 2) AS 实收_人民币
                FROM receipts r
                WHERE r.status = 'confirmed'
                GROUP BY LEFT(r.customer_code, 1), r.customer_code, r.currency
                ORDER BY 实收_人民币 DESC
                """
            )
            if receipts:
                st.dataframe(receipts, use_container_width=True, hide_index=True)
            else:
                st.info("暂无已确认收款")
        else:
            st.info("暂无合同数据")

    elif report_type == "低库存预警（库存 < 30）":
        rows = run_query(
            """
            SELECT p.material_id, p.spec, w.name AS warehouse_name, i.quantity
            FROM inventory i
            JOIN products p ON i.material_id = p.material_id
            JOIN warehouses w ON i.warehouse_code = w.code
            WHERE i.quantity < 30
            ORDER BY i.quantity ASC
            """
        )
        if rows:
            st.warning(f"发现 {len(rows)} 条低库存记录")
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.success("暂无低库存预警 🎉")

    elif report_type == "未发完合同（已确认但还有未发数量）":
        rows = run_query(
            """
            SELECT sc.contract_no, c.name AS customer_name,
                   p.material_id, p.spec,
                   sci.quantity AS contract_qty,
                   sci.delivered_qty,
                   (sci.quantity - sci.delivered_qty) AS remaining
            FROM sales_contract_items sci
            JOIN sales_contracts sc ON sci.contract_no = sc.contract_no
            JOIN customers c ON sc.customer_code = c.code
            JOIN products p ON sci.material_id = p.material_id
            WHERE sc.status IN ('confirmed', 'delivering')
              AND sci.delivered_qty < sci.quantity
            ORDER BY remaining DESC
            """
        )
        if rows:
            st.info(f"有 {len(rows)} 行合同明细未发完")
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.success("所有执行中合同已发完 🎉")

    elif report_type == "待处理差异（pending credit_notes）":
        rows = run_query(
            """
            SELECT cn.cn_no, cn.shipping_no, c.name AS customer_name,
                   cn.diff_qty, cn.diff_amount, cn.currency,
                   cn.resolution, cn.created_at,
                   DATEDIFF(NOW(), cn.created_at) AS days_pending
            FROM credit_notes cn
            JOIN sales_contracts sc ON cn.contract_no = sc.contract_no
            JOIN customers c ON sc.customer_code = c.code
            WHERE cn.resolution = 'pending'
            ORDER BY days_pending DESC
            """
        )
        if rows:
            for r in rows:
                days = r.get("days_pending", 0)
                if days and days > 90:
                    st.error(f"🚨 {r['cn_no']} 已挂账 {days} 天（超 90 天，严重逾期！）")
                elif days and days > 30:
                    st.warning(f"⚠️ {r['cn_no']} 已挂账 {days} 天（超 30 天，请催办）")
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.success("无待处理差异 🎉")

    elif report_type == "本月汇率":
        rows = run_query(
            """
            SELECT currency, rate_to_cny, effective_date, source
            FROM exchange_rates
            WHERE effective_date >= DATE_FORMAT(NOW(), '%Y-%m-01')
            ORDER BY currency
            """
        )
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("本月暂无汇率记录，请财务经理录入。")


# ──────────────────────────────────────────────────────────────
# 校验日志
# ──────────────────────────────────────────────────────────────
def page_validation_logs():
    st.header("🔍 校验日志")
    st.caption("显示本地校验工具生成的最新报告")

    log_content = load_latest_validation_log()

    # 判断日志状态
    if "ERROR" in log_content.upper():
        st.error("⚠️ 最近一次校验包含 ERROR，请查看详情")
    elif "WARN" in log_content.upper():
        st.warning("最近一次校验包含 WARN 提醒")
    else:
        st.success("最近一次校验全部通过 ✅")

    with st.expander("查看最新日志详情", expanded=True):
        st.code(log_content, language="text")

    # 历史日志列表
    st.divider()
    st.subheader("📁 历史校验日志")
    if LOG_DIR.exists():
        log_files = sorted(LOG_DIR.glob("validation_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        if log_files:
            for lf in log_files:
                mtime = datetime.fromtimestamp(lf.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                size = lf.stat().st_size
                cols = st.columns([3, 1, 1])
                cols[0].write(lf.name)
                cols[1].write(mtime)
                cols[2].write(f"{size} B")
        else:
            st.info("暂无历史日志")
    else:
        st.info("日志目录不存在")


# ──────────────────────────────────────────────────────────────
# 📝 录入中心 (A 期: 汇率 / 收款 / 物料)
# 交互模式参考「标准化外贸工作流」: 填表 → 预览(派生) → 打勾确认 → 提交
# 所有写入走 db_writer 规则层, 校验不过进不了库
# ──────────────────────────────────────────────────────────────
def _submit_flow(tab_key: str, table: str, data: dict, preview_lines: list[str]) -> None:
    """两段式提交流程: 预览(不落库) → 打勾 → 确认提交(落库+写后校验+审计)"""
    if st.button("🔍 预览（校验 + 派生）", key=f"pv_{tab_key}"):
        pv = db_writer.preview_insert(table, data)
        st.session_state[f"pv_{tab_key}"] = pv
    pv = st.session_state.get(f"pv_{tab_key}")
    if not pv:
        st.caption("点「预览」先看校验和派生结果，确认无误后再提交入库。")
        return
    if not pv["ok"]:
        for e in pv["errors"]:
            st.error(f"❌ {e}")
        st.caption("请按提示修改后重新预览。")
        return
    st.success("校验通过，派生结果如下：")
    for line in preview_lines:
        st.write(line)
    if pv.get("rate_note"):
        st.info(f"💱 {pv['rate_note']}")
    for lv, msg in pv.get("engine_msgs", []):
        if lv == "info":
            st.caption(f"⚙️ {msg}")
        else:
            st.warning(f"⚠️ {msg}")
    derived = pv["derived_row"]
    with st.expander("查看完整入库行"):
        st.json({k: str(v) for k, v in derived.items()})
    confirmed = st.checkbox("我确认以上数据无误，同意写入数据库", key=f"cf_{tab_key}")
    if st.button("✅ 确认提交", key=f"sb_{tab_key}", disabled=not confirmed):
        operator = st.session_state.get("operator_name", "frontend")
        result = db_writer.insert_row(table, data, operator=operator)
        if result["ok"]:
            st.success(f"✅ 已入库（记录 id={result['record_id']}），审计日志已留痕")
            for wmsg in result["warnings"]:
                st.warning(f"⚠️ {wmsg}")
            for lv, msg in result["checks"]:
                if lv == "info":
                    st.caption(f"📊 {msg}")
            st.session_state.pop(f"pv_{tab_key}", None)
        else:
            for e in result["errors"]:
                st.error(f"❌ 写入被拦截: {e}")
            st.caption("数据未入库（已自动回滚）。请修改后重新预览提交。")


def page_entry():
    st.header("📝 录入中心")
    st.caption("A 期开放：汇率 / 收款 / 物料。报价、合同、发货录入在后续阶段开放。")

    st.session_state["operator_name"] = st.text_input(
        "操作人（写入审计日志）", value=st.session_state.get("operator_name", ""), placeholder="如: 梁经理"
    )

    tab_rate, tab_receipt, tab_product = st.tabs(["💱 汇率", "💰 收款", "🧱 物料"])

    # ── 汇率 ──
    with tab_rate:
        st.subheader("录入当月汇率（汇率月固定：每月 1 号录一次）")
        c1, c2, c3 = st.columns(3)
        with c1:
            currency = st.selectbox("币种", ["USD", "EUR", "IDR", "CNY"], key="er_cur")
        with c2:
            rate = st.number_input("汇率（1 原币 = ? CNY）", min_value=0.0, value=0.0,
                                   step=0.0001, format="%.4f", key="er_rate")
        with c3:
            eff = st.date_input("生效日期（每月 1 号）", key="er_date")
        remark = st.text_input("备注", value="", key="er_rmk")
        data = {"currency": currency, "rate_to_cny": rate,
                "effective_date": eff.isoformat(), "source": "manual", "remark": remark}
        _submit_flow("rate", "exchange_rates", data,
                     [f"**{currency}** = {rate:.4f} CNY，自 {eff.isoformat()} 起生效"])
        st.divider()
        st.caption("最近汇率：")
        rows = db_writer.list_options(
            "SELECT currency, rate_to_cny, effective_date, source FROM exchange_rates "
            "ORDER BY effective_date DESC, currency LIMIT 10")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── 收款 ──
    with tab_receipt:
        st.subheader("录入收款（汇率按到账日期自动带出，金额自动折 CNY）")
        customers = db_writer.list_customers()
        if not customers:
            st.warning("基础资料里没有客户，请先维护 customers。")
            return
        c1, c2, c3 = st.columns(3)
        with c1:
            cust = st.selectbox("客户", customers, key="rc_cust",
                                format_func=lambda x: f"{x['code']} - {x['name']}")
            contracts = db_writer.list_contracts(cust["code"])
            contract_opts = [{"contract_no": "", "total_amount": "", "currency": "", "status": ""}] + contracts
            cont = st.selectbox(
                "关联合同（预收款留空）", contract_opts, key="rc_cont",
                format_func=lambda x: f"{x['contract_no']}（{x['total_amount']} {x['currency']}）" if x["contract_no"] else "（不关联合同）")
        with c2:
            receipt_no = st.text_input("收款单号", value=f"RC{datetime.now().strftime('%Y%m%d')}",
                                       key="rc_no", help="建议格式 RC+日期+流水，如 RC20260801001")
            amount = st.number_input("收款金额（原币）", min_value=0.0, value=0.0, step=100.0, key="rc_amt")
            currency = st.selectbox("币种", ["USD", "EUR", "IDR", "CNY"], key="rc_cur")
        with c3:
            paid = st.date_input("实际到账日期", key="rc_paid")
            pay_method = st.selectbox("付款方式", ["T/T", "L/C", "D/P", "D/A", "other"], key="rc_pm")
            bank_ref = st.text_input("银行水单号", value="", key="rc_ref")
        remark = st.text_input("备注", value="", key="rc_rmk")
        data = {"receipt_no": receipt_no, "customer_code": cust["code"],
                "contract_no": cont["contract_no"] or None,
                "amount": amount, "currency": currency,
                "paid_date": paid.isoformat(), "pay_method": pay_method,
                "bank_ref": bank_ref, "status": "confirmed", "remark": remark}
        _submit_flow("receipt", "receipts", data,
                     [f"**{receipt_no}** 收 {cust['name']} {amount:,.2f} {currency}"
                      + (f"，合同 {cont['contract_no']}" if cont["contract_no"] else "（预收款）")])

    # ── 物料 ──
    with tab_product:
        st.subheader("录入新物料（边填边算：外径 / 厚度 / 米重 / 单重 / 规格实时派生）")
        st.caption("💡 谈判达成新重量/新规格时，建议优先用【⚡ 操作中心 → 克隆建物料】，自动带溯源备注。"
                   "本页适合全新物料的手工录入。")
        customers = db_writer.list_customers()

        # 第 1 行: 客户 / 物料编码(按客户自动建议) / 产品类别(真实类别下拉, 可新增)
        c1, c2, c3 = st.columns(3)
        with c1:
            cust = st.selectbox("所属客户", customers, key="pd_cust",
                                format_func=lambda x: f"{x['code']} - {x['name']}")
        with c2:
            material_id = st.text_input(
                "物料编码（按客户自动建议，可改）",
                value=db_writer.suggest_material_id(cust["code"]),
                key=f"pd_mid_{cust['code']}",
                help="规则 M-{客户编码}-{流水号}，建议值 = 该客户现有最大流水 + 1")
        with c3:
            cat_options = db_writer.distinct_categories() + ["➕ 手动输入新类别"]
            cat_choice = st.selectbox("产品类别（按真实数据使用频次排序）", cat_options, key="pd_cat")
            if cat_choice == "➕ 手动输入新类别":
                category = st.text_input("新类别名称", key="pd_cat_new", placeholder="如 线管").strip()
            else:
                category = cat_choice

        # 第 2 行: 品牌 / 材质类型 / 内径
        c4, c5, c6 = st.columns(3)
        with c4:
            brand = st.text_input("品牌", value="", key="pd_brand")
        with c5:
            mtype = st.text_input("材质类型", value="", key="pd_type", placeholder="如 PVC")
        with c6:
            inner_d = st.number_input("内径 (mm, 必填)", min_value=0.0, value=0.0, step=0.5, key="pd_id")

        st.markdown("**几何与重量（任选路径，其余自动算）**")
        st.caption("路径①: 填厚度 → 出外径 ｜ 路径②: 填外径 → 反推厚度 ｜ "
                   "路径③: 内径+厚度+长度 → 出米重/单重。手填值与公式冲突时保留你的值，仅提示偏差。")
        c7, c8, c9, c10, c11 = st.columns(5)
        with c7:
            thickness = st.number_input("厚度 (mm)", min_value=0.0, value=0.0, step=0.05,
                                        format="%.2f", key="pd_thk")
        with c8:
            length = st.number_input("长度 (M)", min_value=0.0, value=0.0, step=1.0, key="pd_len")
        with c9:
            outer_d = st.number_input("外径 (mm)", min_value=0.0, value=0.0, step=0.1, key="pd_od")
        with c10:
            wpm = st.number_input("米重 (g/m)", min_value=0.0, value=0.0, step=10.0, key="pd_wpm")
        with c11:
            weight = st.number_input("单重 (KG)", min_value=0.0, value=0.0, step=0.5, key="pd_w")

        # ── 实时派生面板: Streamlit 每次输入变化都重跑脚本, 这里边填边刷新 ──
        inputs = {"product_category": category or None,
                  "inner_diameter": inner_d or None,
                  "thickness": thickness or None,
                  "length": length or None,
                  "outer_diameter": outer_d or None,
                  "weight_per_meter": wpm or None,
                  "weight": weight or None}
        row, computed, msgs, density, group = db_writer.live_derive_products(inputs)

        with st.container(border=True):
            info_bits = []
            if group:
                info_bits.append(f"大类 **{group}**")
            if density is not None:
                info_bits.append(f"密度 **{density:g}**")
            elif category:
                info_bits.append("密度 **待客户补充**（该类别暂无密度规则，重量无法自动算）")
            if row.get("inner_diameter_inch"):
                info_bits.append(f"标称 **{row['inner_diameter_inch']}**")
            if info_bits:
                st.markdown("｜".join(info_bits))

            def _fmt(field, digits=2):
                v = row.get(field)
                if v in (None, ""):
                    return "—"
                mark = " ⚙️" if field in computed else ""
                try:
                    return f"{float(v):,.{digits}f}{mark}"
                except (TypeError, ValueError):
                    return f"{v}{mark}"

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("外径 (mm)", _fmt("outer_diameter"))
            m2.metric("厚度 (mm)", _fmt("thickness"))
            m3.metric("米重 (g/m)", _fmt("weight_per_meter", digits=0))
            m4.metric("单重 (KG)", _fmt("weight"))
            st.caption("⚙️ = 本次按公式自动算出；无 ⚙️ = 你手填的值。"
                       "体积(CBM)需外观尺寸实测后补，不补也能入库（影响装箱校验）。")

        for level, msg in msgs:
            if level == "info":
                continue
            (st.warning if level == "warn" else st.error)(msg)

        spec = st.text_input(
            "规格描述（自动推算，可改）",
            value=str(row.get("spec") or ""),
            key=f"pd_spec_{row.get('spec', '')}",
            help="格式: 英寸 ID内径mm -米数M (短/中/长)。留空则提交时由引擎自动算。")

        data = {"material_id": material_id.strip(), "customer_code": cust["code"], "brand": brand,
                "product_category": category or None, "material_type": mtype,
                "spec": spec or None,
                "inner_diameter": inner_d or None, "thickness": thickness or None,
                "length": length or None,
                "outer_diameter": outer_d or None, "weight_per_meter": wpm or None,
                "weight": weight or None,
                "inner_diameter_inch": row.get("inner_diameter_inch"),
                "spec_meter": row.get("spec_meter"),
                "is_active": 1}
        _submit_flow("product", "products", data,
                     [f"**{material_id}** {category or ''}/{spec or '(规格自动算)'}，"
                      f"内径 {inner_d}mm，长度 {length}M"])


# ──────────────────────────────────────────────────────────────
# 📥 导入中心 (B 期占位)
# ──────────────────────────────────────────────────────────────
def page_import():
    st.header("📥 导入中心")
    st.info(
        "B 期建设内容：上传 CSV → 自动跑校验 → 绿了才亮「导入 MySQL」按钮 → 显示导入报告。\n\n"
        "当前请沿用命令行流程：`bash scripts/run_local_validation.sh`（校验）+ "
        "`bash scripts/load-csv-to-db.sh`（导入）。",
        icon="🚧",
    )


# ──────────────────────────────────────────────────────────────
# ⚡ 操作中心 (A 期: 跑校验 / 克隆建物料)
# ──────────────────────────────────────────────────────────────
CSV_DIR_IN_CONTAINER = Path("/app/data/csv")


def _run_tool(cmd: list[str], timeout: int = 180) -> tuple[int, str]:
    """跑 tools/ 下的脚本, 返回 (退出码, 输出)"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, f"执行超时（>{timeout}s）"


def page_operations():
    st.header("⚡ 操作中心")
    st.caption("点击触发型操作。危险操作需要先打勾确认（学自标准化外贸工作流）。")

    # ── 跑 16 步校验 ──
    st.subheader("1. 跑 16 步校验（对 data/csv 真实数据）")
    st.caption("等价于命令行 `python3 tools/local_validator.py --csv-dir data/csv`")
    if st.button("▶️ 立即校验", key="op_validate"):
        with st.spinner("校验中，通常 10-30 秒..."):
            code, out = _run_tool(
                ["python3", "/app/tools/local_validator.py", "--csv-dir", str(CSV_DIR_IN_CONTAINER)])
        st.session_state["op_validate_out"] = (code, out)
    if "op_validate_out" in st.session_state:
        code, out = st.session_state["op_validate_out"]
        if code == 0:
            st.success("✅ 校验全部通过")
        else:
            st.error(f"❌ 校验未通过（退出码 {code}），请检查下方 ERROR 行")
        st.code(out[-6000:], language="text")

    st.divider()

    # ── 克隆建物料 ──
    st.subheader("2. 克隆建物料（报价谈成新重量/新规格 → 归位新编码）")
    st.caption("规则见 ADR-0005：克隆源物料 → 换编码 → 覆盖谈判值 → 派生列自动重算 → 报价/合同可连带换码")
    products_csv = CSV_DIR_IN_CONTAINER / "products.csv"
    if not products_csv.exists():
        st.warning(f"找不到 {products_csv}（容器未挂载 data/csv）")
        return
    import csv as _csv
    with products_csv.open(newline="", encoding="utf-8") as f:
        product_ids = [r["material_id"] for r in _csv.DictReader(f)]
    c1, c2 = st.columns(2)
    with c1:
        source_id = st.selectbox("源物料（克隆模板）", product_ids, key="cl_src")
        new_id = st.text_input("新物料编码（必须不存在）", key="cl_new", placeholder="如 M-Q025-013")
    with c2:
        ow = st.number_input("新单重 KG（0=不覆盖）", min_value=0.0, value=0.0, step=0.5, key="cl_w")
        olen = st.number_input("新长度 M（0=不覆盖）", min_value=0.0, value=0.0, step=1.0, key="cl_len")
        update_quote = st.text_input("连带换码的报价单号（可空）", key="cl_uq",
                                     help="填了就把该报价单里源物料的行换成新编码")
    st.caption("💡 长度变更会把外观尺寸/体积置空待实测；内径/厚度等几何参数变更建议先用命令行工具（更多参数）。")
    ack = st.checkbox("我确认：克隆会追加新物料到 products.csv，历史数据不动", key="cl_ack")
    if st.button("🧬 执行克隆", key="cl_run",
                 disabled=not (ack and new_id.strip() and source_id)):
        cmd = ["python3", "/app/tools/clone_material.py", source_id, new_id.strip(),
               "--products-csv", str(products_csv)]
        if ow:
            cmd += ["--weight", str(ow)]
        if olen:
            cmd += ["--length", str(olen)]
        if update_quote.strip():
            cmd += ["--update-quote", update_quote.strip(),
                    "--quotation-csv", str(CSV_DIR_IN_CONTAINER / "quotation_items.csv")]
        with st.spinner("克隆中..."):
            code, out = _run_tool(cmd)
        if code == 0:
            st.success("✅ 克隆完成")
            st.code(out, language="text")
            st.info("📌 下一步：跑【1. 跑 16 步校验】确认数据自洽，然后用 `scripts/load-csv-to-db.sh` 导入 MySQL")
        else:
            st.error("❌ 克隆失败")
            st.code(out, language="text")


# ──────────────────────────────────────────────────────────────
# 主路由
# ──────────────────────────────────────────────────────────────
PAGES = {
    "🏠 首页": page_dashboard,
    # F2.4: 录入中心/导入中心已下线 —— 录入迁移至 React 录入端，导入中心待 FB.1 重做。
    # page_entry / page_import 函数本体保留(不挂载)，避免影响其他页的复用函数。
    "⚡ 操作中心": page_operations,
    "📦 库存查询": page_inventory,
    "📋 合同执行": page_contracts,
    "🏭 基础资料": page_master_data,
    "📊 报表中心": page_reports,
    "🔍 校验日志": page_validation_logs,
}

if nav in PAGES:
    PAGES[nav]()
else:
    page_dashboard()
