#!/usr/bin/env python3
"""演示测试: 四角色多场景全链路 e2e (2026-08-14)

角色: 业务员(客户/物料/报价/合同/发货/关行/收款) · 生产调度(生产入库)
      保管员(调拨/销售出库/辅料收发) · 老板(特批/复核)
测试数据专用编码段: 客户 Z9999 / 物料 M-Z9999-* / 单据 *-TEST*,
跑前做冲突预检(撞上任何现存数据立即中止), 跑完逐条清理, 不碰真实数据。
跑法: python3 tests/demo_roleplay_test.py
"""
import json
import subprocess
import sys
import urllib.request

API = "http://127.0.0.1:8000"
OP = "demo-test"
CUST = "Z9999"
MAT1, MAT2, MAT3 = "M-Z9999-001", "M-Z9999-002", "M-Z9999-003"
RESULTS: list[tuple[str, bool, str]] = []


def call(method: str, path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"}, method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def sql(stmt: str) -> str:
    pw = ""
    with open(".env") as f:
        for line in f:
            if line.startswith("MYSQL_PASSWORD="):
                pw = line.strip().split("=", 1)[1]
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "db",
         "mysql", "-uinventory", f"-p{pw}", "inventory_db", "-N", "-e", stmt],
        capture_output=True, text=True)
    if out.returncode != 0:
        print(f"  [SQL警告] {out.stderr.strip()[:120]}")
    return out.stdout.strip()


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, cond, detail))
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))


def doc(path: str, header: dict, items: list[dict]) -> dict:
    return call("POST", path, {"header": header, "items": items, "operator": OP})


# ── 冲突预检: 测试编码段撞上任何现存数据 → 立即中止 ─────────────
print("【预检】测试编码段冲突检查 (客户 Z9999 / 物料 M-Z9999-* / 单据 *-TEST*)")
clash = sql(f"""SELECT (SELECT COUNT(*) FROM customers WHERE code='{CUST}')
 + (SELECT COUNT(*) FROM products WHERE material_id LIKE 'M-Z9999-%')
 + (SELECT COUNT(*) FROM sales_contracts WHERE contract_no LIKE '%-TEST%')
 + (SELECT COUNT(*) FROM quotations WHERE quote_no LIKE '%-TEST%')
 + (SELECT COUNT(*) FROM delivery_orders WHERE delivery_no LIKE '%-TEST%')
 + (SELECT COUNT(*) FROM stock_in WHERE in_no LIKE '%-TEST%')
 + (SELECT COUNT(*) FROM stock_out WHERE out_no LIKE '%-TEST%')
 + (SELECT COUNT(*) FROM receipts WHERE receipt_no LIKE '%-TEST%')
 + (SELECT COUNT(*) FROM aux_materials WHERE aux_code='LP-TEST01')""")
if clash != "0":
    print(f"❌ 预检失败: 测试编码段与现存数据冲突 ({clash} 条), 中止以保护数据")
    sys.exit(2)
print("  ✅ 编码段干净, 可以开跑")

print("=" * 64)
print("演示测试开始 (全部测试数据, 结束后自动清理)")
print("=" * 64)

# ── S0 准备: 辅料标签档案 (保管员/采购) ─────────────────────────
print("\n【S0 准备】辅料标签纸档案 LP-TEST01")
r = call("POST", "/api/aux/materials", {"data": {
    "aux_code": "LP-TEST01", "aux_type": "label_paper", "name": "演示标签纸",
    "shape": "rect", "width_mm": 100, "height_mm": 60,
    "material_desc": "铜版纸", "unit": "张", "min_stock": 50,
}, "operator": OP})
check("辅料建档", r.get("ok"), str(r.get("errors", "")))

