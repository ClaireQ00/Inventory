#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
克隆建物料 (半自动) · clone_material.py
========================================

业务场景 (2026-08-01 与老板确认, 见 BUSINESS_RULES.md R10 快照重量分阶段规则):
  formal/converted 阶段报价快照重量偏离主数据 >5% 时, 校验会 WARN 提示"归位":
  谈成新重量 = 新规格, 应该【新增物料】。本脚本把新增物料的机械部分自动化:

    人做决策: 新编码、新重量/长度等谈判达成值
    机器干杂活: 克隆源物料整行 → 换编码 → 覆盖谈判值 → 受影响派生列置空
                (导入时由 csv_to_sql.py 按 DERIVED_RULES 自动重算) → 溯源备注

用法:
  # 只克隆物料 (最常见: 同规格谈了新重量)
  python3 tools/clone_material.py M-Q025-003 M-Q025-013 --weight 17

  # 长度也变 (外观尺寸需实测, 会置空提醒补录)
  python3 tools/clone_material.py M-Q025-003 M-Q025-013 --weight 17 --length 50

  # 同时把某张报价单里的物料编码换成新编码
  python3 tools/clone_material.py M-Q025-003 M-Q025-013 --weight 17 \\
      --update-quote YL260728Q025

  # 覆盖任意其他列 (如喷码/包装)
  python3 tools/clone_material.py M-Q025-003 M-Q025-013 --weight 17 \\
      --set spray_code="新喷码内容"

完成后按提示跑: bash scripts/run_local_validation.sh

⚠️ 设计约定 (给未来的前端按钮):
  核心逻辑在 clone_material() 函数里, 返回结构化 dict, 不打印、不退出。
  CLI (main()) 只是薄壳。将来做前端界面时, 按钮后端直接 import 调用:

      from clone_material import clone_material
      result = clone_material("data/csv/products.csv", src, dst, {"weight": 17})

  不要把业务逻辑搬进 main(), 否则前端接进来时还得重写一遍。
