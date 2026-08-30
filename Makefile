# ============================================================
# Inventory 质量门槛 (2026-08-15 加)
# 用法:
#   make lint      语法级门槛, 秒级 (pre-commit 自动跑, 暂存区含 .py 时)
#   make test      e2e 门槛, ~40s, 打真实 API (需 docker 容器在跑)
#   make validate  16 步业务校验, ~30s, SQLite 镜像不碰 MySQL
#   make check     完整门槛 = lint + test + validate (pre-push 自动跑)
# 约定: Claude 改完代码必须 make check 全绿才提交/推送; 不过就修复或回滚。
#       Kimi 只读, 不参与此循环。
# 说明: 项目测试是自研 e2e (tests/), 非 pytest 用例, 故 test 不走 pytest;
#       mypy 暂不进硬门槛 (存量代码无类型标注, 全量报错无意义),
#       待类型渐进补齐后再加入。ruff 未安装时自动跳过 (pip install ruff 启用)。
# ============================================================

.PHONY: lint test validate check help

lint:
	@fail=0; for f in tools/*.py api/*.py tests/*.py; do \
		python3 -m py_compile "$$f" || fail=1; \
	done; \
	if [ "$$fail" -eq 1 ]; then echo "❌ lint FAIL (py_compile)"; exit 1; \
	else echo "✓ lint: py_compile 全部通过"; fi
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check --select E9,F63,F7,F82 tools api tests; \
	else echo "(ruff 未安装, 跳过; pip install ruff 启用)"; fi

test:
	python3 tests/demo_roleplay_test.py
	python3 tests/run_tests.py

validate:
	bash scripts/run_local_validation.sh --demo

check: lint test validate
	@echo ""
	@echo "✓✓✓ 完整门槛全绿: lint + e2e + 16 步校验"

help:
	@grep -E '^#   make ' Makefile | sed 's/^#   //'
