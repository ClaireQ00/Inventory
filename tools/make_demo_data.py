#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成一套演示用的"假真实数据"
============================

为什么需要它:
- 真实数据放在 data/csv 下, 不进仓库, 别人看不到
- 但本项目要能"开箱即跑", 让别人知道这套流程长啥样
- 所以这个脚本生成一套 "假但完整" 的数据

⚠️ 安全约定 (2026-07-28 事故后加):
- 演示数据写到独立目录 `data/csv/demo_runtime/`, **绝对不写到 `data/csv/` 根目录**
- 真实基础资料 (products/suppliers/customers/warehouses) 一旦录入绝不能被 demo 覆盖
- 历史教训: 之前写到 data/csv/ 根目录, --demo 模式覆盖了真实数据, 没备份很难恢复

使用方法:
    python3 tools/make_demo_data.py              # 生成到 data/csv/demo_runtime/
    bash scripts/run_local_validation.sh --demo  # 用 demo_runtime 跑验证 (见 scripts/)

注意: 生成的数据全是假的 (物料号 DEMO-*, 客户 客户A/客户B 等)
绝对不会跟真实业务重名, 即使不小心提交到仓库也不算泄密
"""

import os
import csv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ⚠️ 演示数据只能写这里, 不能写到 data/csv/ 根目录 (会覆盖真实数据)
CSV_DIR = os.path.join(ROOT_DIR, "data", "csv", "demo_runtime")

# 永远不许被覆盖的"真实数据"文件名 (即使脚本路径改错也兜底)
PROTECTED_FILES = {
    "products.csv", "suppliers.csv", "customers.csv", "warehouses.csv",
}


def write_csv(filename, headers, rows):
    # 守卫: 如果 CSV_DIR 是 data/csv 根目录, 4 张真实基础资料绝不能被覆盖
    # 在 demo_runtime 子目录里允许写同名文件 (因为那是独立沙箱)
    csv_root = os.path.join(ROOT_DIR, "data", "csv")
    if os.path.abspath(CSV_DIR) == os.path.abspath(csv_root):
        if filename in PROTECTED_FILES:
            raise RuntimeError(
                f"安全拦截: 不允许把 demo 数据写到 {csv_root}/{filename} (会覆盖真实基础资料)。"
                f"请检查 CSV_DIR 配置, demo 应输出到 data/csv/demo_runtime/ 等子目录。"
            )
    os.makedirs(CSV_DIR, exist_ok=True)
    path = os.path.join(CSV_DIR, filename)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"  [生成] {filename}  ({len(rows)} 行)")


def main():
    print("生成演示数据 (假但完整)...")
    print(f"  输出目录: {CSV_DIR}")
    print(f"  (独立目录, 不会覆盖 data/csv/ 下的真实数据)\n")

    # 1. 物料 (含外观尺寸, 用于算单件体积 CBM)
    # 单件体积公式: appearance_outer² × appearance_height × 0.93 / 1e6
    # DEMO-M-001: 40 × 40 × 30 × 0.93 / 1e6 = 0.0446 CBM
    # DEMO-M-002: 33 × 33 × 25 × 0.93 / 1e6 = 0.0253 CBM
    # DEMO-M-003: 20 × 20 × 15 × 0.93 / 1e6 = 0.0056 CBM
    write_csv(
        "products.csv",
        ["id", "material_id", "customer_code", "brand", "product_category",
         "material_type", "spec", "inner_diameter", "outer_diameter",
         "id_x_od", "thickness", "weight_per_meter", "weight",
         "appearance_outer", "appearance_height", "volume", "is_active"],
        [
            [1, "DEMO-M-001", "C-A", "华孚", "线管", "出口线管", '1-1/4"',
             32, 40.36, "32x40.36", 4.18, 640, 64, 40, 30, 0.0446, 1],
            [2, "DEMO-M-002", "C-B", "华孚", "线管", "出口线管", '1"',
             25, 32.5, "25x32.5", 3.75, 410, 41, 33, 25, 0.0253, 1],
            [3, "DEMO-M-003", "C-A", "华孚", "线管", "出口线管", '1/2"',
             13, 18.5, "13x18.5", 2.75, 130, 13, 20, 15, 0.0056, 1],
        ],
    )

    # 2. 仓库
    write_csv(
        "warehouses.csv",
        ["id", "code", "name", "address", "is_active"],
        [
            [1, "WH-01", "主仓库", "宁波市海曙区DEMO路1号", 1],
            [2, "WH-02", "外协仓", "宁波市江北区DEMO路2号", 1],
        ],
    )

    # 3. 供应商 (含本公司 SUP-003, is_self=1, 用于合同模板调取卖方信息)
    write_csv(
        "suppliers.csv",
        ["id", "code", "name", "contact_person", "phone", "address", "is_self", "is_active"],
        [
            [1, "SUP-001", "DEMO塑胶原料厂", "张经理", "13800000001", "浙江省DEMO市", 0, 1],
            [2, "SUP-002", "DEMO包装材料厂", "李经理", "13800000002", "浙江省DEMO市", 0, 1],
            [3, "SUP-003", "DEMO 本公司 (卖方)", "DEMO老板", "13800000003", "山东省DEMO市", 1, 1],
        ],
    )

    # 4. 客户
    write_csv(
        "customers.csv",
        ["id", "code", "name", "contact_person", "phone", "address", "is_active"],
        [
            [1, "C-001", "客户A (DEMO)", "Mr.A", "+86-000-00000001", "上海市DEMO路", 1],
            [2, "C-002", "客户B (DEMO)", "Mr.B", "+86-000-00000002", "广州市DEMO路", 1],
        ],
    )

    # 5. 采购单 (注意金额跟明细对得上)
    #    total_volume = Σ volume_subtotal = 0.446 + 0.253 = 0.699 (展示统计, 非报关数)
    write_csv(
        "purchase_orders.csv",
        ["id", "po_no", "supplier_id", "order_date", "expected_date",
         "total_amount", "total_volume", "status", "remark"],
        [
            [1, "PO20260726001", 1, "2026-07-20", "2026-07-25", 20000, 0.699, "confirmed", "演示采购单1"],
        ],
    )

    # 6. 采购明细 (10件@1000 + 10件@1000 = 20000)
    #    体积: DEMO-M-001 0.0446 × 10 = 0.446
    #          DEMO-M-002 0.0253 × 10 = 0.253
    write_csv(
        "purchase_order_items.csv",
        ["id", "po_id", "product_id", "quantity", "unit_price", "subtotal",
         "volume_subtotal", "received_qty", "remark"],
        [
            [1, 1, 1, 10, 1000, 10000, 0.446, 0, "明细1"],
            [2, 1, 2, 10, 1000, 10000, 0.253, 0, "明细2"],
        ],
    )

    # 7. 销售合同
    #    [改] 加金额四件套 + 贸易条款
    #    R11: 件价改后 total = 8634.57 USD × 7.15 = 61737.17 CNY
    #    total_volume = Σ volume_subtotal = 0.3568 + 0.3542 = 0.711 (展示统计, 非报关数)
    write_csv(
        "sales_contracts.csv",
        ["id", "contract_no", "customer_id", "sign_date", "delivery_deadline",
         "currency", "total_amount", "exchange_rate", "total_amount_cny",
         "total_volume",
         "trade_terms", "port_loading", "port_discharge", "freight", "insurance",
         "status", "payment_term", "packing", "remark"],
        [
            [1, "SC20260720001", 1, "2026-07-15", "2026-08-15",
             "USD", 8634.5688, 7.15, 61737.1669,
             0.711,
             "FOB", "Qingdao", "Jakarta", 0, 0,
             "confirmed",
             "TT 30% DOWN + BALANCE BEFORE COPY OF B/L",
             "PACKED IN WOVEN BAGS OF 500 COILS EACH",
             "演示合同"],
        ],
    )

    # 8. 合同明细 (R11: 件价由报价系数 1.112 × 汇率 7.15 × 单重 反推, 让第15步反算精确通过)
    #    体积: DEMO-M-001 0.0446 × 8  = 0.3568
    #          DEMO-M-002 0.0253 × 14 = 0.3542
    #    件价: DEMO-M-001 1.112×7.15×64 = 508.8512 → 508.85 (×8 = 4070.81)
    #          DEMO-M-002 1.112×7.15×41 = 325.9828 → 325.98 (×14 = 4563.76)
    write_csv(
        "sales_contract_items.csv",
        ["id", "contract_id", "product_id", "quantity", "unit_price", "subtotal",
         "volume_subtotal", "delivered_qty", "remark"],
        [
            [1, 1, 1, 8, 508.8512, 4070.8096, 0.3568, 0, "合同行1"],
            [2, 1, 2, 14, 325.9828, 4563.7592, 0.3542, 0, "合同行2"],
        ],
    )

    # 9. 入库单 (跟采购单 1 关联) + 调拨入库 (从主仓调到外协仓的接收端)
    write_csv(
        "stock_in.csv",
        ["id", "in_no", "in_type", "warehouse_id", "po_id", "operator",
         "in_date", "status", "transfer_ref", "remark"],
        [
            [1, "IN20260726001", "purchase", 1, 1, "DEMO操作员",
             "2026-07-26", "confirmed", "", "采购到货"],
            [2, "TR20260729001-IN", "transfer", 2, "", "DEMO操作员",
             "2026-07-29", "confirmed", "TR20260729001", "从主仓调入(调拨接收端)"],
        ],
    )

    # 10. 入库明细 (采购 10+10, 调拨接收物料1 3件)
    write_csv(
        "stock_in_items.csv",
        ["id", "stock_in_id", "product_id", "quantity", "remark"],
        [
            [1, 1, 1, 10, "物料1全部到货"],
            [2, 1, 2, 10, "物料2全部到货"],
            [3, 2, 1, 3, "调拨入库: 从主仓接收 3 件"],
        ],
    )

    # 11. 发货单 (跟客户 1 关联)
    #     total_volume = Σ volume_subtotal = 0.223 + 0.253 = 0.476 (展示统计, 非报关数)
    write_csv(
        "delivery_orders.csv",
        ["id", "delivery_no", "customer_id", "delivery_date", "receiver",
         "receiver_phone", "receiver_address", "transport_no",
         "total_volume", "status", "remark"],
        [
            [1, "DN20260726001", 1, "2026-07-26", "Mr.A 收货人",
             "+86-000-00000001", "上海市DEMO路", "SF-DEMO-0001",
             0.476, "confirmed", "首批发货"],
        ],
    )

    # 12. 发货明细 (物料1发5, 物料2发10, 都没超合同)
    #     体积: DEMO-M-001 0.0446 × 5  = 0.223
    #           DEMO-M-002 0.0253 × 10 = 0.253
    #     [新增] actual_quantity 装柜后填, 这里假设全部满发, short_qty=0
    write_csv(
        "delivery_order_items.csv",
        ["id", "delivery_id", "contract_item_id", "product_id", "quantity",
         "actual_quantity", "short_qty", "volume_subtotal", "remark"],
        [
            [1, 1, 1, 1, 5, 5, 0, 0.223, "合同行1发5 (满发)"],
            [2, 1, 2, 2, 10, 10, 0, 0.253, "合同行2发10 (满发)"],
        ],
    )

    # 12b. [改] 报关单 shipping_records (跟发货单 1 关联)
    #      装柜后填, total_pkgs 跟 actual_qty 对齐
    #      [改] total_amount_usd -> 金额四件套: currency/total_amount/exchange_rate/total_amount_cny
    #      4500 USD × 7.15 = 32175 CNY
    write_csv(
        "shipping_records.csv",
        ["id", "shipping_no", "delivery_id", "shipping_date", "container_no",
         "seal_no", "vessel", "total_pkgs", "total_gross_wt", "total_net_wt",
         "total_cbm", "currency", "total_amount", "exchange_rate", "total_amount_cny",
         "status", "remark"],
        [
            [1, "SH20260726001", 1, "2026-07-26", "MSCU-DEMO-1234",
             "SEAL-001", "OOCL DEMO / V.001", 15, 320.50, 289.50,
             0.476, "USD", 4500.00, 7.15, 32175.00,
             "customs_cleared", "首船报关 (正常场景, 无短装)"],
        ],
    )

    # 12c. [新增] 报关明细 shipping_record_items
    #      planned_qty 从发货单带, actual_qty = planned_qty (满发, 不触发 UCP600 容差)
    #      subtotal_usd = actual_qty × unit_price_usd
    write_csv(
        "shipping_record_items.csv",
        ["id", "shipping_id", "product_id", "planned_qty", "actual_qty",
         "shipping_mark", "gross_weight_per", "net_weight_per", "unit_volume",
         "unit_price_usd", "subtotal_usd", "remark"],
        [
            [1, 1, 1, 5, 5, "PAGODA / C-001 / SH20260726001",
             12.80, 11.50, 0.0446, 500.00, 2500.00, "物料1 实发5"],
            [2, 1, 2, 10, 10, "PAGODA / C-001 / SH20260726001",
             11.30, 10.20, 0.0253, 200.00, 2000.00, "物料2 实发10"],
        ],
    )

    # 12d. [改] 贷记单 credit_notes (本场景无差异, 留空表头示范)
    #      真实业务里短装时会在这里挂一条 pending → replenish/refund/writeoff
    #      [改] 加金额四件套: currency / diff_amount / exchange_rate / diff_amount_cny
    write_csv(
        "credit_notes.csv",
        ["id", "cn_no", "shipping_id", "contract_item_id", "product_id",
         "diff_qty", "currency", "diff_amount", "exchange_rate", "diff_amount_cny",
         "resolution", "resolved_at", "remark"],
        [
            # 故意留空: 本 demo 是"正常报关无短装"场景
            # 短装示例见 .claude/skills/trade-documents/SKILL.md
            # (T2.4 短装场景改走 tests/ 独立测试路线, 不污染 demo, 见 TASKS.md)
        ],
    )

    # 12e. [新增] 汇率表 exchange_rates (第7模块)
    #      业务约定: 每月1日记录一次当月固定汇率
    #      演示场景: 2026-07 月的 USD/EUR 汇率 (人民币记账用)
    write_csv(
        "exchange_rates.csv",
        ["id", "currency", "rate_to_cny", "effective_date", "source", "remark"],
        [
            [1, "USD", 7.15, "2026-07-01", "manual", "2026年7月美元固定汇率"],
            [2, "EUR", 7.85, "2026-07-01", "manual", "2026年7月欧元固定汇率"],
        ],
    )

    # 12f. [新增] 应收收款 receipts (第7模块)
    #      跟报关单 1 关联, 4500 USD × 7.15 = 32175 CNY
    #      业务场景: 客户 T/T 全款到账, 跟合同/报关单金额对齐
    write_csv(
        "receipts.csv",
        ["id", "receipt_no", "customer_id", "contract_id", "shipping_id",
         "delivery_id", "amount", "currency", "exchange_rate", "amount_cny",
         "paid_date", "pay_method", "bank_ref", "status", "remark"],
        [
            [1, "RC20260726001", 1, 1, 1, 1,
             4500.00, "USD", 7.15, 32175.00,
             "2026-07-26", "T/T", "BK-DEMO-001",
             "confirmed", "首船全款到账 (T/T in advance)"],
        ],
    )

    # 12g. [新增 R10] 报价参数 quotation_params (全局键值对)
    #      业务背景: 全局参数表, 存默认汇率/默认币种/报价有效期
    #      注意: 这里 exchange_rate=7.25 是报价专用汇率 (跟 exchange_rates 表的月度汇率独立)
    write_csv(
        "quotation_params.csv",
        ["param_key", "param_value", "effective_date", "description"],
        [
            ["exchange_rate", "7.25", "2026-07-01", "报价专用汇率 (USD→CNY)"],
            ["default_currency", "USD", "", "默认报价币种"],
            ["valid_days", "7", "", "报价有效期天数"],
        ],
    )

    # 12h. [新增 R10] 报价主表 quotations (2 条: 简要报价 + 正式 QT)
    #      QT001 简要报价 → 后续可派生 QT002 正式报价 (parent_quote_id=1)
    #
    #      QT001 total_amount 汇总 (不是 DERIVED_RULES 算的, 是 Σ quotation_items.subtotal):
    #        明细1 subtotal (DEMO-M-001, 64kg × 1.112 × 10) = 711.68
    #        明细2 subtotal (DEMO-M-002, 41kg × 1.112 × 10) = 455.92
    #        合计 = 711.68 + 455.92 = 1167.60
    #      total_amount_cny 派生 (DERIVED_RULES 算): 1167.60 × 7.25 = 8465.10
    #      total_volume (展示统计) = Σ quotation_items.total_volume = 0.446 + 0.253 = 0.699
    #
    #      QT002 是从 QT001 派生的正式报价 (parent_quote_id=1), 暂无明细 → total_amount=0, total_volume=0
    write_csv(
        "quotations.csv",
        ["quote_no", "customer_id", "quote_type", "parent_quote_id", "version",
         "quote_date", "valid_until", "total_amount", "currency", "exchange_rate",
         "total_amount_cny", "total_volume", "status", "converted_contract_id",
         "trade_terms", "port_loading", "port_discharge", "payment_term", "packing",
         "remark"],
        [
            # QT001: Q025 简要报价, 客户A(id=1), 总价 1167.60 USD × 7.25 = 8465.10 CNY
            # brief 阶段不带贸易/付款/包装条款 (确认后才补)
            ["QT20260729001", 1, "brief", "", 1,
             "2026-07-29", "2026-08-05", 1167.60, "USD", 7.25,
             8465.10, 0.699, "draft", "",
             "", "", "", "", "",
             "Q025 简要报价 (R10 系数定价)"],
            # QT002: 正式 QT, 从 QT001 派生 (parent_quote_id=1), 暂无明细故金额=0
            # formal 阶段带完整 5 个外贸条款字段
            ["QT20260729002", 1, "formal", 1, 1,
             "2026-07-29", "2026-08-05", 0, "USD", 7.25,
             0, 0, "draft", "",
             "FOB", "Qingdao", "Jakarta",
             "TT 30% DOWN + BALANCE BEFORE COPY OF B/L",
             "PACKED IN WOVEN BAGS OF 500 COILS EACH",
             "从 QT001 派生的正式 QT (待补明细)"],
        ],
    )

    # 12i. [新增 R10] 报价明细 quotation_items (对应 QT001=quote_id 1)
    #      定价铁律 R10: unit_price = weight_per_unit × price_coefficient (USD/KG)
    #      subtotal 直接展开 = weight_per_unit × price_coefficient × quantity (不走派生 unit_price)
    #
    #      明细1: DEMO-M-001 (id=1, weight=64kg)
    #        total_weight = 64 × 10 = 640
    #        unit_price   = 64 × 1.112 = 71.168
    #        subtotal     = 64 × 1.112 × 10 = 711.68
    #        volume       = 0.0446 (从 products 带出), total_volume = 0.0446 × 10 = 0.446
    #
    #      明细2: DEMO-M-002 (id=2, weight=41kg)
    #        total_weight = 41 × 10 = 410
    #        unit_price   = 41 × 1.112 = 45.592
    #        subtotal     = 41 × 1.112 × 10 = 455.92
    #        volume       = 0.0253 (从 products 带出), total_volume = 0.0253 × 10 = 0.253
    write_csv(
        "quotation_items.csv",
        ["quote_id", "product_id", "group_code", "price_coefficient",
         "weight_per_unit", "quantity", "total_weight", "unit_price", "subtotal",
         "volume", "total_volume", "remark"],
        [
            # 派生字段算好填进去 (跟现有 demo 风格一致, 如 purchase_order_items 的 subtotal/volume_subtotal)
            [1, 1, "A组-1.112", 1.112, 64, 10, 640, 71.168, 711.68, 0.0446, 0.446, "1-1/4管"],
            [1, 2, "A组-1.112", 1.112, 41, 10, 410, 45.592, 455.92, 0.0253, 0.253, "1寸管"],
        ],
    )

    # 13. 出库单 (跟发货单 1 关联) + 调拨出库 (从主仓调到外协仓的发出端)
    write_csv(
        "stock_out.csv",
        ["id", "out_no", "out_type", "warehouse_id", "delivery_id", "operator",
         "out_date", "status", "transfer_ref", "remark"],
        [
            [1, "OUT20260726001", "sale", 1, 1, "DEMO操作员",
             "2026-07-26", "confirmed", "", "销售出库"],
            [2, "TR20260729001-OUT", "transfer", 1, "", "DEMO操作员",
             "2026-07-29", "confirmed", "TR20260729001", "调拨到外协仓(调拨发出端)"],
        ],
    )

    # 14. 出库明细 (销售 5+10, 调拨发出物料1 3件)
    write_csv(
        "stock_out_items.csv",
        ["id", "stock_out_id", "product_id", "quantity", "remark"],
        [
            [1, 1, 1, 5, ""],
            [2, 1, 2, 10, ""],
            [3, 2, 1, 3, "调拨出库: 发往仓库2 3 件"],
        ],
    )

    # 15. 当前库存
    #     物料1: 采购入 10 - 销售出 5 - 调拨出 3 = 2  (仓库1)
    #            调拨入 3 = 3                            (仓库2)
    #     物料2: 采购入 10 - 销售出 10 = 0              (仓库1)
    write_csv(
        "inventory.csv",
        ["id", "product_id", "warehouse_id", "quantity"],
        [
            [1, 1, 1, 2],
            [2, 2, 1, 0],
            [3, 1, 2, 3],
        ],
    )

    print("\n[完成] 演示数据生成完毕。")
    print("下一步: bash scripts/run_local_validation.sh")


if __name__ == "__main__":
    main()
