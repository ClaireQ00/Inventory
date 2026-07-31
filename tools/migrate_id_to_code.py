#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外键迁移脚本: *_id INT → 业务编号
================================

背景 (ADR-0004):
- 2026-07-30 schema 改造, 所有硬外键从 INT 自增 id 改成 VARCHAR 业务编号
- 但 data/csv/ 下的真实业务数据还是老格式 (customer_id=2, contract_id=1 ...)
- 这个脚本把老 CSV 转成新格式, 让真实数据能重新导入新 schema

迁移哪些文件:
- data/csv/sales_contracts.csv         (customer_id → customer_code)
- data/csv/sales_contract_items.csv    (contract_id→contract_no, product_id→material_id, 补 item_no)
- data/csv/quotations.csv              (customer_id→customer_code, parent_quote_id→parent_quote_no,
                                        converted_contract_id→converted_contract_no)
- data/csv/quotation_items.csv         (quote_id→quote_no, product_id→material_id, 补 item_no)

为什么不全自动:
- products.csv 有 id 列, 可以自动反查 id→material_id
- 但 customers / sales_contracts / quotations 三张主表的 CSV 没有 id 列
  (它们的 id 只在 MySQL 里, 而 MySQL 在 B1 改 schema 时已 TRUNCATE)
- 所以 customer_id=2 到底对应哪个 code, 只能人工填下面的映射表
- 数据量很小 (当前真实数据总共 ~17 行), 人工填映射比写复杂反查逻辑更稳妥

使用方法:
    1. 填好下面三个映射表 (CUSTOMER_ID_TO_CODE / CONTRACT_ID_TO_NO / QUOTE_ID_TO_NO)
    2. python3 tools/migrate_id_to_code.py
    3. 脚本会先备份 *.csv → *.csv.bak, 再原地覆盖
    4. 迁移前会先校验所有 INT 值都能在映射表里找到, 找不到就停, 不写半成品

映射值怎么找:
- customer_id=2 是谁: 看 customers.csv 第几行 (第2行=id 2), 或从 quotations.csv
  的备注里反推 (如 "YL260728Q025 是 Q025 客户的报价")