# ── S1 业务员: 客户建档 ────────────────────────────────────────
print(f"\n【S1 业务员】客户建档 {CUST}")
r = call("POST", "/api/customers", {"data": {"code": CUST, "name": "演示测试客户"}, "operator": OP})
check("客户建档", r.get("ok"), str(r.get("errors", "")))
r2 = call("POST", "/api/customers", {"data": {"code": CUST, "name": "重复"}, "operator": OP})
check("重复建档被拒", not r2.get("ok"), r2.get("errors", [""])[0])
r3 = call("POST", "/api/customers", {"data": {"code": "Z99999", "name": "五位数字"}, "operator": OP})
check("五位数字编号被拒(R12)", not r3.get("ok"), r3.get("errors", [""])[0][:40])

# ── S2 业务员: 物料建档 ────────────────────────────────────────
print(f"\n【S2 业务员】物料建档 {MAT1}/{MAT2}/{MAT3}")
for mid, w, lbl in [(MAT1, 28.5, "TEST01"), (MAT2, 50.0, ""), (MAT3, 10.0, "")]:
    r = call("POST", "/api/insert", {"table": "products", "operator": OP, "data": {
        "material_id": mid, "customer_code": CUST, "product_category": "线管",
        "spec": f"1寸x50m-{mid[-3:]}", "inner_diameter": 25.4, "thickness": 3.5,
        "length": 50, "weight": w, "label_paper": lbl, "remark": "演示测试料",
    }})
    check(f"物料建档 {mid}", r.get("ok"), ";".join(e for e in r.get("errors", []))[:60])
r = call("POST", "/api/insert", {"table": "products", "operator": OP, "data": {
    "material_id": MAT1, "customer_code": CUST, "product_category": "线管",
    "spec": "重复", "inner_diameter": 25.4, "weight": 1}})
check("重复物料编码被拒", not r.get("ok"), str(r.get("errors", [""]))[:50])

# ── S3 业务员: 报价录入 (系数定价) ─────────────────────────────
print("\n【S3 业务员】报价 QT-TEST01 (公斤价系数 1.08, 单价应=单重×1.08)")
r = doc("/api/docs/quotation", {
    "quote_no": "QT-TEST01", "customer_code": CUST, "quote_date": "2026-08-14",
    "currency": "USD", "payment_term": "T/T", "delivery_days": 30,
}, [
    {"material_id": MAT1, "quantity": 100, "price_coefficient": 1.08},
    {"material_id": MAT2, "quantity": 50, "price_coefficient": 1.08},
])
exp_price = round(28.5 * 1.08, 2)
exp_total = round(exp_price * 100 + round(50 * 1.08, 2) * 50, 2)
ok = r.get("ok") and abs(r.get("total_amount", 0) - exp_total) < 0.01
check("报价落库+公式定价正确", bool(ok),
      f"总额={r.get('total_amount')} 预期={exp_total} 错误={r.get('errors')}")

# ── S4 业务员: 报价转合同 ──────────────────────────────────────
print("\n【S4 业务员】报价转合同 SC-TEST01 (源报价应置 converted, 二次转应拒)")
r = doc("/api/docs/contract", {
    "contract_no": "SC-TEST01", "customer_code": CUST, "sign_date": "2026-08-14",
    "currency": "USD", "source_quote_no": "QT-TEST01", "delivery_deadline": "2026-09-15",
}, [
    {"material_id": MAT1, "quantity": 100, "unit_price": exp_price},
    {"material_id": MAT2, "quantity": 50, "unit_price": round(50 * 1.08, 2)},
])
check("合同落库", r.get("ok"), str(r.get("errors", "")))
st = sql("SELECT status FROM quotations WHERE quote_no='QT-TEST01'")
check("源报价已置 converted", st == "converted", f"status={st}")
r2 = doc("/api/docs/contract", {
    "contract_no": "SC-TESTXX", "customer_code": CUST, "sign_date": "2026-08-14",
    "source_quote_no": "QT-TEST01",
}, [{"material_id": MAT1, "quantity": 1, "unit_price": 1}])
check("已转化报价二次转合同被拒", not r2.get("ok"), str(r2.get("errors", [""]))[:40])

