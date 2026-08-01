# tests/ 独立测试套件

## 这是什么

T2.X 任务要求：让 4 类"故意出错"的校验场景有真实代码覆盖，但**不污染 demo 数据**
（demo 必须 0 错误是铁律）。所以这里单独建一套测试，每次运行时会用 demo 生成器
造一份**临时假数据**放进 `tests/fixtures/<场景名>/`，再故意改坏其中一张表，断言校验器能正确报警。

## 怎么跑

```bash
python3 tests/run_tests.py
```

期望输出：`结果: ✓ 全部通过 (4 个用例)`。任何用例失败会打印具体断言信息并返回非 0 退出码。

## 覆盖的 4 个场景

| # | 场景 | 预期 | 测的是 |
| --- | --- | --- | --- |
| ① | 米重×长度 vs 单重偏差 >5% | WARN，不阻止生成 SQL | `csv_to_sql.py::check_cross_field_consistency` |
| ② | 手填派生列 `outer_diameter` 偏 0.1mm | ERROR，阻止生成 SQL | `csv_to_sql.py::apply_derived_rules` 反向校验 |
| ③ | 报关短装 20% 超 UCP600 ±5% + 贷记单 pending 挂账 >90 天 | 两个 ERROR | `local_validator.py` 第 10/11 步 |
| ④ | 外币业务存在但汇率只录到上月 | ERROR | `local_validator.py` 第 12 步 |

## 目录约定

- `tests/fixtures/` 是**运行期生成**的临时数据（已被 `.gitignore` 排除），不要手工改。
- 用例数据与 `data/csv/demo/` 完全隔离，改坏也不影响真实 demo。
- 测试直接 import `tools/` 下的模块（`csv_to_sql.py` / `local_validator.py` / `make_demo_data.py`），无第三方依赖。
