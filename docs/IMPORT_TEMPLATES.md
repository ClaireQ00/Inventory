# 导入模板说明

本目录已提供一组 CSV 模板文件，用于填充真实数据并验证当前进销存流程。建议将真实数据文件保存在本地 `data/` 或 `private/` 目录中，并确保这些目录被 `.gitignore` 忽略。

## 模板位置

- `sample/templates/`

已提供以下模板：

- `products_template.csv`
- `warehouses_template.csv`
- `suppliers_template.csv`
- `customers_template.csv`
- `inventory_template.csv`
- `purchase_orders_template.csv`
- `purchase_order_items_template.csv`
- `stock_in_template.csv`
- `stock_in_items_template.csv`
- `sales_contracts_template.csv`
- `sales_contract_items_template.csv`
- `delivery_orders_template.csv`
- `delivery_order_items_template.csv`
- `stock_out_template.csv`
- `stock_out_items_template.csv`

## 使用说明

1. 复制模板文件到本地 `data/` 或 `private/` 目录。
2. 用真实业务数据填充 CSV 文件。
3. 真实数据文件请勿加入版本控制。
4. 录入时请注意以下字段：
   - `product_id`、`warehouse_id`、`supplier_id`、`customer_id` 等字段目前使用数据库内部 ID。
   - 若你需要更方便的导入方式，可先将 `products`、`warehouses`、`suppliers`、`customers` 录入数据库，再使用其自增 ID。

## 建议的验证流程

1. 先导入基础数据：
   - `products`
   - `warehouses`
   - `suppliers`
   - `customers`
   - `inventory`
2. 再导入单据数据：
   - `purchase_orders` + `purchase_order_items`
   - `stock_in` + `stock_in_items`
   - `sales_contracts` + `sales_contract_items`
   - `delivery_orders` + `delivery_order_items`
   - `stock_out` + `stock_out_items`
3. 验证后，运行以下查询检查结果：
   - 当前库存查询
   - 销售合同发货情况
   - `stock_logs` 与 `inventory` 对账

## 注意事项

- 真实客户信息、合同金额、供应商价格等属于敏感数据，请严格隔离。
- 如需共享数据，请先脱敏，避免通过 Git 或公共渠道直接传输原始数据。
- 真实数据请保存在本地 `data/` 或 `private/` 目录，不要直接提交到仓库。
