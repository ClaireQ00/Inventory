#!/usr/bin/env bash
# ============================================================
# CSV → MySQL 灌数脚本
# ------------------------------------------------------------
# 作用: 把 data/csv/ 下的 CSV 数据批量导入正在运行的 MySQL 容器。
#       文件名即表名 (products.csv -> products 表)。
#
# 前提: docker compose up -d 已经把数据库跑起来了。
#
# 用法:
#   bash scripts/load-csv-to-db.sh                # 灌 data/csv 下的真实数据
#   bash scripts/load-csv-to-db.sh --demo         # 先生成演示数据再灌
#   bash scripts/load-csv-to-db.sh --csv-dir <目录>  # 指定其他 CSV 目录
#
# 注意: 这是你(本地有真实数据时)用的脚本。远程团队只看数据的话不需要跑这个。
# ============================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fatal() { echo -e "${RED}[FATAL]${NC} $*"; exit 1; }

# ---------- 参数解析 ----------
USE_DEMO=0
CSV_DIR="data/csv"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) USE_DEMO=1; CSV_DIR="data/csv/demo_runtime"; shift;;
    --csv-dir) CSV_DIR="$2"; shift 2;;
    *) fatal "未知参数: $1";;
  esac
done

# ---------- 前置检查 ----------
command -v python3 >/dev/null || fatal "未找到 python3"
[[ -f docker-compose.yml ]] || fatal "当前目录没有 docker-compose.yml, 请在项目根目录运行"

# 容器是否在跑
if ! docker compose ps db --format json 2>/dev/null | grep -q "running"; then
  fatal "MySQL 容器没在跑, 请先执行: docker compose up -d"
fi

# ---------- 准备数据 ----------
if [[ "$USE_DEMO" -eq 1 ]]; then
  warn "--demo 模式: 生成演示假数据到 ${CSV_DIR}/"
  python3 tools/make_demo_data.py
elif [[ ! -d "$CSV_DIR" ]] || [[ -z "$(ls "$CSV_DIR"/*.csv 2>/dev/null)" ]]; then
  fatal "${CSV_DIR}/ 下没有 .csv 文件。放好真实数据后重跑, 或加 --demo 用演示数据"
fi

# ---------- 读取数据库连接信息 ----------
# 从 .env 读 (没有就用 compose 里的默认值)
if [[ -f .env ]]; then set -a; source .env; set +a; fi
DB_NAME="${MYSQL_DATABASE:-inventory_db}"
DB_USER="${MYSQL_USER:-inventory}"
DB_PASSWORD="${MYSQL_PASSWORD:-inventorypassword}"
CONTAINER="inventory-db"

info "目标数据库: ${DB_NAME} (容器 ${CONTAINER}, 用户 ${DB_USER})"
info "CSV 目录: ${CSV_DIR}"
echo ""

# ---------- 逐个 CSV 灌库 ----------
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SUCCESS=0
FAILED=0
for csv_file in "$CSV_DIR"/*.csv; do
  [[ -f "$csv_file" ]] || continue
  table_name="$(basename "$csv_file" .csv)"
  out_sql="$TMP_DIR/${table_name}.sql"

  # 第一步: CSV -> INSERT SQL 文件 (含反向校验, 失败会报错退出)
  if ! python3 tools/csv_to_sql.py "$csv_file" "$table_name" "$out_sql" --mode replace; then
    warn "  ✗ ${table_name}: 生成 SQL 失败 (数据有反向校验错误), 跳过"
    FAILED=$((FAILED + 1))
    continue
  fi

  # 第二步: 灌进 MySQL (通过容器内的 mysql 客户端执行)
  # 包一层外键检查开关: REPLACE INTO 在被外键引用时会触发 DELETE, 被约束拦截 (ERROR 1451)。
  # 灌数阶段先关掉, 灌完恢复, 不影响表里已定义的约束本身。
  #
  # ⚠️ pipefail 陷阱: set -e + 管道会在 mysql 非零退出时直接终止整个脚本,
  # 后续表就灌不到了。用 `|| true` + PIPESTATUS 显式接住退出码, 让单表失败
  # 只计入 FAILED 计数器, 不影响其他表。
  set +e
  {
    echo "SET FOREIGN_KEY_CHECKS=0;"
    cat "$out_sql"
    echo "SET FOREIGN_KEY_CHECKS=1;"
  } | docker exec -i "$CONTAINER" mysql -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" 2>&1 | grep -v "Using a password"
  PIPE_STATUS=("${PIPESTATUS[@]}")
  set -e
  if [[ "${PIPE_STATUS[1]}" -eq 0 ]]; then
    info "  ✓ ${table_name}: 已导入 ($(wc -l < "$out_sql" | tr -d ' ') 行 SQL)"
    SUCCESS=$((SUCCESS + 1))
  else
    warn "  ✗ ${table_name}: 导入 MySQL 失败 (mysql 退出码 ${PIPE_STATUS[1]})"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
info "完成: 成功 ${SUCCESS} 张表, 失败 ${FAILED} 张表"
if [[ "$FAILED" -gt 0 ]]; then
  warn "有失败项, 请检查上面的错误信息 (常见: CSV 列与表结构对不上, 或反向校验不过)"
  exit 1
fi
echo -e "${GREEN}全部导入成功。可浏览器打开 http://localhost:8080 查看。${NC}"