- contract_id / quote_id: sales_contracts.csv / quotations.csv 每行按导入顺序就是 id 1,2,3...
"""

import csv
import os
import shutil
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(ROOT_DIR, "data", "csv")

# ============================================================
# 用户必填: INT id → 业务编号 映射表
# ============================================================
# 怎么填: 打开对应的 CSV, 第 N 行数据 (不含表头) 对应 id=N
# 例如 customers.csv 第 2 行是 Q025, 那 CUSTOMER_ID_TO_CODE[2] = "Q025"

CUSTOMER_ID_TO_CODE = {
    2: "Q025",   # 印尼大雄 (YL260728Q025 报价的客户)
    # 3: "Q026",
    # 4: "Q027",
}

CONTRACT_ID_TO_NO = {
    1: "SC20260730001",   # 从 formal 报价 YL260728Q025 转单
}

QUOTE_ID_TO_NO = {
    1: "YL260728Q025-brief",   # 简要报价
    2: "YL260728Q025",         # 正式报价
}

# ============================================================
# 列名重命名规则 (老列名 → 新列名)
# ============================================================
RENAME_MAP = {
    "sales_contracts.csv": {
        "customer_id": "customer_code",
    },
    "sales_contract_items.csv": {
        "contract_id": "contract_no",
        "product_id": "material_id",
    },
    "quotations.csv": {
        "customer_id": "customer_code",
        "parent_quote_id": "parent_quote_no",
        "converted_contract_id": "converted_contract_no",
    },
    "quotation_items.csv": {
        "quote_id": "quote_no",
        "product_id": "material_id",
    },
}

# 明细表需要补 item_no 列 (按主表单号分组, 001/002/003 递增)
DETAIL_TABLES_NEED_ITEM_NO = {
    "sales_contract_items.csv": "contract_no",
    "quotation_items.csv": "quote_no",
}

# product_id → material_id 映射从 products.csv 自动读
PRODUCT_ID_TO_MATERIAL = {}


def load_product_mapping():
    """从 products.csv 读 id → material_id 映射 (products 有 id 列)"""
    path = os.path.join(CSV_DIR, "products.csv")
    if not os.path.exists(path):
        print(f"[警告] {path} 不存在, product_id 反查会失败")
        return
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("id", "").strip()
            mid = row.get("material_id", "").strip()
            if pid and mid:
                PRODUCT_ID_TO_MATERIAL[int(pid)] = mid
    print(f"[加载] products.csv: {len(PRODUCT_ID_TO_MATERIAL)} 条 id→material_id 映射")


def lookup(value, mapping, mapping_name, context):
    """
    把 CSV 单元格里的 INT 值转成业务编号
    value: 原始值 (字符串或空)
    mapping: 查找表 dict
    mapping_name: 报错时显示哪个映射表
    context: 报错时显示是哪一行 (用于排错)
    返回: 转换后的业务编号字符串, 或空字符串 (空值保持空)
    """
    if value is None or str(value).strip() == "":
        return ""
    try:
        key = int(value)
    except ValueError:
        # 已经是业务编号了 (可能之前迁移过), 原样返回
        return value
    if key not in mapping:
        raise RuntimeError(
            f"[迁移失败] {mapping_name} 里找不到 id={key} ({context})\n"
            f"  请在脚本顶部的映射表里补上 {mapping_name}[{key}] = ?"
        )
    return mapping[key]


def gen_item_no_sequence(rows, group_col):
    """
    给一组明细行按 group_col (主表单号) 分组, 生成 001/002/003... 的 item_no
    返回: [(row_index, item_no), ...] 顺序与输入 rows 一致
    """
    counter = {}
    result = []
    for idx, row in enumerate(rows):
        group_key = row.get(group_col, "")
        counter[group_key] = counter.get(group_key, 0) + 1
        result.append((idx, f"{counter[group_key]:03d}"))
    return result


def migrate_file(filename):
    """迁移单个 CSV 文件"""
    path = os.path.join(CSV_DIR, filename)
    if not os.path.exists(path):
        print(f"[跳过] {filename} 不存在")
        return False

    # 读老数据
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        all_rows = list(reader)
    if len(all_rows) < 2:
        print(f"[跳过] {filename} 没有数据行")
        return False

    old_header = all_rows[0]
    data_rows = all_rows[1:]

    rename = RENAME_MAP.get(filename, {})
    # 生成新表头
    new_header = [rename.get(col, col) for col in old_header]

    # 转换每一行
    new_data_rows = []
    for row_idx, row in enumerate(data_rows):
        if not row:  # 空行跳过
            continue
        old_dict = dict(zip(old_header, row))
        new_dict = {}
        for old_col, val in old_dict.items():
            new_col = rename.get(old_col, old_col)
            context = f"{filename} 行{row_idx+2} 列{old_col}={val}"
            if old_col == "customer_id":
                new_dict[new_col] = lookup(val, CUSTOMER_ID_TO_CODE, "CUSTOMER_ID_TO_CODE", context)
            elif old_col == "contract_id":
                new_dict[new_col] = lookup(val, CONTRACT_ID_TO_NO, "CONTRACT_ID_TO_NO", context)
            elif old_col == "quote_id":
                new_dict[new_col] = lookup(val, QUOTE_ID_TO_NO, "QUOTE_ID_TO_NO", context)
            elif old_col == "parent_quote_id":
                # parent_quote_id 可空 (brief 报价没父单), 空值保持空
                new_dict[new_col] = lookup(val, QUOTE_ID_TO_NO, "QUOTE_ID_TO_NO", context)
            elif old_col == "converted_contract_id":
                # 软关联, 可空
                new_dict[new_col] = lookup(val, CONTRACT_ID_TO_NO, "CONTRACT_ID_TO_NO", context)
            elif old_col == "product_id":
                new_dict[new_col] = lookup(val, PRODUCT_ID_TO_MATERIAL, "products.csv (id→material_id)", context)
            else:
                new_dict[new_col] = val
        new_data_rows.append(new_dict)

    # 明细表补 item_no
    if filename in DETAIL_TABLES_NEED_ITEM_NO:
        group_col = DETAIL_TABLES_NEED_ITEM_NO[filename]
        # item_no 插在 group_col 后面
        insert_pos = new_header.index(group_col) + 1
        new_header.insert(insert_pos, "item_no")
        item_no_seq = gen_item_no_sequence(new_data_rows, group_col)
        for row_idx, item_no in item_no_seq:
            # 在对应行的 dict 里, 按 new_header 顺序插入
            row_dict = new_data_rows[row_idx]
            # 重建有序 dict
            ordered = {}
            for col in new_header:
                if col == "item_no":
                    ordered[col] = item_no
                else:
                    ordered[col] = row_dict.get(col, "")
            new_data_rows[row_idx] = ordered

    # 先备份 (覆盖之前的 .bak, 保证每次迁移前的状态)
    bak_path = path + ".bak"
    shutil.copy2(path, bak_path)
    print(f"[备份] {filename} → {filename}.bak")

    # 写新数据
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(new_header)
        for row_dict in new_data_rows:
            writer.writerow([row_dict.get(col, "") for col in new_header])

    renamed_cols = [f"{k}→{v}" for k, v in rename.items()]
    extra_msg = ""
    if filename in DETAIL_TABLES_NEED_ITEM_NO:
        extra_msg = " + 补 item_no 列"
    print(f"[完成] {filename}: {len(new_data_rows)} 行, 改列 {renamed_cols}{extra_msg}")
    return True


def main():
    print("=" * 60)
    print("外键迁移: *_id INT → 业务编号 (ADR-0004)")
    print("=" * 60)
    print(f"CSV 目录: {CSV_DIR}")
    print()

    # 0. 先加载 products 映射
    load_product_mapping()
    print()

    # 1. 检查映射表是否填了
    if not CUSTOMER_ID_TO_CODE:
        print("[警告] CUSTOMER_ID_TO_CODE 是空的, sales_contracts/quotations 的 customer_id 会迁移失败")
    if not CONTRACT_ID_TO_NO:
        print("[警告] CONTRACT_ID_TO_NO 是空的")
    if not QUOTE_ID_TO_NO:
        print("[警告] QUOTE_ID_TO_NO 是空的")
    print()

    # 2. 逐个迁移
    targets = [
        "sales_contracts.csv",
        "sales_contract_items.csv",
        "quotations.csv",
        "quotation_items.csv",
    ]
    migrated = 0
    for fn in targets:
        try:
            if migrate_file(fn):
                migrated += 1
        except RuntimeError as e:
            print()
            print(str(e))
            print()
            print("[中止] 上面这个文件迁移失败, 后面的文件没动。")
            print("       修好映射表后重新跑即可 (已迁移的会有 .bak 备份)。")
            sys.exit(1)

    print()
    print(f"[汇总] 成功迁移 {migrated}/{len(targets)} 个文件")
    print()
    print("下一步:")
    print("  1. 检查迁移结果: head data/csv/sales_contract_items.csv")
    print("  2. 跑真实数据校验: bash scripts/run_local_validation.sh")
    print("  3. 如果有问题, 恢复备份: cp data/csv/*.csv.bak data/csv/*.csv")


if __name__ == "__main__":
    main()
