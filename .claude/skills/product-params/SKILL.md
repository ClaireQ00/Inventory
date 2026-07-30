---
name: product-params
description: 进销存项目的产品类别参数计算规则集。当用户在 products 表里处理 内径/厚度/长度/米重(weight_per_meter)/单件重量(weight)/密度 这些互相推算的字段，问到"线管密度"、"钢丝管密度"、"反推厚度"、"客户只给了内径和重量怎么算厚度"、"5% 重量容差"、"米重和单重对不上"时使用此 skill。涉及 tools/csv_to_sql.py 的 DENSITY_RULES / calc_theoretical_thickness / check_cross_field_consistency。
allowed-tools: Read, Grep, Glob, Bash(python3:*)
---

# 产品类别参数计算 · 完整规则集

## ⏱️ 5 分钟速查卡（没时间就只看这 3 条）

1. **铁律**：所有重量都从**密度公式**出发（`米重 = (内径+厚度) × 厚度 × 3.14 × 密度`），**不要**为不同产品类别写两套公式
2. **必看**：厚度反推有 3 条路径（A 几何 `外径→内径` / B 密度方程 `内径+米重` / C `内径+单重+长度`），优先用 A（最精确）
3. **闪人**：如果是外径/体积/金额派生 → `derived-fields`；如果是收款/汇率 → `payment-receivable`

---

## 谁会用这个 skill

| 角色 | 关心什么 | 重点看哪节 |
| --- | --- | --- |
| 物料管理员 / 数据录入员 | 录物料时只给 3-4 个参数，其他自动算 | §1 密度公式、§2 厚度反推 3 条路径 |
| 外贸业务经理 | 跟客户核对米重 / 单重对不对 | §3 米重公式、§4 5% 重量容差 |
| QA / 验收 | 米重和单件重量互相反推对不对得上 | §5 跨字段一致性校验 |

## 一句话总结

新增物料时，客户通常只给 3~4 个参数（必给内径，再加 长度/厚度/米重/单重 中的 2~3 个），剩下的字段靠**密度公式**自动推算或反推。米重和单件重量跟公式算的理论值允许有 5% 偏差（客户会"上下浮动"确定），按客户给定的值保存。

---

## 1. 产品类别与密度公式

不同产品类别（线管/钢丝管/塑筋管/水带）密度公式不同，**所有重量计算都从密度出发**，不要有两套公式。

| 产品类别 | 密度公式 | 备注 |
| --- | --- | --- |
| 线管 | `ρ = 1.35` (固定) | |
| 钢丝管 | `ρ = inner_diameter × 0.003 + 1.46` | 钢丝型号会影响, 粗略按口径估 |
| 塑筋管 | (TODO 待客户补充) | |
| 水带 | (TODO 待客户补充) | |

**单位约定**：内径/厚度 mm，长度 m，米重 g/m，单件重量 kg，密度无量纲。

代码：`tools/csv_to_sql.py::DENSITY_RULES` 字典 + `calc_density(row)` 函数。

---

## 2. 统一公式链

```
密度 ρ (由 product_category 决定)
   │
   ▼
理论米重 (g/m) = (内径 + 厚度) × 厚度 × 3.14 × ρ
   │
   ▼
理论单件重量 (kg) = 理论米重 × 长度 / 1000
```

代码：
- `calc_theoretical_weight_per_meter(row)` — 米重正算
- `calc_theoretical_weight(row)` — 单重正算
- `calc_theoretical_thickness(row)` — **厚度反算（三条路径，见 §3）**

---

## 3. 厚度反推（三条路径，按优先级）

当客户没给厚度时，系统按以下**优先级**依次尝试反推（任一成功即返回）：

### 路径 A（优先，几何反推）：已知 外径 + 内径

```
厚度 = (外径 - 内径) / 2
```

**优点**：纯几何关系，不依赖密度，跟产品类别无关，100% 精确。

**触发条件**：CSV 里有 `outer_diameter` 且大于 `inner_diameter`。

### 路径 B（密度方程反推）：已知 内径 + 米重 + 密度

```
原式:  米重 = (内径 + 厚度) × 厚度 × 3.14 × 密度
       ↓ 设 t = 厚度, k = 密度 × 3.14
       k·t² + k·内径·t − 米重 = 0
       ↓ 求根公式 (取正根)
       t = [−k·内径 + √((k·内径)² + 4·k·米重)] / (2·k)
```

