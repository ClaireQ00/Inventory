-- ============================================================
-- 2026-08-14 合同明细行级状态 (客户部分取消场景)
-- ------------------------------------------------------------
-- 背景: 客户可能只放弃合同里的某一行 ("这个料不要了, 其他继续")。
--       原来只能整合同关单 (status=completed/cancelled), 粒度太粗,
--       导致"还欠"统计把客户已放弃的行也算成需求, 缺口预警失真。
-- 方案: sales_contract_items 加行级 status:
--   active  = 正常执行 (默认)
--   closed  = 客户放弃余量, 此余量不再计入任何"还欠/未发完/需求"统计
-- 整合同状态联动: 所有行都"发完或关闭" → completed (在 db_writer 发货/关行
-- 动作里检查, 逻辑同 2026-08-02 定的全发完置 completed)。
-- ============================================================

ALTER TABLE sales_contract_items
  ADD COLUMN status ENUM('active','closed') NOT NULL DEFAULT 'active' AFTER delivered_qty;

CREATE INDEX idx_sci_status ON sales_contract_items(status);