"""

import argparse
import csv
import os
import sys
from datetime import date

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# products 表的派生列 (跟 tools/csv_to_sql.py::DERIVED_RULES["products"] 对齐)
# 这些列在"影响它的输入被覆盖"时置空, 导入时由 DERIVED_RULES 自动重算
GEO_DERIVED = ["outer_diameter", "id_x_od", "weight_per_meter", "spec"]  # 内径/厚度变了要重算
SPEC_DERIVED = ["spec"]                                                   # 长度变了规格描述要重算
APPEARANCE_FIELDS = ["appearance_inner", "appearance_outer", "appearance_height", "volume"]


def _find_row(rows, material_id):
    for i, r in enumerate(rows):
        if r.get("material_id") == material_id:
            return i
    return None


def clone_material(products_csv, source_id, new_id, overrides=None,
                   quotation_csv=None, quote_no=None):
    """克隆物料主数据一行, 应用覆盖字段, 追加到 products_csv。

    参数:
        products_csv:   products.csv 路径 (真实数据, 通常在 data/csv/)
        source_id:      源物料编码 (克隆模板)
        new_id:         新物料编码 (必须不存在)
        overrides:      {列名: 新值} 谈判达成值, 如 {"weight": 17, "length": 50}
        quotation_csv:  (可选) quotation_items.csv 路径, 配合 quote_no 换编码
        quote_no:       (可选) 该报价单里 material_id==source_id 的行改成 new_id

    返回:
        {
          "new_row": dict,          # 新物料整行 (已写入 products_csv)
          "blanked": [列名...],      # 被置空待重算的列 (导入时 DERIVED_RULES 自动算)
          "reminders": [str...],     # 需要人工补录的提醒 (如外观尺寸实测)
          "quote_rows_updated": int, # 报价单里换了编码的行数 (0 = 没动报价)
        }

    只改 CSV, 不碰数据库; 调用方随后跑 run_local_validation.sh 完成校验导入。
    """
    overrides = dict(overrides or {})
    if not os.path.exists(products_csv):
        raise FileNotFoundError(f"products.csv 不存在: {products_csv}")
    if source_id == new_id:
        raise ValueError("新编码不能跟源编码相同")

    with open(products_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)

    src_idx = _find_row(rows, source_id)
    if src_idx is None:
        raise ValueError(f"源物料不存在: {source_id}")
    if _find_row(rows, new_id) is not None:
        raise ValueError(f"新编码已存在: {new_id} (换个编码, 或先停用旧行)")

    # 覆盖字段合法性: 只允许 products 表已有的列
    unknown = [c for c in overrides if c not in header]
    if unknown:
        raise ValueError(f"未知列名: {unknown} (products 表没有这些列)")
    if "material_id" in overrides:
        raise ValueError("material_id 由参数 new_id 决定, 不要放进 overrides")

    # ---- 1. 克隆 + 换编码 + 应用覆盖 ----
    new_row = dict(rows[src_idx])
    new_row["material_id"] = new_id
    for col, val in overrides.items():
        new_row[col] = str(val)

    # ---- 2. 受影响派生列置空 (导入时由 DERIVED_RULES 重算, 避免带上旧规格的旧值) ----
    blanked = []

    def _blank(cols):
        for c in cols:
            if c in header and new_row.get(c) and c not in overrides and c not in blanked:
                new_row[c] = ""
                blanked.append(c)

    geo_changed = "inner_diameter" in overrides or "thickness" in overrides
    length_changed = "length" in overrides
    weight_changed = "weight" in overrides

    if geo_changed:
        _blank(GEO_DERIVED + ["weight"])          # 几何变了, 外径/串/米重/单重全部重算
        if "spec_meter" in header:
            _blank(["spec_meter"])
    if length_changed:
        _blank(SPEC_DERIVED + ["weight"])         # 长度变了, 规格描述/单重重算
        if "spec_meter" in header:
            # spec_meter = 长度四舍五入取整 (跟 gen_products_from_excel.py 同规则)
            try:
                new_row["spec_meter"] = str(round(float(overrides["length"])))
            except (TypeError, ValueError):
                _blank(["spec_meter"])
        _blank(APPEARANCE_FIELDS)                  # 长度变了外观尺寸必然变, 需实测
        _blank(["meter_mark_count"])               # 米标个数跟长度相关
    if weight_changed and not geo_changed and not length_changed:
        pass                                       # 最常见场景: 同规格只谈新重量, 无需重算

    # ---- 3. 溯源备注 ----
    if "remark" not in overrides:
        origin = f"克隆自 {source_id} ({date.today().isoformat()}, 快照归位新增)"
        new_row["remark"] = (new_row.get("remark", "") + " | " + origin).strip(" |")

    # ---- 4. 追加写入 products.csv ----
    rows.append(new_row)
    with open(products_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    # ---- 5. 提醒清单 ----
    reminders = []
    if length_changed:
        reminders.append(
            "长度变更: 外观尺寸(appearance_*)和体积已置空, 请实测后补录 "
            "(不补也能导入, 体积会缺, 影响装箱/体积校验)"
        )
    if blanked:
        reminders.append(
            f"已置空待重算: {', '.join(blanked)} (跑 run_local_validation.sh 时自动算)"
        )

    # ---- 6. (可选) 报价单换编码 ----
    quote_rows_updated = 0
    if quotation_csv and quote_no:
        if not os.path.exists(quotation_csv):
            raise FileNotFoundError(f"quotation_items.csv 不存在: {quotation_csv}")
        with open(quotation_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            q_header = reader.fieldnames
            q_rows = list(reader)
        for r in q_rows:
            if r.get("quote_no") == quote_no and r.get("material_id") == source_id:
                r["material_id"] = new_id
                quote_rows_updated += 1
        if quote_rows_updated:
            with open(quotation_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=q_header)
                writer.writeheader()
                writer.writerows(q_rows)

    return {
        "new_row": new_row,
        "blanked": blanked,
        "reminders": reminders,
        "quote_rows_updated": quote_rows_updated,
    }


def main():
    ap = argparse.ArgumentParser(
        description="克隆建物料: 复制源物料行 → 换编码 → 覆盖谈判达成值 → 派生列待重算",
        epilog="完成后请跑: bash scripts/run_local_validation.sh",
    )
    ap.add_argument("source_id", help="源物料编码 (克隆模板), 如 M-Q025-003")
    ap.add_argument("new_id", help="新物料编码 (必须不存在), 如 M-Q025-013")
    ap.add_argument("--weight", type=float, help="谈判达成的新单件重量 (KG)")
    ap.add_argument("--length", type=float, help="新长度 (M); 变了会置空外观尺寸提醒实测")
    ap.add_argument("--thickness", type=float, help="新厚度 (mm)")
    ap.add_argument("--inner-diameter", type=float, help="新内径 (mm)")
    ap.add_argument("--weight-per-meter", type=float, help="新米重 (g/m)")
    ap.add_argument("--remark", help="自定义备注 (默认自动生成溯源备注)")
    ap.add_argument("--set", dest="sets", action="append", default=[],
                    metavar="列=值", help="覆盖任意其他列, 可多次使用")
    ap.add_argument("--update-quote", metavar="报价单号",
                    help="把该报价单里源物料的行换成新编码")
    ap.add_argument("--products-csv", default=os.path.join(ROOT_DIR, "data", "csv", "products.csv"))
    ap.add_argument("--quotation-csv", default=os.path.join(ROOT_DIR, "data", "csv", "quotation_items.csv"))
    args = ap.parse_args()

    # 组装 overrides
    overrides = {}
    for col, val in [("weight", args.weight), ("length", args.length),
                     ("thickness", args.thickness), ("inner_diameter", args.inner_diameter),
                     ("weight_per_meter", args.weight_per_meter), ("remark", args.remark)]:
        if val is not None:
            overrides[col] = val
    for item in args.sets:
        if "=" not in item:
            ap.error(f"--set 格式应为 列=值, 收到: {item}")
        col, val = item.split("=", 1)
        overrides[col.strip()] = val.strip()

    try:
        result = clone_material(
            args.products_csv, args.source_id, args.new_id, overrides,
            quotation_csv=args.quotation_csv if args.update_quote else None,
            quote_no=args.update_quote,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    r = result["new_row"]
    print(f"[OK] 新物料已建: {r['material_id']} (克隆自 {args.source_id})")
    if overrides:
        print(f"     覆盖值: {overrides}")
    for msg in result["reminders"]:
        print(f"     ⚠ {msg}")
    if result["quote_rows_updated"]:
        print(f"     报价单 {args.update_quote}: {result['quote_rows_updated']} 行已换成新编码")
    print()
    print("下一步: bash scripts/run_local_validation.sh  (校验 + 重算派生列)")


if __name__ == "__main__":
    main()