# ── S5 生产调度: 生产入库挂合同 ────────────────────────────────
print("\n【S5 生产调度】生产入库 IN-TEST01 (WH-01, 挂 SC-TEST01)")
r = doc("/api/docs/stock-in", {
    "in_no": "IN-TEST01", "in_type": "production", "warehouse_code": "WH-01",
    "in_date": "2026-08-14", "contract_no": "SC-TEST01",
}, [{"material_id": MAT1, "quantity": 100}])
check("生产入库(合同物料)", r.get("ok"), str(r.get("errors", "")))
inv = sql(f"SELECT quantity FROM inventory WHERE warehouse_code='WH-01' AND material_id='{MAT1}'")
check("WH-01 库存 +100", inv == "100", f"inv={inv}")
r2 = doc("/api/docs/stock-in", {
    "in_no": "IN-TESTXX", "in_type": "production", "warehouse_code": "WH-01",
    "in_date": "2026-08-14", "contract_no": "SC-TEST01",
}, [{"material_id": MAT3, "quantity": 1}])
check("合同外物料入库被拒", not r2.get("ok"), str(r2.get("errors", [""]))[:50])
r3 = doc("/api/docs/stock-in", {
    "in_no": "IN-TESTXY", "in_type": "production", "warehouse_code": "WH-01",
    "in_date": "2026-08-14",
}, [{"material_id": MAT1, "quantity": 1}])
check("生产入库不挂合同被拒", not r3.get("ok"), str(r3.get("errors", [""]))[:40])

# ── S6 保管员: 调拨 (本厂→临沂) ────────────────────────────────
print("\n【S6 保管员】调拨 OUT-TEST01 (WH-01 出) + IN-TEST02 (WH-03 入, 同号 TF-TEST01)")
r = doc("/api/docs/stock-out", {
    "out_no": "OUT-TEST01", "out_type": "transfer", "warehouse_code": "WH-01",
    "out_date": "2026-08-14", "transfer_ref": "TF-TEST01",
}, [{"material_id": MAT1, "quantity": 40}])
check("调拨出库 WH-01 -40", r.get("ok"), str(r.get("errors", "")))
r = doc("/api/docs/stock-in", {
    "in_no": "IN-TEST02", "in_type": "transfer", "warehouse_code": "WH-03",
    "in_date": "2026-08-14", "transfer_ref": "TF-TEST01",
}, [{"material_id": MAT1, "quantity": 40}])
check("调拨入库 WH-03 +40", r.get("ok"), str(r.get("errors", "")))
inv1 = sql(f"SELECT quantity FROM inventory WHERE warehouse_code='WH-01' AND material_id='{MAT1}'")
inv3 = sql(f"SELECT quantity FROM inventory WHERE warehouse_code='WH-03' AND material_id='{MAT1}'")
check("调拨后库存正确", inv1 == "60" and inv3 == "40", f"WH-01={inv1} WH-03={inv3}")
r2 = doc("/api/docs/stock-out", {
    "out_no": "OUT-TESTXX", "out_type": "transfer", "warehouse_code": "WH-01",
    "out_date": "2026-08-14",
}, [{"material_id": MAT1, "quantity": 1}])
check("调拨不填关联号被拒", not r2.get("ok"), str(r2.get("errors", [""]))[:40])

# ── S7 业务员: 发货超发拦截 ────────────────────────────────────
print("\n【S7 业务员】发货 200 卷 > 合同 100 卷 (应整单拦截回滚)")
r = doc("/api/docs/delivery", {
    "delivery_no": "DN-TEST01", "customer_code": CUST, "delivery_date": "2026-08-14",
}, [{"contract_no": "SC-TEST01", "contract_item_no": "001", "quantity": 200}])
check("超发被拦截", not r.get("ok"), str(r.get("errors", [""]))[:50])
dq = sql("SELECT delivered_qty FROM sales_contract_items WHERE contract_no='SC-TEST01' AND item_no='001'")
check("拦截后已发数未被污染", dq == "0", f"delivered={dq}")

