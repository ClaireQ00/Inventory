#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV 编码 & 格式规范化
====================

为什么需要它:
- 用户用 Excel (Windows / 中文环境) 编辑 CSV 时, Excel 默认存成 GBK + CRLF
- 多行字段 (如 billing_profiles 里的地址) 会让文件出现混合换行, 破坏 CSV 结构
- 这些文件直接喂给 validator 会乱码 / 解析错位

它做什么 (3 件事):
1. 自动检测编码 (UTF-8 / GBK / GB18030), 转 UTF-8
2. 规范换行符: CRLF / CR -> LF
3. 多行字段压成单行 (字段内部的换行换成空格), 并规范双引号转义

它不做什么 (B 类问题, 救不了):
- Excel 把日期转成 7/29/2026 -> 信息已丢, 脚本无法恢复
- Excel 把大数字变科学计数法 1E+08 -> 同上
- 这些要在 Excel 填写时避免 (见 docs/IMPORT_TEMPLATES.md "Excel 避坑指南")

使用方法:
    python3 tools/normalize_csv.py                    # 规范化 data/csv/ 下所有 *.csv
    python3 tools/normalize_csv.py data/csv/a.csv    # 规范化指定文件
    python3 tools/normalize_csv.py --check           # 只检查不改, 报告哪些需要规范化

集成:
    run_local_validation.sh 在步骤 2c 自动调用 (用户无需手动跑)
"""

import csv
import os
import sys
import glob

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CSV_DIR = os.path.join(ROOT_DIR, "data", "csv")

# 试这些编码, 哪个能解码成功就用哪个 (顺序很重要: UTF-8 优先)
CANDIDATE_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "latin-1")


def detect_encoding(path):
    """尝试用候选编码读文件, 返回第一个成功的编码名"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in CANDIDATE_ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    # 实在识别不出来, 兜底用 latin-1 (不会失败, 但中文可能乱码)
    return "latin-1"


def normalize_one(path, check_only=False):
    """
    规范化单个 CSV 文件
    返回: (是否改动, 改动描述列表)
    """
    if not os.path.exists(path):
        return False, [f"文件不存在: {path}"]

    changes = []

    # 1. 检测编码
    enc = detect_encoding(path)
    with open(path, encoding=enc) as f:
        raw = f.read()

    if enc not in ("utf-8", "utf-8-sig"):
        changes.append(f"编码 {enc} → UTF-8")

    # 2. 检查换行符
    has_crlf = "\r\n" in raw
    has_cr_only = "\r" in raw and "\r\n" not in raw
    if has_crlf:
        changes.append("换行 CRLF → LF")
    if has_cr_only:
        changes.append("换行 CR → LF")

    # 规范化换行
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    # 3. 用 csv 模块解析, 检查多行字段
    try:
        reader = csv.reader(raw.splitlines())
        rows = list(reader)
    except csv.Error as e:
        return False, [f"CSV 解析失败: {e} (文件可能已损坏)"]

    # 检查字段里有没有残留的换行 (csv.reader 会把引号内的换行保留在字段值里)
    multiline_fields = 0
    for r in rows:
        for i, v in enumerate(r):
            if "\n" in v:
                multiline_fields += 1
    if multiline_fields > 0:
        changes.append(f"压平 {multiline_fields} 个多行字段")

    # 如果没改动, 直接返回
    if not changes:
        return False, []

    if check_only:
        return True, changes

    # 执行修改: 压平多行字段
    for r in rows:
        for i, v in enumerate(r):
            if "\n" in v:
                # 多个连续空白压成一个空格
                r[i] = " ".join(v.split())

    # 写回 (UTF-8 + LF)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerows(rows)

    return True, changes


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    args = [a for a in args if a != "--check"]

    # 决定要处理哪些文件
    if args:
        targets = args
    else:
        # 默认处理 data/csv/ 下所有 *.csv (不递归 demo_runtime 等子目录)
        targets = sorted(glob.glob(os.path.join(DEFAULT_CSV_DIR, "*.csv")))

    if not targets:
        print("[normalize] 没有找到 CSV 文件")
        return 0

    print(f"[normalize] 处理 {len(targets)} 个文件{' (只检查不改)' if check_only else ''}...")
    changed_count = 0
    for path in targets:
        rel = os.path.relpath(path, ROOT_DIR) if path.startswith(ROOT_DIR) else path
        changed, changes = normalize_one(path, check_only=check_only)
        if changed:
            changed_count += 1
            detail = ", ".join(changes)
            print(f"  [{'需改' if check_only else '已改'}] {rel}: {detail}")
        else:
            print(f"  [OK]   {rel}")

    print(f"[normalize] 完成: {changed_count}/{len(targets)} 个文件{'需要规范化' if check_only else '已规范化'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
