-- 2026-08-11 业务员基础资料 + 客户编码补全迁移
-- 背景: 老板定客户编码规则 = 字母(业务员) + 4位数字(客户终身号, 首位=首次引入业务员数字编码)
-- 1. 新建 salespersons 业务员档案 (后期客户管理/回款/提成/统计的锚点)
-- 2. 按现有 596 个客户编号统计出的 字母↔首位数字 写入种子
-- 3. Q024/Q025 → Q0024/Q0025 补全为4位 (先子表后母表, FK 是 NO ACTION)

START TRANSACTION;

CREATE TABLE IF NOT EXISTS salespersons (
    id           INT AUTO_INCREMENT PRIMARY KEY COMMENT '业务员ID',
    code         VARCHAR(8)   NOT NULL UNIQUE  COMMENT '业务员代码(客户编码的首字母, 如 A/D/Q)',
    name         VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '姓名(回填期可空, 待补充)',
    digit        CHAR(1)      NOT NULL         COMMENT '客户编码首位数字(该业务员的数字编码, 0-9)',
    phone        VARCHAR(32)  DEFAULT NULL     COMMENT '电话',
    commission_rate DECIMAL(6,4) DEFAULT NULL  COMMENT '提成比例(预留, 后期业务提成管理)',
    is_active    TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '在职: 1是 0否',
    remark       VARCHAR(255) DEFAULT ''       COMMENT '备注',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务员档案(客户编码首字母/首位数字的权威来源)';

-- 种子: 从现有客户编号统计出的唯一主数字 (名称待老板补充)
INSERT INTO salespersons (code, name, digit, remark) VALUES
    ('A', '', '8', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('B', '', '6', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('C', '', '0', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('D', '', '1', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('E', '', '9', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('F', '', '5', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('H', '', '7', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('K', '', '7', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('L', '', '4', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('P', '', '0', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('Q', '', '0', '默认序列: 非业务员引入/公共客户, 姓名待补充'),
    ('T', '', '7', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('W', '', '9', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('X', '', '9', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('Y', '', '2', '2026-08-11 按客户编号统计回填, 姓名待补充'),
    ('Z', '', '9', '2026-08-11 按客户编号统计回填, 姓名待补充')
ON DUPLICATE KEY UPDATE digit=VALUES(digit);

-- Q 序列补全 3位→4位。注意 FK 是 NO ACTION, 顺序必须是:
-- ① 先补建新码母行 → ② 子表改挂新码 → ③ 删旧码母行 (先改子表会被 fk_do_customer 等拦住)
INSERT INTO customers (code, name, contact_person, phone, address, bank_account, brand_name, company_profiles, billing_profiles, is_active, remark)
SELECT 'Q0024', name, contact_person, phone, address, bank_account, brand_name, company_profiles, billing_profiles, is_active, remark FROM customers WHERE code='Q024';
INSERT INTO customers (code, name, contact_person, phone, address, bank_account, brand_name, company_profiles, billing_profiles, is_active, remark)
SELECT 'Q0025', name, contact_person, phone, address, bank_account, brand_name, company_profiles, billing_profiles, is_active, remark FROM customers WHERE code='Q025';
UPDATE products        SET customer_code='Q0024' WHERE customer_code='Q024';
UPDATE delivery_orders SET customer_code='Q0024' WHERE customer_code='Q024';
UPDATE quotations      SET customer_code='Q0024' WHERE customer_code='Q024';
UPDATE receipts        SET customer_code='Q0024' WHERE customer_code='Q024';
UPDATE sales_contracts SET customer_code='Q0024' WHERE customer_code='Q024';
UPDATE products        SET customer_code='Q0025' WHERE customer_code='Q025';
UPDATE delivery_orders SET customer_code='Q0025' WHERE customer_code='Q025';
UPDATE quotations      SET customer_code='Q0025' WHERE customer_code='Q025';
UPDATE receipts        SET customer_code='Q0025' WHERE customer_code='Q025';
UPDATE sales_contracts SET customer_code='Q0025' WHERE customer_code='Q025';
DELETE FROM customers WHERE code IN ('Q024','Q025');

COMMIT;