# ── S8 业务员: 正常发货 (部分) ─────────────────────────────────
print("\n【S8 业务员】正常发货 DN-TEST01 = 40 卷 (合同应转 delivering)")
r = doc("/api/docs/delivery", {
    "delivery_no": "DN-TEST01", "customer_code": CUST, "delivery_date": "2026-08-14",
    "receiver": "测试收货人",
}, [{"contract_no": "SC-TEST01", "contract_item_no": "001", "quantity": 40}])
check("发货落库", r.get("ok"), str(r.get("errors", "")))
st = sql("SELECT status FROM sales_contracts WHERE contract_no='SC-TEST01'")
check("合同状态联动 delivering", st == "delivering", f"status={st}")

# ── S9 保管员: 销售出库挂发货单 ────────────────────────────────
print("\n【S9 保管员】销售出库 OUT-TEST02 (WH-03, 挂 DN-TEST01, 40卷装柜海运)")
r = doc("/api/docs/stock-out", {
    "out_no": "OUT-TEST02", "out_type": "sale", "warehouse_code": "WH-03",
    "out_date": "2026-08-14", "delivery_no": "DN-TEST01",
}, [{"material_id": MAT1, "quantity": 40}])
check("销售出库", r.get("ok"), str(r.get("errors", "")))
inv3 = sql(f"SELECT quantity FROM inventory WHERE warehouse_code='WH-03' AND material_id='{MAT1}'")
check("临沂仓库存归零", inv3 == "0", f"inv={inv3}")
r2 = doc("/api/docs/stock-out", {
    "out_no": "OUT-TESTXY", "out_type": "sale", "warehouse_code": "WH-03",
    "out_date": "2026-08-14", "delivery_no": "DN-TEST01",
}, [{"material_id": MAT2, "quantity": 1}])
check("发货单外物料出库被拒", not r2.get("ok"), str(r2.get("errors", [""]))[:50])

# ── S10 业务员+老板: 低价先发货拦截与特批 ──────────────────────
print("\n【S10 业务员/老板】低价新合同 SC-TEST02 (25.00 < 30.78) 发货应被拦, 特批放行")
r = doc("/api/docs/contract", {
    "contract_no": "SC-TEST02", "customer_code": CUST, "sign_date": "2026-08-14",
    "currency": "USD",
}, [{"material_id": MAT1, "quantity": 10, "unit_price": 25.00}])
check("低价合同落库", r.get("ok"), str(r.get("errors", "")))
r = doc("/api/docs/delivery", {
    "delivery_no": "DN-TEST02", "customer_code": CUST, "delivery_date": "2026-08-14",
}, [{"contract_no": "SC-TEST02", "contract_item_no": "001", "quantity": 1}])
check("低价先发货被拦截", not r.get("ok") and "price_gap_approved" in r.get("errors", [""])[0],
      str(r.get("errors", [""]))[:60])
r = doc("/api/docs/delivery", {
    "delivery_no": "DN-TEST02", "customer_code": CUST, "delivery_date": "2026-08-14",
    "price_gap_approved": True, "price_gap_reason": "客户确认高价旧单暂缓(e2e)",
}, [{"contract_no": "SC-TEST02", "contract_item_no": "001", "quantity": 1}])
check("老板特批放行", r.get("ok") and any("特批" in w for w in r.get("warnings", [])),
      str(r.get("errors", ""))[:50])

# ── S11 业务员: 关行 (空原因拒/有原因过/关后禁发) ──────────────
print("\n【S11 业务员】关行 SC-TEST02#001 (余量9/10=90%>5%)")
r = call("POST", "/api/contracts/SC-TEST02/items/001/close", {"operator": OP, "data": {"reason": ""}})
check("空原因关行被拒", not r.get("ok"), str(r.get("errors", [""]))[:40])
r = call("POST", "/api/contracts/SC-TEST02/items/001/close", {"operator": OP, "data": {"reason": "客户确认余量不要(e2e)"}})
check("有原因关行成功+超5%进复核清单",
      r.get("ok") and any("复核" in w for w in r.get("warnings", [])), str(r.get("warnings", ""))[:60])