**触发条件**：CSV 里有 `weight_per_meter` + `product_category`（决定密度）。

### 路径 C（密度方程反推）：已知 内径 + 单重 + 长度 + 密度

```
先算米重 = 单重 × 1000 / 长度
再走路径 B
```

**触发条件**：CSV 里有 `weight` + `length` + `product_category`。

---

**底层代码**：`tools/csv_to_sql.py::calc_theoretical_thickness(row)`

**DERIVED_RULES 配置**：
```python
"thickness": {
    "expr": ...,
    "depends_on": ["inner_diameter"],            # 必要字段
    "depends_on_any": [                          # 任一路径齐即可
        ["outer_diameter"],                      # 路径 A
        ["product_category", "weight_per_meter"],  # 路径 B
        ["product_category", "weight", "length"],  # 路径 C
    ],
    ...
}
```

---

## 4. 客户可能给的参数组合（7 种场景）

| # | 客户给的 | 系统自动补算 |
| --- | --- | --- |
| ① | 内径 + 厚度 + 长度 | 米重、单重 (密度公式) |
| ② | 内径 + 厚度 + 长度 + 米重 | 单重 (按客户米重算) |
| ③ | 内径 + 厚度 + 长度 + 单重 | 米重 (按客户单重反推) |
| ④ | **内径 + 长度 + 米重** | **厚度** (解方程), 单重 |
| ⑤ | **内径 + 长度 + 单重** | **厚度** (解方程), 米重 |
| ⑥ | 内径 + 厚度 + 米重 | 单重 (无长度算不出体积/单重, 留空) |
| ⑦ | 内径 + 厚度 + 单重 | 米重 (无长度算不出体积, 留空) |

**长度字段是物料核心属性，必须给**——业务约定一卷物料长度固定，变了就新增物料。

---

## 5. 容差规则（5% 百分比）

### 5.1 反向校验（强制 error，阻止生成 SQL）

下列字段，客户手填值跟公式算的理论值偏差 > 5% → **报错阻止**：

| 字段 | 公式 | 容差 |
| --- | --- | --- |
| `thickness` 厚度 | 反推公式 (见 §3) | 5% |
| `weight_per_meter` 米重 | 密度公式正算 | 5% |
| `weight` 单件重量 | 密度公式正算 × 长度 | 5% |

**注意**：客户允许"上下浮动"确定最终值，5% 内按客户值保存（不被覆盖）。

### 5.2 跨字段互校（warn，不阻止生成）

| 检查 | 触发条件 |
| --- | --- |
| `米重 × 长度 / 1000` vs `单件重量` | 偏差 > 5% → WARN |

为什么是 warn 不是 error：客户可以单独虚标米重或单重（虚标是外贸业务约定），各自跟密度公式 5% 内都算正常，但两者互相反推差太多给个提醒。

代码：`check_cross_field_consistency()` 函数 + `CROSS_FIELD_TOLERANCE = 0.05`。

---

## 6. depends_on_any：多路径依赖

`tools/csv_to_sql.py` 的 `apply_derived_rules()` 支持两种依赖写法：

```python
"thickness": {
    "expr": ...,
    "depends_on": ["product_category", "inner_diameter"],     # 必须都有 (AND)
    "depends_on_any": [                                         # 任一组齐即可 (OR)
        ["weight_per_meter"],          # 路径1: 客户给米重
        ["weight", "length"],          # 路径2: 客户给单重+长度
    ],
    ...
}
```

逻辑：`depends_on` 全有 **且** `depends_on_any` 至少一组全有 → 才会调用 expr 加算。

---

## 7. 加新物料类别（如塑筋管/水带补全密度公式）

### 7.1 简单固定密度（像线管）

```python
DENSITY_RULES["水带"] = lambda row: 1.40  # 改成实际值
```

### 7.2 按规格变化的密度（像钢丝管）

```python
DENSITY_RULES["塑筋管"] = lambda row: (
    lambda id_: round(id_ * 0.005 + 1.30, 4) if id_ is not None else None
)(_to_float(row.get("inner_diameter")))
```

### 7.3 同步更新

- `DENSITY_RULES` 字典里加新条目
- 本 skill 文档第 1 节加新行
- `make_demo_data.py` 加该类别的示例物料（验证公式）

