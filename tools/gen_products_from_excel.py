#!/usr/bin/env python3
# ============================================================
# 一次性迁移脚本: 产品数据.xlsx -> data/csv/products.csv
#
# 背景 (2026-08-01 与老板逐条确认):
#   - Excel 第 1 行是英文子表头, 跳过; 真实数据 14338 行
#   - material_id: 从 M-10001 起编顺序号, Excel 原始 ID 写进 remark 溯源
#   - 保留现有 12 行 M-Q025 数据 (被 8 张业务表引用), 新数据追加在后
#   - 米重: Excel 单位 kg/m -> products 表 g/m, 乘 1000
#   - 米重/重量区间值 (如 "180-185") 取中值, 原值写进 remark
#   - 内径英寸: 按 mm/25.4 就近换算到 1/16 精度 (分母 2/4/8/16)
#   - spec_meter = 长度四舍五入取整; length = 原值
#   - 虚重为 "0" 的行当空处理
#   - 壁厚缺失的行: 按密度公式反推 (线管/水带=1.35, 钢丝管/复合管=内径*0.003+1.46)
#   - 手填米重/重量与密度公式偏差 >5% 的行: 数据不改, remark 写偏差提示
#   - 派生字段 (spec/外径/id_x_od/体积) 由本脚本按 DERIVED_RULES 同逻辑填好
#
# 用法: python3 tools/gen_products_from_excel.py
# ============================================================

import csv
import io
import math
import re
import sys
from fractions import Fraction
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# 直接复用 csv_to_sql 的密度/派生逻辑, 保证生成的值和导入工具算出来的完全一致
from csv_to_sql import (  # noqa: E402
    calc_theoretical_thickness,
    calc_theoretical_weight,
    calc_theoretical_weight_per_meter,
    _build_spec,
    _format_id_od,
)

EXCEL_PATH = ROOT / "data" / "产品数据.xlsx"  # data/ 已 gitignore, 放根目录会触发敏感数据检查
PRODUCTS_CSV = ROOT / "data" / "csv" / "products.csv"
MATERIAL_ID_START = 10001

HEADER = [
    "material_id", "customer_code", "brand", "product_category", "material_type",
    "spec", "inner_diameter", "inner_diameter_inch", "outer_diameter", "id_x_od",
    "thickness", "length", "spec_meter", "virtual_weight", "virtual_length",
    "wire_spacing", "weight_per_meter", "weight",
    "appearance_inner", "appearance_outer", "appearance_height", "volume",
    "package", "label_paper", "material_used", "wire_pattern", "coil_type",
    "pressure", "spray_code", "meter_mark", "meter_mark_count", "remark", "is_active",
]

stats = {
    "total": 0, "thickness_derived": 0, "wpm_range_mid": 0, "weight_range_mid": 0,
    "weight_typo_fixed": 0, "weight_unparsable": 0, "deviation_noted": 0,
    "virtual_weight_zero_dropped": 0, "remark_truncated": 0, "spray_truncated": 0,
    "wpm_filled_from_weight": 0,
}


def fmt(v):
    """数值格式化: 整数去掉小数点"""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:g}"


