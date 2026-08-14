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

    # ── 单据链路图: 一张合同从报价到收款的全生命周期 ──
    st.divider()
    st.subheader("🔗 单据链路图")
    st.caption("选一张合同，看它从报价到收款的全链路单据。节点颜色：蓝=报价 金=合同 绿=入库 橙=出库 紫=发货 青=报关 红=收款")

    all_contracts = run_query(
        """
        SELECT sc.contract_no, sc.customer_code, c.name AS customer_name
        FROM sales_contracts sc JOIN customers c ON sc.customer_code = c.code
        ORDER BY sc.sign_date DESC
        """
    )
    if all_contracts:
        mode = st.radio("查看方式", ["按合同", "按客户"], horizontal=True, key="chain_mode")
        if mode == "按合同":
            chain_options = {
                f"{r['contract_no']}（{r['customer_name']}）": r["contract_no"]
                for r in all_contracts
            }
            picked = st.selectbox("选择合同", list(chain_options), key="chain_contract")
            if picked:
                render_doc_chain(chain_options[picked])
        else:
            cust_map = {}
            for r in all_contracts:
                cust_map.setdefault(
                    f"{r['customer_code']}（{r['customer_name']}）", []
                ).append(r["contract_no"])
            picked_cust = st.selectbox("选择客户", list(cust_map), key="chain_customer")
            if picked_cust:
                for cno in cust_map[picked_cust]:
                    st.markdown(f"**合同 {cno}**")
                    render_doc_chain(cno)
    else:
        st.info("暂无合同数据")