st = sql("SELECT status FROM sales_contracts WHERE contract_no='SC-TEST02'")
check("全行了结合同自动 completed", st == "completed", f"status={st}")
r = doc("/api/docs/delivery", {
    "delivery_no": "DN-TEST03", "customer_code": CUST, "delivery_date": "2026-08-14",
    "price_gap_approved": True, "price_gap_reason": "x",
}, [{"contract_no": "SC-TEST02", "contract_item_no": "001", "quantity": 1}])
check("已关闭行再发货被拒", not r.get("ok"), str(r.get("errors", [""]))[:40])

# ── S12 业务员: 收款 + 提成吨位口径 ────────────────────────────
print("\n【S12 业务员】收款 RC-TEST01 挂 SC-TEST01; 提成吨位=实发41卷×28.5kg÷1000=1.1685吨")
r = call("POST", "/api/insert", {"table": "receipts", "operator": OP, "data": {
    "receipt_no": "RC-TEST01", "customer_code": CUST, "contract_no": "SC-TEST01",
    "amount": 1000.00, "currency": "USD", "paid_date": "2026-08-14", "status": "confirmed",
}})
check("收款录入", r.get("ok"), str(r.get("errors", ""))[:60])
ton = sql(f"""SELECT ROUND(SUM(COALESCE(NULLIF(di.actual_quantity,0), di.quantity) * p.weight / 1000), 4)
             FROM delivery_order_items di
             JOIN delivery_orders d ON d.delivery_no = di.delivery_no
             JOIN products p ON p.material_id = di.material_id
             JOIN sales_contracts sc ON sc.contract_no = di.contract_no
             WHERE sc.customer_code='{CUST}' AND d.status IN ('confirmed','shipped')""")
check("提成吨位实发口径正确", ton == "1.1685", f"tonnage={ton}")

# ── S13 保管员: 标签纸需求提示 + 辅料收发 ──────────────────────
print("\n【S13 保管员】标签纸需求(合同100卷→需100) → 采购入库200 → 生产领用40")
r = call("GET", "/api/aux/label-demand?contract_no=SC-TEST01")
line = (r.get("lines") or [{}])[0]
check("标签纸需求测算正确", line.get("required") == 100 and line.get("shortage") == 100,
      f"required={line.get('required')} in_stock={line.get('in_stock')} shortage={line.get('shortage')}")
r = call("POST", "/api/aux/stock-in", {"aux_code": "LP-TEST01", "warehouse_code": "AUX",
    "qty": 200, "source_type": "purchase", "source_no": "PO-TEST01", "operator": OP})
check("辅料采购入库 200", r.get("ok"), str(r.get("errors", ""))[:50])
r = call("POST", "/api/aux/stock-out", {"aux_code": "LP-TEST01", "warehouse_code": "AUX",
    "qty": 40, "source_type": "production_use", "source_no": "SC-TEST01", "operator": OP})
check("生产领用出库 40", r.get("ok"), str(r.get("errors", ""))[:50])
aux_inv = sql("SELECT quantity FROM aux_inventory WHERE aux_code='LP-TEST01' AND warehouse_code='AUX'")
check("辅料库存 200-40=160", aux_inv == "160", f"inv={aux_inv}")

# ── S14 保管员: 装柜后回填实发数 (🔴-4) ────────────────────────
print("\n【S14 保管员】回填 DN-TEST01 实发 38 (计划40, 短装2)")
r = call("POST", "/api/docs/delivery/actual", {"operator": OP, "data": {
    "delivery_no": "DN-TEST01",
    "items": [{"contract_no": "SC-TEST01", "contract_item_no": "001", "actual_quantity": 200}]}})
check("回填超合同量被拒", not r.get("ok"), str(r.get("errors", [""]))[:50])
r = call("POST", "/api/docs/delivery/actual", {"operator": OP, "data": {
    "delivery_no": "DN-TEST01",
    "items": [{"contract_no": "SC-TEST01", "contract_item_no": "001", "actual_quantity": 0}]}})
check("实发回填0给整行短装警告", r.get("ok") and any("短装" in w for w in r.get("warnings", [])),
      str(r.get("warnings", ""))[:60])
