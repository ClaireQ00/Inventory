# 变更日志（CHANGELOG.md）

> 按时间倒序的阶段归纳（全量明细看 `git log`）。格式参考 Keep a Changelog。

## 2026-08-15 审查修复第①批「钱和账」

- 独立代码审查（docs/REVIEW_BY_CLAUDE_CODE.md）：4🔴 / 10🟡 / 10🔵，Kimi 逐条核对 23 成立 / 1 误判
- 修复 6 项（🔴-3/2/1, 🟡-9/5/6）：删孤立 JOIN、actual_quantity 闸门、price_gap 特批落库（含迁移 SQL 已执行）、SQLite 镜像补自然键、FOR UPDATE、draft 拒发
- 双回归全绿；api/streamlit 容器重启加载新代码

## 2026-08-14 规则强化

- 低价先发货 WARN 升级为拦截 + 老板特批机制（ee785c5）
- 合同行级关闭（客户部分取消余量）+ 原因必填 + 大额余量首页复核卡（ba8b925, 6dc4cde）
- 四角色 13 场景 demo 测试 41 断言全绿（38dfb07）

## 2026-08-11 ~ 08-13 主数据治理 + 报表

- 物料全量重编码 M-{客户编码}-{3位流水}、客户编码按业务员推荐（R12 铁律）
- 同物异名三道防线、拼音模糊搜索、内径标称英寸口径修正
- 8501 新增：单据链路图（报价→…→收款）、合同进度、客户订单总览、提成模块（R13 实发口径）

## 2026-08 上旬 录入端收官（F2.x）

- 报价/合同/发货/出入库/收款/汇率录入全线迁移 React，Streamlit 录入中心下线
- 前端生产容器（Nginx + 反代 /api），同事浏览器直达 :8082
- 辅料模块 M1（档案/库存/收发/标签纸需求测算/采购需求单）
- CSV 灌库幂等修复 + 双轨回写工具（R14 自然唯一键）

## 2026-08-01 快照重量链路（ADR-0005）

- 报价明细 weight_per_unit 快照化，永不回写主数据
- R11 反算取数快照优先；归位工具 clone_material.py

## 2026-07 下旬 SDD 体系 + 校验器

- 文档先行（GLOSSARY/BUSINESS_RULES/DATA_MODEL/SPECS/DESIGN/adr）
- local_validator 16 步校验 + normalize_csv 自动修 Excel 痕迹
- 外键改业务编号（ADR-0004），根治 AUTO_INCREMENT 漂移

## 2026-07 上旬 项目诞生

- 进销存 + 报关单据 + 应收收款三合一骨架，CSV 双轨，demo 数据生成器
