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
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

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
        "【提示】本界面为阶段一原型，\n"
        "数据录入仍通过 CSV → 校验 → 导入流程。\n"
        "详见 docs/VALIDATION_GUIDE.md"
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


# ──────────────────────────────────────────────────────────────
# 基础资料
# ──────────────────────────────────────────────────────────────
def page_master_data():
    st.header("🏭 基础资料")

    subtab = st.tabs(["产品", "客户", "供应商", "仓库"])

    with subtab[0]:
        st.subheader("📦 产品物料")
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

    with subtab[3]:
        st.subheader("🏭 仓库")
        warehouses = run_query(
            "SELECT code, name, address, is_active FROM warehouses ORDER BY code"
        )
        if warehouses:
            st.dataframe(warehouses, use_container_width=True, hide_index=True)
        else:
            st.info("暂无仓库数据")


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
        ],
    )

    if report_type == "低库存预警（库存 < 30）":
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
# 主路由
# ──────────────────────────────────────────────────────────────
PAGES = {
    "🏠 首页": page_dashboard,
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