r = call("POST", "/api/docs/delivery/actual", {"operator": OP, "data": {
    "delivery_no": "DN-TEST01",
    "items": [{"contract_no": "SC-TEST01", "contract_item_no": "001", "actual_quantity": 38}]}})
check("回填实发38落库", r.get("ok"), str(r.get("errors", ""))[:50])
row = sql("""SELECT actual_quantity, short_qty FROM delivery_order_items
             WHERE delivery_no='DN-TEST01' AND contract_no='SC-TEST01'""")
check("实发38/短装2(生成列)", row == "38\t2", f"row={row!r}")
dq = sql("SELECT delivered_qty FROM sales_contract_items WHERE contract_no='SC-TEST01' AND item_no='001'")
check("合同已发数按差额修正 40→38", dq == "38", f"delivered={dq}")

# ── S15 保管员: 销售出库累计闸门 (🟡-13) ───────────────────────
print("\n【S15 保管员】DN-TEST01 实发38已出库40, 再出1卷应被累计闸门拒")
r = doc("/api/docs/stock-out", {
    "out_no": "OUT-TESTXZ", "out_type": "sale", "warehouse_code": "WH-01",
    "out_date": "2026-08-14", "delivery_no": "DN-TEST01",
}, [{"material_id": MAT1, "quantity": 1}])
check("累计出库超实发被拒", not r.get("ok") and "超发" in r.get("errors", [""])[0],
      str(r.get("errors", [""]))[:60])

# ── S16 业务员: 发货单作废 (🟡-7) ──────────────────────────────
print("\n【S16 业务员】DN-TEST04 发60卷 → 空原因作废拒 → 作废冲回已发数")
r = doc("/api/docs/delivery", {
    "delivery_no": "DN-TEST04", "customer_code": CUST, "delivery_date": "2026-08-14",
}, [{"contract_no": "SC-TEST01", "contract_item_no": "001", "quantity": 60}])
check("发货 DN-TEST04=60 落库", r.get("ok"), str(r.get("errors", ""))[:50])
dq = sql("SELECT delivered_qty FROM sales_contract_items WHERE contract_no='SC-TEST01' AND item_no='001'")
check("已发数累计 38+60=98", dq == "98", f"delivered={dq}")
r = call("POST", "/api/docs/delivery/cancel", {"operator": OP, "data": {
    "delivery_no": "DN-TEST04", "reason": ""}})
check("空原因作废被拒", not r.get("ok"), str(r.get("errors", [""]))[:40])
r = call("POST", "/api/docs/delivery/cancel", {"operator": OP, "data": {
    "delivery_no": "DN-TEST04", "reason": "客户改单重开(e2e)"}})
check("作废成功+冲回已发数", r.get("ok"), str(r.get("errors", ""))[:50])
dq = sql("SELECT delivered_qty FROM sales_contract_items WHERE contract_no='SC-TEST01' AND item_no='001'")
check("已发数冲回 98→38", dq == "38", f"delivered={dq}")
st = sql("SELECT status FROM sales_contracts WHERE contract_no='SC-TEST01'")
check("合同状态回到 delivering", st == "delivering", f"status={st}")
r = call("POST", "/api/docs/delivery/cancel", {"operator": OP, "data": {
    "delivery_no": "DN-TEST04", "reason": "再次作废"}})
check("重复作废幂等成功", r.get("ok") and any("cancelled" in w for w in r.get("warnings", [])),
      str(r.get("warnings", ""))[:50])
r = doc("/api/docs/stock-out", {
    "out_no": "OUT-TESTXW", "out_type": "sale", "warehouse_code": "WH-01",
    "out_date": "2026-08-14", "delivery_no": "DN-TEST04",
}, [{"material_id": MAT1, "quantity": 1}])
check("作废发货单不再放出库额度", not r.get("ok"), str(r.get("errors", [""]))[:60])

