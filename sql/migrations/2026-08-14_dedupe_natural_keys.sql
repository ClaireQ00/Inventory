-- ============================================================
-- 2026-08-14 去重 + item_no 格式规范化 + 明细表自然唯一键
-- ------------------------------------------------------------
-- 背景: load-csv-to-db.sh 用 csv_to_sql.py --mode replace 生成 REPLACE INTO,
--       但 delivery_order_items / stock_in_items / stock_out_items /
--       shipping_record_items 四张明细表只有自增 id 主键、没有自然唯一键,
--       REPLACE 失去锚点退化成纯追加 → 每跑一次校验脚本就重复灌一遍
--       (实测累计 6~8 倍重复)。
-- 本迁移:
--   1) 删除重复行 (每组自然键保留最小 id, 即首次写入的行)
--   2) item_no / contract_item_no 浮点格式 ('1.0') 规范化为三位补零 ('001'),
--      与 CSV 约定及 SC20260802001 等新单据一致
--      (pandas 读 Excel 时把 '001' 吃成 1.0 的历史遗留)
--   3) 给四张明细表补自然唯一键, REPLACE INTO 从此幂等
-- 执行前已备份: data/backups/inventory_db_20260814_pre_dedupe.sql
-- ============================================================

SET FOREIGN_KEY_CHECKS=0;

-- ---------- 1) 去重 ----------
DELETE d1 FROM delivery_order_items d1
JOIN delivery_order_items d2
  ON d1.delivery_no      = d2.delivery_no
 AND d1.contract_no      = d2.contract_no
 AND d1.contract_item_no = d2.contract_item_no
 AND d1.material_id      = d2.material_id
 AND d1.id > d2.id;

DELETE a FROM stock_in_items a
JOIN stock_in_items b
  ON a.in_no = b.in_no AND a.material_id = b.material_id AND a.id > b.id;

DELETE a FROM stock_out_items a
JOIN stock_out_items b
  ON a.out_no = b.out_no AND a.material_id = b.material_id AND a.id > b.id;

DELETE a FROM shipping_record_items a
JOIN shipping_record_items b
  ON a.shipping_no = b.shipping_no AND a.material_id = b.material_id AND a.id > b.id;

-- ---------- 2) item_no 浮点格式规范化 ----------
UPDATE quotation_items
   SET item_no = LPAD(CAST(CAST(item_no AS DECIMAL(10,1)) AS UNSIGNED), 3, '0')
 WHERE item_no REGEXP '^[0-9]+\\.[0-9]+$';

UPDATE sales_contract_items
   SET item_no = LPAD(CAST(CAST(item_no AS DECIMAL(10,1)) AS UNSIGNED), 3, '0')
 WHERE item_no REGEXP '^[0-9]+\\.[0-9]+$';

UPDATE delivery_order_items
   SET contract_item_no = LPAD(CAST(CAST(contract_item_no AS DECIMAL(10,1)) AS UNSIGNED), 3, '0')
 WHERE contract_item_no REGEXP '^[0-9]+\\.[0-9]+$';

-- ---------- 3) 自然唯一键 (让 REPLACE INTO 幂等) ----------
ALTER TABLE delivery_order_items
  ADD UNIQUE KEY uk_doi_doc_item (delivery_no, contract_no, contract_item_no);

ALTER TABLE stock_in_items
  ADD UNIQUE KEY uk_sii_doc_material (in_no, material_id);

ALTER TABLE stock_out_items
  ADD UNIQUE KEY uk_soi_doc_material (out_no, material_id);

ALTER TABLE shipping_record_items
  ADD UNIQUE KEY uk_sri_doc_material (shipping_no, material_id);

SET FOREIGN_KEY_CHECKS=1;