def parse_num_or_range(raw, field_label):
    """
    解析数值单元格。返回 (value, note)。
    - 普通数值: 直接转
    - 区间 "180-185" / "39~40": 取中值, note 记录原值
    - 笔误 "34..7": 多点修单点, note 记录原值
    - 其他: 无法解析, note 记录原值
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None, None
    try:
        return float(s), None
    except ValueError:
        pass
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[-~—–]\s*(\d+(?:\.\d+)?)", s)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        mid = round((a + b) / 2, 3)
        return mid, f"{field_label}原值「{s}」取中值{fmt(mid)}"
    fixed = re.sub(r"\.{2,}", ".", s)
    try:
        v = float(fixed)
        return v, f"{field_label}原值「{s}」按{fmt(v)}计"
    except ValueError:
        pass
    # 兜底: 从文本里提取第一个数字 (如 "28/" -> 28, "大约56" -> 56)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        v = float(m.group(1))
        return v, f"{field_label}原值「{s}」按{fmt(v)}计"
    return None, f"{field_label}原值「{s}」无法解析"


def mm_to_inch_str(mm):
    """内径 mm -> 标称英寸字符串, 就近取 1/16 精度 (分母 2/4/8/16)"""
    sixteenths = max(1, round(mm / 25.4 * 16))
    frac = Fraction(sixteenths, 16)
    whole = frac.numerator // frac.denominator
    rem = Fraction(frac.numerator % frac.denominator, frac.denominator)
    if rem == 0:
        return f'{whole}"'
    if whole == 0:
        return f'{rem.numerator}/{rem.denominator}"'
    return f'{whole}-{rem.numerator}/{rem.denominator}"'


def calc_volume(ao, ah):
    """复刻 DERIVED_RULES volume: _safe_mul 链 (6 位) 再 _safe_div (4 位)"""
    a = round(round(round(ao * ao, 6) * ah, 6) * 0.93, 6)
    return round(a / 1_000_000, 4)


def build_row(rec, material_id):
    """把一行 Excel 记录转成 products 行 (dict)"""
    notes = []

    def s(key):
        v = rec.get(key)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return str(v).strip()

    category = s("产品类别")
    inner = float(s("内径"))
    length = float(s("长度"))
    spec_meter = int(length + 0.5)  # 四舍五入取整 (50.1 -> 50)
    inch = mm_to_inch_str(inner)

    # ---- 米重: kg/m -> g/m; 区间取中值 ----
    kgm_hand, note = parse_num_or_range(rec.get("米重"), "米重")
    if note:
        notes.append(note)
        if "取中值" in note:
            stats["wpm_range_mid"] += 1
    wpm_hand = round(kgm_hand * 1000, 3) if kgm_hand is not None else None

    # ---- 重量: 区间取中值 / 笔误修复 ----
    weight_hand, note = parse_num_or_range(rec.get("重量"), "重量")
    if note:
        notes.append(note)
        if "取中值" in note:
            stats["weight_range_mid"] += 1
        elif "按" in note and "计" in note:
            stats["weight_typo_fixed"] += 1
        elif "无法解析" in note:
            stats["weight_unparsable"] += 1

    # ---- 壁厚: 手填优先, 缺失则按密度公式反推 (路径 B/C) ----
    t_hand, _ = parse_num_or_range(rec.get("壁厚"), "壁厚")
    derive_ctx = {
        "product_category": category,
        "inner_diameter": fmt(inner),
        "weight_per_meter": fmt(wpm_hand) if wpm_hand is not None else "",
        "weight": fmt(weight_hand) if weight_hand is not None else "",
        "length": fmt(length),
    }
    if t_hand is not None:
        thickness = round(t_hand, 2)
    else:
        thickness = calc_theoretical_thickness(derive_ctx)
        if thickness is not None:
            stats["thickness_derived"] += 1

    # ---- 米重缺失时: 有重量+长度就按 重量*1000/长度 补 (与路径 C 自洽) ----
    if wpm_hand is None and weight_hand is not None and length > 0:
        wpm_hand = round(weight_hand * 1000 / length, 3)
        stats["wpm_filled_from_weight"] += 1

    # ---- 派生: 外径 / id_x_od / spec ----
    outer = round(inner + thickness * 2, 2) if thickness is not None else None
    id_x_od = _format_id_od(inner, outer) if outer is not None else ""
    spec = _build_spec({
        "inner_diameter_inch": inch,
        "inner_diameter": fmt(inner),
        "spec_meter": str(spec_meter),
    }) or ""

    # ---- 理论值与偏差提示 (>5% 才写 remark, 数据不改) ----
    final_ctx = {
        "product_category": category,
        "inner_diameter": fmt(inner),
        "thickness": fmt(thickness) if thickness is not None else "",
        "length": fmt(length),
    }
    theory_wpm = calc_theoretical_weight_per_meter(final_ctx)      # g/m
    theory_weight = calc_theoretical_weight(final_ctx)             # kg
    if theory_wpm and wpm_hand is not None and theory_wpm > 0:
        dev = abs(theory_wpm - wpm_hand) / theory_wpm
        if dev > 0.05:
            notes.append(
                f"米重手填{fmt(kgm_hand)}kg/m与理论{fmt(round(theory_wpm / 1000, 3))}kg/m偏差{dev * 100:.1f}%"
            )
            stats["deviation_noted"] += 1
    if theory_weight and weight_hand is not None and theory_weight > 0:
        dev = abs(theory_weight - weight_hand) / theory_weight
        if dev > 0.05:
            notes.append(
                f"单重手填{fmt(weight_hand)}kg与理论{fmt(theory_weight)}kg偏差{dev * 100:.1f}%"
            )

    # ---- 虚重: "0" 当空 ----
    vw, _ = parse_num_or_range(rec.get("虚重"), "虚重")
    if vw is not None and vw == 0:
        vw = None
        stats["virtual_weight_zero_dropped"] += 1
    vl, _ = parse_num_or_range(rec.get("虚米"), "虚米")

    # ---- 外观与体积 ----
    ai, _ = parse_num_or_range(rec.get("内圈"), "内圈")
    ao, _ = parse_num_or_range(rec.get("外圈"), "外圈")
    ah, _ = parse_num_or_range(rec.get("高度"), "高度")
    volume = calc_volume(ao, ah) if (ao is not None and ah is not None) else None

    # ---- remark: 原备注 + 各类提示 + 原 ID 溯源 ----
    base_remark = s("备注")
    notes.append(f"原ID:{s('ID')}")
    remark_parts = ([base_remark] if base_remark else []) + notes
    remark = "；".join(remark_parts)
    if len(remark) > 505:  # remark VARCHAR(512), 留余量: 优先保留提示, 截断原备注
        remark = remark[:502] + "..."
        stats["remark_truncated"] += 1

    spray = s("喷码")
    if len(spray) > 512:  # spray_code VARCHAR(512)
        spray = spray[:512]
        stats["spray_truncated"] += 1

    return {
        "material_id": material_id,
        "customer_code": s("客户编码"),
        "brand": "",
        "product_category": category,
        "material_type": "",
        "spec": spec,
        "inner_diameter": fmt(inner),
        "inner_diameter_inch": inch,
        "outer_diameter": fmt(outer) if outer is not None else "",
        "id_x_od": id_x_od,
        "thickness": fmt(thickness) if thickness is not None else "",
        "length": fmt(length),
        "spec_meter": str(spec_meter),
        "virtual_weight": fmt(vw) if vw is not None else "",
        "virtual_length": fmt(vl) if vl is not None else "",
        "wire_spacing": s("线距"),
        "weight_per_meter": fmt(wpm_hand) if wpm_hand is not None else "",
        "weight": fmt(weight_hand) if weight_hand is not None else "",
        "appearance_inner": fmt(ai) if ai is not None else "",
        "appearance_outer": fmt(ao) if ao is not None else "",
        "appearance_height": fmt(ah) if ah is not None else "",
        "volume": fmt(volume) if volume is not None else "",
        "package": s("包装"),
        "label_paper": "",
        "material_used": s("用料"),
        "wire_pattern": s("打线"),
        "coil_type": s("盘型说明"),
        "pressure": "",
        "spray_code": spray,
        "meter_mark": "",
        "meter_mark_count": "",
        "remark": remark,
        "is_active": "1",
    }


def main():
    df = pd.read_excel(EXCEL_PATH, dtype=str)
    df = df.iloc[1:].reset_index(drop=True)  # 跳过英文子表头行
    stats["total"] = len(df)

    # 幂等: 重建基底 = 现有 products.csv 中非本脚本生成的行
    # (M-XXXXX 纯数字编号是本脚本产物, 重跑时先剔除再追加, 不会重复)
    kept_rows = []
    if PRODUCTS_CSV.exists():
        with open(PRODUCTS_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if not re.fullmatch(r"M-\d{5}", row.get("material_id", "")):
                    kept_rows.append(row)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEADER, lineterminator="\n")
    writer.writeheader()
    for row in kept_rows:
        writer.writerow({k: (row.get(k) or "") for k in HEADER})

    # 生成新行 (csv.writer 保证引号/换行转义正确)
    for i, (_, rec) in enumerate(df.iterrows()):
        material_id = f"M-{MATERIAL_ID_START + i}"
        writer.writerow(build_row(rec.to_dict(), material_id))

    PRODUCTS_CSV.write_text(buf.getvalue(), encoding="utf-8")

    print(f"[OK] 保留现有 {len(kept_rows)} 行 + 新增 Excel 数据 {stats['total']} 行 -> {PRODUCTS_CSV}")
    print(f"     material_id 范围: M-{MATERIAL_ID_START} ~ M-{MATERIAL_ID_START + stats['total'] - 1}")
    for k, v in stats.items():
        if k != "total" and v:
            print(f"     {k}: {v}")


if __name__ == "__main__":
    main()
