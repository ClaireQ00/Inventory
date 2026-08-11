#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""name_variants.py — 档案字段"同物异名"归一工具 (2026-08-11)

业务背景 (老板提出): 同一产品类别会被写成谐音/异体字 —— "双联"vs"双连"、
"磨砂"vs"磨沙"。人录入时随手一打就产生新类别, 报表统计就裂成两类。

三道防线的共用基础:
  ① 录入实时提示: db_writer.live_derive_products 调 near_match 给 WARN
  ② 落库自动归一: db_writer.validate_fields 把异写替换成标准写法
  ③ 存量兜底扫描: local_validator 校验第 1 步报近名簇 WARN

归一规则 (norm_name):
  1. 去全部空白字符
  2. 易混字归一 (HOMOPHONE_MAP, 可扩充 —— 发现新谐音对就加)
  3. 英文统一小写

近名判定 (near_match): 仅认归一后相等 (谐音/空白/大小写)。**不用编辑距离** —
中文档案名一字之差常是真区别 (黄花园管≠蓝花园管), 见 near_match docstring。
"""

from __future__ import annotations

# 易混字对照 (谐音/形近): 键 → 归一目标字。单向归一即可, 发现新对就加。
HOMOPHONE_MAP: dict[str, str] = {
    "联": "连",   # 双联 → 双连
    "砂": "沙",   # 磨砂 → 磨沙 (老板原例: 实际写法以"磨沙"入库的为准, 统一向存量多的一侧)
    "兰": "蓝",
    "像": "象",
    "煌": "黄",
    "嘀": "的",
}


def norm_name(s: str | None) -> str:
    """档案名归一: 去空白 + 易混字 + 小写。用于比对, 不改库里的原文。"""
    if not s:
        return ""
    x = "".join(str(s).split())
    for k, v in HOMOPHONE_MAP.items():
        x = x.replace(k, v)
    return x.lower()


def near_match(name: str | None, candidates: list[str]) -> str | None:
    """在既有写法候选里找 name 的"同物异名"。返回候选原文, 没有返回 None。

    完全相等(未归一)不算异名, 返回 None —— 那是正常命中。
    只认"归一后相等"(谐音/空白/大小写变体) —— 故意不用编辑距离:
    中文档案名一字之差往往是真区别 (黄花园管≠蓝花园管、三胶一线≠两胶一线),
    编辑距离会误并, 2026-08-11 实测产生大量误报后移除。
    """
    if not name:
        return None
    raw = str(name).strip()
    n = norm_name(raw)
    if not n:
        return None
    for c in candidates:
        if c == raw:
            return None  # 精确命中既有写法, 不是异名
    for c in candidates:
        if norm_name(c) == n:
            return c
    return None


def find_clusters(names: list[str]) -> list[list[str]]:
    """存量扫描: 按归一相等聚簇 (同 near_match, 不用编辑距离), 返回 >1 个写法的簇。"""
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(norm_name(n), []).append(n)
    return [v for v in groups.values() if len(v) > 1]
