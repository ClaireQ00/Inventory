#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV -> SQL 通用导入脚本
=====================作用（用大白话说）:
把一张 CSV 表 (比如真实客户的 Excel 另存为 CSV)
翻译成数据库能直接执行的 INSERT 语句。

为什么需要它:
- 你在 Excel/Numbers 里填好真实数据 -> 另存为 CSV
- 本脚本负责把 CSV 转成 SQL, 避免手工写 INSERT 写错
- 真实 CSV 只放在本地 data/ 下, 生成的 SQL 也写本地, 不会进仓库

基本用法:
    python3 tools/csv_to_sql.py <csv路径> <表名> <输出SQL路径>

示例:
    python3 tools/csv_to_sql.py data/csv/products.csv products data/sql/04_products.sql

注意:
- CSV 第一行必须是表字段名 (跟数据库表字段一一对应)
- 空单元格 -> NULL
- 脚本会对值做参数化处理, 防 SQL 注入 (即使是真实数据也安全)
"""

import csv
import sys
import os
import math
import argparse


# ------------------------------------------------------------
# 一些"派生字段"的自动计算规则
# 比如外径 = 内径 + 壁厚 * 2, 这种可以从其它列算出来, 不用人工填
# 写在这里的好处: 人工填容易算错, 脚本算不会错
#
# 每条规则包含:
#   "expr"           : 计算函数, 输入 row 字典, 输出计算值 (算不出返回 None)
#   "depends_on"     : 依赖的字段 (必须存在于 CSV 才能算)
#   "tolerance"      : 反向校验时的容差数值
#   "tolerance_mode" : 容差方式 (可选)
#                      "absolute" (默认): 容差是绝对值, 例如 0.05 mm
#                      "percent":         容差是百分比 (0~1), 例如 0.05 表示 5%
#   "skip_if_no_dep" : 依赖字段不全时是否跳过 (默认 True)
# ------------------------------------------------------------
DERIVED_RULES = {
    # ============================================================
    # products 物料主数据
    # ============================================================
    "products": {
        # A0: 厚度 (mm) 反推
        # 业务场景: 客户没给厚度, 系统按以下优先级反推 (任一可用即可):
        #
        # 路径 A (优先, 几何): outer_diameter
        #     厚度 = (外径 - 内径) / 2
        #     不依赖密度, 跟产品类别无关, 100% 精确
        #
        # 路径 B (密度方程): weight_per_meter
        #     解一元二次方程
        #
        # 路径 C (密度方程): weight + length
        #     先算米重 = 单重 × 1000 / 长度, 再走路径 B
        #
        # 必要字段: inner_diameter (所有路径都需要)
        # 注意: 路径 B/C 还需要 product_category 决定密度, 但 depends_on 里
        #       写 product_category 会让纯几何路径也被卡, 所以放到 expr 内判断
        "thickness": {
            "expr": lambda row: calc_theoretical_thickness(row),
            "depends_on": ["inner_diameter"],
            "depends_on_any": [
                ["outer_diameter"],
                ["product_category", "weight_per_meter"],
                ["product_category", "weight", "length"],
            ],
            "tolerance": 0.05,
            "tolerance_mode": "percent",  # 厚度也用 5% 容差
            # 2026-08-01 真实主数据导入约定: 客户手填值与公式超差时保留客户值,
            # 只 WARN 不阻止生成 (偏差提示写入 remark)
            "mismatch_level": "warn",
            "description": "厚度(mm) 反推: 优先从 (外径-内径)/2 几何反推, 其次密度方程",
        },
        # A1: 外径 (mm) = 内径 + 壁厚 × 2
        "outer_diameter": {
            "expr": lambda row: _safe_add(
                _to_float(row.get("inner_diameter")),
                _mul(_to_float(row.get("thickness")), 2),
            ),
            "depends_on": ["inner_diameter", "thickness"],
            "tolerance": 0.05,  # mm
            "description": "外径 = 内径 + 壁厚 × 2",
        },
        # A2: 内径x外径 字符串拼接
        "id_x_od": {
            "expr": lambda row: _format_id_od(
                row.get("inner_diameter"), row.get("outer_diameter")
            ),
            "depends_on": ["inner_diameter", "outer_diameter"],
            "tolerance": None,
            "description": "内径x外径字符串拼接",
        },
        # A2b: 规格 spec 自动拼接
        # 规则: {英寸} ID{内径mm} -{标称米数}M [(短|中|长)]
        # - spec_meter 为空时退化为 "{英寸} ID{内径mm}"
        # - 短/中/长 标签按 spec_meter 自动判: <=20短, 21~45中, 46~99长, >=100无标签
        "spec": {
            "expr": lambda row: _build_spec(row),
            "depends_on": ["inner_diameter_inch", "inner_diameter", "spec_meter"],
            "tolerance": None,
            "description": "规格 = 英寸 + ID内径 + -标称米数M + 短/中/长标签",
        },
        # A3: 单件重量 (kg)
        # 业务规则: 用密度公式算理论值, 5% 内算正常
        # 公式链: 密度 -> 理论米重 -> 理论单件重量
        # 详见 calc_theoretical_weight()
        "weight": {
            "expr": lambda row: calc_theoretical_weight(row),
            "depends_on": ["product_category", "inner_diameter", "thickness", "length"],
            "tolerance": 0.05,
            "tolerance_mode": "percent",  # 5% 百分比容差
            # 2026-08-01 真实主数据导入约定: 保留客户手填值, 超差只 WARN
            "mismatch_level": "warn",
            "description": "单件重量(kg) = (内径+厚度)×厚度×3.14×密度×长度/1000",
        },
        # E1: 米重 (g/m)
        # 同样用密度公式算理论值, 5% 内算正常
        "weight_per_meter": {
            "expr": lambda row: calc_theoretical_weight_per_meter(row),
            "depends_on": ["product_category", "inner_diameter", "thickness"],
            "tolerance": 0.05,
            "tolerance_mode": "percent",
            # 2026-08-01 真实主数据导入约定: 保留客户手填值, 超差只 WARN
            "mismatch_level": "warn",
            "description": "米重(g/m) = (内径+厚度)×厚度×3.14×密度",
        },
        # A4: 单件体积 CBM (m³) = 外观外径(cm)² × 外观高度(cm) × 0.93 / 1e6
        # 外贸装箱经验系数 0.93: 圆卷装柜, 毛圆柱(π/4≈0.785)偏小、长方体(1.0)偏大,
        # 0.93 介于六方密排(0.87)与方阵(1.0)之间, 预算舱位略保守 (2026-08-10 老板拍板统一口径)
        # 单位铁律: appearance_outer / appearance_height 都是 cm (卷的外观尺寸, 非管子口径),
        # 1e6 把 cm³ 换算成 m³。注意: 早期文档误写 mm, 若按 mm 录入体积会大 1000 倍!
        "volume": {
            "expr": lambda row: (
                lambda ao, ah: _safe_div(
                    _safe_mul(_safe_mul(_safe_mul(ao, ao), ah), 0.93, 6),
                    1_000_000,
                    ndigits=4,
                )
            )(
                _to_float(row.get("appearance_outer")),
                _to_float(row.get("appearance_height")),
            ),
            "depends_on": ["appearance_outer", "appearance_height"],
            "tolerance": 0.001,  # m³
            "description": "单件体积(CBM) = 外观外径(mm)² × 外观高度(mm) × 0.93 / 1e6",
        },
    },

    # ============================================================
    # 采购单明细 purchase_order_items
    # ============================================================
    "purchase_order_items": {
        # C1: 小计金额 = 数量 × 单价
        "subtotal": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("quantity")),
                _to_float(row.get("unit_price")),
                ndigits=2,
            ),
            "depends_on": ["quantity", "unit_price"],
            "tolerance": 0.01,
            "description": "采购明细小计 = 数量 × 单价",
        },
        # D1: 体积小计 = 单件体积 × 数量
        # 注意: 单件体积(unit_volume) 如果 CSV 里有就用, 没有就跳过 (validator 会从 products 表查)
        "volume_subtotal": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("unit_volume")),
                _to_float(row.get("quantity")),
                ndigits=2,
            ),
            "depends_on": ["unit_volume", "quantity"],
            "tolerance": 0.01,
            "description": "体积小计 = 单件体积 × 数量 精度0.01",
        },
    },

    # ============================================================
    # 销售合同明细 sales_contract_items
    # ============================================================
    "sales_contract_items": {
        # C3: 小计金额 = 数量 × 单价
        "subtotal": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("quantity")),
                _to_float(row.get("unit_price")),
                ndigits=2,
            ),
            "depends_on": ["quantity", "unit_price"],
            "tolerance": 0.01,
            "description": "合同明细小计 = 数量 × 单价",
        },
        # D1: 体积小计 = 单件体积 × 数量
        "volume_subtotal": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("unit_volume")),
                _to_float(row.get("quantity")),
                ndigits=2,
            ),
            "depends_on": ["unit_volume", "quantity"],
            "tolerance": 0.01,
            "description": "体积小计 = 单件体积 × 数量 精度0.01",
        },
    },

    # ============================================================
    # 发货单明细 delivery_order_items
    # ============================================================
    "delivery_order_items": {
        # D1: 体积小计 = 单件体积 × 数量
        "volume_subtotal": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("unit_volume")),
                _to_float(row.get("quantity")),
                ndigits=2,
            ),
            "depends_on": ["unit_volume", "quantity"],
            "tolerance": 0.01,
            "description": "体积小计 = 单件体积 × 数量 精度0.01",
        },
        # D2 [新增]: 短装数 = 计划 - 实际 (默认0, 未装柜时 actual 为空)
        "short_qty": {
            "expr": lambda row: (
                max(
                    0,
                    (_to_float(row.get("quantity")) or 0)
                    - (_to_float(row.get("actual_quantity")) or _to_float(row.get("quantity")) or 0),
                )
                if _to_float(row.get("quantity")) is not None
                else None
            ),
            "depends_on": ["quantity", "actual_quantity"],
            "tolerance": 0,
            "description": "短装数 = 计划 - 实际 (没填 actual_quantity 时为 0)",
        },
    },

    # ============================================================
    # [新增] 报关单明细 shipping_record_items
    # ============================================================
    "shipping_record_items": {
        # CI 小计 (USD) = 实际装柜数 × 单价
        "subtotal_usd": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("actual_qty")),
                _to_float(row.get("unit_price_usd")),
                ndigits=2,
            ),
            "depends_on": ["actual_qty", "unit_price_usd"],
            "tolerance": 0.01,
            "description": "CI 小计 (USD) = 实际装柜数 × 单价",
        },
    },

    # ============================================================
    # [新增] 报关单主表 shipping_records
    # 金额四件套: amount + currency + exchange_rate + amount_cny
    # ============================================================
    "shipping_records": {
        # 人民币金额 = 美元金额 × 汇率
        "total_amount_cny": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("total_amount")),
                _to_float(row.get("exchange_rate")),
                ndigits=2,
            ),
            "depends_on": ["total_amount", "exchange_rate"],
            "tolerance": 0.01,
            "description": "报关金额 (CNY) = 外币金额 × 当期汇率",
        },
    },

    # ============================================================
    # [新增] 贷记单 credit_notes (短装/差异单)
    # 金额四件套
    # ============================================================
    "credit_notes": {
        "diff_amount_cny": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("diff_amount")),
                _to_float(row.get("exchange_rate")),
                ndigits=2,
            ),
            "depends_on": ["diff_amount", "exchange_rate"],
            "tolerance": 0.01,
            "description": "差异金额 (CNY) = 外币差异 × 当期汇率",
        },
    },

    # ============================================================
    # [新增] 销售合同 sales_contracts
    # 金额四件套: total_amount (外币) + currency + exchange_rate + total_amount_cny
    # ============================================================
    "sales_contracts": {
        "total_amount_cny": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("total_amount")),
                _to_float(row.get("exchange_rate")),
                ndigits=2,
            ),
            "depends_on": ["total_amount", "exchange_rate"],
            "tolerance": 0.01,
            "description": "合同金额 (CNY) = 外币金额 × 当期汇率",
        },
    },

    # ============================================================
    # [新增] 应收收款 receipts (第7模块)
    # 金额四件套: amount + currency + exchange_rate + amount_cny
    # 业务场景: 财务确认到账后, 用 paid_date 查 exchange_rates 表的当期汇率,
    #          填入 exchange_rate, 然后本规则自动算 amount_cny = amount × rate
    # ============================================================
    "receipts": {
        "amount_cny": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("amount")),
                _to_float(row.get("exchange_rate")),
                ndigits=2,
            ),
            "depends_on": ["amount", "exchange_rate"],
            "tolerance": 0.01,
            "description": "收款人民币金额 = 外币到账金额 × 当期汇率",
        },
    },

    # ============================================================
    # [新增 R10] 报价明细 quotation_items
    # 业务背景: 报价定价 = 单卷重量(KG) × 报价系数(USD/KG)
    #   - weight_per_unit : 单卷重量 (从 products.weight 带出, 可覆盖)
    #   - price_coefficient : 报价系数 (USD/KG, 不同管径组用不同值)
    #   - quantity        : 数量 (卷数)
    #   - volume          : 单卷体积 m³ (复用 products.volume 公式)
    #
    # 注意: subtotal 不依赖派生的 unit_price, 而是直接展开成原始字段
    #       乘积 (weight_per_unit × price_coefficient × quantity)。
    #       原因: apply_derived_rules 是单轮遍历, 不做多轮依赖链计算,
    #       若 subtotal 依赖 unit_price 会在 unit_price 尚未加算前就跳过。
    # ============================================================
    "quotation_items": {
        # Q1: 总重 (KG) = 单卷重量 × 数量
        "total_weight": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("weight_per_unit")),
                _to_float(row.get("quantity")),
                ndigits=3,
            ),
            "depends_on": ["weight_per_unit", "quantity"],
            "tolerance": 0.001,
            "description": "总重(KG) = 单卷重量 × 数量",
        },
        # Q2: 单卷价 (USD) = 单卷重量 × 报价系数
        "unit_price": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("weight_per_unit")),
                _to_float(row.get("price_coefficient")),
                ndigits=2,
            ),
            "depends_on": ["weight_per_unit", "price_coefficient"],
            "tolerance": 0.01,
            "description": "单卷价(USD) = 单卷重量(KG) × 报价系数(USD/KG)",
        },
        # Q3: 小计 (USD) = 单卷重量 × 报价系数 × 数量
        # 直接展开成原始字段相乘, 不走派生 unit_price, 避免单轮依赖链问题
        "subtotal": {
            "expr": lambda row: (
                lambda wpu, coef, qty: None if None in (wpu, coef, qty) else round(wpu * coef * qty, 2)
            )(
                _to_float(row.get("weight_per_unit")),
                _to_float(row.get("price_coefficient")),
                _to_float(row.get("quantity")),
            ),
            "depends_on": ["weight_per_unit", "price_coefficient", "quantity"],
            "tolerance": 0.01,
            "description": "小计(USD) = 单卷重量 × 报价系数 × 数量 (直接公式, 不依赖派生 unit_price)",
        },
        # Q4: 总体积 (m³) = 单卷体积 × 数量
        "total_volume": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("volume")),
                _to_float(row.get("quantity")),
                ndigits=2,
            ),
            "depends_on": ["volume", "quantity"],
            "tolerance": 0.01,
            "description": "总体积(m³) = 单卷体积 × 数量 精度0.01",
        },
    },

    # ============================================================
    # [新增 R10] 报价主表 quotations
    # 金额四件套: total_amount (外币) + currency + exchange_rate + total_amount_cny
    # total_amount = Σ quotation_items.subtotal (在导入明细后由应用层汇总,
    #                不在本规则算; 本规则只负责外币→CNY 折算)
    # ============================================================
    "quotations": {
        "total_amount_cny": {
            "expr": lambda row: _safe_mul(
                _to_float(row.get("total_amount")),
                _to_float(row.get("exchange_rate")),
                ndigits=2,
            ),
            "depends_on": ["total_amount", "exchange_rate"],
            "tolerance": 0.01,
            "description": "报价金额(CNY) = 外币金额 × 当期汇率",
        },
    },
}


def _to_float(v):
    """把单元格安全转 float; 转不了返回 None"""
    if v is None or v == "":
        return None
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def _safe_add(a, b):
    """两个数都存在才加, 否则 None"""
    if a is None or b is None:
        return None
    return round(a + b, 2)


def _mul(a, n):
    if a is None or n is None:
        return None
    return a * n


def _safe_mul(a, b, ndigits=3):
    """两个数都存在才乘"""
    if a is None or b is None:
        return None
    return round(a * b, ndigits)


def _safe_div(a, b, ndigits=3):
    """两个数都存在且 b!=0 才除"""
    if a is None or b is None or b == 0:
        return None
    return round(a / b, ndigits)


# ============================================================
# 产品类型感知的密度与理论重量计算
#
# 业务背景 (来自客户):
#   所有重量都从密度出发算, 不要有两套公式。
#
#   统一公式链:
#     1) 密度 ρ           = DENSITY_RULES[产品大类](row)
#     2) 理论米重 (g/m)   = (内径+厚度) × 厚度 × 3.14 × ρ
#     3) 理论单件重量(kg) = 理论米重 × 长度 / 1000
#
#   单位约定: 内径/厚度 mm, 长度 m, 重量 kg, 米重 g/m
#
# 产品大类密度规则 (2026-08-01 老板确认, 详见 BUSINESS_RULES.md R4):
#   线管    : ρ = 1.35 (固定)
#   水带    : ρ = 1.35 (固定, 与线管相同)
#   钢丝管  : ρ = 内径 × 0.003 + 1.46
#   复合管  : ρ = 内径 × 0.003 + 1.46 (与钢丝管相同)
#   塑筋管  : (TODO 待客户补充)
#
# products.product_category 存的是客户原始类别 (70+ 种, 如"无味钢丝管"/
# "钩编管"/"白复合防静电"), 先经 CATEGORY_ALIASES 映射成 4 个大类再查密度。
# 映射不到的原始类别: 按名称关键词兜底 (含"钢丝"->钢丝管, 含"复合"->复合管,
# 含"水带"->水带), 仍判不了返回 None (跳过校验)。
#
# 容差: 客户通常会"上下稍微浮动"确定最终重量, 5% 内算正常
# ============================================================

# 原始产品类别 -> 产品大类 别名表 (2026-08-01 真实主数据 70 个类别全量梳理)
CATEGORY_ALIASES = {
    # ---- 钢丝管大类 ----
    "钢丝管": "钢丝管",
    "无味钢丝管": "钢丝管",
    "耐高温钢丝管": "钢丝管",
    "防静电钢丝管": "钢丝管",
    # ---- 复合管大类 (老板: 复合管按钢丝管公式算) ----
    "钢丝复合管": "复合管",
    "白复合防静电": "复合管",
    "绿色复合耐低温防静电": "复合管",
    # ---- 水带大类 (老板: 水带密度与线管相同 = 1.35) ----
    "水带": "水带",
    "蓝色水带": "水带",
    "红色水带": "水带",
    "绿色水带": "水带",
    "橙色水带": "水带",
    "蓝龙水带（永利5号）": "水带",
    # ---- 线管大类 (老板: 其余类别密度都与线管相同 = 1.35) ----
    "线管": "线管",
    "无味线管": "线管",
    "流体管": "线管",
    "钩编管": "线管",
    "浩丝管": "线管",
    "合股双编": "线管",
    "双合股线": "线管",
    "双编合股线管": "线管",
    "双合股中压管": "线管",
    "三胶两线管": "线管",
    "三胶两线 氧气乙炔管": "线管",
    "三胶两线 红蓝双连氧气管": "线管",
    "三胶一线": "线管",
    "三胶一线蓝龙": "线管",
    "三胶一线花园管内胶白（不透明）中黑外绿": "线管",
    "三胶一线柠檬黄三维花园管内胶白色（不透明）中黑无味外柠檬黄": "线管",
    "三胶一线海之蓝三维花园管内胶白（不透明）中黑无味外海之蓝": "线管",
    "两胶一线": "线管",
    "黄色两胶一线": "线管",
    "黑色两胶一线": "线管",
    "黑四胶两线 胶管": "线管",
    "四胶两线": "线管",
    "黄四胶两线": "线管",
    "红四胶两线": "线管",
    "四胶两线 浩丝管": "线管",
    "四胶三线 胶管": "线管",
    "黄色三胶一线 花线管": "线管",
    "蓝色三胶一线 花线管": "线管",
    # 2026-08-11 产品数据全量核实补录 (原始数据双空格变体, 老板确认归线管 1.35)
    "黄色三胶一线  花线管": "线管",
    "牛筋管  磨沙流体管 淡蓝色": "线管",
    "内白外黄三胶一线  邢培栩": "线管",
    "工程管": "线管",
    "工程管内瓷白中黑（黑无味）外透明三胶双编": "线管",
    "黑园林工程高压专用管": "线管",
    "蓝龙工业管": "线管",
    "蓝龙管": "线管",
    "黄金管": "线管",
    "黄花园管": "线管",
    "蓝花园管": "线管",
    "黑双编花园管": "线管",
    "日式线管": "线管",
    "日式合股双编": "线管",
    "黑两胶一线 合股双编": "线管",
    "绿色牛筋防寒管": "线管",
    "磨沙牛筋管": "线管",
    "牛筋管 磨沙流体管 淡蓝色": "线管",
    "黄流体": "线管",
    "硅胶软管": "线管",
    "乳胶管": "线管",
    "原子管": "线管",
    "喷雾管": "线管",
    "水平管": "线管",
    "黑色煤气管": "线管",
    "仿广东管": "线管",
    "桔红": "线管",
    "P5黄色合股双编网线管": "线管",
    "p8海蓝合股单编": "线管",
    "内白外黄三胶一线 邢培栩": "线管",
    "外兰内磁白双编管（原蓝龙线管颜色）": "线管",
}

# 密度公式表: 每个产品大类 -> 一个 lambda, 输入 row, 输出密度
_DENSITY_GANGSI = lambda row: (
    lambda id_: round(id_ * 0.003 + 1.46, 4) if id_ is not None else None
)(_to_float(row.get("inner_diameter")))

DENSITY_RULES = {
    "线管": lambda row: 1.35,
    "水带": lambda row: 1.35,  # 2026-08-01 老板确认: 与线管相同
    "钢丝管": _DENSITY_GANGSI,
    "复合管": _DENSITY_GANGSI,  # 2026-08-01 新增大类: 与钢丝管相同
    # 塑筋管 等待客户补充, 暂时返回 None (无法计算, 跳过校验)
    "塑筋管": lambda row: None,
}


def _parse_nominal_inch(inch_str):
    """解析标称英寸 ('1-1/4"', '1/4"', '2"') 为浮点; 失败返回 None"""
    s = (inch_str or "").strip().rstrip('"').strip()
    if not s:
        return None
    try:
        if "-" in s:  # 带分数: 1-1/4
            whole, frac = s.split("-", 1)
            num, den = frac.split("/")
            return int(whole) + int(num) / int(den)
        if "/" in s:  # 纯分数: 1/4
            num, den = s.split("/")
            return int(num) / int(den)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


def classify_id_size(inch_str, inner_mm=None):
    """物料内径大小分类 (老板 2026-08-11 口径, 按标称英寸判):
      <1"        → 小内径
      1" ~ <3"   → 中内径
      3" 起      → 大内径 (内径 ≥170mm → 超大内径)
    判不了返回 None。注意 23.8mm 这种 1" 标称实际不足 25.4mm, 必须按标称英寸判, 不能按 mm。
    """
    inch = _parse_nominal_inch(inch_str)
    if inch is None:
        return None
    if inch < 1:
        return "小内径"
    if inch < 3:
        return "中内径"
    if inner_mm is not None and inner_mm >= 170:
        return "超大内径"
    return "大内径"


def resolve_category_group(raw_category):
    """
    把客户原始产品类别映射成产品大类 (钢丝管/线管/复合管/水带)。
    先查全量别名表, 再按名称关键词兜底, 都判不了返回 None。
    """
    cat = (raw_category or "").strip()
    if not cat:
        return None
    if cat in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cat]
    # 2026-08-11: 内部连续空格归一成单空格再查一次
    # (原始数据有 "黄色三胶一线  花线管" 这类双空格变体, 曾致 102 行漏映射)
    cat_norm = " ".join(cat.split())
    if cat_norm != cat and cat_norm in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cat_norm]
    if cat in DENSITY_RULES:  # 直接就是大类名 (或塑筋管)
        return cat
    if "钢丝" in cat:
        return "钢丝管"
    if "复合" in cat:
        return "复合管"
    if "水带" in cat:
        return "水带"
    return None


def calc_density(row):
    """
    根据产品类别 (product_category 字段) 返回密度。
    原始类别先经 resolve_category_group 映射成大类再查公式。
    未知类型或信息不全返回 None。
    """
    group = resolve_category_group(row.get("product_category"))
    if group is None:
        return None
    fn = DENSITY_RULES.get(group)
    if fn is None:
        return None
    return fn(row)


def calc_theoretical_weight_per_meter(row):
    """
    理论米重 (g/m) = (内径 + 厚度) × 厚度 × 3.14 × 密度

    内径/厚度: mm
    密度: 由 calc_density 根据 product_category 决定
    """
    inner = _to_float(row.get("inner_diameter"))
    thick = _to_float(row.get("thickness"))
    density = calc_density(row)

    if None in (inner, thick, density):
        return None

    wpm = (inner + thick) * thick * 3.14 * density
    return round(wpm, 3)


def calc_theoretical_weight(row):
    """
    理论单件重量 (kg) = 理论米重 (g/m) × 长度 (m) / 1000

    长度: m
    """
    wpm = calc_theoretical_weight_per_meter(row)
    length = _to_float(row.get("length"))
    if wpm is None or length is None:
        return None
    return round(wpm * length / 1000, 3)


def calc_theoretical_thickness(row):
    """
    反推厚度 (mm)。按可靠性优先级走 3 条路径, 任一成功即返回:

    路径 A (最可靠, 几何反推):
        已知 内径 + 外径, 直接算:
            厚度 = (外径 - 内径) / 2
        优点: 纯几何关系, 不依赖密度, 跟产品类别无关, 100% 精确

    路径 B (密度方程反推, 从米重):
        已知 内径 + 米重 + 密度, 解一元二次方程 (见下方推导)

    路径 C (密度方程反推, 从单重+长度):
        已知 内径 + 单重 + 长度 + 密度, 先算米重 = 单重 × 1000 / 长度, 再走路径 B

    ----------------------------------------------------------
    密度方程推导 (路径 B/C):
        米重 = (内径 + 厚度) × 厚度 × 3.14 × 密度
        设 t = 厚度, k = 密度 × 3.14
        k·t² + k·内径·t - 米重 = 0
        t = [-k·内径 + √((k·内径)² + 4·k·米重)] / (2·k)
    """
    inner = _to_float(row.get("inner_diameter"))
    if inner is None:
        return None

    # ---- 路径 A: 从外径几何反推 (优先, 最可靠) ----
    outer = _to_float(row.get("outer_diameter"))
    if outer is not None and outer > inner:
        return round((outer - inner) / 2, 2)

    # ---- 路径 B/C: 密度方程反推 ----
    density = calc_density(row)
    if density is None or density <= 0:
        return None

    # 米重优先用 weight_per_meter; 没有就从 weight × 1000 / length 反推
    wpm = _to_float(row.get("weight_per_meter"))
    if wpm is None:
        w = _to_float(row.get("weight"))
        length = _to_float(row.get("length"))
        if w is not None and length is not None and length > 0:
            wpm = w * 1000 / length

    if wpm is None or wpm <= 0:
        return None

    k = density * 3.14
    b = k * inner
    discriminant = b * b + 4 * k * wpm
    sqrt_disc = math.sqrt(discriminant)
    t = (-b + sqrt_disc) / (2 * k)
    return round(t, 2)


def _format_id_od(inner, outer):
    inner_v = _to_float(inner)
    outer_v = _to_float(outer)
    if inner_v is None or outer_v is None:
        return None
    # 整数就去掉小数点, 否则保留 2 位
    inner_s = f"{int(inner_v)}" if inner_v.is_integer() else f"{inner_v:g}"
    outer_s = f"{int(outer_v)}" if outer_v.is_integer() else f"{outer_v:g}"
    return f"{inner_s}x{outer_s}"


def _build_spec(row):
    """根据 inch + 内径 + 标称米数 拼接 spec 字符串.

    格式: {英寸} ID{内径mm} -{标称米数}M [(短|中|长)]
    短/中/长 规则 (按 spec_meter):
        <= 20  -> 短
        21-45  -> 中
        46-99  -> 长
        >= 100 -> 无标签 (大卷默认)
    任何关键字段缺失时返回 None (让 CSV 原值生效).
    """
    inch = (row.get("inner_diameter_inch") or "").strip()
    inner_v = _to_float(row.get("inner_diameter"))
    meter_v = _to_float(row.get("spec_meter"))
    if not inch or inner_v is None:
        return None
    # 内径整数化: 6.5 -> "6.5", 8 -> "8"
    inner_s = f"{int(inner_v)}" if inner_v.is_integer() else f"{inner_v:g}"
    parts = [f'{inch} ID{inner_s}']
    if meter_v is not None:
        meter_i = int(meter_v)
        parts.append(f'-{meter_i}M')
        # 短/中/长 标签
        if meter_i <= 20:
            parts.append('(短)')
        elif meter_i <= 45:
            parts.append('(中)')
        elif meter_i < 100:
            parts.append('(长)')
        # >= 100: 无标签
    return ' '.join(parts)


def sql_escape(value):
    """
    把字符串安全转义成 SQL 字面量 (防注入 + 防语法错误)。

    处理:
      - 单引号 -> ''         (SQL 标准转义)
      - 反斜杠 \\ -> \\\\    (MySQL 默认开启 NO_BACKSLASH_ESCAPES 时也需要)
      - 换行 \\n -> \\n      (否则多行文本在 MySQL 里会报错)
      - 回车 \\r -> \\r
      - tab \\t -> \\t
      - NULL -> NULL (无引号)

    这样 customers/suppliers 的 company_profiles 这种"多行大文本"字段
    能被正确 INSERT 到数据库, 合同模板调取时再被还原成原始多行文本。
    """
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        # 数值不引号
        return str(value)
    s = str(value)
    # 顺序很重要: 先转义反斜杠本身, 再转义其它字符
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "''")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")
    return f"'{s}'"


def apply_derived_rules(table, row, row_index=None, report=None):
    """
    对一行数据应用派生规则。两件事一起做:

    1. 加算 (补列): 如果 CSV 里没有某派生列, 或值为空,
       按公式计算后填进去 (并把它加进 row, 让后续 INSERT 也带上)

    2. 反向校验: 如果 CSV 里手填了派生列的值, 跟公式算出来的对比,
       差距超过容差 -> 记录到 report 里, 让用户核对是公式错还是数据错

    参数:
      row        : 当前行的字典
      row_index  : 行号 (用于报错定位, 从 1 开始数数据行)
      report     : 列表 [(level, msg), ...], 传 None 不做记录
    """
    rules = DERIVED_RULES.get(table, {})
    for field, rule in rules.items():
        expr = rule["expr"]
        tolerance = rule.get("tolerance")

        # 判断依赖齐不齐, 支持两种写法:
        #   depends_on       : 列表, 全部都得有 (AND 关系)
        #   depends_on_any   : 列表的列表, 任一子列表全有即可 (OR 关系)
        #                     用于"米重 OR (单重+长度)" 这种多路径反推
        # 注意: depends_on 里既可能有数值字段, 也可能有字符串字段 (如 product_category)
        #       所以判断"有没有"用 _has_value, 而不是 _to_float
        deps_and = rule.get("depends_on", [])
        deps_any = rule.get("depends_on_any")

        def _has_value(key):
            v = row.get(key)
            return v is not None and v != ""

        if deps_any:
            # 任一组齐即可
            can_compute = any(
                all(_has_value(d) for d in group)
                for group in deps_any
            )
            # 但 depends_on 里的"必要字段"也必须齐 (如 product_category)
            if can_compute and deps_and:
                can_compute = all(_has_value(d) for d in deps_and)
        else:
            can_compute = all(_has_value(d) for d in deps_and)

        current = row.get(field)

        if current is None or current == "":
            # 加算: 没填 -> 算出来填进去
            if can_compute:
                new_value = expr(row)
                if new_value is not None:
                    row[field] = new_value
                    if report is not None and row_index is not None:
                        report.append(
                            ("info", f"[{table} 第 {row_index} 行] 自动计算 {field} = {new_value}")
                        )
        else:
            # 反向校验: 填了, 但对不对?
            if not can_compute:
                continue
            expected = expr(row)
            if expected is None:
                continue

            current_num = _to_float(current)
            if current_num is None:
                # 字符串字段 (如 id_x_od), 跳过数值校验
                continue

            if tolerance is None:
                continue

            # 计算容差: 支持绝对值 (absolute) 和百分比 (percent) 两种模式
            mode = rule.get("tolerance_mode", "absolute")
            if mode == "percent":
                # 百分比容差: 允许的差值 = 理论值 × 百分比
                allowed_diff = abs(expected) * tolerance
                diff_desc = f"{tolerance*100:.1f}% (≈{round(allowed_diff, 3)})"
            else:
                # 绝对值容差: 直接用数值
                allowed_diff = tolerance
                diff_desc = str(tolerance)

            diff = abs(current_num - expected)
            if diff > allowed_diff:
                # 公式值跟手填值对不上。默认 error 阻止生成;
                # 规则声明 mismatch_level="warn" 时降级为提醒 (如 products 真实主数据,
                # 客户手填值与密度公式超差时约定保留客户值, 偏差提示写入 remark)
                level = rule.get("mismatch_level", "error")
                loc = f"[{table} 第 {row_index} 行]" if row_index else f"[{table}]"
                pct = round(diff / abs(expected) * 100, 2) if expected else "N/A"
                report.append(
                    (level,
                     f"{loc} 字段 {field} 手填值 {current_num} "
                     f"与公式计算值 {expected} 相差 {round(diff, 3)} ({pct}%) "
                     f"(超过容差 {diff_desc}), 请核对公式或数据")
                )
    return row


def ensure_derived_columns(table, fields):
    """
    根据派生规则, 把缺的列名补到 fields 里 (按表结构的字段顺序追加)。
    这一步让"CSV 里没 outer_diameter 列" 也能自动补上该列。
    """
    rules = DERIVED_RULES.get(table, {})
    existing = set(fields)
    for field in rules.keys():
        if field not in existing:
            fields.append(field)
    return fields


# ============================================================
# 跨字段校验 (cross-field checks)
#
# 跟 apply_derived_rules 的区别:
#   - apply_derived_rules 是单字段校验 (一个字段 vs 一个公式)
#   - cross-field 是两个字段互相之间是否自洽
#
# 用 warn 级别, 不阻止生成 SQL (业务允许客户值跟公式差 5%)
# ============================================================
CROSS_FIELD_TOLERANCE = 0.05  # 5%


def check_cross_field_consistency(table, row, row_index=None, report=None):
    """
    跨字段一致性校验 (warn 级别, 不阻止生成)。

    products 表:
      米重 × 长度 / 1000 vs 单件重量, 偏差 > 5% -> warn

    业务背景:
      客户可以"上下浮动"确定米重或单重, 各自跟密度公式 5% 内都算正常,
      但两者互相反推差距过大说明数据可能有问题, 给个提醒。
    """
    if report is None:
        return

    if table == "products":
        wpm = _to_float(row.get("weight_per_meter"))
        length = _to_float(row.get("length"))
        weight = _to_float(row.get("weight"))

        if None in (wpm, length, weight) or length <= 0:
            return

        weight_from_wpm = wpm * length / 1000
        if weight_from_wpm <= 0:
            return
        diff_pct = abs(weight_from_wpm - weight) / weight_from_wpm
        if diff_pct > CROSS_FIELD_TOLERANCE:
            loc = f"[products 第 {row_index} 行]" if row_index else "[products]"
            material_id = row.get("material_id", "?")
            report.append(
                ("warn",
                 f"{loc} 物料 {material_id}: 米重×长度/1000 = {round(weight_from_wpm, 3)} kg, "
                 f"但单重填的是 {weight} kg, 偏差 {round(diff_pct*100, 1)}% (超 5%)。"
                 f"提示: 两者互相反推对不上, 请核对")
            )


def convert_csv_to_sql(csv_path, table_name, output_sql_path, mode="insert"):
    """
    核心转换函数。
    mode:
      - "insert"  : 用 INSERT VALUES  (MySQL/SQLite 通用)
      - "replace" : 用 REPLACE VALUES (有主键/唯一冲突时覆盖, 适合重跑)

    行为说明:
      - 自动加算: 缺 outer_diameter 等派生列时, 按公式补上
      - 反向校验: 手填值跟公式对不上时报错, 阻止生成错误 SQL
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV 不存在: {csv_path}")

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        # utf-8-sig: 自动吃掉 Excel 另存时可能加的 BOM
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    # 把派生规则需要的列补进 fields (CSV 缺哪列就补哪列)
    fields = ensure_derived_columns(table_name, fields)

    # 跳过 MySQL GENERATED ALWAYS AS 列: 这种列由数据库自己算, INSERT 写值会报
    # ERROR 3105: The value specified for generated column is not allowed
    # 目前唯一一处: delivery_order_items.short_qty (见 sql/01_schema.sql)
    GENERATED_COLUMNS = {
        "delivery_order_items": {"short_qty"},
    }
    skip_cols = GENERATED_COLUMNS.get(table_name, set())
    if skip_cols:
        fields = [f for f in fields if f not in skip_cols]

    keyword = "REPLACE" if mode == "replace" else "INSERT"

    lines = []
    lines.append(f"-- ============================================================")
    lines.append(f"-- 由 tools/csv_to_sql.py 自动生成")
    lines.append(f"-- 源 CSV : {csv_path}")
    lines.append(f"-- 目标表 : {table_name}")
    lines.append(f"-- 行数   : {len(rows)}")
    lines.append(f"-- 派生列 : {list(DERIVED_RULES.get(table_name, {}).keys())}")
    lines.append(f"-- 请勿手工编辑本文件, 改了源 CSV 后重新生成即可")
    lines.append(f"-- ============================================================")
    lines.append("")
    lines.append(f"USE inventory_db;")
    lines.append("")

    # 收集加算/校验信息
    report = []

    for idx, row in enumerate(rows, start=1):
        # 应用派生规则 (加算 + 反向校验)
        row = apply_derived_rules(table_name, row, row_index=idx, report=report)
        # 跨字段一致性校验 (warn 级别, 不阻止生成)
        check_cross_field_consistency(table_name, row, row_index=idx, report=report)
        # 取出本行非空字段, 空值 -> NULL
        cols = []
        vals = []
        for field in fields:
            raw = row.get(field)
            if raw is None or raw == "":
                # 数值类型空值用 NULL, 字符串类型如果带默认值也用 NULL
                cols.append(f"`{field}`")
                vals.append("NULL")
            else:
                # 尝试转数值
                num = _to_float(raw)
                if num is not None and _looks_like_number(raw):
                    cols.append(f"`{field}`")
                    vals.append(str(num))
                else:
                    cols.append(f"`{field}`")
                    vals.append(sql_escape(raw))

        if not cols:
            continue

        cols_sql = ", ".join(cols)
        vals_sql = ", ".join(vals)
        lines.append(f"{keyword} INTO `{table_name}` ({cols_sql}) VALUES ({vals_sql});")

    # 打印报告
    info_count = sum(1 for lvl, _ in report if lvl == "info")
    warn_count = sum(1 for lvl, _ in report if lvl == "warn")
    error_count = sum(1 for lvl, _ in report if lvl == "error")
    if report:
        print(f"\n[派生列处理报告] 表 {table_name}:")
        for lvl, msg in report:
            if lvl == "info":
                prefix = "[INFO] "
            elif lvl == "warn":
                prefix = "[WARN] "
            else:
                prefix = "[ERROR]"
            print(f"  {prefix} {msg}")
    if warn_count > 0:
        print(f"\n[跨字段提醒] 发现 {warn_count} 处米重/单重互相反推对不上 (仅供参考, 不阻止生成)")
    if error_count > 0:
        print(f"\n[阻止生成] 发现 {error_count} 处反向校验失败, 已停止写入 SQL 文件。")
        print(f"           请修正源 CSV 或检查公式, 然后重跑。")
        return 0

    os.makedirs(os.path.dirname(output_sql_path), exist_ok=True)
    with open(output_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if info_count > 0:
        print(f"[INFO] 已自动加算 {info_count} 个派生字段值")

    return len(rows)


def _looks_like_number(s):
    """判断字符串是不是数值 (避免把电话号码/银行账号当数字处理)

    2026-07-30 修复: 之前纯数字字符串(如电话号 081297100933、银行账号
    6220000015815815) 会被 float() 成功转换, 然后通过 str(num) 输出
    '81297100933.0' 灌进 MySQL, phone/bank_account 这种本质是字符串的
    字段被破坏。

    新规则: 只在"看起来是计量数值"时才返回 True:
      - 含小数点 (3.14, 0.93)
      - 或 纯整数且长度 ≤ 10 (id/quantity 这种)
    长度 > 10 的纯数字串一定是 phone/account/code, 不当数字处理。
    """
    s = str(s).strip()
    if s == "":
        return False
    # 带字母/中文/分隔符的不算数值 (比如 '1-1/4"' 这种规格)
    if any(c in s for c in ["-", "/", '"', "'", "(", ")", "x", "Ｘ"]):
        return False
    # 长度超过 10 的纯数字串一定是电话号/银行账号/单号, 不当数字处理
    # (FLOAT 精度上限本来也只到 15-16 位有效数字, 16 位银行账号会被四舍五入)
    if len(s) > 10 and "." not in s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="把 CSV 转成数据库 INSERT 语句"
    )
    parser.add_argument("csv_path", help="输入 CSV 路径")
    parser.add_argument("table_name", help="目标表名 (如 products)")
    parser.add_argument("output_sql_path", help="输出 SQL 文件路径")
    parser.add_argument(
        "--mode",
        choices=["insert", "replace"],
        default="insert",
        help="insert=新增; replace=主键冲突时覆盖(适合反复重跑)",
    )
    args = parser.parse_args()

    n = convert_csv_to_sql(
        args.csv_path, args.table_name, args.output_sql_path, args.mode
    )
    if n > 0:
        print(f"[OK] {args.csv_path} -> {args.output_sql_path}  ({n} 行)")
    elif n == 0 and os.path.exists(args.output_sql_path):
        # 空表: 没数据行, 但 SQL 文件已正常生成 (只有 USE 等头注释)
        print(f"[OK] {args.csv_path} -> {args.output_sql_path}  (空表, 仅生成文件头)")
    else:
        # n == 0 且没生成文件 = 反向校验失败, 已在上游打印了详细错误
        sys.exit(1)


if __name__ == "__main__":
    main()
