# ============================================================
# Inventory 项目 - 应用镜像
# ------------------------------------------------------------
# 这个镜像封装了"数据校验 + CSV 转 SQL"工具链。
# 团队成员装好 Docker 后, 一条命令就能跑出和你本机完全一样的环境。
#
# 技术栈说明: 本项目只用 Python 标准库 (sqlite3 等), 不需要 pip install,
# 因此基础镜像用 python:3.11-slim 即可, 体积小、构建快。
# ============================================================

FROM python:3.11-slim

# 设置工作目录 (容器内的"项目根")
WORKDIR /app

# 先只 COPY 脚本依赖, 利用 Docker 层缓存: 代码不改变时不会重装
COPY tools/ ./tools/
COPY scripts/ ./scripts/
COPY sql/ ./sql/
COPY sample/ ./sample/

# 校验脚本默认会把演示/真实数据写到 data/csv/
# 镜像里先建好空目录, 运行时再通过 volume 挂载真实数据进去 (可选)
RUN mkdir -p data/csv

# 赋予执行权限
RUN chmod +x scripts/*.sh

# 默认入口: 一键跑端到端校验 (等价于本机的 bash scripts/run_local_validation.sh)
# 团队成员 docker run 时可覆盖, 例如:
#   docker run --rm inventory python3 tools/csv_to_sql.py ...
ENTRYPOINT ["bash", "scripts/run_local_validation.sh"]