def render_doc_chain(contract_no: str):
    """把一张合同关联的所有单据画成 graphviz 流程图 (只读查询, 不写库)。"""
    quotes = run_query(
        "SELECT quote_no, quote_type, quote_date, status FROM quotations "
        "WHERE converted_contract_no=%s OR parent_quote_no IN "
        "(SELECT quote_no FROM quotations WHERE converted_contract_no=%s)",
        (contract_no, contract_no),
    )
    contract = run_query(
        "SELECT contract_no, sign_date, status, total_amount, currency "
        "FROM sales_contracts WHERE contract_no=%s",
        (contract_no,),
    )
    ins = run_query(
        "SELECT DISTINCT si.in_no, si.in_date, si.in_type, si.status, si.transfer_ref "
        "FROM stock_in si JOIN stock_in_items i ON si.in_no=i.in_no "
        "WHERE i.contract_no=%s",
        (contract_no,),
    )
    outs = run_query(
        "SELECT DISTINCT so.out_no, so.out_date, so.out_type, so.status, "
        "so.transfer_ref, so.delivery_no "
        "FROM stock_out so JOIN stock_out_items i ON so.out_no=i.out_no "
        "WHERE i.contract_no=%s",
        (contract_no,),
    )
    deliveries = run_query(
        "SELECT DISTINCT d.delivery_no, d.delivery_date, d.status "
        "FROM delivery_orders d JOIN delivery_order_items i ON d.delivery_no=i.delivery_no "
        "WHERE i.contract_no=%s",
        (contract_no,),
    )
    # 每张发货单的实发卷数与吨位 (actual_quantity 优先, 同校验第 5 步口径)
    delivery_totals = {}
    if deliveries:
        dnos = [d["delivery_no"] for d in deliveries]
        ph = ",".join(["%s"] * len(dnos))
        for t in run_query(
            f"SELECT doi.delivery_no, "
            f"SUM(IF(doi.actual_quantity>0, doi.actual_quantity, doi.quantity)) AS qty, "
            f"SUM(IF(doi.actual_quantity>0, doi.actual_quantity, doi.quantity) * p.weight) / 1000 AS tons "
            f"FROM delivery_order_items doi JOIN products p ON doi.material_id=p.material_id "
            f"WHERE doi.delivery_no IN ({ph}) GROUP BY doi.delivery_no",
            tuple(dnos),
        ):
            delivery_totals[t["delivery_no"]] = t

    # 入库/出库单 likewise: 每单总卷数与吨位
    def _doc_totals(item_table, doc_col, doc_nos):
        if not doc_nos:
            return {}
        ph = ",".join(["%s"] * len(doc_nos))
        return {
            t["doc"]: t
            for t in run_query(
                f"SELECT i.{doc_col} AS doc, SUM(i.quantity) AS qty, "
                f"SUM(i.quantity * p.weight) / 1000 AS tons "
                f"FROM {item_table} i JOIN products p ON i.material_id=p.material_id "
                f"WHERE i.{doc_col} IN ({ph}) GROUP BY i.{doc_col}",
                tuple(doc_nos),
            )
        }

    in_totals = _doc_totals("stock_in_items", "in_no", [r["in_no"] for r in ins])
    out_totals = _doc_totals("stock_out_items", "out_no", [r["out_no"] for r in outs])
    shippings = run_query(
        "SELECT s.shipping_no, s.shipping_date, s.status, s.delivery_no, "
        "s.total_pkgs, s.total_cbm, s.total_gross_wt "
        "FROM shipping_records s WHERE s.delivery_no IN "
        "(SELECT DISTINCT delivery_no FROM delivery_order_items WHERE contract_no=%s)",
        (contract_no,),
    )
    receipts = run_query(
        "SELECT receipt_no, paid_date, amount, currency, status "
        "FROM receipts WHERE contract_no=%s",
        (contract_no,),
    )

    # 调拨配对补全: 一侧关联了合同的调拨单, 把 transfer_ref 配对的另一侧也拉进图
    # (否则"本厂→临沂"这类中转链会只显示半条)
    linked_refs = {r["transfer_ref"] for r in (ins + outs) if r.get("transfer_ref")}
    known = {r["in_no"] for r in ins} | {r["out_no"] for r in outs}
    missing = linked_refs - known
    if missing:
        ph = ",".join(["%s"] * len(missing))
        ins += run_query(
            f"SELECT in_no, in_date, in_type, status, transfer_ref "
            f"FROM stock_in WHERE in_no IN ({ph})",
            tuple(missing),
        )
        outs += run_query(
            f"SELECT out_no, out_date, out_type, status, transfer_ref, delivery_no "
            f"FROM stock_out WHERE out_no IN ({ph})",
            tuple(missing),
        )

    # 节点颜色按单据类型
    STYLE = {
        "quote":    ("lightblue", "报价"),
        "contract": ("gold",      "合同"),
        "in":       ("palegreen", "入库"),
        "out":      ("orange",    "出库"),
        "delivery": ("plum",      "发货"),
        "shipping": ("turquoise", "报关"),
        "receipt":  ("lightcoral","收款"),
    }

    def node(nid, label, kind):
        color, _ = STYLE[kind]
        return f'  "{nid}" [label="{label}", style=filled, fillcolor="{color}"];'

    lines = [
        'digraph G {',
        '  rankdir=LR; node [shape=box, fontname="Arial"]; edge [fontname="Arial"];',
    ]
    edges = []

    for q in quotes:
        tag = "简要" if q["quote_type"] == "brief" else "正式"
        lines.append(node(q["quote_no"], f'报价 {q["quote_no"]}\\n{tag} | {q["quote_date"]} | {q["status"]}', "quote"))
        edges.append(f'  "{q["quote_no"]}" -> "{contract_no}" [label="转合同"];')

    if contract:
        c = contract[0]
        lines.append(node(contract_no,
                          f'合同 {c["contract_no"]}\\n{c["sign_date"]} | {c["status"]}\\n{c["total_amount"]:,.2f} {c["currency"]}',
                          "contract"))

    for r in ins:
        tag = {"purchase": "采购入库", "production": "生产入库", "transfer": "调拨入库", "adjust": "调整入库"}.get(r["in_type"], r["in_type"])
        t = in_totals.get(r["in_no"])
        qty_txt = f"\\n{int(t['qty'])} 卷 / {float(t['tons']):.2f} 吨" if t else ""
        lines.append(node(r["in_no"], f'入库 {r["in_no"]}\\n{tag} | {r["in_date"]} | {r["status"]}{qty_txt}', "in"))
        if r["in_type"] == "transfer" and r["transfer_ref"]:
            edges.append(f'  "{r["transfer_ref"]}" -> "{r["in_no"]}" [label="调拨到达"];')
        else:
            edges.append(f'  "{contract_no}" -> "{r["in_no"]}" [label="生产/采购"];')

    for r in outs:
        tag = {"sale": "销售出库", "transfer": "调拨发出", "adjust": "调整出库"}.get(r["out_type"], r["out_type"])
        t = out_totals.get(r["out_no"])
        qty_txt = f"\\n{int(t['qty'])} 卷 / {float(t['tons']):.2f} 吨" if t else ""
        lines.append(node(r["out_no"], f'出库 {r["out_no"]}\\n{tag} | {r["out_date"]} | {r["status"]}{qty_txt}', "out"))
        if r["out_type"] == "transfer":
            edges.append(f'  "{contract_no}" -> "{r["out_no"]}" [label="调拨发出"];')
        elif r["delivery_no"]:
            edges.append(f'  "{r["delivery_no"]}" -> "{r["out_no"]}" [label="装柜出库"];')

    for d in deliveries:
        t = delivery_totals.get(d["delivery_no"])
        qty_txt = f"\\n实发 {int(t['qty'])} 卷 / {float(t['tons']):.2f} 吨" if t else ""
        lines.append(node(d["delivery_no"],
                          f'发货 {d["delivery_no"]}\\n{d["delivery_date"]} | {d["status"]}{qty_txt}',
                          "delivery"))
        edges.append(f'  "{contract_no}" -> "{d["delivery_no"]}" [label="下发货单"];')
    for s in shippings:
        lines.append(node(s["shipping_no"],
                          f'报关 {s["shipping_no"]}\\n{s["shipping_date"]} | {s["status"]}\\n{s["total_pkgs"]} 件 / {float(s["total_cbm"]):.2f} m³ / 毛重 {float(s["total_gross_wt"]):.0f} kg',
                          "shipping"))
        edges.append(f'  "{s["delivery_no"]}" -> "{s["shipping_no"]}" [label="报关"];')

    for r in receipts:
        lines.append(node(r["receipt_no"],
                          f'收款 {r["receipt_no"]}\\n{r["paid_date"]} | {r["amount"]:,.2f} {r["currency"]} | {r["status"]}',
                          "receipt"))
        edges.append(f'  "{contract_no}" -> "{r["receipt_no"]}" [label="回款"];')

    lines.extend(edges)
    lines.append("}")
    st.graphviz_chart("\n".join(lines))