---

## 8. 给 Claude 自己的提醒（处理此类任务时遵循）

- ✅ 客户只给 3 个参数时，**先用密度公式反推**，不要问"厚度是多少"
- ✅ 客户给的米重/单重在 5% 内偏差，**按客户值保存**，不要覆盖成公式值
- ✅ 客户给的米重/单重偏差 > 5%，**报错阻止生成 SQL**，让用户核对
- ❌ 不要建议用户手填厚度（除非客户真的提供了）
- ❌ 不要把"米重 × 长度 = 单重"做成 error（这会跟密度校验冲突），用 warn 互校
- ❌ 不要为不同产品类别写不同的重量公式——**全走密度公式链**
- ✅ 加新类别时，同步改 `DENSITY_RULES` + 本 skill 第 1 节
- ✅ 厚度反推的求根公式取**正根**（负根没物理意义）

---

## 9. 完整决策流程图

```
用户填 products.csv 一行
   │
   ├─ 客户给的参数: 内径 (必) + 长度 (必) + 厚度/米重/单重 (任 1~3 个)
   │
   ▼
apply_derived_rules() 按字段顺序处理:
   │
   ├─ 1. thickness 缺?
   │     ├─ 有 米重 OR (单重+长度) → 解方程反推
   │     └─ 都没有 → 跳过
   │
   ├─ 2. outer_diameter 缺? → 内径 + 厚度 × 2
   ├─ 3. id_x_od 缺? → "内径x外径" 字符串
   │
   ├─ 4. weight_per_meter 缺? → 密度公式算
   ├─ 5. weight 缺? → 米重 × 长度 / 1000 (注: 现用密度公式直接算)
   │
   ├─ 6. volume 缺? → 外观外径(mm)² × 外观高度(mm) × 0.93 / 1e6
   │
   ▼
反向校验 (填了的字段都跟公式比 5%):
   │
   ├─ 偏差 ≤ 5%: 保留客户值, INFO 提示已校验通过
   └─ 偏差 > 5%: ERROR, 阻止生成 SQL
   │
   ▼
跨字段互校:
   │
   └─ 米重×长度 vs 单重 偏差 > 5%: WARN (不阻止)
   │
   ▼
生成 SQL INSERT
```

---

## 🔗 跨 skill 协作场景

### 场景：录新物料（同时涉及 product-params + derived-fields）

**触发**：客户发来一个新规格，需要录入 `products` 表

**协作顺序**：
1. 先用 **product-params**（本 skill）算出**厚度**（通过 3 条路径之一）+ **米重 / 单重**（密度公式）
2. 再让 **derived-fields** 自动派生 **外径**（`内径 + 厚度 × 2`）/ **id_x_od** 字符串 / **单件体积**

**举例**：客户给 PVC 线管 `内径=32mm + 米重=450g/m + 长度=6m`
- Step 1（product-params）：解方程反推厚度 ≈ 2.18mm；线管密度 ρ=1.35
- Step 2（derived-fields）：外径 = 32 + 2.18×2 = 36.36mm；volume 由外观尺寸算

**为什么拆两步**：厚度依赖产品类别（密度），是 product-params 独有职责；外径不依赖类别（纯几何），是 derived-fields 职责。

### 场景：跟报关衔接（product-params → trade-documents）

**触发**：装柜时报关单需要毛重 / 净重

**协作顺序**：
1. product-params 提供 `weight`（单件重量）和 `weight_per_meter`（米重）
2. trade-documents 在 `shipping_record_items.gross_weight_per` / `net_weight_per` 里用这些值做报关数据

**关键**：单件重量来自 product-params，报关行不能自己改——改了就跟库存对不上。

---

## 10. 相关文件索引

| 文件 | 作用 |
| --- | --- |
| `tools/csv_to_sql.py` | 派生规则定义 + 密度公式 + 厚度反推 + 跨字段校验 |
| `tools/local_validator.py` | 跨表校验（不重算产品参数） |
| `tools/make_demo_data.py` | 演示数据（含线管/钢丝管示例） |
| `.claude/skills/derived-fields/SKILL.md` | 行内公式规则（外径/体积/金额等），不含产品参数 |
| `sql/01_schema.sql` | products 表字段定义 |
