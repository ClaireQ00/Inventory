-- 提成系数表 (2026-08-13 老板): 业务员提成的"规则层"预留
-- 三种提成方式: quantity=按量(系数单位 元/吨) / price=按价格 / receipt_time=按回款时间
-- 系数现在未定, 先建表; 老板给了系数后 INSERT 即生效, 不必改代码
-- 坏账规则(预留, 文档见 BUSINESS_RULES R13): 坏账损失 1% 以内不报警,
-- 超过 1% 的部分按坏账金额等额扣减业务提成
CREATE TABLE IF NOT EXISTS commission_rules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    salesperson_code VARCHAR(8) NOT NULL,           -- 业务员代码 (salespersons.code)
    method ENUM('quantity','price','receipt_time') NOT NULL,  -- 提成方式
    coefficient DECIMAL(12,6) NOT NULL,             -- 系数: 按量=元/吨; 按价=比例; 按回款时间=分档系数
    tier_note VARCHAR(128) DEFAULT NULL,            -- 分档说明 (如 "30天内回款" / "月结60天")
    effective_from DATE NOT NULL,                   -- 生效起期 (系数可随时间调整, 留历史)
    effective_to DATE DEFAULT NULL,                 -- NULL=至今有效
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    remark VARCHAR(255) DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sp (salesperson_code, method, is_active),
    FOREIGN KEY (salesperson_code) REFERENCES salespersons(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务员提成系数表(三种方式:按量元/吨/按价/按回款时间;坏账超1%等额扣减规则见R13)';