# ── S17 业务员: 借非交易月汇率给前端可见 WARN (🟡-8) ────────────
print("\n【S17 业务员】收款 paid_date=2027-01 (无当月汇率) 应带汇率WARN")
r = call("POST", "/api/insert", {"table": "receipts", "operator": OP, "data": {
    "receipt_no": "RC-TEST02", "customer_code": CUST, "contract_no": "SC-TEST01",
    "amount": 500.00, "currency": "USD", "paid_date": "2027-01-15", "status": "confirmed",
}})
check("非交易月汇率收款落库+WARN可见",
      r.get("ok") and any("汇率提示" in w for w in r.get("warnings", [])),
      f"ok={r.get('ok')} warnings={r.get('warnings')}")

# ── 清理 (逐条执行, 单条失败不中断, 最后核对) ───────────────────
print("\n【清理】删除全部 TEST 数据 (逐条执行)")
for stmt in [
    "DELETE FROM quotation_items WHERE quote_no LIKE '%-TEST%'",
    "DELETE FROM quotations WHERE quote_no LIKE '%-TEST%'",
    "DELETE FROM stock_out_items WHERE out_no LIKE '%-TEST%'",
    "DELETE FROM stock_out WHERE out_no LIKE '%-TEST%'",
    "DELETE FROM stock_in_items WHERE in_no LIKE '%-TEST%'",
    "DELETE FROM stock_in WHERE in_no LIKE '%-TEST%'",
    "DELETE FROM delivery_order_items WHERE delivery_no LIKE '%-TEST%'",
    "DELETE FROM delivery_orders WHERE delivery_no LIKE '%-TEST%'",
    "DELETE FROM receipts WHERE receipt_no LIKE '%-TEST%'",
    "DELETE FROM sales_contract_items WHERE contract_no LIKE '%-TEST%'",
    "DELETE FROM sales_contracts WHERE contract_no LIKE '%-TEST%'",
    "DELETE FROM inventory WHERE material_id LIKE 'M-Z9999-%'",
    "DELETE FROM stock_logs WHERE material_id LIKE 'M-Z9999-%'",
    "DELETE FROM aux_stock_moves WHERE aux_code='LP-TEST01'",
    "DELETE FROM aux_inventory WHERE aux_code='LP-TEST01'",
    "DELETE FROM aux_materials WHERE aux_code='LP-TEST01'",
    "DELETE FROM products WHERE material_id LIKE 'M-Z9999-%'",
    "DELETE FROM customers WHERE code='Z9999'",
    "DELETE FROM audit_logs WHERE operator='demo-test'",
]:
    sql(stmt)
leftover = sql("""SELECT (SELECT COUNT(*) FROM sales_contracts WHERE contract_no LIKE '%-TEST%')
  + (SELECT COUNT(*) FROM quotations WHERE quote_no LIKE '%-TEST%')
  + (SELECT COUNT(*) FROM products WHERE material_id LIKE 'M-Z9999-%')
  + (SELECT COUNT(*) FROM customers WHERE code='Z9999')
  + (SELECT COUNT(*) FROM aux_materials WHERE aux_code='LP-TEST01')
  + (SELECT COUNT(*) FROM delivery_orders WHERE delivery_no LIKE '%-TEST%')
  + (SELECT COUNT(*) FROM stock_in WHERE in_no LIKE '%-TEST%')
  + (SELECT COUNT(*) FROM stock_out WHERE out_no LIKE '%-TEST%')
  + (SELECT COUNT(*) FROM receipts WHERE receipt_no LIKE '%-TEST%')
  + (SELECT COUNT(*) FROM stock_logs WHERE material_id LIKE 'M-Z9999-%')
  + (SELECT COUNT(*) FROM audit_logs WHERE operator='demo-test')""")
check("测试数据已清零", leftover == "0", f"leftover={leftover}")

print("\n" + "=" * 64)
passed = sum(1 for _, c, _ in RESULTS if c)
print(f"结果: {passed}/{len(RESULTS)} 项通过")
if passed < len(RESULTS):
    print("失败项:")
    for n, c, d in RESULTS:
        if not c:
            print(f"  ❌ {n} — {d}")
    sys.exit(1)
print("全部通过 ✓")