# ──────────────────────────────────────────────────────────────
# 库存查询
# ──────────────────────────────────────────────────────────────
def page_inventory():
    st.header("📦 库存查询")
    st.caption(
        "口径说明：当前库存 = 现在仓库里实际剩余的卷数（每次入库/出库确认后实时增减，"
        "与库存流水 stock_logs 逐笔对账）。库存是大池子，不按合同分开存放。"
    )

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

    # ── 同一物料跨合同分布: 一个料供几张合同, 各欠多少, 池子还剩多少 ──
    st.divider()
    st.subheader("🧩 同一物料跨合同分布")
    st.caption("库存是大池子、不按合同分开放。这里按物料看：几张合同在等这个料、各欠多少卷、池子里还剩多少。")

    mats_with_contracts = run_query(
        """
        SELECT DISTINCT sci.material_id, p.spec
        FROM sales_contract_items sci
        JOIN sales_contracts sc ON sci.contract_no = sc.contract_no
        JOIN products p ON sci.material_id = p.material_id
        WHERE sc.status NOT IN ('cancelled', 'completed')
        ORDER BY sci.material_id
        """
    )
    if mats_with_contracts:
        mat_opts = {f"{m['material_id']} - {m['spec']}": m["material_id"] for m in mats_with_contracts}
        picked_mat = st.selectbox("选择物料（只列有未完成合同的）", list(mat_opts), key="cross_mat")
        if picked_mat:
            mid = mat_opts[picked_mat]
            dist = run_query(
                """
                SELECT sc.contract_no, c.name AS customer_name, sc.status,
                       sci.quantity AS contract_qty,
                       (SELECT COALESCE(SUM(IF(doi.actual_quantity>0, doi.actual_quantity, doi.quantity)),0)
                          FROM delivery_order_items doi JOIN delivery_orders d ON doi.delivery_no=d.delivery_no
                         WHERE doi.contract_no=sci.contract_no AND doi.contract_item_no=sci.item_no
                           AND d.status IN ('confirmed','shipped')) AS shipped_qty
                FROM sales_contract_items sci
                JOIN sales_contracts sc ON sci.contract_no = sc.contract_no
                JOIN customers c ON sc.customer_code = c.code
                WHERE sci.material_id = %s AND sc.status NOT IN ('cancelled')
                ORDER BY sc.sign_date
                """,
                (mid,),
            )
            stock = run_query(
                "SELECT COALESCE(SUM(quantity),0) AS total FROM inventory WHERE material_id=%s",
                (mid,),
            )
            total_stock = stock[0]["total"] if stock else 0
            if dist:
                st.dataframe(
                    [
                        {
                            "合同号": r["contract_no"],
                            "客户": r["customer_name"],
                            "状态": status_badge(r["status"]),
                            "合同数(卷)": r["contract_qty"],
                            "已发(卷)": r["shipped_qty"],
                            "还欠(卷)": r["contract_qty"] - r["shipped_qty"],
                        }
                        for r in dist
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                owe = sum(r["contract_qty"] - r["shipped_qty"] for r in dist)
                c1, c2, c3 = st.columns(3)
                c1.metric("当前库存（全仓合计）", f"{int(total_stock)} 卷")
                c2.metric("所有合同还欠", f"{int(owe)} 卷")
                c3.metric(
                    "缺口（欠 − 库存）",
                    f"{int(owe - total_stock)} 卷",
                    delta="库存够用" if total_stock >= owe else "⚠️ 库存不够，需安排生产/采购",
                    delta_color="normal" if total_stock >= owe else "inverse",
                )
            else:
                st.info("该物料没有关联合同")
    else:
        st.info("暂无未完成合同的物料")



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

        # ── 合同进度: 生产/采购入库 → 发货 → 出库 → 当前库存 (按物料逐行)
        st.subheader("📈 合同进度（生产/采购 → 入库 → 发货 → 出库 → 库存）")
        progress = run_query(
            """
            SELECT sci.item_no, sci.material_id, p.spec, p.weight,
                   sci.quantity AS contract_qty,
                   (SELECT COALESCE(SUM(i.quantity),0)
                      FROM stock_in_items i JOIN stock_in s ON i.in_no=s.in_no
                     WHERE i.contract_no=sci.contract_no AND i.material_id=sci.material_id
                       AND s.in_type IN ('production','purchase') AND s.status='confirmed') AS produced_qty,
                   (SELECT COALESCE(SUM(IF(doi.actual_quantity>0, doi.actual_quantity, doi.quantity)),0)
                      FROM delivery_order_items doi JOIN delivery_orders d ON doi.delivery_no=d.delivery_no
                     WHERE doi.contract_no=sci.contract_no AND doi.contract_item_no=sci.item_no
                       AND d.status IN ('confirmed','shipped')) AS shipped_qty,
                   (SELECT COALESCE(SUM(oi.quantity),0)
                      FROM stock_out_items oi JOIN stock_out o ON oi.out_no=o.out_no
                     WHERE oi.contract_no=sci.contract_no AND oi.material_id=sci.material_id
                       AND o.status='confirmed') AS out_qty,
                   (SELECT COALESCE(SUM(quantity),0) FROM inventory
                     WHERE material_id=sci.material_id) AS stock_total,
                   (SELECT COALESCE(SUM(sci2.quantity - sci2.delivered_qty),0)
                      FROM sales_contract_items sci2
                      JOIN sales_contracts sc2 ON sci2.contract_no=sc2.contract_no
                     WHERE sci2.material_id=sci.material_id AND sci2.contract_no<>sci.contract_no
                       AND sc2.status NOT IN ('cancelled','completed')) AS other_contracts_owe
            FROM sales_contract_items sci
            JOIN products p ON sci.material_id = p.material_id
            WHERE sci.contract_no = %s
            ORDER BY sci.item_no
            """,
            (sel_contract,),
        )
        if progress:
            st.dataframe(
                [
                    {
                        "行号": r["item_no"],
                        "物料号": r["material_id"],
                        "规格": r["spec"],
                        "合同数(卷)": r["contract_qty"],
                        "已入库(卷)": r["produced_qty"],
                        "已发货(卷)": r["shipped_qty"],
                        "已发货(吨)": round(float(r["shipped_qty"]) * float(r["weight"]) / 1000, 3),
                        "已出库(卷)": r["out_qty"],
                        "当前库存(卷·全仓)": r["stock_total"],
                        "其他合同还欠(卷)": r["other_contracts_owe"],
                    }
                    for r in progress
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "「其他合同还欠」= 同一物料在其他未完成合同里的未发量。"
                "判断库存够不够：当前库存 ≥ 本合同未发 + 其他合同还欠 才够。"
            )
            with st.expander("❓ 这些列是什么意思？（点我看大白话解释）"):
                st.markdown(
                    """
| 列名 | 大白话解释 | 对应实际工作 |
| --- | --- | --- |
| **合同数** | 跟客户签合同时承诺的卷数 | 业务经理签合同 |
| **已入库** | 这张合同的货，工厂做完（或外协买回来）已经入到仓库的累计卷数。外协走"采购入库"，自产走"生产入库" | 车间完工/外协到货，仓库点收 |
| **已发货（卷/吨）** | **装柜后回填的实际卷数**（不是计划数）。预制发货单只是备货指令；装柜时可能有损耗，装完回填"实发数"才算真发了。吨位 = 实发卷数 × 单卷重量 | 仓库装柜、回填实发数 |
| **已出库** | 仓库账上实际出掉的卷数（这个动作才真正扣库存）。一般和已发货一致；调拨中转时会先出到临沂仓 | 仓库做出库单 |
| **当前库存** | 这个物料**现在所有仓库加总**还剩多少卷。注意：库存是个大池子，**不按合同分开存**——同一个物料供好几张合同时，池子是共用的 | 实时余量 |

**发货和出库的区别**：发货单管"对客户的承诺兑现了多少"（业务口径，算应收、算提成用它）；
出库单管"仓库货架上少了多少"（库存口径，盘仓用它）。正常一单对一单，调拨中转时会错开。
"""
                )

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
            "单据查询（按日期范围）",
            "客户订单总览（截止某日的生产/发货情况）",
            "低库存预警（库存 < 30）",
            "未发完合同（已确认但还有未发数量）",
            "待处理差异（pending credit_notes）",
            "本月汇率",
            "业务员提成基数（按客户汇总吨位/回款）",
        ],
    )

    if report_type == "客户订单总览（截止某日的生产/发货情况）":
        st.caption(
            "客户视角：截止你选的那天，这个客户下的所有合同，每个物料**生产入库了多少、"
            "发货发了多少、还欠多少**。入库/发货都只统计截止日及之前的单据。"
        )
        from datetime import date as _date2
        custs = run_query(
            "SELECT DISTINCT c.code, c.name FROM customers c "
            "JOIN sales_contracts sc ON sc.customer_code=c.code ORDER BY c.code"
        )
        if custs:
            c1, c2 = st.columns(2)
            with c1:
                cust_opts = {f"{c['code']} - {c['name']}": c["code"] for c in custs}
                picked_c = st.selectbox("客户", list(cust_opts), key="ov_cust")
            with c2:
                cutoff = st.date_input("截止日期", _date2.today(), key="ov_cutoff")
            rows = run_query(
                """
                SELECT sc.contract_no, sc.status AS contract_status,
                       sci.item_no, sci.material_id, p.spec,
                       sci.quantity AS contract_qty,
                       (SELECT COALESCE(SUM(i.quantity),0)
                          FROM stock_in_items i JOIN stock_in s ON i.in_no=s.in_no
                         WHERE i.contract_no=sci.contract_no AND i.material_id=sci.material_id
                           AND s.in_type IN ('production','purchase') AND s.status='confirmed'
                           AND s.in_date <= %s) AS produced_qty,
                       (SELECT COALESCE(SUM(IF(doi.actual_quantity>0, doi.actual_quantity, doi.quantity)),0)
                          FROM delivery_order_items doi JOIN delivery_orders d ON doi.delivery_no=d.delivery_no
                         WHERE doi.contract_no=sci.contract_no AND doi.contract_item_no=sci.item_no
                           AND d.status IN ('confirmed','shipped')
                           AND d.delivery_date <= %s) AS shipped_qty,
                       p.weight
                FROM sales_contract_items sci
                JOIN sales_contracts sc ON sci.contract_no=sc.contract_no
                JOIN products p ON sci.material_id=p.material_id
                WHERE sc.customer_code=%s AND sc.status NOT IN ('cancelled')
                ORDER BY sc.contract_no, sci.item_no
                """,
                (cutoff, cutoff, cust_opts[picked_c]),
            )
            if rows:
                st.dataframe(
                    [
                        {
                            "合同号": r["contract_no"],
                            "合同状态": status_badge(r["contract_status"]),
                            "物料号": r["material_id"],
                            "规格": r["spec"],
                            "合同数(卷)": r["contract_qty"],
                            "已生产入库(卷)": r["produced_qty"],
                            "已发货(卷)": r["shipped_qty"],
                            "已发货(吨)": round(float(r["shipped_qty"]) * float(r["weight"]) / 1000, 3),
                            "还欠(卷)": r["contract_qty"] - r["shipped_qty"],
                            "发货进度": f"{round(float(r['shipped_qty']) / float(r['contract_qty']) * 100, 1)}%" if r["contract_qty"] else "-",
                        }
                        for r in rows
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("该客户没有合同明细")

    elif report_type == "单据查询（按日期范围）":
        st.caption(
            "按日期范围查单据。默认按**出库日期**过滤；也可切到入库/发货/收款日期。"
            "数量列：发货单显示实发卷数/吨位（actual_quantity 优先），入出库单显示明细合计。"
        )
        from datetime import date as _date, timedelta as _td
        c1, c2, c3 = st.columns(3)
        with c1:
            d_from = st.date_input("从哪天", _date.today() - _td(days=30), key="docq_from")
        with c2:
            d_to = st.date_input("到哪天", _date.today() + _td(days=60), key="docq_to")
        with c3:
            date_field = st.selectbox(
                "按哪种日期查",
                ["出库日期", "入库日期", "发货日期", "收款日期"],
                key="docq_field",
            )

        if date_field == "出库日期":
            doc_rows = run_query(
                """
                SELECT o.out_no AS 单号, o.out_date AS 日期, o.out_type AS 类型,
                       o.warehouse_code AS 仓库, o.delivery_no AS 关联发货单,
                       o.status AS 状态, o.operator AS 经手人, o.remark AS 备注,
                       (SELECT SUM(i.quantity) FROM stock_out_items i WHERE i.out_no=o.out_no) AS 卷数,
                       (SELECT ROUND(SUM(i.quantity*p.weight)/1000,3)
                          FROM stock_out_items i JOIN products p ON i.material_id=p.material_id
                         WHERE i.out_no=o.out_no) AS 吨位
                FROM stock_out o
                WHERE o.out_date BETWEEN %s AND %s
                ORDER BY o.out_date DESC, o.out_no
                """,
                (d_from, d_to),
            )
        elif date_field == "入库日期":
            doc_rows = run_query(
                """
                SELECT s.in_no AS 单号, s.in_date AS 日期, s.in_type AS 类型,
                       s.warehouse_code AS 仓库, s.po_no AS 关联采购单,
                       s.status AS 状态, s.operator AS 经手人, s.remark AS 备注,
                       (SELECT SUM(i.quantity) FROM stock_in_items i WHERE i.in_no=s.in_no) AS 卷数,
                       (SELECT ROUND(SUM(i.quantity*p.weight)/1000,3)
                          FROM stock_in_items i JOIN products p ON i.material_id=p.material_id
                         WHERE i.in_no=s.in_no) AS 吨位
                FROM stock_in s
                WHERE s.in_date BETWEEN %s AND %s
                ORDER BY s.in_date DESC, s.in_no
                """,
                (d_from, d_to),
            )
        elif date_field == "发货日期":
            doc_rows = run_query(
                """
                SELECT d.delivery_no AS 单号, d.delivery_date AS 日期, d.customer_code AS 客户,
                       d.status AS 状态, d.receiver AS 收货人, d.remark AS 备注,
                       (SELECT SUM(IF(i.actual_quantity>0,i.actual_quantity,i.quantity))
                          FROM delivery_order_items i WHERE i.delivery_no=d.delivery_no) AS 实发卷数,
                       (SELECT ROUND(SUM(IF(i.actual_quantity>0,i.actual_quantity,i.quantity)*p.weight)/1000,3)
                          FROM delivery_order_items i JOIN products p ON i.material_id=p.material_id
                         WHERE i.delivery_no=d.delivery_no) AS 实发吨位
                FROM delivery_orders d
                WHERE d.delivery_date BETWEEN %s AND %s
                ORDER BY d.delivery_date DESC, d.delivery_no
                """,
                (d_from, d_to),
            )
        else:
            doc_rows = run_query(
                """
                SELECT r.receipt_no AS 单号, r.paid_date AS 日期, r.customer_code AS 客户,
                       r.contract_no AS 关联合同, r.amount AS 金额, r.currency AS 币种,
                   r.status AS 状态, r.remark AS 备注
                FROM receipts r
                WHERE r.paid_date BETWEEN %s AND %s
                ORDER BY r.paid_date DESC, r.receipt_no
                """,
                (d_from, d_to),
            )
        if doc_rows:
            st.success(f"{d_from} ~ {d_to} 共 {len(doc_rows)} 张单据")
            st.dataframe(doc_rows, use_container_width=True, hide_index=True)
        else:
            st.info(f"{d_from} ~ {d_to} 没有{date_field}的单据")

    elif report_type == "业务员提成基数（按客户汇总吨位/回款）":
        st.caption(
            "提成规则说明：三种方式（按量·元/吨 ｜ 按价格 ｜ 按回款时间）各有系数，"
            "系数未定前本表先出**基数**。**吨位基数按实际发货重量**（2026-08-14 老板定："
            "实发与合同有偏差，±5% 内合理，超 5% 标红关注）。坏账扣减：损失 ≤1% 不报警，"
            "超出部分等额扣提成（R13）。"
        )
        # 吨位基数 = Σ 发货明细实际数量 × 单重(products.weight) / 1000 (kg→吨)
        # 实发口径: actual_quantity>0 优先否则 quantity (同校验第 5 步); 已确认发货单
        # 注意: 合同吨位用客户级子查询单独汇总 (整合同口径), 不与发货行直接 JOIN,
        #       避免同一合同行分多批发货时合同数量被重复计数。
        # 数量偏差 = (累计实发 - 合同总量) / 合同总量; 分批未发完时显示负偏差属正常。
        rows = run_query(
            """
            SELECT sp.code AS 业务员, sp.name AS 姓名,
                   c.code AS 客户编码, c.name AS 客户名称,
                   d.cnt AS 发货单数,
                   ROUND(d.tons, 3) AS 实发吨位_基数,
                   ROUND(ct.tons, 3) AS 合同吨位_对照,
                   ROUND((d.qty - ct.qty) / NULLIF(ct.qty, 0) * 100, 2) AS 数量偏差_pct
            FROM customers c
            JOIN salespersons sp ON sp.code = LEFT(c.code, 1)
            JOIN (
                SELECT sc.customer_code,
                       COUNT(DISTINCT doi.delivery_no) AS cnt,
                       SUM(IF(doi.actual_quantity > 0, doi.actual_quantity, doi.quantity)) AS qty,
                       SUM(IF(doi.actual_quantity > 0, doi.actual_quantity, doi.quantity)
                           * p.weight) / 1000 AS tons
                FROM delivery_order_items doi
                JOIN delivery_orders d2 ON doi.delivery_no = d2.delivery_no
                JOIN sales_contracts sc ON doi.contract_no = sc.contract_no
                JOIN products p ON doi.material_id = p.material_id
                WHERE d2.status IN ('confirmed', 'shipped')
                GROUP BY sc.customer_code
            ) d ON d.customer_code = c.code
            LEFT JOIN (
                SELECT sc.customer_code,
                       SUM(sci.quantity) AS qty,
                       SUM(sci.quantity * p.weight) / 1000 AS tons
                FROM sales_contracts sc
                JOIN sales_contract_items sci ON sci.contract_no = sc.contract_no
                JOIN products p ON sci.material_id = p.material_id
                WHERE sc.status NOT IN ('cancelled')
                  AND sc.contract_no IN (
                      SELECT DISTINCT doi.contract_no
                      FROM delivery_order_items doi
                      JOIN delivery_orders d3 ON doi.delivery_no = d3.delivery_no
                      WHERE d3.status IN ('confirmed', 'shipped')
                  )
                GROUP BY sc.customer_code
            ) ct ON ct.customer_code = c.code
            ORDER BY sp.code, 实发吨位_基数 DESC
            """
        )
        if rows:
            for r in rows:
                dev = r.get("数量偏差_pct")
                if dev is not None and abs(float(dev)) > 5:
                    st.warning(
                        f"⚠️ {r['客户编码']} {r['客户名称']}：累计实发与合同数量偏差 {dev}%"
                        "（超 ±5% 合理线；若为分批未发完的负偏差则属正常）"
                    )
            st.dataframe(rows, use_container_width=True, hide_index=True)
            # 业务员小计 (实发口径)
            st.subheader("业务员小计（实发吨位 = 提成按量基数）")
            summary = run_query(
                """
                SELECT sp.code AS 业务员, sp.name AS 姓名,
                       COUNT(DISTINCT doi.delivery_no) AS 发货单数,
                       COUNT(DISTINCT c.code) AS 客户数,
                       ROUND(SUM(IF(doi.actual_quantity>0, doi.actual_quantity, doi.quantity) * p.weight) / 1000, 3) AS 实发吨位合计
                FROM delivery_order_items doi
                JOIN delivery_orders d ON doi.delivery_no = d.delivery_no
                JOIN sales_contracts sc ON doi.contract_no = sc.contract_no
                JOIN customers c ON sc.customer_code = c.code
                JOIN products p ON doi.material_id = p.material_id
                JOIN salespersons sp ON sp.code = LEFT(c.code, 1)
                WHERE d.status IN ('confirmed', 'shipped')
                GROUP BY sp.code, sp.name
                ORDER BY 实发吨位合计 DESC
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
