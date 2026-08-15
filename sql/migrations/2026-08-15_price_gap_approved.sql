-- ============================================================
-- 2026-08-15 发货单低价特批留痕落库
-- ------------------------------------------------------------
-- 背景: BUSINESS_RULES.md 2026-08-14 变更要求"老板特批低价先发货"必须
--       在发货单头记录 price_gap_approved + price_gap_reason，并随审计留痕。
--       此前只存在于 HTTP 响应，前端弹窗关闭即丢失。
-- 本迁移: 给 delivery_orders 增加两列，用于持久化特批状态及原因。
-- ============================================================

ALTER TABLE delivery_orders
  ADD COLUMN price_gap_approved TINYINT NOT NULL DEFAULT 0 COMMENT '老板特批低价先发货(0=否,1=是) (2026-08-15)',
  ADD COLUMN price_gap_reason   VARCHAR(255) DEFAULT '' COMMENT '低价特批原因(留痕) (2026-08-15)';
