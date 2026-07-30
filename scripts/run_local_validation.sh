#!/usr/bin/env bash
# ============================================================
# 本地真实数据验证 - 一键启动脚本
# ============================================================
#
# 类比: 这就是工厂流水线的总开关
# 一按下去: 检查环境 -> 检查敏感数据 -> 导入CSV -> 跑校验 -> 出报告
#
# 使用方法:
#   bash scripts/run_local_validation.sh           # 用 data/csv 下的数据
#   bash scripts/run_local_validation.sh --demo    # 先生成演示数据再跑
#
# 你只需要在 data/csv 下放好真实数据 CSV, 这个脚本搞定一切
# ============================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# 颜色输出, 让新手也能看清状态
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fatal() { echo -e "${RED}[FATAL]${NC} $*"; exit 1; }

# ---------- 0. 参数解析 ----------
USE_DEMO=0
if [[ "${1:-}" == "--demo" ]]; then
  USE_DEMO=1
fi

# ---------- 1. 环境检查 ----------
info "步骤 1/4: 检查环境..."
command -v python3 >/dev/null  || fatal "未找到 python3, 请先安装 Python 3"
info "  python3: $(python3 --version)"

# ---------- 2. 敏感数据保护检查 ----------
info "步骤 2/4: 检查敏感数据..."
if bash scripts/check-sensitive-data.sh; then
  info "  敏感数据检查通过"
else
  fatal "敏感数据检查未通过, 请先处理再继续"
fi

# ---------- 2b. 模板 ↔ Schema 同步检查 ----------
info "步骤 2b/4: 检查模板字段与 schema 一致..."
if bash scripts/check-template-schema-sync.sh; then
  info "  模板字段一致"
else
  # 不致命, 只 warn: 用户可能临时改 schema 测试, 不强制阻止校验
  warn "  模板字段与 schema 不一致, 详见上面输出 (不阻止校验, 但建议尽快同步)"
fi

# ---------- 3. 准备数据 ----------
info "步骤 3/4: 准备 CSV 数据..."

if [[ "$USE_DEMO" -eq 1 ]]; then
  warn "  --demo 模式: 用 tools/make_demo_data.py 生成演示数据 (假但完整)"
  warn "  ⚠️ 演示数据写到 data/csv/demo_runtime/ (不会覆盖 data/csv/ 下的真实数据)"
  python3 tools/make_demo_data.py
  # 演示模式: 让 local_validator.py 读 demo_runtime 目录
  CSV_DIR_ARG="--csv-dir data/csv/demo_runtime"
elif [[ ! -d data/csv ]] || [[ -z "$(ls data/csv/*.csv 2>/dev/null)" ]]; then
  warn "  data/csv 目录下没有真实 .csv 文件, 自动生成演示数据到 demo_runtime/"
  warn "  真实数据请按 sample/templates/*_template.csv 的格式, 填好后放到 data/csv 下"
  python3 tools/make_demo_data.py
  CSV_DIR_ARG="--csv-dir data/csv/demo_runtime"
else
  info "  使用 data/csv 下已有的数据 (共 $(ls data/csv/*.csv 2>/dev/null | wc -l | tr -d ' ') 个 .csv 文件)"
  CSV_DIR_ARG=""
fi

# ---------- 4. 跑验证 ----------
info "步骤 4/4: 跑端到端业务流程校验..."
if python3 tools/local_validator.py $CSV_DIR_ARG; then
  echo ""
  echo -e "${GREEN}============================================================${NC}"
  echo -e "${GREEN}✓ 全部通过${NC}"
  echo -e "${GREEN}============================================================${NC}"
  exit 0
else
  echo ""
  echo -e "${RED}============================================================${NC}"
  echo -e "${RED}✗ 校验未通过, 请按上面的错误信息修正 data/csv 里的数据${NC}"
  echo -e "${RED}============================================================${NC}"
  exit 1
fi
